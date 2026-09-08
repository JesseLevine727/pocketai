# Closed pre-M6 goal: cold startup and prompt-inclusive throughput

All required gates below pass; see [results](M5_STARTUP_RESULTS.md) and the
read-only chained startup audit. The <=5-second initialization stretch is not
met, and the measured short-request margin is only 3.1 ms. The requirements and
experiment bounds below are retained unchanged.

Baseline: pushed `1fa4a82`. M6 and its report remain unstarted. Preserve the
complete W8A8/int16 GPT-2, both fast-multiply Ibex harts, all existing closure
audits and unrelated `NA/`. Prefer exact firmware improvements on the same
qualified 91-MHz DSP0 overlay. No hidden preparation or host inference.

## Gates

- Original science/computing prompts with one generated token: <=10 seconds
  START through safe ownership return and token copy, each of three plain runs.
- Original story prompt with two generated tokens: <=20 seconds, each of three
  plain runs. Count only output tokens in throughput, not prompt tokens.
- Independently measure cold derived initialization. Initial engineering gates:
  <=10 seconds pure initialization and <=20 seconds cold delivered forward for
  both past-1022 prefixes; prefer <=5 seconds initialization / <=15 seconds total.
  The old ~45-second figure includes a complete forward, not just preparation.
  If materialization becomes demand-driven, initialization accounting includes
  complete preparation **and first-demand materialization**, while every later
  demand is charged to its actual forward. Never hide work by deferring it.
- Preserve <=10-second warm maximum-context delivery for three genuine cold/warm
  pairs per prefix, reaching 1024 valid K/V positions without future-state reuse.
- Exact tokens, every final logit, complete valid KV, original story traces,
  native threaded/multirow/layout/arithmetic tests, overflow non-mutation/recovery,
  byte-identical rebuild and normal zero-owner/pages/PTE cleanup.

The short-request metric includes actual prompt prefill and first-use numerical
preparation. Model provisioning, firmware loading and checking remain separately
reported. No repeated-prompt memoization, lower precision, context truncation or
relocation of numerical work outside START. Trace-enabled regression need not
meet the untraced performance gate, but must preserve original tensor correctness.

## Bounded sequence

1. Add separate diagnostic counters for cold key transpose, V maximum scanning,
   units and V quantization/layout. Profile one actual short prefill through all
   layers to separate projection, attention, normalization and smoothing costs.
2. Optimize the measured cold bottleneck with exact packed/contiguous access,
   existing two-hart parallel work and/or existing accelerator operations.
3. Optimize multirow prefill's measured costs, avoiding repeated metadata and
   conversions while preserving every rounding and per-row scaling boundary.
4. Recheck both objectives together, including unchanged warm maximum-context
   speed, then freeze final plain repetitions and independent exactness checks.

Each physical campaign is capped at 60 minutes including staging, queueing,
checks and cleanup, with a 120-second cleanup reserve and finite case bounds.
Use short hypothesis-driven cases, not full-1024 physical prefill, exhaustive
endurance or multi-hour individual tests. Preserve failures and misses. Never
force-unload or free undrained pages. All work uses new `m5_startup` paths; frozen
`m5_context` files/artifacts stay untouched. No agents or tracker scaffolding.

Deliver engineering results, machine evidence, a read-only chained audit and
scoped commits. Do not push or begin M6 without the corresponding user request.
