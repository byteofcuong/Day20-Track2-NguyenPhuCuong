# 02 - Serve: load test + saturation reading

Host `Windows-AMD64` · llama.cpp `b10488` ·
`--parallel 4` · `ctx=2048` · `threads=14` ·
`ngl=99`

| Users | Reqs | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Eff. concurrency | Failures |
|:--|--:|--:|--:|--:|--:|--:|--:|
| 10 | 216 | 3.69 | 1800 | 3100 | 3800 | 6.8 | 0.0% |
| 50 | 204 | 3.43 | 13000 | 15000 | 16000 | 41.5 | 0.0% |

*Effective concurrency = RPS x average latency (Little's Law) -- how many requests were
really in flight, regardless of how many users locust simulated. It counts queued requests
too, so the occupancy/slot ratio can legitimately exceed 1.0; it is occupancy, not
utilisation. For true slot utilisation use the server's own gauges (`make metrics`).*

## What these two runs say

| Going from 10 to 50 users | |
|:--|--:|
| Offered load | 5x |
| Throughput actually delivered | **0.93x** (19% of linear) |
| P95 latency | **4.84x** |
| Effective concurrency at 50 users | 41.5 vs `--parallel 4` slots (occupancy/slot ratio 10.36) |

**Saturated.** Throughput delivered only 0.93x for 5x the offered load, and effective concurrency (41.5) is at or above all 4 decode slots. Saturation sets in somewhere at or below 50 users; the load you added beyond that point became queue time rather than throughput.

Throughput moved 0.93x while P95 moved 4.84x. That gap is the goodput argument: past saturation you buy throughput by spending latency, and if your SLO is a P95 target then the requests you added are no longer being served within it. (This lab does not fix an SLO number for you -- pick one in your write-up and state how much goodput you keep at it.)

## Your reading
Server bão hoà từ dưới 10 user. Con số làm tôi tin là RPS: 3.69 xuống 3.43 khi tải tăng 5
lần. Không phải đứng yên mà đi lùi 7%.

Phần latency tăng thêm là queue time chứ không phải compute, và tôi dựa vào ba thứ. Thứ
nhất, P95 tăng 4.84 lần trong khi RPS giảm; nếu mỗi request tốn nhiều compute hơn thì phải
thấy ở thời gian decode, mà TPOT thì không đổi. Thứ hai, server tự khai requests_deferred
đỉnh 45, tức 45 request đang chờ slot. Thứ ba, busy_slots 3.97/4 cho thấy engine không hề
rảnh, nó chạy hết công suất, chỉ là không còn chỗ.

Effective concurrency 41.5 so với 4 slot ra tỉ lệ 10.36, tức mỗi slot có chừng 10 request
xếp hàng. Theo Little's Law thì một request đợi khoảng 9 lượt trước khi tới lượt mình, nhân
với ~1.2 giây phục vụ là ra đúng vùng 12-15 giây đo được. Phần RPS mất đi chính là chi phí
xếp lịch cho đống hàng đợi đó.

Nếu đặt SLO P95 dưới 5 giây thì ở 10 user tôi giữ được gần như toàn bộ goodput ở 3.69 RPS,
còn ở 50 user P95 là 15 giây nên goodput về 0, dù throughput danh nghĩa vẫn 3.43 RPS.

Knob tôi đổi trước là --parallel, từ 4 lên 8-12, kèm nâng --ctx-size. Nút thắt đã được định
danh là số slot chứ không phải tốc độ tính, nên phải nới đúng cái đang thiếu. Tôi không tăng
-t vì sweep ngl=99 cho thấy nó vô tác dụng khi đã offload GPU, và không hạ xuống Q2 vì nó
chỉ được 1.17 lần trong khi khoảng cách cần bù là 10 lần. Phải nâng ctx cùng lúc vì 2048
chia cho 4 slot đã chỉ còn 512 token mỗi slot, thêm slot mà giữ nguyên ctx thì bóp chết
request RAG dài. Chỗ này tôi còn dư VRAM nên nâng cả hai được. Cũng phải nói thật là việc
này không cho 10 lần đâu, GPU vẫn là trần cứng; nó chỉ hạ P95 ở vùng concurrency trung bình
cho tới khi trần mới là băng thông GPU.
