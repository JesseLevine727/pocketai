"""Cache-enabled copy of the frozen fast-M ISA suite; same tests and waivers."""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from scripts.m5_fast_sources import ROOT, compliance, pinned, digest


def main():
    p = argparse.ArgumentParser(__doc__); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); out = a.output.resolve()
    if out.exists() or not out.name.startswith('m5_startup_'):
        raise ValueError('fresh startup output required')
    out.mkdir()
    pinned(ROOT/'scripts/m5_fast_sources.py',
        'e75dd2a76ef2e4bfb145e0f85845a5c3c894524133122eff0cdc83b2787561c2')
    compliance(out/'parent.sh', pipeline=True)
    copied = out/'compliance'
    shutil.copytree(ROOT/'riscv-compliance', copied,
                    ignore=shutil.ignore_patterns('.git', 'work', 'build', '__pycache__'))
    header = copied/'riscv-target/ibex/compliance_test.h'
    source = header.read_text()
    lines = source.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.strip() == 'RVTEST_CODE_BEGIN                                                     \\']
    if len(matches) != 1: raise ValueError('ambiguous test entry')
    idx = matches[0]+1
    lines[idx:idx] = ['        '+line+' \\\n' for line in (
        'li t0, 1; csrs 0x7c0, t0; csrr t1, 0x7c0;',
        'andi t1, t1, 1; bnez t1, 991f; unimp;',
        '991: li t0, 0; li t1, 0;')]
    header.write_text(''.join(lines))
    script = (out/'parent.sh').read_text()
    script = script.replace('COMPLIANCE_DIR="$ROOT/riscv-compliance"',
                            'COMPLIANCE_DIR='+shlex.quote(str(copied)))
    script = script.replace('M5_ISA_BUILD=$(mktemp -d "$ROOT/build/m5_fast_compliance.XXXXXX")',
                            'M5_ISA_BUILD='+shlex.quote(str(out/'run'))+'\nmkdir "$M5_ISA_BUILD"')
    script = script.replace('--ICache=0', '--ICache=1').replace('-GICache=0', '-GICache=1')
    script = script.replace('M5 FAST DERIVED-IBEX COMPLIANCE PASS', 'STARTUP CACHE-ENABLED ISA PASS')
    if 'mktemp' in script: raise ValueError('test work escaped startup scope')
    (out/'run.sh').write_text(script)
    (out/'manifest.json').write_text(json.dumps(dict(schema=1,
        source_header_sha256=digest(source.encode()), derived_header_sha256=digest(header.read_bytes()),
        script_sha256=digest(script.encode()), tests=88, unchanged_expected_failures=4,
        note='ICache instantiated AND CSR enabled/read back before every test'), indent=2)+'\n')
    with (out/'test.log').open('w') as stream:
        subprocess.run(['bash', str(out/'run.sh')], cwd=ROOT, stdout=stream,
                       stderr=subprocess.STDOUT, check=True, timeout=300)
    print((out/'run/result.log').read_text())


if __name__ == '__main__': main()
