"""Actual-checkpoint complete 1024-position cache boundary on frozen candidate."""
import json
from pathlib import Path
import numpy as np
from ref.gpt2_scaled import ScaledGPT2
from tests.m4.qualify_scaled_quality import verify_frozen
from tests.m4.evaluate_scaled import sha


def main():
    output = Path('build/m4_v2_context_boundary.json')
    if output.exists():
        raise ValueError('refusing to overwrite context evidence')
    freeze = verify_frozen()
    # Functional stress, not a new quality/calibration sample. Concatenates
    # the first four preselected development contexts, each 256 tokens.
    tokens = np.load('build/m4_quality_data/validation_256.npy', allow_pickle=False)[:4, :-1].reshape(-1)
    model = ScaledGPT2('build/m4_model', 'build/m4_calibration.json', freeze['alpha'])
    full, expected_cache, _ = model.forward(tokens)
    print('M4 CONTEXT full 1024 complete', flush=True)
    cache, offset = None, 0
    for length in (512, 511, 1):
        actual, cache, _ = model.forward(tokens[offset:offset + length], cache)
        offset += length
        print('M4 CONTEXT cached position count', offset, flush=True)
    np.testing.assert_array_equal(actual, full)
    for (k, v), (ek, ev) in zip(cache, expected_cache):
        np.testing.assert_array_equal(k, ek)
        np.testing.assert_array_equal(v, ev)
    try:
        model.forward([0], cache)
    except ValueError:
        pass
    else:
        raise AssertionError('position 1024 was accepted')
    # Rejected extension must not mutate any cache tensor.
    for (k, v), (ek, ev) in zip(cache, expected_cache):
        np.testing.assert_array_equal(k, ek)
        np.testing.assert_array_equal(v, ev)
    clipping = {k: v for k, v in model.stats.items() if k.endswith('.clipped') and v}
    report = {'status': 'EXACT_1024_CACHE_BOUNDARY_PASS' if not clipping else 'FAIL_UNINTENDED_CLIPPING',
              'candidate_sha256': sha('tests/m4/scaled_candidate.json'), 'runner_sha256': sha(__file__),
              'development_windows_sha256': sha('build/m4_quality_data/validation_256.npy'),
              'positions': 1024, 'cached_chunks': [512, 511, 1], 'overflow_rejected_without_mutation': True,
              'unintended_clipping': clipping, 'limitation': 'Host functional stress, not a physical or held-out quality result.'}
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 CONTEXT FINAL', report['status'], flush=True)
    if clipping:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
