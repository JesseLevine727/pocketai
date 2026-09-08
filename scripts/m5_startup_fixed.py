"""Row-invariant fixed scales, with a proof before every integer publication."""
from scripts.m5_iterate_sources import once


def derive(source):
    ops = '#include "fixed_branch.h"\n'+source['attention_ops.c']
    ops = once(ops, 'static inline int16_t startup_narrow_saturate(',
        'static __attribute__((noinline)) int16_t startup_narrow_saturate(')
    ops = once(ops, '  uint32_t shifts[16], adjustments[16];',
        '  uint32_t shifts[16], adjustments[16], fixed_row[16];\n  const uint32_t *fixed_weight;')
    ops = once(ops, '    double w0 = weights[i], w1 = weights[i+1];',
        '    uint32_t w0 = job->fixed_weight[i], w1 = job->fixed_weight[i+1];')
    start = ops.index('      uint32_t m0 = pa_startup_project_multiplier(job->factors+row')
    end = ops.index('      ((startup_word *)(output+row*n))', start)
    ops = ops[:start]+'''      int32_t s0 = sums[row*n+i], s1 = sums[row*n+i+1], v0, v1;
      int16_t q0, q1;
      if (startup_fixed_branch(s0, w0, job->fixed_row[row], shift, &v0)) {
        v0 += b0; q0 = v0 < -32768 ? -32768 : v0 > 32767 ? 32767 : (int16_t)v0;
      } else q0 = startup_narrow_saturate(s0,
          pa_startup_project_multiplier(job->factors+row, weights[i], adjustment, shift), shift, b0);
      if (startup_fixed_branch(s1, w1, job->fixed_row[row], shift, &v1)) {
        v1 += b1; q1 = v1 < -32768 ? -32768 : v1 > 32767 ? 32767 : (int16_t)v1;
      } else q1 = startup_narrow_saturate(s1,
          pa_startup_project_multiplier(job->factors+row, weights[i+1], adjustment, shift), shift, b1);
'''+ops[end:]
    ops = once(ops, '  startup_batch_job job;\n  job.weights', '''  int normalize = 1053-(int)(maximum_weight>>52);
  uint64_t normalized_maximum = maximum_weight+((uint64_t)(int64_t)normalize<<52);
  if (pa_scalar_rne_scaled32(normalized_maximum, 0) >= UINT32_C(0x80000000)) --normalize;
  uint32_t *fixed_weight = (uint32_t *)(bias_scratch+n);
  startup_batch_job job;
  job.fixed_weight = fixed_weight;
  job.weights''')
    ops = once(ops, '    job.shifts[row] = shift; job.adjustments[row] = power<<20;', '''    job.shifts[row] = shift; job.adjustments[row] = power<<20;
    union { double floating; uint64_t bits; } u = {.floating = units[row]};
    int row_power = (int)power+(int)shift-normalize+30;
    int row_encoded = (int)factor.exponent+row_power;
    if (row_encoded <= 0 || row_encoded >= 2047) return 0;
    u.bits += (uint64_t)(int64_t)row_power<<52;
    job.fixed_row[row] = pa_scalar_rne_scaled32(u.bits, 0);
    if (!job.fixed_row[row] || job.fixed_row[row] >= UINT32_C(0x80000000)) return 0;''')
    ops = once(ops, '    bias_scratch[i] = negative ? -(int32_t)magnitude : (int32_t)magnitude;', '''    bias_scratch[i] = negative ? -(int32_t)magnitude : (int32_t)magnitude;
    union { double floating; uint64_t bits; } w = {.floating = linear->scale[i]};
    int encoded_weight = (int)(w.bits>>52)+normalize;
    if (encoded_weight <= 0 || encoded_weight >= 2047) return 0;
    w.bits += (uint64_t)(int64_t)normalize<<52;
    fixed_weight[i] = pa_scalar_rne_scaled32(w.bits, 0);
    if (fixed_weight[i] >= UINT32_C(0x80000000)) return 0;''')
    source['attention_ops.c'] = ops
