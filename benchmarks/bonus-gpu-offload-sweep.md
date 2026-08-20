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
Full offload thắng, 13.7 lên 77.0 tok/s, tức 5.62 lần. Không có mức nào peak ở giữa rồi tụt,
nghĩa là không thứ gì cạn trước: model 2.97 GB, card có 6 GB nên weight cộng KV cache của
ctx 2048 vẫn vừa. Nếu model lớn hơn VRAM thì đường cong sẽ đổi hình, đạt đỉnh ở một mức ngl
nào đó rồi đi xuống vì driver phải kéo weight qua PCIe từng token.

Điều tôi không ngờ là đường cong lồi lên chứ không tuyến tính. 8 layer đầu chỉ mua thêm 5.7
tok/s, còn nhóm layer cuối mua thêm 23.0. Lý do là ở partial offload thời gian mỗi token là
tổng nối tiếp của phần CPU với phần GPU, mà tok/s lại là nghịch đảo của tổng đó. Khi phía
CPU còn nhiều, bỏ vài layer chỉ cắt được một phần nhỏ. Đến lúc phía CPU gần biến mất thì
cùng một mức cải thiện tuyệt đối lại đẩy tok/s lên nhiều hơn hẳn. Nói cách khác partial
offload luôn bị chặn bởi phần chậm nhất còn sót lại trên CPU, và mỗi token đều phải đi qua
nó.

Chỗ này có ý nghĩa thực tế: ai đang ở partial offload thì bỏ tiền mua thêm VRAM để nhét nốt
phần cuối đáng giá hơn nhiều so với suy luận tuyến tính.

Một điểm để đối chiếu: mức -ngl 0 ra 13.7 tok/s, khớp với -t 14 ra 14.1 tok/s bên
01-tuning-tg128.md, chênh 3% là nhiễu. Hai sweep đo hai knob khác nhau nhưng gặp nhau ở cùng
một điểm, nên tôi tin cả hai phép đo.
