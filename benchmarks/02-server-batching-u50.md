# 02 - Continuous batching under load (u50)

Host `Windows-AMD64` · `--parallel 4` · 15 samples over
60s at 2.0s intervals · raw CSV: `02-server-metrics-u50.csv`

| Gauge | Peak observed |
|:--|--:|
| `n_busy_slots_per_decode` (avg/decode) | 3.97 of 4 slots (99%) |
| `requests_processing` | 4 |
| `requests_deferred` | 45 |
| `kv_cache_usage_ratio` | n/a — not exported by llama.cpp `b10488` |
| `tokens_predicted_total` (final) | 20492 |

Highest sampled value was **3.97 of 4** slots. Note this gauge is llama.cpp's *average* busy slots per decode step, so the number below is the highest average we sampled, not an instantaneous maximum batch width. A peak near 1 means
requests were served one at a time -- either the load was too light to overlap, or
they arrived too far apart. A peak approaching `--parallel` means the scheduler was
genuinely packing concurrent requests into shared decode steps.
`requests_deferred` went above zero: more requests arrived than there were slots, so some waited. That wait is the queue time in your P95.

## Your observation

_What was the peak batch width, and does it match the effective concurrency in
`02-server-results.md`? If the two disagree, which do you trust and why?_

**Nhận xét của tôi (Nguyễn Phú Cường):**

Peak batch width là **3.97 / 4 slot (99%)**, và `requests_processing` chạm trần 4 ở mọi
mẫu. Continuous batching hoạt động đúng như mô tả: scheduler gói gần như tối đa 4 request
vào chung mỗi decode step. Con số này là *trung bình* slot bận mỗi `llama_decode()`, nên
3.97 nghĩa là gần như không có decode step nào chạy với slot rỗng.

**Hai con số này KHÔNG mâu thuẫn với effective concurrency 40.9 trong
`02-server-results.md` — chúng đo hai thứ khác nhau:**

- `n_busy_slots_per_decode` = 3.97 đo **occupancy bên trong engine**: có bao nhiêu
  request đang thực sự được decode. Trần cứng của nó là `--parallel 4`, nên nó *không thể*
  vượt 4 dù có bao nhiêu user đi nữa.
- Effective concurrency = 40.9 (Little's Law, RPS × latency trung bình) đếm **tất cả
  request đang nằm trong hệ thống**, gồm cả những request đang xếp hàng chờ slot.

Chỗ nối hai con số lại là `requests_deferred`, đỉnh **45**. 45 request bị hoãn + 4 đang
chạy ≈ 49, khớp gần như chính xác với 50 user mà locust mô phỏng, và cũng khớp với
effective concurrency 40.9 (thấp hơn một chút vì Little's Law chỉ tính request đã hoàn
thành trong cửa sổ đo).

**Tôi tin cả hai, nhưng mỗi con số trả lời một câu hỏi khác nhau.** Nếu chỉ đọc
`busy_slots = 3.97/4` tôi sẽ kết luận sai rằng server đang chạy hoàn hảo — 99% utilisation
mà. Đúng là engine không lãng phí chu kỳ nào; vấn đề là 45 request khác đang đợi ngoài
cửa. Đây chính xác là lý do deck tách "throughput" khỏi "goodput@SLO": utilisation cao là
điều kiện cần, không phải bằng chứng người dùng đang được phục vụ tử tế. Phần chênh giữa
49 request trong hệ thống và 4 slot đang chạy **chính là** queue time đã thổi P95 từ
3.9 s lên 17 s.
