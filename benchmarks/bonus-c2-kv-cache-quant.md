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

_Did the memory saving cost you accuracy? Trading memory for quality is not a win --
say which side of that trade this machine landed on, and at what context length the
saving starts to matter._

**Finding của tôi (Nguyễn Phú Cường):**

**Không mất accuracy — nhưng cũng gần như không tiết kiệm được gì, và phải trả bằng tốc
độ. Trên máy này `q8_0` KV cache là một trade tồi.**

**1. Tiết kiệm bộ nhớ: nhỏ đến mức gây thất vọng.** 29 MiB ở ctx 2048, 49 MiB ở ctx 8192,
60 MiB ở ctx 16384 — tức khoảng **2% tổng VRAM đang dùng**. Đáng lẽ q8_0 phải cắt đôi KV
cache (16 bit → 8 bit), nên nếu KV thực sự lớn thì mức tiết kiệm phải lớn hơn nhiều. Con
số nhỏ này nói lên rằng **KV cache không phải phần chiếm chỗ**: gần như toàn bộ ~1.7 GB
mà server thêm vào là weight. Có hai lý do cộng dồn: Gemma 4 E2B dùng chung KV ở 20 trong
35 layer (nên chỉ 15 layer thực sự có KV riêng), và tổng ctx 2048–16384 chia cho 4 slot
vẫn là ngân sách rất nhỏ so với 2.97 GB weight.

Xu hướng vẫn đúng chiều — mức tiết kiệm tăng theo ctx (29 → 49 → 60 MiB), đúng như dự
đoán vì KV cache tỉ lệ với context. Ngoại suy thô: phải lên tới ctx hàng trăm nghìn token,
hoặc `--parallel` hàng chục slot, thì con số này mới đủ lớn để đáng quan tâm.

**2. Latency: chậm hơn 7%.** TPOT P50 đi từ **13.83 ms lên 14.89 ms** (72.3 → 67.2 tok/s).
Đây không phải nhiễu, và nó có cơ chế rõ ràng: mỗi decode step phải **dequantize KV cache
trở lại** trước khi tính attention. Ở ctx nhỏ như thế này, KV chưa đủ lớn để việc đọc ít
byte hơn bù lại được chi phí dequantize — nên ta trả phí giải nén mà không nhận được lợi
ích băng thông. TTFT gần như không đổi (204 → 205 ms P50), hợp lý vì prefill ghi KV chứ
không đọc lại nhiều.

**3. Chất lượng: không suy giảm.** Cả hai đều đạt **9/10**, và quan trọng hơn con số:
**cả hai fail đúng cùng một item với output giống hệt nhau từng ký tự** — cùng trả về
`{"product": "mouse", "price": "25 dollars"}` trong khi grader của tôi chờ `price: 25`.
Đó là grader quá chặt (model trích xuất đúng, chỉ giữ đơn vị), không phải model sai. Việc
hai cấu hình cho ra output trùng khít ở cả 10 prompt là bằng chứng mạnh hơn con số 9/10:
ở ctx này, `q8_0` KV **không làm đổi hành vi model**.

**Kết luận triển khai:** tôi sẽ **không** bật `--cache-type-k/v q8_0` trong cấu hình của
mình. Nó đổi 2% VRAM lấy 7% throughput, mà VRAM lại không phải thứ tôi đang thiếu — điểm
nghẽn thật của tôi là **số slot** (`bonus-gpu-offload-sweep.md` và
`02-server-results.md`: `requests_deferred` đỉnh 45). Ngưỡng để tôi đổi ý là khi KV cache
trở thành phần chi phối bộ nhớ: `--parallel` lớn kèm ctx dài, ví dụ 16 slot × 32k context.
Lúc đó phép tính lật ngược — nhưng phải đo lại chứ không suy ra từ bài này.

Điều này cũng cho thấy vì sao không nên bê thẳng "FP8 KV cache là bộ nhớ miễn phí" từ
deck sang máy mình. Trên GPU datacenter phục vụ context dài với batch lớn, KV cache thực
sự là phần chiếm chỗ và FP8 là chiến thắng rõ ràng. Trên một laptop chạy 4 slot × 512
token, cùng knob đó là chi phí thuần. Cơ chế không đổi; cái đổi là KV cache có phải phần
lớn của bộ nhớ hay không.
