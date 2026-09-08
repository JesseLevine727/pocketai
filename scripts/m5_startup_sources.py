"""Derive cold/prefill instrumentation without editing the closed context release."""
import argparse
import json
from pathlib import Path
from scripts.m5_fast_sources import ROOT, pinned
from scripts.m5_iterate_sources import once
from scripts.m5_tenth_sources import function
from scripts.m5_sweep_policy import sha

PARENT = 'fba00cff33d41f707d620f4de1a247f60b17520c12d8178790794316f5446e63'
READY = '7ab0d5ef8e2ab4a498372f57868d7be8a491d4b49929eee13b63f384a6e2c6a9'


def instrument_ready(source):
    old = function(source, 'pa_context_prepare')
    new = once(old, '    uint32_t maximum[64], multiplier[64];',
        '    uint64_t total = pa_startup_begin(), stamp = total;\n    uint32_t maximum[64], multiplier[64];')
    new = once(new, '    double maximum_unit = 0;',
        '    pa_startup_end(START_TRANSPOSE, stamp); stamp = pa_startup_begin();\n    double maximum_unit = 0;')
    new = once(new, '    state->key_maximum_unit[index] = maximum_unit;',
        '    pa_startup_end(START_SCAN, stamp); stamp = pa_startup_begin();\n    state->key_maximum_unit[index] = maximum_unit;')
    new = once(new, '    for (uint32_t feature = 0; feature < 64; feature += 4)\n      rebuild_group',
        '    pa_startup_end(START_UNITS, stamp); stamp = pa_startup_begin();\n    for (uint32_t feature = 0; feature < 64; feature += 4)\n      rebuild_group')
    new = once(new, '    state->valid[index] = past;',
        '    pa_startup_end(START_VALUES, stamp); pa_startup_end(START_INIT_TOTAL, total);\n    state->valid[index] = past;')
    return '#include "detail.h"\n'+once(source, old, new)


def instrument_ops(source):
    old = function(source, 'pa_m5_project')
    new = once(old, '  if (pa_fast_quantize(', '  uint64_t stamp = pa_startup_begin();\n  if (pa_fast_quantize(')
    new = once(new, '  for (uint32_t tile = 0;',
        '  pa_startup_end(START_PROJECT_QUANT, stamp); stamp = pa_startup_begin();\n  for (uint32_t tile = 0;')
    new = once(new, '  for (uint32_t row = 0; row < rows; ++row) {\n    pa_tenth_factor',
        '  pa_startup_end(START_PROJECT_GEMM, stamp);\n  for (uint32_t row = 0; row < rows; ++row) {\n    stamp = pa_startup_begin();\n    pa_tenth_factor')
    new = once(new, '    int status = pa_search_project_affine',
        '    pa_startup_end(START_PROJECT_SCALE, stamp); stamp = pa_startup_begin();\n    int status = pa_search_project_affine')
    new = once(new, '    if (residual) {',
        '    pa_startup_end(START_PROJECT_AFFINE, stamp); stamp = pa_startup_begin();\n    if (residual) {')
    new = once(new, '  }\n  pa_m5_workspace_rewind(workspace, mark); return 0;',
        '    pa_startup_end(START_PROJECT_RESIDUAL, stamp);\n  }\n  pa_m5_workspace_rewind(workspace, mark); return 0;')
    source = once(source, old, new)
    prefix, suffix = source.split('#undef pa_m5_smooth', 1)
    old = function(suffix, 'pa_m5_smooth')
    new = once(old, '  uint32_t shift;', '  uint64_t stamp = pa_startup_begin();\n  uint32_t shift;')
    new = once(new, '  int any_overflow = 0;',
        '  pa_startup_end(START_SMOOTH_SETUP, stamp); stamp = pa_startup_begin();\n  int any_overflow = 0;')
    new = once(new, '  if (any_overflow) {\n    for (uint32_t i',
        '  pa_startup_end(START_SMOOTH_SCAN, stamp); stamp = pa_startup_begin();\n  if (any_overflow) {\n    for (uint32_t i')
    new = once(new, '  pa_m5_workspace_rewind(workspace, mark); return 0;',
        '  pa_startup_end(START_SMOOTH_ROWS, stamp);\n  pa_m5_workspace_rewind(workspace, mark); return 0;')
    source = prefix+'#undef pa_m5_smooth'+once(suffix, old, new)
    # Diagnostic entry always binds the optimized cache and does not capture
    # full tensors. Omit its unreachable legacy copy to fit instrumentation.
    old = function(source, 'pa_context_attention_legacy')
    source = once(source, old, '#if !defined(PA_STARTUP_DIAGNOSTIC) || !defined(__riscv)\n'+old+'\n#endif')
    source = once(source, '''  if (!pa_context_enabled(cache))
    return pa_context_attention_legacy(backend, workspace, cache, layer, qkv, rows, past, context);''',
        '''  if (!pa_context_enabled(cache)) {
#if defined(PA_STARTUP_DIAGNOSTIC) && defined(__riscv)
    return -90;
#else
    return pa_context_attention_legacy(backend, workspace, cache, layer, qkv, rows, past, context);
#endif
  }''')
    return '#include "detail.h"\n'+source


def local_affine(source):
    source = once(source, '  uint32_t *multipliers;\n  int32_t *bias;',
        '  uint32_t *multipliers;\n  int32_t *bias;\n  const int32_t *input;\n  int32_t *result;')
    start = source.index('static void pa_context_affine_leaf(')
    end = source.index('static int pa_search_project_affine(', start)
    source = source[:start]+(ROOT/'runtime/m5_startup/local_affine.c.inc').read_text()+source[end:]
    old = function(source, 'pa_search_project_affine')
    new = once(old, '  job.scales = scales;', '  job.input = input; job.result = result;\n  job.scales = scales;')
    start = new.index('  for (uint32_t offset = 0; offset < count; offset += 3072) {')
    end = new.index('  pa_m5_workspace_rewind(workspace, mark); return 0;', start)
    new = new[:start]+'''  uint32_t i = 0;
  if (!((uintptr_t)output & 3u)) {
    typedef uint32_t packed_alias __attribute__((__may_alias__));
    packed_alias *packed = (packed_alias *)output;
    for (; i+1 < count; i += 2)
      packed[i/2] = (uint16_t)result[i] | (uint32_t)(uint16_t)result[i+1] << 16;
  }
  for (; i < count; ++i) output[i] = (int16_t)result[i];
'''+new[end:]
    return once(source, old, new)


def generate(output, variant):
    inline_fixed = variant == 'inline_fixed'
    inline_product = variant == 'inline_product'
    local_bias = variant == 'local_bias'
    local_rows = variant in ('local_rows', 'local_bias')
    rolling_fixed = variant in ('rolling_fixed', 'local_rows', 'local_bias')
    residual_fixed = variant in ('residual_fixed', 'rolling_fixed', 'local_rows', 'local_bias')
    bias_reuse = variant in ('bias_reuse', 'residual_fixed', 'rolling_fixed', 'local_rows', 'local_bias')
    if inline_fixed or inline_product or bias_reuse: variant = 'split_fixed'
    requested_variant = variant
    if variant == 'split_fixed': variant = 'fixed_branch'
    if variant in ('certified_branch', 'packed_attention', 'fixed_branch'): variant = 'scalar_batch'
    if variant in ('lazy_values', 'scalar_batch'): variant = 'batch_project'
    if variant == 'implicit_product': variant = 'batch_project'
    batch_variant = variant == 'batch_project'
    if variant == 'batch_project': variant = 'range_hint'
    hint_variant = variant == 'range_hint'
    if variant == 'range_hint': variant = 'word_affine'
    if variant == 'leaf_profile': variant = 'word_affine'
    if variant == 'cold_features': variant = 'word_affine'
    word_variant = variant == 'word_affine'
    if variant == 'word_affine': variant = 'quant_parallel'
    quant_variant = variant == 'quant_parallel'
    if quant_variant: variant = 'smooth_once'
    smooth_variant = variant == 'smooth_once'
    if smooth_variant: variant = 'extrema_scan'
    inherited_variant = variant
    if variant in ('interval_product', 'packed_ops', 'extrema_scan', 'high_product'): variant = 'register_values'
    pinned(ROOT/'scripts/m5_context_sources.py', PARENT)
    from scripts.m5_context_sources import generate as parent
    parent(output, 'masked')
    source = {p.name: p.read_text() for p in output.glob('*.c')}
    ready = pinned(ROOT/'runtime/m5_context/ready_cache.c', READY).decode()
    if variant in ('cold_parallel', 'cold_lut', 'local_affine', 'bounded_cache', 'fused_project', 'register_values'):
        start = ready.index('static void transpose_keys(')
        end = ready.index('static uint32_t quantized_four(', start)
        ready = ready[:start]+ready[end:]
        # Rebuild is only needed by the replaced serial cold phase and the
        # inactive feature-partition variant; the retained masked job is shared.
        start = ready.index('static void rebuild_group(')
        end = ready.index('#ifdef PA_CONTEXT_PARALLEL_VALUES', start)
        ready = ready[:start]+ready[end:]
        old = function(ready, 'pa_context_prepare')
        cold = (ROOT/'runtime/m5_startup/cold_prepare.c.inc').read_text()
        if variant in ('bounded_cache', 'fused_project', 'register_values'):
            start = cold.index('static void startup_scan(')
            end = cold.index('int pa_context_prepare(', start)
            scan = 'cold_extrema_scan.c.inc' if inherited_variant in ('extrema_scan', 'high_product') else 'cold_register_scan.c.inc'
            cold = cold[:start]+(ROOT/'runtime/m5_startup'/scan).read_text()+cold[end:]
            cold = once(cold, '    for (uint32_t i = 0; i < 256; ++i) temporary[i] = tile[i];',
                '''    for (uint32_t i = 0; i < 256; ++i) temporary[i] = tile[i];
    uint32_t valid = job->past-block*16;
    if (valid < 16) for (uint32_t i = valid*16; i < 256; ++i) temporary[i] = 0;''')
            cold = once(cold, '        uint32_t position = block*16+column;\n', '')
            for ordinal, name in enumerate(('a', 'b', 'c', 'd')):
                row = 'column' if not ordinal else f'(column+{ordinal})'
                position = 'position' if not ordinal else f'position+{ordinal}'
                cold = once(cold,
                    f'uint32_t {name} = {position} < job->past ? temporary[{row}*16+feature/4] : 0;',
                    f'uint32_t {name} = temporary[{row}*16+feature/4];')
        if variant == 'register_values':
            cold = once(cold, 'int pa_context_prepare(',
                (ROOT/'runtime/m5_startup/cold_register_values.c.inc').read_text()+'\nint pa_context_prepare(')
            cold = once(cold, 'pa_context_parallel(update_groups, &job, past)',
                'pa_context_parallel(startup_register_values, &job, past)')
        if variant in ('cold_lut', 'local_affine'):
            cold = once(cold, 'int pa_context_prepare(',
                (ROOT/'runtime/m5_startup/cold_lut_values.c.inc').read_text()+'\nint pa_context_prepare(')
            cold = once(cold, '      if (pa_context_parallel(update_groups, &job, past)) return -40;',
                '      if (pa_context_parallel(past >= 512 ? startup_lut_values : update_groups, &job, past)) return -40;')
        ready = once(ready, old, cold)
        if variant in ('bounded_cache', 'fused_project', 'register_values'):
            ready = '#include "bounded_quant.h"\n'+ready.replace('pa_scalar_quantize24(', 'pa_startup_bounded_quant(')
            if variant == 'register_values': ready = ready.replace('pa_startup_bounded_quant(', 'pa_startup_signed_quant(')
        source['ready_cache.c'] = '#include "detail.h"\n'+ready
    else:
        source['ready_cache.c'] = instrument_ready(ready)
    if variant in ('local_affine', 'bounded_cache', 'fused_project', 'register_values') and not smooth_variant:
        source['attention_ops.c'] = local_affine(source['attention_ops.c'])
    source['attention_ops.c'] = instrument_ops(source['attention_ops.c'])
    if variant in ('fused_project', 'register_values'):
        ops = source['attention_ops.c']
        ops = once(ops, 'int pa_m5_project(', (ROOT/'runtime/m5_startup/fused_project.c.inc').read_text()+'\nint pa_m5_project(')
        ops = once(ops, '  for (uint32_t row = 0; row < rows; ++row) {\n    stamp = pa_startup_begin();\n    pa_tenth_factor', '''  uint64_t minimum_weight = UINT64_MAX, maximum_weight = 0;
  for (uint32_t i = 0; i < n; ++i) {
    union { double floating; uint64_t bits; } v = {.floating = linear->scale[i]};
    uint32_t encoded = (uint32_t)(v.bits >> 52);
    if (!encoded || encoded >= 2047) { minimum_weight = maximum_weight = 0; break; }
    if (v.bits < minimum_weight) minimum_weight = v.bits;
    if (v.bits > maximum_weight) maximum_weight = v.bits;
  }
  for (uint32_t row = 0; row < rows; ++row) {
    stamp = pa_startup_begin();
    int fast = startup_project_row(linear, units[row], input_exponents[row], sums+row*n,
        scaled, residual ? residual+row*n : 0, residual ? residual_exponents[row] : 0,
        minimum_weight, maximum_weight, (int16_t *)bias, output+row*n, output_exponents+row);
    pa_startup_end(START_PROJECT_AFFINE, stamp); stamp = pa_startup_begin();
    if (fast < 0) { pa_m5_workspace_rewind(workspace, mark); return fast; }
    if (fast) continue;
    pa_tenth_factor''')
        source['attention_ops.c'] = ops
    if inherited_variant in ('interval_product', 'packed_ops', 'extrema_scan', 'high_product'):
        ops = source['attention_ops.c']
        product = 'high_product.h' if inherited_variant == 'high_product' else 'interval_product.h'
        ops = f'#include "{product}"\n'+ops
        ops = once(ops, '''    union { double floating; uint64_t bits; } scale = {
        .floating = pa_tenth_mul_factor(&factor, weight[i])}, b = {.floating = bias[i]};
    scale.bits += (uint64_t)adjustment << 32;
    uint32_t multiplier = pa_scalar_rne_scaled32(scale.bits, shift);''', '''    union { double floating; uint64_t bits; } b = {.floating = bias[i]};
    uint32_t multiplier = pa_startup_project_multiplier(&factor, weight[i], adjustment, shift);''')
        source['attention_ops.c'] = ops
    if inherited_variant in ('packed_ops', 'extrema_scan', 'high_product'):
        ops = source['attention_ops.c']
        ops = '#define PA_STARTUP_SHARED_PRODUCT\n#include "packed_io.h"\n'+ops
        # Preserve the complete legacy trace path within the unchanged 48-KiB
        # code gate. Only this non-primary trace/fallback function uses -Os.
        ops = once(ops, 'static int pa_context_attention_legacy(',
            'static int __attribute__((optimize("Os", "no-tree-loop-distribute-patterns"))) pa_context_attention_legacy(')
        ops = once(ops, 'int pa_m5_attention(', (ROOT/'runtime/m5_startup/attention_output.c.inc').read_text()+'\nint pa_m5_attention(')
        old = '''    for (uint32_t feature = 0; feature < 64; ++feature)
      { scales[feature] = probability_unit * value_units[feature] * 256.0;
        zero_bias[feature] = 0.0; }
    status = affine_row(backend, workspace, value_sums, scales, zero_bias, 64,
                        PA_M5_SFPU_AFFINE, value_output);
    if (status) { pa_m5_workspace_rewind(workspace, mark); return status - 20; }'''
        attention = function(ops, 'pa_m5_attention')
        replaced = once(attention, old, '''    status = startup_attention_output(value_sums, probability_unit, value_units, value_output);
    if (status < 0) { pa_m5_workspace_rewind(workspace, mark); return status; }
    if (!status) {
'''+old+'''\n    }''')
        ops = once(ops, attention, replaced)
        replacements = {
          'for (uint32_t i = 0; i < columns; ++i) x_plane[i] = input[row*columns+i];':
            'startup_expand(input+row*columns, x_plane, columns);',
          'for (uint32_t i = 0; i < columns; ++i) output[row*columns+i] = (int16_t)result[i];':
            'startup_pack(result, output+row*columns, columns);',
          'for (uint32_t i = 0; i < length; ++i) source[i] = input[offset+i];':
            'startup_expand(input+offset, source, length);',
          'for (uint32_t i = 0; i < length; ++i) output[offset+i] = (int16_t)result[i];':
            'startup_pack(result, output+offset, length);',
        }
        for old, new in replacements.items(): ops = once(ops, old, new)
        # Both retained generic smoothing and its optimized wrapper expand here.
        old = 'for (uint32_t i = 0; i < columns; ++i) expanded[i] = input[row*columns+i];'
        if ops.count(old) != 2: raise ValueError('smoothing expand derivation drift')
        ops = ops.replace(old, 'startup_expand(input+row*columns, expanded, columns);')
        source['attention_ops.c'] = ops
    if smooth_variant:
        prefix, suffix = source['attention_ops.c'].split('#undef pa_m5_smooth', 1)
        suffix = once(suffix, 'int pa_m5_smooth(', (ROOT/'runtime/m5_startup/smooth_once.c.inc').read_text()+'\nint pa_m5_smooth(')
        suffix = once(suffix, '  int any_overflow = 0;', '''  int fast = startup_smooth_once(workspace, input, multipliers, shift, rows, columns, output, exponents);
  pa_startup_end(START_SMOOTH_SCAN, stamp); stamp = pa_startup_begin();
  if (fast) { pa_m5_workspace_rewind(workspace, mark); return fast < 0 ? fast : 0; }
  int any_overflow = 0;''')
        ops = prefix+'#undef pa_m5_smooth'+suffix
        # Cold generic projection fallback, not the certified hot path.
        ops = once(ops, 'static void pa_context_project_leaf(',
            'static void __attribute__((optimize("Os", "no-tree-loop-distribute-patterns"))) pa_context_project_leaf(')
        ops = once(ops, 'static int pa_search_project_affine(',
            'static int __attribute__((optimize("Os", "no-tree-loop-distribute-patterns"))) pa_search_project_affine(')
        source['attention_ops.c'] = ops
    if quant_variant:
        source['attention_ops.c'] = once(source['attention_ops.c'], 'static void pa_context_affine_leaf(',
            'static void __attribute__((optimize("Os", "no-tree-loop-distribute-patterns"))) pa_context_affine_leaf(')
        requant = source['requant.c']
        requant = once(requant, function(requant, 'pa_m5_requant_offload'),
            (ROOT/'runtime/m5_startup/quant_parallel.c.inc').read_text())
        source['requant.c'] = requant
    if word_variant:
        ops = '#include "word_affine.h"\n'+source['attention_ops.c']
        ops = once(ops, '''    int64_t branch = pa_scalar_rne_product(sum, multiplier, shift);
    if (branch <= -(INT64_C(1) << 29) || branch >= (INT64_C(1) << 29)) { status = 1; break; }
    int32_t value = (int32_t)branch+rounded_bias;''', '''    int32_t branch;
    if (!startup_word_affine(sum, magnitude, multiplier, shift, &branch)) { status = 1; break; }
    int32_t value = branch+rounded_bias;''')
        source['attention_ops.c'] = ops
    if hint_variant:
        ops = source['attention_ops.c']
        original = function(ops, 'startup_project_row')
        row = once(original, '  union { uint64_t bits; double floating; } minimum = {.bits = minimum_weight},', '''  if (scaled && !residual) {
    /* A small subset is a lower bound, never a claimed full-vector range.
     * The full-row certificate below still proves the chosen exponent.
     * This avoids a predictably wrong zero-exponent first attempt for heads
     * whose logits all have a large common magnitude. No input is memoized. */
    double sample_scales[4];
    pa_context_project_job preview;
    preview.factor = factor; preview.linear = linear; preview.sums = sums;
    preview.residual = 0; preview.scales = sample_scales;
    preview.input_exponent = input_exponent; preview.residual_exponent = 0; preview.range = 1;
    pa_context_project_leaf(&preview, 0, linear->n < 4 ? linear->n : 4, 0);
    union { uint64_t bits; double floating; } sample = {.bits = preview.maximum[0]};
    candidate = pa_m5_storage_exponent(sample.floating);
    if (candidate > 30) return 0;
  }
  union { uint64_t bits; double floating; } minimum = {.bits = minimum_weight},''')
        source['attention_ops.c'] = once(ops, original, row)
    if batch_variant:
        ops = source['attention_ops.c']
        ops = '#include "shared_factor.h"\n'+ops
        ops = once(ops, 'int pa_m5_project(', (ROOT/'runtime/m5_startup/batch_project.c.inc').read_text()+'\nint pa_m5_project(')
        ops = once(ops, '  for (uint32_t row = 0; row < rows; ++row) {\n    stamp = pa_startup_begin();\n    int fast = startup_project_row', '''  if (!scaled && !residual) {
    stamp = pa_startup_begin();
    int batched = startup_batch_project(linear, units, input_exponents, rows, sums,
        minimum_weight, maximum_weight, (int32_t *)bias, output, output_exponents);
    pa_startup_end(START_PROJECT_AFFINE, stamp);
    if (batched) { pa_m5_workspace_rewind(workspace, mark); return batched < 0 ? batched : 0; }
  }
  for (uint32_t row = 0; row < rows; ++row) {
    stamp = pa_startup_begin();
    int fast = startup_project_row''')
        source['attention_ops.c'] = ops
    if requested_variant in ('implicit_product', 'scalar_batch', 'certified_branch', 'packed_attention', 'fixed_branch', 'split_fixed'):
        source['attention_ops.c'] = once(source['attention_ops.c'], '#include "interval_product.h"',
            '#include "implicit_product.h"')
    if requested_variant in ('lazy_values', 'scalar_batch', 'certified_branch', 'packed_attention', 'fixed_branch', 'split_fixed'):
        from scripts.m5_startup_lazy import derive
        derive(source)
    if requested_variant in ('scalar_batch', 'certified_branch', 'packed_attention', 'fixed_branch', 'split_fixed'):
        from scripts.m5_startup_scalar_batch import derive
        derive(source)
    if requested_variant == 'certified_branch':
        from scripts.m5_startup_branch import derive
        derive(source)
    if requested_variant in ('packed_attention', 'fixed_branch', 'split_fixed'):
        from scripts.m5_startup_packed_attention import derive
        derive(source)
    if requested_variant in ('fixed_branch', 'split_fixed'):
        from scripts.m5_startup_fixed import derive
        derive(source)
    if requested_variant == 'split_fixed':
        from scripts.m5_startup_split import derive, linker
        derive(source)
        (output/'memory.ld').write_text(linker())
    if requested_variant == 'leaf_profile':
        ops = source['attention_ops.c']
        ops = once(ops, '  const startup_project_job *job = opaque;',
            '  uint64_t leaf_instructions = pa_startup_instructions(), leaf_start = pa_startup_begin();\n  const startup_project_job *job = opaque;')
        ops = once(ops, '  ((startup_project_job *)opaque)->status[worker] = status;',
            '  ((startup_project_job *)opaque)->status[worker] = status;\n  pa_startup_leaf_end(worker, leaf_start, leaf_instructions);')
        source['attention_ops.c'] = ops
    if requested_variant == 'cold_features':
        old = (ROOT/'runtime/m5_startup/cold_register_values.c.inc').read_text()
        new = once(old, '  const uint32_t *multipliers = job->multipliers;',
            '  const uint32_t *multipliers = job->multipliers;\n  const uint32_t length = job->position+1;')
        new = once(new, 'for (uint32_t feature = 0; feature < 64; feature += 4)',
            'for (uint32_t feature = first; feature < end; feature += 4)')
        new = once(new, 'values+first*64+feature', 'values+feature')
        new = once(new, 'feature%16+first*16', 'feature%16')
        new = once(new, 'uint32_t position = first; position < end;', 'uint32_t position = 0; position < length;')
        ready = once(source['ready_cache.c'], old, new)
        source['ready_cache.c'] = once(ready, 'pa_context_parallel(startup_register_values, &job, past)',
            'pa_context_parallel(startup_register_values, &job, 64)')
    profile = '#include "detail.h"\n'+source['attention_profile.c']
    profile = once(profile, 'control->command != 2 || control->count != 1 || control->generated != 1 ||',
        'control->command != 2 || !control->count || control->count > 16 || control->generated != 1 ||')
    profile = once(profile, 'control->flags > 1 || !control->deadline || !control->past ||\n      control->past >= 1024',
        'control->flags > 1 || !control->deadline || control->past >= 1024 ||\n      control->count > 1024-control->past')
    profile = once(profile, '  uint64_t start = cycles(); previous_time = start;',
        '  uint64_t start = cycles(); previous_time = start;\n  pa_startup_reset();')
    profile = once(profile, 'pa_m5_forward_chunk(&runtime, token, 1, control->past,',
        'pa_m5_forward_chunk(&runtime, token, control->count, control->past,')
    profile = once(profile, 'control->generated_count = 1; ++control->past;',
        'control->generated_count = 1; control->past += control->count;')
    source['attention_profile.c'] = profile
    if inline_fixed:
        # Exact same operations; use the space freed by the split images to
        # remove the per-element ABI call/spill overhead in batched projection.
        header = pinned(ROOT/'runtime/m5_startup/fixed_branch.h',
            '70d16e7fa7081f6621dd9b11efb42e0ff382c045e4ec5f8a179c24c9cb276ea9').decode()
        source['fixed_branch.h'] = once(header,
            'static __attribute__((noinline, unused)) int startup_fixed_branch(',
            'static inline __attribute__((always_inline, unused)) int startup_fixed_branch(')
        source['attention_ops.c'] = once(source['attention_ops.c'],
            'static __attribute__((noinline)) int16_t startup_narrow_saturate(',
            'static inline __attribute__((always_inline)) int16_t startup_narrow_saturate(')
    if inline_product:
        # Inline only the general projection leaf. Inlining all call sites
        # overflowed the diagnostic image; retain that experiment, not its
        # memory overrun. The cold/batch callers keep the original shared helper.
        header = pinned(ROOT/'runtime/m5_startup/implicit_product.h',
            'd904a5186efc122ed66cbc92993673de93d74ad919e3e7e07d4226ad51849281').decode()
        body = header[header.index('uint32_t pa_startup_project_multiplier('):header.rindex('\n}\n')+2]
        body = once(body, 'pa_startup_project_multiplier(', 'pa_startup_inline_multiplier(')
        source['inline_product.h'] = ('#include "implicit_product.h"\n'
            'static inline __attribute__((always_inline))\n'+body+'\n')
        ops = once(source['attention_ops.c'], '#include "implicit_product.h"', '#include "inline_product.h"')
        start = ops.index('static void startup_project_leaf(')
        end = ops.index('{', start)+1
        depth = 1
        while depth:
            depth += (ops[end] == '{')-(ops[end] == '}')
            end += 1
        leaf = ops[start:end]
        ops = once(ops, leaf, once(leaf, 'pa_startup_project_multiplier(', 'pa_startup_inline_multiplier('))
        source['attention_ops.c'] = ops
    if bias_reuse:
        from scripts.m5_startup_bias_reuse import derive
        derive(source)
    if residual_fixed:
        from scripts.m5_startup_residual_fixed import derive
        derive(source)
    if rolling_fixed:
        from scripts.m5_startup_rolling_rows import derive
        derive(source)
    if local_rows:
        # Attention and projection are sequential. Every parallel attention
        # leaf has joined before projection starts, so its 4-KiB score storage
        # is dead here. The two projection workers own disjoint aligned slices.
        # Keep all original workspace reservations and the large-row fallback.
        source['attention_ops.c'] = once(source['attention_ops.c'],
            '  uint32_t candidate = residual ? residual_exponent : 0;',
            '  if (linear->n <= 2048) scratch = (int16_t *)pa_context_score_storage();\n'
            '  uint32_t candidate = residual ? residual_exponent : 0;')
        source['attention_ops.c'] += ('\n#ifndef __riscv\n'
            'uint32_t pa_startup_local_project_capacity(void) { return 2048; }\n#endif\n')
    if local_bias:
        from scripts.m5_startup_local_bias import derive
        derive(source)
    for name, value in source.items(): (output/name).write_text(value)
    (output/'startup_derivation.json').write_text(json.dumps(dict(schema=1,
        variant='local_bias' if local_bias else 'local_rows' if local_rows else 'rolling_fixed' if rolling_fixed else 'residual_fixed' if residual_fixed else 'bias_reuse' if bias_reuse else 'inline_product' if inline_product else 'inline_fixed' if inline_fixed else requested_variant,
        parent_sha256=PARENT, ready_sha256=READY,
        files={p.name: sha(p) for p in sorted(output.iterdir()) if p.suffix in ('.c', '.ld', '.h')}), indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('output', type=Path)
    p.add_argument('--variant', choices=('baseline', 'cold_parallel', 'cold_lut', 'local_affine', 'bounded_cache', 'fused_project', 'register_values', 'interval_product', 'packed_ops', 'extrema_scan', 'high_product', 'smooth_once', 'quant_parallel', 'word_affine', 'cold_features', 'leaf_profile', 'range_hint', 'batch_project', 'implicit_product', 'lazy_values', 'scalar_batch', 'certified_branch', 'packed_attention', 'fixed_branch', 'split_fixed', 'inline_fixed', 'inline_product', 'bias_reuse', 'residual_fixed', 'rolling_fixed', 'local_rows', 'local_bias'), default='baseline'); args = p.parse_args()
    generate(args.output, args.variant)
