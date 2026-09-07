"""Isolated three-cycle search from the hash-qualified scalar release."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.m5_fast_sources import ROOT, pinned

BASE_GENERATOR = 'aa50e2dbda00ac8d41db9be8f2c17c0bf5104e1ca1d17925a1afadb0836ca5e2'
BASE = {
    'ops.c': '3b68f9c45319886b32d15c47d30922d506dc03ff150e2ea6457e58b57e9158b3',
    'numerics.c': 'b784dac6e810804033b5eb9151b0c06cf8ba470f38e2ebdd0e48822bbbbebea0',
    'runtime.c': '19d51cf03a371b76cfec96f1f27d2f97e1d7532647db100b907f05a758331b07',
    'requant.c': 'd6698029321cfd8c08c3331eba54f708e92542d2cde9363ccf657f1c93528091',
    'profile.c': '96d261c265c5b03ee6bf904825af22f1797283362134ffc16482b711ac3a8dff',
}


def fusion(ops):
    from scripts.m5_iterate_sources import once, function
    ops = '#include "affine_round.h"\n' + ops
    ops = once(ops, 'int pa_m5_project(',
               (ROOT/'runtime/m5_search/project_affine.c.inc').read_text()+'\nint pa_m5_project(')
    old = function(ops, 'pa_m5_project')
    new = once(old, '''        scales[i] = pa_fast_scale_power2(channel_scale, 8);
        bias[i] = pa_fast_scale_power2(linear->bias[i], 8);''', '        scales[i] = channel_scale;')
    new = once(new, '''      for (uint32_t i = 0; i < n; ++i) {
        scales[i] = pa_fast_scale_power2(scales[i], 8 - (int)exponent);
        bias[i] = pa_fast_scale_power2(linear->bias[i], 8 - (int)exponent);
      }
''', '')
    new = once(new, '''    int status = affine_row(backend, workspace, sums + row*n, scales, bias, n,
                            PA_M5_SFPU_AFFINE, output + row*n);''',
               '''    int status = pa_search_project_affine(backend, workspace, sums+row*n, scales,
                                           linear->bias, bias, n, 8-(int)output_exponents[row], output+row*n);''')
    return once(ops, old, new)


def generate(output, variant):
    pinned(ROOT/'scripts/m5_scalar_sources.py', BASE_GENERATOR)
    from scripts.m5_scalar_sources import generate as base, instrument
    base(output, 'affine')
    sources = {name: pinned(output/name, digest).decode() for name, digest in BASE.items()}
    if variant not in ('baseline', 'lto', 'fusion', 'product'):
        raise ValueError('unknown search variant')
    if variant in ('fusion', 'product'): sources['ops.c'] = fusion(sources['ops.c'])
    if variant == 'product':
        from scripts.m5_iterate_sources import once
        ops = '#include "mul_i32.h"\n' + sources['ops.c']
        ops = once(ops, 'double logical = (double)sum * scale;',
                   'double logical = pa_search_mul_i32(sum, scale);')
        ops = once(ops, 'double logical = (double)input[row*columns+i] * reciprocal[i];',
                   'double logical = pa_search_mul_i32(input[row*columns+i], reciprocal[i]);')
        sources['ops.c'] = ops
    for name, value in sources.items():
        (output/name).write_text(value)
    for name, value in zip(('fine_ops.c', 'fine_numerics.c', 'fine_profile.c'),
                          instrument(sources['ops.c'], sources['numerics.c'], sources['profile.c'])):
        (output/name).write_text(value)
    report = dict(schema=1, variant=variant, parent_generator_sha256=BASE_GENERATOR, parent_files=BASE,
                  files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob('*.c'))})
    (output/'search_derivation.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--variant', choices=('baseline', 'lto', 'fusion', 'product'), required=True)
    args = parser.parse_args()
    generate(args.output, args.variant)
