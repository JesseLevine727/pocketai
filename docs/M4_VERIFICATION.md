# M4 verification — IN PROGRESS / NOT QUALIFIED

M3 is closed/pushed at `68da8f8`. M4 implementation began 2026-09-05 after goal
initialization. No RTL, accepted overlay, M1–M3 numerical contract or physical
board programming has changed. M5/M6 remain unstarted. Full acceptance is in
[`M4_PLAN.md`](M4_PLAN.md).

## Current gates

- G0 plan/status: recorded.
- G1: checkpoint/tokenizer pinned; independent floating-model equations pass
  oracle/cached/generation tests. First complete integer reference is a
  **development candidate**, not a model-quality PASS.
- G2: **not passed**. Direct use of M3's fixed activation range fails on real
  GPT-2. The diagnostic evidence below changes the next implementation step:
  represent outliers without clipping and qualify calibrated quantization.
- G3–G7: not passed; no M4 physical inference/performance claim.

## Identity, data and reproduction

Checkpoint: [openai-community/gpt2 at 607a30d](https://huggingface.co/openai-community/gpt2/tree/607a30d783dfa663caf39e06633721c8d4cfcd7e),
MIT license, **124,439,808 trainable parameters**, original Conv1D weights in
`[input,output]` layout, 50,257-token vocabulary. The safetensors file additionally
contains twelve static causal masks; those are not learned parameters. The
independent implementation excludes only keys ending **`.attn.bias`**, not
`c_attn.bias` (learned QKV bias). An initial filter/count assertion caught that
distinction before reference qualification and was fixed.

Original semantic source remains [OpenAI GPT-2 model.py](https://github.com/openai/gpt-2/blob/9b63575ef42771a015060c964af2c3da4cf7c8ab/src/model.py).
`scripts/fetch_m4_model.py` verifies pinned Git blob IDs for small assets and
the upstream LFS SHA-256 for the large safetensors payload. It does not load
pickle, execute downloaded code, overwrite mismatched existing files, or use
an unpinned model revision. Original source text/license are also hash pinned.

Quality-data source: [Salesforce WikiText](https://huggingface.co/datasets/Salesforce/wikitext/tree/b08601e04326c79dfdd32d625aee71d232d685c3),
`wikitext-2-raw-v1`, revision `b08601e04326c79dfdd32d625aee71d232d685c3`,
CC-BY-SA-3.0/GFDL as recorded in its dataset card. Train, validation and test
parquet files are separately fetched/hash-checked; **no held-out model-quality
evaluation has run yet**. Sampling/quality thresholds are now frozen as below,
before the second candidate is evaluated or FPGA integration begins. No published benchmark perplexity is
being claimed for an unmeasured subset.

```bash
python3 -m venv --system-site-packages build/m4_venv
build/m4_venv/bin/python -m pip install -r scripts/requirements-m4-host.txt
python3 scripts/fetch_m4_model.py
python3 -m scripts.fetch_m4_data
build/m4_venv/bin/python -m tests.m4.qualify_float
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m unittest discover -s tests/m4 -v
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m tests.m4.explore_quantization
```

The isolated venv uses pre-existing Torch **2.11.0+cu130**, executed on CPU,
and NumPy 2.4.3; Transformers 4.57.1 is the separate eager-attention oracle.
Additional package versions are locked in `scripts/requirements-m4-host.txt`.
Four CPU threads are used for the model study. No GPU benchmark or new board
runtime dependency is inferred from these host references.

## Frozen generation fixtures and floating-reference evidence

`tests/m4/prompts.json` was written before model generation tests. Prompts:

1. `Once upon a time, in a small village near the mountains,`
2. `The purpose of a scientific experiment is to`
3. `A computer program can solve a problem by`

Batch one, greedy lowest-ID exact-tie break, exactly 20 new tokens. EOS 50256
is an ordinary selected token for this fixed-length test: continue without
resetting positions/cache until 20 tokens. No prompts were replaced after
observing agreement or disagreement. Input lengths are 13, 8 and 8 tokens.

`ref/gpt2_float.py` implements the equations independently with Torch CPU
primitives, without Transformers model internals: all layers, full heads,
learned embeddings/positions, cache, final LN and tied vocabulary projection.
`tests/m4/qualify_float.py` checks against a separately instantiated pinned
Transformers model using the exact checkpoint.

Results:

- All **3×20 floating-reference greedy tokens match** the oracle.
- Maximum prefill logit absolute errors: 0.0000610352, 0.0000762939,
  0.0000610352, below the predetermined 0.001 FP32 implementation tolerance.
- Incremental versus complete-prefill maximum logit errors: 0.000244141,
  0.000396729, 0.000381470; cache tensors pass their numerical comparisons.
- Final legal position 1023 passes oracle comparison; requesting position
  1024 is rejected. Full model context boundary is 1024 tokens.
- Eight fast/slow tokenizer comparisons and byte/text round trips pass,
  including Unicode, whitespace, empty text and EOS.

These are floating-reference correctness results, **not quantized quality or
physical inference acceptance**. Raw tokens/text and boundary error are saved
in `build/m4_float_qualification.json`.

## Integer candidate v1 — rejected model-quality diagnostic

`ref/gpt2_quantized.py` implements all model operations using exact M3 SFPU
equations, W8A8 dot products, explicit scales and int16 boundaries. Host
float64 BLAS accelerates integer GEMM only: every signed-int8 product/partial
sum for K<=3072 is exactly representable in binary64. It is not float32 fake
quantization. Unit tests compare full-range/maximal K=3072 products with int64,
signed RNE at all shifts, affine results and the unsigned-probability bridge
against the independent frozen operator references.

The quantized cache test is **exact**, including all cache tensors. K is
quantized per token; V per feature over only the causal prefix. Using future
V values to select a scale during prefill would change past outputs despite a
softmax mask, so that shortcut is explicitly avoided.

Actual checkpoint hazards, measured on the first frozen prompt:

- Nine final-LN gains exceed the representable M3 gain range; maximum
  **17.419317**. The diagnostic uses LN(gamma/4,0) then AFFINE(4,beta), rather
  than silently clipping the learned gain. The extra rounding is explicit.
- Floating residual outliers reach **3028.0969** before the last block; M3's
  fixed Q8 activation range is only [-128,127.99609375]. Final LN reaches
  magnitude **198.46997**. These are real checkpoint effects, not a GEMM
  accumulator overflow or a failure of M3's represented-input operator tests.
- The direct fixed-Q8 model clips projection/residual/final-LN/logit values.
  On the 13 diagnostic next-token positions, top-1 agreement with floating
  reference is **3/13 = 23.08%**, and maximum logit error is **89.092606**.
- Exact cached-decoding agreement passes for this same bad-quality candidate.
  This demonstrates why integer self-consistency cannot close G2.

`build/m4_quantization_v1_diagnostic.json` is explicitly
`DIAGNOSTIC_NOT_QUALIFIED`, with per-layer errors and clipping counts. It is
not a held-out benchmark, calibration set, numerical freeze or accepted model
pack, and it will not be used for M4 physical acceptance.

### Frozen quality policy and training-only calibration

`tests/m4/quality_policy.json` fixes the sample selection seed, independent
split roles, and hard limits before candidate v2 evaluation. Each held-out
context-length group and the token-weighted aggregate must satisfy:

- Perplexity ratio (quantized / float) <= 1.10.
- Teacher-forced top-1 agreement >= 85%; float top-1 in quantized top-5 >= 97%.
- Mean forward KL divergence <= 0.05 nats/token.
- No unintended residual clipping or nonfinite values.

The perplexity ratio limits average extra next-token loss to log(1.10) nats.
Ranking and distribution criteria catch different failure modes, without
demanding identical decisions at every near tie. These are project-specific
finite-sample limits, not full WikiText benchmark coverage. They must not be
relaxed in response to a held-out failure. Greedy float/quantized differences
are separately recorded; physical/quantized agreement must be exact.

Training calibration uses 32 windows of 256 predictions (8,192 total),
development uses eight validation windows of 256 (2,048), and final held-out
evaluation uses 16 test windows of 256 plus eight of 512 (8,192). Raw text rows
are joined with two newlines and tokenized with the pinned tokenizer. Seeded
selection without replacement from 513-token slots prevents overlapping
windows within a split. Window indices, tensor shapes and hashes are recorded
in `build/m4_quality_data/manifest.json`. Preparation does not evaluate a model.

`tests/m4/calibrate_channels.py` measures per-channel linear-input maxima and
residual ranges on **training windows only**. It does not use the frozen
generation prompts, development windows, or held-out test windows.

```bash
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m tests.m4.prepare_quality_data
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m tests.m4.calibrate_channels
```

### Scaled candidate v2 — development and cache evidence

[`M4_NUMERICS.md`](M4_NUMERICS.md) defines the explicit residual/logit exponents,
training-only channel balancing, LayerNorm epsilon compensation and score
centering. No M3 source, ABI or operator budget changed. Required A9 metadata
work is disclosed and must be timed; these equations are not yet physically
qualified compositions.

The alpha=0.5 candidate completed all eight validation windows (2,048
predictions): float perplexity **48.89257**, quantized **49.47771**, ratio
**1.011968**; top-1 agreement **89.6973%**, top-5 inclusion **100%**, mean
forward KL **0.0215716 nats**. No unintended clipping occurred. Deliberate
far-negative score clamps preserve exact zero probability beyond M3's LUT
cutoff and are separately counted. First-block centered logit/layer errors
and all counters are retained in `build/m4_v2_alpha05_dev8.json`.

`tests/m4/check_scaled_cache.py` tests 17 actual development tokens using
single-token, 7+5+5, and 16+1 chunkings: all logits and all twelve K/V caches
match full prefill **exactly**. Reset and five malformed/overlength input
checks pass. This is not yet the full 1024-position physical boundary test.
Ten M4 unit tests and all 24 M3 host regression tests pass.

Candidate sources, alpha, model/calibration/data identities and selection
evidence are frozen in `tests/m4/scaled_candidate.json` **before held-out
evaluation**. No alpha sweep was required. Development success does not itself
pass G2, and no M4 FPGA inference/performance is being claimed.

### Numerical rationale retained from v1 diagnosis

Explore a versioned **model-level** scale policy that preserves large residuals
in int16 storage with explicit power-of-two scale metadata, and balances
activation/weight channels before int8 conversion. The latter follows the
algebraic idea studied by [SmoothQuant](https://arxiv.org/abs/2211.10438v7):
`(x / s) @ (s * W)` preserves the unquantized linear function. This is a
candidate method, not an imported accuracy/speedup claim for GPT-2/PYNQ.

Any residual rescaling must account for LayerNorm epsilon: normalizing `x/c`
with unchanged epsilon is not exactly normalizing `x`. Derive/test explicit
correction or a versioned operator extension; do not silently rely on approximate
scale invariance. Quantization/calibration must use train/development data,
not tune on the acceptance prompts or held-out test. No M3 numerical limit,
RTL, ABI or quality gate has been relaxed. G2 remains open.

## Board resource inventory (read-only)

SSH key access to `xilinx@10.0.0.223` works. Board Linux 6.6.10, ARMv7,
reported RAM 491 MiB, available RAM about 387 MiB, swap 511 MiB (21 MiB used),
19 GiB free on the root filesystem. CMA total 131072 KiB, free 16988 KiB at
inventory time. These are live availability observations, not reserved memory.
Do not clear another process's buffers or assume 1 GiB board RAM. The M4
runtime must fit bounded buffers and avoid swapping during reported timings.
No board reprogramming or global settings change was made in this work.

## Evidence hashes

| Evidence | SHA-256 |
|---|---|
| `tests/m4/prompts.json` | `0886333492f4ff907845c7ba6aed6c914b5b7c1e5cc0595bc4665b860eb7a90c` |
| `build/m4_model/model.safetensors` | `248dfc3911869ec493c76e65bf2fcf7f615828b0254c12b473182f0f81d3a707` |
| `build/m4_model/model_manifest.json` | `01b56d06d25a66e3e431961906bab5bf1dcb5eb968b3d54f272478ea8a0a2fdf` |
| `build/m4_data/data_manifest.json` | `6ae574f0385d700e4fdfa76b1ed2b798233d5da4a6dab3116e068d936b8c88bb` |
| `build/m4_float_qualification.json` | `095ad37bbb38aea4ef5e9baf3fc7e1289648423d16b649aaa547a0aef685d0b5` |
| `build/m4_float_qualification.log` | `6b46da7626bf5b1f896255c21bc00c52d80f9fda8784ab8b7da47470d226cd68` |
| `build/m4_quantization_v1_diagnostic.json` | `366ac6d49b4685f1a8c94573d3eb9fe31c2f8a518ba629b17d91af2a8ac84a33` |
| `build/m4_quantization_v1_diagnostic.log` | `a58125da48eaf70aa909094b5d035ff4d4782320e0600f8607bbce8eacd30fe4` |

All M4 model/board/quality/performance closure gates remain mandatory. No M4
PASS, full-model speedup or tokens/s is claimed here.
