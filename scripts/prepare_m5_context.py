"""Fresh short diagnostic policy; reuse the already qualified independent cache."""
import argparse
import json
from pathlib import Path
from scripts.m5_sweep_policy import ROOT, sha


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    stage = args.stage.resolve()
    if (stage/'policy.json').exists():
        raise ValueError('use a fresh policy/stage')
    policy = json.loads((ROOT/'build/m5_sweep_v1/policy.json').read_text())
    policy['scope'] = 'maximum-context attention block diagnosis; no speed claim'
    policy['matrix'] = [dict(id='attention_detail_p1023', kind='cached', past=1023,
                             profile=True, bound_seconds=180, role='maximum_context_diagnostic')]
    for name, path in (('m5_profile.bin', stage/'m5_profile.bin'),
                       ('m5_context_run.py', ROOT/'zynq/m5_context_run.py'),
                       ('m5_sweep.py', ROOT/'zynq/m5_sweep.py')):
        policy['pinned'][name] = sha(path)
        policy['source_paths'][name] = str(path.relative_to(ROOT))
    (stage/'policy.json').write_text(json.dumps(policy, indent=2)+'\n')
    refs = json.loads((ROOT/'build/m5_sweep_v1/references/manifest.json').read_text())
    refs['policy_sha256'] = sha(stage/'policy.json')
    refs['seeds'] = {'1023': refs['seeds']['1023']}
    reference = stage/'references'
    (reference/'p1023').mkdir(parents=True)
    (reference/'manifest.json').write_text(json.dumps(refs, indent=2)+'\n')
    (reference/'p1023/seed').symlink_to(ROOT/'build/m5_sweep_v1/references/p1023/seed', target_is_directory=True)
    (reference/'p1023/m5_profile.bin').symlink_to(stage/'m5_profile.bin')
    print('CONTEXT DIAGNOSTIC POLICY FROZEN', sha(stage/'policy.json'))


if __name__ == '__main__':
    main()
