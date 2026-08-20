# 01 - Measure: latency baseline

Model `Gemma 4 E2B` · host `Windows-AMD64` · llama.cpp `b10488`
Settings: `threads=14` `ngl=99` `ctx=2048`
`max_tokens=64` · warm-up discarded
Completed requests: `UD-Q4_K_XL` 10/10 · `UD-Q2_K_XL` 10/10

| Quantization | Size (GB) | Load (ms) | TTFT P50/P95 (ms) | TPOT P50/P95 (ms) | E2E P50/P95/P99 (ms) | Decode (tok/s) |
|:--|--:|--:|--:|--:|--:|--:|
| UD-Q4_K_XL | 2.97 | 4888 | 201 / 384 | 11.8 / 12.4 | 946 / 1120 / 1120 | 84.9 |
| UD-Q2_K_XL | 2.24 | 4115 | 188 / 370 | 10.1 / 10.6 | 819 / 999 / 999 | 99.0 |

- **TTFT** = prefill. Short prompts keep it small; long-context RAG is where it explodes.
- **TPOT** = per-output-token decode cost, bounded by memory bandwidth. `decode tok/s = 1000 / TPOT_p50`.
- `UD-Q2_K_XL` decodes **1.17x faster** than `UD-Q4_K_XL` here, for 0.73 GB less on disk.

## Your observation

_Is the smaller quantization worth it on your machine? Compare the numbers above,
then judge the answer quality yourself: run `make serve` on each and ask the same
question twice. Size and speed are measurable; usefulness is your call._

**Nhận xét của tôi (Nguyễn Phú Cường):**

Trên máy này (RTX 4050, cả hai quant đều offload trọn vẹn lên GPU với `ngl=99`),
`UD-Q2_K_XL` decode nhanh hơn `UD-Q4_K_XL` **1.17×** (99.0 so với 84.9 tok/s, tức TPOT
10.1 so với 11.8 ms) và nhỏ hơn **0.73 GB**. TTFT gần như không đổi (188 so với 201 ms ở
P50, và ở P95 thì 370 so với 384 ms — chênh lệch nằm trong nhiễu) — đúng như kỳ vọng:
prefill bị giới hạn bởi compute chứ không phải số byte của weight, nên bớt bit gần như
không giúp gì cho prefill. Phần thắng nằm trọn ở decode, nơi mỗi token phải đọc lại weight
của các layer active, và đó chính là dấu hiệu decode ở đây bounded bởi memory bandwidth.

**Có đáng không? Với tôi là KHÔNG.** Tôi đã bật lần lượt hai server và hỏi cùng 5 câu ở
`temperature=0`. Hai câu dễ chấm thì hoà: cả hai đều trả lời `17 * 24 = 408` và đều trích
xuất đúng `{"name": "Mai", "age": 27}`. Nhưng ở câu cần kiến thức, Q2 sai theo kiểu khó
phát hiện:

- Hỏi PagedAttention giải quyết vấn đề gì: Q4 trả lời "virtual memory system for attention
  keys and values"; Q2 trả lời cơ chế này cho phép cấp phát bộ nhớ **"contiguous"** — ngược
  hẳn với ý tưởng cốt lõi (PagedAttention tồn tại chính là để KV cache **không** cần liền
  khối).
- Hỏi về các format GGUF: Q2 mở đầu bằng "GGUF (GPT-GPU)" — một cụm bịa hoàn toàn.

Đổi lại 1.17× tốc độ và 0.73 GB, tôi nhận về những câu trả lời trôi chảy nhưng lật ngược
nội dung kỹ thuật. Với 6 GB VRAM thì `UD-Q4_K_XL` (2.97 GB) vẫn nằm gọn, nên tôi không có
lý do phải tiết kiệm 0.73 GB đó. Tôi sẽ chỉ chọn Q2 nếu VRAM ép buộc: ví dụ cần chạy đồng
thời một model thứ hai, hoặc phải nâng `--ctx-size` lên mức mà KV cache cạnh tranh chỗ với
weight.
