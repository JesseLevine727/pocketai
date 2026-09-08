"""Exact demand-materialized V derivation, isolated from frozen eager releases."""
from scripts.m5_fast_sources import ROOT
from scripts.m5_iterate_sources import once
from scripts.m5_tenth_sources import function


def derive(source):
    ready = source['ready_cache.c']
    ready = once(ready, 'static int enabled;', '''static int enabled;
static uint32_t *startup_materialized;
static uint8_t *startup_initial_pending;
_Static_assert(0x2b200+144*32*4 <= 0x30000, "lazy bitmap overlaps smoothing");''')
    ready = once(ready, '  state = enabled ?', '''  startup_materialized = enabled ? (uint32_t *)(trace+0x2b200) : 0;
  startup_initial_pending = enabled ? trace+0x2b080 : 0;
  state = enabled ?''')
    start = ready.index('static uint32_t quantized_four(')
    end = ready.index('/* Cold phases may borrow local-score BRAM:', start)
    ready = ready[:start]+ready[end:]
    start = ready.index('/* No changed-feature dispatch')
    end = ready.index('int pa_context_prepare(', start)
    ready = ready[:start]+(ROOT/'runtime/m5_startup/lazy_values.c.inc').read_text()+'\n'+ready[end:]
    ready = ready.replace('state->version != 1', 'state->version != 2').replace('state->version = 1', 'state->version = 2')
    old = function(ready, 'pa_context_prepare')
    start = old.index('    if (past) {\n      value_job')
    end = old.index('    pa_startup_end(START_VALUES', start)
    new = old[:start]+'''    for (uint32_t i = 0; i < 32; ++i) startup_materialized[index*32+i] = 0;
    startup_initial_pending[index] = 1;
'''+old[end:]
    ready = once(ready, old, new)
    old = function(ready, 'pa_context_update_values')
    new = once(old, '  int8_t *ready = value_head(index);\n', '')
    start = new.index('#ifdef PA_CONTEXT_MASKED_VALUES')
    end = new.index('  for (uint32_t feature', start)
    new = new[:start]+new[end:]
    start = new.index('#ifdef PA_CONTEXT_MASKED_VALUES')
    end = new.index('      ++state->updated_columns;', start)
    new = new[:start]+new[end:]
    start = new.index('#ifdef PA_CONTEXT_PARALLEL_VALUES')
    end = new.index('  double unit = cache->key_units', start)
    new = new[:start]+'''  if (changed)
    for (uint32_t i = 0; i < 32; ++i) startup_materialized[index*32+i] = 0;
'''+new[end:]
    # No unused stack copy of unchanged multipliers is needed by lazy conversion.
    new = once(new, '    } else multiplier[feature] = state->multiplier[index][feature];', '    }')
    source['ready_cache.c'] = once(ready, old, new)
    ops = source['attention_ops.c']
    ops = '''#include "ready_cache.h"
int pa_startup_require_values(pa_m5_cache *, uint32_t, uint32_t, uint32_t, const int8_t *);
'''+ops
    ops = once(ops, '    pa_context_end(CTX_VMAX, detail); detail = pa_context_begin();', '''    if (pa_startup_require_values(cache, layer, head, length, probability_i8)) {
      pa_m5_workspace_rewind(workspace, mark); return -33;
    }
    pa_context_end(CTX_VMAX, detail); detail = pa_context_begin();''')
    ops = once(ops, '''    /* Maxima and consumer-ready V are maintained for the exact prefix.
     * Requantize every affected four-column group when any maximum changes. */''',
        '''    /* Full-prefix maxima; materialize every nonzero-probability V row.
     * Other rows multiply by exact integer zero, regardless of stored bytes. */''')
    source['attention_ops.c'] = ops
