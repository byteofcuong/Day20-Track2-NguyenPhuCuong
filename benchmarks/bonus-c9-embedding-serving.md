# Bonus C9 — Embedding serving

Nguyễn Phú Cường · Windows, llama.cpp b10488 · embedding server chạy ngl=0 (CPU) vì chat
server đang giữ GPU · corpus 8 doc, dim 1536

```powershell
$env:LAB_N_GPU_LAYERS='0'; .\lab.ps1 serve-embed
.venv\Scripts\python bonus\serving-regimes\embedding-serving.py `
    --base-url http://127.0.0.1:8081/v1
```

## Retrieval

Query: "Does embedding serving use a KV cache and a decode loop like chat serving?"

| # | cosine | Document |
|--:|--:|---|
| 1 | 0.845 | Embedding serving is prefill-bound: one forward pass, no KV cache, no decode loop. |
| 2 | 0.783 | RadixAttention reuses a shared prompt prefix across requests via a radix tree. |
| 3 | 0.739 | Speculative decoding drafts several tokens and verifies them in one forward pass. |

Document đúng xếp hạng 1, nhưng khoảng cách tới document sai chỉ 0.062 và cả ba đều nằm
trong dải 0.74 đến 0.85. Đúng triệu chứng của embedder yếu đã phân tích ở bonus/c8. Với 8
document thì thứ hạng vẫn đúng, corpus lớn thì biên 0.06 sẽ bị nhiễu nuốt.

## Throughput theo batch size

| batch | latency (ms) | texts/s | latency mỗi text (ms) |
|--:|--:|--:|--:|
| 1 | 376.0 | 2.7 | 376.0 |
| 2 | 560.3 | 3.6 | 280.2 |
| 4 | 540.2 | 7.4 | 135.1 |
| 8 | 917.0 | 8.7 | 114.6 |
| 16 | 1588.5 | 10.1 | 99.3 |

Từ batch 1 lên 16, throughput tăng 3.7 lần nhưng latency mỗi request tăng 4.2 lần. Chi phí
biên mỗi text giảm từ 376 xuống 99 ms, tức static batching mua throughput bằng cách trả bằng
latency của request đơn lẻ, và đường cong đã bắt đầu bão hoà (8 lên 16 chỉ còn thêm 16%).

## Vì sao ngược với chat serving

| | Chat / decode | Embedding |
|---|---|---|
| Forward pass mỗi request | 1 prefill + N decode step | 1, hết |
| KV cache | có, sống suốt request | không |
| Nút thắt | băng thông bộ nhớ khi decode | compute khi prefill |
| Batching | continuous | static |
| Tăng batch | throughput tăng, latency gần như giữ nguyên | throughput tăng, latency tăng tuyến tính |
| Đo bằng | TTFT + TPOT | latency mỗi batch |

Chat có vòng decode kéo dài nên continuous batching mới có nghĩa, request mới nhập được vào
batch đang chạy ở decode step kế tiếp mà không phải đợi request cũ xong. Đó chính là cái
n_busy_slots_per_decode 3.97/4 đo được ở track 02.

Embedding không có vòng decode nào để nhập vào. Mỗi text đúng một forward pass rồi xong, nên
không có gì để continuous cả. Cách duy nhất tăng throughput là gom nhiều text vào cùng một
forward pass, và cái giá là text đầu tiên trong batch 16 phải chờ 15 text kia.

## Hệ quả khi phục vụ cả hai sau một autoscaler

Hai regime đòi hai chiến lược ngược nhau, nên đây là phần đáng nói nhất.

Chỉ số để scale khác nhau. Chat nên scale theo queue depth hoặc requests_deferred vì số slot
là thứ khan hiếm, đúng như track 02 đo được. Embedding nên scale theo tokens/s của prefill
vì nó nghẽn ở compute chứ không ở chỗ ngồi.

Ý nghĩa của việc latency tăng cũng trái ngược. Ở chat, latency tăng khi batch đầy là dấu
hiệu bão hoà, cần thêm replica. Ở embedding, latency tăng theo batch là hành vi thiết kế;
autoscaler nào coi đó là quá tải sẽ scale ra vô ích và còn làm giảm hiệu quả, vì batch nhỏ
hơn thì throughput mỗi replica cũng thấp hơn.

Hồ sơ tài nguyên cũng khác. Chat cần VRAM cho KV cache tỉ lệ với parallel nhân ctx. Embedding
không cần KV cache, nó cần đủ compute và chỗ cho activation của một batch lớn.

Kết luận thực tế là đừng đặt chung sau một autoscaler với một bộ metric. Tách hai deployment
với policy riêng. Đây cũng là lý do các stack production tách embedding và reranker ra khỏi
LLM serving thay vì nhét chung một endpoint.

## Giới hạn phải khai báo

Demo dùng lại chat GGUF ở pooling mode để khỏi tải thêm model, nên biên similarity mới chỉ
0.06. Cùng vấn đề đã phân tích kỹ ở bonus/c8-semantic-cache.md. Retrieval thật cần embedding
model chuyên dụng.

Số throughput ở trên đo trên CPU vì GPU đang giữ chat server, chạy trên GPU thì số tuyệt đối
sẽ cao hơn nhiều. Thứ cần rút ra là hình dạng đường cong, throughput bão hoà dần còn latency
tăng tuyến tính, và nó không phụ thuộc vào việc chạy ở đâu.
