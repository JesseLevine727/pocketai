"""Validate v3 only on development: unchanged short contexts plus range stress."""
import json
from pathlib import Path
import numpy as np
from ref.gpt2_adaptive import AdaptiveGPT2
from tests.m4.qualify_scaled_quality import verify_frozen
from tests.m4.evaluate_scaled import sha


def main():
    output = Path('build/m4_v3_development.json')
    if output.exists():
        raise ValueError('refusing to overwrite development evidence')
    # v3 extends exactly these v2 equations/assets. Do not modify the v2 freeze.
    verify_frozen()
    model = AdaptiveGPT2('build/m4_model', 'build/m4_calibration.json', 0.5)
    data = np.load('build/m4_quality_data/validation_256.npy', allow_pickle=False)
    from ref.gpt2_scaled import ScaledGPT2
    baseline = ScaledGPT2('build/m4_model', 'build/m4_calibration.json', 0.5)
    for i, tokens in enumerate(data):
        a, ac, _ = model.forward(tokens[:-1], all_logits=True)
        b, bc, _ = baseline.forward(tokens[:-1], all_logits=True)
        np.testing.assert_array_equal(a, b)
        for (ak, av), (bk, bv) in zip(ac, bc):
            np.testing.assert_array_equal(ak, bk)
            np.testing.assert_array_equal(av, bv)
        print('M4 V3 DEVELOPMENT EXACT V2', i + 1, flush=True)
    del baseline
    tokens = data[:4, :-1].reshape(-1)
    full, expected, _ = model.forward(tokens)
    print('M4 V3 DEVELOPMENT full context complete', flush=True)
    cache, offset = None, 0
    for length in (512, 511, 1):
        got, cache, _ = model.forward(tokens[offset:offset + length], cache)
        offset += length
        print('M4 V3 DEVELOPMENT cached positions', offset, flush=True)
    np.testing.assert_array_equal(got, full)
    for (k, v), (ek, ev) in zip(cache, expected):
        np.testing.assert_array_equal(k, ek)
        np.testing.assert_array_equal(v, ev)
    try:
        model.forward([0], cache)
    except ValueError:
        pass
    else:
        raise AssertionError('overflow position accepted')
    for (k, v), (ek, ev) in zip(cache, expected):
        np.testing.assert_array_equal(k, ek)
        np.testing.assert_array_equal(v, ev)
    clipping = {k: v for k, v in model.stats.items() if k.endswith('.clipped') and v}
    report = {'status': 'DEVELOPMENT_PASS' if not clipping else 'FAIL', 'candidate': model.identity,
              'source_sha256': sha('ref/gpt2_adaptive.py'), 'runner_sha256': sha(__file__),
              'validation_windows_sha256': sha('build/m4_quality_data/validation_256.npy'),
              'development_2048_exact_v2': True, 'full_context_1024_exact_cache': True,
              'overflow_rejected_without_cache_mutation': True, 'unintended_clipping': clipping,
              'range_adjustments': {k: v for k, v in model.stats.items() if '.balance_exponent_' in k},
              'held_out_status': 'Not evaluated for v3; candidate freeze and requalification still required.'}
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 V3 DEVELOPMENT FINAL', report['status'], flush=True)
    if clipping:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
