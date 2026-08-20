# Bonus - GPU offload sweep

Host `Windows-AMD64` · backend(s) `nvidia_cuda, vulkan` ·
llama.cpp `b10488` · `threads=14` · metric `tg128`

| -ngl | tg128 (tok/s) | vs -ngl 0 | vs best |
|:--|--:|--:|--:|
| 0 | 13.7 | 1.00x | 18% |
| 8 | 19.4 | 1.42x | 25% |
| 16 | 25.4 | 1.86x | 33% |
| 24 | 38.2 | 2.79x | 50% |
| 32 | 54.0 | 3.95x | 70% |
| 99 | 77.0 | 5.63x | 100% |

Best: `-ngl 99` at 77.0 tok/s
-- 5.63x faster than CPU-only.

Where the curve flattens tells you the model ran out of layers to move. Where it
*peaks below* full offload tells you something did not fit and the accelerator
started paying to fetch weights it could not hold.

## Your finding

_Is full offload best on your machine? If the curve peaked at a partial value,
what ran out first -- VRAM, or bandwidth between host and device?_

**Finding của tôi (Nguyễn Phú Cường):**

**Có, full offload là tốt nhất trên máy này** — và đường cong không hề phẳng ở đoạn nào:

| -ngl | tok/s | tăng thêm so với mức trước |
|--:|--:|--:|
| 0 | 13.7 | — |
| 8 | 19.4 | +5.7 |
| 16 | 25.4 | +6.0 |
| 24 | 38.2 | +12.8 |
| 32 | 54.0 | +15.8 |
| 99 | 77.0 | +23.0 |

Tổng cộng **5.62×** (13.7 → 77.0 tok/s). Điều đáng chú ý là đường cong **lồi lên**, không
phải tuyến tính: 8 layer đầu chỉ mua được +5.7 tok/s, còn nhóm layer cuối mua được +23.0.

Lý do là ở partial offload, **thời gian mỗi token là tổng của hai phần nối tiếp nhau**:
phần CPU (các layer còn ở host) cộng phần GPU. Vì tốc độ là nghịch đảo của tổng thời gian,
việc bỏ đi vài layer khỏi phía CPU chậm chỉ làm giảm một phần nhỏ của tổng, nên phần đầu
đường cong dốc thoải. Khi phía CPU gần như biến mất thì cùng một lượng cải thiện tuyệt đối
về thời gian lại tạo ra mức tăng tok/s lớn hơn nhiều. Nói ngắn gọn: **partial offload
luôn bị giới hạn bởi phần chậm nhất còn sót lại trên CPU**, và mỗi token đều phải đi qua
nó.

**Không có mức nào peak dưới full offload**, nghĩa là không thứ gì cạn trước: Gemma 4 E2B
UD-Q4_K_XL nặng 2.97 GB, RTX 4050 có 6.0 GB (≈5.0 GB trống sau desktop), nên toàn bộ
weight + KV cache của ctx 2048 vẫn nằm gọn trong VRAM. Nếu model lớn hơn VRAM, đường cong
sẽ đổi hình: nó sẽ đạt đỉnh ở một `-ngl` nào đó rồi tụt, vì driver bắt đầu phải kéo weight
qua PCIe mỗi token — lúc đó thứ cạn là VRAM chứ không phải layer.

**Ở đây có một chi tiết dễ bị nhầm cần nói rõ:** con số `-ngl 0` = 13.7 tok/s khớp với
`-t 14` = 14.1 tok/s trong `01-tuning-tg128.md` (cùng cấu hình CPU, chênh 3% nhiễu đo).
Hai sweep này đo hai knob khác nhau nhưng gặp nhau ở cùng một điểm — đó là dấu hiệu cả hai
phép đo đều nhất quán, không phải trùng lặp.

**So với deck:** đây là phiên bản laptop của quyết định "cái gì chạy trên accelerator, cái
gì ở lại host". Trên datacenter, cùng logic này xuất hiện dưới dạng offload optimizer state
hoặc KV cache sang host memory. Kết luận giống nhau ở cả hai quy mô: nếu còn *bất kỳ* phần
nào của đường tính toán nóng nằm ở phía chậm, nó sẽ chi phối, vì mỗi token đều phải đi
qua nó.
