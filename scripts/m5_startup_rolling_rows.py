"""A tagged, call-local cache that rebuilds after exponent changes/fallback."""
from scripts.m5_iterate_sources import once


def derive(source):
    ops = source['attention_ops.c']
    ops = once(ops, '''  if (rows < 2 || !residual || exponents[0] > 30) return 0;
  for (uint32_t row = 1; row < rows; ++row)
    if (exponents[row] != exponents[0]) return 0;
''', '''  (void)exponents;
  if (rows < 2 || !residual) return 0;
''')
    ops = once(ops, ''' * Equal residual exponents are required because they fix the speculative
 * candidate. A scaled/no-residual preview can change it, so never reuse there.
 * Only acceptance of the whole first row publishes this private cache. */''',
        ''' * Reuse requires the current residual exponent to match the last accepted
 * row's tag. A change or fallback rebuilds on the next row before publication.
 * Scaled/no-residual previews can change the candidate, so never reuse there.
 * Only acceptance of the whole populating row publishes this private cache. */''')
    ops = once(ops, '  int32_t *bias_cache = startup_bias_rows(rows, residual, residual_exponents, n, bias);',
        '  int32_t *bias_cache = startup_bias_rows(rows, residual, residual_exponents, n, bias);\n'
        '  uint32_t cached_exponent = UINT32_MAX;')
    ops = once(ops, '        bias_cache, row != 0, bias_cache ? (uint32_t *)scales : 0);',
        '        bias_cache, bias_cache && cached_exponent == residual_exponents[row],\n'
        '        bias_cache ? (uint32_t *)scales : 0);')
    ops = once(ops, '    if (fast) continue;\n',
        '    if (fast) {\n      if (bias_cache) cached_exponent = residual_exponents[row];\n      continue;\n    }\n')
    ops = once(ops, '    bias_cache = 0;\n    pa_tenth_factor factor',
        '    cached_exponent = UINT32_MAX;\n    pa_tenth_factor factor')
    ops = once(ops, 'int pa_startup_fixed_rows_test(', 'int pa_startup_rolling_rows_test(')
    ops = once(ops, '  int reused = 0;\n', '  int reused = 0;\n  uint32_t cached_exponent = UINT32_MAX;\n')
    ops = once(ops, '    reused += cache && row != 0;',
        '    uint32_t reuse = cache && cached_exponent == residual_exponents[row];\n    reused += reuse;')
    ops = once(ops, '        cache, row != 0, cache ? (uint32_t *)(scratch+n) : 0);',
        '        cache, reuse, cache ? (uint32_t *)(scratch+n) : 0);')
    ops = once(ops, '    if (status != 1) {\n      cache = 0;',
        '    if (status == 1) {\n      if (cache) cached_exponent = residual_exponents[row];\n    } else {\n      cached_exponent = UINT32_MAX;')
    source['attention_ops.c'] = ops
