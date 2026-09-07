/* Leaf work never calls the backend, allocates workspace or mutates shared
 * quantizer/cache state. Disjoint output slices and per-worker reductions. */
typedef struct {
  pa_tenth_factor factor;
  const pa_m5_linear *linear;
  const int32_t *sums;
  const int16_t *residual;
  double *scales;
  uint32_t input_exponent, residual_exponent, range;
  uint64_t maximum[2];
} pa_context_project_job;
static void pa_context_project_leaf(void *opaque, uint32_t first, uint32_t end, uint32_t worker) {
  pa_context_project_job *job = opaque;
  uint64_t maximum = 0;
  for (uint32_t i = first; i < end; ++i) {
    double scale = pa_tenth_mul_factor(&job->factor, job->linear->scale[i]);
    scale = pa_fast_scale_power2(scale, (int)job->input_exponent);
    job->scales[i] = scale;
    if (job->range) {
      double logical = pa_iter_range_term(job->sums[i], scale, job->linear->bias[i],
          job->residual ? job->residual+i : 0, job->residual_exponent);
      maximum = pa_iter_range_max(maximum, logical);
    }
  }
  job->maximum[worker] = maximum;
}

typedef struct {
  const double *scales, *raw_bias;
  uint32_t *multipliers;
  int32_t *bias;
  uint64_t adjustment;
  uint32_t shift;
  int power_shift, status[2];
} pa_context_affine_job;
static void pa_context_affine_leaf(void *opaque, uint32_t first, uint32_t end, uint32_t worker) {
  pa_context_affine_job *job = opaque;
  for (uint32_t i = first; i < end; ++i) {
    union { double floating; uint64_t bits; } value = {.floating = job->scales[i]};
    uint32_t rounded = pa_scalar_rne_scaled32(value.bits+job->adjustment, job->shift);
    if (!rounded || rounded >= UINT32_C(0x80000000)) { job->status[worker] = -1; return; }
    job->multipliers[i] = rounded;
    int64_t bias = pa_m5_rne_f64_signed(pa_fast_scale_power2(job->raw_bias[i], job->power_shift));
    if (bias < INT32_MIN || bias > INT32_MAX) { job->status[worker] = -1; return; }
    job->bias[i] = (int32_t)bias;
  }
}
