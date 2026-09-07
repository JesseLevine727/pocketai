# M5 — pursuit of 0.1 delivered token/s

Status: **CLOSED / PASS — 0.1-token/s target achieved on the matched cached decode**.
Baseline: qualified local `10d9d22` (11.043111 s model / 12.102234 s delivered).

## Primary matched cached-decode result

**0.10041853 delivered token/s**, mean **9.958321549 s** resident START through
safe ownership return and token copy. All three observations are below 10 s.
This meets the goal on the original past13/input257 single-token benchmark,
but with only **41.68 ms / 0.42% margin**. It is not a sustained, tail-latency,
long-context or prompt-prefill-inclusive guarantee. Provisioning and independent
reference checking remain outside this named boundary, exactly as before.

| Matched boundary | Previous | New mean | Throughput gain |
|---|---:|---:|---:|
| Model + greedy selection | 11.043111 s | 8.896736 s | 1.2413× |
| Resident START → safe return + token copy | 12.102234 s | 9.958322 s | 1.2153× |

Delivered latency falls **17.72%**, model latency **19.44%**. Model-only rate
is **0.11240077 token/s**; it is not substituted for delivered performance.
The ~1.0616-s request overhead is retained and is per request, not necessarily
per generated token in a multi-token request. No preparation was excluded.

| Three unprofiled samples | Model (s) | START → delivery (s) |
|---|---:|---:|
| 1 | 8.896719923 | 9.957809136 |
| 2 | 8.896756341 | 9.959404130 |
| 3 | 8.896732319 | 9.957751380 |
| Median | 8.896732319 | 9.957809136 |
| Minimum | 8.896719923 | 9.957751380 |
| Maximum | 8.896756341 | 9.959404130 |
| Population deviation | 0.000015118 | 0.000765864 |

The diagnostic and warmup are also retained; every observation checks token,
all 50,257 logits and complete valid-14 KV exactly against the independent
frozen reference. The final separate profile is 8.924170 s; its 0.027434-s
overhead relative to the measured mean is reported, not subtracted. Final
profile remainder is 7.548849 s outside 1.375321 s backend service: **84.59%**
of model time, and **22.12% less remainder** than the previous release.

## Implemented candidates and first-principles decisions

| Incremental candidate | Diagnostic model (s) | START → delivery (s) | Decision |
|---|---:|---:|---|
| Exact signed rounding / signed-zero scaling | 10.310100 | 11.370750 | Retain |
| Prepared full-width channel multiplication | 9.011370 | 10.070974 | Retain |
| Certified exact smoothing reciprocal | 8.895653 | 9.956963 | Retain; qualify |

Three configurations were measured, all with exact token582, all 50,257 logits
and complete valid-14 KV from the independent past13/input257 seed. No fourth
configuration or fine-counter run was needed once the diagnostic crossed 0.1.
The diagnostic comparisons are not repeated-run throughput estimates.

The zoom-out review traced phase costs down to repeated scalar arithmetic.
The improvement is not more MACs or different quantization: it is less work
to construct the same accelerator inputs and global range decisions.

1. **Signed rounding:** decode the binary64 sign/exponent directly and reuse
   bounded integer ties-to-even conversion when the input magnitude is below
   2^31. Larger values and specials retain the original full int64 ABI.
   Positive finite power-of-two factors preserve signed zero directly, avoiding
   a generic double multiply for the head's many zero biases. This also reduces
   LayerNorm preparation. No changed rounding, saturation or special result.
2. **Channel multiplication:** prepare the row-constant quantization unit's
   sign/exponent/significand once. Four full native 32×32 products preserve all
   106 significant product bits, followed by exactly one binary64 ties-to-even
   rounding. Specials and underflow/overflow edges use the original multiply.
   Actual RV32 code has four MUL and four MULHU instructions, on the existing
   fast harts. No float32 conversion or smaller multiplier result is used.
3. **Reciprocal:** smoothing uses 1/x. A uint32 division seeds two integer
   Newton steps, but the estimate is never itself accepted as the answer.
   Full-width product/remainder checks establish the exact integer quotient,
   with bounded correction followed by exact ties-to-even rounding. Failed
   certification, special inputs and range edges use the original division.
   This is an exact reciprocal algorithm, not approximate reciprocal math.

Prepared row factors are local and set up inside the model interval. Reciprocal
work also stays inside each smoothing call. The existing lazy quantizer cache
and its per-forward invalidation are unchanged; there is no persisted table or
untimed model sidecar. Global exponent reductions, ordered bias/residual math,
all vocabulary entries, chunking and workspace/error behavior remain intact.

The initial round_v1 source-generation attempt stopped because the reused
extractor only recognized `int` functions, not `int64_t`/`static double`.
The isolated extractor was corrected; round_v2 is the actual built/measured
candidate. No failed firmware or board comparison was omitted.

## Correctness and unchanged architecture

Focused native checks pass: **321,205 signed binary64/int64 rounding cases**,
**984,736 full binary64 products**, and **298,048 exact reciprocals**, including
all real 65,280 smoothing values. They cover signs, zero, all exponent classes,
rounding boundaries, special values and fallback. Another 990 generated
power-of-two comparisons cover signed-zero/range/special cases. The complete
native model suite checks 396 tensors / 4,670,788 values, all logits, 60 generated tokens,
78 operator cases / 7,779,561 words and existing arena/error behavior. Original
quantizer, cache, norm, affine, uniform and attention regressions pass.
The valid1024 attention test is a short native operator test, not endurance.

Preserve both pipelined RV32MFast harts, exact W8A8/int16 GPT-2, 12 layers/heads,
1024 KV capacity and the same 91-MHz DSP0 overlay (+0.263-ns setup, +0.018-ns
hold, TNS/THS0). No RTL, synthesis, FPU, slow multiply, WFI clock shortcut,
pruning, W4/W4A4 or ARM model arithmetic. Seeded workspace remains 2,026,052
bytes; native maximum is 2,302,532 bytes, within the unchanged 266,289,152-byte
full arena. Runtime text/data/BSS is 37,868 / 128 / 128 bytes.

The request-control review found 10-ms polling, not a removable one-second
sleep. The ~1.06-s delivered-minus-model interval includes noncoherent DMA
ownership/cache synchronization over the full mapped arena. Those operations,
drain checks, errors and the actual START-through-token-copy boundary were
left unchanged. Driver, host runners and their policy hashes remain frozen.

## Remaining bottleneck

The third candidate's diagnostic has 7.547614 s outside backend service out of
8.923183 s total. That remainder includes scalar instructions, memory stalls
and control, not just floating-point arithmetic. Backend service is 1.375569 s;
GEMM 0.087228 s and SFPU 0.291977 s are nested within it, not additive latency.

| Non-overlapping diagnostic phase | Total (s) | Outside service (s) |
|---|---:|---:|
| Smoothed MLP-down/residual | 2.000211 | 1.701809 |
| Full vocabulary head | 1.925848 | 1.548841 |
| Attention | 1.287680 | 1.251513 |
| MLP-up | 1.190773 | 0.906297 |
| Smoothed attention projection/residual | 0.936524 | 0.839714 |
| QKV | 0.897318 | 0.681833 |

The head is no longer the largest phase. A later bounded pass could examine
smoothing's remaining metadata/range passes, attention's scalar loops, or
dependency-aware reduction of projection scans. These are unmeasured future
hypotheses, not a promise of another speedup or a demonstrated architectural
limit. Hardware redesign and persistent metadata would need separate timing,
memory/ownership and setup accounting. One token/s remains an unmet stretch.

## Final qualification and reproduction

Runtime, primary profile and diagnostic fine-profile firmware reproduce
byte-for-byte in a fresh build, with the complete native suite passing again.
Timed entry points, hardware controller, quantizer-cache lifecycle and
requantization sources remain byte-identical to the prior release. Only the
documented scalar math/source derivation changes. All earlier audits pass.

```text
runtime 40f93fd566fbbd0d59e6e1cea3c13ccf2e98785da37376be3cae52188590fb17
profile 1e3a48c4cabb0e0505e9e4a62835ffeb905c1d52bd6fbf838adebe42f7014097
fine    c32359a232e9835c62b56c721241be15276d445576ae47fef71c3103200f2d1d
```

The original short full 2/1/1 board campaign passes:

| Request | Exact generated IDs | Model (s) | START → delivery (s) | Prior delivery (s) |
|---|---|---:|---:|---:|
| Story: 13 prompt / 2 new | 257, 582 | 73.168156 | 74.220165 | 91.325472 |
| Science: 8 prompt / 1 new | 5004 | 40.377804 | 41.431210 | 51.088366 |
| Computing: 8 prompt / 1 new | 22712 | 40.401908 | 41.459565 | 51.120905 |

These are single complete-request observations and include prompt processing,
so their token rates differ from the cached-decode target above. Story prefill
is 64.203404 s, model first-token time 64.275951 s, and its additional decode
8.892202 s. This is not streamed delivered TTFT. All final logits/KV and selected
story prefill traces match the independent frozen reference. Overflow rejects
without cache/output mutation; subsequent accepted requests prove recovery.
Arena, per-request workspace and transport counts remain unchanged.

Provisioning is separately 19.344580 s. The complete campaign including checks
took **205.841828 s (~3 min 26 s)**, below its cleanup-safe 1200-s watchdog.
No hours-long sweep or full-model1024 endurance run was needed. Ownership
returns safely and mappings/file close; read-only reopen confirms
**owner=0, allocated_pages=0, pte_dma=0**, then the helper unloads normally.

The [machine evidence](m5_tenth_evidence.json) retains all diagnostic, warmup,
measured and full-request reports. The read-only audit enforces identical
outputs, source/hardware identities, timing/accounting, unchanged workspace,
binary reproduction, the actual delivered target and safe cleanup. Negative
tests reject corrupted results, changed boundaries, missing samples, leaked
resources and even internally consistent statistics that miss the target.

```bash
M5_TENTH_BUILD=build/m5_tenth_fresh M5_TENTH_VARIANT=reciprocal bash scripts/build_m5_tenth.sh
python3 -m unittest discover -s tests/m5_tenth -v
python3 -m scripts.audit_m5_tenth
```

Use a fresh directory. `reciprocal` includes all three retained changes;
`round`/`factor` reproduce intermediate implementations. Build artifacts remain
local; committed evidence records generated-source/binary identities and raw
reports. The old policy is reused as the fixed measurement/full-request
protocol, not as this pass's objective; [M5_TENTH_PLAN](M5_TENTH_PLAN.md) defines
the target and bounded scope. Prior audits and hash-pinned evidence are
preserved. No new push or M6 is included in this goal.
