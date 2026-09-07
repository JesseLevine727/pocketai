# M5 scalar preparation — results

Status: **CLOSED / PASS**. The four candidate diagnostics, final matched decode
samples, native tests, original full-request physical qualification, safe release
and binary reproduction pass. Baseline is pushed `1825659`; this is a bounded acceleration of the same
FPGA-led GPT-2, not M6 or an ARM implementation.

## Matched cached decode

| Qualified boundary | Previous | Scalar release | Throughput gain |
|---|---:|---:|---:|
| Model + greedy selection | 15.681728 s | 12.211767 s | 1.2841× |
| Resident START → safe return + token copy | 16.735890 s | 13.266107 s | 1.2616× |

The release achieves **0.07538 delivered token/s** and **0.08189 model-only
token/s**. Latency falls 20.73% delivered / 22.13% model-only. Neither figure
includes model provisioning or independent result checking. No new preparation
was moved outside the measured model interval. The ~1.05-s request overhead is
per request, not necessarily per generated token in a longer request.

Three unprofiled measured model samples: 12.211751308, 12.211825352,
12.211724516 s. Delivered: 13.264102947, 13.267801267, 13.266417843 s.
Model median/min/max: 12.211751308 / 12.211724516 / 12.211825352;
population deviation 0.000042646 s. Delivered median/min/max:
13.266417843 / 13.264102947 / 13.267801267; population deviation 0.001525712 s.
All samples, including the separate diagnostic and warmup, remain in evidence.
No claim about distribution tails, sustained generation or long-context speed.

Every sample restores the independent original past-13 seed and input 257,
then checks token 582, all 50,257 logits and complete valid-14 KV exactly.
The final separate profile takes 12.240062 s; its 0.028295-s difference from
the measured mean is reported, not subtracted. Fine-counter binaries have
different layouts and are diagnostic only, never mixed into primary statistics.

## Four measured candidates — all retained incrementally

| Candidate | Unprofiled diagnostic model time | Change |
|---|---:|---|
| Arithmetic | 14.667002 s | uint32 quantizer division; inlined exact RNE24/saturation |
| Lookup | 14.447761 s | lazy exact maximum-indexed multiplier/unit table |
| Metadata/locality | 13.108852 s | exact norm power-of-two operations, prefill reuse, smoothing rounding, contiguous V scan/direct packing |
| Affine | 12.211151 s | 32-bit bounded affine rounding; prepare common scale once |

These pairs are diagnostic adopt/reject evidence, not three-sample throughput
claims for each intermediate version. The final three-sample means above are
the primary performance result. All four keep the same 9,701 backend jobs and
134,861,772 / 1,981,892 mover input/output bytes.

The compiler initially reconstructed REMU from quotient/multiply/subtraction.
A zero-instruction RV32 value barrier preserves one DIVU followed by fast MUL
and subtraction. The corrected `arithmetic_v2` is the measured candidate;
`arithmetic_v1` was a compile inspection, not an omitted board measurement.

### Exact table ownership and setup

The table is lazy, not a preloaded model sidecar. Each forward chunk allocates
32,769 uint32 multipliers and binary64 units in its existing DDR workspace,
clears validity multipliers, computes misses using original unit arithmetic,
and invalidates pointers before workspace rewind on both success and failure.
Every clear, miss and lookup is inside model time. There is no warm cache
carried between requests, model versions or chunks, and no A9 tensor work.

Zero retains multiplier 0 / unit 1.0. Out-of-domain maxima and small workspaces
use arithmetic; Q15 probability units preserve the exact power-of-two relation.
The implementation is hart-0-only, not a shared/reentrant parallel tensor cache.
Payload is 393,228 bytes; allocator/alignment cost is **393,344 bytes**.
Seeded high-water rises 1,632,708 → **2,026,052 bytes**; native maximum rises
1,909,188 → **2,302,532 bytes**, within the unchanged workspace/arena.

### Arithmetic and memory changes

- Quantization keeps the entire multiply result, exactly one ties-to-even
  rounding and original saturation, including the signed endpoint.
- LayerNorm retains ordered scaling operations and original special-value
  fallback; shifts are not combined across possible overflow/underflow.
  Consecutive exponent-zero prefill rows reuse call-local gain/bias preparation;
  a nonzero exponent forces recalculation. No model-lifetime norm cache.
- V maxima are recomputed over the valid history, now in contiguous order.
  Values are quantized directly into GEMM tiles; changing a maximum never
  leaves stale previously quantized V. Legacy scratch reservations retain
  existing allocation/error boundaries.
- Affine conversion exploits its actual output domain below 2^31, preserving
  the original fallback and partial outputs for invalid scales. Uniform
  residual alignment and norm restoration prepare one multiplier, retaining
  backend chunking, integer bias, RNE, errors and workspace boundaries.

## Remaining first-principles bottleneck

The final profile has **10.862112 s outside backend service (88.74%)**, versus
14.338103 s previously: **24.24% less CPU/control/scalar-memory remainder**.
This is not a measurement of floating-point time alone. Service is 1.377951 s;
nested GEMM compute is 0.087228 s and SFPU compute 0.291977 s. Never add these
nested engine intervals to service.

| Non-overlapping phase | Total (s) | Outside backend service (s) |
|---|---:|---:|
| Full vocabulary head | 3.505035 | 3.127186 |
| Smoothed MLP-down/residual | 2.335484 | 2.036912 |
| MLP-up | 1.728893 | 1.443832 |
| QKV | 1.299013 | 1.083078 |
| Attention | 1.298056 | 1.261698 |
| Smoothed attention projection/residual | 1.204205 | 1.107245 |
| All LayerNorm | 0.691122 | 0.629091 |

The intermediate fine profile justified the later choices: after lookup,
norm metadata alone cost 1.567653 s; after metadata specialization it cost
0.555341 s. At that point affine metadata still cost 1.267120 s outside the
head plus 0.398646 s in the head, motivating the last candidate. Those fine
values describe their own intermediate binaries, not the final release.

Future priorities are the head's ordered channel/range preparation and remaining
smoothing reciprocals, then explicitly owned model-invariant preparation or
a measured fused preparation/packing operation. More MAC lanes do not remove
these loops. The current work does not prove a hardware limit or a global
optimum. Even eliminating 90% of today's remainder while leaving service fixed
would leave ~2.46 s model time; one token/s remains an unmet stretch target.

## Correctness and reproduction

Both final and fresh runtime/profile/fine binaries reproduce byte-for-byte.
The complete native suite preserves 396 tensors / 4,670,788 values, all 50,257
logits, 60 generated tokens and existing arena/error checks. Focused tests cover:

- 42,772 divider and 655,370 full-domain fixed-shift quantization cases.
- 642,240 signed variable-shift and 393,024 binary64 affine-rounding cases.
- 524,368 table-unit comparisons, fallback, bounds and poisoned invalidation.
- 1,683 norm cases (524 failures preserving partial outputs), 1,715 affine
  differential cases and 31,666 original integer comparisons.
- 1,188 uniform-affine plane/chunk/error/workspace comparisons and 15 complete
  attention/cache comparisons through valid1024. The latter is a subsecond
  native operator test, not a 1024-token full-model campaign.

Unchanged hardware: both pipelined RV32MFast harts, 91 MHz, setup +0.263 ns,
hold +0.018 ns, TNS/THS0, DSP0. No RTL, clock relaxation, slow multiply, FPU,
W4/W4A4, WFI, ARM model helper, pruning or new synthesis. Prior audits pass.

Source tests reproduce the generated C, reject an altered parent, verify the
actual one-DIVU/MUL implementation and keep setup inside the timed forward.
The initial parent-rejection test expected the wrong exception class; corrected
to the existing pin check's RuntimeError. Both the failed harness log and its
passing rerun remain; no production change or failed board run was concealed.

```text
runtime bdc5505830ba1bfd9b6397a077542978a0316014104906de8ae19d5e4ea38779
profile 65c2a77bbd2aaa6acfdc5c87f5d5c3a9664181a0dfe3dfbfb3843c688d7a704b
fine    10986bdc51ac04c8a21c3ef68dab1a893d071437f1cfb891efe0edd3b87e05e2
```

## Original full-request physical qualification

| Request | Exact generated IDs | Model total (s) | START → delivery (s) | Previous delivery (s) |
|---|---|---:|---:|---:|
| Story: 13 prompt / 2 new | 257, 582 | 97.628130 | 98.681533 | 143.485204 |
| Science: 8 prompt / 1 new | 5004 | 54.160666 | 55.217658 | 78.863607 |
| Computing: 8 prompt / 1 new | 22712 | 54.197254 | 55.256506 | 78.873650 |

These are single original full-request observations, not three-run means.
Story prefill is 85.347615 s; model first-token time is 85.420199 s (not streamed
delivered TTFT), and its additional decode is 12.207927 s. Call-scoped prefill
reuse helps these requests more than the one-row seeded decode. All final
logits/KV and selected prefill traces match the independent frozen references.

Overflow rejects without changing cache/output sentinels, followed by successful
accepted requests. Full arena allocation remains 266,289,152 bytes. Provisioning
is separately 20.175679 s. The complete campaign including independent checks
took **258.817787 s (~4 min 19 s)**, under the cleanup-safe 1200-s watchdog.
No hours-long sweep or full-model 1024 endurance run was needed.

Ownership returned safely; mappings/file closed. A read-only reopen confirms
**owner=0, allocated_pages=0, pte_dma=0**, followed by normal helper unload.
No force unload, tensor access under wrong ownership or undrained page release.
The [machine evidence](m5_scalar_evidence.json) and negative audit tests retain
all samples and enforce exact outputs, nested clocks, hardware/source identity,
new workspace cost, original full requests, reproduction and cleanup.

## Reproduce

```bash
M5_SCALAR_BUILD=build/m5_scalar_fresh M5_SCALAR_VARIANT=affine bash scripts/build_m5_scalar.sh
python3 -m unittest discover -s tests/m5_scalar -v
python3 -m scripts.audit_m5_scalar
```

Use a fresh build directory. Generated artifacts remain local; committed
evidence identifies source/artifact hashes and raw reports. The read-only audit
reuses earlier closure gates without programming the board. The unchanged
three-cycle policy is imported only as the seeded measurement/full-request
protocol; this pass's four-candidate scope is [M5_SCALAR_PLAN](M5_SCALAR_PLAN.md).
The arithmetic/lookup/metadata variants preserve intermediate experiments;
`affine` is the release. LTO sweeps, persistent smoothing/model preparation and
new RTL are deferred, not silently claimed completed. No push was requested
for this goal.
