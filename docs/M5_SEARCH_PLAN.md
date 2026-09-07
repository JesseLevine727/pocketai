# M5 — another bounded first-principles search

Status: **CLOSED / PASS**. Baseline: pushed `9238ffbb9f41e82c79871df7aa6910b3b88958a3`.

Three measured configurations completed: reject LTO; retain fused projection
preparation and exact integer/binary64 scaling. Final repeated decode,
original full 2/1/1 requests, clean reproduction and normal DMA release pass.
See [results](M5_SEARCH_RESULTS.md), [reviews](M5_SEARCH_REVIEWS.md) and
[machine evidence](m5_search_evidence.json). No fourth cycle or M6 started.

Three actual optimize/test/measure/reassess cycles, maximum four measured
implementation configurations total (correctness corrections excepted):

1. Strict-math LTO: exploit compiler visibility and remove unused code without
   changing numerical policy or the two-hart protocol.
2. Fuse remaining projection preparation, retaining global range/exponent
   decisions and exact intermediate operations.
3. Specialize accumulator scaling or the largest surviving justified scalar
   cost, using the preceding measurements to decide.

Keep the fastest useful exact combination, not every attempted change. Each
cycle closes with a measured retain/reject decision and a first-principles
review. The compiler cycle may legitimately reject LTO. No claim that three
cycles establish a global optimum or the board's performance limit.

Preserve the same autonomous FPGA-led GPT-2 W8A8/int16 model, full 50,257 logits,
12 layers/heads, 1024 KV capacity, A9 provisioning-only role, both pipelined
RV32MFast harts and exact qualified 91-MHz DSP0 overlay. No precision, clock,
timing-margin, FPU/DSP, slow-multiply, WFI or scheduler changes; no M6/new RTL.
One token/s remains stretch. Keep all setup honestly timed, workspace bounds,
cache lifetime/invalidation, operation ordering and descriptor ownership.

Reuse the qualified past-13 seed: input257 → token582, valid14, complete logits
and KV exact in each short diagnostic. Run affected native regressions and the
existing model suite. Final release: diagnostic, warmup + three unprofiled
observations, separate model and resident START-through-delivery statistics,
byte-identical clean firmware reproduction, and one original full 2/1/1 board
campaign with traces/error recovery, safe ownership return, zero retained DMA
resources and normal helper unload. Use the existing cleanup-safe 1200-s
campaign watchdog. No hours-long parameter sweeps or full-model1024 endurance.

Preserve prior source/artifact/evidence hashes through isolated derivation;
leave `NA/` alone. No agents, tracker scaffolding or stored credentials. The
requested initial push covers9238ffb only; finish new work in a scoped local
commit, with results, three reviews, auditable evidence and negative checks.
