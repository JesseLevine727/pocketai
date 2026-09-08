/* Unscaled, no-residual projections have a prescribed zero output exponent.
 * Validate every row's metadata domain before publishing output, then reuse
 * each immutable weight/bias pair across all prompt rows. No range speculation
 * or intermediate-output round trip is needed in this exact domain. */
typedef struct {
  pa_tenth_factor factors[16];
  uint32_t shifts[16], adjustments[16];
  const double *weights;
  const int32_t *bias, *sums;
  int16_t *output;
  uint32_t rows, columns;
} startup_batch_job;
static void startup_batch_leaf(void *opaque, uint32_t first,
                                uint32_t end, uint32_t worker) {
  const startup_batch_job *job = opaque; (void)worker;
  const double *weights = job->weights;
  const int32_t *bias = job->bias, *sums = job->sums;
  int16_t *output = job->output;
  uint32_t rows = job->rows, n = job->columns;
  for (uint32_t i = first; i < end; i += 2) {
    double w0 = weights[i], w1 = weights[i+1];
    int32_t b0 = bias[i], b1 = bias[i+1];
    for (uint32_t row = 0; row < rows; ++row) {
      uint32_t shift = job->shifts[row], adjustment = job->adjustments[row];
      uint32_t m0 = pa_startup_project_multiplier(job->factors+row, w0, adjustment, shift);
      uint32_t m1 = pa_startup_project_multiplier(job->factors+row, w1, adjustment, shift);
      /* Positive-normal min/max and bias validation proved metadata success
       * for every element before entry; retain the complete int64 finalizer. */
      int64_t v0 = pa_scalar_rne_product(sums[row*n+i], m0, shift)+b0;
      int64_t v1 = pa_scalar_rne_product(sums[row*n+i+1], m1, shift)+b1;
      int16_t q0 = v0 < -32768 ? -32768 : v0 > 32767 ? 32767 : (int16_t)v0;
      int16_t q1 = v1 < -32768 ? -32768 : v1 > 32767 ? 32767 : (int16_t)v1;
      ((startup_word *)(output+row*n))[i/2] = (uint16_t)q0|(uint32_t)(uint16_t)q1<<16;
    }
  }
}
static int __attribute__((noinline, optimize("Os", "no-tree-loop-distribute-patterns")))
startup_batch_project(const pa_m5_linear *linear, const double *units,
    const uint32_t *input_exponents, uint32_t rows, const int32_t *sums,
    uint64_t minimum_weight, uint64_t maximum_weight, int32_t *bias_scratch,
    int16_t *output, uint32_t *output_exponents) {
  uint32_t n = linear->n;
  if (rows < 2 || n > 3072 || (n&31u) || ((uintptr_t)output&3u) ||
      !minimum_weight || !maximum_weight) return 0;
  startup_batch_job job;
  job.weights = linear->scale; job.bias = bias_scratch; job.sums = sums;
  job.output = output; job.rows = rows; job.columns = n;
  for (uint32_t row = 0; row < rows; ++row) {
    if (input_exponents[row] > 30) return 0;
    pa_tenth_factor factor = pa_tenth_prepare_factor(units[row]);
    if (factor.sign || !factor.exponent || factor.exponent == 2047) return 0;
    union { uint64_t bits; double floating; } lo = {.bits = minimum_weight}, hi = {.bits = maximum_weight};
    lo.floating = pa_tenth_mul_factor(&factor, lo.floating);
    hi.floating = pa_tenth_mul_factor(&factor, hi.floating);
    uint32_t low_exponent = (uint32_t)(lo.bits>>52), high_exponent = (uint32_t)(hi.bits>>52);
    uint32_t power = input_exponents[row]+8;
    if (!low_exponent || high_exponent+power >= 2047) return 0;
    lo.bits += (uint64_t)power<<52; hi.bits += (uint64_t)power<<52;
    uint32_t shift = 31;
    while (shift && pa_scalar_rne_scaled32(hi.bits, shift) >= UINT32_C(0x80000000)) --shift;
    if (pa_scalar_rne_scaled32(hi.bits, shift) >= UINT32_C(0x80000000) ||
        !pa_scalar_rne_scaled32(lo.bits, shift)) return 0;
    /* Explicit fields avoid a freestanding compiler-generated libc copy. */
    volatile pa_tenth_factor *prepared = job.factors+row;
    prepared->value = factor.value; prepared->low = factor.low; prepared->high = factor.high;
    prepared->exponent = factor.exponent; prepared->sign = factor.sign;
    job.shifts[row] = shift; job.adjustments[row] = power<<20;
  }
  for (uint32_t i = 0; i < n; ++i) {
    union { double floating; uint64_t bits; } b = {.floating = linear->bias[i]};
    uint32_t negative = (uint32_t)(b.bits>>63);
    b.bits &= UINT64_C(0x7fffffffffffffff);
    uint32_t encoded = (uint32_t)(b.bits>>52), magnitude = 0;
    if (encoded) {
      if (encoded >= 1046) return 0;
      magnitude = pa_scalar_rne_scaled32(b.bits+(UINT64_C(8)<<52), 0);
      if (magnitude >= UINT32_C(0x80000000)) return 0;
    }
    bias_scratch[i] = negative ? -(int32_t)magnitude : (int32_t)magnitude;
  }
  if (pa_context_parallel(startup_batch_leaf, &job, n)) return -40;
  for (uint32_t row = 0; row < rows; ++row) output_exponents[row] = 0;
  return 1;
}

#ifndef __riscv
int pa_startup_batch_test(const double *units, const uint32_t *input_exponents,
    const double *weights, const double *bias, const int32_t *sums,
    uint32_t rows, uint32_t count, int32_t *scratch, int16_t *output,
    uint32_t *output_exponents) {
  if (!rows || rows > 16) return 0;
  uint64_t minimum = UINT64_MAX, maximum = 0;
  for (uint32_t i = 0; i < count; ++i) {
    union { double floating; uint64_t bits; } v = {.floating = weights[i]};
    uint32_t encoded = (uint32_t)(v.bits>>52);
    if (!encoded || encoded >= 2047) { minimum = maximum = 0; break; }
    if (v.bits < minimum) minimum = v.bits;
    if (v.bits > maximum) maximum = v.bits;
  }
  pa_m5_linear linear = {.scale = weights, .bias = bias, .n = count};
  return startup_batch_project(&linear, units, input_exponents, rows, sums,
      minimum, maximum, scratch, output, output_exponents);
}
#endif
