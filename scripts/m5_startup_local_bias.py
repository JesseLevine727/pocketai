"""Store exact narrow biases beside dead-score projection scratch in BRAM."""
from scripts.m5_iterate_sources import once


def derive(source):
    ops = source['attention_ops.c']
    # Three private declarations: job, leaf copy, row argument; plus the caller.
    if ops.count('int32_t *bias_cache') != 4: raise ValueError('bias pointer shape changed')
    ops = ops.replace('int32_t *bias_cache', 'int16_t *bias_cache')
    ops = once(ops, 'static int32_t *startup_bias_rows(', 'static int16_t *startup_bias_rows(')
    ops = once(ops, '  return (int32_t *)scratch+n;', '''  /* 2*n tentative-output bytes + 2*n exact bias bytes fit the existing
   * 4-KiB score buffer for n<=1024. Larger rows keep private DDR storage. */
  return n <= 1024 ? (int16_t *)pa_context_score_storage()+n : (int16_t *)scratch+2*n;''')
    ops = once(ops, '      if (bias_cache) bias_cache[i] = rounded_bias;', '''      if (bias_cache) {
        /* This is an exact storage certificate, not bias quantization. A
         * wider value rejects tentative publication and uses the unchanged
         * complete generic row, even when cancellation could make it fit. */
        if (rounded_bias < -32768 || rounded_bias > 32767) { status = 1; break; }
        bias_cache[i] = (int16_t)rounded_bias;
      }''')
    ops = once(ops, '  int32_t *cache = startup_bias_rows(', '  int16_t *cache = startup_bias_rows(')
    # Keep per-row setup/certification out of the large generic fallback
    # caller. Retain O2: Os introduced unsupported compiler memcpy calls.
    ops = once(ops, 'static int startup_project_row(',
        'static __attribute__((noinline)) int startup_project_row(')
    ops = once(ops, '      for (uint32_t i = 0; i < n*4; ++i) ((uint32_t *)scratch)[i] = 0xa5a5a5a5;',
        '      for (uint32_t i = 0; i < n*4; ++i) ((uint32_t *)scratch)[i] = 0xa5a5a5a5;\n'
        '      for (uint32_t i = 0; i < 1024; ++i) pa_context_score_storage()[i] = (int32_t)0xa5a5a5a5;')
    ops += '\n#ifndef __riscv\nuint32_t pa_startup_local_bias_capacity(void) { return 1024; }\n#endif\n'
    source['attention_ops.c'] = ops
