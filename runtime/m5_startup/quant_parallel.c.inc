#include "parallel.h"
#include "bounded_quant.h"
typedef uint32_t quant_word __attribute__((__may_alias__));
typedef struct {
  const int16_t *input;
  int8_t *output;
  uint32_t maximum[2], multiplier;
} startup_quant_job;
static void startup_quant_scan(void *opaque, uint32_t first,
                                uint32_t end, uint32_t worker) {
  startup_quant_job *job = opaque;
  const int16_t *input = job->input;
  uint32_t maximum = 0;
  for (uint32_t i = first; i < end; ++i) {
    int32_t v = input[i];
    uint32_t magnitude = v < 0 ? (uint32_t)-v : (uint32_t)v;
    if (magnitude > maximum) maximum = magnitude;
  }
  job->maximum[worker] = maximum;
}
static void startup_quant_pack(void *opaque, uint32_t first,
                                uint32_t end, uint32_t worker) {
  const startup_quant_job *job = opaque; (void)worker;
  const int16_t *input = job->input;
  int8_t *output = job->output;
  uint32_t multiplier = job->multiplier, i = first;
  if (!((uintptr_t)(input+first)&3u) && !((uintptr_t)(output+first)&3u)) {
    for (; i+3 < end; i += 4) {
      uint32_t a = ((const quant_word *)input)[i/2], b = ((const quant_word *)input)[i/2+1];
      ((quant_word *)output)[i/4] = (uint8_t)pa_startup_signed_quant((int16_t)a, multiplier) |
          (uint32_t)(uint8_t)pa_startup_signed_quant((int16_t)(a>>16), multiplier)<<8 |
          (uint32_t)(uint8_t)pa_startup_signed_quant((int16_t)b, multiplier)<<16 |
          (uint32_t)(uint8_t)pa_startup_signed_quant((int16_t)(b>>16), multiplier)<<24;
    }
  }
  for (; i < end; ++i) output[i] = pa_startup_signed_quant(input[i], multiplier);
}
int pa_m5_requant_offload(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                          const int16_t *input, uint32_t rows, uint32_t columns,
                          int8_t *output, double *units) {
  if (!backend || !backend->sfpu || !workspace || !input || !output || !units ||
      !rows || rows > 16 || !columns || columns > 3072) return -1;
  /* Keep the original reservation/error boundary; no larger live allocation. */
  uint32_t mark = workspace->used;
  int32_t *expanded = pa_m5_workspace_allocate(workspace, columns*4, 64);
  int32_t *result = pa_m5_workspace_allocate(workspace, columns*4, 64);
  if (!expanded || !result) { pa_m5_workspace_rewind(workspace, mark); return -1; }
  int status = 0;
  for (uint32_t row = 0; row < rows; ++row) {
    startup_quant_job job = {.input = input+row*columns, .output = output+row*columns,
                            .maximum = {0, 0}, .multiplier = 0};
    if (pa_context_parallel(startup_quant_scan, &job, columns)) { status = -40; break; }
    uint32_t maximum = job.maximum[0] > job.maximum[1] ? job.maximum[0] : job.maximum[1];
    units[row] = pa_scalar_dynamic(maximum, 8, &job.multiplier);
    if (job.multiplier == UINT32_MAX) { status = -2; break; }
    /* Unaligned row output could share a word across workers. Serialize only
     * that generic case; model row widths and the normal fast path are aligned. */
    if ((uintptr_t)job.output&3u) startup_quant_pack(&job, 0, columns, 0);
    else if (pa_context_parallel(startup_quant_pack, &job, columns)) { status = -40; break; }
  }
  pa_m5_workspace_rewind(workspace, mark); return status;
}
