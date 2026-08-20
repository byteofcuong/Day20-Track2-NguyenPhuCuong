# 02 - Continuous batching under load (u50)

Host `Windows-AMD64` · `--parallel 4` · 15 samples over
60s at 2.0s intervals · raw CSV: `02-server-metrics-u50.csv`

| Gauge | Peak observed |
|:--|--:|
| `n_busy_slots_per_decode` (avg/decode) | 3.97 of 4 slots (99%) |
| `requests_processing` | 4 |
| `requests_deferred` | 45 |
| `kv_cache_usage_ratio` | n/a — not exported by llama.cpp `b10488` |
| `tokens_predicted_total` (final) | 24170 |

Highest sampled value was **3.97 of 4** slots. Note this gauge is llama.cpp's *average* busy slots per decode step, so the number below is the highest average we sampled, not an instantaneous maximum batch width. A peak near 1 means
requests were served one at a time -- either the load was too light to overlap, or
they arrived too far apart. A peak approaching `--parallel` means the scheduler was
genuinely packing concurrent requests into shared decode steps.
`requests_deferred` went above zero: more requests arrived than there were slots, so some waited. That wait is the queue time in your P95.

## Your observation
Peak 3.97 trên 4 slot, và requests_processing chạm trần 4 ở mọi mẫu. Batching chạy đúng như
mô tả, gần như không có decode step nào để trống slot.

Con số này không mâu thuẫn với effective concurrency 41.5 bên 02-server-results.md, vì hai
bên đo hai thứ. busy_slots đo occupancy trong engine, trần cứng của nó là --parallel 4 nên
không bao giờ vượt được 4. Effective concurrency tính theo Little's Law thì đếm cả request
đang xếp hàng ngoài. Chỗ nối hai số là requests_deferred, đỉnh 45: 45 chờ cộng 4 đang chạy
là 49, khớp với 50 user locust mô phỏng.

Tôi tin cả hai, nhưng nếu chỉ đọc busy_slots 3.97/4 thì sẽ kết luận sai là server đang chạy
ngon. Engine đúng là không lãng phí chu kỳ nào, chỉ là 45 người đang đợi ngoài cửa. Phần
chênh giữa 49 request trong hệ thống và 4 slot đang chạy chính là queue time đã thổi P95 từ
3.1 lên 15 giây.
