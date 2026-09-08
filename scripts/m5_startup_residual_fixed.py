"""Extend the existing exact fixed-factor certificate to residual prompt rows."""
from scripts.m5_iterate_sources import once


def derive(source):
    ops = source['attention_ops.c']
    ops = once(ops, '  int32_t *bias_cache;\n  uint32_t reuse_bias;',
        '  int32_t *bias_cache;\n  uint32_t *fixed_weights;\n'
        '  uint32_t fixed_row;\n  int normalize;\n  uint32_t reuse_bias;')
    ops = once(ops, '  int32_t *bias_cache = job->bias_cache;',
        '  int32_t *bias_cache = job->bias_cache;\n'
        '  uint32_t *fixed_weights = job->fixed_weights;\n'
        '  const uint32_t fixed_row = job->fixed_row;\n'
        '  const int normalize = job->normalize;')
    ops = once(ops, '''    uint32_t multiplier = pa_startup_project_multiplier(&factor, weight[i], adjustment, shift);
    if (!multiplier || multiplier >= UINT32_C(0x80000000)) { status = 1; break; }
''', '''    int32_t sum = sums[i];
    uint32_t magnitude = sum < 0 ? 0u-(uint32_t)sum : (uint32_t)sum;
    if (magnitude > (UINT32_C(1) << 26)) { status = 1; break; }
    uint32_t fixed_weight = 0;
    if (fixed_weights) {
      if (reuse_bias) fixed_weight = fixed_weights[i];
      else {
        union { double floating; uint64_t bits; } w = {.floating = weight[i]};
        int encoded = (int)(w.bits>>52)+normalize;
        if (encoded > 0 && encoded < 2047) {
          w.bits += (uint64_t)(int64_t)normalize<<52;
          fixed_weight = pa_scalar_rne_scaled32(w.bits, 0);
        }
        fixed_weights[i] = fixed_weight;
      }
    }
    int32_t branch;
    /* The existing four-unit multiplier enclosure must collapse to one exact
     * final RNE result. Otherwise execute the unchanged full multiplier path.
     * The range certificate below sees precisely the same integer branch. */
    if (!fixed_weights || !startup_fixed_branch(sum, fixed_weight, fixed_row, shift, &branch)) {
      uint32_t multiplier = pa_startup_project_multiplier(&factor, weight[i], adjustment, shift);
      if (!multiplier || multiplier >= UINT32_C(0x80000000)) { status = 1; break; }
      if (!startup_word_affine(sum, magnitude, multiplier, shift, &branch)) { status = 1; break; }
    }
''')
    ops = once(ops, '''    int32_t sum = sums[i];
    uint32_t magnitude = sum < 0 ? 0u-(uint32_t)sum : (uint32_t)sum;
    if (magnitude > (UINT32_C(1) << 26)) { status = 1; break; }
    int32_t branch;
    if (!startup_word_affine(sum, magnitude, multiplier, shift, &branch)) { status = 1; break; }
''', '')
    ops = once(ops, '    int32_t *bias_cache, uint32_t reuse_bias) {',
        '    int32_t *bias_cache, uint32_t reuse_bias, uint32_t *fixed_weights) {')
    ops = once(ops, '  if (shift < 8) return 0;\n  startup_project_job job = {', '''  if (shift < 8) return 0;
  int normalize = 0;
  uint32_t fixed_row = 0;
  if (fixed_weights) {
    normalize = 1053-(int)(maximum_weight>>52);
    uint64_t normalized = maximum_weight+((uint64_t)(int64_t)normalize<<52);
    if (pa_scalar_rne_scaled32(normalized, 0) >= UINT32_C(0x80000000)) --normalize;
    int row_power = adjustment+(int)shift-normalize+30;
    int encoded = (int)factor.exponent+row_power;
    if (encoded > 0 && encoded < 2047) {
      union { double floating; uint64_t bits; } u = {.floating = unit};
      u.bits += (uint64_t)(int64_t)row_power<<52;
      fixed_row = pa_scalar_rne_scaled32(u.bits, 0);
    }
  }
  startup_project_job job = {''')
    ops = once(ops, '      .bias_cache = bias_cache, .reuse_bias = reuse_bias,',
        '      .bias_cache = bias_cache, .reuse_bias = reuse_bias,\n'
        '      .fixed_weights = fixed_weights, .fixed_row = fixed_row, .normalize = normalize,')
    ops = once(ops, 'scratch, output, output_exponent, 0, 0);',
        'scratch, output, output_exponent, 0, 0, 0);')
    ops = once(ops, '        bias_cache, row != 0);',
        '        bias_cache, row != 0, bias_cache ? (uint32_t *)scales : 0);')
    # Native-only row sequence uses two existing-size scratch regions, with
    # both poisoned on fallback exactly as their production owners permit.
    ops = once(ops, 'int pa_startup_bias_rows_test(', 'int pa_startup_fixed_rows_test(')
    ops = once(ops, '        cache, row != 0);',
        '        cache, row != 0, cache ? (uint32_t *)(scratch+n) : 0);')
    ops = once(ops, 'for (uint32_t i = 0; i < n*2; ++i) ((uint32_t *)scratch)[i] = 0xa5a5a5a5;',
        'for (uint32_t i = 0; i < n*4; ++i) ((uint32_t *)scratch)[i] = 0xa5a5a5a5;')
    source['attention_ops.c'] = ops
