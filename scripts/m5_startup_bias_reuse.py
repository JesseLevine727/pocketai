"""Reuse exact bias rounding across equal-exponent residual prompt rows.

The first accepted speculative row populates unused upper scratch storage.
No persistent cache, extra allocation, changed arithmetic, or untimed work.
"""
from scripts.m5_iterate_sources import once


def derive(source):
    ops = source['attention_ops.c']
    ops = once(ops, '  const double *weight, *bias;\n  const int32_t *sums;',
        '  const double *weight, *bias;\n  int32_t *bias_cache;\n  uint32_t reuse_bias;\n  const int32_t *sums;')
    ops = once(ops, '  const double *weight = job->weight, *bias = job->bias;',
        '  const double *weight = job->weight, *bias = job->bias;\n'
        '  int32_t *bias_cache = job->bias_cache;\n'
        '  const uint32_t reuse_bias = job->reuse_bias;')
    ops = once(ops, '    union { double floating; uint64_t bits; } b = {.floating = bias[i]};\n', '')
    start = ops.index('    uint32_t sign = (uint32_t)(b.bits >> 63);', ops.index('static void startup_project_leaf('))
    end = ops.index('    int32_t sum = sums[i];', start)
    conversion = ops[start:end].replace('    int32_t rounded_bias = 0;\n', '')
    ops = ops[:start]+'''    int32_t rounded_bias = 0;
    if (bias_cache && reuse_bias) rounded_bias = bias_cache[i];
    else {
      union { double floating; uint64_t bits; } b = {.floating = bias[i]};
'''+''.join('  '+line+'\n' for line in conversion.splitlines())+'''      if (bias_cache) bias_cache[i] = rounded_bias;
    }
'''+ops[end:]
    ops = once(ops, '    uint64_t minimum_weight, uint64_t maximum_weight,\n    int16_t *scratch, int16_t *output, uint32_t *output_exponent) {',
        '    uint64_t minimum_weight, uint64_t maximum_weight,\n    int16_t *scratch, int16_t *output, uint32_t *output_exponent,\n'
        '    int32_t *bias_cache, uint32_t reuse_bias) {')
    ops = once(ops, '      .factor = factor, .weight = linear->scale, .bias = linear->bias,',
        '      .factor = factor, .weight = linear->scale, .bias = linear->bias,\n'
        '      .bias_cache = bias_cache, .reuse_bias = reuse_bias,')
    ops = once(ops, 'residual, residual_exponent, minimum, maximum, scratch, output, output_exponent);',
        'residual, residual_exponent, minimum, maximum, scratch, output, output_exponent, 0, 0);')
    helper = '''/* Bias scratch already reserves 8*n bytes. Tentative int16 outputs use
 * only the first 2*n; the upper 4*n hold these int32 values without overlap.
 * Equal residual exponents are required because they fix the speculative
 * candidate. A scaled/no-residual preview can change it, so never reuse there.
 * Only acceptance of the whole first row publishes this private cache. */
static int32_t *startup_bias_rows(uint32_t rows, const int16_t *residual,
    const uint32_t *exponents, uint32_t n, double *scratch) {
  if (rows < 2 || !residual || exponents[0] > 30) return 0;
  for (uint32_t row = 1; row < rows; ++row)
    if (exponents[row] != exponents[0]) return 0;
  return (int32_t *)scratch+n;
}

'''
    ops = once(ops, 'int pa_m5_project(', helper+'int pa_m5_project(')
    ops = once(ops, '  for (uint32_t row = 0; row < rows; ++row) {\n    stamp = pa_startup_begin();\n    int fast = startup_project_row',
        '  int32_t *bias_cache = startup_bias_rows(rows, residual, residual_exponents, n, bias);\n'
        '  for (uint32_t row = 0; row < rows; ++row) {\n    stamp = pa_startup_begin();\n    int fast = startup_project_row')
    ops = once(ops, 'minimum_weight, maximum_weight, (int16_t *)bias, output+row*n, output_exponents+row);',
        'minimum_weight, maximum_weight, (int16_t *)bias, output+row*n, output_exponents+row,\n'
        '        bias_cache, row != 0);')
    ops = once(ops, '    if (fast) continue;\n    pa_tenth_factor factor',
        '    if (fast) continue;\n'
        '    /* The generic fallback owns all 8*n scratch bytes: invalidate before\n'
        '     * it can overwrite any cached biases, including a failed first row. */\n'
        '    bias_cache = 0;\n    pa_tenth_factor factor')
    ops += '''
#ifndef __riscv
/* Raw-row edge seam: same eligibility, row operator, and invalidation as the
 * public projection. Poisoning all scratch models the generic fallback's
 * documented ownership, without replacing its independent full-model tests. */
int pa_startup_bias_rows_test(double unit, uint32_t input_exponent,
    const double *weights, const double *bias, const int32_t *sums,
    uint32_t rows, uint32_t n, const int16_t *residual,
    const uint32_t *residual_exponents, double *scratch, int16_t *output,
    uint32_t *output_exponents, int32_t *statuses) {
  if (!rows || rows > 16 || !n) return -1;
  uint64_t minimum = UINT64_MAX, maximum = 0;
  for (uint32_t i = 0; i < n; ++i) {
    union { double floating; uint64_t bits; } w = {.floating = weights[i]};
    uint32_t exponent = (uint32_t)(w.bits>>52);
    if (!exponent || exponent >= 2047) { minimum = maximum = 0; break; }
    if (w.bits < minimum) minimum = w.bits;
    if (w.bits > maximum) maximum = w.bits;
  }
  pa_m5_linear linear = {.scale = weights, .bias = bias, .n = n};
  int32_t *cache = startup_bias_rows(rows, residual, residual_exponents, n, scratch);
  int reused = 0;
  for (uint32_t row = 0; row < rows; ++row) {
    reused += cache && row != 0;
    int status = startup_project_row(&linear, unit, input_exponent, sums+row*n,
        1, residual ? residual+row*n : 0, residual ? residual_exponents[row] : 0,
        minimum, maximum, (int16_t *)scratch, output+row*n, output_exponents+row,
        cache, row != 0);
    statuses[row] = status;
    if (status != 1) {
      cache = 0;
      for (uint32_t i = 0; i < n*2; ++i) ((uint32_t *)scratch)[i] = 0xa5a5a5a5;
    }
  }
  return reused;
}
#endif
'''
    source['attention_ops.c'] = ops
