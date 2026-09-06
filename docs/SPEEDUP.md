# M4 performance — validated resident and process-start measurements

The physical FPGA offload path is **slower than the matching native A9 CPU
baseline** for this full GPT-2 workload. A 13-token prompt plus 20 generated
tokens takes a median **433.008 s on FPGA versus 113.483 s on CPU**: **0.04619
versus 0.17624 delivered tokens/s**, including prefill. FPGA latency is 3.816x
higher. This is a measured result, not a failed correctness check: all timed
outputs pass their independent exact checks. A speedup was not an M4 gate.

The complete resident report is terminal and audited. Physical CPU/FPGA
full-context and supplemental process-cold qualification also pass. M4 closure
is recorded in `M4_VERIFICATION.md`. M3's 5.793 kernel GMAC/s and 0.085 synthetic-chain
end-to-end GMAC/s have different workloads/boundaries; neither predicts GPT-2
performance. Diagnostic correctness times include validation and are not used
as benchmarks here.

## Workload and sampling

The sampling contract is `tests/m4/performance_policy.json`, committed before
performance timing. It uses the frozen story prompt (13 token IDs) with both
the native quantized A9 CPU backend and the exact M3 FPGA overlay. The scheduler,
model pack, full vocabulary and quantized arithmetic are shared. Single-thread
native C/NEON CPU arithmetic is the baseline; it is not FP32 GPT-2 and is not
claimed to be the fastest possible ARM implementation.

For each backend: three warmups and twenty measured trials of prefill/first
token and cached decode at the same 13-token prefix. CPU/FPGA order is paired
and deterministically interleaved. Three complete 20-token generation chains
per backend follow; the smaller chain sample count is predetermined because
diagnostic runs already show seconds-to-tens-of-seconds per token. Twenty fixed
trials remain mandatory. Three chains are three independent observations, not
sixty, and cannot establish a reliable production tail latency.

The common headline boundary is **resident token IDs in → greedy token IDs
delivered in a Python list**. Reset for prefill/generation, model computation,
metadata, packet packing, dispatch, DMA/cache maintenance, KV writes, all logits
and selection are included. Reference checks, text tokenization/detokenization,
networking and UI are excluded and must remain visibly excluded in summaries.
Cached decode restores an identical already-prepared prefix outside timing;
that does not make prefix preparation free. Full generation starts with reset
and includes its prefill.

Retain every raw sample and order. Report median, interpolated p95, range,
mean, standard deviation, physical transfer bytes, peak RSS, PSS/swap snapshots and the
fixed 110,592-byte CMA allocation. Separate process initialization/model
integrity checks and warmup from resident results. Integrity scans warm the
OS page cache, so this is **not disk-cold timing**. No global cache drop,
governor change or other board tuning is authorized or required.

Profile complete backend GEMM/SFPU calls as non-overlapping wall spans. Their
sum plus residual host wall equals model wall time. Hardware compute-cycle
counters are separate diagnostics that overlap transfers; never add them to
those wall spans. Compare all seven SFPU operations and representative GEMMs.
Measure scalar versus equivalent batched dynamic V requantization with the
same inputs at lengths 13, 32 and 1024, width 64. Exact output and effective
scale checks occur after each measurement. A primitive improvement is not
automatically an integrated improvement. Report any slowdowns.

All **794 raw observations** are retained: 108 warmups and 686 measurements
(600 primitive/bridge, 80 fixed-model, six full-generation). Three two-token
prefill/decode warmups precede each backend's three full chains; these are not
three discarded 20-token chains. No sample was dropped or trimmed.

## Resident model results

Times are seconds. p95 is linear interpolation of the observed samples;
standard deviation is the population standard deviation. Fixed workloads have
n=20 per backend; full generation has only n=3. No confidence interval or
production tail guarantee is implied.

| Workload | Backend | n | Median | p95 | Min–max | Mean | Std. dev. |
|---|---|---:|---:|---:|---:|---:|---:|
| 13-token prefill → first token | CPU | 20 | 36.234 | 36.303 | 34.320–36.305 | 35.605 | 0.897 |
| 13-token prefill → first token | FPGA | 20 | 71.242 | 71.511 | 68.111–71.677 | 70.370 | 1.354 |
| Cached next token, resulting context 14 | CPU | 20 | 4.001 | 4.004 | 3.787–4.005 | 3.929 | 0.099 |
| Cached next token, resulting context 14 | FPGA | 20 | 18.645 | 18.765 | 18.030–18.828 | 18.490 | 0.281 |
| Prefill + 20 generated tokens | CPU | 3 | 113.483 | 113.578 | 113.210–113.589 | 113.427 | 0.159 |
| Prefill + 20 generated tokens | FPGA | 3 | 433.008 | 434.599 | 432.243–434.776 | 433.342 | 1.060 |

CPU/FPGA ratios of latency medians are **0.50861** for first token, **0.21461**
for fixed decode, and **0.26208** for full generation. Equivalently, FPGA is
1.966x, 4.660x and 3.816x slower. Medians of the paired per-trial CPU/FPGA ratios
are 0.50771, 0.21380 and 0.26232 respectively; these are different statistics,
not interchangeable rounding choices.

| Throughput boundary | CPU median | FPGA median |
|---|---:|---:|
| Prefill input tokens / model time before greedy selection | 0.35879 input tokens/s | 0.18248 input tokens/s |
| Fixed cached decode, one delivered token / complete step | 0.24991 tokens/s | 0.05363 tokens/s |
| All 20 delivered tokens / complete generation including prefill | 0.17624 tokens/s | 0.04619 tokens/s |
| Nineteen cached tokens / cached portion of each full chain | 0.24607 tokens/s | 0.05254 tokens/s |

Model-prefill latency before greedy selection is 36.233 s CPU / 71.241 s FPGA
(medians); the headline first-token clock also includes selection/list delivery.
Input-token throughput is not output generation throughput. Throughput
distributions are computed per observation; complete p95/range/mean/deviation
and paired ratios are in the analysis JSON.

Every independent full-chain observation is shown below; the small n=3 p95
above is descriptive only. Cached steps advance through contexts 14–32.

| Trial | CPU total s | CPU first token s | CPU cached portion s | FPGA total s | FPGA first token s | FPGA cached portion s |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 113.588569 | 36.277059 | 77.311478 | 433.008388 | 71.402812 | 361.605542 |
| 1 | 113.483428 | 36.270564 | 77.212831 | 432.243420 | 71.420759 | 360.822630 |
| 2 | 113.210140 | 36.187521 | 77.022587 | 434.775636 | 71.776757 | 362.998845 |

The 57 cached-step latencies nested within each backend's three chains have
median/p95 4.063/4.109 s CPU and 19.092/19.210 s FPGA. They are **not 57
independent chain trials**, nor a fixed-context distribution. Full-context
correctness testing is separate: these short-context timing results cannot
be extrapolated to latency at 1024 positions.

## Measured costs and transfer accounting

Each cell below is mean seconds and share of total measured wall time.
The three columns form a disjoint partition. GEMM/SFPU spans include the entire
backend call, not just fabric computation. Host remainder includes scheduling,
metadata, packet construction outside the backend, KV and greedy/list work.

| Workload/backend | GEMM calls | SFPU calls | Host remainder |
|---|---:|---:|---:|
| Prefill CPU | 3.121 (8.8%) | 9.315 (26.2%) | 23.169 (65.1%) |
| Prefill FPGA | 24.509 (34.8%) | 22.402 (31.8%) | 23.459 (33.3%) |
| Fixed decode CPU | 0.555 (14.1%) | 0.957 (24.3%) | 2.418 (61.5%) |
| Fixed decode FPGA | 13.766 (74.4%) | 2.294 (12.4%) | 2.430 (13.1%) |
| Full chain CPU | 13.964 (12.3%) | 28.321 (25.0%) | 71.143 (62.7%) |
| Full chain FPGA | 293.183 (67.7%) | 68.525 (15.8%) | 71.635 (16.5%) |

The exact operation/packet/byte counts are invariant across repetitions of
each workload. CPU and FPGA execute matching GEMM MAC counts and SFPU operation
counts; CPU does not perform DMA.

| Workload | GEMM MACs | GEMM packets | SFPU packets | DMA input bytes | DMA output bytes |
|---|---:|---:|---:|---:|---:|
| Prefill/first token | 1,145,144,064 | 15,958 | 12,020 | 247,523,724 | 25,202,948 |
| Fixed cached decode | 123,790,080 | 9,046 | 1,232 | 136,497,996 | 2,582,852 |
| Full 20-token chain | 3,500,307,456 | 190,136 | 35,428 | 2,864,564,208 | 81,023,824 |

Full generation moves **2,809.132 MiB** through DMA, despite a 195.763-MiB
packed model: weights are streamed repeatedly and packet metadata/results add
traffic. One fixed decode alone moves 132.638 MiB. A9 launches and checks many
small transfers; the packet interface does not provide resident fabric weights
or an autonomous full-model schedule.

For the full chain, GEMM hardware counters total 176,320,112 cycles
(1.856001 s at 95 MHz) and SFPU counters total 1,221,866,593 cycles
(12.861754 s). These intervals occur inside/overlap backend transfer/control
work and **must not be added to the wall spans above**. The large difference
from 293.183 s GEMM-call wall time is evidence of substantial non-compute cost;
this instrumentation does not separately attribute that gap to every driver,
copy, transfer or waiting component. It is not proof that removing Python
alone would recover the whole gap. The matching CPU path also spends most
time outside its native GEMM kernel. No unmeasured optimization or M5 speedup
is claimed.

## Primitive comparisons and controlled batching improvement

These are complete host-delivered calls, including required packing and
FPGA transfers, with 3 warmups and 20 measured trials each. Times below are
milliseconds. Inputs are deterministic; GEMMs use actual packed checkpoint
weights. The N=17 case is a representative column-tail shape, not an entire
vocabulary projection. GELU/AFFINE/REQUANT8/AFFINE_GELU/ADD lengths are 3072,
LayerNorm 768 and masked softmax 13.

| Primitive | CPU median / p95 ms | FPGA median / p95 ms | CPU/FPGA median-latency ratio |
|---|---:|---:|---:|
| GEMM M=1, K=3072, N=16 | 0.730 / 0.794 | 1.985 / 2.020 | 0.3681 |
| GEMM M=1, K=768, N=17 | 0.660 / 0.671 | 3.539 / 3.689 | 0.1864 |
| GELU | 1.052 / 1.144 | 2.095 / 2.209 | 0.5021 |
| LayerNorm | 1.237 / 1.358 | 4.021 / 4.061 | 0.3077 |
| Masked softmax | 0.978 / 0.994 | 1.835 / 1.898 | 0.5329 |
| AFFINE | 1.384 / 1.399 | 4.510 / 4.618 | 0.3068 |
| REQUANT8 | 1.257 / 1.323 | 4.315 / 4.357 | 0.2913 |
| AFFINE_GELU | 1.465 / 1.698 | 4.579 / 4.711 | 0.3199 |
| ADD | 1.099 / 1.165 | 2.110 / 2.192 | 0.5206 |

FPGA is slower for **all nine** delivered primitives in this experiment.
That does not negate fabric arithmetic throughput; it exposes the cost of the
actual interface and these shapes.

The controlled before/after comparison uses identical signed-int16 dynamic
V-bridge inputs with width 64. Scalar per-column REQUANT8 is compared against
the runtime's exactly equivalent batched AFFINE composition. Output codes and
effective units match after every timed observation. Times are milliseconds.

| Context length | CPU scalar → batched median | CPU improvement | FPGA scalar → batched median | FPGA improvement |
|---|---:|---:|---:|---:|
| 13 | 93.099 → 3.274 | 28.438x | 145.779 → 4.622 | 31.539x |
| 32 | 93.821 → 3.721 | 25.214x | 145.691 → 6.080 | 23.964x |
| 1024 | 131.644 → 53.234 | 2.473x | 226.332 → 119.619 | 1.892x |

These are measured **bridge improvements**, not a measured full-model
before/after speedup. Both full-model backends above already use batching.
Even the improved FPGA bridge remains slower than the improved CPU bridge.

## Residency, memory and initialization

PYNQ-Z1: ARMv7 Cortex-A9 (650-MHz clock observed in the compatibility inventory),
95-MHz accepted M3 fabric, Linux 6.6.10-xilinx-v2024.1, Python 3.10.4, NumPy
1.21.5, PYNQ 3.1.1. `OPENBLAS_NUM_THREADS=1`; process snapshots show one thread.
Native GCC 11.2.0 flags are `-O3 -Wall -Wextra -Werror -shared -fPIC
-mcpu=cortex-a9 -mfpu=neon` (SFPU also links `-lm`). CPU identification is
`ARMv7 NEON int8 widening multiply/int32 accumulate, N16 tiled`. Both use
the same exact integer contract; this is not a benchmark against FP32 GPT-2,
an optimized language-model serving framework, or the fastest possible ARM
implementation. Governor sysfs was unavailable; no fixed-governor assertion
or board-global tuning is made.

The board reports 503,464 KiB total RAM and 399,628 KiB available before this
benchmark; CMA total/free were 131,072/42,336 KiB then. Availability is a snapshot,
not reserved capacity. Pack payload is 205,271,824 bytes of readonly ordinary
DDR mappings, cache allocation 48,365,568 bytes, DMA allocation 110,592 bytes,
and cached-prefix snapshot 614,016 bytes. Payload sizes are not additive RSS
measurements: file-backed pages and cache capacity may not all be touched.

Benchmark process peak RSS was **218,364 KiB (213.246 MiB)**. Last fixed CPU/FPGA
PSS snapshots were 194,090/194,098 KiB; last generation CPU/FPGA snapshots were
203,902/210,070 KiB. Final PSS was 195,678 KiB after temporary-output lifetimes
ended. **PSS values are snapshots, not sampled peak PSS.** Peak RSS is cumulative
for the shared process and cannot be assigned separately to each backend.
Every recorded model-process swap measurement is zero; existing system-wide
swap usage is unrelated and is not claimed zero. Separate short-context
correctness processes peak at 156,912 KiB CPU and 202,800 KiB FPGA, but their
validation lifetimes differ and they are not isolated benchmark peaks.
The separate **physical CPU 1024-context correctness run** now passes: peak RSS
219,244 KiB (214.105 MiB), final PSS snapshot 212,339 KiB, one thread and zero
process swap, with the same 48,365,568-byte cache and no CPU CMA allocation.
These include diagnostic-validation lifetimes, not an isolated benchmark peak
or long-context throughput result. Evidence is `build/m4_runtime_cpu_boundary.json`,
SHA-256 `1cd038f0608517adaa2932e959900ca3359af3373d5d6e9311f0dc73a1a2f0c9`.
The separate **physical FPGA 1024-context correctness run** also passes: peak
RSS **261,840 KiB (255.703 MiB)**, final PSS snapshot **254,587 KiB**, one thread
and zero process swap. It uses the same cache plus 110,592 CMA bytes. Final
full-vocabulary logits and every layer's KV match the independent reference;
overflow rejection leaves cache/length unchanged and DMA cleanup completes.
Evidence is `build/m4_runtime_fpga_boundary.json`, SHA-256
`1f9a858cec49de78e1b934c18e6c227ace74a773f885f0fb0be2639cee0c8423`.
Its diagnostic elapsed time includes validation; it is not a long-context
performance measurement or a substitute for the repeated resident benchmark.

Initialization component observations inside the benchmark process:

| Component | Seconds |
|---|---:|
| Bundle integrity scan | 16.841667 |
| CPU backend/model runtime initialization | 11.738711 |
| Overlay programming/DMA initialization | 10.947374 |
| Preparation of CPU prefix snapshot used by fixed cached-decode trials | 36.416221 |

These are n=1 components, not cold distributions or complete process-start
latencies. Model download and offline packing happen before deployment and
are excluded, not claimed free. The scan warms OS page cache. A separate
process-start observation is reported below.

## Evidence identity

The completed board report is `build/m4_benchmark_board.json`, SHA-256
`b839f78c9ac2010c04d97c254e52656d83faca4196311ca9231914a0db271dd0`.
Its status is `BENCHMARK_SELECTED_PHASES_EXACT_PASS`, phase `all`.
`build/m4_performance_analysis.json` SHA-256 is
`d77d21ead5de368aec60a1086fbec0fc675ec4579537fcf7101f66e5561a1741`.
The complete sample inventory, source identity, exact results, CPU/FPGA work
parity and disjoint profile sums pass the reproducible analyzer's checks.

Frozen sampling policy SHA-256:
`17bcd0a823f551c539525fc54c0f51e759a306f9c346e968de06523b8380d8cf`.
Benchmark runner SHA-256:
`e859c94a443d7e238b2fa88d11ad0b2d2315469d239497f2d044b744571a90ed`.
Analyzer SHA-256:
`a0f6b187dcc763610048b4987d06d59c3f903d1761fa7943418f9c3d2eb59cf0`.
Board bundle manifest SHA-256:
`e711e00ecac9cb7756b116fe8b41517224b2286afad8d13e9b13ad61c3a91cfa`.
The bundle retains the exact accepted model/fixtures, ARM library identities,
and unchanged M3 qual3 bit/HWH. Full source/model/overlay pins and physical
correctness evidence are in `M4_VERIFICATION.md` and the raw bundle manifest.

## Reproducible analysis and instrumentation costs

`scripts/summarize_m4_performance.py` refuses partial/failed runs and changed
policy/runtime identities, audits the complete raw sample inventory, and emits
statistics directly from those observations. Use a fresh output path:

```bash
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m scripts.summarize_m4_performance --input build/m4_benchmark_board.json --output build/m4_performance_analysis.recheck.json
```

It reports both the ratio of CPU/FPGA median latencies and paired trial ratios;
values below one mean the FPGA is slower. Throughput distributions are computed
from each observation, not by relabelling a latency percentile. Full-generation
latency has **three chain observations**; the 57 cached step observations are
nested within those chains at successive contexts 14–32 and are not independent
repeated chain samples. Raw warmups and all chain totals remain available.

The benchmark shares one model pack/runtime/cache and switches backends.
FPGA libraries and the small CMA allocation remain resident during CPU samples
too; separate CPU-only and FPGA correctness runs provide additional memory
measurements. Full generation retains 20 returned float64 logit arrays
(8,041,120 payload bytes) for validation after the clock stops. Their reference
checks are outside timing, but list/timestamp/profiling overhead is included
for both backends, and retained output memory is included in process RSS/PSS.
The cached-prefix snapshot is also explicitly counted. These costs must not
be hidden or attributed to model weights alone.

### Supplemental process-cold boundary

The main runner's initialization-component timers begin inside Python; they
are not complete interpreter-launch-to-first-token measurements. The separate
`tests/m4/cold_start_policy.json` freezes one descriptive fresh-process
observation per backend, after the benchmark/context sequence finishes.
It includes interpreter/module/library startup, integrity/loading, FPGA setup
where applicable, the same complete story prefill, greedy selection and local
pipe delivery. Validation occurs afterward and remains mandatory.

This has n=1 per backend: no cold median/p95, variability or speedup claim will
be inferred. Assets already exist on the board and OS caches are untouched;
the boundary is **process-cold, not disk-cold, board boot or model download**.
It supplements, rather than changes, the frozen repeated resident benchmark.

`zynq/m4_cold_start.py` implements that boundary with a fresh child interpreter.
The parent acknowledges receipt only **after** recording the delivery time;
the child waits for this acknowledgement before reference checking. Parent
and child therefore cannot accidentally overlap validation with the startup
measurement. The probe checks that the existing main benchmark and both
physical context-result files have completed successfully before launching a
child, uses bounded observation/graceful abort, and never force-kills a
potential DMA owner. Its four host protocol/lifecycle tests pass.

Both physical fresh-process observations are **terminal PASS**, including exact
first-token, full-logit and all-KV validation after timed delivery, successful
DMA cleanup and child exit code zero. The same 13-token story prompt delivers
token ID 257. CPU ran first, then FPGA, exactly as frozen before timing.

| Backend | Launch → first token, s (n=1) | Whole child process incl. checks/cleanup, s | Peak RSS, KiB | Final PSS snapshot, KiB |
|---|---:|---:|---:|---:|
| Native A9 CPU | 55.673811 | 55.992047 | 152,720 | 144,836 |
| FPGA offload | 99.185217 | 100.405617 | 199,764 | 191,896 |

Both model-process snapshots show one thread and zero swap. Each allocates
48,365,568 cache bytes; only FPGA allocates 110,592 CMA bytes. These short-prompt
startup peaks do not replace the full-context memory measurements above.
Full-process completion is deliberately a different clock from first-token
delivery. No n=1 CPU/FPGA startup speedup ratio or latency distribution is claimed.

The probe ran from `/home/xilinx/pocketai_m4_startup.yMtIVx`, without modifying
the accepted data/runtime bundle. `build/m4_process_cold.json` SHA-256 is
`b784fe3174406237203e35eb11f6e8676ccc89ddb91d6d3799cb2ad1c12f4e91`;
its terminal board log is `build/m4_process_cold_board.log`, SHA-256
`7b09cff746e04d87d86a3e000838f821c7daa78e307039e9d88e545ad73101a8`.
The final evidence audit verifies the frozen policy, helper/current runtime,
model/overlay identities, sampling, result checks, memory and clean child exits.

For a new reproduction, after the board sequence has terminated, copy the standalone helper
and frozen policy into a fresh owned probe directory, preserving the accepted
bundle and old outputs. Under the normal login-shell/PYNQ environment, run:

```bash
OPENBLAS_NUM_THREADS=1 sudo -E /usr/local/share/pynq-venv/bin/python3 /path/to/fresh-probe/m4_cold_start.py --stage /home/xilinx/pocketai_m4_bench.lkETvP --policy /path/to/fresh-probe/cold_start_policy.json --output /path/to/fresh-probe/process_cold.json
```

Use interactive sudo; no password belongs in a command or file. The helper
and policy are supplemental evidence, not replacements for the frozen runtime.
The startup endpoint includes a local pipe receipt, while resident timing ends
at a Python token list. Do not subtract these observations to invent an exact
startup overhead or mix the n=1 observations into the n=20 resident statistics.
