"""Bind a short two-forward campaign to fresh firmware and independent references."""
import argparse
import json
from pathlib import Path
from scripts.m5_sweep_policy import ROOT, sha


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--stage', type=Path, required=True); p.add_argument('--build', type=Path, required=True)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--repetitions', type=int, default=1); p.add_argument('--diagnostic', action='store_true')
    p.add_argument('--full-checks', action='store_true')
    p.add_argument('--baseline', action='store_true')
    args = p.parse_args(); stage = args.stage.resolve(); stage.mkdir(exist_ok=False)
    if args.baseline and (args.diagnostic or args.full_checks):
        raise ValueError('baseline is a plain matched cached pair only')
    build = args.build.resolve(); refs_path = args.references.resolve()
    policy = json.loads((ROOT/'build/m5_sweep_v1/policy.json').read_text())
    policy['scope'] = 'exact maximum-context optimization: cold FPGA initialization then actual greedy last-slot forward'
    if args.baseline: policy['scope'] = 'matched original frozen baseline: same independent prefix and two genuine forwards, no derived cache'
    policy['accounting'] = 'Cold seed restore outside START but inside campaign; all derived-cache initialization/maintenance inside FPGA model time. Warm sample retains only previous actual FPGA state. Detail-enabled runs diagnostic only.'
    policy['matrix'] = [dict(id=f'{role}_{n}', kind='cached', past=past, profile=args.diagnostic,
        bound_seconds=240 if past == 1022 else 120, role=role)
        for n in range(args.repetitions) for past, role in ((1022, 'cold_initialization'), (1023, 'last_slot'))]
    if args.full_checks:
        policy['matrix'] += [dict(id=f'full_{name}_{capture}', kind='full', case=name,
            new_tokens=count, capture=capture, bound_seconds=180, role='original_full_request_and_trace' if capture else 'optimized_full_request')
            for name, count, capture in (('story', 2, True), ('science', 1, False), ('computing', 1, False), ('story', 2, False))]
    paths = {'m5_runtime.bin': build/'m5_runtime.bin',
             'm5_profile.bin': build/('m5_detail.bin' if args.diagnostic else 'm5_profile.bin'),
             'm5_context_run.py': ROOT/'zynq/m5_context_run.py',
             'm5_context_ready_run.py': ROOT/'zynq/m5_context_ready_run.py',
             'm5_sweep.py': ROOT/'zynq/m5_sweep.py'}
    for name, path in paths.items():
        policy['pinned'][name] = sha(path); policy['source_paths'][name] = str(path.relative_to(ROOT))
    (stage/'policy.json').write_text(json.dumps(policy, indent=2)+'\n')
    refs = json.loads((refs_path/'manifest.json').read_text())
    if args.baseline:
        for seed in refs['seeds'].values(): seed['context_baseline'] = True
    fixtures = json.loads((ROOT/'build/m4_runtime_fixtures/manifest.json').read_text())
    refs.update(policy_sha256=sha(stage/'policy.json'), cases={c['id']: c for c in fixtures['generation']})
    (stage/'references').mkdir()
    (stage/'references/manifest.json').write_text(json.dumps(refs, indent=2)+'\n')
    for past in (1022, 1023):
        directory = stage/'references'/f'p{past}'; directory.mkdir()
        (directory/'seed').symlink_to(refs_path/'seed', target_is_directory=True)
        (directory/'m5_profile.bin').symlink_to('../../m5_profile.bin')
    for name, path in paths.items(): (stage/name).symlink_to(path)
    print('CONTEXT READY POLICY FROZEN', sha(stage/'policy.json'))


if __name__ == '__main__': main()
