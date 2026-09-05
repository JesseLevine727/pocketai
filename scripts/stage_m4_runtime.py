"""Create a fresh, scoped board bundle; never push git or overwrite evidence."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
from ref.m4_model_pack import file_sha256
from zynq.m4_offload import PACK_SHA
from zynq.m4_driver import BIT_SHA, HWH_SHA


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gemm-library', type=Path, required=True)
    parser.add_argument('--sfpu-library', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source_pack = root / 'build/m4_pack_v3'
    if file_sha256(source_pack / 'manifest.json') != PACK_SHA:
        raise ValueError('unexpected source model pack')
    overlay = root / 'build/m3_qual3'
    for filename, expected in (('m3_pynq.bit', BIT_SHA), ('m3_pynq.hwh', HWH_SHA)):
        if file_sha256(overlay / filename) != expected:
            raise ValueError('unexpected overlay')
    fixtures = root / 'build/m4_runtime_fixtures'
    if not (fixtures / 'manifest.json').is_file():
        raise ValueError('reference fixture export has not completed')
    stage = Path(tempfile.mkdtemp(prefix='m4_runtime_stage.', dir=root / 'build'))
    for folder in ('ref', 'zynq'):
        (stage / folder).mkdir()
    sources = ('ref/__init__.py', 'ref/m4_model_pack.py', 'ref/m4_cpu.py', 'ref/m4_cpu_sfpu.py',
               'ref/sfpu_ref.py', 'ref/sfpu_stream.py', 'zynq/m4_offload.py', 'zynq/m4_driver.py',
               'zynq/m4_run.py', 'zynq/m4_control_checks.py', 'zynq/m4_cpu_gemm.c', 'zynq/m4_cpu_sfpu.c')
    for name in sources:
        shutil.copy2(root / name, stage / name)
    for filename in ('m3_pynq.bit', 'm3_pynq.hwh'):
        shutil.copy2(overlay / filename, stage / filename)
    shutil.copy2(args.gemm_library, stage / 'm4_cpu_gemm.so')
    shutil.copy2(args.sfpu_library, stage / 'm4_cpu_sfpu.so')
    shutil.copytree(source_pack, stage / 'pack')
    shutil.copytree(fixtures, stage / 'fixtures')
    manifest = {'schema': 1, 'purpose': 'M4 runtime correctness; no performance or closure claim',
                'stager_sha256': file_sha256(__file__),
                'sha256': {str(path.relative_to(stage)): file_sha256(path) for path in sorted(stage.rglob('*')) if path.is_file()}}
    (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('M4 STAGE READY', stage, file_sha256(stage / 'manifest.json'), flush=True)


if __name__ == '__main__':
    main()
