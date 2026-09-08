"""Certify final rounded branch to avoid oversolving metadata precision."""
from scripts.m5_iterate_sources import once


def derive(source):
    ops = '#include "shared_factor.h"\n#include "certified_branch.h"\n'+source['attention_ops.c']
    # Preserve the original body as fallback, sharing it between both callers.
    marker = 'static void startup_batch_leaf('
    helper = '''static __attribute__((noinline)) int64_t startup_final_branch(
    const pa_tenth_factor *factor, double weight, uint32_t adjustment,
    uint32_t shift, int32_t sum) {
  int32_t result;
  if (startup_certified_branch(factor, weight, adjustment, shift, sum, &result)) return result;
  uint32_t multiplier = pa_startup_project_multiplier(factor, weight, adjustment, shift);
  return pa_scalar_rne_product(sum, multiplier, shift);
}
'''
    ops = once(ops, marker, helper+marker)
    start = ops.index('      uint32_t m0 = pa_startup_project_multiplier(job->factors+row')
    end = ops.index('      int16_t q0 = v0 < -32768', start)
    ops = ops[:start]+'''      int64_t v0 = startup_final_branch(job->factors+row, w0, adjustment, shift, sums[row*n+i])+b0;
      int64_t v1 = startup_final_branch(job->factors+row, w1, adjustment, shift, sums[row*n+i+1])+b1;
'''+ops[end:]
    source['attention_ops.c'] = ops
    # The metadata reduction is small and cold relative to the shared finalizer.
    # Keep the unchanged code/local-score boundary, with no stack reduction.
    source['numerics.c'] = once(source['numerics.c'], 'int pa_m5_layernorm_metadata(',
        'int __attribute__((optimize("Os", "no-tree-loop-distribute-patterns"))) pa_m5_layernorm_metadata(')
    source['ready_cache.c'] = once(source['ready_cache.c'], 'int pa_context_prepare(',
        'int __attribute__((optimize("Os", "no-tree-loop-distribute-patterns"))) pa_context_prepare(')
