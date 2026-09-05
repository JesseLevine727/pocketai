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
