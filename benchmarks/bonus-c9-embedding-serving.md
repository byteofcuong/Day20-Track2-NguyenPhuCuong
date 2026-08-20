# Bonus C9 — Embedding serving: một regime phục vụ khác hẳn

*Nguyễn Phú Cường · Windows-AMD64 · llama.cpp `b10488` · embedding server chạy `ngl=0`
(CPU), chat server giữ GPU · corpus 8 doc, dim = 1536*

```powershell
$env:LAB_N_GPU_LAYERS='0'; .\lab.ps1 serve-embed        # :8081
.venv\Scripts\python bonus\serving-regimes\embedding-serving.py `
    --base-url http://127.0.0.1:8081/v1
```

## 1. Retrieval hoạt động

Query: *"Does embedding serving use a KV cache and a decode loop like chat serving?"*

| # | cosine | Document |
|--:|--:|---|
| 1 | 0.845 | Embedding serving is prefill-bound: one forward pass, no KV cache, no decode loop. |
| 2 | 0.783 | RadixAttention reuses a shared prompt prefix across requests via a radix tree. |
| 3 | 0.739 | Speculative decoding drafts several tokens and verifies them in one forward pass. |

Document đúng xếp hạng 1. Nhưng khoảng cách tới document sai chỉ là **0.062**, và cả ba
đều nằm trong dải hẹp 0.74–0.85 — đúng triệu chứng của embedder yếu đã phân tích trong
`bonus/c8-semantic-cache.md`. Với corpus 8 document thì thứ hạng 1 vẫn đúng; với corpus
lớn, biên 0.06 sẽ bị nhiễu nuốt chửng.

## 2. Throughput theo batch size (prefill-bound)

| batch | latency (ms) | texts/s | latency mỗi text (ms) |
|--:|--:|--:|--:|
| 1 | 376.0 | 2.7 | 376.0 |
| 2 | 560.3 | 3.6 | 280.2 |
| 4 | 540.2 | 7.4 | 135.1 |
| 8 | 917.0 | 8.7 | 114.6 |
| 16 | 1588.5 | 10.1 | 99.3 |

Từ batch 1 lên batch 16: throughput tăng **3.7×** (2.7 → 10.1 texts/s), trong khi latency
mỗi request tăng **4.2×** (376 → 1588 ms). Chi phí biên mỗi text giảm từ 376 ms xuống
99 ms — tức **static batching mua throughput bằng cách trả bằng latency của request đơn
lẻ**, và đường cong đang bắt đầu bão hoà ở batch 16 (8→16 chỉ còn +16%).

## 3. Vì sao đường cong này ngược với chat serving

| | Chat / decode (track 02) | Embedding (bài này) |
|---|---|---|
| Số forward pass mỗi request | 1 prefill + N decode step | **1 forward pass, hết** |
| KV cache | có, tồn tại suốt request | **không có** |
| Nút thắt | băng thông bộ nhớ khi decode | **compute khi prefill** |
| Batching | **continuous** — request vào/ra từng decode step | **static** — gom rồi bắn một lượt |
| Tăng batch thì sao | throughput tăng, latency gần như không đổi | throughput tăng, **latency tăng tuyến tính** |
| Đo bằng | TTFT + TPOT | chỉ có latency mỗi batch |

Chat serving có vòng decode kéo dài, nên continuous batching có ý nghĩa: một request mới
có thể **nhập vào batch đang chạy** ở decode step kế tiếp mà không phải đợi request cũ
xong. Đó chính là điều `n_busy_slots_per_decode = 3.97/4` đã đo được ở
`02-server-batching-u50.md`.

Embedding không có vòng decode để nhập vào. Mỗi text là đúng một forward pass, rồi xong.
Vì thế không có gì để "continuous" cả — cách duy nhất tăng throughput là **gom nhiều text
vào cùng một forward pass** để chia sẻ chi phí khởi động kernel và lấp đầy đơn vị tính
toán. Đó là static batching, và nó đánh đổi thẳng: text đầu tiên trong batch 16 phải chờ
15 text kia được xử lý cùng.

## 4. Hệ quả khi phục vụ cả hai sau một autoscaler

Đây là phần đáng nói nhất, vì hai regime đòi hai chiến lược **mâu thuẫn nhau**:

- **Chỉ số scale khác nhau.** Chat nên scale theo `requests_deferred` / queue depth (số
  slot là thứ khan hiếm — đúng như đã đo ở track 02). Embedding nên scale theo *tokens/s
  của prefill*, vì nó bị chặn bởi compute chứ không phải số chỗ ngồi.
- **Ý nghĩa của "latency tăng" trái ngược nhau.** Ở chat, latency tăng khi batch đầy là
  dấu hiệu bão hoà, cần thêm replica. Ở embedding, latency tăng theo batch là **hành vi
  thiết kế** — autoscaler nào coi đó là tín hiệu quá tải sẽ scale ra vô ích và làm giảm
  hiệu quả (batch nhỏ hơn = throughput thấp hơn trên mỗi replica).
- **Hồ sơ tài nguyên khác nhau.** Chat cần VRAM cho KV cache tỉ lệ với
  `--parallel × ctx`. Embedding không cần KV cache — nó cần đủ compute và chỗ cho
  activation của một batch lớn.
- **Kết luận thực tế:** đừng đặt chung sau một autoscaler và một bộ HPA metric. Tách thành
  hai deployment với policy riêng. Đây cũng là lý do các stack production tách
  embedding/reranker service ra khỏi LLM serving thay vì nhét chung một endpoint.

## 5. Giới hạn phải khai báo

Demo này dùng lại **chat GGUF** (Gemma 4 E2B) ở pooling mode để không phải tải thêm model.
Đó là lý do biên similarity ở mục 1 chỉ 0.06, và là cùng một vấn đề đã phân tích kỹ trong
`bonus/c8-semantic-cache.md` (decoder mean-pooled không phải sentence encoder). Retrieval
thật cần embedding model chuyên dụng — Qwen3-Embedding, BGE-M3, EmbeddingGemma — được train
contrastive.

Ngoài ra, con số throughput ở mục 2 đo trên **CPU** (`ngl=0`), vì GPU đang giữ chat server;
trên GPU các con số tuyệt đối sẽ cao hơn nhiều. **Hình dạng đường cong** — throughput tăng
dần bão hoà, latency tăng tuyến tính — mới là thứ cần rút ra, và nó không phụ thuộc vào
việc chạy ở đâu.
