"""Deterministic disjoint calibration/development/test windows; no model eval."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
from transformers import GPT2TokenizerFast


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path('build/m4_data'))
    parser.add_argument('--model', type=Path, default=Path('build/m4_model'))
    parser.add_argument('--output', type=Path, default=Path('build/m4_quality_data'))
    args = parser.parse_args()
    policy_file = Path('tests/m4/quality_policy.json')
    policy = json.loads(policy_file.read_text())
    manifest = json.loads((args.data / 'data_manifest.json').read_text())
    if manifest['revision'] != policy['dataset_revision']:
        raise ValueError('wrong dataset revision')
    tokenizer = GPT2TokenizerFast.from_pretrained(args.model, local_files_only=True)
    tokenizer.model_max_length = 10 ** 12  # tokenize corpus, not a model forward
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'schema': 1, 'policy_sha256': sha(policy_file),
              'data_manifest_sha256': sha(args.data / 'data_manifest.json'),
              'tokenizer_sha256': sha(args.model / 'tokenizer.json'), 'groups': {}}
    for split_index, split in enumerate(('train', 'validation', 'test')):
        path = args.data / f'{split}-00000-of-00001.parquet'
        if sha(path) != manifest['files'][path.name]['sha256']:
            raise ValueError('dataset hash mismatch')
        texts = pq.read_table(path, columns=['text']).column('text').to_pylist()
        tokens = np.asarray(tokenizer.encode(policy['join_separator'].join(texts), add_special_tokens=False), dtype='<u4')
        configs = ([policy['calibration']] if split == 'train' else
                   [policy['development']] if split == 'validation' else policy['held_out'])
        # Slots are 513 tokens wide, so even the 512-prediction windows do not
        # overlap. Short windows use the beginning of their own distinct slot.
        rng = np.random.default_rng(policy['selection_seed'] + split_index)
        slots = rng.choice(len(tokens) // 513, sum(c['blocks'] for c in configs), replace=False)
        cursor = 0
        for config in configs:
            count, length = config['blocks'], config['predictions_per_block']
            starts = sorted(int(s) * 513 for s in slots[cursor:cursor + count])
            cursor += count
            windows = np.stack([tokens[s:s + length + 1] for s in starts])
            name = f'{split}_{length}.npy'
            np.save(args.output / name, windows, allow_pickle=False)
            report['groups'][name] = {'split': split, 'corpus_tokens': len(tokens),
                                      'starts': starts, 'shape': list(windows.shape),
                                      'sha256': sha(args.output / name)}
            print(f'M4 QUALITY DATA {name} shape={windows.shape}', flush=True)
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('M4 QUALITY DATA PREPARATION PASS (no model-quality evaluation)')


if __name__ == '__main__':
    main()
