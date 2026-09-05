"""Frozen-reference tensors and generation cache hashes, never runtime goldens."""
import hashlib
import json
from pathlib import Path
import numpy as np
from ref.gpt2_adaptive import AdaptiveGPT2
from ref.m4_model_pack import file_sha256
from tests.m4.qualify_scaled_quality import verify_frozen


def cache_digest(cache):
    digest = hashlib.sha256()
    for layer, (k, v) in enumerate(cache):
        digest.update(f'{layer}:{k.shape}:<i2'.encode())
        digest.update(np.ascontiguousarray(k, dtype='<i2').tobytes())
        digest.update(np.ascontiguousarray(v, dtype='<i2').tobytes())
    return digest.hexdigest()


def main():
    directory = Path('build/m4_runtime_fixtures')
    if directory.exists():
        raise ValueError('refusing to overwrite fixture evidence')
    verify_frozen('tests/m4/adaptive_candidate.json')
    directory.mkdir()
    model = AdaptiveGPT2('build/m4_model', 'build/m4_calibration.json', .5)
    generation = json.loads(Path('build/m4_v3_generation.json').read_text())
    if file_sha256('build/m4_v3_generation.json') != '188c2b6e790ce214ba05e629da94ff74105e388f1859af52b262f4420cb6c1b7':
        raise ValueError('frozen generation evidence changed')
    manifest = {'schema': 1, 'candidate_sha256': file_sha256('tests/m4/adaptive_candidate.json'),
                'exporter_sha256': file_sha256(__file__), 'cases': [], 'generation': []}
    cases = [{'id': 'single', 'input_tokens': [464]}] + generation['cases']
    for case in cases:
        logits, cache, trace = model.forward(case['input_tokens'], capture=True)
        entry = {'id': case['id'], 'input_tokens': case['input_tokens'], 'tensors': {}}
        for name, value in list(trace.items()) + [('logits', logits)]:
            filename = case['id'] + '.' + name + '.npy'
            np.save(directory / filename, value, allow_pickle=False)
            entry['tensors'][name] = {'file': filename, 'sha256': file_sha256(directory / filename)}
        entry['cache_sha256'] = cache_digest(cache)
        manifest['cases'].append(entry)
        print('M4 FIXTURE TENSOR EXPORT', case['id'], flush=True)
    for case in generation['cases']:
        cache, selected, steps = None, [], []
        for i, expected in enumerate(case['steps']):
            tokens = case['input_tokens'] if i == 0 else [selected[-1]]
            logits, cache, _ = model.forward(tokens, cache)
            token = int(logits[0].argmax())
            logit_hash = hashlib.sha256(logits.astype('<f8').tobytes()).hexdigest()
            if token != expected['token'] or logit_hash != expected['logits_sha256']:
                raise AssertionError('reference no longer matches frozen generation')
            selected.append(token)
            steps.append({'token': token, 'logits_sha256': logit_hash, 'cache_sha256': cache_digest(cache)})
        manifest['generation'].append({'id': case['id'], 'input_tokens': case['input_tokens'], 'steps': steps})
        print('M4 FIXTURE GENERATION EXPORT', case['id'], flush=True)
    tokens = np.load('build/m4_quality_data/validation_256.npy', allow_pickle=False)[:4, :-1].reshape(-1)
    logits, cache, _ = model.forward(tokens)
    manifest['boundary'] = {'input_tokens': tokens.tolist(),
                            'logits_sha256': hashlib.sha256(logits.astype('<f8').tobytes()).hexdigest(),
                            'cache_sha256': cache_digest(cache)}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('M4 FIXTURE EXPORT PASS', file_sha256(directory / 'manifest.json'), flush=True)


if __name__ == '__main__':
    main()
