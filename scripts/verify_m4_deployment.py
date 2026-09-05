"""Read-only full source/asset preflight for a frozen M4 deployment.

No downloads, model evaluation, remote calls, programming or threshold changes.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from ref.m4_model_pack import ModelPack, file_sha256
from zynq.m4_offload import CANDIDATE_SHA, PACK_SHA
from zynq.m4_driver import BIT_SHA, HWH_SHA

FIXTURE_SHA = '7324fb3a88c9b7340e9aa65ea6dd43f77253f0ddf7e7aca9fb100f47f963c537'


def verify_files(directory, entries):
    """Validate actual bytes, not only the manifest describing those bytes."""
    directory = Path(directory).resolve()
    result = {}
    for name, entry in entries.items():
        path = (directory / name).resolve()
        if path.parent != directory:
            raise ValueError('asset escapes its pinned directory: ' + name)
        if ('size' in entry and path.stat().st_size != entry['size']) or file_sha256(path) != entry['sha256']:
            raise ValueError('pinned asset bytes changed: ' + name)
        result[name] = entry['sha256']
    return result


def verify_deployment(root):
    root = Path(root).resolve()
    freeze_path = root / 'tests/m4/adaptive_candidate.json'
    if file_sha256(freeze_path) != CANDIDATE_SHA:
        raise ValueError('not the selected frozen candidate')
    freeze = json.loads(freeze_path.read_text())
    verified = {}
    for group in ('source_sha256', 'asset_sha256', 'selection_evidence_sha256'):
        for name, expected in freeze[group].items():
            path = (root / name).resolve()
            if not path.is_relative_to(root) or file_sha256(path) != expected:
                raise ValueError('frozen deployment source changed: ' + name)
            verified[name] = expected
    model_dir = root / 'build/m4_model'
    model = json.loads((model_dir / 'model_manifest.json').read_text())
    model_files = verify_files(model_dir, model['files'])
    pack_dir = root / 'build/m4_pack_v3'
    if file_sha256(pack_dir / 'manifest.json') != PACK_SHA:
        raise ValueError('not the accepted model-pack manifest')
    pack = ModelPack(pack_dir, CANDIDATE_SHA)
    fixtures_dir = root / 'build/m4_runtime_fixtures'
    if file_sha256(fixtures_dir / 'manifest.json') != FIXTURE_SHA:
        raise ValueError('not the frozen independent runtime fixtures')
    fixtures = json.loads((fixtures_dir / 'manifest.json').read_text())
    tensor_files = {}
    for case in fixtures['cases']:
        for entry in case['tensors'].values():
            if entry['file'] in tensor_files:
                raise ValueError('duplicate reference tensor file')
            tensor_files[entry['file']] = {'sha256': entry['sha256']}
    verify_files(fixtures_dir, tensor_files)
    for name, expected in (('m3_pynq.bit', BIT_SHA), ('m3_pynq.hwh', HWH_SHA)):
        if file_sha256(root / 'build/m3_qual3' / name) != expected:
            raise ValueError('not the accepted M3 overlay: ' + name)
    return {'status': 'DEPLOYMENT_SOURCE_IDENTITY_PASS_NOT_RUNTIME_ACCEPTANCE',
            'verified_utc': datetime.now(timezone.utc).isoformat(), 'verifier_sha256': file_sha256(__file__),
            'candidate_sha256': CANDIDATE_SHA, 'frozen_source_asset_evidence_sha256': verified,
            'model_repository': model['repository'], 'model_revision': model['revision'],
            'model_license': model['license'], 'model_actual_file_sha256': model_files,
            'pack_manifest_sha256': PACK_SHA, 'pack_arrays_checked': len(pack.arrays),
            'pack_payload_bytes': pack.payload_bytes, 'fixture_manifest_sha256': FIXTURE_SHA,
            'independent_tensor_files_checked': len(tensor_files),
            'bit_sha256': BIT_SHA, 'hwh_sha256': HWH_SHA,
            'notes': ['Actual checkpoint, configuration, tokenizer, vocabulary, merges and license bytes checked.',
                      'Every packed array and independent tensor fixture checked against frozen manifests.',
                      'Packed weights, not the original 548 MB safetensors file, are loaded by the board runtime.',
                      'Identity verification is not model quality, runtime correctness, performance or M4 closure.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite deployment preflight evidence')
    report = verify_deployment(Path(__file__).resolve().parents[1])
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 DEPLOYMENT SOURCE PREFLIGHT PASS', args.output, flush=True)


if __name__ == '__main__':
    main()
