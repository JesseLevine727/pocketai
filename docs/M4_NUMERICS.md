# M4 model arithmetic — scaled v2, host quality PASS / physical checks pending

This is a **model-level representation**, composed from unchanged M3 v1
operators. It is not a change to `ref/sfpu_ref.py`, M3's packet ABI, its error
budgets, clock, or accepted overlay. Candidate implementation:
`ref/gpt2_scaled.py`. M4 quality limits were committed in `12f5386` before this
candidate was evaluated. The direct fixed-Q8 v1 failure remains preserved.

## Representations and boundaries

- Persistent activation payloads remain int16. Most tensors have logical
  value `raw / 256`. Residuals and final logits additionally carry a per-row
  exponent `e >= 0`, with logical value `raw * 2^e / 256`.
- GEMM inputs and weights are int8; reductions are exact signed int32 with
  K<=3072. No W8A16 or floating-point fabric is substituted.
- QKV and cached K/V remain Q8. K quantization uses a separate scale for each
  token; V quantization uses each feature over **only the causal prefix**.
  Future tokens cannot select the scale for an earlier output.
- Softmax remains M3's unsigned Q0.15, including positive 32768. The dynamic
  W8A8 bridge uses unsigned probabilities without signed reinterpretation.
- Embeddings, learned positions and biases come from the same pinned model.
  Final projection derives from the tied embedding weights, with a different
  quantized view after channel balancing; there are no newly trained or
  independently untied output weights.

The host study keeps int8 codes expanded to float64 for BLAS speed. This
represents all bounded integer dot-product sums exactly, as separately tested.
It is **not** a board memory layout or an acceptable 1-GiB A9 allocation.
The physical runtime must use bounded native int8 weights and scratch buffers.

## Channel balancing

For a linear input channel, choose positive `s` and replace the unquantized
linear function by `(x/s) @ (s*W)`. Train-only per-channel absolute maxima `a`
and weight-row maxima `w` give `s = a^alpha / w^(1-alpha)`, with nonzero floors.
The first development candidate uses **alpha=0.5**. A common scalar normalizes
the largest calibrated balanced activation to at most 64 and, for folded LN,
the largest gain magnitude to at most 7.5. This uses int16/gain resolution
without changing relative channel balancing. Out-of-calibration clipping is
still counted; the calibration bound is not presumed universal.

LN-to-QKV, LN-to-MLP-up and final-LN-to-vocabulary fold `gamma/s, beta/s`
into LN and `s*W` into the following weights. Attention-context and post-GELU
balancing require an explicit per-channel M3 AFFINE before requantization.
Scales are **not moved through GELU or softmax**. Weight quantization remains
symmetric, per output channel. The algebra is the idea studied by
[SmoothQuant](https://arxiv.org/abs/2211.10438v7); its published speed/quality
results are not evidence for this GPT-2/PYNQ implementation.

## Residual ranges and LayerNorm epsilon

A9 examines wide GEMM sums and their scale metadata before narrowing. The
smallest nonnegative exponent that gives at most 32700 raw magnitude is used.
For a residual addition, range selection bounds `abs(old) + abs(branch)` so
both addends and their sum fit. M3 AFFINE aligns the old residual and projects
the branch into the chosen units, followed by M3 ADD. Bias rounding and each
alignment/narrowing boundary are explicit. The headroom covers ordinary
rounding; saturation counters remain mandatory. Logits use one common exponent
across **all 50,257 vocabulary entries in each row**, not incomparable tile
scales. Wide scratch is temporary, not persistent activation storage.

Scaled LayerNorm cannot just ignore epsilon. Let `z=raw/256`, `c=2^e` and
`x=c*z`. M3 normalizes `z` with epsilon=1e-5. A9 multiplies the learned gain by

`sqrt((var(z)+epsilon) / (var(z)+epsilon/c^2))`.

This restores the desired epsilon algebra for the represented `x` before gain
quantization. The variance numerator `L*sum(raw^2)-sum(raw)^2` is computed in
integer arithmetic, avoiding subtractive floating-point cancellation. Constant
and near-constant vectors are tested. The gain is then rounded to M3 Q12.
If it exceeds the gain range, an explicit power-of-two decomposition performs
LN(gamma/factor,0), then AFFINE(factor,beta); its extra rounding is part of this
candidate. Otherwise M3's single rounding, **bias then saturation** is retained.
The fixed M3 integer square-root/epsilon rounding remains unchanged; model
quality must absorb the declared metadata/gain quantization, not hide it.

This introduces A9 variance/square-root/scale bookkeeping. It is a disclosed
hybrid assistance cost, not autonomous RISC-V inference or free computation.
Required metadata work belongs inside end-to-end inference measurements.

## Attention score centering

Rounded wide QK scores can exceed signed Q8 even when their relevant
differences are small. Before AFFINE saturation, A9 selects a common bias equal
to the negative maximum rounded raw score. This makes the maximum zero without
changing any score difference. AFFINE then saturates only far negative tails.
Such tails have differences above 32768 raw, already beyond M3's exact
4096-raw exponential cutoff; their represented probability was zero anyway.
These **intentional zero-tail clamps** are counted separately from unintended
clipping. Positive-score saturation before centering is not allowed.

## Acceptance status and remaining physical checks

Unit tests establish scaling algebra, exact M3 affine/LN behavior, range
selection and zero-tail equivalence. Real-checkpoint cached/full-prefill and
independent float comparisons pass as recorded in `M4_VERIFICATION.md`, including
8,192 held-out predictions and all 60 generated cache/recomputation steps. The
source/calibration policy was frozen before held-out testing; thresholds were
not tuned. The compact model-pack serialization is verified. Every affected
composition still requires physical-board equivalence on the accepted overlay;
host equations alone do not prove delivered hardware behavior or performance.
