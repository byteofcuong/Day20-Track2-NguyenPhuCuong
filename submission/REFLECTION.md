# Reflection — Day 20 Lab (Personal Report)

> **Đây là báo cáo cá nhân.** Số liệu của bạn **không** so sánh được với bạn cùng lớp
> — chỉ so **before vs after trên chính máy bạn**. Rubric chấm độ rõ ràng của setup,
> đo lường và **lập luận**, không chấm tốc độ tuyệt đối.
>
> `make verify` sẽ fail nếu còn placeholder chưa điền. Đó là cố ý.

**Họ Tên:** Nguyễn Phú Cường
**Cohort:** AICB-P2T2
**Ngày submit:** 2026-08-20

---

## 1. Hardware & runtime  *(rubric 1, 2 — 10 điểm)*

> Từ `make probe`. Paste output hoặc điền tay.

- **OS:** Windows 11 (AMD64), Python 3.13.7
- **CPU:** 13th Gen Intel(R) Core(TM) i7-13650HX (Raptor Lake-HX, 6 P-core + 8 E-core)
- **Cores:** 14 physical / 20 logical
- **CPU extensions:** AVX2 + FMA + F16C, **không có AVX-512** — xem ghi chú bên dưới
- **RAM:** 15.7 GB
- **Accelerator:** NVIDIA GeForce RTX 4050 Laptop GPU, 6141 MiB VRAM (driver 581.86, CUDA 13.0); Vulkan cũng hiện diện
- **llama.cpp asset đã tải:** `llama-b10488-bin-win-cuda-12.4-x64.zip` (+ `cudart-llama-bin-win-cuda-12.4-x64.zip`)
- **Model đã dùng:** Gemma 4 E2B (`LAB_MODEL=gemma4-e2b`)
- **Quantization:** UD-Q4_K_XL (primary, 2.97 GB) + UD-Q2_K_XL (compare, 2.24 GB) (từ `models/active.json`)

> **Ghi chú về dòng "CPU extensions".** `hardware.json` để trống mục này, và
> `benchmarks/bonus-build-compare-tg128.md` in ra "Vector extensions detected: none".
> Đó là giới hạn của probe chứ không phải sự thật về CPU: nhánh Windows của
> `labs/00-setup/detect-hardware.py` (dòng 65–78) chỉ lấy tên CPU và số core, cờ AVX chỉ
> được dò trên Linux và macOS. Số liệu thật ở trên lấy từ log configure của cmake khi
> build bonus B1: `HAS_AVX2_1 - Success`, `HAS_AVX512_1 - Failed`.

**Chạy ở đâu:** laptop của tôi (chạy local, `runtime_environment = "local"` trong `hardware.json`).
Không dùng Colab/Kaggle.

**Setup story** (≤ 80 chữ): điều gì cần thay đổi để lab chạy trên máy bạn? Có bước
nào fail rồi phải workaround không?

Ba việc. (1) Windows không có `make` → dùng `.\lab.ps1` + `bootstrap.ps1`. (2) `make serve`
crash với `error: invalid argument: of` — `os.execv` trên Windows tách đường dẫn có dấu
cách (`D:\Direc of code\...`); tôi sửa `labs/02-serve/serve.py` để dùng `subprocess.run`
trên win32. (3) Probe báo `GPU offload : ACTIVE` (asset CUDA + cudart), nên `ngl=99` là mặc
định — điều này định hình lại toàn bộ §5.

---

## 2. Đo lường  *(rubric 3, 4, 5 — 20 điểm)*

> Paste bảng từ `benchmarks/01-quickstart-results.md` (`make bench` tự sinh).

| Quantization | Size (GB) | Load (ms) | TTFT P50/P95 (ms) | TPOT P50/P95 (ms) | E2E P50/P95/P99 (ms) | Decode (tok/s) |
|---|--:|--:|--:|--:|--:|--:|
| UD-Q4_K_XL | 2.97 | 4080 | 215 / 453 | 14.1 / 15.8 | 1091 / 1404 / 1404 | 70.8 |
| UD-Q2_K_XL | 2.24 | 4775 | 210 / 349 | 12.0 / 13.8 | 971 / 1116 / 1116 | 83.0 |

*(Cấu hình: `threads=14`, `ngl=99`, `ctx=2048`, `max_tokens=64`, 10/10 request thành công
mỗi quant, warm-up đã bỏ. TTFT đo phía client; TPOT tính từ `predicted_n` do server báo,
nên hai cột này là hai đại lượng tách biệt chứ không phải end-to-end chia đôi.)*

**Quan sát** (≤ 60 chữ): 2-bit nhanh hơn bao nhiêu, và **có đáng không**? Bạn đã thử
hỏi cùng một câu trên cả hai (`make serve` vs `.venv/bin/python labs/02-serve/serve.py --compare`)
chưa? Chất lượng khác nhau thế nào?

Q2 nhanh hơn **1.17×** khi decode (TPOT 12.0 vs 14.1 ms) và nhỏ hơn 0.73 GB, nhưng TTFT
gần như y hệt (210 vs 215 ms) — prefill bị chặn bởi compute, không phải số byte weight.
Tôi đã hỏi cùng 5 câu ở `temperature=0` trên cả hai. Hoà ở câu dễ chấm (cả hai:
`17*24=408`, JSON đúng). Nhưng Q2 nói PagedAttention cấp phát bộ nhớ **"contiguous"** —
ngược hẳn ý tưởng cốt lõi — và bịa "GGUF (GPT-GPU)". **Không đáng:** 2.97 GB vẫn vừa 6 GB
VRAM, tôi không cần tiết kiệm 0.73 GB để đổi lấy câu trả lời lật ngược nội dung.

---

## 3. Serving under load  *(rubric 8, 9, 10 — 20 điểm)*

> Từ `benchmarks/02-server-results.md` (`make load-report`).

| Users | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Eff. concurrency | Failures |
|--:|--:|--:|--:|--:|--:|--:|
| 10 | 2.89 | 2400 | 3900 | 4500 | 7.3 | 0 (0.0%) |
| 50 | 2.95 | 15000 | 17000 | 17000 | 40.9 | 0 (0.0%) |

- **Offered load tăng 5×, throughput thực tăng:** _1.02×_
- **P95 tăng:** _4.36×_
- **Effective concurrency ở 50 users:** _40.9_ so với `--parallel` = _4_ slots

**Peak `llamacpp:n_busy_slots_per_decode`** (từ `make metrics` khi `make load-50` đang
chạy): _3.97_ / _4_ slots  *(kèm `requests_deferred` đỉnh **45**, `requests_processing` chạm trần 4 ở mọi mẫu)*

**Saturation reading** (≤ 80 chữ): server của bạn bão hoà ở đâu, và **bằng chứng nào**
thuyết phục bạn? Nếu P95 tăng nhanh hơn RPS thì phần latency thêm đó là queue time hay
compute time — bạn biết bằng cách nào? Nếu bạn phải nâng goodput@SLO, bạn sẽ đổi knob
nào **trước**, và vì sao knob đó?

**Bão hoà từ dưới 10 user.** Con số quyết định là RPS: 2.89 → 2.95 khi offered load tăng
5×. Đó là **queue time, không phải compute time**, và tôi biết nhờ ba dấu hiệu độc lập:
(1) RPS đứng yên trong khi P95 tăng 4.36× — nếu mỗi request tốn nhiều compute hơn thì RPS
đã phải *giảm*; (2) server tự khai `requests_deferred` đỉnh **45**, tức 45 request đang
nằm chờ slot; (3) `busy_slots` 3.97/4 nói engine không hề rảnh — nó chạy hết công suất,
chỉ là không có chỗ cho người mới.

Ghép lại: 45 chờ + 4 chạy ≈ 49 ≈ đúng 50 user locust mô phỏng, và khớp effective
concurrency 40.9. Occupancy/slot = 10.24, tức mỗi slot có ~10 request xếp hàng.

**Goodput ở SLO P95 ≤ 5 s:** 10 user → P95 3.9 s → giữ ~100% goodput ở 2.89 RPS. 50 user →
P95 17 s → **goodput = 0**, dù throughput danh nghĩa vẫn 2.95 RPS. Sau điểm bão hoà,
throughput không tăng mà goodput *sụp*.

**Knob tôi đổi trước: `--parallel` 4 → 8–12, kèm nâng `--ctx-size`.** Nút thắt đã được
định danh là **số slot**, nên phải nới đúng cái đang thiếu. Tôi không chọn tăng `-t` (sweep
`01-tuning-tg128-ngl99.md` chứng minh `-t` vô tác dụng khi đã offload GPU), không chọn hạ
xuống Q2 (chỉ 1.17×, trong khi khoảng cách cần bù là 10×, lại mất chất lượng). Phải nâng
ctx cùng lúc vì `ctx=2048` chia cho 4 slot đã chỉ còn 512 token/slot. Thành thật mà nói:
việc này sẽ **không** cho 10× — GPU vẫn là trần cứng — nhưng nó hạ P95 ở vùng concurrency
trung bình cho tới khi trần mới là băng thông GPU.

---

## 4. Integration  *(rubric 12, 13 — 15 điểm)*

> Từ `make pipeline`. Nói thật cái nào real, cái nào stub — stub **không** mất điểm.

| Day | Piece | Real hay stub? |
|---|---|---|
| N16 Cloud/IaC | không có IaC, chạy tay trên laptop | **stub** |
| N17 Data pipeline | `TOY_DOCS` hard-code, 6 chuỗi (`pipeline.py:36`) | **stub** |
| N18 Lakehouse | corpus nằm trong RAM process, mất khi thoát | **stub** |
| N19 Vector + features | đếm từ trùng nhau, không vector index, không embedding model (`pipeline.py:81`) | **stub** |
| N20 Serving | `llama-server` | real |

**Latency split** (mean của 3 query, từ output của `pipeline.py`):

- embed: _0.0 ms_
- retrieve: _0.0 ms_
- llm: _657.9 ms_
- **stage chiếm nhiều nhất:** _llm_ (_100%_ của total)

**Reflection** (≤ 60 chữ): bottleneck ở đâu? Có khớp với kỳ vọng của bạn không? Nếu
phải giảm latency của pipeline này 2×, bạn sẽ tấn công vào đâu?

`embed` và `retrieve` = 0.0 ms không phải vì nhanh mà vì **không tồn tại** — nói "LLM là
bottleneck" ở đây gần như là tautology. Chỗ tôi đoán sai mới đáng giá: lần chạy đầu cho
llm ≈ **2727 ms** trong khi server tự báo prefill+decode ≈ **370 ms**. Hơn 2.2 s không
thuộc stage nào. Cô lập được: `localhost` = 2542 ms, `127.0.0.1` = 326 ms cho cùng
request. Server bind IPv4-only, client thử `::1` trước và phải chờ timeout. **77% con số
tôi suýt ghi vào báo cáo là lỗi mạng phía client, không phải LLM** — bắt được nhờ
`pipeline.py` in cả hai đồng hồ. Giảm 2×: stream response (TTFT ~250 ms thay vì chờ đủ
658 ms) và cắt `max_tokens` từ 200 xuống, vì câu trả lời chỉ dài 24–30 token.

---

## 5. The single change that mattered most  *(rubric 11 — 10 điểm)*

> **Phần quan trọng nhất của report.** Không cần bonus track: `make tune` đã cho bạn
> một before/after thật (`benchmarks/01-tuning-tg128.md`). Đổi quantization,
> `LAB_N_CTX`, hay `--parallel` rồi đo lại cũng được.

**Change:** hạ `-t` từ 40 xuống 14 khi decode chạy trên CPU (`ngl=0`) — tức thôi
oversubscribe, về đúng số physical core

```
before:  8.6 tok/s   (-t 40, oversubscribe 2x số logical core)
after:   14.1 tok/s  (-t 14, đúng số physical core)
speedup: 1.64×
```

*(Cùng sweep còn cho biên độ rộng hơn: `-t 1` = 6.1 tok/s → `-t 14` = 14.1 tok/s là
**2.32×**. Tôi lấy 1.64× làm con số chính vì "hạ thread xuống" là thay đổi tôi thật sự sẽ
áp dụng — không ai cố tình chạy 1 thread, nhưng rất nhiều người mặc định `-t $(nproc)` hoặc
cao hơn.)*

**Tại sao nó work** (1–2 đoạn — đây là phần grader đọc kỹ nhất):

Toàn bộ đường cong: 6.1 → 13.9 → **14.1** → 12.2 → 8.6 tok/s cho `-t` 1/7/14/20/40. Phần
đáng chú ý không phải cái đỉnh mà là chỗ nó **ngừng dốc**: từ `-t 7` lên `-t 14`, tôi tăng
gấp đôi số core nhưng chỉ được **+1.4%**. Nếu decode bị chặn bởi FLOPs thì đoạn đó phải cho
gần 2×. Nó cho 1.4%, nghĩa là từ khoảng 7 thread máy đã **bão hoà băng thông bộ nhớ**. Cơ
chế: mỗi token decode phải kéo lại weight của các layer active từ DRAM và chỉ làm một phép
nhân ma trận–vector duy nhất trên đó — tỉ lệ tính-toán-trên-byte cực thấp. Ở 14 tok/s với
file 2.97 GB, con số này rơi vào vùng hàng chục GB/s, cùng bậc độ lớn với trần thực tế của
DDR5 dual-channel laptop. Thêm core không thêm được kênh nhớ.

Hai điểm bên phải đỉnh là hai cơ chế khác nhau và không nên gộp. `-t 20` (dùng hết logical
core) tụt còn 87% vì hyperthread không phải core: hai SMT sibling dùng chung L1/L2 và chung
cổng load-store, nên với workload đã nghẽn ở memory chúng chỉ làm bẩn cache. `-t 40` tụt
tiếp còn 61% vì lý do khác hẳn — scheduling: 40 thread tranh 20 lõi logic, và ggml đồng bộ
ở cuối mỗi layer, nên mỗi barrier phải chờ thread bị OS preempt; cả đoàn đi bằng tốc độ của
thằng chậm nhất.

**Chỗ kết quả trái với kỳ vọng từ deck, và tôi nghĩ đây mới là phần quan trọng nhất:** tôi
chạy sweep này **hai lần**. Lần đầu với cấu hình mặc định của lab (`ngl=99`, vì probe xác
nhận runtime CUDA thấy RTX 4050) cho đường cong **phẳng tuyệt đối**: 76.7 / 76.8 / 76.8 /
77.1 / 76.7 tok/s — chênh 0.5%, trong nhiễu đo (`01-tuning-tg128-ngl99.md`). Cùng một knob,
cùng một máy, cùng một model: đáng giá **2.32×** khi decode ở CPU, và đáng giá **0** khi
decode ở GPU. Lý do là `-t` chỉ điều khiển threadpool của backend CPU; khi 35 layer đã nằm
trên GPU thì CPU chỉ còn sampling token và đẩy byte HTTP — một thread thừa sức.

Bài học tôi rút ra không phải "chọn `-t 14`", mà là: **một knob chỉ có giá trị khi nó chạm
đúng bottleneck đang hoạt động.** Nếu tôi chỉ chạy `make tune` một lần theo mặc định, tôi
đã kết luận "thread count không quan trọng" — đúng với máy tôi, sai về cơ chế, và vô dụng
với người ngồi cạnh không có GPU. Đây cũng là lý do §6 của tôi dùng `-ngl` chứ không phải
`-t`: trên máy này, knob thật sự nới được nút thắt là chỗ đặt các layer.

---

## 6. Bonus  *(optional — tối đa 20 điểm)*

> Bỏ trống nếu không làm. Xem `bonus/README.md`. Đừng làm hết — **một** finding sâu
> ăn điểm hơn năm bảng nông.

**Đã làm:** B1 (`build-llama` + `compare-builds`, build MSVC 2019 `-DGGML_NATIVE=ON`) ·
B2 (`sweep-gpu`) · B3 (mục này) · B4 (challenge **C2** — KV cache quantization, script tự
viết `bonus/c2-kv-cache-quant.py`) · B5 (challenge **C8** — semantic cache,
`bonus/c8-semantic-cache.md`; kèm C9 embedding serving,
`benchmarks/bonus-c9-embedding-serving.md`)

**Numbers:** (B2 — GPU offload sweep, `benchmarks/bonus-gpu-offload-sweep.md`)

```
before:  13.7 tok/s   (-ngl 0,  toàn bộ 35 layer ở CPU)
after:   77.0 tok/s   (-ngl 99, toàn bộ layer trên RTX 4050)
speedup: 5.62×
```

Đường cong đầy đủ: `-ngl` 0/8/16/24/32/99 → 13.7 / 19.4 / 25.4 / 38.2 / 54.0 / 77.0 tok/s.

**Điều này nói lên gì mà deck chưa nói:**

**1. Partial offload cho lợi ích phi tuyến, và hiểu sai chiều là rất dễ.** Đường cong
**lồi lên**: 8 layer đầu chỉ mua thêm +5.7 tok/s, nhóm layer cuối mua thêm +23.0. Lý do là
thời gian mỗi token là **tổng nối tiếp** của phần CPU và phần GPU, còn tok/s là nghịch đảo
của tổng đó. Khi phía CPU còn nhiều, bỏ vài layer chỉ cắt được một phần nhỏ của tổng. Hệ
quả thực tế: "offload được một nửa model" **không** mang lại một nửa lợi ích — mà ít hơn
nhiều. Ai đang ở partial offload thì việc mua thêm VRAM để nhét nốt phần cuối có giá trị
cao hơn hẳn so với suy luận tuyến tính.

**2. Hai bonus còn lại đều cho kết quả *âm*, và đó mới là phần tôi học được nhiều nhất.**
Cả hai đều là những knob deck trình bày như chiến thắng hiển nhiên:

- **B1 — compile cho đúng CPU của mình: 14.8 → 15.0 tok/s, tức 1.01×, bằng đúng nhiễu đo.**
  Không phải build hỏng. Prebuilt Windows ship **14 DLL CPU backend** và chọn theo CPUID
  lúc chạy; tôi xác nhận nó nạp `ggml-cpu-alderlake.dll` — đúng biến thể AVX2 cho Raptor
  Lake. Trong khi đó cmake báo `HAS_AVX512 - Failed`, nên `-DGGML_NATIVE=ON` cũng chỉ bật
  được `/arch:AVX2`. Hai bên chạy **cùng tập lệnh**. Cộng thêm: workload bandwidth-bound
  (bằng chứng ở §5: 7→14 thread chỉ +1.4%), nên kể cả kernel tốt hơn cũng chỉ rút ngắn
  phần không phải nút thắt.
- **C2 — KV cache `q8_0`: tiết kiệm 29–60 MiB (~2% VRAM) nhưng TPOT **chậm hơn 7%**
  (13.83 → 14.89 ms).** Mỗi decode step phải dequantize KV; ở ctx 2048–16384 thì KV chưa đủ
  lớn để việc đọc ít byte hơn bù lại chi phí đó. Chất lượng không đổi: cả hai đạt 9/10 và
  **fail đúng cùng một item với output trùng khít từng ký tự**. Lý do mức tiết kiệm bé đến
  vậy: KV cache **không phải** phần chiếm chỗ — Gemma 4 E2B dùng chung KV ở 20/35 layer, và
  ~1.7 GB mà server thêm vào gần như toàn bộ là weight.

**Sợi chỉ chung của cả ba:** deck mô tả đúng *cơ chế*, nhưng mỗi cơ chế chỉ sinh lời khi
thứ nó tối ưu đang **thật sự là nút thắt**. FP8 KV cache thắng đậm trên GPU datacenter
phục vụ context dài batch lớn — ở đó KV cache thật sự chiếm bộ nhớ. Trên laptop 4 slot ×
512 token, cùng knob đó là chi phí thuần. Kernel chuyên biệt cho silicon thắng khi chưa ai
build sẵn cho bạn — nhưng runtime dispatch đã lo phần lớn rồi. Bài học tôi mang đi: **đo để
tìm nút thắt trước, chọn knob sau** — thứ tự ngược lại tốn 20 phút compile để nhận về
1.01×.

---

## 7. Điều làm bạn ngạc nhiên nhất  *(optional)*

_(1–2 câu. Không bắt buộc, nhưng grader đọc hết.)_

Việc `localhost` chậm hơn `127.0.0.1` **2.1 giây mỗi request** — đủ để chiếm 77% "LLM
latency" trong pipeline RAG của tôi, và tôi đã suýt ghi con số đó vào báo cáo như thể đó
là chi phí inference. Ngạc nhiên thứ hai: trong bonus C8, **stub bag-of-words 40 dòng phân
loại paraphrase tốt hơn** decoder 5B chạy ở pooling mode — nó bắt đúng paraphrase mà
embedder "thật" bỏ lỡ, và không dính false hit mà embedder "thật" mắc phải.

---

## 8. Self-check trước khi push

- [x] `hardware.json` committed
- [x] `models/active.json` committed
- [x] `benchmarks/01-quickstart-results.md` committed (`make bench`)
- [x] `benchmarks/01-tuning-tg128.md` committed (`make tune`)
- [x] `benchmarks/02-server-results.md` committed (`make load-report`)
- [x] `benchmarks/02-server-batching-u50.md` hoặc `-metrics-u50.csv` committed (`make metrics`)
- [x] `benchmarks/locust-10_stats.csv` + `locust-50_stats.csv` committed (`make load-10` / `load-50`)
- [x] `benchmarks/03-integration-results.md` committed (`make pipeline`)
- [x] Mọi section **"required — replace this line"** trong các file `benchmarks/*.md`
      đã được thay bằng nhận xét của tôi
- [x] 5 screenshots trong `submission/screenshots/`
- [x] `make verify` → **exit 0**
- [ ] Repo GitHub ở chế độ **public**
- [ ] Đã paste public URL vào VinUni LMS
- [x] **Không** commit `models/*.gguf` hay `runtime/` (đã có trong `.gitignore`)

**Quan trọng:** repo phải **public** đến khi điểm được công bố. Private → grader không
xem được → 0 điểm.
