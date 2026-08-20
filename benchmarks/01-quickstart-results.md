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
Q2 decode nhanh hơn Q4 1.17 lần (99.0 so với 84.9 tok/s) và nhẹ hơn 0.73 GB. TTFT thì gần
như y hệt, 188 so với 201 ms, vì prefill nghẽn ở compute chứ không ở số byte weight đọc lên.

Tôi bật lần lượt hai server và hỏi cùng 5 câu ở temperature 0. Câu dễ chấm thì hoà: cả hai
đều ra 17*24 = 408 và trích xuất JSON đúng. Câu cần kiến thức thì Q2 sai kiểu khó thấy: nó
bảo PagedAttention cấp phát bộ nhớ contiguous (ngược hẳn, cơ chế này sinh ra để KV cache
không cần liền khối), và mở đầu một câu trả lời bằng "GGUF (GPT-GPU)".

Nên với tôi là không đáng. Q4 2.97 GB vẫn vừa 6 GB VRAM, tôi chưa cần tiết kiệm 0.73 GB để
đổi lấy câu trả lời lật ngược nội dung. Chỉ khi VRAM ép thật, kiểu phải chạy thêm model thứ
hai hoặc nâng ctx lên nhiều, tôi mới tính lại.
