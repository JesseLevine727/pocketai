"""Isolated, fail-closed derivation of three-cycle firmware from qualified M5_FAST."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from scripts.m5_fast_sources import ROOT, pinned

BASE_GENERATOR = '0b7e8c6c0d65f491e62cb2034da05a17b8dcd37378aacd7e427c033b4705a126'
BASE_OPS = '03edc6897c644852135cc33c41d677133bca7126b043813f4e230fee70c625df'
BASE_NUMERIC = 'f058b5d517b8b53193da9c5521507e20304016607d8574fe7124c338b5213a01'
BASE_HW = '6f01ac0720e797abab1e6d6e568c87fc53ac5631309692c073b28d675aa6fc04'


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('ambiguous iteration derivation: '+old[:100])
    return text.replace(old, new)


def function(text, name):
    match = re.search(r'(?m)^int '+name+r'\([^\{]+\) \{', text)
    if not match:
        raise ValueError('function missing: '+name)
    start, end, depth = match.start(), match.end(), 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def cycle1(ops, numeric):
    ops = once(ops, 'int pa_m5_attention(',
               (ROOT/'runtime/m5_iterate/attention_prepared.c.inc').read_text()+'\nint pa_m5_attention(')
    ops = once(ops, '  for (uint32_t i = 0; i < 1024; ++i) zero_bias[i] = 0.0;\n', '')
    old = '''    for (uint32_t position = 0; position < length; ++position) zero_bias[position] = -(double)maximum_score;
    // Release the explicit metadata probe; affine_row recomputes the same common metadata.
    workspace->used = (uint32_t)((uint8_t *)score_multipliers - workspace->base);
    int status = affine_row(backend, workspace, scores_raw, scales, zero_bias, length,
                            PA_M5_SFPU_AFFINE, scores);'''
    new = '''    int status = pa_iter_attention_affine(backend, workspace, scores_raw,
                                           score_multipliers, score_shift, maximum_score,
                                           length, scores);
    workspace->used = (uint32_t)((uint8_t *)score_multipliers - workspace->base);'''
    ops = once(ops, old, new)
    original = function(numeric, 'pa_m5_layernorm_metadata')
    candidate = once(original, '  uint32_t factor = 1;', '''  /* For finite gains and nonnegative correction, rounded multiply/divide
   * and absolute value preserve magnitude order. Only the largest gain
   * determines the factor; keep the original operation order at that gain. */
  double largest_gain = 0.0;
  for (uint32_t i = 0; i < count; ++i) {
    if (!finite_value(gain[i]))
      return pa_iter_original_layernorm_metadata(values, count, exponent, gain,
                                                  bias, gain_q12, bias_q8, factor_out);
    double magnitude = absolute_value(gain[i]);
    if (magnitude > largest_gain) largest_gain = magnitude;
  }
  uint32_t factor = 1;''')
    candidate = once(candidate, '''    double maximum = 0.0;
    for (uint32_t i = 0; i < count; ++i) {
      double corrected = absolute_value(gain[i] * correction / (double)factor);
      if (corrected > maximum) maximum = corrected;
    }''', '''    double maximum = absolute_value(largest_gain * correction / (double)factor);''')
    numeric = once(numeric, original,
                   original.replace('int pa_m5_layernorm_metadata(',
                                    'static int pa_iter_original_layernorm_metadata(', 1)
                   +'\n\n'+candidate)
    return ops, numeric


def generate(output, variant):
    pinned(ROOT/'scripts/m5_fast_firmware_sources.py', BASE_GENERATOR)
    from scripts.m5_fast_firmware_sources import generate as generate_base
    generate_base(output, fine=False, prepare=True, requant=True)
    ops = pinned(output/'ops.c', BASE_OPS).decode()
    numeric = pinned(output/'numerics.c', BASE_NUMERIC).decode()
    hardware = pinned(ROOT/'runtime/m5/pa_m5_hw.c', BASE_HW).decode()
    if variant in ('cycle1', 'cycle2', 'cycle2_hart1', 'cycle3'):
        ops, numeric = cycle1(ops, numeric)
    elif variant != 'baseline':
        raise ValueError('unknown iteration variant')
    if variant in ('cycle2', 'cycle2_hart1'):
        hardware = once(hardware, 'static void fence(void)',
                        (ROOT/'runtime/m5_iterate/mailbox_wait.c.inc').read_text()
                        +'\nstatic void fence(void)')
        # cycle2 is the retained diagnostic reproduction, NOT deployable:
        # hart 0 mcycle stops in WFI and undercounts model/service wall time.
        if variant == 'cycle2':
            hardware = once(hardware,
                            '  while (!(REG(PA_M5_MBOX, 8) & 2u)) __asm__ volatile("nop");',
                            '  pa_iter_wait_mailbox(2);')
            hardware = once(hardware, '  shared->magic = 0; shared->hart1_ready = 0;',
                            '  pa_iter_enable_mailbox_wait();\n  shared->magic = 0; shared->hart1_ready = 0;')
        hardware = once(hardware, 'void pa_m5_hw_service_hart1(pa_m5_hw_shared *shared) {',
                        'void pa_m5_hw_service_hart1(pa_m5_hw_shared *shared) {\n  pa_iter_enable_mailbox_wait();')
        hardware = once(hardware,
                        '    while (!(REG(PA_M5_MBOX, 8) & 1u)) __asm__ volatile("nop");',
                        '    pa_iter_wait_mailbox(1);')
    if variant == 'cycle3':
        ops = once(ops, 'int pa_m5_project(',
                   (ROOT/'runtime/m5_iterate/project_range.c.inc').read_text()+'\nint pa_m5_project(')
        original = function(ops, 'pa_m5_project')
        candidate = once(original, '      double maximum = 0.0;', '      uint64_t maximum_bits = 0;')
        candidate = once(candidate, '''        double logical = (double)sums[row*n+i] * channel_scale + linear->bias[i];
        if (logical < 0) logical = -logical;
        if (residual) {
          double old = (double)residual[row*n+i] * power2(residual_exponents[row]) / 256.0;
          if (old < 0) old = -old;
          logical += old;
        }
        if (logical > maximum) maximum = logical;''', '''        double logical = pa_iter_range_term(sums[row*n+i], channel_scale, linear->bias[i],
                                             residual ? residual+row*n+i : 0,
                                             residual ? residual_exponents[row] : 0);
        maximum_bits = pa_iter_range_max(maximum_bits, logical);''')
        candidate = once(candidate, '      uint32_t exponent = pa_m5_storage_exponent(maximum);',
                         '      union { uint64_t bits; double floating; } maximum = {.bits = maximum_bits};\n'
                         '      uint32_t exponent = pa_m5_storage_exponent(maximum.floating);')
        ops = once(ops, original, candidate)
    (output/'ops.c').write_text(ops)
    (output/'numerics.c').write_text(numeric)
    (output/'hardware.c').write_text(hardware)
    report = dict(schema=1, variant=variant, baseline_generator_sha256=BASE_GENERATOR,
                  baseline_ops_sha256=BASE_OPS, baseline_numerics_sha256=BASE_NUMERIC,
                  files={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(output.glob('*.c'))})
    (output/'derivation.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--variant', choices=('baseline', 'cycle1', 'cycle2', 'cycle2_hart1', 'cycle3'), required=True)
    args = parser.parse_args()
    generate(args.output, args.variant)
