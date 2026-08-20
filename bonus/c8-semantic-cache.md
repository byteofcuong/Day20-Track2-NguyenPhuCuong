# Bonus C8 — Semantic cache: chẩn đoán một embedder yếu

*Nguyễn Phú Cường · tiêu chí bonus **B5** (một so sánh runtime/regime) · Windows-AMD64 ·
RTX 4050 · llama.cpp `b10488`*

## Thiết lập

```powershell
.\lab.ps1 serve                                    # chat      :8080  (ngl=99, GPU)
$env:LAB_N_GPU_LAYERS='0'; .\lab.ps1 serve-embed   # embedding :8081  (ngl=0, CPU)
.venv\Scripts\python bonus\serving-regimes\semantic-cache-demo.py `
    --chat-url http://127.0.0.1:8080/v1 --embed-url http://127.0.0.1:8081/v1
.venv\Scripts\python bonus\serving-regimes\semantic-cache-demo.py --offline --sweep
```

Embedding server chạy `ngl=0` có chủ đích: chat server đã giữ ~2.5 GB VRAM, và hai bản
copy của Gemma 4 E2B trên một card 6 GB sẽ không vừa. Embedding là regime chỉ prefill nên
CPU đủ dùng.

Cả hai server dùng `127.0.0.1` chứ không phải `localhost` — xem
`benchmarks/03-integration-results.md` để biết vì sao (`localhost` tốn thêm ~2.1 s/request
trên máy này do fallback IPv6).

## Kết quả thô (threshold 0.80)

| # | Kết quả | sim | ms | Prompt | Đây có phải paraphrase? |
|--:|---|--:|--:|---|---|
| 1 | miss | 0.00 | 1554 | What is goodput at SLO? | — (prompt đầu tiên) |
| 2 | miss | 0.56 | 1350 | Explain TTFT and TPOT. | không, chủ đề mới |
| 3 | miss | **0.73** | 1437 | Can you define goodput@SLO? | **CÓ — paraphrase của #1** |
| 4 | miss | **0.75** | 1359 | What does time to first token mean? | **CÓ — paraphrase của #2** |
| 5 | miss | 0.64 | 1438 | How does PagedAttention work? | không, chủ đề mới |
| 6 | HIT | 0.80 | 0 | Tell me what goodput@SLO is. | CÓ — paraphrase của #1 ✅ |
| 7 | **HIT** | **0.85** | 0 | What is prefix caching? | **KHÔNG — chủ đề hoàn toàn mới** |
| 8 | HIT | 0.84 | 0 | Describe how PagedAttention works. | CÓ — paraphrase của #5 ✅ |

Hit rate 3/8 = 38%. **Con số này vô nghĩa và tôi không dùng nó làm kết quả** — trong 3 hit
có 1 hit sai, và trong 5 miss có 2 miss sai.

## 1. False hit

**#7 "What is prefix caching?" — similarity 0.85, HIT.**

Đây là một chủ đề chưa từng xuất hiện trong cache. Cache trả về câu trả lời đã lưu của một
prompt khác, với **0 ms** và không một token nào được sinh ra. Trong hệ thống thật, người
dùng hỏi về prefix caching sẽ nhận về định nghĩa goodput@SLO hoặc PagedAttention, và **không
có tín hiệu nào cho biết điều đó đã xảy ra** — không lỗi, không cảnh báo, chỉ là một câu trả
lời trôi chảy về sai chủ đề. Đây là chế độ hỏng nguy hiểm nhất của layer này.

Điều làm nó tệ hơn: 0.85 là **similarity cao nhất trong toàn bộ 8 prompt**. Cặp giống nhau
nhất theo embedder lại là cặp không hề liên quan.

## 2. False miss

**#3 "Can you define goodput@SLO?" — similarity 0.73, MISS.**
**#4 "What does time to first token mean?" — similarity 0.75, MISS.**

#3 là paraphrase gần như từ điển của #1 ("What is goodput at SLO?") — cùng thuật ngữ, cùng
ý định, chỉ khác cách diễn đạt. #4 là trường hợp khó hơn nhưng đúng loại mà semantic cache
sinh ra để xử lý: "time to first token" là dạng viết đầy đủ của "TTFT" trong #2. Cả hai đều
trượt ngưỡng và phải trả giá bằng ~1.4 s decode.

## 3. Không có một threshold nào sửa được cả hai

Đây là phần cốt lõi. Sắp toàn bộ similarity lên một trục:

```
0.56    0.64      0.73   0.75   0.80  0.84  0.85
 #2      #5        #3     #4     #6    #8    #7
strangerstranger  PARA   PARA   PARA  PARA  STRANGER
                                            ^^^^^^^^
```

- Muốn bắt #3 (paraphrase, 0.73) → threshold ≤ 0.73. Nhưng #7 nằm ở **0.85 > 0.73**, nên
  false hit vẫn còn, và ta còn kéo thêm #5 (0.64) vào vùng nguy hiểm.
- Muốn chặn #7 (stranger, 0.85) → threshold > 0.85. Khi đó #6 (0.80), #8 (0.84) và cả #3,
  #4 đều miss — **mọi paraphrase thật đều trượt**, cache trở thành vô dụng.

Nguyên nhân không phải chọn sai ngưỡng mà là **thứ tự bị đảo**: có ít nhất một cặp không
liên quan xếp hạng cao hơn mọi cặp paraphrase. Không tồn tại đường cắt một chiều nào tách
được hai tập khi chúng đã chồng lấn và đảo thứ tự. Threshold chỉ có nghĩa khi phân phối
similarity của paraphrase và của stranger tách rời nhau — ở đây chúng dồn vào dải hẹp
0.56–0.85 và trộn vào nhau.

Threshold sweep offline (`--offline --sweep`) cho 3/8 hit ở **mọi** ngưỡng 0.70→0.95, nhưng
đó là artifact của stub bag-of-words (similarity gần như chỉ nhận 0.0 hoặc 1.0), chính
script cũng cảnh báo như vậy. Nó không phải bằng chứng — bằng chứng là bảng similarity thật
ở trên.

## 4. Vì sao decoder mean-pooled là sentence encoder yếu

`make serve-embed` chạy **chat model** ở chế độ pooling vì lab chỉ ship một model. Gemma 4
E2B được train cho một mục tiêu duy nhất: **dự đoán token kế tiếp**. Hidden state ở vị trí
token *t* được tối ưu để chứa đúng thứ cần cho việc đoán token *t+1* — chủ yếu là tín hiệu
cục bộ về cú pháp và văn phong. Lấy trung bình các state đó trên toàn câu cho ra một vector
phản ánh **"câu này trông như thế nào"** chứ không phải **"câu này nói về cái gì"**.

Điều đó giải thích chính xác bảng số ở trên: cả 8 prompt đều là câu hỏi kỹ thuật ngắn, cùng
thể nghi vấn, cùng thanh ghi văn phong. Embedder đo được sự giống nhau về *hình thức* đó và
báo 0.56–0.85 cho mọi cặp — kể cả cặp không liên quan. #7 đạt 0.85 vì nó là câu hỏi
"What is X?" ngắn nhất, giống #1 về hình thức nhất, dù X hoàn toàn khác.

Embedding model chuyên dụng (Qwen3-Embedding, BGE-M3, EmbeddingGemma) khác ở **mục tiêu
huấn luyện**, không phải ở kích thước. Chúng được train contrastive: kéo các cặp positive
(paraphrase, cặp query–document) lại gần và **đẩy hard negative ra xa** — mà hard negative
chính là những câu trông giống nhau nhưng khác nghĩa, đúng loại đã đánh lừa embedder này.
Kết quả là phân phối similarity tách bạch, và lúc đó một threshold mới có ý nghĩa. Chúng
cũng dùng bidirectional attention và pooling head được train riêng thay vì mean-pool thô
trên decoder state nhân quả.

Một quan sát bổ sung đáng nói: **stub bag-of-words 40 dòng trong chế độ `--offline` phân
loại đúng hơn** — nó bắt #3 (sim 1.0, nhờ chung từ "goodput") và **không** hit #7. Trên
đúng bộ prompt này, đếm từ trùng nhau đánh bại decoder 5B mean-pooled. Đó không phải lời
khen cho bag-of-words (nó sẽ trượt #4, vì "time to first token" và "TTFT" không chung một
từ nào) mà là thước đo mức độ tệ của việc dùng sai công cụ: một decoder không được train
để làm encoder thì thua cả baseline tầm thường.

## 5. Rủi ro bảo mật: cache dùng chung là một kênh phụ

Semantic cache và prefix/KV cache đều **dùng chung giữa các người dùng** theo mặc định, và
một hit thay đổi timing theo cách đo được từ bên ngoài: ở bảng trên, hit = **0 ms**, miss =
**~1.4 giây**. Chênh lệch ba bậc độ lớn đó là một oracle nhị phân hoàn hảo.

Kẻ tấn công vì thế có thể dò xem **người khác đã hỏi gì**: gửi một prompt phỏng đoán, đo
thời gian trả lời, và một hit gần như tức thì chính là câu trả lời "có, đã có người hỏi câu
tương tự". Với prefix cache thì độ phân giải còn cao hơn — có thể dò từng token của prefix
qua thời gian prefill. Đây là lớp tấn công đã được mô tả trong tài liệu NDSS'25 về suy luận
prompt qua timing của shared cache.

Biện pháp giảm thiểu, theo thứ tự ưu tiên:

1. **Salt cache key theo tenant.** Khoá thành `(tenant_id, embedding)` để cache không bao
   giờ vượt ranh giới người dùng. Mất một phần hit rate, đổi lấy việc kênh phụ biến mất.
2. **Không cache nội dung nhạy cảm.** Đánh dấu prompt chứa PII/bí mật là no-store.
3. **Làm phẳng timing** ở đường trả về của cache hit (thêm độ trễ nhân tạo) nếu buộc phải
   dùng cache chung — biện pháp này tốn kém và chỉ nên coi là phương án cuối.

Điều cần nhấn mạnh: **false hit ở mục 1 và lỗ hổng ở đây là cùng một cơ chế nhìn từ hai
phía.** Cả hai đều bắt nguồn từ việc hệ thống coi "gần giống theo embedding" là "giống
nhau". Ngưỡng càng thấp thì hit rate càng đẹp, và cả sai sót lẫn rò rỉ đều càng nhiều.

## 6. Kết luận

Deck mô tả stack ba tầng cache: `request → [1] semantic → [2] prefix/KV → [3] full
inference`. Bài này cho thấy tầng 1 **chỉ tốt bằng embedder của nó**, và đó không phải chi
tiết triển khai mà là điều kiện tiên quyết. Với embedder sai, tầng 1 không chỉ kém hiệu quả
mà còn **có hại**: nó phục vụ câu trả lời sai với sự tự tin tuyệt đối, ở 0 ms, không dấu
vết.

Nếu triển khai thật, tôi sẽ tách embedding endpoint khỏi chat endpoint và chạy một model
embedding chuyên dụng. Đó cũng là kết luận đến từ hướng khác của bonus C9
(`benchmarks/bonus-c9-embedding-serving.md`): embedding là một regime phục vụ khác hẳn —
prefill-bound, static batching, không KV cache — nên nó cần model riêng, autoscaler riêng,
và không nên ghép chung với chat.
