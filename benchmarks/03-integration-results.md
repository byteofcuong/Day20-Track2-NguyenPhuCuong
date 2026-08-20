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
| Day | Thành phần | Real hay stub |
|---|---|---|
| N16 Cloud/IaC | không có IaC, chạy tay trên laptop | stub |
| N17 Data pipeline | TOY_DOCS hard-code 6 chuỗi (pipeline.py:36) | stub |
| N18 Lakehouse | corpus nằm trong RAM, mất khi thoát | stub |
| N19 Vector + features | đếm từ trùng nhau, không index, không embedding model (pipeline.py:81) | stub |
| N20 Serving | llama-server, Gemma 4 E2B trên RTX 4050 | real |

Điểm số nguyên trong bảng trên (1.0, 2.0, 0.0) là bằng chứng cho dòng N19: đó là số từ khớp
chứ không phải cosine similarity. Retrieval kiểu này vẫn lấy đúng document cho cả 3 query,
nhưng chỉ vì query được viết dùng lại đúng từ khoá của document. Gặp paraphrase thật là
hỏng, tôi đo đúng chuyện đó ở bonus C8.

Stage dominant thì đúng như đoán, llm chiếm 100%. Nhưng embed và retrieve bằng 0.0 ms không
phải vì nhanh mà vì chúng không tồn tại, nên nói LLM là bottleneck ở đây gần như là nói thừa.

Chỗ tôi đoán sai mới đáng nói. Lần chạy đầu cho llm khoảng 2727 ms mỗi query, trong khi
server tự báo prefill cộng decode chỉ khoảng 370 ms. Hơn 2.2 giây không thuộc stage nào cả.
Tôi gửi cùng một request tới hai địa chỉ thì ra: localhost mất 2542 ms, 127.0.0.1 mất 326 ms.
Server bind IPv4, client resolve localhost ra ::1 trước rồi phải chờ hết timeout mới quay về
IPv4. Số trong file này là lần chạy lại với 127.0.0.1, mean còn 657.9 ms.

Nếu chỉ nhìn cột dominant stage thì tôi đã ghi 2727 ms vào báo cáo và đổ hết cho LLM, trong
khi 77% con số đó là lỗi mạng phía client. Bắt được là nhờ pipeline.py in cả đồng hồ client
lẫn đồng hồ server, hai cái không khớp nhau chính là tín hiệu.

Muốn giảm latency 2 lần thì không phải nhắm vào retrieval, nó tốn 0 ms. Trong 658 ms còn
lại thì decode chừng 330 ms, prefill 40 ms, còn lại là overhead HTTP. Tôi sẽ bật stream
trước, không giảm tổng thời gian nhưng đưa cái người dùng cảm nhận từ 658 ms xuống khoảng
250 ms, rồi cắt max_tokens vì câu trả lời chỉ dài 24-30 token mà đang để 200. Chỉ khi corpus
lớn lên hàng triệu document thì retrieval mới đáng để đụng tới.
