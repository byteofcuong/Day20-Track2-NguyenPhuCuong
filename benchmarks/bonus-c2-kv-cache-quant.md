# Bonus C2 - KV cache quantization (`--cache-type-k/v`)

Host `Windows-AMD64` - model `gemma-4-E2B-it-UD-Q4_K_XL.gguf` -
llama.cpp `b10488` - `threads=14` -
`ngl=99` - `--parallel 4`
Latency and quality measured at `ctx=2048`, `temperature=0`, warm-up discarded.

## 1. Memory footprint

| ctx | cache-type-k/v | GPU in use (MiB) | GPU delta vs idle (MiB) | Host RSS (MiB) |
|:--|--:|--:|--:|--:|
| 2048 | `f16` | 2855 | +1662 | 1974 |
| 2048 | `q8_0` | 2826 | +1713 | 1974 |
| 8192 | `f16` | 2914 | +1766 | 1977 |
| 8192 | `q8_0` | 2865 | +1733 | 1976 |
| 16384 | `f16` | 2950 | +1831 | 1979 |
| 16384 | `q8_0` | 2890 | +1779 | 1978 |

- ctx 2048: `q8_0` holds **+29 MiB** less GPU memory than `f16` (2855 -> 2826 MiB in use).
- ctx 8192: `q8_0` holds **+49 MiB** less GPU memory than `f16` (2914 -> 2865 MiB in use).
- ctx 16384: `q8_0` holds **+60 MiB** less GPU memory than `f16` (2950 -> 2890 MiB in use).

GPU figures are whole-device readings from `nvidia-smi`, taken ~3 s after the server
reports healthy, so they include the desktop's own usage; the delta column is the part
this server added. Host RSS is the llama-server process itself.

## 2. Latency and quality at ctx 2048

| cache-type-k/v | TTFT P50/P95 (ms) | TPOT P50 (ms) | Decode (tok/s) | Eval correct |
|:--|--:|--:|--:|--:|
| `f16` | 204 / 230 | 13.83 | 72.3 | 9/10 |
| `q8_0` | 205 / 208 | 14.89 | 67.2 | 9/10 |

The eval is 5 arithmetic + 5 JSON-extraction prompts, graded automatically at
`temperature=0`. It is a *regression check*, not a benchmark: the question is whether
the answers change when the KV cache loses precision.

## Your finding
Không mất accuracy, nhưng cũng gần như không tiết kiệm được gì, và phải trả bằng tốc độ.
Với máy này thì q8_0 là một trade tệ.

Mức tiết kiệm nhỏ đến mức bất ngờ: 29 MiB ở ctx 2048, 49 MiB ở 8192, 60 MiB ở 16384, tức
khoảng 2% tổng VRAM đang dùng. Đáng lẽ q8_0 phải cắt đôi KV cache, nên con số bé thế này
nói lên rằng KV cache không phải phần chiếm chỗ: gần như toàn bộ 1.7 GB server thêm vào là
weight. Có hai lý do cộng lại, Gemma 4 E2B dùng chung KV ở 20 trong 35 layer nên chỉ 15
layer có KV riêng, và ctx 2048-16384 chia cho 4 slot vẫn là ngân sách rất nhỏ so với 2.97 GB
weight. Xu hướng thì vẫn đúng chiều, tiết kiệm tăng dần theo ctx, nên phải lên tới hàng trăm
nghìn token hoặc hàng chục slot thì con số mới đủ lớn để quan tâm.

Về latency thì chậm hơn 7%, TPOT từ 13.83 lên 14.89 ms. Không phải nhiễu, và có lý do rõ:
mỗi decode step phải dequantize KV trước khi tính attention, mà ở ctx nhỏ thế này thì KV
chưa đủ lớn để việc đọc ít byte hơn bù lại chi phí giải nén. TTFT gần như không đổi, hợp lý
vì prefill ghi KV chứ không đọc lại nhiều.

Chất lượng thì cả hai đều 9/10, và quan trọng hơn con số đó là cả hai fail đúng cùng một
item với output trùng khít từng ký tự (đều trả `{"product": "mouse", "price": "25 dollars"}`
trong khi grader của tôi chờ price là số). Đó là grader quá chặt chứ model trích xuất đúng.
Việc hai cấu hình cho ra output giống hệt nhau ở cả 10 prompt là bằng chứng mạnh hơn con số
9/10: ở ctx này q8_0 không làm đổi hành vi model.

Nên tôi sẽ không bật knob này. Nó đổi 2% VRAM lấy 7% throughput, mà VRAM không phải thứ tôi
đang thiếu, nút thắt thật của tôi là số slot. Tôi chỉ đổi ý khi KV cache thành phần chi phối
bộ nhớ, kiểu 16 slot với ctx 32k, và lúc đó phải đo lại chứ không suy ra từ bài này.

Chỗ này cũng cho thấy vì sao không nên bê thẳng câu "FP8 KV cache là bộ nhớ miễn phí" từ
deck sang máy mình. Trên GPU datacenter phục vụ context dài batch lớn thì KV cache đúng là
chiếm chỗ thật và FP8 thắng rõ. Trên laptop 4 slot với 512 token mỗi slot thì cùng knob đó
là chi phí thuần. Cơ chế không đổi, cái đổi là KV cache có phải phần lớn của bộ nhớ hay
không.
