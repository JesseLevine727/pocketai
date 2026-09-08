/* Reuse each multiplier pair across prompt rows and publish complete words.
 * The existing flat leaf remains the odd-shape/alignment fallback. */
static void startup_smooth_batch_leaf(void *opaque, uint32_t first,
                                       uint32_t end, uint32_t worker) {
  startup_smooth_job *job = opaque;
  uint32_t columns = job->columns, shift = job->shift;
  int overflow = 0;
  for (uint32_t column = first; column < end; column += 2) {
    uint32_t m0 = job->multipliers[column], m1 = job->multipliers[column+1];
    const startup_word *input = (const startup_word *)(job->input+column);
    startup_word *output = (startup_word *)(job->scratch+column);
    for (uint32_t row = 0; row < job->rows; ++row) {
      uint32_t packed = input[row*(columns/2)];
      int32_t v0 = (int16_t)packed, v1 = (int16_t)(packed>>16), q0 = 0, q1 = 0;
      uint32_t a0 = v0 < 0 ? 0u-(uint32_t)v0 : (uint32_t)v0;
      uint32_t a1 = v1 < 0 ? 0u-(uint32_t)v1 : (uint32_t)v1;
      if (!startup_word_affine(v0, a0, m0, shift, &q0) || q0 < -32768 || q0 > 32767) overflow = 1;
      if (!startup_word_affine(v1, a1, m1, shift, &q1) || q1 < -32768 || q1 > 32767) overflow = 1;
      output[row*(columns/2)] = (uint16_t)q0|(uint32_t)(uint16_t)q1<<16;
    }
  }
  job->overflow[worker] = overflow;
}
typedef struct { const double *source; double *result; } startup_reciprocal_job;
static void startup_reciprocal_leaf(void *opaque, uint32_t first,
                                    uint32_t end, uint32_t worker) {
  startup_reciprocal_job *job = opaque; (void)worker;
  for (uint32_t i = first; i < end; ++i) job->result[i] = pa_tenth_reciprocal(job->source[i]);
}
