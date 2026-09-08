"""Remove narrow DDR writes/copies and avoid widening a proven int32 sum."""
from scripts.m5_fast_sources import ROOT
from scripts.m5_iterate_sources import once
from scripts.m5_tenth_sources import function


def derive(source):
    ops = '#include "bounded_quant.h"\n'+source['attention_ops.c']
    ops = once(ops, 'static void startup_batch_leaf(', '''static __attribute__((noinline)) int16_t startup_wide_saturate(
    int32_t sum, uint32_t multiplier, uint32_t shift, int32_t bias) {
  int64_t value = pa_scalar_rne_product(sum, multiplier, shift)+bias;
  return value < -32768 ? -32768 : value > 32767 ? 32767 : (int16_t)value;
}
static inline int16_t startup_narrow_saturate(int32_t sum, uint32_t multiplier,
                                             uint32_t shift, int32_t bias) {
  uint32_t magnitude = sum < 0 ? 0u-(uint32_t)sum : (uint32_t)sum;
  int32_t value;
  if (!startup_word_affine(sum, magnitude, multiplier, shift, &value))
    return startup_wide_saturate(sum, multiplier, shift, bias);
  /* Preflight bounds bias strictly within +/-2^29. No signed overflow. */
  value += bias;
  return value < -32768 ? -32768 : value > 32767 ? 32767 : (int16_t)value;
}
static void startup_batch_leaf(''')
    start = ops.index('      int32_t s0 = sums[row*n+i]')
    end = ops.index('      ((startup_word *)(output+row*n))', start)
    ops = ops[:start]+'''      int16_t q0 = startup_narrow_saturate(sums[row*n+i], m0, shift, b0);
      int16_t q1 = startup_narrow_saturate(sums[row*n+i+1], m1, shift, b1);
'''+ops[end:]
    old = ops[ops.index('startup_batch_project('):ops.index('\nint pa_m5_project(')]
    new = once(old, 'if (magnitude >= UINT32_C(0x80000000)) return 0;',
        'if (magnitude >= (UINT32_C(1)<<29)) return 0;')
    ops = once(ops, old, new)
    old = function(ops, 'pa_m5_attention')
    start = old.index('  for (uint32_t row = 0; row < rows; ++row) for (uint32_t head = 0; head < 12; ++head) {')
    end = old.index('  pa_context_end(CTX_APPEND, detail);', start)
    new = old[:start]+'''  for (uint32_t head = 0; head < 12; ++head) {
    int appended = startup_append_head(cache, layer, head, past, rows, qkv);
    if (appended) { pa_m5_workspace_rewind(workspace, mark); return appended; }
  }
'''+old[end:]
    new = new.replace('pa_scalar_quantize24(', 'pa_startup_signed_quant(')
    new = once(new, '''    for (uint32_t feature = 0; feature < 64; ++feature)
      value_units[feature] = pa_context_value_units(layer, head)[feature];''',
        '    value_units = (double *)pa_context_value_units(layer, head);')
    # The packed helper retains explicit narrow reads for unaligned qkv.
    ops = once(ops, old, (ROOT/'runtime/m5_startup/append_packed.c.inc').read_text()+'\n'+new)
    ops = once(ops, 'static int startup_append_head(',
        'static int __attribute__((optimize("Os", "no-tree-loop-distribute-patterns"))) startup_append_head(')
    ops = once(ops, 'static uint64_t cache_vector(',
        'static uint64_t __attribute__((unused)) cache_vector(')
    source['attention_ops.c'] = ops
    source['ready_cache.c'] = once(source['ready_cache.c'], 'int pa_context_prepare(',
        'int __attribute__((optimize("Os", "no-tree-loop-distribute-patterns"))) pa_context_prepare(')
