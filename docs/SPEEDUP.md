# M4 performance — sampling frozen, results pending

No full-model speedup or token-rate result is claimed yet. M3's 5.793 kernel
GMAC/s and 0.085 synthetic-chain end-to-end GMAC/s describe different boundaries;
neither predicts GPT-2 performance. Diagnostic M4 correctness times include
validation and are not benchmarks.

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
mean, standard deviation, physical transfer bytes, peak RSS/PSS/swap and the
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

Results, source/board/tool hashes, raw evidence paths and limitations will be
added only after physical measurements and validation complete.

## Reproducible analysis and instrumentation costs

`scripts/summarize_m4_performance.py` refuses partial/failed runs and changed
policy/runtime identities, audits the complete raw sample inventory, and emits
statistics directly from those observations. Use a fresh output path:

```bash
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m scripts.summarize_m4_performance --input build/m4_benchmark_board.json --output build/m4_performance_analysis.json
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
observation per backend, after the active benchmark/context sequence finishes.
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

After the existing board sequence has terminated, copy the standalone helper
and frozen policy into a fresh owned probe directory, preserving the active
bundle and old outputs. Under the normal login-shell/PYNQ environment, run:

```bash
OPENBLAS_NUM_THREADS=1 sudo -E /usr/local/share/pynq-venv/bin/python3 /path/to/fresh-probe/m4_cold_start.py --stage /home/xilinx/pocketai_m4_bench.lkETvP --policy /path/to/fresh-probe/cold_start_policy.json --output /path/to/fresh-probe/process_cold.json
```

Use interactive sudo; no password belongs in a command or file. The helper
and policy are supplemental evidence, not replacements for the frozen runtime.
The startup endpoint includes a local pipe receipt, while resident timing ends
at a Python token list. Do not subtract these observations to invent an exact
startup overhead or mix the n=1 observations into the n=20 resident statistics.
