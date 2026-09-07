#!/usr/bin/env python3
"""Generate isolated firmware sources from exact audited inputs.

The derived files are build artifacts, not edited historical source. Every
transformation is explicit and fail-closed; the generated text is pinned by
the build. Fine counters are inclusive and must not be summed across nesting.
"""
import argparse
from pathlib import Path
import re
from scripts.m5_fast_sources import ROOT, pinned

PINS = {
    'runtime/m5/pa_m5_ops.c': '963fef221133c20b1604e2e1e1aede8ec616bad0193ce91cdb1d796a3e71f3de',
    'runtime/m5_opt/pa_m5_ops_opt.c': 'de1397d2130b7f70fd7f2882905af345969d9a8e8ee716519fe5a561ca8e1d2d',
    'runtime/m5_opt/pa_m5_metadata_opt.c': '77d6b47827c2dfba1130b9f64a7fb57b96d399b0f22100f2187513d1dba9610b',
    'runtime/m5_opt/pa_m5_numerics_opt.c': 'c3b068e92aac7f6cdffd430fa983b805e1da044ef2e06e804a57b030467bda5d',
    'runtime/m5/pa_m5_numerics.c': '4b924da9404a7962d89cd1635cb9a925d8cdcad23413a78acef2003b1c3b52ac',
    'firmware/m5_opt/profile_firmware.c': '96d261c265c5b03ee6bf904825af22f1797283362134ffc16482b711ac3a8dff',
    'firmware/m5/runtime_firmware.c': '2f0b94acb0e12296bd5f66c86c12d89ce747ffc7201435a0c71ce8e53f4ab20f',
}


def source(name):
    return pinned(ROOT / name, PINS[name]).decode()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'ambiguous derivation marker: {old!r}')
    return text.replace(old, new)


def wrap(text, name, arguments, kind, head=False):
    match = re.search(rf'(?m)^(?:static )?int {name}\([^{{]+\) \{{', text)
    if not match:
        raise ValueError(f'missing function {name}')
    opening = match.end() - 1
    depth = 1; end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}'); end += 1
    signature = text[match.start():opening]
    body = text[opening:end]
    inner = signature.replace(name + '(', 'pa_fast_inner_' + name + '(')
    before = '  pa_fast_profile_head = linear && linear->n == 50257;\n' if head else ''
    after = '  pa_fast_profile_head = 0;\n' if head else ''
    wrapper = (signature + '{\n' + before + '  uint64_t begin = pa_fast_profile_begin();\n'
               + f'  int status = pa_fast_inner_{name}({arguments});\n'
               + f'  pa_fast_profile_end({kind}, begin);\n' + after + '  return status;\n}')
    return text[:match.start()] + inner + body + '\n\n' + wrapper + text[end:]


def generate(output, fine=False, prepare=False, requant=False):
    output.mkdir(parents=True, exist_ok=False)
    ops = source('runtime/m5/pa_m5_ops.c')
    reuse = source('runtime/m5_opt/pa_m5_ops_opt.c')
    ops = replace_once(reuse, '#include "../m5/pa_m5_ops.c"', ops)
    if requant:
        ops = replace_once(ops, '#include "pa_m5_ops.h"', '''#include "pa_m5_ops.h"
#include "pa_m5_requant.h"
static int pa_fast_quantize(const pa_m5_backend *backend, pa_m5_workspace *workspace,
                            const int16_t *input, uint32_t rows, uint32_t columns,
                            int8_t *output, double *units) {
  return pa_m5_requant_offload(backend, workspace, input, rows, columns, output, units);
}
''')
        ops = replace_once(ops, 'pa_m5_dynamic_quantize(input, rows, k, quantized, units)',
                            'pa_fast_quantize(backend, workspace, input, rows, k, quantized, units)')
    if prepare:
        # Preserve the original ordered unit*weight multiplication. Reuse that
        # exact rounded channel value between the range and finalization scans.
        helper = (ROOT / 'runtime/m5_fast/exact_power2.c.inc').read_text()
        ops = replace_once(ops, '#include "pa_m5_ops.h"', '#include "pa_m5_ops.h"\n' + helper)
        ops = replace_once(ops,
            '        double logical = (double)sums[row*n+i] * channel_scale + linear->bias[i];',
            '        scales[i] = channel_scale;\n'
            '        double logical = (double)sums[row*n+i] * channel_scale + linear->bias[i];')
        ops = replace_once(ops, '''      double inverse_unit = 256.0 / power2(exponent);
      for (uint32_t i = 0; i < n; ++i) {
        double channel_scale = units[row] * linear->scale[i];
        channel_scale *= power2(input_exponents[row]);
        scales[i] = channel_scale * inverse_unit;
        bias[i] = linear->bias[i] * inverse_unit;
      }''', '''      for (uint32_t i = 0; i < n; ++i) {
        scales[i] = pa_fast_scale_power2(scales[i], 8 - (int)exponent);
        bias[i] = pa_fast_scale_power2(linear->bias[i], 8 - (int)exponent);
      }''')
        # These substitutions occur only inside the original project function.
        if ops.count('channel_scale *= power2(input_exponents[row]);') != 2:
            raise ValueError('projection input-scale markers changed')
        ops = ops.replace('channel_scale *= power2(input_exponents[row]);',
                          'channel_scale = pa_fast_scale_power2(channel_scale, (int)input_exponents[row]);')
        ops = replace_once(ops, '        scales[i] = channel_scale * 256.0;',
                            '        scales[i] = pa_fast_scale_power2(channel_scale, 8);')
        ops = replace_once(ops, '        bias[i] = linear->bias[i] * 256.0;',
                            '        bias[i] = pa_fast_scale_power2(linear->bias[i], 8);')
    numeric = source('runtime/m5_opt/pa_m5_metadata_opt.c')
    shift = source('runtime/m5_opt/pa_m5_numerics_opt.c')
    shift = replace_once(shift, '#include "../m5/pa_m5_numerics.c"', source('runtime/m5/pa_m5_numerics.c'))
    numeric = replace_once(numeric, '#include "pa_m5_numerics_opt.c"', shift)
    if prepare:
        old = '''  int64_t total = 0;
  uint64_t squares = 0;
  for (uint32_t i = 0; i < count; ++i) {
    int64_t value = values[i]; total += value; squares += (uint64_t)(value * value);
  }
  uint64_t variance = (uint64_t)count * squares - (uint64_t)(total * total);
  double epsilon = 1.0e-5 * 65536.0 * (double)(count * count);
  double divisor = (double)(UINT64_C(1) << (2 * exponent));
  double correction = pa_m5_sqrt_f64(((double)variance + epsilon) /
                                     ((double)variance + epsilon / divisor));'''
        # For exponent zero the positive numerator and denominator are exactly
        # identical binary64 values. Division and correctly-rounded sqrt are
        # exactly one, independent of input. Dynamic exponent behavior stays.
        guarded = old.replace('  double correction = ', '  correction = ')
        numeric = replace_once(numeric, old,
            '  double correction = 1.0;\n  if (exponent) {\n' + guarded + '\n  }')
    firmware = source('firmware/m5_opt/profile_firmware.c')
    if fine:
        # Rename only definitions: callers continue through the timed wrapper.
        # Smooth is expanded under a macro for the historical dead definition;
        # instrument only the retained definition after its undef.
        prefix, retained = ops.split('#undef pa_m5_smooth', 1)
        retained = wrap(retained, 'pa_m5_smooth',
                        'backend, workspace, input, rows, columns, smoothing, output, exponents',
                        'PA_FAST_SMOOTH')
        ops = prefix + '#undef pa_m5_smooth' + retained
        if requant:
            ops = wrap(ops, 'pa_fast_quantize', 'backend, workspace, input, rows, columns, output, units', 'PA_FAST_DYNAMIC')
        else:
            ops = wrap(ops, 'pa_m5_dynamic_quantize', 'input, rows, columns, output, units', 'PA_FAST_DYNAMIC')
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
        for name, value in (('ops', ops), ('numeric', numeric), ('firmware', firmware)):
            value = '#include "pa_m5_fine_profile.h"\n' + value
            if name == 'ops': ops = value
            elif name == 'numeric': numeric = value
            else: firmware = value
        firmware = replace_once(firmware, '  uint64_t start = cycles(); previous_time = start;',
                                '  pa_fast_profile_enabled = control->flags;\n  uint64_t start = cycles(); previous_time = start;')
        firmware = replace_once(firmware, '  results[0].state = 4; control->state = 4;',
                                '  pa_fast_profile_publish((volatile uint32_t *)(TRACE + 0x24000));\n  results[0].state = 4; control->state = 4;')
    (output / 'ops.c').write_text(ops)
    (output / 'numerics.c').write_text(numeric)
    (output / 'profile.c').write_text(firmware)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--fine', action='store_true')
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--requant', action='store_true')
    args = parser.parse_args()
    generate(args.output, args.fine, args.prepare, args.requant)
