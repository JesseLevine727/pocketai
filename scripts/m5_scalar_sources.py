"""Fail-closed scalar candidates derived from the qualified three-cycle release."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.m5_fast_sources import ROOT, pinned
from scripts.m5_iterate_sources import once, function

PINS = {
    'scripts/m5_iterate_sources.py': 'acd65c7167a33036f3f4a7ba98492a1617b465e6559fd15a3d0ea7e8e307600d',
    'runtime/m5/pa_m5_runtime.c': 'f312f54343c00af0d6c5b548a90459943210c4a703843602c49eec61f7278925',
    'runtime/m5_fast/pa_m5_requant.c': '9c95e9db04ddaa9d4fb302738d9cf46f83f0d6b6061031353922597d1e3427d6',
}
GENERATED = {
    'ops.c': 'f4105a725ce430b4633501b9906048c0b4dba47f893b58c4f2933402937a1c8d',
    'numerics.c': '6fe7055ac7bcdf20911ebfa34623b6cdc7d08011fb00741010dfd2796a7962aa',
    'profile.c': '96d261c265c5b03ee6bf904825af22f1797283362134ffc16482b711ac3a8dff',
}


def arithmetic(ops, numeric):
    original = '''uint32_t pa_m5_dynamic_multiplier(uint32_t maximum) {
  if (!maximum) return 0;
  uint64_t result = pa_m5_rne_u64(UINT64_C(127) << 24, maximum);
  return result < UINT32_C(0x80000000) ? (uint32_t)result : UINT32_MAX;
}'''
    numeric = once(numeric, original,
                   (ROOT/'runtime/m5_scalar/multiplier.c.inc').read_text().rstrip())
    ops = '#include "quantize.h"\n' + ops
    for old, new in (
        ('''pa_m5_sat_i8(pa_m5_rne_i64(
          (int64_t)cache->keys[destination+feature]*multiplier, UINT64_C(1)<<24))''',
         'pa_scalar_quantize24(cache->keys[destination+feature], multiplier)'),
        ('''pa_m5_sat_i8(pa_m5_rne_i64((int64_t)query[feature]*multiplier,
                                                    UINT64_C(1)<<24))''',
         'pa_scalar_quantize24(query[feature], multiplier)'),
        ('''pa_m5_sat_i8(pa_m5_rne_i64(
          (int64_t)probability[position]*multiplier, UINT64_C(1)<<24))''',
         'pa_scalar_quantize24(probability[position], multiplier)'),
        ('''pa_m5_sat_i8(pa_m5_rne_i64(
            (int64_t)cache->values[cache_vector(layer,head,position)+feature]*multiplier,
            UINT64_C(1)<<24))''',
         'pa_scalar_quantize24(cache->values[cache_vector(layer,head,position)+feature], multiplier)'),
        ('''      int64_t product = (int64_t)input[row * columns + column] * multiplier;
      output[row * columns + column] = pa_m5_sat_i8(pa_m5_rne_i64(product, UINT64_C(1) << 24));''',
         '''      output[row * columns + column] = pa_scalar_quantize24(input[row * columns + column], multiplier);'''),
    ):
        ops = once(ops, old, new)
    return ops, numeric


def lookup(ops, requant, runtime):
    ops = '#include "cache.h"\n' + ops
    requant = '#include "cache.h"\n' + requant
    # Combine each maximum/multiplier/unit preparation at its original point.
    # No cross-row movement, changed maximum, or delayed error check.
    for label, text in (('ops', ops), ('requant', requant)):
        if label == 'ops':
            text = once(text, '    uint32_t multiplier = pa_m5_dynamic_multiplier(maximum_i16(query, 64));',
                        '    uint32_t multiplier;\n    double query_unit = pa_scalar_dynamic(maximum_i16(query, 64), 8, &multiplier);')
            text = once(text, '    double query_unit = pa_m5_dynamic_unit(multiplier, 1.0/256.0);\n', '')
            text = once(text, '''    multiplier = pa_m5_dynamic_multiplier(probability_maximum);
    double probability_unit = pa_m5_dynamic_unit(multiplier, 1.0/32768.0);''',
                        '    double probability_unit = pa_scalar_dynamic(probability_maximum, 15, &multiplier);')
            text = once(text, '''      multiplier = pa_m5_dynamic_multiplier(maximum);
      value_units[feature] = pa_m5_dynamic_unit(multiplier, 1.0/256.0);''',
                        '      value_units[feature] = pa_scalar_dynamic(maximum, 8, &multiplier);')
        # Remaining two ops sites are ordinary rows and newly appended K;
        # requant has one ordinary row site.
        marker = '    uint32_t multiplier = pa_m5_dynamic_multiplier(maximum);'
        expected = 2 if label == 'ops' else 1
        if text.count(marker) != expected:
            raise ValueError('scalar quantizer pairing changed')
        text = text.replace(marker, '    uint32_t multiplier;\n    double scalar_unit = pa_scalar_dynamic(maximum, 8, &multiplier);')
        for unit in ('1.0 / 256.0', '1.0/256.0'):
            text = text.replace('pa_m5_dynamic_unit(multiplier, '+unit+')', 'scalar_unit')
        if label == 'ops': ops = text
        else: requant = text
    runtime = '#include "cache.h"\n' + runtime
    runtime = once(runtime, 'int pa_m5_forward_chunk(', 'static int pa_scalar_inner_forward_chunk(')
    marker = '\nint pa_m5_prefill('
    wrapper = '''
int pa_m5_forward_chunk(pa_m5_runtime *runtime, const uint32_t *tokens,
                        uint32_t rows, uint32_t past,
                        int16_t *logits, uint32_t *logits_exponent) {
  if (!valid_runtime(runtime) || !tokens || !logits || !logits_exponent ||
      !rows || rows > 16 || past + rows > 1024) return -1;
  for (uint32_t row = 0; row < rows; ++row) if (tokens[row] >= 50257) return -1;
  pa_m5_workspace *work = runtime->workspace;
  uint32_t mark = work->used;
  pa_scalar_cache_begin(work);
  int status = pa_scalar_inner_forward_chunk(runtime, tokens, rows, past, logits, logits_exponent);
  pa_scalar_cache_end();
  pa_m5_workspace_rewind(work, mark);
  return status;
}
'''
    runtime = once(runtime, marker, wrapper+marker)
    return ops, requant, runtime


def metadata(ops, numeric):
    helper = (ROOT/'runtime/m5_fast/exact_power2.c.inc').read_text()
    numeric = once(numeric, '#include "pa_m5_numerics.h"', '#include "pa_m5_numerics.h"\n'+helper)
    original = function(numeric, 'pa_m5_layernorm_metadata')
    candidate = once(original, '  uint32_t factor = 1;', '  uint32_t factor = 1;\n  int factor_shift = 0;')
    candidate = once(candidate, '    factor <<= 1;', '    factor <<= 1; ++factor_shift;')
    candidate = once(candidate, '''    int64_t g = pa_m5_rne_f64_signed(gain[i] * correction * 4096.0 / (double)factor);
    int64_t b = pa_m5_rne_f64_signed(bias[i] * 256.0);''', '''    /* Retain the two ordered power-of-two operations: combining shifts
     * would incorrectly erase an intermediate overflow or underflow. */
    double corrected = exponent ? gain[i] * correction : gain[i];
    double scaled = pa_fast_scale_power2(corrected, 12);
    int64_t g = pa_m5_rne_f64_signed(pa_fast_scale_power2(scaled, -factor_shift));
    int64_t b = pa_m5_rne_f64_signed(pa_fast_scale_power2(bias[i], 8));''')
    numeric = once(numeric, original, candidate)
    original = function(ops, 'pa_m5_apply_norm')
    candidate = once(original, '''  for (uint32_t row = 0; row < rows; ++row) {
    uint32_t factor;
    if (pa_m5_layernorm_metadata(input + row*columns, columns, exponents[row],
                                 norm->gain, norm->bias, gain, bias, &factor)) {
      pa_m5_workspace_rewind(workspace, mark); return -3;
    }
    for (uint32_t i = 0; i < columns; ++i) {
      x_plane[i] = input[row*columns+i]; gain_plane[i] = gain[i];
    }''', '''  uint32_t factor = 0, prepared_zero = 0;
  for (uint32_t row = 0; row < rows; ++row) {
    if (!prepared_zero || exponents[row]) {
      if (pa_m5_layernorm_metadata(input + row*columns, columns, exponents[row],
                                   norm->gain, norm->bias, gain, bias, &factor)) {
        pa_m5_workspace_rewind(workspace, mark); return -3;
      }
      for (uint32_t i = 0; i < columns; ++i) gain_plane[i] = gain[i];
      prepared_zero = exponents[row] == 0;
    }
    for (uint32_t i = 0; i < columns; ++i) x_plane[i] = input[row*columns+i];''')
    ops = once(ops, original, candidate)
    prefix, retained = ops.split('#undef pa_m5_smooth', 1)
    retained = once(retained, '''pa_m5_rne_i64((int64_t)input[row*columns+i] * multipliers[i],
                                         UINT64_C(1) << shift)''',
                    'pa_scalar_rne_product(input[row*columns+i], multipliers[i], shift)')
    retained = once(retained, 'scales[i] = reciprocal[i] / power2(exponents[row]);',
                    'scales[i] = pa_fast_scale_power2(reciprocal[i], -(int)exponents[row]);')
    ops = prefix + '#undef pa_m5_smooth' + retained
    ops = once(ops, '''pa_m5_rne_i64((int64_t)scores_raw[position]*score_multipliers[position],
                                  UINT64_C(1)<<score_shift)''',
               'pa_scalar_rne_product(scores_raw[position], score_multipliers[position], score_shift)')
    old = '''    for (uint32_t feature = 0; feature < 64; ++feature) {
      uint32_t maximum = 0;
      for (uint32_t position = 0; position < length; ++position) {
        int16_t value = cache->values[cache_vector(layer,head,position)+feature];
        uint32_t magnitude = magnitude_i16(value); if (magnitude > maximum) maximum = magnitude;
      }
      value_units[feature] = pa_scalar_dynamic(maximum, 8, &multiplier);
      for (uint32_t position = 0; position < length; ++position)
        values_i8[position*64+feature] = pa_scalar_quantize24(cache->values[cache_vector(layer,head,position)+feature], multiplier);
    }
    for (uint32_t tile = 0; tile < 4; ++tile) {
      for (uint32_t position = 0; position < length; ++position)
        for (uint32_t column = 0; column < 16; ++column)
          weight_tile[position*16+column] = values_i8[position*64+tile*16+column];'''
    new = '''    /* Scan contiguous position vectors, then quantize directly into each
     * consumer tile. Recompute every evolving maximum; no stale int8 V cache.
     * Keep the legacy scratch reservation/error boundary above unchanged. */
    uint32_t value_multipliers[64];
    for (uint32_t feature = 0; feature < 64; ++feature) value_multipliers[feature] = 0;
    for (uint32_t position = 0; position < length; ++position) {
      const int16_t *vector = cache->values + cache_vector(layer,head,position);
      for (uint32_t feature = 0; feature < 64; ++feature) {
        uint32_t magnitude = magnitude_i16(vector[feature]);
        if (magnitude > value_multipliers[feature]) value_multipliers[feature] = magnitude;
      }
    }
    for (uint32_t feature = 0; feature < 64; ++feature)
      value_units[feature] = pa_scalar_dynamic(value_multipliers[feature], 8, value_multipliers+feature);
    for (uint32_t tile = 0; tile < 4; ++tile) {
      for (uint32_t position = 0; position < length; ++position) {
        const int16_t *vector = cache->values + cache_vector(layer,head,position) + tile*16;
        for (uint32_t column = 0; column < 16; ++column)
          weight_tile[position*16+column] = pa_scalar_quantize24(vector[column], value_multipliers[tile*16+column]);
      }'''
    ops = once(ops, old, new)
    return ops, numeric


def affine(ops, numeric):
    numeric = '#include "affine_round.h"\n' + numeric
    start = numeric.index('static uint64_t rne_scaled_bits(')
    end = numeric.index('\n\nint pa_m5_affine_metadata(', start)
    numeric = numeric[:start] + '''static uint32_t rne_scaled_bits(uint64_t bits, uint32_t shift) {
  return pa_scalar_rne_scaled32(bits, shift);
}''' + numeric[end:]
    ops = once(ops, 'int pa_m5_dynamic_quantize(',
               (ROOT/'runtime/m5_scalar/uniform_affine.c.inc').read_text()+'\nint pa_m5_dynamic_quantize(')
    ops = once(ops, '''      for (uint32_t i = 0; i < columns; ++i) {
        x_plane[i] = (int16_t)result[i]; scale[i] = (double)factor; affine_bias[i] = (double)bias[i];
      }
      int status = affine_row(backend, workspace, x_plane, scale, affine_bias,
                              columns, PA_M5_SFPU_AFFINE, output + row*columns);''',
               '''      for (uint32_t i = 0; i < columns; ++i) x_plane[i] = (int16_t)result[i];
      int status = pa_scalar_uniform_affine(backend, workspace, x_plane, (double)factor,
                                            bias, columns, output + row*columns);''')
    ops = once(ops, '''      for (uint32_t i = 0; i < n; ++i) {
        expanded[i] = residual[row*n+i]; scales[i] = align_scale; bias[i] = 0.0;
      }
      status = affine_row(backend, workspace, expanded, scales, bias, n,
                          PA_M5_SFPU_AFFINE, aligned);''',
               '''      for (uint32_t i = 0; i < n; ++i) expanded[i] = residual[row*n+i];
      status = pa_scalar_uniform_affine(backend, workspace, expanded, align_scale, 0, n, aligned);''')
    return ops, numeric


def instrument(ops, numeric, firmware):
    # Reuse the qualified nine inclusive counters; no per-element timers.
    from scripts.m5_fast_firmware_sources import wrap
    prefix, retained = ops.split('#undef pa_m5_smooth', 1)
    retained = wrap(retained, 'pa_m5_smooth',
                    'backend, workspace, input, rows, columns, smoothing, output, exponents', 'PA_FAST_SMOOTH')
    ops = prefix + '#undef pa_m5_smooth' + retained
    ops = wrap(ops, 'pa_fast_quantize', 'backend, workspace, input, rows, columns, output, units', 'PA_FAST_DYNAMIC')
    ops = wrap(ops, 'affine_row', 'backend, workspace, input, scales, bias, count, operation, output',
               'pa_fast_profile_head ? PA_FAST_HEAD_AFFINE_ROW : PA_FAST_AFFINE_ROW')
    ops = wrap(ops, 'pa_m5_project',
               'backend, workspace, linear, input, input_exponents, rows, scaled, residual, residual_exponents, output, output_exponents',
               'pa_fast_profile_head ? PA_FAST_HEAD_PROJECT : PA_FAST_PROJECT', head=True)
    numeric = wrap(numeric, 'pa_m5_layernorm_metadata',
                   'values, count, exponent, gain, bias, gain_q12, bias_q8, factor_out', 'PA_FAST_NORM_METADATA')
    prefix, retained = numeric.split('#undef pa_m5_affine_metadata', 1)
    retained = wrap(retained, 'pa_m5_affine_metadata', 'scales, count, multipliers, shift',
                    'pa_fast_profile_head ? PA_FAST_HEAD_AFFINE_METADATA : PA_FAST_AFFINE_METADATA')
    numeric = prefix + '#undef pa_m5_affine_metadata' + retained
    firmware = once(firmware, '  uint64_t start = cycles(); previous_time = start;',
                    '  pa_fast_profile_enabled = control->flags;\n  uint64_t start = cycles(); previous_time = start;')
    firmware = once(firmware, '  results[0].state = 4; control->state = 4;',
                    '  pa_fast_profile_publish((volatile uint32_t *)(TRACE + 0x24000));\n  results[0].state = 4; control->state = 4;')
    return tuple('#include "pa_m5_fine_profile.h"\n' + text for text in (ops, numeric, firmware))


def generate(output, variant):
    for path, digest in PINS.items():
        pinned(ROOT/path, digest)
    from scripts.m5_iterate_sources import generate as base
    base(output, 'cycle3')
    sources = {name: pinned(output/name, digest).decode() for name, digest in GENERATED.items()}
    ops, numeric = sources['ops.c'], sources['numerics.c']
    if variant in ('arithmetic', 'lookup', 'metadata', 'affine'):
        ops, numeric = arithmetic(ops, numeric)
    elif variant != 'baseline':
        raise ValueError('unknown scalar variant')
    runtime = pinned(ROOT/'runtime/m5/pa_m5_runtime.c', PINS['runtime/m5/pa_m5_runtime.c']).decode()
    requant = pinned(ROOT/'runtime/m5_fast/pa_m5_requant.c', PINS['runtime/m5_fast/pa_m5_requant.c']).decode()
    if variant in ('lookup', 'metadata', 'affine'):
        ops, requant, runtime = lookup(ops, requant, runtime)
    if variant in ('metadata', 'affine'):
        ops, numeric = metadata(ops, numeric)
    if variant == 'affine':
        ops, numeric = affine(ops, numeric)
    sources.update({'ops.c': ops, 'numerics.c': numeric, 'runtime.c': runtime, 'requant.c': requant})
    for name, value in sources.items():
        (output/name).write_text(value)
    for name, value in zip(('fine_ops.c', 'fine_numerics.c', 'fine_profile.c'),
                           instrument(ops, numeric, sources['profile.c'])):
        (output/name).write_text(value)
    report = dict(schema=1, variant=variant, input_pins=PINS, baseline_generated=GENERATED,
                  files={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(output.glob('*.c'))})
    (output/'scalar_derivation.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--variant', choices=('baseline', 'arithmetic', 'lookup', 'metadata', 'affine'), required=True)
    args = parser.parse_args()
    generate(args.output, args.variant)
