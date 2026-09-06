# M5 optimization — bounded, exact software pass

Status: **CLOSED — QUALIFIED**, 2026-09-06 UTC. Original M5 closure remains valid and unchanged; this is
an isolated optimization, not M6. See [scope and acceptance](M5_OPTIMIZATION_PLAN.md).

The matched cached-token request improves from **40.228 to 25.704 seconds including
safe return and delivery: 1.565x throughput** (0.02486 to 0.03890 token/s).
Inside that request, the firmware model loop improves from **39.174 to 24.648
seconds: 1.589x** (0.02553 to 0.04057 token/s). These are different, explicitly
measured boundaries; neither is accelerator-only performance. >=1 token/s
remains an unmet stretch target.

## Matched fixed-context measurements

One instrumented diagnostic, one retained unprofiled warmup and three measured
unprofiled requests per variant. No sample excluded after observation.

| Variant | Three measured model times (s) | Mean model (s) | Mean START-through-delivery (s) |
|---|---|---:|---:|
| Original numerical sources | 39.174450, 39.174277, 39.174583 | 39.174437 | 40.228231 |
| Exact power-of-two integer rounding | 37.383218, 37.383178, 37.384279 | 37.383558 | 38.441516 |
| Plus affine metadata scan/arithmetic | 26.866023, 26.871189, 26.869236 | 26.868816 | 27.924374 |
| Plus smoothing preparation reuse, retained | 24.648318, 24.647880, 24.647831 | 24.648010 | 25.704113 |

Final model median is 24.647880 s, min/max 24.647831/24.648318 s and population
standard deviation 0.000219 s. Final delivered-request median is 25.703968 s,
min/max 25.702986/25.705385 s and population standard deviation 0.000985 s.
The instrumented-versus-unprofiled model overhead is 24.5–27.8 ms across
variants (26.8 ms final). It is retained in the diagnostic, not subtracted from
the unprofiled measurements. n=3 is descriptive, not a tail-latency guarantee.
Firmware reload, seed restoration and independent checks are outside these
resident request intervals; the measured host boundary includes mandatory
firmware startup, safe ownership return and token delivery, about 1.05 s beyond
the firmware model interval. The original historical M5 decode used growing
contexts, so this new matched baseline is the denominator for the speedup.

## Complete resident requests — final physical gate passed

| Prompt | Input / generated count | Generated IDs | START through delivery (s) | Output tok/s | First token ready in DDR (s) |
|---|---:|---|---:|---:|---:|
| story | 13 / 2 | 257, 582 | 228.384305 | 0.008757 | 202.679957 |
| science | 8 / 1 | 5004 | 126.698833 | 0.007893 | 125.637927 |
| computing | 8 / 1 | 22712 | 126.707358 | 0.007892 | 125.648244 |

All final complete logits and valid int16 KV match the original frozen
reference. Story's five selected prefill traces also match exactly. Its
unseeded cached continuation takes 24.648418 seconds, consistent with the
separate fixed-context samples. Firmware model-loop times are 227.328378,
125.637932 and 125.648249 seconds respectively. Forward-only prefill takes
202.607410, 125.565386 and 125.577249 seconds.

The primary complete-request boundary includes empty-cache prefill, all
required numerical/preparation/transfer work, safe ownership return and output
copy; independent checking is excluded. Tokens are delivered together after
DONE, so first-token-ready-in-DDR is **not interactive host TTFT**. The original
story closure generated five tokens, this lean pass two: do not compare their
output-token rates as a matched speedup. Use the fixed-context comparison above.

The final process finishes successfully under its 20-minute total watchdog;
the measured complete requests sum to 481.790 seconds (about eight minutes).
Provisioning is separately measured at 20.483 seconds. All 266,289,152 bytes /
65,012 owned pages remain allocated during inference, preserving full
1024-position cache capacity. The maximum workspace is unchanged at 1,909,188
bytes. Peak process RSS is 325,736 KiB (includes mapped arena pages; do not add
the arena again). Global free swap changed from 423,676 KiB after provisioning
to 420,348 KiB after cleanup; process VmSwap was not sampled, so no swap-free
claim is made.

The bounded invalid request preserves all four cache-region hashes and the
output sentinel, then all three accepted requests demonstrate recovery.
Close/reopen verifies zero allocated pages, zero owner and zero page-table DMA
address. Normal module unload passes. No cache dropping, CMA resizing, boot
change, endurance run or timing relaxation was needed.

## What the physical profile established

The independently seeded story decode uses past=13, input token 257, output
582 and cache-valid=14. Each sample restores the same cache and firmware before
timing. Every observed result must match all 50,257 logits and complete valid
int16 K/V against the frozen independent M4 runtime, not a new self-reference.
These measurements are cached decode, not empty-cache prefill or endurance.

Baseline unprofiled model time is 39.174 seconds. Its diagnostic model interval
is 39.202 seconds: 37.881 seconds outside backend service and 1.321 seconds of
inclusive backend service. Inside that service, GEMM consumes 0.087 seconds and
SFPU 0.238 seconds. The remaining approximately 0.995 seconds includes transfer,
submission and waiting; it is not an independently measured pure DMA interval.
The diagnostic has 9,652 jobs, 134,600,652 mover input bytes and 1,720,772 output
bytes. Scalar CPU DDR traffic is not in these mover counters.

The 37.881-second remainder includes arithmetic, memory stalls and bookkeeping,
not pure compute. Short controlled probes distinguish the causes:

| Probe | Original | Optimized / local alternative |
|---|---:|---:|
| 32,768 scalar reads, identical loop | DDR 22.069 ms | SRAM 8.651 ms |
| 8,192 exact RNE divisions by 2^24 | 110.545 ms | Shift/mask 50.635 ms |
| 4,096 affine metadata values, SRAM | 344.393 ms | Exact metadata 26.408 ms |
| Same affine metadata, DDR | 356.618 ms | Exact metadata 33.089 ms |

All paired checksums agree. These synthetic probes are not full-model speedups.
Loop overhead remains included. Moving the original metadata probe to SRAM
saved only 3.4%, while changing its redundant arithmetic saved 90.7% in DDR.
This is evidence for doing the exact software work first, not evidence that a
cache could never help other accesses.

## Six-point disposition

1. **Profile — passed.** Exclusive stage intervals, nested service/engine
   accounting, 64-bit totals and an enabled/disabled profiling comparison.
   Diagnostic records stay in existing on-chip SRAM until model timing ends;
   their publication remains inside the separately reported host request.
2. **Software preparation — native and matched cached board checks passed.**
   Replace power-of-two integer division with exact shift/mask/ties-to-even.
   Determine affine common shift from one maximum scan instead of repeated
   whole-array scans; derive rounded power-of-two-scaled binary64 values from
   their representation without software floating multiplication. Reuse each
   smoothing reciprocal across rows and reuse already prepared multipliers
   when exponent zero permits it. Preserve exceptional fallback behavior,
   rounding, saturation, biases and the original model pack.
3. **Additional BRAM locality/cache — deferred for this lean pass.** The actual
   local-vs-DDR probes above show a real scalar-memory penalty, but much smaller
   benefit than eliminating original metadata arithmetic. Existing spare 44.5
   BRAM tiles are not a coherent accelerator cache: current DMA accepts only
   the protected DDR arena. An implementation needs a genuinely accessible
   buffer/cache, invalidation or bypass rules for accelerator writes, ownership
   and reset tests, and a new routed overlay. No unqualified local pointer was
   passed to DDR-only DMA. Next experiment: after software closure, count the
   remaining hot scalar accesses and simulate a bounded read-only metadata
   line buffer, with explicit full-model benefit before an RTL build.
4. **Larger jobs / overlap / fusion — deferred beyond preparation reuse.** At
   baseline even eliminating *all* backend service would improve total latency
   only about 3.5%; eliminating its non-engine portion would save about 2.5%.
   Actual overlap can recover less and needs asynchronous ownership, dependency
   and error/drain handling. A GEMM job includes weights and activations; W4
   cannot halve all service work. Standalone GELU is only 81 ms across all
   layers, including preparation and service, so fusing it is not the current
   priority. Next experiment: once firmware cost falls further, pipeline one
   projection with retained activation input and two explicitly owned slots;
   qualify exact wide results and cancellation before system integration.
   In the retained candidate, inclusive backend service is still 1.322 seconds
   inside 24.675 profiled seconds. Even its impossible complete elimination
   caps speedup at 1.057x; the attainable queue/transfer improvement is smaller.
5. **Arithmetic — exact firmware optimization implemented, hardware deferred.**
   The accepted zero-DSP, RV32IMC/no-FPU hardware stays unchanged. Integer RNE
   fast paths and bit-exact affine metadata remove expensive arithmetic rather
   than adding idle MACs. GEMM/SFPU together were under 1% of baseline model time.
   A portable faster Ibex multiply could still accelerate remaining software
   floating-point helpers, but requires a newly timed overlay and ISA/board
   qualification. Next experiment: profile the remaining scalar helpers after
   this pass, then test one fast-multiply candidate if its end-to-end value
   warrants that separate hardware cycle. No ASIC-portability concession.
6. **W4A8 — small candidate rejected; W4A4 deferred.** One predeclared symmetric
   per-output-channel W4 quantizer, no sweep or retuning, ran against independent
   floating GPT-2 and accepted W8A8 on 128 teacher-forced validation predictions.
   The complete screen took 11.43 seconds on the host, not hours. Results below
   reject this simple candidate; they do not rule out groupwise or other W4
   methods. W4A4 adds activation error risk before either quality or the present
   bottleneck justifies it. Next low-bit experiment, if later needed: one
   separately versioned groupwise W4A8 candidate with exact group accumulation
   and scale-cost accounting, not a claimed free nibble substitution.

| Development screen, 128 predictions | W8A8 | Simple W4A8 | Frozen limit |
|---|---:|---:|---:|
| Perplexity / independent float perplexity | 0.9859 | 38.3755 | <=1.10 |
| Float top-1 agreement | 88.28% | 14.84% | >=85% |
| Float top-1 inside quantized top-5 | 100% | 33.59% | >=97% |
| Mean forward KL (nats) | 0.0231 | 3.7812 | <=0.05 |
| Unintended clipping | 0 | 0 | 0 |

This is a development screen, not a new held-out benchmark or production model
qualification. The signed-nibble pack/unpack roundtrip matched every weight.
Logical matrix payload is 61,766,016 packed bytes; preserving the existing
16-column tile padding would require 61,771,776 bytes. Embeddings/positions,
metadata, int16 KV and derived caches remain separate: halving GEMM weights
saves about 30.1% of the 205,271,824-byte model payload, not half the arena.
No packed-weight hardware or physical W4 performance is claimed. Ibex unpacking
and new scale handling have nonzero costs and were not hidden in a speedup.

## Qualification

Every software candidate so far passes the original native numerical foundation:
396 full-model traces / 4,670,788 values, 60 generated tokens, complete logits
and KV checks, arithmetic and operation edge cases. Additional differential
tests cover 31,666 integer results and 1,139 affine arrays, including exceptional
inputs and partial-output/error semantics. These native tests complete within
the 120-second watchdog; no physical 60-token rerun is required.

A final supplemental test adds adjacent binary64 values around common-shift
and ties-to-even boundaries, for 1,715 affine arrays total, also passing.
Two fresh optimized firmware builds produce the identical 65,536-byte image
SHA-256 `6a004e8585f972d8d565e0c393dcbe1f58b0f05291fcaadc1f45aa5a2c33eb35`.
The unprofiled runtime contains 33,616 text bytes, 128 data bytes and 112 BSS
bytes, with the original linker reservations and stacks. No new FPGA BRAM,
LUT, DSP or clock resource is consumed.

## Remaining bottleneck

After these improvements the profiled model still spends **23.353 of 24.675
seconds outside backend service (94.6%)**. The full-vocabulary head alone has
6.540 seconds of that scalar remainder. Across layers, smoothed MLP down plus
residual contributes 3.744 seconds, MLP up 3.098 seconds and attention 2.847
seconds. These remain inclusive of scalar memory stalls, not per-helper CPU
instruction profiles. The next substantial performance project is still
exact scalar preparation/arithmetic and its locality, not additional MAC rows.

## Reproduction

Run from the repository root with the existing pinned dependencies, M4 model,
fixtures and toolchains. Build outputs and board reports must use fresh names.

```bash
# Fast native regression plus source-pinned optimized firmware.
M5_OPT_RUNTIME_BUILD=build/m5_opt_runtime_new bash scripts/build_m5_opt_runtime.sh

# Independent fixed-context seed; preserves the original model and fixtures.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 \
  build/m4_venv/bin/python -m scripts.export_m5_opt_seed --output build/m5_opt_seed_new

# Variants: baseline, exact (integer shift), metadata, reuse (retained).
M5_OPT_VARIANT=reuse M5_OPT_PROFILE_BUILD=build/m5_opt_profile_new \
  bash scripts/build_m5_opt_profile.sh

# One fixed small quality screen, not a sweep.
OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 timeout 600 \
  build/m4_venv/bin/python -m tests.m5_opt.evaluate_precision \
  --output build/m5_opt_precision_new.json

# Read-only evidence checks; no board access or allocation.
python3 -m scripts.audit_m5_opt
build/m4_venv/bin/python -m unittest tests.m5_opt.test_profile \
  tests.m5_opt.test_precision tests.m5_opt.test_evidence
```

For board reproduction, stage the exact accepted M5 `.bit/.hwh`, original
`model.bin/layout.json`, unchanged `zynq/m5_run.py`, new profiling runner,
`m5_profile.bin`, `seed/` and `opt_policy.json` (the performance policy). Run
`m5_opt_profile.py --stage ... --output fresh.json` in the normal root PYNQ
environment with the original DMA helper loaded. For complete requests, use
the optimized `m5_runtime.bin`, original selected `fixtures/`, unchanged
`m5_run.py`, and `complete_policy.json` staged as `performance_policy.json`.
The complete runner is invoked with `timeout -s INT 1200 ... --timeout 600`;
its interrupt/error path returns ownership and closes mappings. Never program
an overlay or unload the helper while an owned request is active. After normal
completion, `m5_opt_release_check.py` verifies zero retained pages/ownership,
then unload the helper normally. SSH is used; no JTAG or stored credentials.

The original M5 read-only source/timing audit and new optimization audit pass.
The latter pins all new sources and original report artifacts, reconciles
timing/counters, checks independent references, sample coverage, retained
speedups, complete requests, precision rejection, reproducibility and cleanup.
Mutation tests reject altered evidence. Full reports and source/artifact pins
are in [machine evidence](m5_opt_evidence.json); build products remain local.

Hardware is the original exact qualified 91-MHz overlay, SHA-256
`b25c6058b00783df611761f0cc1edf15b6c8d666cc86011c03e051c4b24dc813`:
WNS +0.584 ns, TNS 0, hold +0.045 ns, 28,442 LUT, 21,688 registers,
95.5 BRAM tiles, zero DSPs and reviewed DRC/methodology warnings. This is reuse
of a qualified build, not a new FPGA implementation result. M1–M5 source and
artifact identities, including their audited historical README/PLAN/performance
documents, remain unchanged. No push without a request; M6 is not started.
