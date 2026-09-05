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

| Evidence | SHA-256 |
|---|---|
| `ref/sfpu_ref.py` | `1156d7ef30657200a384a93627fad1eec9b6b9c76d7b377a995535b8dc946d23` |
| `ref/gemm_v3_ref.py` | `18d94d8da514ba1efb4c5c22ba33452ac331ac48d0bc7a7ff7f99ff501589ff6` |
| `tests/m3/qualify_numerics.py` | `81149123659297f1dfcbf0c43dcba59a4363bed9550f02727a6632d3ec1948d8` |
| `build/m3_numerics_v1.json` | `f1d6be4390681ee94ccda6d3af3e3dc23156454ce8859654baf4d55721ff4516` |

The earlier candidate runs remain diagnostic artifacts, not the final figures
above. Operator references use float64 and exact Python integers; generated ROMs
and fabric implementation must still be independently checked in G3. No
checkpoint/token/model-accuracy evidence is inferred from these numerical tests.

## Open gates

- G3: arithmetic RTL, numerical/protocol/lifecycle/chain tests and regressions.
- G4: two independent clean, fully constrained 95 MHz implementations.
- G5: physical M1/M2/M3 qualification of the exact accepted M3 overlay.
- G6: full evidence audit and scoped local milestone commit.

No M3 timing, accuracy, operator performance or full-model claim is made here.
M1/M2 historical closure records and qualified overlays remain unchanged.
