"""One frozen candidate, untouched held-out windows, precommitted hard gates."""
import json
import os
import time
from pathlib import Path
import numpy as np
import torch
from ref.gpt2_float import FloatGPT2
from ref.gpt2_scaled import ScaledGPT2
from scripts.fetch_m4_model import identity
from tests.m4.evaluate_scaled import aggregate, metrics, sha


def check_limits(result, limits):
    return {'perplexity_ratio': result['perplexity_ratio'] <= limits['maximum_perplexity_ratio'],
            'top1_agreement': result['top1_agreement'] >= limits['minimum_teacher_forced_top1_agreement'],
            'top5_inclusion': result['top5_inclusion'] >= limits['minimum_float_top1_in_quantized_top5'],
            'mean_forward_kl': result['mean_forward_kl_nats'] <= limits['maximum_mean_forward_kl_nats']}


def verify_frozen():
    freeze_file = Path('tests/m4/scaled_candidate.json')
    freeze = json.loads(freeze_file.read_text())
    for collection in ('source_sha256', 'asset_sha256', 'selection_evidence_sha256'):
        for path, expected in freeze[collection].items():
            if identity(Path(path)) != expected:
                raise ValueError('frozen identity changed: ' + path)
    if np.__version__ != freeze['host_environment']['numpy'] or torch.__version__ != freeze['host_environment']['torch']:
        raise ValueError('host library versions changed')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '4':
        raise ValueError('set OPENBLAS_NUM_THREADS=4')
    return freeze


def main():
    output = Path('build/m4_v2_heldout_quality.json')
    if output.exists():
        raise ValueError('refusing to overwrite held-out evidence')
    freeze = verify_frozen()
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    policy = json.loads(Path('tests/m4/quality_policy.json').read_text())
    manifest = json.loads(Path('build/m4_quality_data/manifest.json').read_text())
    fmodel = FloatGPT2('build/m4_model')
    qmodel = ScaledGPT2('build/m4_model', 'build/m4_calibration.json', freeze['alpha'])
    if qmodel.identity['version'] != freeze['version']:
        raise ValueError('candidate version changed')
    initial_clipping = {k: v for k, v in qmodel.stats.items() if k.endswith('.clipped') and v}
    qmodel.stats.clear(); qmodel.maxima.clear()
    report = {'status': 'IN_PROGRESS_NOT_QUALIFIED', 'candidate_sha256': sha('tests/m4/scaled_candidate.json'),
              'runner_sha256': sha(__file__), 'groups': {}, 'initial_weight_clipping': initial_clipping}
    all_rows = []
    started = time.monotonic()
    for group in policy['held_out']:
        filename = f"{group['split']}_{group['predictions_per_block']}.npy"
        path = Path('build/m4_quality_data') / filename
        if sha(path) != manifest['groups'][filename]['sha256']:
            raise ValueError('held-out window identity changed')
        windows = np.load(path, allow_pickle=False)
        if windows.shape != (group['blocks'], group['predictions_per_block'] + 1):
            raise ValueError('held-out shape differs from frozen policy')
        rows, layer_errors = [], {}
        for index, tokens in enumerate(windows):
            f, _, ft = fmodel.forward(tokens[:-1], all_logits=True, capture=index == 0)
            q, _, qt = qmodel.forward(tokens[:-1], all_logits=True, capture=index == 0)
            row = metrics(f.numpy(), q, tokens[1:])
            rows.append(row); all_rows.append(row)
            if index == 0:
                for key, value in qt.items():
                    diff = value - ft[key].numpy()
                    layer_errors[key] = {'rmse': float(np.sqrt(np.mean(diff ** 2))),
                                         'max_abs': float(np.abs(diff).max())}
            print('M4 HELDOUT', filename, index + 1, json.dumps(aggregate([row])), flush=True)
        result = aggregate(rows)
        report['groups'][filename] = {'windows_sha256': sha(path), 'blocks': rows, 'aggregate': result,
                                      'limits': check_limits(result, policy['gates']),
                                      'first_block_layer_errors': layer_errors}
    report['aggregate'] = aggregate(all_rows)
    report['aggregate_limits'] = check_limits(report['aggregate'], policy['gates'])
    report['stats'], report['maxima'] = dict(qmodel.stats), qmodel.maxima
    clipping = {k: v for k, v in qmodel.stats.items() if k.endswith('.clipped') and v}
    residual_clipping = sum(v for k, v in clipping.items() if k.endswith('.residual.clipped'))
    report['unintended_clipping'] = clipping
    report['arithmetic_limits'] = {'residual_clipping': residual_clipping <= policy['gates']['maximum_unintended_residual_clipping'],
                                   'finite': True, 'all_other_clipping_zero': not clipping and not initial_clipping}
    passing = (all(report['aggregate_limits'].values()) and all(report['arithmetic_limits'].values()) and
               all(all(group['limits'].values()) for group in report['groups'].values()))
    report['status'] = 'HELD_OUT_DISTRIBUTION_PASS_NOT_PHYSICAL_M4_CLOSURE' if passing else 'FAIL'
    report['host_evaluation_seconds'] = time.monotonic() - started
    report['limitations'] = 'Finite sampled teacher-forced quality only; generation, model-pack and physical checks are separate. Host evaluation time is not a board benchmark.'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 HELDOUT FINAL', report['status'], json.dumps(report['aggregate']), flush=True)
    if not passing:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
