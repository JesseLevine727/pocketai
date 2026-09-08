/* An exact speculative fast path, never an approximate numerical path.
 * Try the incoming residual exponent (zero without a residual), and certify
 * that the original binary64 range calculation would select it. Uncertain
 * or unsupported rows execute the unchanged generic implementation instead.
 * All tentative results live in scratch until the entire row is accepted. */
typedef struct {
  pa_tenth_factor factor;
  const double *weight, *bias;
  const int32_t *sums;
  const int16_t *residual;
  int16_t *scratch;
  uint32_t shift, adjustment, power, range;
  uint32_t lower[2], upper[2];
  int status[2];
} startup_project_job;

static void startup_project_leaf(void *opaque, uint32_t first,
                                  uint32_t end, uint32_t worker) {
  const startup_project_job *job = opaque;
  /* Copy row constants before stores; no per-element reload of a shared job. */
  const pa_tenth_factor factor = job->factor;
  const double *weight = job->weight, *bias = job->bias;
  const int32_t *sums = job->sums;
  const int16_t *residual = job->residual;
  int16_t *scratch = job->scratch;
  const uint32_t shift = job->shift, adjustment = job->adjustment;
  const int power = (int)job->power;
  uint32_t lower = 0, upper = 0;
  int status = 0;
  for (uint32_t i = first; i < end; ++i) {
    union { double floating; uint64_t bits; } scale = {
        .floating = pa_tenth_mul_factor(&factor, weight[i])}, b = {.floating = bias[i]};
    scale.bits += (uint64_t)adjustment << 32;
    uint32_t multiplier = pa_scalar_rne_scaled32(scale.bits, shift);
    if (!multiplier || multiplier >= UINT32_C(0x80000000)) { status = 1; break; }
    uint32_t sign = (uint32_t)(b.bits >> 63);
    b.bits &= UINT64_C(0x7fffffffffffffff);
    int encoded = (int)(b.bits >> 52);
    int32_t rounded_bias = 0;
    if (encoded) {
      if (encoded == 2047 || encoded+power <= 0 || encoded+power >= 1052) { status = 1; break; }
      b.bits += (uint64_t)(int64_t)power << 52;
      uint32_t magnitude = pa_scalar_rne_scaled32(b.bits, 0);
      rounded_bias = sign ? -(int32_t)magnitude : (int32_t)magnitude;
    }
    /* Subnormal biases, scaled by at most 2^8, still round to zero. */
    int32_t sum = sums[i];
    uint32_t magnitude = sum < 0 ? 0u-(uint32_t)sum : (uint32_t)sum;
    if (magnitude > (UINT32_C(1) << 26)) { status = 1; break; }
    int64_t branch = pa_scalar_rne_product(sum, multiplier, shift);
    if (branch <= -(INT64_C(1) << 29) || branch >= (INT64_C(1) << 29)) { status = 1; break; }
    int32_t value = (int32_t)branch+rounded_bias;
    if (job->range) {
      uint32_t absolute = value < 0 ? 0u-(uint32_t)value : (uint32_t)value;
      uint32_t error = (magnitude >> shift)+5u;
      /* |integer approximation - ordered binary64 logical value| < error.
       * Multiplier rounding: <= |sum|/(2*2^shift); integer and bias rounding:
       * <=1 combined; all binary64 roundings: <1 under the bounds above.
       * The extra two units cover the floor and strict endpoint comparison.
       * Residual units are exact here because candidate==residual_exponent. */
      uint32_t old = residual ? (residual[i] < 0 ? -(int32_t)residual[i] : residual[i]) : 0;
      uint32_t lo = (absolute > error ? absolute-error : 0)+old;
      uint32_t hi = absolute+error+old;
      if (lo > lower) lower = lo;
      if (hi > upper) upper = hi;
    }
    value = value < -32768 ? -32768 : value > 32767 ? 32767 : value;
    if (residual) {
      value += residual[i];
      value = value < -32768 ? -32768 : value > 32767 ? 32767 : value;
    }
    scratch[i] = (int16_t)value;
  }
  ((startup_project_job *)opaque)->lower[worker] = lower;
  ((startup_project_job *)opaque)->upper[worker] = upper;
  ((startup_project_job *)opaque)->status[worker] = status;
}

static int startup_project_row(const pa_m5_linear *linear, double unit,
    uint32_t input_exponent, const int32_t *sums, int scaled,
    const int16_t *residual, uint32_t residual_exponent,
    uint64_t minimum_weight, uint64_t maximum_weight,
    int16_t *scratch, int16_t *output, uint32_t *output_exponent) {
  uint32_t candidate = residual ? residual_exponent : 0;
  if (!minimum_weight || !maximum_weight || input_exponent > 30 || candidate > 30) return 0;
  pa_tenth_factor factor = pa_tenth_prepare_factor(unit);
  if (factor.sign || !factor.exponent || factor.exponent == 2047) return 0;
  union { uint64_t bits; double floating; } minimum = {.bits = minimum_weight},
      maximum = {.bits = maximum_weight};
  minimum.floating = pa_tenth_mul_factor(&factor, minimum.floating);
  maximum.floating = pa_tenth_mul_factor(&factor, maximum.floating);
  int low = (int)(minimum.bits >> 52), high = (int)(maximum.bits >> 52);
  int power = 8-(int)candidate, adjustment = (int)input_exponent+power;
  if (low <= 0 || high >= 2047 || low+(int)input_exponent <= 0 ||
      high+(int)input_exponent >= 2047 || low+adjustment <= 0 || high+adjustment >= 2047) return 0;
  maximum.bits += (uint64_t)(int64_t)adjustment << 52;
  uint32_t shift = 31;
  while (shift && pa_scalar_rne_scaled32(maximum.bits, shift) >= UINT32_C(0x80000000)) --shift;
  if (shift < 8) return 0;
  startup_project_job job = {
      .factor = factor, .weight = linear->scale, .bias = linear->bias,
      .sums = sums, .residual = residual, .scratch = scratch, .shift = shift,
      .adjustment = (uint32_t)adjustment << 20, .power = (uint32_t)power,
      .range = scaled || residual, .lower = {0, 0}, .upper = {0, 0}, .status = {0, 0}};
  if (pa_context_parallel(startup_project_leaf, &job, linear->n)) return -40;
  if (job.status[0] || job.status[1]) return 0;
  uint32_t lower = job.lower[0] > job.lower[1] ? job.lower[0] : job.lower[1];
  uint32_t upper = job.upper[0] > job.upper[1] ? job.upper[0] : job.upper[1];
  if (job.range && (upper > 32700 || (candidate && lower <= 16350))) return 0;
  typedef uint32_t packed_alias __attribute__((__may_alias__));
  uint32_t i = 0;
  if (!((uintptr_t)output & 3u)) {
    for (; i+1 < linear->n; i += 2)
      ((packed_alias *)output)[i/2] = ((const packed_alias *)scratch)[i/2];
  }
  for (; i < linear->n; ++i) output[i] = scratch[i];
  *output_exponent = candidate;
  return 1;
}

#ifndef __riscv
/* Native-only raw-sum test seam: independently exercise certification near
 * exponent boundaries and metadata ties without hiding it behind a GEMM. */
int pa_startup_project_test(double unit, uint32_t input_exponent,
    const double *weight, const double *bias, const int32_t *sums, uint32_t count,
    int scaled, const int16_t *residual, uint32_t residual_exponent,
    int16_t *scratch, int16_t *output, uint32_t *output_exponent) {
  uint64_t minimum = UINT64_MAX, maximum = 0;
  for (uint32_t i = 0; i < count; ++i) {
    union { double floating; uint64_t bits; } v = {.floating = weight[i]};
    uint32_t encoded = (uint32_t)(v.bits >> 52);
    if (!encoded || encoded >= 2047) { minimum = maximum = 0; break; }
    if (v.bits < minimum) minimum = v.bits;
    if (v.bits > maximum) maximum = v.bits;
  }
  pa_m5_linear linear = {.scale = weight, .bias = bias, .n = count};
  return startup_project_row(&linear, unit, input_exponent, sums, scaled,
      residual, residual_exponent, minimum, maximum, scratch, output, output_exponent);
}
#endif
