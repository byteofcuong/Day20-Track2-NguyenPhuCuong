# 02 - Serve: load test + saturation reading

Host `Windows-AMD64` · llama.cpp `b10488` ·
`--parallel 4` · `ctx=2048` · `threads=14` ·
`ngl=99`

| Users | Reqs | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Eff. concurrency | Failures |
|:--|--:|--:|--:|--:|--:|--:|--:|
| 10 | 169 | 2.89 | 2400 | 3900 | 4500 | 7.3 | 0.0% |
| 50 | 176 | 2.95 | 15000 | 17000 | 17000 | 40.9 | 0.0% |

*Effective concurrency = RPS x average latency (Little's Law) -- how many requests were
really in flight, regardless of how many users locust simulated. It counts queued requests
too, so the occupancy/slot ratio can legitimately exceed 1.0; it is occupancy, not
utilisation. For true slot utilisation use the server's own gauges (`make metrics`).*

## What these two runs say

| Going from 10 to 50 users | |
|:--|--:|
| Offered load | 5x |
| Throughput actually delivered | **1.02x** (20% of linear) |
| P95 latency | **4.36x** |
| Effective concurrency at 50 users | 40.9 vs `--parallel 4` slots (occupancy/slot ratio 10.24) |

**Saturated.** Throughput delivered only 1.02x for 5x the offered load, and effective concurrency (40.9) is at or above all 4 decode slots. Saturation sets in somewhere at or below 50 users; the load you added beyond that point became queue time rather than throughput.

Throughput moved 1.02x while P95 moved 4.36x. That gap is the goodput argument: past saturation you buy throughput by spending latency, and if your SLO is a P95 target then the requests you added are no longer being served within it. (This lab does not fix an SLO number for you -- pick one in your write-up and state how much goodput you keep at it.)

## Your reading

_Where does your server saturate, and what is the evidence? Name the number that
convinced you. Then say what you would change first to raise goodput at your SLO --
and why that knob and not another._

**Bài đọc của tôi (Nguyễn Phú Cường):**

**Server bão hoà ở đâu đó dưới 10 user, và con số thuyết phục tôi là RPS: 2.89 → 2.95.**
Tăng offered load 5× (10 → 50 user) chỉ đổi lấy **1.02×** throughput. Nếu server còn
headroom ở 10 user, RPS phải tăng đáng kể. Nó đứng yên, nên trần đã bị chạm từ trước
mốc 10 user.

**Phần latency tăng thêm là queue time, không phải compute time.** Ba bằng chứng độc lập:

1. **P95 tăng 4.36× (3.9 s → 17 s) trong khi RPS đứng yên.** Nếu server phải làm việc
   nặng hơn cho mỗi request thì RPS đã phải giảm. RPS không đổi mà latency tăng nghĩa là
   cùng lượng công việc đó bị trải ra trên thời gian chờ dài hơn.
2. **`requests_deferred` đỉnh 45** (`02-server-batching-u50.md`). Đây là bằng chứng trực
   tiếp và không thể chối cãi: server tự khai báo có 45 request đang nằm chờ slot.
3. **TPOT không đổi.** Ở bench 1 request/lần, TPOT P50 là 14.1 ms. Dưới 50 user,
   `busy_slots` = 3.97/4 và throughput token vẫn ~340 tok/s tổng. Thời gian *decode* mỗi
   token không tệ đi; chỉ có thời gian *đợi được decode* tăng lên.

Đối chiếu: effective concurrency **40.9** so với `--parallel 4` → occupancy/slot ratio
**10.24**. Trung bình mỗi slot có ~10 request xếp hàng. Với Little's Law, một request điển
hình đợi ~9 lượt trước khi tới lượt mình — nhân với ~1.7 s thời gian phục vụ thì ra đúng
vùng 15–17 s quan sát được.

**Đặt SLO và tính goodput:** lấy SLO là P95 ≤ 5 s (mức chấp nhận được cho chat câu ngắn).
Ở 10 user, P95 = 3.9 s → **giữ được ~100% goodput ở 2.89 RPS**. Ở 50 user, P95 = 17 s →
**goodput = 0**: throughput danh nghĩa vẫn 2.95 RPS nhưng không request nào đạt SLO. Đây
là minh hoạ sạch cho luận điểm của deck §8: sau điểm bão hoà, throughput mua thêm được
bằng cách tiêu latency, và tại một SLO cố định thì goodput *sụp* chứ không phẳng.

**Knob tôi sẽ đổi trước tiên: `--parallel` từ 4 lên 8–12, kèm nâng `--ctx-size`.**
Lý do chọn knob này chứ không phải knob khác:

- Nút thắt đã được định danh là **số slot**, không phải tốc độ tính toán. `busy_slots`
  3.97/4 nói engine không lãng phí gì; `deferred = 45` nói cái thiếu là chỗ ngồi. Knob
  đúng phải là knob nới cái đang thiếu.
- Tôi *không* chọn tăng thread (`-t`): sweep ở `01-tuning-tg128-ngl99.md` cho thấy `-t`
  hoàn toàn vô tác dụng khi đã offload GPU.
- Tôi *không* chọn hạ quantization xuống Q2: nó chỉ cho 1.17× decode (và đổi lại lỗi nội
  dung — xem `01-quickstart-results.md`), trong khi khoảng cách cần bù là 10×.
- Giới hạn thực tế: `--ctx-size 2048` hiện chia cho 4 slot = 512 token/slot. Nâng
  `--parallel` mà không nâng ctx sẽ bóp ngân sách mỗi slot và làm hỏng request RAG dài.
  Với 5 GB VRAM trống và KV cache của Gemma 4 E2B rất rẻ (đo ở
  `bonus-c2-kv-cache-quant.md`: chỉ ~60 MiB chênh lệch giữa f16 và q8_0 ở ctx 16384),
  tôi có thừa chỗ để nâng cả hai.
- Kỳ vọng thành thật: nâng slot **không** làm RPS tăng 10×. GPU vẫn là trần cứng. Nó sẽ
  cải thiện goodput ở mức concurrency trung bình và làm P95 xuống, cho tới khi trần mới
  trở thành băng thông GPU. Sau đó knob tiếp theo mới là giảm `max_tokens` hoặc thêm
  máy.
