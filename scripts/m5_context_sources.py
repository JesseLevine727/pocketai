"""Pinned derivation of the qualified release, with block-level diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.m5_fast_sources import ROOT, pinned
from scripts.m5_iterate_sources import once
from scripts.m5_tenth_sources import function

PARENT = 'ac033dd3db1ad1b84a7d2312cf14318005c0eeb89a78acb85a2477e56d976e72'
BASE = dict(ops='6c407e24cb0d9fe99fb85f1047d6c54debeacc1885dac3bbe9bfb0c94c455f5e',
            numerics='205277a62f77c5eac7d772d94065daf5c9c9b899ac5c57ea3479d60c8af57d43',
            runtime='19d51cf03a371b76cfec96f1f27d2f97e1d7532647db100b907f05a758331b07',
            profile='96d261c265c5b03ee6bf904825af22f1797283362134ffc16482b711ac3a8dff',
            requant='d6698029321cfd8c08c3331eba54f708e92542d2cde9363ccf657f1c93528091',
            hardware='6f01ac0720e797abab1e6d6e568c87fc53ac5631309692c073b28d675aa6fc04')


def instrument(ops):
    old = function(ops, 'pa_m5_attention')
    new = once(old, '  // Publish physical cache', '  uint64_t detail = pa_context_begin();\n  // Publish physical cache')
    new = once(new, '  for (uint32_t row = 0; row < rows; ++row) for (uint32_t head = 0; head < 12; ++head) {\n    uint32_t length',
               '  pa_context_end(CTX_APPEND, detail);\n  for (uint32_t row = 0; row < rows; ++row) for (uint32_t head = 0; head < 12; ++head) {\n    detail = pa_context_begin();\n    uint32_t length')
    transitions = (
        ('    for (uint32_t tile = 0; tile < (length+15)/16; ++tile) {', 'CTX_QUERY'),
        ('    int64_t maximum_score = INT64_MIN;', 'CTX_QK'),
        ('    for (uint32_t position = 0; position < length; ++position)\n      softmax_input[position]', 'CTX_SCORES'),
        ('    /* Scan contiguous position vectors', 'CTX_PROBABILITY'),
        ('    for (uint32_t feature = 0; feature < 64; ++feature)\n      value_units[feature]', 'CTX_VMAX'),
        ('    for (uint32_t tile = 0; tile < 4; ++tile) {', 'CTX_VUNITS'),
        ('    for (uint32_t feature = 0; feature < 64; ++feature)\n      { scales[feature]', 'CTX_AV'),
    )
    for marker, kind in transitions:
        new = once(new, marker, f'    pa_context_end({kind}, detail); detail = pa_context_begin();\n'+marker)
    new = once(new, '      context[row*768+head*64+feature] = value_output[feature];',
               '      context[row*768+head*64+feature] = value_output[feature];\n    pa_context_end(CTX_OUTPUT, detail);')
    return '#include "attention_detail.h"\n'+once(ops, old, new)


def ready_cache(source):
    original = function(source['ops'], 'pa_m5_attention')
    legacy = once(original, 'int pa_m5_attention(', 'static int pa_context_attention_legacy(')
    ops = instrument(source['ops'])
    old = function(ops, 'pa_m5_attention')
    new = once(old, '  if (!backend', '''  if (!pa_context_enabled(cache))
    return pa_context_attention_legacy(backend, workspace, cache, layer, qkv, rows, past, context);
  if (!backend''')
    new = once(new, '  // Publish physical cache', '''  if (pa_context_prepare(cache, layer, past)) {
    pa_m5_workspace_rewind(workspace, mark); return -31;
  }
  // Publish physical cache''')
    new = once(new, '      cache->keys_i8[destination+feature] = pa_scalar_quantize24(cache->keys[destination+feature], multiplier);',
               '      pa_context_store_key(cache, layer, head, past+row, feature, pa_scalar_quantize24(cache->keys[destination+feature], multiplier));')
    new = once(new, '''      for (uint32_t feature = 0; feature < 64; ++feature)
        for (uint32_t column = 0; column < 16; ++column)
          weight_tile[feature*16+column] = column < width ? cache->keys_i8[
              cache_vector(layer,head,tile*16+column)+feature] : 0;''',
               '      const int8_t *ready_keys = pa_context_key_tile(cache, layer, head, tile);')
    new = once(new, '''      if (backend->gemm_tile(backend->context, 1, 64, width, query_i8,
                             weight_tile, tile_output)) {''',
               '''      if (backend->gemm_tile(backend->context, 1, 64, width, query_i8,
                             ready_keys, tile_output)) {''')
    start = new.index('    /* Scan contiguous position vectors')
    end = new.index('    pa_context_end(CTX_VMAX', start)
    new = new[:start]+'''    /* Maxima and consumer-ready V are maintained for the exact prefix.
     * Requantize every affected four-column group when any maximum changes. */
    if (pa_context_update_values(cache, layer, head, past+row)) {
      pa_m5_workspace_rewind(workspace, mark); return -32;
    }
'''+new[end:]
    new = once(new, '      value_units[feature] = pa_scalar_dynamic(value_multipliers[feature], 8, value_multipliers+feature);',
               '      value_units[feature] = pa_context_value_units(layer, head)[feature];')
    new = once(new, '''      for (uint32_t position = 0; position < length; ++position) {
        const int16_t *vector = cache->values + cache_vector(layer,head,position) + tile*16;
        for (uint32_t column = 0; column < 16; ++column)
          weight_tile[position*16+column] = pa_scalar_quantize24(vector[column], value_multipliers[tile*16+column]);
      }''', '      const int8_t *ready_values = pa_context_value_tile(layer, head, tile);')
    new = once(new, '''      if (backend->gemm_tile(backend->context, 1, length, 16, probability_i8,
                             weight_tile, tile_output)) {''',
               '''      if (backend->gemm_tile(backend->context, 1, length, 16, probability_i8,
                             ready_values, tile_output)) {''')
    source['ops'] = '#include "ready_cache.h"\n'+once(ops, old, legacy+'\n\n'+new)
    cache = (ROOT/'runtime/m5_scalar/cache.c').read_text()
    source['cache'] = once(cache, '3u*1024u*1024u', '(2u*1024u*1024u + DOMAIN*12u + 128u)')
    runtime = (ROOT/'firmware/m5/runtime_firmware.c').read_text()
    runtime = '#include "ready_cache.h"\n'+runtime
    runtime = once(runtime, '  pa_m5_cache_open(&cache, PA_M5_ARENA);', '''  pa_m5_cache_open(&cache, PA_M5_ARENA);
  int ready_cache = !(control->flags & 1u);
  pa_context_bind(&cache, (uint8_t *)PA_M5_WORK_BASE, (uint8_t *)PA_M5_TRACE_BASE, ready_cache);
  if (ready_cache) workspace.capacity = PA_CONTEXT_WORK_LIMIT - 0x3000;''')
    source['runtime_entry'] = runtime
    profile = '#include "ready_cache.h"\n'+source['profile']
    profile = once(profile, 'static record_t records[MAX_RECORDS];',
                   'static record_t * const records = (record_t *)(TRACE + RECORD_OFFSET);')
    profile = once(profile, '  pa_m5_cache cache; pa_m5_cache_open(&cache, ARENA);', '''  pa_m5_cache cache; pa_m5_cache_open(&cache, ARENA);
  pa_context_bind(&cache, (uint8_t *)WORK, (uint8_t *)TRACE, 1);
  workspace.capacity = PA_CONTEXT_WORK_LIMIT - 0x3000;''')
    source['profile'] = profile


def generate(output, variant='diagnostic'):
    requested_variant = variant
    if variant in ('dual', 'direct', 'position', 'combined', 'masked'): variant = 'parallel'
    pinned(ROOT/'scripts/m5_tenth_sources.py', PARENT)
    from scripts.m5_tenth_sources import generate as parent
    parent(output, 'reciprocal')
    source = {name: pinned(output/(name+'.c'), digest).decode() for name, digest in BASE.items()}
    if variant in ('ready', 'score', 'smooth', 'product', 'local', 'parallel'):
        ready_cache(source)
        if variant in ('score', 'smooth', 'product', 'local', 'parallel'):
            old = function(source['ops'], 'pa_m5_attention')
            new = once(old, '''    for (uint32_t position = 0; position < length; ++position)
      scales[position] = query_unit * cache->key_units[((uint64_t)layer*12+head)*1024+position] * 32.0;
    uint32_t *score_multipliers = pa_m5_workspace_allocate(workspace, length*4, 64);
    if (!score_multipliers || pa_m5_affine_metadata(scales, length, score_multipliers, &score_shift)) {''',
                '''    const double *key_units = cache->key_units + (layer*12+head)*1024;
    double maximum_unit = pa_context_key_maximum(layer, head);
    if (key_units[length-1] > maximum_unit) maximum_unit = key_units[length-1];
    uint32_t *score_multipliers = pa_m5_workspace_allocate(workspace, length*4, 64);
    if (!score_multipliers || pa_context_score_metadata(key_units, length, query_unit,
          maximum_unit, score_multipliers, &score_shift, scales)) {''')
            source['ops'] = '#include "score_metadata.h"\n'+once(source['ops'], old, new)
        if variant in ('smooth', 'product', 'local', 'parallel'):
            prefix, retained = source['ops'].split('#undef pa_m5_smooth', 1)
            retained = once(retained, '''  for (uint32_t i = 0; i < columns; ++i) {
    reciprocal[i] = pa_tenth_reciprocal(smoothing[i]); zero_bias[i] = 0.0;
  }
  uint32_t shift;
  if (pa_m5_affine_metadata(reciprocal, columns, multipliers, &shift)) {
    pa_m5_workspace_rewind(workspace, mark); return -3;
  }''', '''  uint32_t shift;
  const uint32_t *prepared = pa_context_smooth_get(smoothing, columns, &shift);
  if (prepared) multipliers = (uint32_t *)prepared;
  else {
    for (uint32_t i = 0; i < columns; ++i) reciprocal[i] = pa_tenth_reciprocal(smoothing[i]);
    if (pa_m5_affine_metadata(reciprocal, columns, multipliers, &shift)) {
      pa_m5_workspace_rewind(workspace, mark); return -3;
    }
    pa_context_smooth_put(smoothing, columns, multipliers, shift);
  }''')
            retained = once(retained, '''  for (uint32_t row = 0; row < rows; ++row) {
    if (any_overflow) {''', '''  if (any_overflow) {
    for (uint32_t i = 0; i < columns; ++i) {
      if (prepared) reciprocal[i] = pa_tenth_reciprocal(smoothing[i]);
      zero_bias[i] = 0.0;
    }
  }
  for (uint32_t row = 0; row < rows; ++row) {
    if (any_overflow) {''')
            source['ops'] = '#include "smooth_cache.h"\n'+prefix+'#undef pa_m5_smooth'+retained
        if variant in ('local', 'parallel'):
            old = function(source['ops'], 'pa_m5_attention')
            start = old.index('    for (uint32_t position = 0; position < length; ++position) {\n      int64_t raw =')
            end = old.index('    if (backend->sfpu(backend->context, PA_M5_SFPU_SOFTMAX', start)
            retained = old[start:end]
            retained = once(retained, '    int status = pa_iter_attention_affine', '    status = pa_iter_attention_affine')
            retained = once(retained, '    workspace->used = (uint32_t)((uint8_t *)score_multipliers - workspace->base);\n', '')
            retained = once(retained, '    pa_context_end(CTX_SCORES, detail); detail = pa_context_begin();\n', '')
            replacement = '''    int status;
    if (pa_context_local_scores(scores_raw, score_multipliers, length, score_shift, softmax_input)) {
'''+retained+'''    }
    workspace->used = (uint32_t)((uint8_t *)score_multipliers - workspace->base);
    pa_context_end(CTX_SCORES, detail); detail = pa_context_begin();
'''
            new = old[:start]+replacement+old[end:]
            source['ops'] = '#include "local_scores.h"\n'+once(source['ops'], old, new)
        if variant == 'parallel':
            helper = (ROOT/'runtime/m5_context/project_parallel.c.inc').read_text()
            source['ops'] = '#include "parallel.h"\n'+once(source['ops'], 'static int pa_search_project_affine(', helper+'\nstatic int pa_search_project_affine(')
            old = function(source['ops'], 'pa_m5_project')
            start = old.index('    if (!scaled && !residual) {')
            end = old.index('    int status = pa_search_project_affine', start)
            new = old[:start]+'''    pa_context_project_job job;
    job.factor = factor; job.linear = linear; job.sums = sums+row*n;
    job.residual = residual ? residual+row*n : 0; job.scales = scales;
    job.input_exponent = input_exponents[row];
    job.residual_exponent = residual ? residual_exponents[row] : 0;
    job.range = scaled || residual; job.maximum[0] = 0; job.maximum[1] = 0;
    if (pa_context_parallel(pa_context_project_leaf, &job, n)) {
      pa_m5_workspace_rewind(workspace, mark); return -40;
    }
    if (!job.range) output_exponents[row] = 0;
    else {
      union { uint64_t bits; double floating; } maximum = {
          .bits = job.maximum[0] > job.maximum[1] ? job.maximum[0] : job.maximum[1]};
      uint32_t exponent = pa_m5_storage_exponent(maximum.floating);
      if (exponent == UINT32_MAX) { pa_m5_workspace_rewind(workspace, mark); return -5; }
      output_exponents[row] = exponent;
    }
'''+old[end:]
            source['ops'] = once(source['ops'], old, new)
            old = function(source['ops'], 'pa_search_project_affine')
            start = old.index('  for (uint32_t i = 0; i < count; ++i) {\n    union', old.index('  uint32_t shift = 31;'))
            end = old.index('  for (uint32_t offset = 0;', start)
            new = old[:start]+'''  pa_context_affine_job job;
  job.scales = scales; job.raw_bias = raw_bias; job.multipliers = multipliers;
  job.bias = bias; job.adjustment = adjustment; job.shift = shift;
  job.power_shift = power_shift; job.status[0] = 0; job.status[1] = 0;
  if (pa_context_parallel(pa_context_affine_leaf, &job, count)) {
    pa_m5_workspace_rewind(workspace, mark); return -40;
  }
  if (job.status[0] || job.status[1]) goto fallback;
'''+old[end:]
            source['ops'] = once(source['ops'], old, new)
            source['hardware'] = '#include "parallel.h"\n'+source['hardware']
            source['hardware'] = once(source['hardware'], '  backend->context = context;',
                                     '  pa_context_parallel_bind(context);\n  backend->context = context;')
            source['hardware'] = once(source['hardware'], '  uint32_t engine, expected_input;',
                                     '  if (shared->kind == 3) return pa_context_parallel_execute(shared);\n  uint32_t engine, expected_input;')
        if requested_variant in ('direct', 'position', 'combined', 'masked'):
            old = function(source['ops'], 'pa_m5_project')
            new = once(old, '''    if (backend->gemm_tile(backend->context, rows, k, width, quantized,
                           linear->tiles + (uint64_t)tile * k * 16, tile_output)) {''',
                '''    /* A single row already has the final contiguous consumer layout.
     * The last full 16-word result fits the allocator's preserved 64-byte pad. */
    int32_t *destination = rows == 1 ? sums+tile*16 : tile_output;
    if (backend->gemm_tile(backend->context, rows, k, width, quantized,
                           linear->tiles + (uint64_t)tile * k * 16, destination)) {''')
            new = once(new, '    for (uint32_t row = 0; row < rows; ++row)\n      for (uint32_t column',
                       '    if (rows != 1) for (uint32_t row = 0; row < rows; ++row)\n      for (uint32_t column')
            source['ops'] = once(source['ops'], old, new)
        if requested_variant in ('combined', 'masked'):
            old = function(source['ops'], 'pa_m5_attention')
            new = once(old, '''    if (!score_multipliers || pa_context_score_metadata(key_units, length, query_unit,
          maximum_unit, score_multipliers, &score_shift, scales)) {''',
                '''    if (!score_multipliers) { pa_m5_workspace_rewind(workspace, mark); return -3; }
    int prepared = pa_context_score_combined(key_units, length, query_unit, maximum_unit,
        score_multipliers, &score_shift, scales, scores_raw, softmax_input);
    if (prepared < 0) {''')
            new = once(new, '    if (pa_context_local_scores(scores_raw, score_multipliers, length, score_shift, softmax_input)) {',
                       '    if (prepared && pa_context_local_scores(scores_raw, score_multipliers, length, score_shift, softmax_input)) {')
            source['ops'] = once(source['ops'], old, new)
        if requested_variant in ('direct', 'position', 'combined', 'masked'):
            old = function(source['ops'], 'pa_m5_attention')
            new = once(old, '                             ready_keys, tile_output)) {',
                       '                             ready_keys, scores_raw+tile*16)) {')
            new = once(new, '''      for (uint32_t column = 0; column < width; ++column)
        scores_raw[tile*16+column] = tile_output[column];\n''', '')
            new = once(new, '                             ready_values, tile_output)) {',
                       '                             ready_values, value_sums+tile*16)) {')
            new = once(new, '''      for (uint32_t column = 0; column < 16; ++column)
        value_sums[tile*16+column] = tile_output[column];\n''', '')
            source['ops'] = once(source['ops'], old, new)
        for name, value in source.items(): (output/(name+'.c')).write_text(value)
        (output/'attention_ops.c').write_text(source['ops'])
    elif variant == 'diagnostic':
        (output/'attention_ops.c').write_text(instrument(source['ops']))
    else:
        raise ValueError('unknown context variant')
    profile = '#include "attention_detail.h"\n'+source['profile']
    profile = once(profile, '  results[0].state = 4; control->state = 4;',
                   '  pa_context_publish((volatile uint32_t *)(TRACE + 0x28000));\n  results[0].state = 4; control->state = 4;')
    (output/'attention_profile.c').write_text(profile)
    (output/'context_derivation.json').write_text(json.dumps(dict(schema=1, variant=requested_variant,
        parent_generator_sha256=PARENT, parent_files=BASE,
        files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob('*.c'))}), indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--variant', choices=('diagnostic', 'ready', 'score', 'smooth', 'product', 'local', 'parallel', 'dual', 'direct', 'position', 'combined', 'masked'), default='diagnostic')
    args = parser.parse_args()
    generate(args.output, args.variant)
