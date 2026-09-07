"""Predeclare the non-Cartesian, time-bounded characterization matrix."""
import hashlib
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/m5_sweep_v1'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def policy():
    trials = []

    def full(case, count, bound, capture=False, role='full_request'):
        trials.append(dict(id=f'{case}_g{count}_r{sum(t.get("case") == case and t.get("new_tokens") == count for t in trials)+1}',
                           kind='full', case=case, new_tokens=count,
                           bound_seconds=bound, capture=capture, role=role))

    def cached(past, repeat=1, profile=False):
        for _ in range(repeat):
            ordinal = sum(t.get('past') == past and t.get('profile') == profile for t in trials)+1
            trials.append(dict(id=f'cached_p{past}_{"profile" if profile else "plain"}_r{ordinal}',
                               kind='cached', past=past, profile=profile,
                               bound_seconds=45 + past * .15, role='injected_valid_cache'))

    full('story', 2, 110, True, 'original_anchor')
    full('science', 1, 70, role='original_anchor')
    full('computing', 1, 70, role='original_anchor')
    cached(13, 3)
    for n, bound in ((1, 30), (16, 130), (32, 240), (64, 450)):
        full(f'story_length_{n}', 1, bound, role='synthetic_prefill_length')
    full('story', 1, 100, role='output_length')
    full('story', 4, 140, role='output_length')
    full('story', 16, 290, role='uninterrupted_generation')
    full('story', 16, 290, role='uninterrupted_generation')
    full('science', 16, 260, role='uninterrupted_generation')
    for past in (1, 8, 32, 128, 512, 1023):
        cached(past, 2)
    for past in (13, 128, 1023):
        cached(past, profile=True)
    full('computing', 16, 260, role='optional_content_replication')
    # No 32-output extrapolated oracle: <=20 frozen steps avoid new long references.
    paths = {'m5_runtime.bin': 'build/m5_tenth_reciprocal_v1/m5_runtime.bin',
             'm5_profile.bin': 'build/m5_tenth_reciprocal_v1/m5_profile.bin',
             'm5_pynq.bit': 'build/m5_fast_pynq_finish_v2/m5_pynq.bit',
             'm5_pynq.hwh': 'build/m5_fast_pynq_finish_v2/m5_pynq.hwh',
             'm5_run.py': 'zynq/m5_run.py', 'm5_opt_profile.py': 'zynq/m5_opt_profile.py',
             'm5_opt_release_check.py': 'zynq/m5_opt_release_check.py',
             'fixtures/manifest.json': 'build/m4_runtime_fixtures/manifest.json'}
    return dict(schema=1, frozen_git='e5883bcc99ad61bba381714781febb873a1101e3',
                board_budget_seconds=3600, cleanup_reserve_seconds=120,
                reference_budget_seconds=600, clock_hz=91000000,
                matrix=trials, pinned={p: sha(ROOT/q) for p, q in paths.items()},
                source_paths=paths, context_points=[1, 8, 13, 32, 128, 512, 1023],
                accounting='Full requests include on-FPGA prefill. Cached tests inject independent valid KV; seed restore is outside resident request time but inside campaign time. Profiling is diagnostic only.',
                omissions=['32-output run omitted: frozen generation oracle has 20 steps',
                           'No 1024-token physical prefill, endurance, CPU speed race, power or thermal claims'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--stage', type=Path, default=BUILD)
    args = parser.parse_args()
    args.stage.mkdir(parents=True, exist_ok=True)
    path = args.stage / 'policy.json'
    if path.exists():
        raise ValueError('policy already frozen')
    path.write_text(json.dumps(policy(), indent=2)+'\n')
    print(path)
