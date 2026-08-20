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

_Where is the knee, and why there? If the peak sits at your physical core count
and drops above it, say what the extra threads are competing for. If your curve
does something else -- flat, or still climbing at 2x logical cores -- say that
instead and reason about why. A result that contradicts the expected shape is
worth more than one that matches it, as long as you explain it._

**Giải thích của tôi (Nguyễn Phú Cường):**

Sweep này chạy với `ngl=0` (ép decode về CPU) để cô lập đúng tác dụng của `-t`. Nếu để
mặc định `ngl=99`, decode nằm trên RTX 4050 và đường cong phẳng tuyệt đối — xem
`01-tuning-tg128-ngl99.md`.

**Knee nằm ở `-t 14`, đúng bằng số physical core.** Nhưng phần đáng chú ý không phải
đỉnh, mà là chỗ đường cong *ngừng dốc*:

- `-t 1 → 7`: 6.1 → 13.9 tok/s, tức **2.28×** khi tăng 7× số thread.
- `-t 7 → 14`: 13.9 → 14.1 tok/s, chỉ **+1.4%** dù thêm 7 core nữa.

Nếu decode bị giới hạn bởi FLOPs thì đoạn 7→14 phải cho gần 2×. Nó cho 1.4%, nghĩa là
từ khoảng 7 thread trở đi máy đã **bão hoà băng thông bộ nhớ**, không phải bão hoà năng
lực tính toán. Điều này hợp lý về mặt số học: mỗi token decode phải kéo lại toàn bộ
weight của các layer được kích hoạt từ DRAM. File Q4_K_XL nặng 2.97 GB; Gemma 4 E2B là
kiến trúc "effective-2B" nên phần thực sự đọc mỗi token nhỏ hơn con số đó, nhưng dù lấy
cận dưới thì 14.1 tok/s vẫn tương ứng với hàng chục GB/s — cùng bậc độ lớn với trần
thực tế của DDR5 dual-channel trên laptop. Thêm core không thêm băng thông; nó chỉ tạo
thêm thread cùng xếp hàng trước cùng một memory controller.

Hai điểm cuối là hai cơ chế khác nhau, không nên gộp:

- `-t 20` (dùng hết logical core) tụt xuống 12.2 tok/s (**87%**). 20 logical core ở đây
  là 14 physical + 6 SMT sibling của P-core. Hai hyperthread dùng chung L1/L2 và chung
  cổng load-store; với workload đã nghẽn ở memory, sibling chỉ làm bẩn cache và thêm
  đồng bộ, không thêm băng thông.
- `-t 40` (oversubscribe 2×) tụt tiếp còn 8.6 tok/s (**61%**). Đây không còn là chuyện
  cache mà là scheduling: 40 thread tranh 20 lõi logic, mỗi barrier ở cuối một layer
  phải chờ thread bị OS preempt, nên toàn bộ đoàn phải đợi thằng chậm nhất.

Một lưu ý về CPU hybrid: i7-13650HX có 6 P-core + 8 E-core. `-t 7` (nửa số physical)
đã đạt 98% đỉnh, nghĩa là gần như toàn bộ throughput đến từ P-core; 8 E-core cộng thêm
được đúng 1.4%. Với kiến trúc big.LITTLE, "physical core count" không phải một con số
đồng nhất — và `llama-bench` không cho biết thread được gán vào loại core nào.
