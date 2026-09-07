"""Stage a fresh short campaign; never load a module or take FPGA ownership."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from scripts.m5_sweep_policy import ROOT

BOARD = 'xilinx@10.0.0.223'
BASE = '/home/xilinx/pocketai_m5_context_ready_diag_v1'
REMOTE = '''import pathlib,sys,time
print(time.monotonic(), flush=True)
stage=pathlib.Path(sys.argv[1]); base=pathlib.Path(sys.argv[2]); seed=pathlib.Path(sys.argv[3]); stage.mkdir()
for name in ('m5_pynq.bit','m5_pynq.hwh','model.bin','layout.json','fixtures','m5_run.py','m5_opt_profile.py','m5_opt_release_check.py','m5_sweep.py'):
 (stage/name).symlink_to(base/name)
for past in (1022,1023):
 d=stage/'references'/('p'+str(past)); d.mkdir(parents=True)
 (d/'seed').symlink_to(seed)
 (d/'m5_profile.bin').symlink_to('../../m5_profile.bin')
'''


def main():
    p = argparse.ArgumentParser(__doc__); p.add_argument('--stage', type=Path, required=True)
    p.add_argument('--upload-seed', action='store_true')
    args = p.parse_args(); stage = args.stage.resolve()
    if not re.fullmatch(r'm5_context_[a-z0-9_]+', stage.name) or (stage/'staging.json').exists():
        raise ValueError('fresh context stage required')
    remote = '/home/xilinx/pocketai_'+stage.name
    seed = remote+'/seed' if args.upload_seed else BASE+'/references/p1022/seed'
    start = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        BOARD, 'python3', '-', remote, BASE, seed], input=REMOTE.encode()).decode().strip()
    if args.upload_seed:
        subprocess.run(['scp', '-qr', str(stage/'references/p1022/seed'), BOARD+':'+remote+'/seed'], check=True)
    for name in ('policy.json', 'references/manifest.json', 'm5_runtime.bin', 'm5_profile.bin',
                 'm5_context_run.py', 'm5_context_ready_run.py'):
        subprocess.run(['scp', '-q', str(stage/name), BOARD+':'+remote+'/'+name], check=True)
    (stage/'staging.json').write_text(json.dumps(dict(board_start_monotonic=float(start), remote=remote), indent=2)+'\n')
    print('STAGED', remote, 'CAMPAIGN_START', start)


if __name__ == '__main__': main()
