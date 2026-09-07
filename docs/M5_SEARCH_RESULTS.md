# M5 — three more bounded performance cycles

Status: **CLOSED / PASS**. Baseline **9238ffb was pushed
to origin/main** before this pass. This remains the same autonomous FPGA-led
GPT-2; no M6, new hardware or precision variant was started.

## Matched cached decode

| Boundary | Previous release | Retained combination | Throughput gain |
|---|---:|---:|---:|
| Model + greedy selection | 12.211767 s | 11.043111 s | 1.1058× |
| Resident START → safe return + token copy | 13.266107 s | 12.102234 s | 1.0962× |

The primary user-facing result is **0.08263 delivered token/s** for this
resident, single-token request; model-only is **0.09055 token/s**. Delivered
latency falls **8.77%**, model latency **9.57%**. Neither boundary includes
provisioning or independent reference checking. Required preparation and lazy
table setup remain inside model time; there is no persisted warm model cache.
The ~1.059-s difference is per request, not necessarily per generated token
within a longer request. These are fixed-context observations, not sustained
generation, tail latency or long-context speed claims.

| Three unprofiled samples | Model (s) | START → delivery (s) |
|---|---:|---:|
| 1 | 11.043142066 | 12.103699249 |
| 2 | 11.043068681 | 12.096971427 |
| 3 | 11.043121648 | 12.106031237 |
| Median | 11.043121648 | 12.103699249 |
| Minimum | 11.043068681 | 12.096971427 |
| Maximum | 11.043142066 | 12.106031237 |
| Population deviation | 0.000030926 | 0.003841034 |

The separate diagnostic and warmup are also retained. Each observation restores
the independent original past-13 seed, accepts input257, and checks token582,
all 50,257 logits and complete valid-14 KV exactly. The separate final profile
takes 11.071559 s: its 0.028449-s overhead relative to the measured mean is
reported, not subtracted. Profile-enabled and fine-counter runs are not mixed
into the primary unprofiled statistics.

## Three cycles and decisions

| Measured configuration | Diagnostic model (s) | Decision |
|---|---:|---|
| Strict-math LTO | 12.228432 | Reject: no demonstrated speed benefit |
| Fused projection preparation, non-LTO | 11.771209 | Retain |
| Fusion + exact integer/binary64 scaling | 11.045137 | Retain; final release |

There were three measured configurations, not a flag sweep. Intermediate
diagnostics are adopt/reject evidence, not three-sample performance estimates.
Fusion_v1 was compiled with LTO but never board measured; fusion_v2 reflects
cycle 1's decision to retain original compiler settings. LTO shrank runtime
text from 34,624 to 31,548 bytes without a speed gain. The final runtime uses
36,200 bytes text / 128 data / 128 BSS, within existing local-memory bounds.

The [three first-principles reviews](M5_SEARCH_REVIEWS.md) describe the renewed
assessment after each actual implementation and measurement. The zoom-out
review guided selection from model phases down to scalar preparation loops;
compiler visibility, materialized intermediate planes and operand-specific
arithmetic were tested separately. No global-optimum claim follows from this
bounded search.

### Retained implementation

Projection keeps its global range/exponent reduction, but normal channel
scales now directly produce the exact final integer multiplier/bias planes.
This avoids writing and rereading final scaled-double planes. Exceptional or
invalid inputs fall back to the original affine implementation before backend
calls or output changes. Workspace reservations, error/partial-output behavior,
3,072-element backend chunking and the full-vocabulary head remain unchanged.

Range multiplication exploits the exact int32 operand: two full 32×32 products
cover the entire significand product, followed by one binary64 nearest/even
rounding. RV32 emits two MUL and two MULHU instructions on the already-qualified
fast multipliers. Signed endpoints, zero, rounding carry and overflow are
handled; subnormal/zero/Inf/NaN scales use the original arithmetic. The same
primitive serves smoothing's int16 overflow-range scan. Nonzero bias additions,
residual ordering, global exponents and model precision do not change.

The old per-forward lazy quantizer cache is unchanged: its setup/misses remain
timed and its pointers are invalidated before rewind. Seeded workspace remains
**2,026,052 bytes**, native maximum **2,302,532 bytes** and complete arena
**266,289,152 bytes**. There is no new model-lifetime sidecar or ARM tensor work.

## Bottleneck after this pass

The final profile has **9.693540 s outside backend service (87.55%)**, down
10.76% from the prior 10.862112 s. This includes scalar instructions, memory
stalls and control; it is not a direct floating-point-time measurement.
Backend service remains 1.378019 s. Nested engine times are GEMM 0.087228 s
and SFPU 0.291977 s; do not add these to service.

Cycle 3's diagnostic identifies head (2.747785 s total / 2.369885 s outside
service), smoothed down (2.196247 / 1.897677), up (1.651361 / 1.366329),
attention (1.298488 / 1.262125) and QKV (1.242372 / 1.026485) as the surviving
large phases. The head total is about 21.6% below the prior release's profile.
Those per-phase numbers come from the candidate diagnostic, not a subtraction
from unprofiled timings.

Next hypotheses: dependency-aware preparation reuse, fewer scalar reads and
integer-plane construction passes, and attention-loop specialization. A larger
prepared-metadata format or exact scalar hardware helper could be considered
in a separate pass with its setup, storage and timing explicitly qualified.
More MAC lanes or W4A4 alone do not remove these loops. Even eliminating all
current backend service would yield only about 1.14× if the remainder stayed
fixed; that is an Amdahl estimate, not a limit on a redesigned system.
One token/s remains an unmet stretch target.

## Correctness and reproducibility

Both fresh builds pass the complete native model suite: 396 tensors /
4,670,788 values, all 50,257 logits, 60 generated tokens, 78 operator cases /
7,779,561 words and existing arena/error checks. Focused checks include
**1,033,040 bitwise integer/binary64 products** over all exponent classes,
signed endpoints and special values; **2,916 fused-plane/fallback/error/workspace
comparisons**; and all prior quantizer, cache, norm, affine and uniform tests.
The 15-case attention regression includes valid1024 as a native operator test,
not a full-model endurance campaign. Source tests reject an altered parent,
reproduce generated C and verify native full-width multiply instructions.

Runtime, primary profile and diagnostic fine-profile firmware reproduce
byte-for-byte from a fresh directory. Timed entry points, hardware controller,
cache lifecycle, numerics and requantization sources match the prior release.
Both pipelined RV32MFast harts and the exact **91-MHz DSP0 overlay** remain:
setup **+0.263 ns**, hold **+0.018 ns**, TNS/THS0. No synthesis, timing relaxation,
slow multiplier, FPU, WFI timing change, pruning or W4/W4A4.

```text
runtime c849f05ea992e53c32f8c4f589bbda47ca800e2d4033fb5e3e113bd79e59ace5
profile 98162e9b52868a526ea95c2da30d1f38f0f039adbfa0bea22d391eea1d0c4d0d
fine    64a854b1dd5fd541068180a27efcbd83e2515942e6bea57c11bf141330eb856b
```

## Full-request qualification

| Original request | Exact generated IDs | Model (s) | START → delivery (s) | Previous delivery (s) |
|---|---|---:|---:|---:|
| Story: 13 prompt / 2 new | 257, 582 | 90.269574 | 91.325472 | 98.681533 |
| Science: 8 prompt / 1 new | 5004 | 50.030060 | 51.088366 | 55.217658 |
| Computing: 8 prompt / 1 new | 22712 | 50.066835 | 51.120905 | 55.256506 |

These are individual full-request observations, not repeated-run averages.
Story prefill is 79.157765 s; model first-token time is 79.230284 s, followed
by an 11.039286-s decode. This is not streamed delivered TTFT. Every final
logit and valid KV word, plus selected story prefill traces, matches the frozen
independent references. Overflow rejects without changing cache/output
sentinels, then the original accepted requests prove recovery.

The complete campaign, including reference checking, took **241.913982 s
(~4 min 2 s)** under the cleanup-safe 1200-s watchdog. Provisioning is reported
separately at 19.436173 s. No hours-long sweep or full-model1024 endurance run.
All original arena and per-request workspace/transport sizes are unchanged.

After safe ownership return and mapping/file closure, a read-only reopen
confirms **owner=0, allocated_pages=0, pte_dma=0**. Normal helper unload passes;
no force unload or release of undrained DMA pages. The [machine evidence](m5_search_evidence.json)
retains every diagnostic, warmup, measured sample and complete request.

## Reproduce and audit

```bash
M5_SEARCH_BUILD=build/m5_search_fresh M5_SEARCH_VARIANT=product bash scripts/build_m5_search.sh
python3 -m unittest discover -s tests/m5_search -v
python3 -m scripts.audit_m5_search
```

Use a fresh directory; `product` is the retained fusion+product combination.
`lto` and `fusion` preserve the measured alternatives. Binary/generated build
artifacts stay local; committed evidence preserves identities and raw reports.
The unchanged older policy is imported only as a measurement and full-request
protocol; [M5_SEARCH_PLAN](M5_SEARCH_PLAN.md) defines this pass's three-cycle
scope. Prior source/artifact/evidence hashes remain immutable and earlier
audits pass. The new audit checks exact outputs, timing boundaries, decisions,
hardware/source identity, binary reproduction and DMA cleanup, with negative
tests for corrupted evidence. New work ends in a local commit; only the prior
9238ffb release was requested for the initial push.
