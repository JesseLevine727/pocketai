# M3 verification — IN PROGRESS / NOT QUALIFIED

M3 has not passed. This record tracks actual evidence as the gates in
[`M3_PLAN.md`](M3_PLAN.md) are completed. No M4/M5 implementation is underway.

## Completed gates

- G0: coherent GPT-2-correct scope and acceptance plan recorded.
- G1: physical unchanged-M2 baseline and measured host improvements **PASS**.
  See [`M3_PERFORMANCE.md`](M3_PERFORMANCE.md) for exact commands, source/artifact
  hashes, raw-data paths, statistical results, CPU comparison and limitations.
  Three host tests, 20 native ARM CPU cases, 462 FPGA/CPU projections including
  warmups, and M1's physical two-hart regression passed. All timed projection
  correctness checks happen after timing. The current offload path remains
  slower than the native CPU for both tested shapes.
- G2: GPT-2 semantics, numerical formats/error budgets and interface contract
  **PASS / v1 FROZEN BEFORE ARITHMETIC RTL**. See `NUMERICS.md` and
  `M3_ARCHITECTURE.md`. This is a design/reference gate, not proof of RTL or
  model-level quantization accuracy.
- G3: complete local numerical/protocol/lifecycle/cluster/ISA suite **PASS** on
  the pipelined candidate, including the final signed17 ADD path. No FPGA timing
  or physical-board gate is implied; new RTL changes require affected retests.

## G2 reference evidence

```bash
python3 -m unittest discover -s tests/m3 -v
python3 -m unittest tests.m2.test_gemm_ref -v
python3 -m tests.m3.qualify_numerics --random-cases 10000 \
  --output build/m3_numerics_v1.json
git diff --check
```

Fourteen M3 host unit tests and the five unchanged M2 reference tests pass.
Directed cases include signed rounding ties, zero/constant LayerNorm, all-masked
softmax, raw probability 32768 staying positive through int8 conversion, uniform
1024-entry probability conversion, full-width affine saturation, K=3072 maximum
sum and cancellation that rejects the saturated-int16 partial-sum shortcut.

Deterministic qualification seed: `0x50414d33`. Result:

| Operation | Checked domain | Worst observed error | Frozen bound |
|---|---|---:|---:|
| GELU | all 65,536 scalar inputs | 0.001952292221 absolute | 1/512 + 1e-12 |
| LayerNorm/affine | 10,420 vectors, 15,592,548 elements | 0.002043325944 absolute | 1/128 |
| Softmax | 10,240 vectors, 5,138,044 elements | 0.000148211035 absolute | 1/2048 |
| Softmax L1 | same vectors | 0.015629056822 | valid_count/32768 + 1/1024, checked per vector |
| Requantization | 10,000 vectors | 0.5 code LSB | 0.5 code LSB |
| AFFINE | 10,000 full-width/bias-cancellation vectors | exact rational half-LSB bound passes | 0.5 output LSB |
| AFFINE_GELU | 10,000 vectors | 0.004019243721 absolute | 1/128 |

Every tested softmax has exact declared mass and zero masked entries. LayerNorm's
worst case is a 15-element nearly constant vector with gain -8; no threshold was
relaxed to pass it. L1 is not constrained by comparing only an aggregate maximum
with the maximum possible length: each vector is checked against its own bound.

The following reference hashes identify the frozen G2 snapshot at local commit
`a62bee7`. Later additions to stream-packing helpers do not alter its equations.

| Evidence at G2 freeze | SHA-256 |
|---|---|
| `ref/sfpu_ref.py` | `1156d7ef30657200a384a93627fad1eec9b6b9c76d7b377a995535b8dc946d23` |
| `ref/gemm_v3_ref.py` | `18d94d8da514ba1efb4c5c22ba33452ac331ac48d0bc7a7ff7f99ff501589ff6` |
| `tests/m3/qualify_numerics.py` | `81149123659297f1dfcbf0c43dcba59a4363bed9550f02727a6632d3ec1948d8` |
| `build/m3_numerics_v1.json` | `f1d6be4390681ee94ccda6d3af3e3dc23156454ce8859654baf4d55721ff4516` |

The earlier candidate runs remain diagnostic artifacts, not the final figures
above. Operator references use float64 and exact Python integers; generated ROMs
and fabric implementation must still be independently checked in G3. No
checkpoint/token/model-accuracy evidence is inferred from these numerical tests.

## G3 partial evidence — wide GEMM and SFPU ALU

This subsection records the earlier foundation checkpoint (`77f7053`). The
operator controller and integration have subsequently been implemented; see the
next subsection. No FPGA or physical qualification is implied by local tests.

```bash
PA_CLEAN=1 bash sim/run_gemm_v3.sh
PA_CLEAN=1 bash sim/run_sfpu_alu.sh
PA_CLEAN=1 bash sim/run_m2.sh
PA_CLEAN=1 bash scripts/run_compliance.sh
python3 -m unittest discover -s tests/m3 -v
```

Results (2026-09-04 local time):

- `M3 WIDE GEMM RTL PASS cases=1007 random=1000 seed=0x50414733 cycles=11270319`:
  1000 mixed-format random cases plus seven directed cases, including wide
  K=3072 extrema/cancellation, partial dimensions and poisoned inactive lanes.
  The first paired descriptors use different legacy/wide formats.
- `M3 WIDE LIFECYCLE PASS interruptions=82 staging_immutable=1`: reset/abort
  around pipeline fill, full-K accumulation, each row group's packing and
  output boundary, followed by exact recovery and no stale output. Restaging
  every descriptor field after submit cannot mutate the in-flight operation.
- The same wide-enabled RTL also passes all **1007 original M2 vectors**:
  `M3 WIDE GEMM RTL PASS ... seed=0x50414d32 cycles=2313110`. Legacy CAPS and
  flag-zero dimension/stream behavior remain unchanged; unsupported flags and
  full-width invalid dimensions remain rejected. Legacy-only RTL passes too.
- `M3 ALU RTL PASS cases=15120 reset_abort_phases=336`: unsigned 64x64 multiply
  with overflow reporting, unsigned 64/64 division with exact remainder, and
  unsigned 80-bit floor square root with exact remainder. C++ integer arithmetic
  and an independent Newton square-root reference check results. Every active
  arithmetic cycle is interrupted by both reset and abort; new valid work
  recovers exactly. A request while busy cannot replace the accepted operation.
- `M2 LOCAL PASS`, including the full M1 local suite, active two-hart/GEMM
  simulation and fatal-warning lint.
- `M1 COMPLIANCE PASS rv32imc=25/25 rv32im=8/8 rv32i=44/48+4-xfail
  rv32Zicsr=6/6 rv32Zifencei=1/1`: the same 84 passes/four documented upstream
  expected failures. Dependency pins and Ibex configuration are unchanged.
- Fifteen M3 host unit tests pass, including independent legacy/wide input
  packing comparison and signed-int32 output padding checks.

| Partial implementation / evidence | SHA-256 |
|---|---|
| `rtl/gemm/pa_gemm.sv` | `659d6156cbad7f315df38b447262ce749e39ef1696a2ec72e83cc0281512efcd` |
| `rtl/gemm/pa_gemm_slot.sv` | `70e0ac4dd21b9e9ccecd8ab56adbb89bea7d33c7b98c1f16ab91a901955c24e2` |
| `rtl/sfpu/pa_sfpu_alu.sv` | `e347c4c686ddfbbe0264e5b88370c19c3d74dd39a9a6a9b10047a9d4d70331e5` |
| `build/m3_gemm_wide_final.log` | `f6ef6d59519a5ddfeac47848f021882587536deb3f46f8d0327ec5aa9b593ecd` |
| `build/m3_sfpu_alu_final.log` | `98ee2e7b4917da7fce065af75f9c1cdde14f5716099bc731b685b060857b7d5d` |
| `build/m3_m2_regression.log` | `f2f14f2922515936401ea111fee755c795879cf902e38314ef7c899e2851d5f9` |
| `build/m3_foundation_compliance.log` | `5817c84e5fc0e1ed53c24bd431967c41289900ca2f88a73a48c49299f2656378` |

ISA output is retained at `build/m3_foundation_compliance.log`. These are
development-gate logs, not replacements for M1/M2 historical board evidence.
The accepted M2 bit/HWH and G1 measurement artifacts remain unchanged.

## G3 operator/integration and timing development

The complete local gate passed in `build/m3_local_final.log` (pre-pipeline
snapshot): 21 host tests, full 10,000-case-per-operation numerical qualification,
wide/legacy GEMM, shared ALU, SFPU, cluster chains, M1/M2 local/fatal lint, and
the unchanged 84 ISA passes/four documented upstream expected failures.
Reproduce with `PA_CLEAN=1 bash sim/run_m3.sh`. Affected tests must be rerun on
the final timing-closed source; this earlier log is not final G4/G5 evidence.

The SFPU suite exercises the full descriptor/stream ABI, arbitrary input/output
stalls, stable held output, all seven operations, invalid full-width staging,
byte enables/reserved addresses, IRQs, framing/encoding errors and draining,
route interlock, staging immutability, control-error precedence, and recovery.
All scalar GELU values are exhausted. Additional packets exercise length 1,
partial lengths, and maximum lengths for every operation.

After pipelining the measured long rounding/sign/bias/saturation path,
`PA_CLEAN=1 bash sim/run_sfpu.sh` passes in `build/m3_sfpu_pipeline2.log`:

```
M3 SFPU PROTOCOL PASS
M3 SFPU LIFECYCLE PASS reset_abort_checkpoints=682 ops=7
M3 SFPU RTL PASS cases=3472 clocks=279784779 ops=1:76,2:1048,3:1120,4:310,5:310,6:310,7:298,
```

Cycle counts are exact, including the new pipeline stages. The 682 lifecycle
checkpoints cover reset and abort across observed control/ALU states, reduction
phases and first/middle/last index buckets, plus partial load/output recovery.
ALU exhaustive phase interruption remains separately covered by its 336 tests.
This is state/boundary coverage, not a claim to reset at every cycle of every
possible vector.

The 3472-vector packet set uses seed `0x53465033`. High-precision maximum errors
observed during generation are GELU 0.001952292220, LayerNorm 0.002294558987,
softmax 0.000139375351, AFFINE_GELU 0.004001582240; affine and requantization
meet their exact rational half-LSB limits, and ADD is exact. Every softmax has
exact mask/mass and passes its per-vector L1 bound. No frozen accuracy limit
has changed. Full details: `build/pa_sfpu/vectors.json`.

The pipelined cluster also passes in `build/m3_cluster_pipeline.log`, and strict
M3 lint passes in `build/m3_pipeline_lint.log`. Twenty-two host tests now pass,
including pinned-ROM reproduction, malformed packet files, canonical packing,
all full-shape chain dependencies, and independently computed dynamic scales.
The subsequent ADD narrowing uses its validated signed-int16 domain and retains
a 17-bit sum. The complete local suite passes on that candidate in
`build/m3_local_qualified.log`, including all 3472 SFPU vectors, 682 lifecycle
checkpoints, 315-step actual-result cluster chains, 22 host tests and the
unchanged M1/M2/ISA regressions. No timing or physical acceptance is inferred.

| Development evidence | SHA-256 |
|---|---|
| `build/m3_sfpu_pipeline2.log` | `02c2141eba5385e71afc74634f0876236c7b3ad3d844b4d8c22b98feefd116f7` |
| `build/m3_cluster_pipeline.log` | `bd5a2b01aba0fd220532d6adf5573493bc0cfff360cc3f33df584018736fcc68` |
| `build/m3_pipeline_lint.log` | `03e890366f29828fa9cfeba873f4b5f6488d530b92e56c91ddde5171ddc2fe4e` |
| `build/m3_local_final.log` (pre-pipeline) | `c277db92333b7f32b87bcad3faa149689007bf13586fbf4380255ceb62c09d01` |

ROMs are reproducible from the frozen reference and checked before builds:

| ROM | SHA-256 |
|---|---|
| `rtl/sfpu/gelu_q8.mem` | `1d926a3a1e189eee3b22bae953cc1310727ffbfd57cb0a5fd53f56295f60389d` |
| `rtl/sfpu/exp_q24.mem` | `8db26c8bcf50cb40c9e1a8a91c0ab3a36336b851ac28d4f2d4fffe6435562e35` |

`PA_CLEAN=1 bash sim/run_cluster_m3.sh` exercises 315 steps (305 GEMM, ten
SFPU), with **250 packets patched from actual prior RTL outputs**, not independent
golden replays. It covers a 1x768→3072→768 pre-LayerNorm MLP sub-block with
residual ADD and K=3072 down-projection, plus a 64-wide attention head with
1024 keys, 768 causally valid entries, scale 1/8, softmax, probability conversion,
and a 16-column value output tile. Final compact outputs are published/read back
in shared scratchpad. Both harts complete their unchanged M1 workload during
cluster traffic. Inputs/scales are explicit synthetic fixtures, not checkpoint
weights or evidence of full-model accuracy. Seed: `0x43484e33`.

Full-design explorations use fresh `build/m3_explore*` directories, with private
resolved-source copies. Vivado reads both ROMs successfully. An initial X RAM
coding form inferred distributed memory; explicit write-port selection now
infers four RAMB36 blocks for X, preserving synchronous behavior. The first
non-pipelined routes failed timing (-6.234 ns in explore2; -7.317 ns in explore3).
These are **failed development candidates**, not accepted overlays. Their
reports identify wide SFPU arithmetic and a high-fanout GEMM control net. No
clock, jitter, uncertainty or numerical gate was relaxed. Pipeline/physical
optimization work and two final clean builds remain required.

The pipelined explore4 reached **+0.199 ns** and was rejected. Independent clean
`build/m3_qual1` and `build/m3_qual2` builds from the signed17-ADD candidate both
reached **+0.238 ns**, with positive hold and no final clock/endpoint/DRC-error
issue, but were also **rejected**: the gate is +0.250 ns. Neither exported an
accepted root-level bitstream. Their identical limiting path runs from hart 0's
instruction-ALU register through decode/adder logic to `imd_val_q[0][29]`.
The local RTL source at `61bc496` remains unchanged and G3 stays passed.

Additional isolated post-route optimization experiments in `build/m3_postopt1`
(AlternateReplication/Explore/AggressiveExplore) and `build/m3_postopt2`
(pin/routing/placement/restructuring/clock optimization) retained +0.238 ns;
they are not accepted evidence. A targeted **pre-route** adder-control
replication experiment in `build/m3_fanout1`, using
`zynq/replicate_m3_control.tcl`, finished at +0.074 ns and was discarded.
Fresh candidates `build/m3_qual3` (Performance_ExploreWithRemap) and
`build/m3_qual4` (Performance_ExtraTimingOpt) now test alternative physical
implementation strategies with exactly the same RTL/clock/acceptance limits.
The chosen strategy is explicit through `M3_IMPLEMENTATION_STRATEGY` and printed
in the build log. Any adopted flow must be reproduced independently
and pass every final timing/DRC/clock gate before board programming. This is
physical implementation work, not a numerical or RTL contract change. The
commands follow [Vivado 2025.1 physical-optimization interfaces](https://docs.amd.com/r/2025.1-English/ug904-vivado-implementation/phys_opt_design).

The complete current local-gate log `build/m3_local_qualified.log` has SHA-256
`387cec7b5ec6fdf76399d43244d1e007921925d6ccda8916a9251824ebeabaf1`.
The current `pa_sfpu_compute.sv` and both clean-build source copies have SHA-256
`12ec9ce52018733ba86ecbb4772381e00eb7737be9f4d1284d7ac7b3449aa0a4`.

Physical harnesses `zynq/m3_run.py` and `zynq/run_m3_board.sh` are implemented
but **not yet run on M3 hardware**. They require a full-build PASS and a checked
source/vector/bit/HWH manifest, then run M1/M2, all M3 packet sets, seven operator
benchmarks and both actual-result chains (three warmups/30 timed repeats).
Numerical checking is outside timing; transfers, cache maintenance, A9 dynamic
quantization/patching and shared final-result publication remain inside the
declared chain boundary. Prepacked fixed weights/metadata are an explicit
exclusion; no full-model/token-rate or CPU speedup is inferred.

## Open gates

- Recheck G3 if subsequent timing work changes the qualified RTL.
- G4: two independent clean, fully constrained 95 MHz implementations.
- G5: physical M1/M2/M3 qualification of the exact accepted M3 overlay.
- G6: full evidence audit and scoped local milestone commit.

No accepted M3 timing, physical operator performance or full-model claim is made here.
M1/M2 historical closure records and qualified overlays remain unchanged.
