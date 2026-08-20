# 01 - Tune: thread-count sweep

Model `gemma-4-E2B-it-UD-Q4_K_XL.gguf` · host `Windows-AMD64` · llama.cpp `b10488`
CPU: **14 physical · 20 logical** cores · `ngl=99` · metric `tg128`

| threads (-t) | tg128 (tok/s) | vs best |
|:--|--:|--:|
| 1 | 76.7 | 100% |
| 7 | 76.8 | 100% |
| 14 | 76.8 | 100% |
| 20 | 77.1 | 100% |
| 40 | 76.7 | 99% |

**Best**: `-t 20` at 77.1 tok/s
**Slowest tested**: `-t 40` at 76.7 tok/s (1.01x spread)
**Against the physical-core default** (`-t 14`, 76.8 tok/s): 1.00x

Use this in your run:

```bash
LAB_N_THREADS=20 make bench
```

## Your explanation

_Where is the knee, and why there? If the peak sits at your physical core count
and drops above it, say what the extra threads are competing for. If your curve
does something else -- flat, or still climbing at 2x logical cores -- say that
instead and reason about why. A result that contradicts the expected shape is
worth more than one that matches it, as long as you explain it._

**Giải thích của tôi (Nguyễn Phú Cường):**

Đây là lần chạy đầu tiên, với `ngl=99` — tức cấu hình mặc định của lab trên máy này, vì
`labkit.n_gpu_layers()` xác nhận runtime CUDA thấy được RTX 4050 nên tự đặt ngl=99.

**Đường cong phẳng: 76.7 / 76.8 / 76.8 / 77.1 / 76.7 tok/s.** Chênh lệch giữa `-t 1` và
`-t 20` là 0.5%, nằm trong nhiễu đo. Nói cách khác, khi toàn bộ 35 layer đã nằm trên
GPU, `-t` — knob quan trọng nhất của track này — **không còn tác dụng gì**.

Lý do: `-t` chỉ điều khiển threadpool của backend CPU. Khi offload trọn vẹn, mọi phép
nhân ma trận của decode chạy bằng CUDA kernel; CPU chỉ còn việc sampling token và đẩy
byte qua HTTP. Một thread thừa sức làm phần đó, nên thread thứ 2 đến thứ 40 không có
việc.

Đây là điều đáng ghi lại chứ không phải một lần chạy hỏng: **một knob chỉ có giá trị
khi nó chạm vào đúng bottleneck đang hoạt động.** So cùng `01-tuning-tg128.md` (cùng
model, cùng grid, chỉ khác `ngl=0`) thì `-t` đáng giá 2.32× — cùng một knob, cùng một
máy, và giá trị của nó do bottleneck quyết định chứ không phải do bản thân knob.
