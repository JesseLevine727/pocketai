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

**G3 is still open.** The wide GEMM extension and shared arithmetic unit are
implemented and pass standalone tests; the SFPU operator controller, stream
mux and complete M3 cluster integration are not implemented yet. No new FPGA
timing or physical M3 qualification is claimed by these tests.

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

## Open gates

- G3: arithmetic RTL, numerical/protocol/lifecycle/chain tests and regressions.
- G4: two independent clean, fully constrained 95 MHz implementations.
- G5: physical M1/M2/M3 qualification of the exact accepted M3 overlay.
- G6: full evidence audit and scoped local milestone commit.

No M3 timing, accuracy, operator performance or full-model claim is made here.
M1/M2 historical closure records and qualified overlays remain unchanged.
