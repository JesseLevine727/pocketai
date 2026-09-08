"""Freeze a fresh, short cold/warm/prefill experiment against independent oracles."""
import argparse
import json
from pathlib import Path
from scripts.m5_sweep_policy import ROOT, sha


def main():
    p = argparse.ArgumentParser(__doc__); p.add_argument('--stage', type=Path, required=True)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--case', choices=('story', 'science', 'computing'), default='science')
    p.add_argument('--references', type=Path, default=Path('build/m5_context_story_reference_v2'))
    p.add_argument('--plain', action='store_true')
    p.add_argument('--full-checks', action='store_true')
    p.add_argument('--skip-prefill', action='store_true',
                   help='omit redundant cached-harness prefill when full requests cover it')
    p.add_argument('--overlay', type=Path, help='new qualified startup overlay directory')
    p.add_argument('--repetitions', type=int, default=1, choices=(1, 3))
    args = p.parse_args(); stage = args.stage.resolve(); stage.mkdir(exist_ok=False)
    build = args.build.resolve(); reference = args.references.resolve()
    policy = json.loads((ROOT/'build/m5_sweep_v1/policy.json').read_text())
    policy.update(scope='cold derived-cache setup and actual multirow prompt prefill; M6 held',
        accounting='All numerical initialization/prefill inside FPGA model time; diagnostic instrumentation is not primary performance.')
    policy['matrix'] = [dict(id=role, kind='cached', past=past, profile=not args.plain,
        bound_seconds=240 if past == 1022 else 120, role=role)
        for role, past in (('cold_initialization', 1022), ('last_slot', 1023), ('actual_prefill', 0))]
    if args.skip_prefill:
        policy['matrix'] = [x for x in policy['matrix'] if x['past'] != 0]
    if args.full_checks:
        policy['matrix'] += [dict(id='full_'+name+('_trace' if capture else ''),
            kind='full', case=name, new_tokens=count, capture=capture, bound_seconds=180)
            for name, count, capture in (('story', 2, True), ('story', 2, False),
                                         ('science', 1, False), ('computing', 1, False))]
    if args.repetitions != 1:
        if not args.plain: raise ValueError('final repeated performance must be unprofiled')
        matrix = policy['matrix']
        policy['matrix'] = [dict(trial, id=trial['id']+f'_r{repeat}', repetition=repeat)
            for repeat in range(1, args.repetitions+1) for trial in matrix
            if repeat == 1 or not trial.get('capture', False)]
    paths = {'m5_runtime.bin': build/'m5_runtime.bin', 'm5_profile.bin': build/('m5_profile.bin' if args.plain else 'm5_detail.bin')}
    if (build/'m5_trace.bin').exists(): paths['m5_trace.bin'] = build/'m5_trace.bin'
    if args.overlay:
        overlay = args.overlay.resolve()
        if not overlay.name.startswith('m5_startup_'):
            raise ValueError('only isolated startup overlay overrides are permitted')
        for name in ('m5_pynq.bit', 'm5_pynq.hwh'): paths[name] = overlay/name
        policy['startup_overlay_override'] = True
    for name in ('m5_startup_run.py', 'm5_context_ready_run.py', 'm5_context_run.py', 'm5_sweep.py'):
        paths[name] = ROOT/'zynq'/name
    for name, path in paths.items():
        policy['pinned'][name] = sha(path); policy['source_paths'][name] = str(path.relative_to(ROOT))
    (stage/'policy.json').write_text(json.dumps(policy, indent=2)+'\n')
    refs = json.loads((reference/'manifest.json').read_text())
    fixtures = json.loads((ROOT/'build/m4_runtime_fixtures/manifest.json').read_text())
    cases = {c['id']: c for c in fixtures['generation']}; case = cases[args.case]
    refs['seeds']['0'] = dict(schema=1, status='PASS', past=0, prefill_tokens=case['input_tokens'],
        context_role='actual_prompt_prefill', arrays={}, expected=case['steps'][0])
    refs.update(policy_sha256=sha(stage/'policy.json'), cases=cases)
    (stage/'references').mkdir()
    (stage/'references/manifest.json').write_text(json.dumps(refs, indent=2)+'\n')
    for past in (0, 1022, 1023):
        directory = stage/'references'/f'p{past}'; directory.mkdir()
        (directory/'seed').symlink_to(reference/'seed', target_is_directory=True)
        (directory/'m5_profile.bin').symlink_to('../../m5_profile.bin')
    for name, path in paths.items(): (stage/name).symlink_to(path)
    print('STARTUP POLICY FROZEN', sha(stage/'policy.json'))


if __name__ == '__main__': main()
