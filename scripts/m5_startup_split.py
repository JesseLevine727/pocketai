"""Separate mutually exclusive ready-cache execution and full tensor capture.

Both are built from the same generated model/operators. Native regression keeps
both paths. No BRAM, stack, arithmetic or trace content gate is relaxed.
"""
from scripts.m5_iterate_sources import once
from scripts.m5_tenth_sources import function
from scripts.m5_fast_sources import ROOT, pinned


def linker():
    source = pinned(ROOT/'runtime/m5_context/memory_packed.ld',
        'e2b58ca670460745c04fd3f15571a9650bb5a279dd4bd517fe4330d324487cd8').decode()
    for section in ('context_scores', 'context_lookup'):
        source = once(source, f'*(.{section})', f'KEEP(*(.{section}))')
    return source


def derive(source):
    ops = source['attention_ops.c']
    ops = once(ops, '#if !defined(PA_STARTUP_DIAGNOSTIC) || !defined(__riscv)',
        '#if !defined(PA_STARTUP_READY_ONLY)')
    ops = once(ops, '#if defined(PA_STARTUP_DIAGNOSTIC) && defined(__riscv)',
        '#if defined(PA_STARTUP_READY_ONLY)')
    old = function(ops, 'pa_m5_attention')
    start = ops.index('typedef struct {\n  pa_tenth_factor factor;\n  const double *units;')
    end = ops.index(old)+len(old)
    signature = old[:old.index('{')]
    ops = ops[:start]+'#if !defined(PA_STARTUP_TRACE_ONLY)\n'+ops[start:end]+'''\n#else
'''+signature+'''{
  return pa_context_attention_legacy(backend, workspace, cache, layer, qkv, rows, past, context);
}
#endif
'''+ops[end:]
    source['attention_ops.c'] = ops
    source['runtime_entry.c'] = once(source['runtime_entry.c'],
        '      control->flags > 1 || !control->deadline || !control->prompt_count ||', '''#if defined(PA_STARTUP_READY_ONLY)
      control->flags != 0 ||
#elif defined(PA_STARTUP_TRACE_ONLY)
      control->flags != 1 ||
#else
      control->flags > 1 ||
#endif
      !control->deadline || !control->prompt_count ||''')
