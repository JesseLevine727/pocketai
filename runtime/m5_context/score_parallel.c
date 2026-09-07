#include "score_metadata.h"
#include "pa_m5_numerics.h"
#include "score_product.h"
#include "affine_round.h"
#include "parallel.h"
#ifdef PA_CONTEXT_COMBINED_SCORES
#include "local_scores.h"
#include "quantize.h"
#endif
typedef struct { uint64_t key; uint32_t epoch, multiplier; } score_entry;
#ifdef __riscv
static score_entry entries[128] __attribute__((section(".context_lookup")));
#else
static score_entry entries[128];
#endif
static uint32_t epochs[2];
typedef struct {
  pa_tenth_factor factor;
  const double *units;
  uint32_t *multipliers;
  uint32_t shift;
  int status[2];
#ifdef PA_CONTEXT_COMBINED_SCORES
  const int32_t *raw;
  int32_t *local;
  int32_t maximum[2];
#endif
} job_t;
static double times32(double value) {
  union { double floating; uint64_t bits; } x = {.floating = value};
  uint32_t exponent = (uint32_t)((x.bits >> 52) & 2047u);
  if (exponent && exponent < 2042) { x.bits += UINT64_C(5) << 52; return x.floating; }
  return value*32.0;
}
static void prepare(void *opaque, uint32_t first, uint32_t end, uint32_t worker) {
  job_t *job = opaque;
  score_entry *table = entries+worker*64;
  if (++epochs[worker] == 0) {
    for (uint32_t i = 0; i < 64; ++i) table[i].epoch = 0;
    epochs[worker] = 1;
  }
  uint32_t epoch = epochs[worker];
#ifdef PA_CONTEXT_COMBINED_SCORES
  int32_t maximum = INT32_MIN;
#endif
  for (uint32_t i = first; i < end; ++i) {
    union { double floating; uint64_t bits; } unit = {.floating = job->units[i]}, scale;
    uint32_t low = (uint32_t)unit.bits, high = (uint32_t)(unit.bits >> 32);
    score_entry *entry = table+((low^(low >> 16)^high)&63u);
    uint32_t multiplier;
    if (entry->epoch == epoch && entry->key == unit.bits) multiplier = entry->multiplier;
    else {
      multiplier = pa_context_score_product(&job->factor, unit.floating, job->shift);
      if (multiplier == UINT32_MAX) {
        scale.floating = times32(pa_tenth_mul_factor(&job->factor, unit.floating));
        if ((scale.bits >> 63) || ((scale.bits >> 52)&2047u) == 2047u) { job->status[worker] = -1; return; }
        multiplier = pa_scalar_rne_scaled32(scale.bits, job->shift);
      }
      if (!multiplier || multiplier >= UINT32_C(0x80000000)) { job->status[worker] = -1; return; }
      entry->key = unit.bits; entry->multiplier = multiplier; entry->epoch = epoch;
    }
#ifdef PA_CONTEXT_COMBINED_SCORES
    if (job->raw) {
      int64_t value = pa_scalar_rne_product(job->raw[i], multiplier, job->shift);
      if (value < INT32_MIN || value > INT32_MAX) { job->status[worker] = 1; return; }
      job->local[i] = (int32_t)value;
      if (value > maximum) maximum = (int32_t)value;
    } else
#endif
    job->multipliers[i] = multiplier;
  }
#ifdef PA_CONTEXT_COMBINED_SCORES
  job->maximum[worker] = maximum;
#endif
}
#ifdef PA_CONTEXT_COMBINED_SCORES
static int combined_inner(const double *units, uint32_t length, double query_unit,
    double maximum_unit, uint32_t *multipliers, uint32_t *shift, double *scratch,
    const int32_t *raw, int32_t *tagged) {
#else
int pa_context_score_metadata(const double *units, uint32_t length, double query_unit,
    double maximum_unit, uint32_t *multipliers, uint32_t *shift, double *scratch) {
#endif
  job_t job;
  job.factor = pa_tenth_prepare_factor(query_unit); job.units = units;
  job.multipliers = multipliers; job.status[0] = 0; job.status[1] = 0;
#ifdef PA_CONTEXT_COMBINED_SCORES
  job.raw = raw; job.local = pa_context_score_storage();
  job.maximum[0] = INT32_MIN; job.maximum[1] = INT32_MIN;
#endif
  double maximum = times32(pa_tenth_mul_factor(&job.factor, maximum_unit));
  uint32_t unused;
  if (pa_m5_affine_metadata(&maximum, 1, &unused, &job.shift)) goto fallback;
  if (pa_context_parallel(prepare, &job, length)) return -40;
  if (job.status[0] || job.status[1]) goto fallback;
#ifdef PA_CONTEXT_COMBINED_SCORES
  if (raw) {
    int32_t maximum = job.maximum[0] > job.maximum[1] ? job.maximum[0] : job.maximum[1];
    for (uint32_t i = 0; i < length; ++i) {
      int64_t difference = (int64_t)job.local[i]-maximum;
      int16_t score = difference < -32768 ? -32768 : (int16_t)difference;
      tagged[i] = UINT32_C(0x10000) | (uint16_t)score;
    }
  }
#endif
  *shift = job.shift; return 0;
fallback:
  for (uint32_t i = 0; i < length; ++i) scratch[i] = query_unit*units[i]*32.0;
#ifdef PA_CONTEXT_COMBINED_SCORES
  int status = pa_m5_affine_metadata(scratch, length, multipliers, shift);
  return status ? status : raw ? 1 : 0;
#else
  return pa_m5_affine_metadata(scratch, length, multipliers, shift);
#endif
}
#ifdef PA_CONTEXT_COMBINED_SCORES
int pa_context_score_metadata(const double *units, uint32_t length, double query_unit,
    double maximum_unit, uint32_t *multipliers, uint32_t *shift, double *scratch) {
  return combined_inner(units, length, query_unit, maximum_unit, multipliers, shift, scratch, 0, 0);
}
int pa_context_score_combined(const double *units, uint32_t length, double query_unit,
    double maximum_unit, uint32_t *multipliers, uint32_t *shift, double *scratch,
    const int32_t *raw, int32_t *tagged) {
  return combined_inner(units, length, query_unit, maximum_unit, multipliers, shift, scratch, raw, tagged);
}
#endif
