# 03 - Integrate: RAG pipeline run

Host `Windows-AMD64` · llama.cpp `b10488` ·
retrieval backend: **keyword overlap** · 3 queries

| Query | Contexts retrieved | embed (ms) | retrieve (ms) | llm (ms) | total (ms) |
|:--|--:|--:|--:|--:|--:|
| Why is goodput more useful than raw throughp... | goodput, paged, radix | 0.0 | 0.0 | 915.4 | 915.5 |
| What problem does PagedAttention actually so... | paged, radix, disagg | 0.0 | 0.0 | 529.2 | 529.3 |
| When does splitting prefill and decode help?... | disagg, radix, batching | 0.0 | 0.0 | 529.0 | 529.0 |

Mean per stage (ms): embed **0.0** · retrieve **0.0** ·
llm **657.9** · total **657.9**
Dominant stage: **llm** (100% of total)

## Answers returned

**Why is goodput more useful than raw throughput?**

> Goodput@SLO counts only the requests per second that met the TTFT and TPOT targets. Throughput at saturation ignores SLOs.

**What problem does PagedAttention actually solve?**

> PagedAttention stores the KV cache in non-contiguous pages, which removes the internal fragmentation that wasted most GPU memory.

**When does splitting prefill and decode help?**

> Splitting prefill and decode helps because prefill is compute-bound and decode is memory-bandwidth-bound.


## Which N16-N19 pieces are real

_List each of N16, N17, N18, N19 as real or stubbed. Stubbing costs no points;
misrepresenting it does. Then answer: is the dominant stage above what you expected?
If you had to halve this pipeline's latency, which stage would you attack and why?_

**Khai báo của tôi (Nguyễn Phú Cường):**

| Day | Thành phần | Real hay stub | Cụ thể |
|---|---|---|---|
| N16 Cloud/IaC | — | **stub** | Không có Terraform/IaC. Mọi thứ chạy trên laptop, tiến trình khởi động bằng tay. |
| N17 Data pipeline | — | **stub** | Không có ingestion. `TOY_DOCS` là 6 chuỗi hard-code trong `labs/03-integrate/pipeline.py:36`. |
| N18 Lakehouse | — | **stub** | Không có storage layer. Corpus nằm trong RAM của process, mất khi thoát. |
| N19 Vector + features | — | **stub** | Không có vector index và không có embedding model. `retrieve()` (`pipeline.py:81`) dùng đếm từ trùng nhau; điểm số nguyên (1.0 / 2.0 / 0.0) trong bảng trên là bằng chứng: đó là số từ khớp, không phải cosine similarity. |
| N20 Serving | `llama-server` | **real** | GGUF thật, Gemma 4 E2B UD-Q4_K_XL, offload 35 layer lên RTX 4050, phục vụ qua `/v1/chat/completions`. Cột `llm (ms)` và các con số `server: prefill/decode` là đo thật. |

Retrieval kiểu keyword vẫn lấy đúng document cho cả 3 query, nhưng đó là vì các query
được viết dùng lại đúng từ khoá của document. Với paraphrase thật, nó sẽ hỏng — tôi đã đo
chính xác hiện tượng này trong bonus C8 (`bonus/c8-semantic-cache.md`).

**Stage dominant có đúng như tôi nghĩ không?** Về nhãn thì có: `llm` chiếm 100%, còn
`embed` và `retrieve` là **0.0 ms** — không phải "nhanh", mà là *không tồn tại* (không có
lệnh gọi mạng nào, chỉ là đếm từ trên 6 chuỗi). Nói "LLM là bottleneck" ở đây gần như là
một tautology.

**Nhưng chỗ tôi đã đoán sai, và nó mới là phần đáng giá.** Lần chạy đầu tiên cho
`llm` ≈ **2727 ms/query**, trong khi chính server báo `prefill 36 ms + decode 333 ms` ≈
**370 ms**. Hơn 2.2 giây không được giải thích bởi bất kỳ stage nào. Tôi đã cô lập nó
bằng cách gửi cùng một request tới hai địa chỉ:

```
http://localhost:8080    wall = 2542 ms   server = 296 ms
http://127.0.0.1:8080    wall =  326 ms   server = 149 ms
```

Nguyên nhân: `llama-server` bind `127.0.0.1` (chỉ IPv4), còn client resolve `localhost`
ra `::1` trước. Kết nối IPv6 không bị từ chối ngay mà bị drop, nên client phải chờ hết
timeout rồi mới fallback sang IPv4 — **~2.1 s mỗi request, nằm hoàn toàn ở client**. Số
trong báo cáo này là lần chạy lại với `--base-url http://127.0.0.1:8080`, nên mean giảm
từ 2727 ms xuống **657.9 ms**.

Bài học tôi rút ra: nếu tôi chỉ nhìn cột "dominant stage", tôi đã ghi 2727 ms vào báo cáo
và gán toàn bộ cho LLM — trong khi 77% con số đó là một lỗi cấu hình mạng. Việc
`pipeline.py` in cả *client-side timing* lẫn *server-side timings* là thứ đã bắt được
điều này; hai đồng hồ không khớp nhau chính là tín hiệu.

**Nếu phải giảm latency pipeline này 2×, tôi tấn công vào đâu?** Không phải vào retrieval
(nó tốn 0 ms). Trong 658 ms còn lại, ~330 ms là decode và ~40 ms là prefill, phần dư là
overhead HTTP. Nên:

1. **Stream response** (`stream: true`). Không giảm tổng thời gian nhưng giảm thời gian
   người dùng *cảm nhận* từ 658 ms xuống ~250 ms (TTFT) — với chat đó mới là số quan trọng.
2. **Cắt số token sinh ra.** Câu trả lời chỉ dài 24–30 token nhưng `max_tokens=200`; ràng
   buộc prompt để trả lời ngắn gọn sẽ cắt thẳng vào phần decode, phần đang chiếm ~50%.
3. **Chỉ khi corpus lớn lên** thì retrieval mới thành mục tiêu. Với 6 document thì
   brute-force là đúng; với 6 triệu document, embed + ANN index sẽ chiếm chỗ và lúc đó
   bảng này trông hoàn toàn khác.
