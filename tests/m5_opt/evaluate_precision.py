"""One predeclared small W4A8 screen; no hardware throughput claims."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch
from safetensors.numpy import load_file
from ref.gpt2_adaptive import AdaptiveGPT2
from ref.gpt2_float import FloatGPT2
from tests.m4.evaluate_scaled import aggregate, metrics


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pack(q):
    q = np.asarray(q, dtype=np.int8).reshape(-1)
    if len(q) % 2 or np.any(q < -7) or np.any(q > 7):
        raise ValueError('invalid W4 packing domain')
    return (q[::2].view(np.uint8) & 15) | ((q[1::2].view(np.uint8) & 15) << 4)


def unpack(payload):
    p = np.asarray(payload, dtype=np.uint8)
    q = np.empty(len(p) * 2, dtype=np.int8)
    q[::2] = ((p & 15).astype(np.int8) ^ 8) - 8
    q[1::2] = ((p >> 4).astype(np.int8) ^ 8) - 8
    return q


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('use fresh precision report')
    policy_path = Path('tests/m5_opt/precision_policy.json')
    policy = json.loads(policy_path.read_text())
    for path, expected in ((policy['window_file'], policy['window_sha256']),
                           ('build/m4_model/model.safetensors', policy['model_sha256']),
                           ('build/m4_calibration.json', policy['calibration_sha256'])):
        if sha(path) != expected:
            raise ValueError('precision input identity mismatch: ' + path)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    start = time.monotonic()
    model = AdaptiveGPT2('build/m4_model', 'build/m4_calibration.json', .5)
    floating = FloatGPT2('build/m4_model')
    windows = np.load(policy['window_file'], allow_pickle=False)
    selected = [windows[i, :policy['predictions_per_window']+1] for i in policy['window_indices']]
    float_logits = [floating.forward(w[:-1], all_logits=True)[0].numpy() for w in selected]
    report = {'schema': 1, 'status': 'INCOMPLETE', 'policy': policy,
              'policy_sha256': sha(policy_path), 'source_sha256': {p: sha(p) for p in (
                  __file__, 'ref/gpt2_adaptive.py', 'ref/gpt2_scaled.py',
                  'ref/gpt2_quantized.py', 'ref/gpt2_float.py', 'ref/sfpu_ref.py',
                  'tests/m4/evaluate_scaled.py')}, 'variants': {}}
    for variant in ('accepted_w8a8', 'candidate_w4a8'):
        if variant == 'candidate_w4a8':
            raw = load_file('build/m4_model/model.safetensors')
            packing = []
            for name, (_, _, bias) in model.linears.items():
                weight = raw['wte.weight'].T if name == 'lm_head' else raw[name+'.weight']
                balanced = weight.astype(np.float64) * model.smoothing[name][:, None]
                maximum = np.abs(balanced).max(axis=0)
                scale = np.where(maximum == 0, 1., maximum / 7)
                q = np.rint(balanced / scale).astype(np.int8)
                payload = pack(q)
                decoded = unpack(payload).reshape(q.shape)
                np.testing.assert_array_equal(q, decoded)
                packing.append({'name': name, 'elements': q.size,
                                'packed_bytes': payload.nbytes,
                                'packed_sha256': hashlib.sha256(payload.tobytes()).hexdigest(),
                                'scales_sha256': hashlib.sha256(scale.astype('<f8').tobytes()).hexdigest()})
                model.linears[name] = (decoded.astype(np.float64), scale, bias)
            report['packing'] = packing
            del raw, balanced, weight, q, payload, decoded
        model.stats.clear(); model.maxima.clear()
        rows = []
        for window, reference in zip(selected, float_logits):
            logits = model.forward(window[:-1], all_logits=True)[0]
            rows.append(metrics(reference, logits, window[1:]))
        result = aggregate(rows)
        clipping = {k: int(v) for k, v in model.stats.items() if k.endswith('.clipped') and v}
        limits = policy['quality_limits']
        gates = {'perplexity': result['perplexity_ratio'] <= limits['maximum_perplexity_ratio'],
                 'top1': result['top1_agreement'] >= limits['minimum_top1_agreement'],
                 'top5': result['top5_inclusion'] >= limits['minimum_top5_inclusion'],
                 'kl': result['mean_forward_kl_nats'] <= limits['maximum_mean_forward_kl_nats'],
                 'clipping': sum(clipping.values()) <= limits['maximum_unintended_clipping']}
        report['variants'][variant] = {'blocks': rows, 'aggregate': result,
                                       'unintended_clipping': clipping, 'gates': gates}
        print('M5 OPT PRECISION', variant, json.dumps(result), flush=True)
    report['status'] = ('SCREEN_PASS_NOT_QUALIFIED' if all(
        report['variants']['candidate_w4a8']['gates'].values()) else 'CANDIDATE_REJECTED')
    report['host_evaluation_seconds'] = time.monotonic() - start
    report['limitations'] = '128 development predictions, one quantizer; does not rule out all W4 schemes. Packing verified on host, no packed hardware or board-speed result.'
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M5 OPT PRECISION COMPLETE', report['status'], flush=True)


if __name__ == '__main__':
    main()
