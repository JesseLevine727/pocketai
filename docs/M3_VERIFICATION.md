# M3 verification — PASS / CLOSED

M3 passed all required gates on 2026-09-05. This record associates the frozen
contracts, qualified source, local tests, two clean 95 MHz implementations and
exact-overlay physical results with [`M3_PLAN.md`](M3_PLAN.md). No M4/M5
implementation, remote push or full-model performance claim is included.

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
  the qualified pipelined RTL, including the final signed17 ADD path. FPGA
  and physical evidence are separate below; new RTL requires affected retests.
- G4: two independent clean full-overlay builds **PASS** at 95 MHz:
  qual3 +0.483 ns / qual5 +0.400 ns setup, zero TNS, positive hold, zero DSPs,
  clean final clock/endpoint checks, no DRC/methodology errors or critical
  warnings, and every remaining warning class reviewed.
- G5: exact qual3 overlay physically passes M1 before/after, M2 regression,
  all M3 packets and repeated actual-result chains. See the physical evidence
  and `M3_PERFORMANCE.md`.
- G6: evidence audit and coherent closure documentation **PASS**, recorded in
  the scoped local milestone commit containing this closure record. No push,
  M4/M5 work or changes to unrelated `NA/` files.

## Source and tool identity

The frozen numerical/reference checkpoint is local commit `a62bee7`; wide
GEMM/shared arithmetic is `77f7053`; the complete pipelined G3 RTL is
`61bc496`; the physical qualification driver and implementation-strategy
selection are `ff9e294`. No arithmetic RTL changed during the subsequent
qual1–qual5 physical-strategy work. Final closure adds evidence and selects the
already-tested strategy; it does not alter the v1 numerical equations or ABI.

Pinned dependencies (verified again with `bash scripts/check_deps.sh all`):

- Ibex `34b0705760ef3dfa00e99637432473d2be8f22f3`, exactly the tracked
  `patches/ibex-34b0705.m1-timing.diff`, SHA-256
  `2e80154b3d9b24f01dd41d74024df3e696d92189b5a54d5d05982541db075b8e`.
  No further Ibex modification was needed for M3 timing.
- riscv-compliance `844c6660ef3f0d9b96957991109dfd80cc4938e2`, exactly the
  tracked local patch, SHA-256
  `f897aa07192485af86f52ffbe69e3157f834618f0a08299fd5293fda71780527`.
  The four expected failures remain I-EBREAK-01, I-ECALL-01,
  I-MISALIGN_JMP-01 and I-MISALIGN_LDST-01; 84 tests pass.
- GPT-2 reference semantics: OpenAI GPT-2 commit
  `9b63575ef42771a015060c964af2c3da4cf7c8ab`, `src/model.py`, as frozen in
  `NUMERICS.md`. No checkpoint/calibration/tokenizer/model-quality claim.

Host: Ubuntu 24.04.3 LTS, Vivado 2025.1 build 6140274,
Digilent PYNQ-Z1 board part `www.digilentinc.com:pynq-z1:part0:1.0`,
Verilator 5.020, FuseSoC 2.4.6, Edalize 0.6.8,
RISC-V GCC 16.1.0 (`g6afcc4f6d`), Python 3.12.3 / NumPy 2.4.3.
Physical runtime versions are separately recorded below. Both clean Vivado
builds have private resolved source trees and captured build scripts.

| Qualified RTL | SHA-256 |
|---|---|
| `rtl/sfpu/pa_sfpu.sv` | `387612215c5d4bd95505c74e807b5625cdbb77524e324269697df502d7d1d4dd` |
| `rtl/sfpu/pa_sfpu_alu.sv` | `e347c4c686ddfbbe0264e5b88370c19c3d74dd39a9a6a9b10047a9d4d70331e5` |
| `rtl/sfpu/pa_sfpu_compute.sv` | `12ec9ce52018733ba86ecbb4772381e00eb7737be9f4d1284d7ac7b3449aa0a4` |
| `rtl/gemm/pa_gemm.sv` | `659d6156cbad7f315df38b447262ce749e39ef1696a2ec72e83cc0281512efcd` |
| `rtl/gemm/pa_gemm_slot.sv` | `70e0ac4dd21b9e9ccecd8ab56adbb89bea7d33c7b98c1f16ab91a901955c24e2` |
| `rtl/soc/pa_cluster_top.sv` | `9e71058fcd5a0658d182db5e4c1f763caf2033fa460f42d98e44c9fa46020d17` |

After G3's complete 22-host-test aggregate run, two additional board-harness
unit tests were added without RTL changes. The final **24 host tests pass** in
`build/m3_final_host.log` (SHA-256
`a7e82186260a7aea843efcac6d970bb0560044094e2d99dd77cf8bb2962f69a3`).
Shell syntax checks pass for all M3 local/build/board runners. The final
10,000-case-per-operation numerical result `build/m3_numerics_final.json` has
the same hash as the frozen G2 qualification JSON below; no accuracy limit or
reference equation was changed to close timing.

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
clock, jitter, uncertainty or numerical gate was relaxed. These failures drove
the pipeline/physical optimization; both final clean results are recorded below.

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
`build/m3_qual4` (Performance_ExtraTimingOpt) tested alternative physical
implementation strategies with exactly the same RTL/clock/acceptance limits.
Qual3 passed at +0.483 ns; qual4 reached +0.190 ns and was rejected.
The chosen strategy is explicit through `M3_IMPLEMENTATION_STRATEGY` and printed
in the build log. Any adopted flow must be reproduced independently
and pass every final timing/DRC/clock gate before board programming. This is
physical implementation work, not a numerical or RTL contract change. The
commands follow [Vivado 2025.1 physical-optimization interfaces](https://docs.amd.com/r/2025.1-English/ug904-vivado-implementation/phys_opt_design).

The complete current local-gate log `build/m3_local_qualified.log` has SHA-256
`387cec7b5ec6fdf76399d43244d1e007921925d6ccda8916a9251824ebeabaf1`.
The current `pa_sfpu_compute.sv` and both clean-build source copies have SHA-256
`12ec9ce52018733ba86ecbb4772381e00eb7737be9f4d1284d7ac7b3449aa0a4`.

Physical harnesses `zynq/m3_run.py` and `zynq/run_m3_board.sh` are implemented.
Physical qualification of the first timing-passing candidate **passed**. The
harnesses require a full-build PASS and a checked
source/vector/bit/HWH manifest, then run M1/M2, all M3 packet sets, seven operator
benchmarks and both actual-result chains (three warmups/30 timed repeats).
Numerical checking is outside timing; transfers, cache maintenance, A9 dynamic
quantization/patching and shared final-result publication remain inside the
declared chain boundary. Prepacked fixed weights/metadata are an explicit
exclusion; no full-model/token-rate or CPU speedup is inferred.

## G4 implementation evidence — two independent clean builds PASS

The unchanged G3 RTL passes the complete build gate in `build/m3_qual3` using
`Performance_ExploreWithRemap`. The independent same-strategy clean rebuild is
`build/m3_qual5`, which also **passes**. Its resolved source tree and captured
build scripts compare byte-for-byte equal with qual3. Synthesis checksum is
`350ce63e` in both; independent placement/routing results differ, as reflected
in the timing and artifact hashes. Reproducible acceptance does not mean
byte-identical bitstreams or identical slack.

```bash
PYNQ_BOARD_REPO=/home/elfo/Documents/MASc/pynq-z1-llm-accel/external/board_files \
M3_VIVADO_BUILD_DIR=build/m3_qual3 \
M3_IMPLEMENTATION_STRATEGY=Performance_ExploreWithRemap PA_CLEAN=1 \
bash zynq/build_m3.sh
# Repeat the same command with a fresh build/m3_qual5 directory.
diff -qr build/m3_qual3/resolved_sources/src build/m3_qual5/resolved_sources/src
diff -qr build/m3_qual3/build_scripts build/m3_qual5/build_scripts
```

| Final full-design result | qual3 | qual5 |
|---|---:|---:|
| Fabric clock | 95 MHz / 10.526 ns | same |
| Setup WNS / TNS | +0.483 ns / 0 | +0.400 ns / 0 |
| Hold WHS / THS | +0.018 ns / 0 | +0.016 ns / 0 |
| Clock/endpoint checks | all 12 categories zero | same |
| Routing errors | 0 / fully routed | same |
| DSP primitives | 0 | 0 |
| LUT as logic / flip-flops | 27,294 / 23,019 | 27,293 / 23,019 |
| Total slice LUTs (including memory) | 28,233 | 28,232 |
| Block RAM tiles | 97 (96 RAMB36 + 2 RAMB18) | same |
| Final DRC errors / critical warnings | 0 / 0 | 0 / 0 |
| Final DRC warning / advisories | RTSTAT-10: 1 / REQP-181: 2 | same |
| Methodology warnings | LUTAR-1: 2; no errors/critical warnings | same |

The required +0.250 ns margin is met; the +0.500 ns stretch is not. The existing
extra 0.526315 ns setup uncertainty is used only to guide implementation
(Vivado rounds it to 0.526 ns), then removed for final reporting. MMCM/PS
generated clocks and vendor jitter remain; no false paths or other exceptions
were added to evade a failing path. The final bitstream is regenerated from the
same optimized design that produced these final reports.

The captured build scripts use an explicit `M3_IMPLEMENTATION_STRATEGY`
override, shown above. Closure makes `Performance_ExploreWithRemap` the default
as well; this selects exactly the tested flow, not a new RTL/constraint
configuration. The board runner defaults to the physically accepted qual3
artifact, not rejected qual2. Fresh reproduction directories remain mandatory.

| qual3 artifact | SHA-256 |
|---|---|
| `m3_pynq.bit` | `78fc22f0e9263759ed2ac6417345ce8c6ef7815438febd9c6a4332532790be5b` |
| `m3_pynq.hwh` | `20a2f3caa860b3dd644b9f4b5e7fa9bb8e7a70dc6a51dbd280e7e9347a3eafd6` |
| `m3_pynq.xsa` | `b49bfb9ad6b72c0ae6663f96fdb05e3cd6446f7d796fb5545f72652202e97a57` |
| `m3_pynq_final.dcp` | `40e1f647c2082eda8da780159085724bc261bd4d45660c96269c9a7fc0022c4a` |
| `reports/m3_timing_summary.rpt` | `447ac00b6b9cdbd23d8c83bd2383e513bf573b8f15c5b1da1d116b32fc1f03ae` |
| `reports/m3_utilization.rpt` | `aca660b9ff4988dc21a09551848d5c6df581859753b948cc6a09cef92e11701b` |
| `reports/m3_drc.rpt` | `4c9fdafec5ae66d8fffc99c0c1b06a6b6a0446da4f4a482ddcdb29c595f4afc7` |
| `reports/m3_methodology.rpt` | `bc0b017bbdc4922ffc0521b0a67da4f1dd09eb487cf31c7779c3d1448f825e45` |
| `reports/m3_route_status.rpt` | `81da1c547f736cf834ddba1c569b3e3b1cce9f0bc3b319c1aa6040b5243bb778` |
| `reset_audit.log` | `bb93cd111003ddc2d62df22fe316e95ebd9d6ff915a935a3a33ea00bc07c9df0` |

| qual5 artifact | SHA-256 |
|---|---|
| `m3_pynq.bit` | `629af0b92a5422bfa1f12a7b940b46b0abb2a249fd846509bd87ab9a0d896e9e` |
| `m3_pynq.hwh` | `1f4deba9bec5e5b4793165024c5e5d3974c0713fcaa1d9fc31700e3258326454` |
| `m3_pynq.xsa` | `a60f6e1ca4fbf440943d69671b8eff2bb0ddecf528acd56e533bd9eb13c1931c` |
| `m3_pynq_final.dcp` | `421c36f6a193a99a9ceb660249638a5417402f6816ff6633cfa2a08a9f2b427e` |
| `reports/m3_timing_summary.rpt` | `53de654412f16d54ea0d1d5188ed91704e1b73fb0ec2877e379f676fa5ba791e` |
| `reports/m3_utilization.rpt` | `9c7cb0e9d95163c8983a6ba45e4fe78b441c9559db9f5f710ec84b5f86627607` |
| `reports/m3_drc.rpt` | `9ea1d4027f3c0a039567e96aa45d60ebbeacc1c1b901d9375305bbb4089c0af4` |
| `reports/m3_methodology.rpt` | `398fbbf4039016a1109aff19f08bf4c1cf417eddfa83b97336acc2293d726504` |
| `reports/m3_route_status.rpt` | `aa2cda7eab6201b786a606e08d2059456ffac00422563861f5b25df4078ee077` |
| `reset_audit.log` | `3554098256a3deddeff1c9bf075942b703cc3ccc17f88c6887d1a93d6dd333aa` |
| `vivado.log` | `158f9bbf2e28860b49a5c616d4b97a44a739b37e96b65b9519a93b52d3420fcf` |

### Warning review

Both consoles have identical diagnostic-class counts and were reviewed, including the
earlier critical messages (two each of PSU-1, PSU-2 and Designutils 20-1280;
one Timing 38-282 under artificial uncertainty). Final timing, DRC and
methodology have no errors or critical warnings. This is a specific review,
not an unrestricted waiver for future source or implementation changes. Both
final-checkpoint reset audits pass, with the same LUT2 functions/input drivers
and correctly derived clocks.

| Messages | Disposition / evidence |
|---|---|
| `PSU-1`, `PSU-2` | Digilent board preset has DDR DQS skews -0.009/-0.033. Vendor settings retained, as in M1/M2; exact-M3 physical DDR/DMA qualification passed. |
| `Designutils 20-1280` | Two optimized SmartConnect reset modules are absent; both named generated board XDC files were inspected and contain only a physical-constraints comment. No constraint is lost. |
| `BD 41-1306` | GPIO is explicitly connected to core reset instead of an external board GPIO; polarity checked by build. |
| `BD 41-3281` | Separate GP0 control and HP0 DMA SmartConnects are intentionally instantiated and explicitly addressed. |
| `BD 41-2384`, `Synth 8-10507` | Generated internal SmartConnect payload/interface metadata. External streams are still 32-bit; local AXI tests and board transfer checks passed. |
| `BD 41-702`, `IP_Flow 19-11770` | Initial interface-frequency metadata; final physical pins use the common MMCM 95 MHz clock, with all clock/endpoint categories zero. |
| `Synth 8-11067` | Upstream package parameters are interpreted as localparams, consistent with package semantics. |
| `Synth 8-2898` | Nine runtime assertions in the new SFPU are omitted from synthesis; they are active in the complete assertion-enabled Verilator suite. |
| `Synth 8-3917` | Configured-out Ibex integrity, capability, cache and shadow outputs are constant; core configuration/pin and ISA regression unchanged. |
| `Synth 8-6014`, `8-3332`, `8-3936` | Unused vendor/optional core state removed. The three SFPU names are block-local procedural temporaries (`difference`, `shift_remainder`, `positive_gelu`), not discarded live pipeline state; exact full-domain/vector tests pass. |
| `Synth 8-7071`, `8-7023`, `8-7129` | Unused optional vendor ports and synchronous-DMA CDC helpers. Final clock/endpoint checks pass. |
| `Synth 8-3848`, `8-3295` | Disabled scatter-gather/status connections and unused reset outputs; unused DMA status inputs tied low. |
| `Synth 8-7137`, `8-4767` | Existing console storage is unreset inside a resettable process; reset occupancy prevents stale-byte visibility. Local regression and both physical console checks passed. |
| `Synth 8-6841` | Whole-word/banked RAM write enables prevent the named byte-wide physical optimization; logical byte strobes remain tested. |
| `Synth 8-3323` | Intermediate arithmetic mapping attempts DSP allocation; final implemented DSP count is strictly zero. |
| `Vivado 12-7122`, deprecated `-fanout_limit` | No incremental checkpoint in this independently clean flow; deprecated option still accepted by pinned Vivado. |
| `Vivado 12-2489` | Temporary setup uncertainty rounded to 0.526 ns; removed only for final qualification, not vendor jitter. |
| `Route 35-39`, `Timing 38-282` | Implementation under deliberately extra uncertainty; final true-95-MHz timing must independently meet +0.250 ns / zero TNS / positive hold. |
| `Power 33-332` | Default reset activity makes estimated power unreliable; no measured power claim. |
| `Project 1-645` | XSA lacks board-image artwork; does not alter bit/HWH function. |
| DRC `RTSTAT-10` | 20 generated SmartConnect reset-pipeline nets have no routable loads; all routable nets fully routed. |
| DRC `REQP-181` | Two vendor DMA FIFO RAMs use WRITE_FIRST; vendor FIFO owns collision avoidance. Exact-M3 physical DMA checks passed. |
| Methodology `LUTAR-1` | Exactly two LUT2s, both INIT=4'h7 (active-high reset NAND), combine GPIO core-reset and synchronized system-reset registers. Read-only final-checkpoint audit proves both inputs/drivers. Supported sequencing holds GPIO reset low during programming/system reset and releases only after clock/reset stabilize and firmware is loaded; no arbitrary simultaneous toggling is supported. |

Reset audit reproduction:

```bash
M3_DIAGNOSTIC_DCP="$PWD/build/m3_qual3/m3_pynq_final.dcp" \
/home/elfo/Documents/2025.1/Vivado/bin/vivado -mode batch -nojournal \
  -log build/m3_qual3/reset_audit.log -source zynq/audit_m3_candidate.tcl
```

## G5 physical qualification — PASS

```bash
M3_VIVADO_BUILD_DIR=build/m3_qual3 bash zynq/run_m3_board.sh
```

SSH `xilinx@10.0.0.223`, staged at `/home/xilinx/pocketai_m3`, login-shell
`sudo -E` with interactive authentication; no credential stored. The runner
checks a 15-file manifest locally/remotely **before programming** and the M3
driver rechecks requested artifact paths. The tested bit/HWH are the exact
qual3 files in the table above, not a failed/internal candidate bitstream.

Physical results, 2026-09-05 (M3 start 04:38:12 UTC):

- M1 before and after: both harts print READY, count0=count1=10000,
  messages `468aad43` / `85558c0a`, work `29c4c2c2` / `a3e316ec`.
  Both `M1 BOARD PASS elapsed_s=0.047`.
- Unchanged M2: 16×768×768 projection, 48 descriptors / 24 pairs,
  12,288 int16 results, 6144 exact DDR and shared-scratchpad words, all pass.
  Cycles 154,752 / MACs 9,437,184 remain unchanged. Its one-run
  validation-inclusive latency was 107.529 ms; this does not replace G1 or
  historical M2's repeated/acceptance evidence.
- `M3 BOARD CONTROL PASS`: IDs/capabilities, both-engine busy route interlocks,
  invalid op/length/parameter descriptor rejection, abort and recovery.
- `M3 BOARD WIDE_MIXED_GEMM PASS cases=1007`: 251 legacy / 756 wide packets,
  seed `0x50414733`; full-range K=3072, cancellation and all directed/random
  packets also used by RTL qualification. Every output word and per-packet
  cycles/MACs/bytes/tag/completion count/error/idle checks pass.
- `M3 BOARD SFPU PASS cases=3472`, seed `0x53465033`: GELU 76 packets
  (including all 65,536 scalar inputs), LayerNorm 1048, softmax 1120,
  AFFINE 310, REQUANT8 310, AFFINE_GELU 310, ADD 298. Every delivered word,
  length/cycles/bytes/tag/completion count/error/idle check passes against the
  exact frozen reference vectors. Their high-precision errors are the G3
  vector qualification figures above; physical agreement does not establish
  additional model-quantization accuracy.
- Seven representative operator benchmarks, three warmups / 30 timed trials
  each, with all exact output/counter checks outside timing.
- Both chain benchmarks, seed `0x43484e33`, three warmups / 30 trials each:
  MLP 246 descriptors / 245 actual-result patches and attention 69 / 5.
  All intermediate and final tensors match; compact shared-scratchpad
  publication and last-descriptor/cumulative counters pass. Dynamic row
  scaling uses actual results inside timing, not frozen golden parameters.
- Final totals: **11,072 GEMM + 4033 SFPU = 15,105 descriptors** in the M3
  harness, including warmups, plus the separate 48-descriptor M2 regression.
  Final `M3 BOARD PASS` and `M3 PHYSICAL ACCEPTANCE PASS` are present.

The driver resets DMA before releasing CMA buffers. The supported reset
sequence and DDR/DMA transfers pass on the exact overlay; this is workload
qualification, not an exhaustive voltage/temperature/reset-glitch campaign.
Reset/abort/framing/IRQ exhaustive phase/boundary coverage remains the G3
simulation evidence, not an invented physical fault-injection claim.

| Physical evidence | SHA-256 |
|---|---|
| `build/m3_qual3/board.log` | `074af80835b0c71b180a5a558e60594aa0e706f50ec61badce91fe49d1c540b1` |
| `build/m3_qual3/board.json` | `cb7faf85c66a5b097b01e88091e75c82e42a1d21daea193058b5f50100ebabe4` |
| `build/m3_qual3/board_manifest.json` | `0c304167a86517ca834c7665c520000befa4639ce72a6647e86ae80b8da686d5` |
| `build/m3_qual3/vivado.log` | `0ff4d1775010014d1e9809976162f352284bb237e3fa0f5576b92f848754c801` |
| `build/pa_sfpu/vectors.bin` | `79a3933da00f82a796acdfe90fde4147dd5548b5abb702d060c4b201bec6b082` |
| `build/pa_gemm_v3/vectors.bin` | `b1bb34c09327b1f89ffa1d9ca29ea6dc62a38084c9ed78d832063e419dc6ade5` |
| `build/pa_cluster_m3/chains.bin` | `1245e3c069492728de312af6c2d2aaccc5136e6fa7b53450ddd837adb06d8930` |
| `build/pa_cluster/cluster.bin` | `1c877c4ccf82060ae3dd71645fe5e1892215b03d95fad1edb2e020ca6f85dcc0` |
| `zynq/m3_run.py` | `aec8ff011ea0663da08d10ee5ae888367b460206c7b698900bca2b7447ad1e2f` |
| `zynq/m3_manifest.py` | `36b0cda0b0c3ac2df28b8ea12b0f49bc74e87cea1de200ddba4768e30b2f1d8f` |

The manifest also hashes all staged references, M1/M2 runners, full resolved
build sources, build-script snapshots and final reports. Runtime/platform,
clock-tree readback and every performance sample are in `board.json`. Timed
boundaries, latency/tail/variability/bytes and limitations are fully described in
[`M3_PERFORMANCE.md`](M3_PERFORMANCE.md). No full-model/token-rate claim is made.

## G6 closure audit and limitations — PASS

All required G0–G6 outcomes are satisfied by the associated evidence above.
The final hash audit rechecks all 189 build-evidence files in the physical
manifest, exact tested bit/HWH, vectors, driver and frozen reference. The
independent qual5 source/script trees match qual3, all final reports pass, and
both warning/reset audits are complete. Dependency pins/patches, M1 firmware,
historical M2 bit/HWH and G1 baseline JSON were rechecked unchanged. Scoped
diff/shell/host checks pass. Closure documentation is included in the local
milestone commit; `NA/` is untouched and nothing is pushed remotely. This is
the implementation agent's evidence review, not independent external peer review.

No mandatory M3 work remains. Important limits for the next milestone:

- This is **W8A8 GEMM arithmetic with int16 activation storage**, not W8A16
  matrix multiplication. Wide int32 results and K=3072 prevent premature
  saturation, but do not prove model-level quantization accuracy.
- GPT-2 semantics/operator accuracy are pinned; actual checkpoint, tokenizer,
  calibration, layer-by-layer model comparison and tokens are M4 work.
- The SFPU shares sequential arithmetic and one descriptor slot. It is exact
  within the frozen budgets, not claimed to be the fastest possible design.
- Chains retain A9 descriptor ownership, dynamic-scale calculation, DDR
  intermediate round trips and final A9 scratchpad publication. No direct
  fabric forwarding, autonomous inference, or physical concurrent-hart speed
  result is claimed. Local concurrent-hart/accelerator tests pass.
- Timing is qualified at **95 MHz**, not 100 MHz. +0.500 ns remains an
  unachieved stretch; both builds exceed the unchanged +0.250 ns hard gate.
  Future M4 changes need their own timing/resource/physical qualification.
- Full overlay uses 97/140 BRAM tiles and approximately 53.1% of slice LUTs;
  later buffers/features must fit the remaining resources. No ASIC/PPA,
  measured power/energy, full-model speedup or token-rate claim is made.

M1/M2 historical closure records and qualified overlays remain unchanged.
M4 and M5 are **not started**.
