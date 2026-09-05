# M3 performance record

## G1: unchanged M2 overlay — PASS

Measured on the physical PYNQ-Z1 on 2026-09-04 local time (run metadata:
2026-09-05T02:19:02 UTC). This closes the baseline/methodology gate, **not M3**.
The most comparable current result is **0.140 GMAC/s delivered for M=16,
including packing**, versus **0.383 GMAC/s** for the native CPU baseline with
the same logical operands and shared-scratchpad destination. The FPGA does not
yet beat this CPU implementation on either measured shape.

The historical M2 acceptance result stays unchanged: **5.793 GMAC/s** from
compute/pack cycle counters, versus **0.085 GMAC/s / 110.649 ms** for its
validation-heavy acceptance harness. Neither number was a GPT-2 token rate.

### Reproduction and identity

```bash
python3 -m unittest tests.m3.test_benchmark -v
bash -n zynq/run_m3_baseline.sh
M3_BASELINE_RESULT_DIR="$PWD/build/m3_baseline2" bash zynq/run_m3_baseline.sh
```

The runner checks the accepted M2 bit/HWH hashes **before programming**, builds
the CPU library on the A9, runs M1 on that exact overlay, then programs it for
the benchmark. Login-shell `sudo -E` preserves PYNQ's XRT environment; normal
interactive sudo authentication is used, with no stored credential.

| Artifact | SHA-256 |
|---|---|
| `build/m2_qual2/m2_pynq.bit` | `f196e92c4509ebad977521bf40a8cd30b0f3f131fbfe199515d6e0ff6600fa03` |
| `build/m2_qual2/m2_pynq.hwh` | `f77dfe909dd8a3d7d0266d4326c05ceb1eb97a0182bbd4d67acf25a96833c390` |
| `zynq/m3_benchmark.py` | `18ac0bf7433421bb0d7cfb89fc8d3c13cface596854be40df0bd26afbe0e564c` |
| `zynq/m3_cpu_gemm.c` | `7a823a587e04c609009ef8c75a06205b411a3fda7d29d36a0eae896e55f1238c` |
| `build/m3_baseline2/m3_cpu_gemm.so` | `d8a5d2a1a0d7e84826b6fb2205a1e57f301cfe733000b9339088102c8f08f2d1` |
| `build/m3_baseline2/board.log` | `114f0e5309ebe4093ceba3978ca31ee3a29221fbc76602d41d0836ef62cba110` |
| `build/m3_baseline2/m3_baseline.json` | `a25a78842cfa915d614b2f4c53801ef1e5a63a21568c4faa95fc3eb1cf597f84` |

Raw JSON retains every timed sample and its phase intervals, configuration,
clock-tree report and source hashes. The earlier exploratory benchmark is
preserved separately in `build/m3_baseline/`, including its source snapshot;
the tables below use only the final interleaved run, not cross-run ratios.

Board: ARMv7 Cortex-A9, Linux 6.6.10-xilinx-v2024.1, Python 3.10.4, NumPy 1.21.5,
PYNQ 3.1.1. Kernel clock-tree readback reports `cpu_div=650000000` Hz; cpufreq
governor information is unavailable. FCLK0 configuration reads 100 MHz; the
qualified overlay's MMCM supplies 95 MHz to fabric. These are configuration
readbacks, not oscilloscope frequency measurements. No CPU frequency, scheduler
or global board settings were changed.

### Work and measurement boundary

Both shapes compute `sat16(A[M,768] @ B[768,768])`, exact signed-int8 products
and wide integer reduction, followed by **one final int16 saturation**. Seed
`0x50414d32`, values `[-32,31]`, 48 descriptors of N=16. For M=16 the generated
inputs also match the historical M2 workload. M=1 is decode-*like* and M=16
prefill-*like*: neither is a transformer layer or a complete decode step.

| M | Useful MACs | Logical input bytes | Packet input bytes | Output bytes | Qualified compute/pack cycles |
|---|---:|---:|---:|---:|---:|
| 1 | 589,824 | 590,592 | 626,688 | 1,536 | 37,536 |
| 16 | 9,437,184 | 602,112 | 1,179,648 | 24,576 | 154,752 |

Inputs, output buffers, MMIO mappings and the CPU library exist before timing.
Reference generation, overlay programming, allocation, warmups and correctness
checks are excluded. **Dispatch, input copies when required, DMA transfers and
cache maintenance, receive completion, result assembly, publication to shared
scratchpad, and an ordered final read fence are included.** Harts are held in
reset for this A9-driven test. M1 passes separately on the identical overlay.

Each policy has three warmups and 30 measured trials. Policies are deterministically
shuffled within each repetition, with no deliberate cache flush: these are warm
repeated workloads. Every trial is checked against the int64 NumPy reference
after timing, both in delivered DDR and in shared scratchpad. The first warmup
also captures and checks all 48 per-descriptor cycle/MAC/tag counters; every
subsequent run checks descriptor count, final counters, idle state and errors
outside timing. These counter reads are not hidden in the measured runtime.

All timed paths include disjoint host phase instrumentation. Phase boundaries
include adjacent loop/bookkeeping overhead; they are elapsed host intervals,
not measurements of pure link or arithmetic activity. Total wall latency is the
sum of those intervals. Compute cycles **overlap** input/output activity and
must not be added to the wall-time phases.

### Policies and CPU implementation

- `sleep_copy_packed`: prepacked ordinary DDR packets; one reusable input CMA
  buffer; paired descriptors; 100-us sleeps while waiting, as in the legacy
  driver. Validation is removed from timing, so this is not the old acceptance
  harness rerun verbatim.
- `spin_copy_packed`: same inputs/buffering, but bounded busy polling. This
  consumes A9 CPU time; it is not a power or CPU-offload improvement claim.
- `spin_resident_packed`: all packets already in DMA-ready CMA DDR; retains
  required cache operations and wire traffic but excludes packet packing and
  initial staging. Input CMA usage rises from 13,056/24,576 bytes (M=1/16) to
  626,688/1,179,648 bytes. This measures reusable resident data, not new inputs.
- `spin_resident_logical`: starts from ordinary row-major A/B and packs into
  preallocated CMA during timing. This exposes the real cost excluded above.
- `spin_compact_packed` / `spin_compact_logical`: same respective residency
  boundaries, but reuse plain NumPy views for copy-only operations and publish
  the assembled DDR result in one batch. PYNQ still owns DMA buffers and performs
  all required flush/invalidate calls. Publication is at projection completion;
  incremental tile visibility is not promised by this benchmark endpoint.
- `cpu_logical`: starts from the same row-major A/B and delivers to the same
  scratchpad. `zynq/m3_cpu_gemm.c` uses one A9 thread, explicit NEON intrinsics,
  16-column register tiling, int32 accumulators and saturating narrowing. Its
  8x8 products widen **before** addition, avoiding int16 intermediate overflow.
  No model-specific packing, BLAS, multithreading or assembly tuning. It is a
  practical baseline, **not the best achievable CPU**. FFI call/validation
  overhead is timed; the reference checks are not.

CPU compilation: GCC (Ubuntu 11.2.0-19ubuntu1) 11.2.0,
`-O3 -Wall -Wextra -Werror -shared -fPIC -mcpu=cortex-a9 -mfpu=neon`.
Twenty independent CPU qualification cases pass on the actual ARM implementation,
including full-range int8, K=3072, cancellation, saturation, N tails and full
projection shape. The host unit test also checks the portable C fallback and
compares vectorized packing with the legacy packer.

### Delivered results

GMAC/s is useful MACs divided by median wall latency, counting one multiply plus
accumulate as **one MAC**, not two MACs. p95 uses NumPy's linear percentile.

| Policy | M=1 median / p95 (ms) | M=1 GMAC/s | M=16 median / p95 (ms) | M=16 GMAC/s |
|---|---:|---:|---:|---:|
| Sleep, copy, packed | 84.132 / 84.913 | 0.00701 | 88.877 / 89.291 | 0.10618 |
| Spin, copy, packed | 72.012 / 72.487 | 0.00819 | 76.393 / 76.797 | 0.12354 |
| Spin, resident, packed | 62.917 / 63.344 | 0.00937 | 65.023 / 65.655 | 0.14514 |
| Spin, resident, logical | 90.426 / 91.732 | 0.00652 | 93.908 / 94.889 | 0.10049 |
| Spin, compact, packed | 55.548 / 57.263 | 0.01062 | 57.545 / 57.966 | 0.16400 |
| Spin, compact, logical | 65.200 / 65.903 | 0.00905 | 67.618 / 68.020 | 0.13957 |
| CPU, logical | 2.195 / 2.267 | 0.26869 | 24.639 / 24.715 | 0.38302 |

Variability is retained rather than presenting just the fastest trial:

| Policy (same order) | M=1 min–max (ms), CV | M=16 min–max (ms), CV |
|---|---:|---:|
| Sleep, copy, packed | 83.104–85.516, 0.537% | 88.269–89.359, 0.265% |
| Spin, copy, packed | 71.637–72.731, 0.347% | 75.896–77.267, 0.357% |
| Spin, resident, packed | 62.607–66.788, 1.139% | 64.475–65.867, 0.462% |
| Spin, resident, logical | 90.076–91.932, 0.520% | 93.269–95.218, 0.510% |
| Spin, compact, packed | 55.318–57.927, 1.130% | 57.161–58.000, 0.348% |
| Spin, compact, logical | 64.921–66.747, 0.564% | 67.446–68.202, 0.248% |
| CPU, logical | 2.162–2.274, 1.467% | 24.551–24.803, 0.197% |

For a common **logical-input → shared-result** boundary, the compact FPGA path
is still about **29.70x slower at M=1 and 2.74x slower at M=16** than this CPU.
The resident packed rate of 0.164 GMAC/s is useful to report, but not interchangeable
with the packing-inclusive 0.140 GMAC/s. Neither approaches the compute-only
5.793 GMAC/s because they include the full operating path.

### Measured improvement and remaining costs

With identical logical-input boundaries, compact buffer handling and batched
publication reduce M=16 median latency **93.908 → 67.618 ms (1.389x)** and M=1
**90.426 → 65.200 ms (1.387x)**. This is the isolated compact-policy comparison
within one run. Separately, spin polling improves the copy/packed M=16 policy
88.877 → 76.393 ms. Resident input eliminates repeated staging only when data
really are reusable; it is not a free benefit for new activations.

Representative M=16 mean phase intervals (ms):

| Host phase | Resident logical | Compact logical |
|---|---:|---:|
| Packing into CMA | 28.767 | 9.985 |
| Descriptor dispatch | 6.925 | 6.802 |
| MM2S API/cache/transfer/wait | 23.948 | 23.875 |
| Receive arm + S2MM API/cache/wait | 22.287 | 22.010 |
| Result assembly | 7.806 | 2.331 |
| Publication | 3.430 | 1.918 |

The JSON also records the remaining small host/fence intervals. The CPU's mean
compute/FFI interval is 23.224 ms and publication is 1.363 ms at M=16. The
accelerator's separately measured compute/pack time is only 1.629 ms. The send
and receive intervals above include Python/PYNQ/cache operations and hardware
waiting: **they do not isolate raw DMA bandwidth or prove every residual cost
is Python**. No sums of overlapping engine/link counters are used.

The full-tile packet format has 8 useful MAC/input byte. A 32-bit stream at
95 MHz therefore imposes an **ideal calculated 3.04 GMAC/s input ceiling**
(380 MB/s), even assuming perfect overlap and no gaps. This is not a measured
bandwidth result. Reducing repeated A traffic, amortizing host dispatch/cache
operations, and keeping GEMM/SFPU chains resident are meaningful M3 design
considerations; the present data do not establish a speedup for unbuilt hardware.

### Acceptance and limits

`M1 BOARD PASS elapsed_s=0.047` and `M3 G1 BENCHMARK PASS` are recorded in the
final log. All 420 measured projections plus 42 warmup projections match DDR
and shared memory; FPGA policies execute 19,008 descriptors in total. All 20
native CPU qualification cases and three host unit tests pass. No arithmetic
RTL, dependency pin, accepted M2 artifact or hardware clock changed.

These are two synthetic warm projection workloads, one CPU implementation and
one Linux/PYNQ operating environment. No full-model speedup, token/s, power,
energy, concurrent-hart performance or peak-DDR claim is made. These baseline
figures qualify only the unchanged M2 overlay; new M3 measurements follow.

## G5: physical M3 operators and chains — PASS

Run start: **2026-09-05T04:38:12 UTC**, physical PYNQ-Z1 over SSH. Exact overlay:
`build/m3_qual3/m3_pynq.bit`, SHA-256
`78fc22f0e9263759ed2ac6417345ce8c6ef7815438febd9c6a4332532790be5b`.
It passed the 95 MHz implementation gate at +0.483 ns setup / +0.018 ns hold,
zero TNS and zero DSPs. The independent rebuild is recorded separately in
`M3_VERIFICATION.md`; it does not change these measured samples.

```bash
M3_VIVADO_BUILD_DIR=build/m3_qual3 bash zynq/run_m3_board.sh
```

The runner checks the manifest locally and remotely before programming, then
runs unchanged M1, unchanged M2, M3 qualification/benchmarks, and M1 again on
the **same bit/HWH**. All passed. M3 executes 11,072 GEMM and 4,033 SFPU
descriptors, including 1007 mixed GEMM and 3472 SFPU qualification packets,
seven repeated operator tests and both repeated chains. Exact output, numerical
budgets, descriptor counters, tags and cycles are checked, as described in the
verification record. Board Python 3.10.4, NumPy 1.21.5, PYNQ 3.1.1 and Linux
6.6.10-xilinx-v2024.1 are unchanged from G1. FCLK0 is configured at 100 MHz;
the qualified MMCM supplies 95 MHz. No board-global tuning was performed.

### Measurement boundary

Every operator and chain has **three warmups and 30 timed repeats**. Operator
order is deterministically shuffled within each repetition; each chain runs
its own repeated workload. These are warm repeated synthetic inputs, not cold
checkpoint loading. Raw samples, median, p95, min/max, mean and coefficient of
variation are retained in JSON. p95 uses NumPy's linear percentile.

- Operator timing starts with prepacked input in ordinary DDR and ends with
  the result copied into ordinary DDR. CMA staging, descriptor/route dispatch,
  both DMA channels, required flush/invalidate, waiting and output copy are
  inside timing. Allocation, packet preparation and reference checking are out.
- Chain timing additionally includes patching consumers from **actual previous
  results**, A9 calculation of dynamic row-quantization parameters, int8 packet
  packing, intermediate assembly, and compact final publication to shared
  scratchpad with an ordered read fence. Fixed weights/coefficients and packet
  layouts are prepacked before timing. No direct fabric GEMM→SFPU forwarding
  is implied; each descriptor returns through DDR and A9 control.
- All reference/tensor checks occur **after** the complete operator or chain.
  Intermediate result captures are retained inside the chain boundary so they
  can be checked later; this overhead is not silently subtracted.
- Harts are held reset during timed work. Both harts pass M1 separately before
  and after testing; concurrent operation is qualified in cluster simulation,
  not claimed as a physical performance result. Bounded spin polling occupies
  an A9 thread. Compute counters overlap DMA/control intervals and must not be
  added to delivered wall latency or treated as disjoint host phases.

### Operator results

All times below are milliseconds. Compute is the validated hardware counter
divided by 95 MHz; delivered latency is the measured boundary above. Non-GEMM
operators are reported in latency, **not GMAC/s**.

| Operation / length | Compute cycles | Compute ms | Delivered median / p95 ms | Input / output bytes |
|---|---:|---:|---:|---:|
| GELU / 3072 | 18,432 | 0.194021 | 1.371216 / 1.413509 | 12,288 / 12,288 |
| LayerNorm + affine / 768 | 216,121 | 2.274958 | 3.334824 / 3.390267 | 9,216 / 3,072 |
| Masked softmax / 1024 | 120,576 | 1.269221 | 2.319736 / 2.379861 | 4,096 / 4,096 |
| AFFINE / 1024 | 76,800 | 0.808421 | 1.898761 / 1.970099 | 12,288 / 4,096 |
| REQUANT8 / 3072 | 230,400 | 2.425263 | 3.618817 / 3.680158 | 12,288 / 12,288 |
| AFFINE_GELU / 3072 | 236,544 | 2.489937 | 3.802430 / 3.870529 | 36,864 / 12,288 |
| Residual ADD / 768 | 3,072 | 0.032337 | 1.161652 / 1.230000 | 6,144 / 3,072 |

| Operation (same order) | Delivered min–max ms | CV |
|---|---:|---:|
| GELU | 1.354586–1.445638 | 1.391% |
| LayerNorm | 3.309021–3.418720 | 0.818% |
| Softmax | 2.297053–2.402604 | 0.994% |
| AFFINE | 1.876663–1.979998 | 1.388% |
| REQUANT8 | 3.577023–3.705910 | 0.754% |
| AFFINE_GELU | 3.778568–3.884304 | 0.720% |
| ADD | 1.134719–1.243286 | 2.517% |

The 64-bit shared sequential arithmetic deliberately trades latency for
portability, bounded resource use and exact frozen numerics. For example,
REQUANT8 has one output word per element even though its value is int8, and
its multiplication/rounding takes 75 cycles per element. Neither these numbers
nor the original GEMM peak establish an SFPU CPU speedup.

### Integrated actual-result chains

The MLP is a **single-row pre-LayerNorm MLP sub-block**, not a transformer layer:
768→3072→768, dynamic int8 conversion, wide K=3072 down-projection,
affine/GELU, rescaling and residual ADD. The attention test is **one 64-wide
head**, 1024 keys with 768 valid entries, scale 1/8, stable masked softmax,
probability conversion and **only a 16-column value output tile**. There are no
Q/K/V projections, full multi-head output projection, embedding lookup, model
checkpoint or token loop in either measurement.

| Chain | Descriptors / actual-result patches | Engine compute ms | Delivered median / p95 ms | Min–max ms / CV |
|---|---:|---:|---:|---:|
| MLP 1×768→3072→768 | 246 / 245 | 11.595042 | 344.713333 / 345.789204 | 343.758701–345.888483 / 0.167% |
| Attention 64×1024→16 | 69 / 5 | 2.967642 | 78.038904 / 78.275496 | 77.899497–78.828666 / 0.224% |

| Chain | Input / output DMA bytes | Final publication bytes | Useful GEMM MACs |
|---|---:|---:|---:|
| MLP | 5,090,304 / 52,224 | 1,536 | 4,718,592 |
| Attention | 107,712 / 16,512 | 32 | 81,920 |

Engine time is the sum of validated per-descriptor compute counters, not an
alternate end-to-end latency. JSON also gives GEMM MACs divided by the whole
mixed-chain wall time; this is **not** the SFPU's arithmetic rate, kernel GMAC/s
or an apples-to-apples replacement for the G1 projection benchmark. Delivered
latency is the fair headline for these mixed workloads. No native CPU baseline
for these complete chains was measured, so no chain speedup is claimed.

### Evidence and limitations

| Evidence | SHA-256 |
|---|---|
| `build/m3_qual3/board.log` | `074af80835b0c71b180a5a558e60594aa0e706f50ec61badce91fe49d1c540b1` |
| `build/m3_qual3/board.json` | `cb7faf85c66a5b097b01e88091e75c82e42a1d21daea193058b5f50100ebabe4` |
| `build/m3_qual3/board_manifest.json` | `0c304167a86517ca834c7665c520000befa4639ce72a6647e86ae80b8da686d5` |
| `zynq/m3_run.py` | `aec8ff011ea0663da08d10ee5ae888367b460206c7b698900bca2b7447ad1e2f` |

The manifest contains all staged source/vector/bit/HWH hashes and captured
build-source/report hashes. The G1 CPU comparison and historical M2 figures
remain immutable; the unchanged M2 acceptance harness on this new M3 overlay
also passes (107.529 ms, validation included), but that single regression run
is not a new repeated performance comparison. These tests establish exact
operator/chain functionality with measured costs, **not** GPT-2 model accuracy,
inference latency, tokens/s, CPU speedup, measured power or autonomous inference.
