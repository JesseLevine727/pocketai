"""Reuse prompt-row constants, pack scalar output and parallelize first use."""
from scripts.m5_fast_sources import ROOT
from scripts.m5_iterate_sources import once
from scripts.m5_tenth_sources import function


def derive(source):
    ops = source['attention_ops.c']
    ops = once(ops, 'static int startup_smooth_once(',
        (ROOT/'runtime/m5_startup/smooth_batch.c.inc').read_text()+'\nstatic int startup_smooth_once(')
    ops = once(ops, '  int status = pa_context_parallel(startup_smooth_leaf, &job, count);', '''  int status;
  if (!(columns&31u) && !((uintptr_t)input&3u) && shift && shift <= 31)
    status = pa_context_parallel(startup_smooth_batch_leaf, &job, columns);
  else status = pa_context_parallel(startup_smooth_leaf, &job, count);''')
    ops = once(ops, '    for (uint32_t i = 0; i < columns; ++i) reciprocal[i] = pa_tenth_reciprocal(smoothing[i]);', '''    startup_reciprocal_job job = {smoothing, reciprocal};
    if (pa_context_parallel(startup_reciprocal_leaf, &job, columns)) {
      pa_m5_workspace_rewind(workspace, mark); return -40;
    }''')
    # Fast word finalizer, with the FULL existing product as fallback. Its
    # successful range leaves ample signed-32 space for the bias addition.
    old = '''      int64_t v0 = pa_scalar_rne_product(sums[row*n+i], m0, shift)+b0;
      int64_t v1 = pa_scalar_rne_product(sums[row*n+i+1], m1, shift)+b1;'''
    new = '''      int32_t s0 = sums[row*n+i], s1 = sums[row*n+i+1], q0_word, q1_word;
      uint32_t a0 = s0 < 0 ? 0u-(uint32_t)s0 : (uint32_t)s0;
      uint32_t a1 = s1 < 0 ? 0u-(uint32_t)s1 : (uint32_t)s1;
      int64_t v0 = (startup_word_affine(s0, a0, m0, shift, &q0_word) ?
          (int64_t)q0_word : pa_scalar_rne_product(s0, m0, shift))+b0;
      int64_t v1 = (startup_word_affine(s1, a1, m1, shift, &q1_word) ?
          (int64_t)q1_word : pa_scalar_rne_product(s1, m1, shift))+b1;'''
    ops = once(ops, old, new)
    source['attention_ops.c'] = ops
    numerics = '#include "parallel.h"\n'+source['numerics.c']
    old = function(numerics, 'pa_m5_layernorm_metadata')
    start = old.index('  for (uint32_t i = 0; i < count; ++i) {\n    /* Retain the two ordered')
    end = old.index('  *factor_out = factor;', start)
    new = old[:start]+'''  startup_norm_job job = {gain, bias, gain_q12, bias_q8, correction,
                           exponent, factor_shift, {0, 0}};
  if ((uintptr_t)gain_q12&3u) startup_norm_leaf(&job, 0, count, 0);
  else if (pa_context_parallel(startup_norm_leaf, &job, count)) return -2;
  if (job.status[0] || job.status[1]) return -2;
'''+old[end:]
    numerics = once(numerics, old, (ROOT/'runtime/m5_startup/norm_parallel.c.inc').read_text()+'\n'+new)
    source['numerics.c'] = numerics
