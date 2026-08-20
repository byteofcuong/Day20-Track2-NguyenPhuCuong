# 01 - Tune: thread-count sweep

Model `gemma-4-E2B-it-UD-Q4_K_XL.gguf` · host `Windows-AMD64` · llama.cpp `b10488`
CPU: **14 physical · 20 logical** cores · `ngl=0` · metric `tg128`

| threads (-t) | tg128 (tok/s) | vs best |
|:--|--:|--:|
| 1 | 6.1 | 43% |
| 7 | 13.9 | 98% |
| 14 | 14.1 | 100% |
| 20 | 12.2 | 87% |
| 40 | 8.6 | 61% |

**Best**: `-t 14` at 14.1 tok/s
**Slowest tested**: `-t 1` at 6.1 tok/s (2.32x spread)
**Against the physical-core default** (`-t 14`, 14.1 tok/s): 1.00x

Use this in your run:

```bash
LAB_N_THREADS=14 make bench
```

## Your explanation
Sweep này chạy với ngl=0 để ép decode về CPU, nếu không thì mọi thứ nằm trên GPU và đường
cong phẳng hết (xem 01-tuning-tg128-ngl99.md).

Đỉnh ở -t 14, đúng số physical core. Nhưng chỗ đáng nhìn không phải cái đỉnh mà là chỗ
đường cong hết dốc: từ 1 lên 7 thread được 2.28 lần, từ 7 lên 14 chỉ thêm 1.4%. Gấp đôi
core mà gần như không được gì thì không phải nghẽn ở compute, mà là băng thông bộ nhớ đã
cạn từ khoảng 7 thread. Cũng hợp lý, vì decode phải kéo lại weight của các layer active từ
DRAM cho từng token rồi chỉ làm một phép nhân ma trận với vector trên đó. Thêm core không
thêm được kênh nhớ.

Hai điểm bên phải đỉnh là hai chuyện khác nhau. -t 20 dùng hết logical core, còn 87%: hai
hyperthread chung L1/L2 và chung cổng load-store, workload đã nghẽn ở memory thì sibling
chỉ làm bẩn cache. -t 40 còn 61% là chuyện lập lịch: 40 thread tranh 20 lõi, mà ggml đồng
bộ ở cuối mỗi layer, nên mỗi barrier phải chờ thread bị OS cắt lượt, cả đoàn đi theo tốc độ
thằng chậm nhất.

Một điểm nữa về CPU hybrid: con này 6 P-core + 8 E-core, mà -t 7 đã đạt 98% đỉnh. Gần như
toàn bộ throughput đến từ P-core, 8 E-core góp đúng 1.4%. Với big.LITTLE thì "số physical
core" không phải một con số đồng nhất, và llama-bench cũng không cho biết thread rơi vào
loại core nào.
