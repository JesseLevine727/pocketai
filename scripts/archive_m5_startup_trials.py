"""Archive the *deployed* historical Python runners, never current source aliases."""
import json
from pathlib import Path
import subprocess
from scripts.m5_sweep_policy import ROOT, sha
from scripts.stage_m5_startup import BOARD


def main():
    count = 0
    for report in sorted((ROOT/'build').glob('m5_startup_*/campaign.json')):
        stage = report.parent
        d = json.loads(report.read_text())
        staging = json.loads((stage/'staging.json').read_text())
        target = stage/'deployed'
        names = {name: digest for name, digest in d['policy']['pinned'].items()
                 if name.endswith('.py')}
        if not target.exists():
            target.mkdir()
            subprocess.run(['scp', '-q'] + [BOARD+':'+staging['remote']+'/'+name for name in names]
                           + [str(target)], check=True, timeout=60)
        for name, expected in names.items():
            if sha(target/name) != expected:
                raise ValueError('deployed historical identity mismatch: '+str(target/name))
        count += 1
    print('STARTUP HISTORICAL DEPLOYED-RUNNER ARCHIVE PASS', count, 'campaigns')


if __name__ == '__main__': main()
