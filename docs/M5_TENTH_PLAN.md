# M5 — bounded pursuit of 0.1 delivered token/s

Status: **CLOSED / PASS — target achieved on the matched cached decode**.
Baseline: qualified local `10d9d22`.

Three measured candidates retained. Final mean is **9.958322 s delivered /
0.10041853 token/s**; all three measured observations are below 10 seconds.
Margin is narrow (41.68 ms); no sustained/tail/long-context guarantee. Exact
native and original full-request board checks, clean firmware reproduction,
zero-resource DMA reopen and normal unload pass. See [results](M5_TENTH_RESULTS.md)
and [machine evidence](m5_tenth_evidence.json). No fourth candidate or M6 started.

Target: mean resident START → safe ownership return and token copy <=10.000 s,
i.e. >=0.100 delivered token/s, using the original independent past13 decode.
Baseline is 12.102234 s delivered / 11.043111 s model. Report the best qualified
result and honest remaining gap if the bounded search falls short.

Up to four measured implementation configurations plus one justified correction
or combination; one optional fine diagnostic. Prioritize exact scalar rounding,
projection preparation and dependency-aware arithmetic/loop simplification.
The ~1.06-s request overhead includes full noncoherent DMA ownership transfers,
not a one-second polling sleep: userspace polls at 10 ms. Do not remove required
cache synchronization, drain or ownership operations to reach the number.

Preserve exact full W8A8/int16 GPT-2, all 50,257 logits, 12 layers/heads,
1024 KV capacity, both pipelined RV32MFast harts and qualified 91-MHz DSP0
overlay (+0.263-ns setup, +0.018-ns hold, TNS/THS0). No new RTL/synthesis,
precision change, slow multiplier, FPU, WFI undercount or ARM tensor work.
All preparation remains charged; no hidden cross-request cache. Keep timing
boundaries, model ordering, workspace/error semantics and safe DMA lifecycle.

Each retained change gets exact native boundary/operator/full-model tests and
a short all-logit/KV board diagnostic. Final retained combination: diagnostic,
warmup+three unprofiled samples, separate model/delivered statistics, a fresh
byte-identical firmware build and one original full 2/1/1 physical campaign
with traces, overflow rejection/recovery and normal zero-resource DMA release.
Use the cleanup-safe 1200-s campaign watchdog. No full-model1024 endurance,
large sweeps or hours-long tests. Reuse unchanged evidence and frozen runners.

Isolated derivation preserves all old sources/artifacts/audits. Leave `NA/`
alone. No agents, tracker setup, stored credentials or new push. Close with
results, candidate decisions, evidence/negative audit tests and scoped local
commit. One token/s stays stretch; this pass specifically targets 0.1.
