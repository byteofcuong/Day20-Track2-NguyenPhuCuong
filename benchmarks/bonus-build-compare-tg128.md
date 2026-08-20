# Bonus B1 - Prebuilt vs source build

Host `Windows-AMD64` · CPU `13th Gen Intel(R) Core(TM) i7-13650HX`
Vector extensions detected: none
llama.cpp `b10488` both sides · `threads=14` ·
**both pinned to `ngl=0`** so this isolates the compiler ·
metric `tg128`, 3 repetitions

> **Backend mismatch, handled.** The prebuilt binary sees
> `['CUDA0: NVIDIA GeForce RTX 4050 Laptop GPU (6140 MiB, 5073 MiB free)']` and your source build sees `(no devices)`.
> Left at `-ngl 99` this comparison would have measured the accelerator and printed
> it under a compiler headline, so both sides were pinned to `-ngl 0`.

| Binary | Built for | tg128 (tok/s) | Relative |
|:--|--:|--:|--:|
| prebuilt release | runtime CPU dispatch | 14.8 | 1.00x |
| your source build | this CPU (`-DGGML_NATIVE=ON`) | 15.0 | 1.01x |

On this machine, **they are within 3% -- no meaningful difference**.

before: 14.8 tok/s (prebuilt release)
after:  15.0 tok/s (source build, -DGGML_NATIVE=ON)
speedup: 1.01x

Same source revision, same model, same backend, same `-ngl` -- the only difference
is what the compiler was allowed to assume about the CPU.
A gap this small usually means the prebuilt binary already dispatches to the right kernels at runtime (releases ship one libggml-cpu-*.so per microarchitecture and pick via CPUID), or that this workload is bandwidth-bound rather than instruction-bound. Both are real findings -- say which one you think it is.


## Your explanation
Prebuilt không thua, và không phải nhờ may: nó đã dùng đúng kernel dành cho CPU của tôi
ngay từ đầu.

Trước hết phải sửa dòng "Vector extensions detected: none" ở đầu file, nó sai. Đó là giới
hạn của detect-hardware.py, nhánh Windows (dòng 65-78) chỉ lấy tên CPU với số core, cờ AVX
chỉ dò trên Linux và macOS. Số thật lấy từ log cmake lúc configure bản build này:
HAS_AVX2_1 Success, HAS_AVX512_1 Failed, và nó chọn /arch:AVX2. i7-13650HX là Raptor Lake-HX,
có AVX2 nhưng không có AVX-512 vì Intel disable trên dòng hybrid do E-core không hỗ trợ.
Nghĩa là trần của -DGGML_NATIVE=ON trên CPU này chính là AVX2, không có tập lệnh nào cao hơn
để mở khoá.

Phía prebuilt thì không phải một binary generic như tôi tưởng. Release Windows ship 14 DLL
CPU backend rồi chọn theo CPUID lúc chạy. Tôi kiểm tra bằng llama-bench --list-devices thì
thấy dòng load_backend nạp ggml-cpu-alderlake.dll, đúng biến thể AVX2 cho Alder Lake, cùng
họ với Raptor Lake. Vậy hai bên đang chạy cùng một tập lệnh, và 1.01 lần là đúng bằng nhiễu
giữa 3 lần lặp. Không có gì để thắng.

Còn một lý do độc lập nữa khiến khoảng cách chắc chắn nhỏ: workload này nghẽn ở băng thông
bộ nhớ chứ không ở tốc độ thực thi lệnh. Bằng chứng nằm bên 01-tuning-tg128.md, đi từ 7 lên
14 thread chỉ được thêm 1.4%. Khi CPU dành phần lớn thời gian chờ weight từ DRAM thì
compiler sinh lệnh vector tốt hơn cũng chỉ rút ngắn phần không phải nút thắt.

Vậy khi nào build từ nguồn mới thắng đậm? Khi prebuilt không có sẵn biến thể khớp CPU, ví
dụ CPU có AVX-512 thật mà bảng dispatch chọn nhầm mức thấp hơn, hoặc một kiến trúc ARM lạ
không nằm trong 14 biến thể kia. Trên một Raptor Lake phổ thông thì 1.01 lần là kết quả nên
xảy ra.

Liên hệ với deck thì đây là câu hỏi chọn FA3 cho Hopper hay FA4 cho Blackwell, thu nhỏ lại.
Điều bài này thêm vào là runtime dispatch đã lo phần lớn vấn đề rồi, llama.cpp ship 14 kernel
chọn theo CPUID cũng giống cách vLLM ship nhiều kernel attention chọn theo compute
capability. Compile-time specialization chỉ còn giá trị ở phần đuôi, những cấu hình không ai
build sẵn cho bạn. Và trước khi bỏ 20 phút compile thì nên hỏi trước bottleneck của mình có
thật sự là instruction throughput không. Ở đây thì không, và bản build 1.01 lần là câu trả
lời rẻ nhất cho câu hỏi đó.
