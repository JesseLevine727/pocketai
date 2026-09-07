# M5 fast-controller results

Status: **CLOSED / PASS** — fast hardware, exact faster firmware, complete
physical qualification, read-only evidence audit and negative evidence tests.
This is the bounded follow-up to `c40d7cd`, not M6. Original M1–M5 and M5
optimization evidence remains unchanged and separately auditable.

## What changed

Both actual Ibex harts use an isolated pipelined **RV32MFast** implementation.
It is not RV32MSlow and not stock fast's 3/4-cycle unit: the timing-corrected
kernel takes **9 execute cycles for MUL and 12 for high-half MUL**, plus
external stalls. Signed/unsigned instruction semantics and iterative division
are preserved. There are no DSP blocks or F/D ISA instructions.

Exact software improvements reuse rounded projection scales between passes,
replace eligible binary64 power-of-two multiplication with exact exponent
adjustment, bypass the redundant exponent-zero LayerNorm correction, and
use the existing SFPU REQUANT8 for project activation quantization. Offload
measurements include max scan, expansion, transfers, packing and unit/scale
calculation. Normal-to-normal exponent scaling has the original arithmetic
fallback for subnormal/zero/special/boundary cases.
The prior smoothing zero-bias specialization is retained and regression-tested;
this pass adds no arbitrary bias-dropping rule. Zero/signed-zero power-of-two
cases are explicitly covered by bitwise tests.

Full GPT-2 remains W8A8/int16, 12 layers and heads, all 50,257 logits and
1024-capacity KV. No bias, epsilon, tie, rounding or saturation relaxation.
A9 provisions and observes; tensor work stays autonomous on Ibex/accelerators.
No new persistent cache, model format, tensor worker or precision sweep.

## Matched cached-decode performance

Every observation starts with the same independent past-13 cache, input 257,
output 582 and valid cache 14. Full logits and valid KV match the original
independent reference on every run. One separate diagnostic, one warmup and
three unprofiled measurements per fast configuration; no discarded samples.
The slow baseline is imported from its original qualification, not remeasured
or relabelled. Fast-only uses its **byte-identical retained firmware**.

| Configuration | Model mean (s) | Resident START → delivery mean (s) | Delivered token/s |
|---|---:|---:|---:|
| Previous qualified slow | 24.648010 | 25.704113 | 0.038904 |
| Fast harts, identical firmware | 24.076211 | 25.192142 | 0.039695 |
| Fast + exact preparation | 17.763754 | 18.820462 | 0.053134 |
| **Fast + preparation + REQUANT8** | **17.400193** | **18.458464** | **0.054176** |

Final versus previous: **1.4165× model throughput, 1.3925× delivered throughput**
(29.40%/28.19% lower latency respectively). Fast-only model gain is just
1.02375×; the larger gain is software. Routing also changes between overlays;
this is an implementation-level hardware ablation, not instruction latency
in isolation. Matched helper probes show some unchanged or slightly slower
operations, so do not claim universally faster multiplication-heavy helpers.

The fairest interactive cached-token number is **0.05418 delivered token/s**,
about 18.46 seconds per independently restarted seeded request. Model-only is
0.05747 token/s. Neither is cold start, empty-cache prefill, long-context speed
or a guaranteed sustained multi-token rate. The roughly 1.06-second final
request overhead is paid once per request, not automatically once per token.
>=1 token/s remains an unmet stretch target.

All measured samples (seconds), in order:

| Configuration | Model samples | START → delivery samples |
|---|---|---|
| Slow | 24.648318, 24.647880, 24.647831 | 25.703968, 25.705385, 25.702986 |
| Fast-only | 24.075795, 24.077085, 24.075755 | 25.156970, 25.282949, 25.136506 |
| Preparation | 17.761446, 17.768249, 17.761567 | 18.819279, 18.825290, 18.816816 |
| Final | 17.400123, 17.400205, 17.400251 | 18.459941, 18.455618, 18.459832 |

Machine evidence retains full precision, mean/median/min/max/population
deviation and aggregate rates. Final medians are 17.400205 / 18.459832 seconds;
population deviations are 0.0000527 / 0.0020126 seconds. Three observations
are descriptive only, not tail-latency or endurance evidence.

## Where time still goes

Final production-style diagnostic: 17.428641 seconds model, **16.051092 seconds
CPU/scalar-memory remainder (92.10%)**, 1.377548 seconds backend service.
GEMM 0.087228 and SFPU 0.291977 seconds are **inside service**, not additive.
9,701 jobs transfer 134,861,772 input and 1,981,892 output bytes through the
mover. These counts are transfer traffic, not an inferred saturated DDR rate.

| Non-overlapping phase groups | Total (s) | Outside backend service (s) |
|---|---:|---:|
| Language-model head | 4.129353 | 3.751637 |
| Smoothed MLP-down/residual | 3.095524 | 2.796824 |
| Attention | 2.809790 | 2.773781 |
| MLP-up | 1.843896 | 1.558847 |
| Smoothed attention projection/residual | 1.743098 | 1.646179 |
| QKV | 1.384642 | 1.168702 |
| All LayerNorm phases | 2.262515 | 2.200484 |

Separate fine instrumentation uses nested 64-bit inclusive intervals:
head project 4.124006 s, head affine finalization 0.745577 s and its nested
metadata 0.398687 s; non-head projects 6.208984 s; LayerNorm metadata 2.118446 s;
smoothing 1.814856 s; dynamic quantization including offload 0.230377 s.
**Do not sum these function counters** or add them to the phase table.
The fine binary measures 17.342948 s enabled / 17.313164 s disabled, a
0.029784-s instrumentation difference. Its code layout differs from the
production-style binary; it is diagnostic, not a substitute primary sample.
Production profiling adds about 0.028448 s relative to its measured mean;
no assumed overhead is subtracted from the reported primary measurements.

Fast-overlay whole REQUANT8 conversion takes 412.82 / 316.77 / 332.17 / 321.83
cycles per element for 1×64 / 1×768 / 1×3072 / 4×3072, versus CPU 854.71 /
796.88 / 793.54 / 793.74. All quantized bytes and binary64 unit bits match.
Scalar read-loop probes are 24.02 cycles/word in SRAM and 61.30 in DDR, almost
unchanged from slow. This establishes a locality penalty, not a full-model
memory-versus-arithmetic decomposition. Software floating-point preparation,
single-word scalar accesses and serial work remain the priorities.

See [bounded decisions](M5_FAST_DECISIONS.md): additional persistent metadata
cache and locality/fused RTL are explicitly deferred with memory/lifecycle
costs and a one-tile follow-up. Faster existing engines alone have only an
idealized 1.086× model ceiling with CPU work fixed; wider fusion that removes
CPU work is **not** restricted by that ceiling.

## Hardware qualification and honest build history

Accepted artifact: `build/m5_fast_pynq_finish_v2/m5_pynq.bit`.

| Gate/resource | Qualified result |
|---|---:|
| Fabric clock | 91 MHz |
| Setup WNS / TNS | +0.263 ns / 0 |
| Hold WNS / THS | +0.018 ns / 0 |
| LUTs / registers | 29,003 / 21,724 |
| BRAM36 / DSP | 95.5 / **0** |
| Occupied slices | 9,605 / 13,300 (72.22%) |
| Route | 44,993 / 44,993 nets; zero errors |

Hard +0.250-ns setup margin passes; +0.500 stretch does not. Versus the prior
qualified overlay: +561 LUTs, +36 registers, unchanged BRAM/DSP, slice use
71.55% → 72.22%. All twelve endpoint/clock checks pass. Final DRC/methodology
have zero errors/critical warnings. One RTSTAT-10 covers the same 30 unloaded
SmartConnect reset-pipeline nets. Six LUTAR-1 warnings were inspected in the
**actual final checkpoint**: five peripheral/core-reset NANDs and one reset/
registered sticky cancellation combination. The established drain/reset/flush
ordering and prohibition on opposed live reset changes remain required; this
is a reviewed waiver, not a claim that arbitrary LUT reset gating cannot glitch.
The separate final methodology report is authoritative: the timing report's
embedded methodology section is a stale earlier snapshot, explicitly labelled
as such by Vivado (it includes old TIMING-16 findings).

Console critical messages are not claimed to be absent: retained vendor
PSU-1/2 DDR skews are −0.009/−0.033, and the two Designutils 20-1280 generated
reset-module XDCs were checked to contain only a comment (no lost constraint).
Timing 38-282 and Route 35-39 occurred during implementation with artificial
extra setup margin; the final constrained 91-MHz reports pass. These match the
[established vendor-message dispositions](M2_VERIFICATION.md), with current
physical DDR/model and reset/lifecycle coverage. They do not waive final
DRC/methodology errors, critical warnings or unconstrained paths.

The initial two launches failed before synthesis (generated Tcl root, then
Vivado's injected Python environment). Stock RV32MFast then implemented at
**−3.598 ns**, with the long operand-selection/multiply/accumulate path proven
by a checkpoint timing diagnostic. Pipelining corrected that concrete cause.
A fresh source-pinned pipelined implementation (`m5_fast_pynq_v4`) reached
+0.184 ns, still short of the unchanged hard gate. A targeted continuation
replicated four measured **data** fanout nets and rerouted the existing
checkpoint with the original directives; it did not resynthesize or sweep
seeds. Its first launch was rejected before modification because forced
replication is unsupported post-route. The corrected continuation unroutes
only its in-memory copy and preserves original checkpoints. It reaches the
qualified +0.263 ns result above. No failed candidate is a qualified overlay.

Fast kernel SHA256:
`5ec64287fb4e01e14083132943e24191fcbadc46e72ac46fcc2778c874e2d09a`.
Final bitstream:
`6c647a3dc2f0305b9add96d6a8240be2ada9c6d91ac526feb8376a124551c9bc`.
Runtime:
`c3022942acbe619f4b05816f270d51d03c03efe501c0a166108adfbc6f14832e`.

## Exactness, memory and physical closure

Pipelined-core ISA: 84 passes and the same four historical expected failures.
Both real simulated harts pass 656 arithmetic pairs each (144 edges plus
512 randomized), all MUL high/low signedness and divide corner cases,
dependencies/pending DDR store/branch behavior, original memory/unaligned/
trap/abort/remap tests. Normal and delayed accelerator simulations pass
9,633 exact words per boot, interrupts, two boots, packet abort and 14 lifecycle
cases. No new regression waiver. The extra full-model numerical RTL simulation
hit its 120-second cap: **incomplete, not passed**; native and physical exact
model results provide the model-level checks instead.

Retained software and a fresh reproduction pass the complete native suite:
396 tensors / 4,670,788 trace values, all 50,257 logits, 60 generated tokens,
86 forward tokens, 78 operator cases / 7,779,561 words and the numerical,
arena/error-side-effect checks. Exact power-of-two scaling additionally passes
109,286 bitwise comparisons. Both runtime and profile binaries reproduce
byte-for-byte from fresh generated source directories.

Model pack, arena layout and capacity are unchanged: 266,289,152 allocated
bytes; full 1024 KV capacity. Native maximum workspace remains 1,909,188 bytes;
the final seeded board decode uses 1,632,708. REQUANT8 temporary int32 planes
are owned DDR workspace, rewound before GEMM. Prepared scales reuse existing
storage. There is no hidden model-lifetime precompute: all mandatory scaling,
metadata and conversions remain inside the measured request. Provisioning
and independent result checking are separate from START-through-delivery.

Final complete requests use the exact final overlay and production runtime,
starting with empty caches. Full final logits/KV and generated IDs pass:

| Original prompt | New tokens | Generated IDs | Model (s) | START → delivery (s) | Delivered token/s |
|---|---:|---|---:|---:|---:|
| Story, 13 input tokens | 2 | 257, 582 | 160.240109 | 161.298975 | 0.012399 |
| Science, 8 input tokens | 1 | 5004 | 87.844784 | 88.908668 | 0.011247 |
| Computing, 8 input tokens | 1 | 22712 | 87.848235 | 88.902496 | 0.011248 |

Previous corresponding delivered latencies were 228.3843 / 126.6988 /
126.7074 seconds. These are one complete request per prompt, not a repeated
latency distribution. Story's firmware first-token time is 142.844013 seconds;
its following cached decode takes 17.396092 seconds. Empty-cache prefill
dominates these short complete requests, explaining their lower token rates.

All five original story prefill traces match: embedding, h.0 QKV, h.0 context,
h.0 output, h.11 output. The prompt+generation overflow is rejected with the
original error, cache validity/count sentinels and all four cache-region hashes
unchanged, followed by successful accepted requests. Safe return/close and a
fresh read-only reopen report **owner=0, allocated_pages=0, pte_dma=0**. Normal
`rmmod` succeeds; no forced unload, reset shortcut or freed live DMA mapping.

Provisioning took **20.048838 seconds**, separate from resident request timing.
Whole final campaign, including provisioning and independent checks, took
**388.971765 seconds (6.48 minutes)** under the 1200-second safe alarm.
Linux MemAvailable was 425,092 KiB before, 166,980 while provisioned, and
422,684 after close; process high-water RSS 327,232 KiB is not a post-close
live allocation. Swap was already in use and increased during provisioning;
these are observations of this board session, not a no-swap or cold-boot claim.

## Reproduction and audit

Use fresh paths; never overwrite historical build products. Focused commands:

```sh
M5_FAST_PIPELINED=1 bash sim/run_m5_fast.sh memory
M5_FAST_PIPELINED=1 bash sim/run_m5_fast.sh accelerators
python3 -m scripts.m5_fast_sources build/m5_fast_compliance_fresh.sh --emit-compliance --pipeline
bash build/m5_fast_compliance_fresh.sh
M5_FAST_REQUANT=1 M5_FAST_RUNTIME_BUILD="$PWD/build/m5_fast_runtime_fresh" bash scripts/build_m5_fast_runtime.sh
```

The accepted hardware is a **two-stage build**, not the failed initial wrapper
alone. Reproduce the clean source-pinned pipelined flow with
`M5_FAST_PIPELINED=1 M5_FAST_VIVADO_BUILD="$PWD/build/m5_fast_pynq_fresh" bash zynq/build_m5_fast.sh`.
The recorded v4 flow stops at the hard-margin guard (+0.184 ns) after writing
its candidate checkpoint. Do not suppress unrelated failures. Inspect that
checkpoint/report before the documented bounded correction:

```sh
python3 -m scripts.m5_fast_sources build/m5_fast_finish_fresh_tail.tcl --emit-finish-tail
/home/elfo/Documents/2025.1/Vivado/bin/vivado -mode batch -nojournal \
  -log build/m5_fast_finish_fresh.log -source zynq/finish_m5_fast.tcl \
  -tclargs build/m5_fast_pynq_fresh build/m5_fast_pynq_finish_fresh build/m5_fast_finish_fresh_tail.tcl
```

The continuation reuses the hash-derived original full acceptance guards.
It preserves the 91-MHz clock and original implementation-only extra margin;
final reports remove that implementation-only margin exactly as the original
qualified M5 flow does. No clock/constraint relaxation was introduced here.
No duplicate clean FPGA build was run merely to reproduce already-passing
hardware. Recorded source/build snapshots and checkpoint hashes are evidence;
bitstream byte identity across future tool runs is not promised.

Physical access was SSH, not JTAG, using the existing DMA helper and PYNQ XRT
environment. The final campaign uses `zynq/m5_fast_complete.py` around the
unchanged checked runner: a 1200-second alarm raises through its ownership/
drain/close cleanup, not an unsafe forced process kill. No credentials saved.

Read-only closure command:
`python3 -m scripts.audit_m5_fast`. It runs the preserved prior audits, checks
the actual resolved fast/LSU/ID sources, re-hashes manifests and validates
timing, exact reports, all samples, candidate benefit and safe release.
Negative evidence tests: `python3 -m unittest tests.m5_fast.test_evidence`.
All 14 focused unit tests pass, including 24 altered-evidence gate checks and
an omitted-source-pin rejection. Large FPGA/model/test products remain local
ignored artifacts; the audit requires the retained files listed and hashed
in [machine evidence](m5_fast_evidence.json), not just a fresh Git checkout.
No 1024 marathon, three-by-twenty campaign, M6 or unrequested push.
