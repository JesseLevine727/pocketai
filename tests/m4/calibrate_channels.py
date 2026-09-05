"""Collect float activation ranges on TRAIN only for a versioned model pack."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from ref.gpt2_float import FloatGPT2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, default=Path('build/m4_model'))
    parser.add_argument('--data', type=Path, default=Path('build/m4_quality_data'))
    parser.add_argument('--output', type=Path, default=Path('build/m4_calibration.json'))
    args = parser.parse_args()
    torch.set_num_threads(4)
    manifest = json.loads((args.data / 'manifest.json').read_text())
    policy = Path('tests/m4/quality_policy.json')
    if hashlib.sha256(policy.read_bytes()).hexdigest() != manifest['policy_sha256']:
        raise ValueError('quality policy changed')
    path = args.data / 'train_256.npy'
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['groups'][path.name]['sha256']:
        raise ValueError('training windows changed')
    windows = np.load(path, allow_pickle=False)
    model = FloatGPT2(args.model)
    maxima, ranges = {}, {}
    for index, tokens in enumerate(windows):
        _, _, trace = model.forward(tokens[:-1], capture=True)
        for layer in range(12):
            for source, destination in (('ln1', 'attn.c_attn'), ('ln2', 'mlp.c_fc'),
                                        ('gelu', 'mlp.c_proj'), ('context', 'attn.c_proj')):
                key = f'h.{layer}.{destination}'
                value = trace[f'h.{layer}.{source}'].abs().amax(dim=0).numpy()
                maxima[key] = np.maximum(maxima.get(key, 0), value)
        value = trace['ln_f'].abs().amax(dim=0).numpy()
        maxima['lm_head'] = np.maximum(maxima.get('lm_head', 0), value)
        for key, value in trace.items():
            if key.endswith(('residual', 'output', 'up', 'qkv')) or key in ('embedding', 'ln_f'):
                ranges[key] = max(ranges.get(key, 0), float(value.abs().max()))
        print(f'M4 CALIBRATION TRAIN {index + 1}/{len(windows)}', flush=True)
    report = {'schema': 1, 'source_split': 'train', 'windows_sha256': manifest['groups'][path.name]['sha256'],
              'policy_sha256': manifest['policy_sha256'], 'tokens': len(windows) * 256,
              'channel_amax': {k: v.tolist() for k, v in maxima.items()}, 'tensor_amax': ranges}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 TRAIN CALIBRATION PASS (ranges only; no quality claim)')


if __name__ == '__main__':
    main()
