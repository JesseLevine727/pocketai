# M5 — three bounded cycles: results

Status: **CLOSED / PASS** — three cycles, exact physical qualification,
byte-identical firmware reproduction and read-only evidence audit.
This follows pushed `bf4ec02`; it is not M6. See the
[three first-principles reviews](M5_ITERATE_REVIEWS.md) and
[bounded contract](M5_ITERATE_PLAN.md). All previous audited sources/evidence
remain unchanged.

## What survived the three cycles

1. **Retained:** reuse attention score affine metadata and its common integer
   bias; search LayerNorm's scaling factor at the largest absolute gain while
   retaining original nonfinite fallback and output arithmetic.
2. **Investigated, not deployed:** WFI waiting. Both-core wakeup tests pass,
   but hart-0 WFI stops its `mcycle`, invalidating elapsed-time measurement.
   The profiler rejected that board diagnostic. A directed simulation
   reproduces the undercount; hart-0 polling restores correct timing. Sleeping
   only hart 1 is exact but saves only 0.065% in a single diagnostic pair, too
   little evidence of material benefit. Both candidate sources/reports remain.
3. **Retained:** exact projection range reduction using binary64 magnitude
   encodings, actual signed-zero bias checks and exact residual power-of-two
   scaling. All ordered nontrivial products/additions, NaN/infinity handling,
   full-vocabulary range dependencies, rounding and final logits are preserved.

No persistent cache or hidden setup was introduced. No new RTL or FPGA build,
precision change, head pruning, CPU tensor helper, frequency relaxation or slow
multiply fallback. Both harts retain pipelined RV32MFast (9/12 execute cycles).

## Matched cached decode — the fair short-request number

**0.05975 delivered token/s**, or **16.735890 s per resident seeded request**.
This includes START through safe ownership return and token copy, not just the
accelerator. Model-only is 15.681728 s / 0.06377 token/s. Provisioning and
independent result checking are outside this delivery boundary; no mandatory
preparation was moved there. About 1.05 s of request overhead is paid per
request, not automatically per token in a longer generation.

| Qualified version | Model mean (s) | START → delivery mean (s) | Delivered token/s |
|---|---:|---:|---:|
| Previous fast-controller closure | 17.400193 | 18.458464 | 0.054176 |
| Three-cycle release | 15.681728 | 16.735890 | 0.059752 |

**1.1096× model throughput / 1.1029× delivered throughput**; latency reductions
9.88% / 9.33%. These are matched fixed-context results, not a claim about cold
start, empty-cache prefill, sustained generation, tail latency or 1024-context
speed. >=1 token/s remains an unmet stretch target.

Every run restores the independent original past-13 cache and input 257;
token 582, all 50,257 logits and the complete valid-14 KV match exactly.
No samples were discarded. Primary results use three unprofiled observations
after one warmup; the separate diagnostic is not averaged into throughput.

| Final role | Model (s) | START → delivery (s) |
|---|---:|---:|
| Profiled diagnostic | 15.713365 | 17.029487 |
| Unprofiled warmup | 15.681728 | 16.766276 |
| Unprofiled measured 1 | 15.681776 | 16.733726 |
| Unprofiled measured 2 | 15.681703 | 16.736572 |
| Unprofiled measured 3 | 15.681704 | 16.737370 |

Model median 15.681704 s, min/max 15.681703 / 15.681776, population deviation
0.0000342 s. Delivered median 16.736572 s, min/max 16.733726 / 16.737370,
population deviation 0.0015641 s. Three observations describe this short test;
they do not establish a distribution tail. Model instrumentation difference
is 0.031637 s; no overhead correction is subtracted from any measurement.
The diagnostic's larger host-side interval is retained as observed.

## Remaining bottleneck and next priorities

The final production-style diagnostic takes 15.713365 s: **14.338103 s (91.25%)
outside backend service**, 1.375262 s within it. This remainder includes scalar
arithmetic, instruction fetches, scalar memory and stalls; it is not a direct
measurement of floating-point time alone. GEMM compute 0.087228 s and SFPU
compute 0.291977 s are nested inside service, not additive to it.

| Non-overlapping phase | Total (s) | Outside service (s) |
|---|---:|---:|
| Full vocabulary head | 3.665179 | 3.288183 |
| Smoothed MLP-down/residual | 2.773718 | 2.475330 |
| Attention | 2.741467 | 2.705582 |
| MLP-up | 1.850197 | 1.565728 |
| Smoothed attention projection/residual | 1.432765 | 1.335959 |
| QKV | 1.389524 | 1.174023 |
| All LayerNorm | 1.699635 | 1.637604 |

Next priorities, **not started**: instrument the surviving preparation within
head/attention/smoothing; test further exact integer specialization or
call-scoped prefill metadata reuse; then consider model-lifetime preparation
with explicit memory ownership, version/invalidation and startup accounting.
New MAC lanes and W4A4 do not eliminate this measured scalar remainder.
The idle-polling experiment did not demonstrate a dominant contention problem.
Even a 10× reduction of the remainder alone would leave ~2.81 s model time,
so reaching one token/s eventually also requires lower backend/mover cost.

## Preserved hardware and verification scope

Exact reused overlay: **91 MHz, setup WNS +0.263 ns, TNS 0, hold +0.018 ns,
THS 0, DSP 0**. Original routed/DRC/methodology qualifications and reviewed
warnings remain in [M5_FAST_RESULTS](M5_FAST_RESULTS.md). The +0.250-ns hard
setup gate is unchanged; +0.500 ns is still stretch. No rerouting was needed.
29,003 LUTs, 21,724 registers, 95.5 BRAM36 and 72.22% occupied slices.

Full GPT-2 W8A8/int16, 12 layers/heads, 1024 KV capacity and A9 provisioning-only
role remain. Arena: 266,289,152 allocated bytes; native maximum workspace
1,909,188 bytes; seeded decode high-water 1,632,708 bytes. The 9,701 jobs and
134,861,772 / 1,981,892 mover input/output bytes are unchanged. These are traffic
counts, not claims of saturated DDR bandwidth.

Retained firmware and fresh reproduction pass the complete native suite:
396 tensors / 4,670,788 traced values, all 50,257 logits, 60 generated tokens,
86 forward tokens, 78 operator cases / 7,779,561 words, and existing arena/error
tests. Targeted additions cover 1,683 norm cases (524 failures with partial
output equivalence), 576 attention plane/output/error/workspace cases and
38,640 bitwise range comparisons. Both runtime and profile binaries reproduce
byte-for-byte. The initial WFI simulation launch had missing unused LUT-table
warnings; a fresh correctly staged launch passes without those warnings.
That configuration correction and the failed board clock diagnostic are
retained, not relabelled as final success.

Final firmware:

```text
runtime 62547bcec54cf70d486ace6eb5723b2fba48ec27cbcfa294fb7dbcc955c90051
profile 9e7831aa497567927c6a2703147c95863837320e451fb387ad03ceed3a26585e
bit     6c647a3dc2f0305b9add96d6a8240be2ada9c6d91ac526feb8376a124551c9bc
hwh     e05c696a5b196cf8e9a3c564108286679b1afb9cc989945bcc71bdbb0342f514
```

## Original full-request physical qualification

Final original **2/1/1** requests pass on the exact reused overlay and new
release runtime. Every token, all final logits, full valid KV and the five
selected story-prefill traces match the independent frozen references.
The overflow case rejects without changing cache/output sentinels, followed
by successful accepted requests. These are single bounded observations, not
three-run means or a substitute for the matched cached-decode benchmark.

| Original request | Generated IDs | Model total (s) | START → delivery (s) |
|---|---|---:|---:|
| Story, 13 prompt tokens / 2 new | 257, 582 | 142.426157 | 143.485204 |
| Science, 8 / 1 | 5004 | 77.811525 | 78.863607 |
| Computing, 8 / 1 | 22712 | 77.817775 | 78.873650 |

For comparison, previous qualified delivered intervals were 161.298975,
88.908668 and 88.902496 s respectively. Empty-cache prefill still dominates
these short generation requests. Story's additional model decode takes
15.686312 s. Provisioning is separately **20.038053 s**; the complete campaign,
including independent checks, took **350.777746 s (~5 min 51 s)** under the
cleanup-safe 1,200-second watchdog. No long-context endurance campaign or
hours-long sweep was run.

Ownership was safely returned and mappings/file closed. A read-only reopen
confirmed **owner=0, allocated_pages=0, pte_dma=0**. The helper then unloaded
normally; no force unload, unowned tensor access or undrained memory release.
All prior M5/optimization/fast-controller audits and negative tests still pass.

The [machine evidence](m5_iterate_evidence.json) includes original raw reports,
all diagnostic and measured samples, rejected-candidate identity, statistics,
source/artifact hashes and closure gates. The closure test suite also rejects
changed exact outputs, missing samples, gated-clock accounting, altered
hardware/policy, missing source pins, incomplete requests and retained DMA
resources. These checks validate the gates, not merely a PASS label.

## Reproduce or inspect without repeating long experiments

```bash
M5_ITER_BUILD=build/m5_iterate_fresh M5_ITER_VARIANT=cycle3 bash scripts/build_m5_iterate.sh
python3 -m unittest discover -s tests/m5_iterate
python3 -m scripts.audit_m5_iterate
```

Use a fresh build path. `cycle1`, `cycle2` and `cycle2_hart1` preserve diagnostic
derivations; **only `cycle3` is the release**. The read-only audit neither
programs the board nor rebuilds hardware. Generated artifacts stay local under
`build/`; committed evidence records their identities. Historical README/PLAN
and earlier reports are hash-audited snapshots; use `STATUS.md` for the current
entry point. No fourth cycle, M6 or push is part of this goal.
