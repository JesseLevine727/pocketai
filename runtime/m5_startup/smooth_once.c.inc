typedef struct {
  const int16_t *input;
  const uint32_t *multipliers;
  int16_t *scratch;
  uint32_t rows, columns, shift;
  int overflow[2];
} startup_smooth_job;
static void startup_smooth_leaf(void *opaque, uint32_t first,
                                 uint32_t end, uint32_t worker) {
  startup_smooth_job *job = opaque;
  const uint32_t columns = job->columns, shift = job->shift;
  const uint32_t *multipliers = job->multipliers;
  const int16_t *input = job->input;
  int16_t *scratch = job->scratch;
  int overflow = 0;
  /* Flat, 16-element-aligned partitions own complete output words even when
   * columns is odd. A column split would share a word on odd-numbered rows. */
  uint32_t column = first%columns;
  for (uint32_t i = first; i < end; ++i) {
    int64_t value = pa_scalar_rne_product(input[i], multipliers[column], shift);
    if (value < -32768 || value > 32767) overflow = 1;
    scratch[i] = (int16_t)value;
    if (++column == columns) column = 0;
  }
  job->overflow[worker] = overflow;
}
static int startup_smooth_once(pa_m5_workspace *workspace, const int16_t *input,
    const uint32_t *multipliers, uint32_t shift, uint32_t rows, uint32_t columns,
    int16_t *output, uint32_t *exponents) {
  uint32_t mark = workspace->used, count = rows*columns;
  int16_t *scratch = pa_m5_workspace_allocate(workspace, count*2, 64);
  if (!scratch) { pa_m5_workspace_rewind(workspace, mark); return 0; }
  startup_smooth_job job = {.input = input, .multipliers = multipliers,
      .scratch = scratch, .rows = rows, .columns = columns, .shift = shift,
      .overflow = {0, 0}};
  int status = pa_context_parallel(startup_smooth_leaf, &job, count);
  if (status || job.overflow[0] || job.overflow[1]) {
    pa_m5_workspace_rewind(workspace, mark); return status ? -40 : 0;
  }
  /* This is exactly the old no-overflow branch: exponent zero, even if its
   * logical magnitude were between the 32700 and 32767 thresholds. */
  uint32_t i = 0;
  if (!((uintptr_t)output&3u)) for (; i+1 < count; i += 2)
    ((startup_word *)output)[i/2] = ((const startup_word *)scratch)[i/2];
  for (; i < count; ++i) output[i] = scratch[i];
  for (uint32_t row = 0; row < rows; ++row) exponents[row] = 0;
  pa_m5_workspace_rewind(workspace, mark); return 1;
}
