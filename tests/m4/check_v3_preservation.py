"""Audit that the development-driven range fix preserved measured v2 behavior."""
import json
from pathlib import Path
from ref.m4_model_pack import file_sha256


def main():
    output = Path('build/m4_v3_preservation.json')
    if output.exists():
        raise ValueError('refusing to overwrite preservation evidence')
    checks, hashes = {}, {}
    for stem, keys in (('heldout_quality', ('aggregate', 'groups')),
                       ('generation', ('cases',)), ('pack_manifest', ('arrays',))):
        paths = ([Path(f'build/m4_pack_{v}/manifest.json') for v in ('v2', 'v3')] if stem == 'pack_manifest'
                 else [Path(f'build/m4_{v}_{stem}.json') for v in ('v2', 'v3')])
        a, b = (json.loads(path.read_text()) for path in paths)
        for key in keys:
            if a[key] != b[key]:
                raise AssertionError(f'v3 changed {stem}.{key}')
            checks[stem + '.' + key] = 'EXACT_EQUAL'
        hashes.update({str(path): file_sha256(path) for path in paths})
    report = {'status': 'PASS', 'checks': checks, 'evidence_sha256': hashes,
              'runner_sha256': file_sha256(__file__),
              'scope': 'All reported held-out groups/metrics, all generation tokens/logit hashes, all packed arrays. The 1024-token clipping fix is separately verified on development stress.'}
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 V3 PRESERVATION PASS', json.dumps(checks), flush=True)


if __name__ == '__main__':
    main()
