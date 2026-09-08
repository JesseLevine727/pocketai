typedef struct {
  const double *gain, *bias;
  int16_t *gain_q12;
  int32_t *bias_q8;
  double correction;
  uint32_t exponent;
  int factor_shift, status[2];
} startup_norm_job;
static void startup_norm_leaf(void *opaque, uint32_t first,
                               uint32_t end, uint32_t worker) {
  startup_norm_job *job = opaque;
  for (uint32_t i = first; i < end; ++i) {
    /* Keep both ordered power-of-two operations, including edge fallback. */
    double corrected = job->exponent ? job->gain[i]*job->correction : job->gain[i];
    double scaled = pa_fast_scale_power2(corrected, 12);
    int64_t g = pa_m5_rne_f64_signed(pa_fast_scale_power2(scaled, -job->factor_shift));
    int64_t b = pa_m5_rne_f64_signed(pa_fast_scale_power2(job->bias[i], 8));
    if (g < -32768 || g > 32767 || b < INT32_MIN || b > INT32_MAX) {
      job->status[worker] = -2; return;
    }
    job->gain_q12[i] = (int16_t)g; job->bias_q8[i] = (int32_t)b;
  }
}
