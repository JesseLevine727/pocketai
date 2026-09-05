"""Actual-checkpoint exact causal/cache checks, using development tokens only."""
import argparse
import json
from pathlib import Path
import numpy as np
from ref.gpt2_scaled import ScaledGPT2
from tests.m4.evaluate_scaled import sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, default=Path('build/m4_model'))
    parser.add_argument('--calibration', type=Path, default=Path('build/m4_calibration.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite evidence')
    source = Path('build/m4_quality_data/validation_256.npy')
    manifest = json.loads(source.with_name('manifest.json').read_text())
    if sha(source) != manifest['groups'][source.name]['sha256']:
        raise ValueError('development windows changed')
    tokens = np.load(source, allow_pickle=False)[0, :17]
    model = ScaledGPT2(args.model, args.calibration, alpha=0.5)
    full, expected_cache, _ = model.forward(tokens, all_logits=True)
    checks = []
    for sizes in ([1] * 17, [7, 5, 5], [16, 1]):
        actual, cache, offset = [], None, 0
        for size in sizes:
            logits, cache, _ = model.forward(tokens[offset:offset + size], cache, all_logits=True)
            actual.append(logits)
            offset += size
        np.testing.assert_array_equal(np.concatenate(actual), full)
        for (ek, ev), (ak, av) in zip(expected_cache, cache):
            np.testing.assert_array_equal(ek, ak)
            np.testing.assert_array_equal(ev, av)
        checks.append({'chunks': sizes, 'status': 'EXACT_PASS'})
        print('M4 SCALED CACHE EXACT PASS', sizes, flush=True)
    # Reset/no-cache must not inherit state from previous forward calls.
    reset, _, _ = model.forward(tokens, all_logits=True)
    np.testing.assert_array_equal(reset, full)
    invalid = ([], [-1], [50257], [[1]], [0] * 1025)
    for bad in invalid:
        try:
            model.forward(bad)
        except ValueError:
            continue
        raise AssertionError('invalid input accepted')
    report = {'status': 'EXACT_CACHE_PASS_NOT_FULL_M4_QUALIFICATION', 'candidate': model.identity,
              'source_sha256': sha('ref/gpt2_scaled.py'), 'development_windows_sha256': sha(source),
              'tokens': tokens.tolist(), 'checks': checks, 'reset': 'PASS', 'invalid_inputs': len(invalid)}
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
