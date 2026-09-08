/* Fuse exact integer finalization into metadata preparation. Results remain
 * scratch until both workers validate; fallback never sees a partial output. */
static void pa_context_affine_leaf(void *opaque, uint32_t first, uint32_t end, uint32_t worker) {
  pa_context_affine_job *job = opaque;
  for (uint32_t i = first; i < end; ++i) {
    union { double floating; uint64_t bits; } value = {.floating = job->scales[i]};
    uint32_t rounded = pa_scalar_rne_scaled32(value.bits+job->adjustment, job->shift);
    if (!rounded || rounded >= UINT32_C(0x80000000)) { job->status[worker] = -1; return; }
    int64_t bias = pa_m5_rne_f64_signed(pa_fast_scale_power2(job->raw_bias[i], job->power_shift));
    if (bias < INT32_MIN || bias > INT32_MAX) { job->status[worker] = -1; return; }
    int64_t output = pa_scalar_rne_product(job->input[i], rounded, job->shift)+bias;
    job->result[i] = output < -32768 ? -32768 : output > 32767 ? 32767 : (int32_t)output;
  }
}

