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
Đây là lần chạy đầu, để nguyên mặc định của lab. Probe xác nhận runtime CUDA thấy được RTX
4050 nên labkit tự đặt ngl=99.

Đường cong phẳng: 76.7 / 76.8 / 76.8 / 77.1 / 76.7 tok/s. Chênh giữa -t 1 và -t 20 là 0.5%,
tức nằm trong nhiễu. Khi cả 35 layer đã nằm trên GPU thì -t không còn tác dụng gì, vì nó
chỉ điều khiển threadpool của backend CPU, mà lúc đó CPU chỉ còn sampling token với đẩy byte
qua HTTP. Một thread làm cũng xong.

Tôi giữ file này lại chứ không coi là lần chạy hỏng. So với 01-tuning-tg128.md (cùng model,
cùng grid, chỉ khác ngl=0) thì đúng knob đó đáng 2.32 lần. Cùng một máy, cùng một knob, giá
trị của nó do bottleneck đang hoạt động quyết định.
