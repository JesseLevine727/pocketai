# M4 verification — IN PROGRESS / NOT QUALIFIED

M3 is closed/pushed at `68da8f8`. M4 implementation began 2026-09-05 after goal
initialization. No RTL, accepted overlay or M1–M3 numerical contract has changed.
The board is now running the exact accepted M3 overlay for M4 runtime tests.
M5/M6 remain unstarted. Full acceptance is in
[`M4_PLAN.md`](M4_PLAN.md).

## Current gates

- G0 plan/status: recorded.
- G1: checkpoint/tokenizer pinned; independent floating-model equations pass
  oracle/cached/generation tests. Scaled integer reference passes exact cached
  generation, including exact 1024-position integer cache/boundary behavior.
- G2: **host model-quality PASS** for frozen adaptive v3. Every held-out
  context-length group and aggregate passes the precommitted limits. The failed
  direct fixed-Q8 and long-context v2 failures remain preserved below. The
  explicit v3 range correction also passes 1024-token stress without clipping.
  Physical qualification of the versioned compositions is required in G4/G5.
- G3: bounded A9 scheduler, native CPU and FPGA packet backends implemented.
  Host exact model/cache tests and physical CPU/FPGA 3×20 generation pass. Full-
  context physical execution/peak-memory qualification remains.
- G4/G5: complete FPGA acceptance passes four cases x99 tensor/logit boundaries
  and all three 20-token generation/logit/KV sequences. The initial single-token
  case additionally passes 1,569 actual-operand native operator cross-checks.
  DMA timeout/recovery, busy routes, clean local/ISA and physical M1/M2/M3/M1
  regressions pass. G4's progressive tensor/regression checks pass; physical
  1024-position qualification still keeps G3/G5 open.
- G6: sampling policy frozen in `546d6f0` before timing. The complete resident
  benchmark passes all 794 raw observations and the independent inventory/
  source/profile audit. FPGA full-generation median is 433.008 s versus
  113.483 s CPU for prefill plus 20 tokens (0.04619 vs 0.17624 tokens/s).
  Full statistics, measured bridge improvements and slowdowns are recorded in
  `SPEEDUP.md`. Supplemental fresh-process observation is still pending.
- G7 remains open. Partial runtime results do not close M4.

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
parquet files are separately fetched/hash-checked. Sampling/quality thresholds
were committed in `12f5386` before v2 evaluation; the selected candidate was
committed in `17b1b98` before held-out evaluation. Held-out results below use
the exact frozen subset, not a claim of complete published WikiText benchmark
coverage. No quality threshold or test selection was changed after results.

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
pass G2 by itself. The subsequent held-out gate is recorded next; no M4 FPGA
inference/performance is being claimed.

### Frozen held-out quality — PASS

`tests/m4/qualify_scaled_quality.py` verifies all frozen sources, checkpoint,
calibration, data, selection evidence and host library versions before running.
It refuses to overwrite evidence. Each group and the aggregate pass **every**
precommitted distribution limit:

| Context predictions/window | Predictions | Float PPL | Quantized PPL | PPL ratio | Top-1 agreement | Top-5 inclusion | Mean KL, nats |
|---|---:|---:|---:|---:|---:|---:|---:|
| 256 | 4096 | 41.41489 | 42.07706 | 1.015989 | 89.6973% | 99.9023% | 0.0214778 |
| 512 | 4096 | 39.33692 | 39.99329 | 1.016686 | 89.0381% | 99.7803% | 0.0226370 |
| Token-weighted aggregate | 8192 | 40.36254 | 41.02195 | 1.016337 | 89.3677% | 99.8413% | 0.0220574 |

No unintended weight/activation/residual clipping, nonfinite values or
unrepresentable nonzero affine scales occurred. Centered logit RMSE is
0.403772; maximum centered error is 17.2197, so low average loss does **not**
mean every vocabulary logit is close. First-window layer errors in both
context groups, all per-window metrics, exponents, tail clamps and range
counters are retained in `build/m4_v2_heldout_quality.json`.

### Frozen generation — exact reference cache checks, not float token identity

All three original prompts produce exactly 20 new tokens. For **all 60 steps**,
cached decode and full recomputation on the same generated prefix have exact
logits and all twelve K/V tensors. No unintended clipping occurs. The output
texts/tokens/logit hashes are in `build/m4_v2_generation.json`.

Greedy quantized text differs from float at new-token indices 1, 2 and 0
(zero-based) for story, science and computing respectively. These differences
are disclosed, not repaired by replacing prompts. Once generation diverges,
later same-position matches are not a teacher-forced accuracy metric. The
frozen quality policy never required universal float token identity.

For example, the computing prompt continues in the quantized model:
`analyzing the data and then performing a series of calculations to determine
the correct answer.` The float continuation begins `solving a problem.` Neither
selective text inspection nor integer self-agreement replaces the held-out
distribution gate above. Physical hardware must still match the **frozen
quantized** outputs, not substitute either text as a new golden.

### V2 1024-position stress — exact cache PASS, range check FAIL (preserved)

`tests/m4/check_scaled_boundary.py` concatenates four existing 256-token
**development** windows for a functional stress, not an additional held-out
quality sample. Full 1024-token prefill matches chunked 512+511+1 execution
exactly in final logits and every K/V tensor. Position 1024 is rejected without
mutating the cache.

However, the range audit finds **6 attention-context balancing clips and 594
post-GELU balancing clips**, counting both schedules, in block 0. These are
out-of-calibration **balancing** ranges, not residual clipping or cache failure.
`build/m4_v2_context_boundary.json` is correctly **FAIL_UNINTENDED_CLIPPING**.
The 8,192-prediction held-out result remains valid; it does not qualify this
long-context stress. Next: add an explicit range-safe balanced-input exponent
and carry its units into GEMM scale metadata. Preserve v2, thresholds, failed
evidence and weight calibration; independently requalify any revised candidate.

### Adaptive v3 — reference/model-quality gates PASS

`ref/gpt2_adaptive.py` preserves v2 and adds only an explicit balanced-input
exponent when the prospective affine result would overflow. It carries that
unit into the next W8A8 GEMM. Weights, calibration, thresholds, prompts and
dataset selection remain unchanged. Required range scans are A9 metadata
costs, not free excluded work. Details: `M4_NUMERICS.md`.

On all eight development windows, v3 matches **every v2 logit and K/V tensor
exactly** (2,048 predictions). On the same 1024-token development stress that
failed v2, full prefill and 512+511+1 chunks now match exactly **with zero
unintended clipping**. Position overflow is rejected without mutation.
The correction is based on this development failure, not held-out tuning.

V3 was source/evidence-frozen in `8a8bec3` before held-out requalification.
V2's held-out results were already known: this is a transparent functional
revision, **not a fresh blind benchmark**. The repeated 8,192-prediction gate
passes with exactly the same per-group/per-window metrics and layer errors
as the v2 table above. All three 20-token generations and per-step logit hashes
are also unchanged; all 60 cached/recomputed comparisons still pass. All 248
packed arrays are byte-identical. `tests/m4/check_v3_preservation.py` audits
these equality claims, separately from the changed long-context stress.

Current freeze: `tests/m4/adaptive_candidate.json`; pack:
`build/m4_pack_v3`. **G1 and host G2 pass.** This is the numerical/runtime
handoff, not physical M4 closure. Versioned compositions still require exact
FPGA equivalence, full prompt/board acceptance and real system timing.

```bash
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m tests.m4.evaluate_adaptive_development
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m tests.m4.qualify_scaled_quality --adaptive-v3
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m tests.m4.qualify_scaled_generation --adaptive-v3
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m scripts.export_m4_pack --adaptive-v3
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m tests.m4.check_v3_preservation
```

### Compact model pack and host regressions

`scripts/export_m4_pack.py` exports 248 hash-checked mmap arrays containing all
49 linears and 25 normalizations. Every weight byte and metadata element is
compared after serialization/reload. Payload is **205,271,824 bytes (195.7625
MiB)**; no float64-expanded weights are required on A9. Full-context int16 KV
storage is another 36 MiB. These are allocation budgets, not measured physical
peak memory. [`M4_RUNTIME.md`](M4_RUNTIME.md) records layout, hashes and remaining
runtime work. Seventeen M4 unit tests and all 24 M3 host regressions pass.
Native GEMM passes 20 independent host and physical A9 cases; native SFPU
passes 140 adversarial cases plus all 3,472 accepted M3 packets on both host
and A9. Host undefined-behavior sanitizer replay also passes the 3,472 packets.
These CPU backend checks are not new FPGA tests or inference benchmarks.

```bash
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m tests.m4.qualify_scaled_quality
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m tests.m4.qualify_scaled_generation
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m tests.m4.check_scaled_boundary
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m scripts.export_m4_pack
```

### Numerical rationale retained from v1 diagnosis

The v2 design implements a versioned **model-level** scale policy that preserves large residuals
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
RTL, ABI or quality gate has been relaxed. Adaptive v3 closes the host
long-context balancing range issue. Physical qualification of these
compositions remains mandatory in G4/G5.

## Board resource inventory (read-only)

SSH key access to `xilinx@10.0.0.223` works. Board Linux 6.6.10, ARMv7,
reported RAM 491 MiB, available RAM about 387 MiB, swap 511 MiB (21 MiB used),
19 GiB free on the root filesystem. CMA total 131072 KiB, free 16988 KiB at
inventory time. These are live availability observations, not reserved memory.
Do not clear another process's buffers or assume 1 GiB board RAM. The M4
runtime must fit bounded buffers and avoid swapping during reported timings.
The inventory itself did not reprogram hardware. Subsequent runtime checks
load the unchanged accepted M3 overlay; no board-global settings were changed.

## Bounded runtime and initial physical model evidence

`zynq/m4_offload.py` is independent of the frozen full-model references. It
uses the compact int8 pack, native/FPGA packet backends, bounded blocks of at
most 16 tokens, all 12 layers/heads and all 50,257 output logits. The fixed
cache allocation including derived K8 and scale metadata is 48,365,568 bytes;
FPGA TX/RX use 110,592 CMA bytes. See `M4_RUNTIME.md` for numerical and lifecycle
details. There is no host floating GEMM fallback.

The exact dynamic bridge batches per-column REQUANT8 through equivalent
per-lane AFFINE when it reduces packet count. Exhaustive represented-range
tests and the frozen full-model checks pass, without changing v3 reference,
pack or output hashes. Native host qualification passes 196 tensor boundaries
across prefill/cached blocks, logits/all KV and 60 generated tokens. Current
M4 unit tests: **44 PASS** (including seven benchmark, three evidence-audit,
three performance-analysis, three deployment-preflight and four startup-probe tests); M3 host tests:
**24 PASS**. Controlled physical before/after measurements are still required
before claiming a speedup from this batching.

Correctness bundle `build/m4_runtime_stage.l3_ox1tq` has manifest SHA-256
`99897c20ad4c7cfa1a47507a94b34c1f0a72c85091435f7628ef54916e307fe7`;
remote owned directory `/home/xilinx/pocketai_m4_runtime.LrxYKW`. Every staged
file is verified before execution. Model pack and M3 bit/HWH remain pinned.

- `build/m4_driver_board_control.json`: both busy-route directions, rejected
  descriptor, real missing-producer DMA timeout, failed-transfer buffer
  protection, reset/restart and wide K=3072/N=13 GEMM after recovery pass.
- `build/m4_runtime_fpga_single.json`: 99 exact tensor/logit boundaries and
  full KV hash, 1,569 independent native checks on actual FPGA operator
  operands/results. This is a real complete model forward pass, not a reduced
  vocabulary or single-layer fixture. Peak RSS 199,056 KiB, process swap zero.
- `build/m4_runtime_cpu_batched.json`: all four tensor/logit/KV cases and all
  three 20-token generation sequences pass on the physical native A9 CPU.
  Peak RSS 156,912 KiB; final PSS 148,871 KiB; one thread, process swap zero.
- `build/m4_runtime_fpga_acceptance.json`: all four cases x99 tensors/logits,
  all three x20 generated tokens, per-step logits and complete KV hashes pass.
  Peak RSS 202,800 KiB; final PSS 184,723 KiB; process swap zero. Both backends
  reused/reset the same runtime across the frozen prompts.
- `build/m4_runtime_host_boundary.json`: host-native runtime exact final
  logits/all KV through 1024 positions in 64 blocks of 16; overflow rejected
  without cache mutation. Physical CPU/FPGA boundary tests remain required.

Diagnostic elapsed times include validation and **are not performance**.
No 1024-context memory claim is inferred from the short-prompt RSS above.
The old intentionally interrupted scalar-bridge run is preserved and is not
a completed generation PASS; details are in `M4_RUNTIME.md`.

The following full texts are decoded on the host from the exact token IDs
accepted on both physical backends. They are illustrative fixed-20-token
continuations, not an additional quality metric or board tokenizer benchmark:

```text
Once upon a time, in a small village near the mountains, a man named Nana was a young man who had been living in the village for a few years

The purpose of a scientific experiment is to determine whether the effects of a given chemical are due to the chemical's effect on the organism. The

A computer program can solve a problem by analyzing the data and then performing a series of calculations to determine the correct answer.

The computer
```

The frozen floating-model generations differ, beginning at zero-based generated
token indices 1, 2 and 0 respectively. Exact agreement is required with the
independent **quantized** reference, not universal floating greedy identity.
`build/m4_v3_generation.json` retains both versions and every token/logit hash.

`tests/m4/performance_policy.json` SHA-256
`17bcd0a823f551c539525fc54c0f51e759a306f9c346e968de06523b8380d8cf`
was committed in `546d6f0` before any benchmark timing. The paired native
CPU/FPGA runner includes required runtime work, excludes validation, and
reports disjoint wall spans separately from overlapping hardware counters.
See `SPEEDUP.md` for exact sampling and token-ID delivery boundaries.

### Complete local and physical compatibility regressions

`build/m4_complete_local_regression.log` preserves the clean-build transcript:
1007 wide/mixed and 1007 legacy GEMMs; 82 wide lifecycle interruptions; 15120
ALU checks plus 336 reset/abort phases; 3472 SFPU vectors plus 682 lifecycle
checkpoints; all 315 cluster-chain steps; M1/M2 local/lint, M3 lint; **84 ISA
passes and exactly the four previously documented expected failures**. Frozen
M3 numerical budgets pass again with 10,000 random cases per vector operation
in `build/m4_m3_numerics_regression.json`. Existing deprecation/duplicate-target
tool warnings remain reviewed M3 warnings, not new failures. Generated SFPU
corpus bytes remain identical to the accepted corpus.

Physical rerun uses the immutable M3 stage copied to fresh owned directory
`/home/xilinx/pocketai_m4_regress.Lqg9RA`, preserving all accepted M3 outputs.
`build/m4_m1_m2_m3_m1_board_tty.log` and
`build/m4_m3_board_regression.json` record M1→M2→M3→M1 PASS, all 1007 mixed
GEMMs, all 3472 SFPU cases, lifecycle controls and the M3 chains. Bit/HWH and
95-MHz fabric are exact. The adjacent board clock inventory reports CPU
650 MHz and FCLK0 100 MHz feeding the 95-MHz fabric clock; cpufreq governor
sysfs is unavailable, so no governor setting is asserted. Python 3.10.4,
NumPy 1.21.5, PYNQ 3.1.1 and board GCC 11.2.0 remain unchanged.

An initial compatibility SSH launch lacked a writable host PTY and remained
at sudo authentication; no tests/programming ran in that attempt. Its scoped
SSH process was terminated, completion checked, and prompt-only log preserved
as `build/m4_m1_m2_m3_m1_board.log`. The successful rerun above has a distinct
log and interactive PTY. No credential is stored in either log.

### Closure audit, not premature closure

`scripts/audit_m4.py` verifies immutable identities, current-source versus
physical evidence, every mandatory generation/tensor/context result, memory,
unchanged hardware/regressions, and the complete benchmark sample inventory.
It rejects dropped/duplicate samples, overlapping profile sums, missing DMA
bytes and CPU/FPGA arithmetic-workload mismatches. Its own tests use clearly
synthetic records solely to test rejection; those are never board evidence.

```bash
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m scripts.audit_m4 --allow-incomplete --output build/m4_evidence_preflight_v3.json
```

That earlier v3 preflight reports seven checks PASS and three PENDING: physical CPU full
context, physical FPGA full context, and completed fair performance. An initial
audit schema assertion incorrectly expected integer zero instead of the frozen
empty clipping dictionary; that audit-only assertion was corrected/tested.
The underlying quality evidence and thresholds never changed. Even a complete
machine audit still requires G7 documentation/limitations review and a scoped
closure commit. The goal remains active; no M4 closure or extra push is claimed.

The closure review additionally tightened deployment provenance: the initial
stager pinned the pack/overlay but did not itself rehash every actual original
model/tokenizer asset or cross-check each tensor file against its independent
manifest. The new read-only `scripts/verify_m4_deployment.py` performs those
checks and is now part of staging and the closure audit. All ten model assets,
248 arrays and 396 tensor files pass; receipt is
`build/m4_deployment_preflight.json`. The new staging helper includes the model
license and small identity/tokenizer assets in future bundles. Existing physical
evidence retains its original bundle identities; this host-side strengthening
does not change the accepted arithmetic, prompts, weights, reference outputs
or running board job. See `M4_RUNTIME.md` for the later host-only bundle.

The main benchmark is now terminal: all twenty fixed-workload paired trials,
all six full 20-token chains and all primitive/bridge comparisons pass exact
post-clock checks. Its 794-observation inventory, CPU/FPGA arithmetic counts,
source hashes and non-overlapping wall profiles pass the reproducible analyzer.
`build/m4_benchmark_board.json` and `build/m4_performance_analysis.json` preserve
raw and derived evidence. `SPEEDUP.md` reports latency/throughput distributions,
every full-chain trial, operation/byte counts, memory, initialization components
and controlled batching improvements. FPGA is 3.816x slower for complete
generation; the unchanged acceptance contract requires honest measurement,
not an assumed speedup. Physical context checks remain in progress.

The updated `build/m4_evidence_preflight_v7.json` reports **eight PASS and
three PENDING**, with no failures. Remaining machine checks are physical CPU
full context, physical FPGA full context and the supplemental fresh-process
observation. G7 documentation/closure review remains separate.

A final timing-boundary review distinguished initialization components measured
inside Python from a complete fresh-interpreter first-token observation.
`tests/m4/cold_start_policy.json` was frozen in `61a08b1` before supplemental
timing: one descriptive process-cold observation per backend, not a cold
distribution or speedup claim. The standalone `zynq/m4_cold_start.py` includes
process/module/library startup and waits for a parent delivery acknowledgement
before any reference checking. It refuses to begin before the main benchmark
and both physical context runs pass, and uses graceful-only abort for a possible
DMA-owning child. Four local protocol/timeout/precondition tests pass; physical
startup observations remain pending. This supplements the original warm
benchmark; its sampling, data, timings and policy are unchanged.

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
| `tests/m4/quality_policy.json` | `97ba47854881a10646be03aee30a194e0b14a3efb1632c558b7b44f6ed6f97f0` |
| `tests/m4/scaled_candidate.json` | `ffebd8cd032bfcc92fb248c596a70082e15b3e7f858b15d8ff90eb1a2637b3ee` |
| `build/m4_v2_heldout_quality.json` | `0ff3d639dcb2e6ec4432ed805fa8679115f58d8fa3ba2ff7eca16124b54cb6af` |
| `build/m4_v2_heldout_quality.log` | `36fb8f30c842bb61a8541bea4b44c568373e24810dd509bf1df74f5eb345bd0a` |
| `build/m4_v2_generation.json` | `0904ebee52d2a9b9b61b10427c26f40bd904b5b213e4bfec45e03a2a503525f4` |
| `build/m4_v2_generation.log` | `1e957bbbc71fa7d69721eb2f47fdf1f972cc515a1cc14c9cd8542de5cc476dfd` |
| `build/m4_pack_v2/manifest.json` | `87ca19ae6557d071db4a79664bd7ced53dbef78b62ad936f065b063be4e004a8` |
| `build/m4_v2_context_boundary.json` | `ba8e82e8dfe9b6ce0d70cbe0c60f4f3e9cb5e2acff9d0312c03350d861dcf170` |
| `build/m4_v2_context_boundary.log` | `40e7ce06c7105c5c30d2f927e81d83e0233917a3886d80818c0cc9e6dc3813fd` |
| `tests/m4/adaptive_candidate.json` | `a8d80d03c1aacc8a40f0f84962acd4033f0a1afb1343fd9e1ab0e9c50d0c397d` |
| `build/m4_v3_development.json` | `f71bf0ca59d3b9e63c30358423ee8882c5bb7935e53a55e2f1db91be9bef831b` |
| `build/m4_v3_heldout_quality.json` | `ee4bc98220d0a2c3e0ab5a92f4615bf859188c0d93af3467ea2f0587ce3eaf81` |
| `build/m4_v3_heldout_quality.log` | `36fb8f30c842bb61a8541bea4b44c568373e24810dd509bf1df74f5eb345bd0a` |
| `build/m4_v3_generation.json` | `188c2b6e790ce214ba05e629da94ff74105e388f1859af52b262f4420cb6c1b7` |
| `build/m4_v3_generation.log` | `1e957bbbc71fa7d69721eb2f47fdf1f972cc515a1cc14c9cd8542de5cc476dfd` |
| `build/m4_pack_v3/manifest.json` | `d2aafeffd3e4b8a134b8e48796a1b0cf8f296a3bd150b79f07e2de037fae8fd6` |
| `build/m4_cpu_gemm_arm.json` | `b5b1bec44d945f1db4fc535ccc4e2f58a6e6f8ef8d5fc34afe8c7057885756eb` |
| `build/m4_cpu_sfpu_arm_m3vectors.json` | `d66b7511fd697da8b7a4b537a9b16dd130fa334325cfe4eca8ec01e82827396b` |
| `build/m4_driver_board_control.json` | `ef0c9975a73c9eba90654b293b8e5c5e6ff6ec60e0accdf791fa1e8489736794` |
| `build/m4_runtime_fpga_single.json` | `058ca8d2c3f857266a40cf0dcdf38932d22f475e479f52f427b285a704d406fe` |
| `build/m4_runtime_cpu_batched.json` | `574b32c04ca7960f02c065043aeb0fcb8c26d27701b0d40de178373158981d62` |
| `build/m4_runtime_fpga_acceptance.json` | `b08a540bd5adcbcc70dfac693841e12422b6af1b2363c85d273da51e112f0e2c` |
| `build/m4_runtime_host_boundary.json` | `878cde00ae03aba97e3721692c458aa41e08997f4e2f8c22868ff6d7d798d668` |
| `build/m4_complete_local_regression.log` | `e275d1e1a090b0af3eef9d11f2a2615f57df4976eb72808522a13839fcd83799` |
| `build/m4_m3_numerics_regression.json` | `f1d6be4390681ee94ccda6d3af3e3dc23156454ce8859654baf4d55721ff4516` |
| `build/m4_m3_board_regression.json` | `2f1c4dea9649d822189dfdc557fcac36527e7338d8775c49fc6a38f915cc7852` |
| `build/m4_m1_m2_m3_m1_board_tty.log` | `a24bcf1b6beacc2f6cbefe83e846223a07d211f3218929e2e2cb937dad69659a` |
| `build/m4_final_host_tests.log` | `9cdba776484ebc345aac5ea84f48798310320ea4bb4b6220713df9275db6aed7` |
| `build/m4_evidence_preflight_v3.json` | `5fb75d2c157ee062cd9e13090bfaa61eca247cbc610026dae0ea31355cb5d88e` |
| `build/m4_analysis_host_tests.log` | `8fccac7fb240325f5d2e0e30ca8101945bc5077dcf69cfd8e12b1c8928e76638` |
| `build/m4_deployment_preflight.json` | `5139aef28f2c0613f8367bfe7d40e68c90f101b1faea162ddccfa1c005f31cf9` |
| `build/m4_deployment_host_tests.log` | `7402ec1fb581e67b2730a59fb1f8d51e2c1005b5bc5e8df8c5dbf8ba65bebf02` |
| `tests/m4/cold_start_policy.json` | `d8a013a8e317039c4a928f724ad0033ca677cf658e5422438886be12f6080b7d` |
| `build/m4_cold_isolated_host_tests.log` | `9761cf3f097b8d4d39f42a9686997b9936a461883f47a1990bcb692c68169926` |
| `build/m4_benchmark_board.json` | `b839f78c9ac2010c04d97c254e52656d83faca4196311ca9231914a0db271dd0` |
| `build/m4_performance_analysis.json` | `d77d21ead5de368aec60a1086fbec0fc675ec4579537fcf7101f66e5561a1741` |
| `build/m4_evidence_preflight_v7.json` | `9d3ccd8380969d05b32fdab8cdb4ef10d401e354707f0b21f8f4954b56df9f0e` |

All M4 closure gates remain mandatory. Full-model throughput above is measured;
it is a slowdown, not a speedup. Pending physical context/startup evidence and
G7 review still prevent M4 closure.
