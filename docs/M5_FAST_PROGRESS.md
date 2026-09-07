# M5 fast-controller pass — live evidence

This investigation log is retained as build history. The goal is now **closed**;
see [final results](M5_FAST_RESULTS.md) and [evidence](m5_fast_evidence.json).
The prior qualified baseline `c40d7cd` remains an unchanged historical result.

## Core implementation

The new flows derive only fresh exported sources. Frozen M1–M5 sources and
their closure audits remain unchanged. `scripts/m5_fast_sources.py` checks
the actual compilation manifest, both wrapper instances, exact LSU/ID fixes
and multiplier identity. Generated Verilator types are resolved per hart;
Vivado checks actual synthesized fast-state registers on both harts and DSP0.
Ten fail-closed source-derivation tests pass, including wrong/duplicate source,
missing opt-in, symlink, changed second hart and pipeline identity rejection.

Stock RV32MFast:

- ISA: `build/m5_fast_compliance.TwT4z7`, 84 passes and four unchanged expected
  failures (88 total).
- Both-hart 656 input-pair arithmetic test plus original memory/unaligned,
  branch/store, fault, abort/remap/restart regression passes in
  `build/m5_fast_memory.UVwrrr/arithmetic.log`. Independent shift/add and
  restoring-division references cover MUL/MULH/MULHSU/MULHU/DIV/DIVU/REM/REMU,
  zero division, signed overflow, forwarding and pending DDR stores.
- Accelerator integration passes normal and delayed-memory runs in
  `build/m5_fast_accelerators.pcH9AC`: exact 9,633 output words per boot,
  mailbox/engine/DMA IRQs, two boots, packet abort and 14 lifecycle cases.
- Extra full Ibex numerical simulation `build/m5_fast_numerics.DVck1m` reached
  the 120-second execution cap. **Incomplete, not a pass.** Native full exact
  regression and eventual physical full-model checks remain required.
- Two shell/Tcl export launch errors occurred before synthesis: generated Tcl
  root-path resolution (v1), then Vivado selecting a Python without PyYAML
  (v2). Corrected with explicit repo root and absolute Python ignoring its
  injected Python environment. No timing strategy changes.
- First implemented stock-fast design, `build/m5_fast_pynq_v3`, fails final
  91-MHz setup at **−3.598 ns**. Synthesis confirms both fast harts/DSP0. Do not
  deploy this failed candidate as qualified hardware.

### Timing diagnosis and corrected fast unit

Ranked hypotheses were multiplier/MAC depth, placement/routing congestion and
a displaced unrelated control path. The read-only post-place checkpoint probe
(`build/m5_fast_physopt_diagnostic`) and final routed worst-path report both
identify operand selection through multiplier/addition to intermediate or
writeback storage. Final worst path is 21 logic levels / 14.538 ns data delay;
placed utilization is only 28,913 LUTs and 70.32% slices. Thus a seed sweep or
clock relaxation is not the chosen correction.

`rtl/m5_fast/*.sv.inc` implements an isolated pipelined derivation of the
RV32MFast kernel: partial products, product assembly, accumulation. The
original high/low signed arithmetic and iterative divider are preserved;
intermediate writes and terminal ready/valid retirement occur only in the
commit phase. Reset clears all pipeline state. This is **9/12 execute cycles
for MUL/MULH plus external stalls**, not stock 3/4 and not RV32MSlow.

Corrected simulation evidence:

- `build/m5_fast_memory.ljzJvY`: directed/random arithmetic on both harts and
  complete memory/restart regression PASS.
- `build/m5_fast_accelerators.cbbJNX`: normal/delayed accelerator, interrupts,
  exact output, abort/drain/reset cases PASS.
- `build/m5_fast_compliance.xEIhne`: 84 ISA passes, same four expected failures.
- Multiplier source SHA256:
  `5ec64287fb4e01e14083132943e24191fcbadc46e72ac46fcc2778c874e2d09a`.
- Corrected implementation: `build/m5_fast_pynq_v4` reaches **+0.184 ns** with
  positive hold, but still misses the preserved +0.250-ns margin by 0.066 ns.
  The worst paths now include the GEMM pack/address fanout and core operand
  selection, not the original full-depth multiplier/MAC path. A bounded
  targeted replication continuation from its routed `m5_candidate.dcp` is
  completed in `build/m5_fast_pynq_finish_v2`. This does not resynthesize, change
  clock/constraints or run a seed sweep; the original full acceptance checks
  are reused. **Final timing passes: WNS +0.263 ns, TNS 0, hold +0.018 ns,
  THS 0, DSP0, full route and accepted DRC/methodology.** Physical fast-overlay
  seeded-decode and complete-request qualification now pass.
  Do not spend time chasing the +0.500 stretch.
  The first continuation was rejected without modifying the design: Vivado
  2025.1 does not support forced replication in post-route mode. Its diagnostic
  also exposed that a timing STARTPOINT_PIN names a clock pin; the corrected
  selector resolves the source register's Q and explicitly rejects clock nets.
  The second continuation unroutes only its in-memory checkpoint copy, applies
  the measured data-net correction, and reroutes with the original directive.
  Original checkpoints are retained unchanged.

## Fine profile and software investigations

The generated fine-counter firmware passes the full native exact regression:
396 traces / 4,670,788 intermediate values, complete logits, 60 generated tokens
and the numerical/operation/arena tests. Original sources are hash-pinned;
generated sources and firmware are retained per build.

On the **old qualified slow overlay**, `build/m5_fast_fine_v1/fine_slow_v2.json`
passes full exact seeded logits/KV with profiling enabled and disabled:
24.545857 / 24.516374 seconds model time. These are diagnostics, not a new
three-sample primary performance claim. Function counters are inclusive and
overlap with their callers:

| Measured function | Calls | Seconds |
|---|---:|---:|
| Dynamic quantization | 49 | 0.601572 |
| LayerNorm metadata | 25 | 2.196092 |
| Smoothing including backend | 24 | 1.891881 |
| Non-head project including backend/children | 48 | 10.409059 |
| Head project including backend/children | 1 | 6.894427 |
| Head affine finalization including backend/metadata | 1 | 0.745571 |
| Head affine metadata (nested in above) | 1 | 0.398711 |

The first board launch lacked the login XRT environment and failed before
programming; safe cleanup occurred. Sourcing `/etc/profile.d/xrt_setup.sh`
corrected the environment for the successful run. No credentials stored.

`build/m5_fast_requant_v1/requant_slow.json` measures a complete candidate
SFPU REQUANT8 conversion against the retained CPU conversion, four repeats
per shape, including max scan, expansion, launch/DMA, output packing and unit
calculation. Every output byte and every unit's binary64 bits compare exactly.

| Shape rows×columns | CPU cycles/element | Complete SFPU cycles/element |
|---|---:|---:|
| 1×64 | 881.44 | 413.80 |
| 1×768 | 831.96 | 318.78 |
| 1×3072 | 829.77 | 334.09 |
| 4×3072 | 830.46 | 321.88 |

Positive on both overlays. The fast-overlay probe and three-sample model
comparison now justify adoption. Engine-only REQUANT8 is 75 cycles/element,
not the full conversion.

The next software candidate reuses exact rounded projection channel scales
between range and finalization passes and uses exact binary64 exponent shifts
on the normal-to-normal power-of-two scaling domain (original arithmetic
fallback for other domains). No extra storage or model-format changes. Full
native exact regression passes in `build/m5_fast_prepare_v1/native_test.log`;
the physical diagnostic passes all final logits/KV at 18.144344 profiled and
18.115953 unprofiled seconds (`prepare_slow.json`). Head project drops from
6.894427 to 4.224897 seconds; the other projects drop from 10.409059 to
6.679256 seconds. These are diagnostic pairs, not three-sample final results.

The second preparation revision also bypasses exponent-zero LayerNorm
variance/correction work: with positive epsilon the identical numerator and
denominator give exactly one. Other exponents retain the original calculation.
Native full exact regression and the physical diagnostic both pass
(`build/m5_fast_prepare_v2`): 18.111929 profiled / 18.083795 unprofiled seconds.
The exact power-of-two helper additionally passes 109,286 bitwise comparisons
against original multiplication, including normals/subnormals/signed zero,
infinities, boundary transitions and randomized bit patterns.

Production-style, non-fine-instrumented firmware candidates are built in
`build/m5_fast_runtime_v1` (preparation) and
`build/m5_fast_runtime_requant_v1` (preparation plus project quantization
offload). Both pass the full native exact regression and 31,666 integer /
1,715 affine error-side-effect comparisons. The extra offload workspace is
reclaimed before GEMM; peak workspace remains 1,909,188 bytes in these tests.
Both production-style candidates pass the exact fast-overlay five-run cached
decode comparison. Model means: fast-only 24.076211 s, preparation 17.763754 s,
preparation plus REQUANT8 17.400193 s. Retain both software improvements.

Freeze the optional software candidate set here: preparation alone versus
preparation plus existing REQUANT8, chosen with fast-overlay evidence. Do not
start another software search. Persistent model-lifetime metadata and
locality/fusion are explicitly deferred in [the decisions](M5_FAST_DECISIONS.md),
informed by the final fast-core profile. Required fast-core qualification is
complete.

## Final closure

Timing, candidate adoption, matched fixed-context performance, byte-identical
clean firmware reproduction, complete physical 2/1/1 original requests,
safety/cleanup, source/artifact evidence and read-only closure audit pass.
The final physical campaign took 388.97 seconds. New evidence tests reject
altered timing, exact results, missing samples, ownership/arena changes and
omitted source pins. No push or M6.
