"""Bounded exact optimization from the immutable 10d9d22 search release."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from scripts.m5_fast_sources import ROOT, pinned
from scripts.m5_iterate_sources import once

PARENT = '3f7c638251f7b8c1c59d50955310ab122bf062014b05fc90ee2958d49a205c13'
BASE = {
    'ops.c': '78c5f7614574a2e14630c2c8dee348fc8eaa1efd945005836ab327c7f327722b',
    'numerics.c': 'b784dac6e810804033b5eb9151b0c06cf8ba470f38e2ebdd0e48822bbbbebea0',
    'runtime.c': '19d51cf03a371b76cfec96f1f27d2f97e1d7532647db100b907f05a758331b07',
    'requant.c': 'd6698029321cfd8c08c3331eba54f708e92542d2cde9363ccf657f1c93528091',
    'profile.c': '96d261c265c5b03ee6bf904825af22f1797283362134ffc16482b711ac3a8dff',
}


def function(text, name):
    match = re.search(r'(?m)^(?:static )?(?:int|int64_t|double) '+re.escape(name)+r'\([^\{]+\) \{', text)
    if not match: raise ValueError('function missing: '+name)
    end, depth = match.end(), 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[match.start():end]


def rounding(sources):
    old = function(sources['numerics.c'], 'pa_m5_rne_f64_signed')
    prefix = '''  /* The common result magnitude fits uint32. Decode sign without
   * soft-float comparisons and retain exact ties-to-even, including both zero
   * signs. Larger values/specials keep the full original int64 ABI below. */
  union { double floating; uint64_t bits; } data = {.floating = value};
  uint32_t encoded = (uint32_t)((data.bits >> 52) & 2047u);
  if (encoded < 1054) {
    uint32_t magnitude = pa_scalar_rne_scaled32(data.bits & UINT64_C(0x7fffffffffffffff), 0);
    return (data.bits >> 63) ? -(int64_t)magnitude : (int64_t)magnitude;
  }
'''
    sources['numerics.c'] = once(sources['numerics.c'], old, once(old, '  if (value == 0.0)', prefix+'  if (value == 0.0)'))
    for name in ('ops.c', 'numerics.c'):
        old = function(sources[name], 'pa_fast_scale_power2')
        new = once(old, '  int shifted =', '''  /* Positive finite power-of-two factors preserve signed zero exactly. */
  if ((data.bits << 1) == 0 && exponent >= -1022 && exponent <= 1023) return value;
  int shifted =''')
        sources[name] = once(sources[name], old, new)


def factors(sources):
    ops = '#include "mul_factor.h"\n' + sources['ops.c']
    old = function(ops, 'pa_m5_project')
    new = once(old, '  for (uint32_t row = 0; row < rows; ++row) {\n    if (!scaled',
               '  for (uint32_t row = 0; row < rows; ++row) {\n    pa_tenth_factor factor = pa_tenth_prepare_factor(units[row]);\n    if (!scaled')
    term = 'double channel_scale = units[row] * linear->scale[i];'
    if new.count(term) != 2: raise ValueError('channel multiply sites changed')
    new = new.replace(term, 'double channel_scale = pa_tenth_mul_factor(&factor, linear->scale[i]);')
    sources['ops.c'] = once(ops, old, new)


def reciprocals(sources):
    ops = '#include "reciprocal.h"\n' + sources['ops.c']
    prefix, retained = ops.split('#undef pa_m5_smooth', 1)
    retained = once(retained, 'reciprocal[i] = 1.0 / smoothing[i];',
                    'reciprocal[i] = pa_tenth_reciprocal(smoothing[i]);')
    sources['ops.c'] = prefix + '#undef pa_m5_smooth' + retained


def generate(output, variant):
    pinned(ROOT/'scripts/m5_search_sources.py', PARENT)
    from scripts.m5_search_sources import generate as base
    from scripts.m5_scalar_sources import instrument
    base(output, 'product')
    sources = {name: pinned(output/name, digest).decode() for name, digest in BASE.items()}
    if variant not in ('baseline', 'round', 'factor', 'reciprocal'):
        raise ValueError('unknown tenth variant')
    if variant in ('round', 'factor', 'reciprocal'): rounding(sources)
    if variant in ('factor', 'reciprocal'): factors(sources)
    if variant == 'reciprocal': reciprocals(sources)
    for name, value in sources.items(): (output/name).write_text(value)
    for name, value in zip(('fine_ops.c', 'fine_numerics.c', 'fine_profile.c'),
                          instrument(sources['ops.c'], sources['numerics.c'], sources['profile.c'])):
        (output/name).write_text(value)
    report = dict(schema=1, variant=variant, parent_generator_sha256=PARENT, parent_files=BASE,
                  files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob('*.c'))})
    (output/'tenth_derivation.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--variant', choices=('baseline', 'round', 'factor', 'reciprocal'), required=True)
    args = parser.parse_args()
    generate(args.output, args.variant)
