"""Split-isolated development evaluation. Never selects from held-out data."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import torch
from ref.gpt2_float import FloatGPT2
from ref.gpt2_scaled import ScaledGPT2


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metrics(float_logits, quant_logits, targets):
    f, q = np.asarray(float_logits, dtype=np.float64), np.asarray(quant_logits, dtype=np.float64)
    if f.shape != q.shape or not np.all(np.isfinite(f)) or not np.all(np.isfinite(q)):
        raise ValueError('invalid logit tensors')
    f = f - f.max(axis=1, keepdims=True)
    q = q - q.max(axis=1, keepdims=True)
    flp = f - np.log(np.exp(f).sum(axis=1, keepdims=True))
    qlp = q - np.log(np.exp(q).sum(axis=1, keepdims=True))
    index = np.arange(len(targets))
    top1f, top1q = f.argmax(axis=1), q.argmax(axis=1)
    # Stable descending order makes equal-logit ties prefer lower token IDs.
    top5q = np.argsort(-q, axis=1, kind='stable')[:, :5]
    return {'tokens': len(targets), 'float_nll_sum': float(-flp[index, targets].sum()),
            'quantized_nll_sum': float(-qlp[index, targets].sum()),
            'top1_matches': int((top1f == top1q).sum()),
            'float_top1_in_quantized_top5': int((top5q == top1f[:, None]).any(axis=1).sum()),
            'forward_kl_sum': float((np.exp(flp) * (flp - qlp)).sum()),
            'centered_logit_squared_error_sum': float(((f - q) ** 2).sum()),
            'centered_logit_max_error': float(np.abs(f - q).max())}


def aggregate(rows):
    total = {key: sum(row[key] for row in rows) for key in rows[0] if key != 'centered_logit_max_error'}
    n = total['tokens']
    total.update({'float_perplexity': float(np.exp(total['float_nll_sum'] / n)),
                  'quantized_perplexity': float(np.exp(total['quantized_nll_sum'] / n)),
                  'perplexity_ratio': float(np.exp((total['quantized_nll_sum'] - total['float_nll_sum']) / n)),
                  'top1_agreement': total['top1_matches'] / n,
                  'top5_inclusion': total['float_top1_in_quantized_top5'] / n,
                  'mean_forward_kl_nats': total['forward_kl_sum'] / n,
                  'centered_logit_rmse': float(np.sqrt(total['centered_logit_squared_error_sum'] / n / 50257)),
                  'centered_logit_max_error': max(row['centered_logit_max_error'] for row in rows)})
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, default=Path('build/m4_model'))
    parser.add_argument('--data', type=Path, default=Path('build/m4_quality_data'))
    parser.add_argument('--calibration', type=Path, default=Path('build/m4_calibration.json'))
    parser.add_argument('--alpha', type=float, default=0.5)
    parser.add_argument('--blocks', type=int, default=8)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite evaluation evidence')
    torch.set_num_threads(4)
    manifest = json.loads((args.data / 'manifest.json').read_text())
    policy_sha = sha('tests/m4/quality_policy.json')
    path = args.data / 'validation_256.npy'
    if manifest['policy_sha256'] != policy_sha or sha(path) != manifest['groups'][path.name]['sha256']:
        raise ValueError('evaluation identity mismatch')
    windows = np.load(path, allow_pickle=False)
    if not 1 <= args.blocks <= len(windows):
        raise ValueError('invalid development subset')
    fp = FloatGPT2(args.model)
    qp = ScaledGPT2(args.model, args.calibration, args.alpha)
    qp.stats.clear(); qp.maxima.clear()
    rows, layers = [], {}
    start = time.monotonic()
    for i, window in enumerate(windows[:args.blocks]):
        f, _, ft = fp.forward(window[:-1], all_logits=True, capture=i == 0)
        q, _, qt = qp.forward(window[:-1], all_logits=True, capture=i == 0)
        row = metrics(f.numpy(), q, window[1:])
        rows.append(row)
        if i == 0:
            for key, tensor in qt.items():
                diff = tensor - ft[key].numpy()
                layers[key] = {'rmse': float(np.sqrt(np.mean(diff ** 2))), 'max_abs': float(np.abs(diff).max())}
        print('M4 DEVELOPMENT', i + 1, json.dumps(aggregate([row])), flush=True)
    report = {'status': 'DEVELOPMENT_NOT_QUALIFIED', 'split': 'validation',
              'candidate': qp.identity, 'windows_sha256': sha(path), 'policy_sha256': policy_sha,
              'source_sha256': {str(p): sha(p) for p in ('ref/gpt2_scaled.py', 'tests/m4/evaluate_scaled.py', 'ref/sfpu_ref.py')},
              'blocks': rows, 'aggregate': aggregate(rows), 'first_block_layer_errors': layers,
              'stats': dict(qp.stats), 'maxima': qp.maxima, 'host_evaluation_seconds': time.monotonic() - start}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 DEVELOPMENT COMPLETE', json.dumps(report['aggregate']), flush=True)
    print('M4 CLIPPING', json.dumps({k: v for k, v in qp.stats.items() if k.endswith('.clipped') and v}), flush=True)


if __name__ == '__main__':
    main()
