typedef struct {
  pa_tenth_factor factor;
  const double *units;
  const int32_t *sums;
  int16_t *output;
  uint32_t shift;
  int status[2];
} startup_attention_job;
static void startup_attention_leaf(void *opaque, uint32_t first,
                                    uint32_t end, uint32_t worker) {
  startup_attention_job *job = opaque;
  const pa_tenth_factor factor = job->factor;
  const double *units = job->units;
  const int32_t *sums = job->sums;
  int16_t *output = job->output;
  uint32_t shift = job->shift;
  int status = 0;
  for (uint32_t i = first; i < end; ++i) {
    uint32_t multiplier = pa_startup_project_multiplier(&factor, units[i], 8u<<20, shift);
    if (!multiplier || multiplier >= UINT32_C(0x80000000)) { status = 1; break; }
    int64_t value = pa_scalar_rne_product(sums[i], multiplier, shift);
    output[i] = value < -32768 ? -32768 : value > 32767 ? 32767 : (int16_t)value;
  }
  job->status[worker] = status;
}
static int startup_attention_output(const int32_t *sums, double probability_unit,
                                     const double *units, int16_t *scratch) {
  pa_tenth_factor factor = pa_tenth_prepare_factor(probability_unit);
  if (factor.sign || !factor.exponent || factor.exponent == 2047) return 0;
  uint64_t minimum = UINT64_MAX, maximum = 0;
  for (uint32_t i = 0; i < 64; ++i) {
    union { double floating; uint64_t bits; } v = {.floating = units[i]};
    uint32_t encoded = (uint32_t)(v.bits>>52);
    if (!encoded || encoded >= 2047) return 0;
    if (v.bits < minimum) minimum = v.bits;
    if (v.bits > maximum) maximum = v.bits;
  }
  union { double floating; uint64_t bits; } low = {.bits = minimum}, high = {.bits = maximum};
  low.floating = pa_tenth_mul_factor(&factor, low.floating);
  high.floating = pa_tenth_mul_factor(&factor, high.floating);
  if (!(low.bits>>52) || (high.bits>>52) >= 2039) return 0;
  high.bits += UINT64_C(8)<<52;
  uint32_t shift = 31;
  while (shift && pa_scalar_rne_scaled32(high.bits, shift) >= UINT32_C(0x80000000)) --shift;
  startup_attention_job job = {.factor = factor, .units = units, .sums = sums,
      .output = scratch, .shift = shift, .status = {0, 0}};
  if (pa_context_parallel(startup_attention_leaf, &job, 64)) return -40;
  return job.status[0] || job.status[1] ? 0 : 1;
}
