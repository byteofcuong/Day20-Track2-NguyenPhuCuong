# Bonus C8 — Semantic cache

Nguyễn Phú Cường · tiêu chí B5 · Windows, RTX 4050, llama.cpp b10488

```powershell
.\lab.ps1 serve                                    # chat      :8080  (ngl=99)
$env:LAB_N_GPU_LAYERS='0'; .\lab.ps1 serve-embed   # embedding :8081  (ngl=0)
.venv\Scripts\python bonus\serving-regimes\semantic-cache-demo.py `
    --chat-url http://127.0.0.1:8080/v1 --embed-url http://127.0.0.1:8081/v1
```

Embedding server để ở CPU vì chat server đã giữ 2.5 GB, hai bản Gemma trên card 6 GB thì
không vừa. Embedding chỉ prefill nên CPU cũng được. Cả hai dùng 127.0.0.1 chứ không phải
localhost, lý do ghi ở benchmarks/03-integration-results.md.

## Kết quả (threshold 0.80)

| # | Kết quả | sim | ms | Prompt | Có phải paraphrase |
|--:|---|--:|--:|---|---|
| 1 | miss | 0.00 | 1554 | What is goodput at SLO? | prompt đầu |
| 2 | miss | 0.56 | 1350 | Explain TTFT and TPOT. | không |
| 3 | miss | 0.73 | 1437 | Can you define goodput@SLO? | có, của #1 |
| 4 | miss | 0.75 | 1359 | What does time to first token mean? | có, của #2 |
| 5 | miss | 0.64 | 1438 | How does PagedAttention work? | không |
| 6 | HIT | 0.80 | 0 | Tell me what goodput@SLO is. | có, của #1 |
| 7 | HIT | 0.85 | 0 | What is prefix caching? | không, chủ đề mới |
| 8 | HIT | 0.84 | 0 | Describe how PagedAttention works. | có, của #5 |

Hit rate 3/8. Tôi không dùng con số này làm kết quả, vì trong 3 hit có 1 hit sai và trong 5
miss có 2 miss sai.

## False hit

#7, "What is prefix caching?", similarity 0.85, HIT. Chủ đề chưa từng có trong cache, mà
cache trả về câu trả lời của một prompt khác, mất 0 ms, không sinh token nào. Người dùng hỏi
về prefix caching sẽ nhận định nghĩa goodput hoặc PagedAttention, và không có gì báo cho họ
biết chuyện đó vừa xảy ra. Không lỗi, không cảnh báo, chỉ là một câu trả lời trôi chảy về
sai chủ đề.

Tệ hơn nữa, 0.85 là similarity cao nhất trong cả 8 prompt. Cặp giống nhau nhất theo embedder
lại là cặp không liên quan gì.

## False miss

#3 "Can you define goodput@SLO?" ở 0.73 và #4 "What does time to first token mean?" ở 0.75,
cả hai đều trượt. #3 là paraphrase gần như từ điển của #1, cùng thuật ngữ cùng ý định. #4
khó hơn nhưng đúng loại mà semantic cache sinh ra để xử lý, "time to first token" chính là
dạng viết đầy đủ của TTFT. Cả hai phải trả giá 1.4 giây decode.

## Không threshold nào cứu được cả hai

Xếp similarity lên một trục:

```
0.56    0.64      0.73   0.75   0.80  0.84  0.85
 #2      #5        #3     #4     #6    #8    #7
 lạ      lạ       para   para   para  para   LẠ
```

Muốn bắt #3 thì threshold phải xuống 0.73 hoặc thấp hơn, nhưng #7 nằm ở 0.85 nên false hit
vẫn còn nguyên, lại kéo thêm #5 vào vùng nguy hiểm. Muốn chặn #7 thì threshold phải trên
0.85, khi đó #6, #8 và cả #3, #4 đều miss, cache thành vô dụng.

Vấn đề không nằm ở chỗ chọn sai ngưỡng mà ở chỗ thứ tự bị đảo: có một cặp không liên quan
xếp cao hơn mọi cặp paraphrase. Không có đường cắt một chiều nào tách được hai tập khi chúng
đã chồng lên nhau và đảo thứ tự như vậy. Threshold chỉ có nghĩa khi hai phân phối tách rời,
mà ở đây tất cả dồn vào dải hẹp 0.56 đến 0.85.

Threshold sweep chạy offline cho 3/8 hit ở mọi mức từ 0.70 đến 0.95, nhưng đó là artifact
của stub bag-of-words (similarity gần như chỉ 0.0 hoặc 1.0), chính script cũng cảnh báo vậy.
Bằng chứng là bảng similarity thật ở trên.

## Vì sao decoder mean-pooled là embedder yếu

serve-embed chạy chat model ở pooling mode vì lab chỉ ship một model. Gemma 4 E2B được train
cho đúng một việc là đoán token kế tiếp, nên hidden state ở vị trí t chứa thứ cần để đoán
token t+1, chủ yếu là tín hiệu cục bộ về cú pháp và văn phong. Lấy trung bình các state đó
ra một vector phản ánh câu này trông như thế nào, chứ không phải câu này nói về cái gì.

Đúng là những gì bảng trên cho thấy. Cả 8 prompt đều là câu hỏi kỹ thuật ngắn, cùng thể nghi
vấn, cùng văn phong. Embedder đo được sự giống nhau về hình thức đó nên báo 0.56 đến 0.85
cho mọi cặp, kể cả cặp không liên quan. #7 lên 0.85 vì nó là câu "What is X?" ngắn nhất,
giống #1 về hình thức nhất, dù X hoàn toàn khác.

Embedding model chuyên dụng như Qwen3-Embedding, BGE-M3 hay EmbeddingGemma khác ở mục tiêu
huấn luyện chứ không phải ở kích thước. Chúng train contrastive, kéo cặp positive lại gần và
đẩy hard negative ra xa, mà hard negative chính là những câu trông giống nhau nhưng khác
nghĩa, đúng loại đã đánh lừa embedder này. Kết quả là hai phân phối tách bạch, và lúc đó
threshold mới có ý nghĩa. Chúng cũng dùng bidirectional attention với pooling head được train
riêng thay vì mean-pool thô trên decoder state nhân quả.

Có một chi tiết đáng nói thêm: stub bag-of-words 40 dòng ở chế độ offline lại phân loại đúng
hơn. Nó bắt được #3 nhờ chung từ goodput và không hit #7. Trên đúng bộ prompt này thì đếm từ
trùng nhau đánh bại decoder 5B mean-pooled. Không phải lời khen cho bag-of-words, nó sẽ
trượt #4 vì "time to first token" với TTFT không chung từ nào, mà là thước đo mức độ tệ của
việc dùng sai công cụ.

## Rủi ro bảo mật

Semantic cache và prefix cache mặc định dùng chung giữa người dùng, và một hit làm đổi timing
theo cách đo được từ ngoài: hit 0 ms, miss 1.4 giây. Chênh ba bậc độ lớn đó là một oracle
nhị phân hoàn hảo.

Kẻ tấn công có thể dò xem người khác đã hỏi gì bằng cách gửi prompt phỏng đoán rồi đo thời
gian trả lời, hit gần như tức thì chính là câu trả lời có. Với prefix cache thì độ phân giải
còn cao hơn, dò được từng token của prefix qua thời gian prefill. Đây là lớp tấn công đã
được mô tả trong tài liệu NDSS'25 về suy luận prompt qua timing của shared cache.

Cách giảm thiểu theo thứ tự: salt cache key theo tenant để cache không vượt ranh giới người
dùng, chấp nhận mất một phần hit rate; đánh dấu prompt chứa PII là no-store; cuối cùng mới
tính tới việc làm phẳng timing ở đường cache hit, vì cách này tốn kém.

Điểm cần nhấn: false hit ở trên và lỗ hổng này là cùng một cơ chế nhìn từ hai phía. Cả hai
đều đến từ việc hệ thống coi gần giống theo embedding là giống nhau. Threshold càng thấp thì
hit rate càng đẹp, mà sai sót lẫn rò rỉ cũng càng nhiều.

## Kết luận

Deck mô tả stack ba tầng cache. Bài này cho thấy tầng 1 chỉ tốt bằng embedder của nó, và đó
không phải chi tiết triển khai mà là điều kiện tiên quyết. Với embedder sai thì tầng 1 không
chỉ kém hiệu quả mà còn có hại, nó phục vụ câu trả lời sai với sự tự tin tuyệt đối, ở 0 ms,
không để lại dấu vết.

Nếu làm thật, tôi sẽ tách embedding endpoint khỏi chat endpoint và chạy một model embedding
riêng. Bonus C9 cũng dẫn tới cùng kết luận từ hướng khác: embedding là một regime phục vụ
khác hẳn, prefill-bound, static batching, không KV cache, nên nó cần model riêng và
autoscaler riêng.
