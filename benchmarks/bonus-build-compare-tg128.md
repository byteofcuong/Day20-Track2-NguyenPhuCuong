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

_Why did the gap come out this size on your CPU? Tie it to something concrete --
which extensions your CPU has, and whether this workload is limited by
instructions or by memory bandwidth. If the prebuilt binary won, explain how that
is possible._

**Giải thích của tôi (Nguyễn Phú Cường):**

**Prebuilt binary không thua, và đó không phải tai nạn — nó đã dùng đúng kernel dành cho
CPU của tôi ngay từ đầu.**

Trước hết phải sửa một dòng ở đầu report này: **"Vector extensions detected: none" là sai.**
Đó là giới hạn của `labs/00-setup/detect-hardware.py` — nhánh Windows (dòng 65–78) chỉ đọc
tên CPU và số core qua CIM, còn cờ AVX2/AVX-512 chỉ được dò trên Linux (`/proc/cpuinfo`) và
macOS (`sysctl`). Sự thật do chính `cmake` báo khi configure bản build này:

```
-- Performing Test HAS_AVX2_1 - Success
-- Performing Test HAS_AVX512_1 - Failed
-- Adding CPU backend variant ggml-cpu: /arch:AVX2 GGML_AVX2;GGML_FMA;GGML_F16C
```

i7-13650HX là Raptor Lake-HX: **có AVX2/FMA/F16C, không có AVX-512** (Intel disable AVX-512
trên dòng hybrid vì E-core không hỗ trợ). Vậy trần lý thuyết của `-DGGML_NATIVE=ON` trên
CPU này là **AVX2** — không có tập lệnh nào cao hơn để mở khoá.

Bây giờ đến phía prebuilt. Nó **không** phải một binary "generic": release Windows ship
**14 DLL CPU backend** và chọn một cái theo CPUID lúc chạy. Xác nhận trực tiếp:

```
$ ls runtime/b10488/ggml-cpu-*.dll        # 14 file: sse42, x64, sandybridge, ivybridge,
                                          # haswell, alderlake, skylakex, icelake,
                                          # cascadelake, cooperlake, sapphirerapids, zen4, ...
$ ./runtime/b10488/llama-bench.exe --list-devices
load_backend: loaded CPU backend from ...runtime/b10488/ggml-cpu-alderlake.dll
untime10488\ggml-cpu-alderlake.dll
```

Prebuilt đã nạp **`ggml-cpu-alderlake.dll`** — biến thể AVX2 dành cho Alder Lake, cùng
microarchitecture family với Raptor Lake của tôi. Nghĩa là hai bên đang chạy **cùng một
tập lệnh**: bản source build của tôi được compile với `/arch:AVX2`, còn prebuilt chọn đúng
kernel AVX2 lúc runtime. Chênh lệch 1.01× (14.8 so với 15.0 tok/s) đúng bằng mức nhiễu đo
giữa 3 lần lặp. **Không có gì để thắng cả** — đây là kết quả đúng, không phải build hỏng.

**Lý do thứ hai, độc lập, khiến khoảng cách này chắc chắn nhỏ: workload bị chặn bởi băng
thông bộ nhớ, không phải bởi tốc độ thực thi lệnh.** Bằng chứng nằm trong
`01-tuning-tg128.md`: đi từ 7 lên 14 thread — gấp đôi năng lực tính toán — chỉ đổi được
**+1.4%** throughput. Khi CPU đã dành phần lớn thời gian chờ weight từ DRAM, việc compiler
sinh ra lệnh vector tốt hơn cũng chỉ rút ngắn phần thời gian *không* phải nút thắt. Ngay cả
nếu prebuilt lỡ chọn nhầm một kernel kém hơn, mức thiệt hại cũng sẽ bị băng thông che lấp
phần lớn.

**Vậy khi nào B1 mới thắng đậm?** Đúng theo cảnh báo trong `bonus/README.md`: khi prebuilt
*không* có sẵn biến thể khớp CPU. Ví dụ CPU có AVX-512 thật (Zen 4, Sapphire Rapids server)
nhưng bảng dispatch chọn nhầm mức thấp hơn, hoặc kiến trúc ARM lạ không nằm trong danh sách
14 biến thể. Trên một Raptor Lake phổ thông với đúng biến thể đã có sẵn, kết quả 1.01× là
kết quả *nên* xảy ra.

**Liên hệ deck:** đây chính là câu hỏi FA3-cho-Hopper so với FA4-cho-Blackwell, ở quy mô
laptop. Điều bài này bổ sung là **runtime dispatch đã giải quyết phần lớn vấn đề rồi**:
llama.cpp ship 14 kernel và chọn theo CPUID, giống hệt cách vLLM/SGLang ship nhiều kernel
attention và chọn theo compute capability. Compile-time specialization chỉ còn giá trị ở
phần đuôi — những cấu hình mà không ai kịp build sẵn cho bạn. Và trước khi bỏ 20 phút
compile, đáng để hỏi trước: **bottleneck của mình có thật sự là instruction throughput
không?** Ở đây thì không, và bản build 1.01× là câu trả lời rẻ nhất cho câu hỏi đó.
