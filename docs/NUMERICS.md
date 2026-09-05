# PocketAI-T numerical contracts

This document is the hardware/software numerical contract. RTL, firmware,
Python references, simulation vectors, and board tests must agree with it
exactly. A milestone may extend this file only before implementing the affected
datapath.

## M2 GEMM

For one descriptor, the accelerator computes

`C[M,N] = sat16(A[M,K] x B[K,N])`.

- `A` and `B` elements are two's-complement signed int8 (`-128..127`).
- Every product is an exact signed 8x8 multiplication yielding signed int16.
- Products accumulate in signed 25-bit registers. This covers the maximum M2
  dot-product magnitude, `768 * 128 * 128 = 12,582,912`, within the signed
  25-bit range `-16,777,216..16,777,215`.
- No saturation, truncation, wrapping, or rounding occurs between products.
- After the complete K-term dot product, the result saturates once to signed
  int16: values below `-32768` become `-32768`; values above `32767` become
  `32767`.
- There is no scaling, zero point, bias, rounding, or unsigned mode in M2.
- Legal dimensions are `1 <= M <= 16`, `1 <= N <= 16`, and
  `1 <= K <= 768`. All descriptor flag bits are reserved and must be zero.
- Partial M and N values compute only active output elements. Padded input bytes
  are ignored and padded output lanes are exactly zero.

The authoritative executable definition is `ref/gemm_ref.py`, which promotes
both inputs to signed int64 for the NumPy matrix product and then clips once to
int16. The extra software width prevents NumPy dtype behavior from silently
changing the hardware contract.

## M2 stream representation

All stream words are 32-bit and all four byte lanes are valid. Byte and halfword
lanes are little-endian within each word.

An input packet contains A followed immediately by B:

1. A is signed-int8 row-major. Each of its M rows is independently padded with
   zero bytes to a 32-bit boundary. Its length is `M * ceil(K/4)` words.
2. B is signed-int8 row-major. Every one of its K rows occupies exactly four
   words (16 columns); columns `N..15` are zero padding. Its length is `4*K`
   words.
3. AXI Stream `TLAST` is asserted only on the final B word. `TKEEP` is `0xf`
   on every word.

The total input length is `M*ceil(K/4) + 4*K` words.

An output packet contains C in signed-int16 row-major form. Every active row
occupies eight words (16 columns); columns `N..15` are zero. The low halfword is
the earlier column. `TLAST` is asserted only on the final word. The total output
length is `8*M` words.

Saturation is part of the compute operation. Packing and unpacking never alter
active numerical values.

## M3 v1 — frozen before arithmetic RTL

Frozen 2026-09-04 local time. This extends, **not replaces**, M2's contract.
Executable references: `ref/sfpu_ref.py` and `ref/gemm_v3_ref.py`. Stream/register
encoding and lifecycle are specified in `docs/M3_ARCHITECTURE.md`. A numerical
change requires a documented versioned rationale and complete requalification;
never silently relax an error budget. M3 hardware is qualified against this v1
contract; evidence and limitations are in `M3_VERIFICATION.md`.

### GPT-2 reference and shapes

Semantic reference: OpenAI GPT-2
[`src/model.py` at `9b63575ef42771a015060c964af2c3da4cf7c8ab`](https://github.com/openai/gpt-2/blob/9b63575ef42771a015060c964af2c3da4cf7c8ab/src/model.py).
Target configuration: 12 layers, hidden width 768, 12 attention heads of width
64, maximum context 1024, learned token and absolute position embeddings.
Blocks use pre-LayerNorm, scaled causal attention and a 768→3072→768 MLP with
the tanh-approximate GELU. There is no RMSNorm, SiLU or RoPE operator.

This is an operator-contract milestone, not full-model inference. No checkpoint
was used to select empirical activation ranges or claim model accuracy. M4 must
pin the actual checkpoint, tokenizer and calibration/prompt data and validate
model-level accuracy; M3's represented-input accuracy does not prove that.

Shapes: GEMM M,N=1..16, wide K=1..3072; softmax length 1..1024; LayerNorm,
GELU, affine, requantization and addition length 1..3072. LayerNorm normally
reduces 768 features. Long tensors are explicitly tiled by software, with wide
results preserved until the complete reduction. GPT-2's original projection
weights are logically `[input,output]`; packers must transpose any checkpoint
layout that differs. A 3072-column output uses 192 N-tiles. Attention QK^T uses
K=64 and the explicit 1/sqrt(64)=1/8 scale **before** masking/softmax. AV can
reduce up to 1024 positions and therefore also needs the extended GEMM path.

### Representations and rounding

| Value | Storage / represented real value |
|---|---|
| General activation, residual, embedding, bias | signed int16 / 256, range [-128,127.99609375] |
| LayerNorm gain | signed int16 / 4096, range [-8,7.999755859375] |
| Softmax score (after attention scaling) | signed int16 / 256 |
| Softmax probability | **unsigned** uint16 / 32768, range [0,1], including raw 32768 |
| GEMM operands | signed int8; real scales are explicit software metadata |
| Wide GEMM output | signed int32 containing an exact signed-27-bit reduction |
| Affine multiplier | nonnegative integer 0..2^31-1; scale = multiplier/2^shift |
| Affine bias | signed int32 in final int16-output units (1/256) |

`RNE(n/d)` means exact integer round-to-nearest, halfway ties to even, with
positive denominator and symmetric handling of negative numerators. `sat16`
clips to [-32768,32767]; `sat8` clips to [-128,127]. No wrapping is allowed.
Negative right shifts must implement RNE, not assume language truncation.
Inputs are finite integers; NaN/Inf have no encoding and are rejected by software
conversion. Invalid descriptors/payload encodings are errors, not arithmetic
values. Padding never contributes to active values.

### Honest quantization policy

This is **W8A8 GEMM arithmetic with int16 activation storage**, not weight-only
W8A16. Before GEMM, each activation/probability row can be converted with
`amax = max(abs(raw))`, `shift=24`, and
`multiplier=RNE((127*2^24)/amax)` (zero when amax=0). Then
`q8 = sat8(RNE(raw*multiplier/2^24))`. The supported dynamic-helper input range
is [-32768,32768], covering signed activations and the unsigned probability
endpoint. Zero point is always zero. General REQUANT8 accepts signed int32
words; raw probability 32768 stays positive, never signed-int16 negative.

Store the effective inverse scale with the quantized row: for nonzero
multiplier, one int8 step corresponds to `(2^24/multiplier)/256` in activation
units or `(2^24/multiplier)/32768` in probability units. All-zero vectors have
zero codes and a documented neutral scale of 1. Using a fixed 1/127 probability
scale would round long uniform rows to zero; dynamic row scaling avoids that
specific failure. It does **not** eliminate activation quantization error.

Weights use symmetric per-output-channel int8 quantization with explicit scale
metadata (e.g. max-absolute/127, neutral 1 for an all-zero column). The floating
source/calibration is M4 work; M3 vectors supply explicit integer values/scales.
The GEMM output real scale is `sA*sB`. To obtain int16 activation raw units,
AFFINE uses a representable multiplier approximating `256*sA*sB` and a bias
already quantized into 1/256 units. Scale approximation and activation/weight
quantization are distinct from SFPU operator error. Software must reject
unrepresentable metadata or explicitly report its clipping/underflow; no hidden
scale, zero point, floating-point fabric conversion or post-clipping recovery.

### GEMM wide-result extension

- `flags=0`: the exact M2 contract, including K<=768 and final int16 saturation.
- `flags=0x00000100` (WideResultV1): K<=3072, exact int8 dot product returned as
  signed int32, **without** saturation, scaling or bias. All other flag values
  are invalid; previously rejected flag 1 remains invalid.
- Widen the physical accumulator to signed 27 bits. Maximum positive sum is
  `3072*16384 = 50,331,648`; most negative sum is `3072*(-16256) = -49,938,432`.
  Both fit [-67,108,864,67,108,863]. No intermediate clipping or wrapping.
- The full 3072 reduction is direct, not a sum of saturated M2 results. A test
  with large positive and negative K-chunks whose final exact sum is 127
  explicitly rejects the int16-partial-sum shortcut.
- Wide output is row-major, 16 signed-int32 lanes per active row, padding
  N..15 with zero: `16*M` words. Legacy remains `8*M` words. Input packing is
  unchanged apart from allowing the larger K; full M=16,K=3072 input is 24,576
  words / 98,304 bytes, output 256 words / 1,024 bytes.

### LayerNorm including learned affine

High-precision target on represented inputs is
`clip16_real((x-mean(x))/sqrt(mean((x-mean(x))^2)+1e-5)*gain+bias)`.
This is population variance, not unbiased sample variance. Epsilon is added
inside the square root, before reciprocal normalization. Gain/bias are learned
per-feature planes, not omitted constants.

Integer algorithm for raw inputs x, gain g and bias b, vector length L:

1. `S=sum(x)`, `T=sum(x*x)`, `V=L*T-S*S`, all exact.
2. `E=RNE((L*L*2^40)/100000)`.
3. `D=floor_sqrt((V<<24)+E)`.
4. `y[i]=sat16(RNE(((L*x[i]-S)*g[i]*256)/D)+b[i])`.

The square root and division implement the reciprocal-square-root normalization;
there is no requirement to materialize a low-precision standalone reciprocal.
The gain scale cancels D's 2^12 scale, allowing one final output rounding.
S requires signed 28 bits, T unsigned 42, V unsigned 54. `L*x-S` requires
signed 29 bits. The epsilon numerator requires **unsigned 64 bits**, not signed
64. Use an unsigned 80-bit radicand and up to 40-bit square root. The final
signed numerator fits 64 bits. No approximate mean subtraction, negative
variance clamp or cancellation-prone floating-point subtraction is used.

Epsilon guarantees D>0 for every legal length, including L=1. Constant vectors
produce exactly the supplied bias after saturation. Zero/near-zero variance
and maximal offsets remain defined. Integer floor sqrt introduces a small
explicit approximation covered by the accuracy budget below.

### GPT-2 GELU

Target:
`0.5*x*(1+tanh(sqrt(2/pi)*(x+0.044715*x^3)))`.
Use a positive-domain ROM with 2049 entries:
`G[i]=RNE(256*GELU(i/256))`, i=0..2048. For raw r>=0, return G[r] when
r<=2048, else r. For r<0, return `G[abs(r)]-abs(r)` when abs(r)<=2048, else 0.
The tail approximation at |x|>8 is below the declared resolution. ROM generation
uses float64 off-chip; fabric is integer only. Test **all 65,536 input values**.
This is not an erf-GELU or SiLU substitution.

### Stable masked softmax

Each score has an explicit validity bit; arbitrary, prefix/causal and all-false
masks are legal. Invalid entries are excluded from the maximum, exponential
sum, normalization and correction. All-masked vectors produce all-zero output
and successful completion (mass 0), not division by zero or a fabricated token.

For at least one valid entry:

1. `maximum=max(valid raw scores)`; `d=maximum-score`, unsigned up to 65535.
2. A 257-entry unsigned-25-bit ROM holds
   `E[i]=RNE(exp(-i/16)*2^24)`, i=0..256. For d<4096, let j=d>>4 and f=d&15;
   weight=`RNE((E[j]*(16-f)+E[j+1]*f)/16)`. For d>=4096, weight=0.
3. `sum=sum(weights)`, positive because a maximum has weight=2^24. It requires
   unsigned 35 bits for L=1024. Normalize with exact integer floor division:
   `p[i]=floor(weight[i]*32768/sum)` (40-bit numerator).
4. Let R=32768-sum(p). In increasing index order, add one to the first R entries
   with **nonzero weights**. Underflowed/masked entries remain exactly zero.
   R is smaller than the number of nonzero weights, so this always completes.

Output is unsigned 0..32768 and sums **exactly** to 32768. The index-ordered
correction has less than one output LSB error per entry relative to the
LUT-normalized distribution; it is not largest-remainder sorting. Quantization,
linear interpolation and the exp cutoff are all included in the error gates.

### Scaling, conversion and vector support

- AFFINE: `sat16(RNE(x32[i]*multiplier[i]/2^shift)+bias32[i])`, shift 0..31.
  All products and bias additions use signed 64-bit intermediates. Bias is
  applied after rounding into output units, before the one final saturation.
- AFFINE_GELU: the exact AFFINE result feeds GELU internally, with the specified
  int16 boundary. This fuses one useful chain without a host/DDR intermediate;
  it is not a single unquantized floating-point expression.
- REQUANT8: `sat8(RNE(x32[i]*scalar_multiplier/2^shift))`, shift 0..31,
  multiplier 0..2^31-1, no bias or implicit zero point. Signed-int32 input safely
  accepts both signed activation and unsigned-probability words.
- ADD: exact signed 17-bit addition of two represented int16 vectors followed
  by sat16. This supports residual and embedding additions; lookup/position
  selection remain software responsibilities in M3.

### Frozen v1 accuracy gates

Every RTL output must equal the fixed-point reference **bit for bit** on all
tested numerical/protocol cases. Independently compare against float64 on the
same represented inputs, including the declared final clipping domain:

| Operation | Required high-precision accuracy |
|---|---|
| GELU | max absolute real error <= 1/512 + 1e-12 over all 65,536 inputs |
| LayerNorm+affine | max absolute real error <= 1/128, every tested element |
| Softmax | max absolute probability error <= 1/2048 |
| Softmax L1 | sum absolute error <= valid_count/32768 + 1/1024 |
| Softmax mass/mask | exact sum 32768 if any valid, otherwise 0; masked/underflowed entries zero |
| AFFINE | <= 0.5 output LSB versus clipped represented affine target |
| AFFINE_GELU | <= 1/128 versus GELU of clipped continuous affine target |
| REQUANT8 | <= 0.5 code LSB versus clipped represented scaling target |
| ADD / wide GEMM | exact represented integer result, zero numerical error |

The 1e-12 GELU allowance is only for float64 comparison noise, not a fabric
accuracy relaxation. Relative-only error near zero is deliberately not a gate.
These limits cover arithmetic on **represented** values, not quantization loss
relative to a floating checkpoint or accumulation of error through a model.
Require deterministic adversarial cases, at least 1000 random vectors per
reduction op and exhaustive GELU; record actual counts/worst errors and seeds.
