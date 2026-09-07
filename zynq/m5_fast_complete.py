"""Run the unchanged full-request checker under a cleanup-safe campaign alarm."""
import argparse
import json
from pathlib import Path
import signal
import sys
import time

import m5_run


def expired(_signum, _frame):
    # m5_run catches BaseException and returns ownership/closes in finally.
    raise TimeoutError('M5 fast complete campaign exceeded 1200 seconds')


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    stage = args.stage.resolve()
    output = stage / 'physical_complete.json'
    watchdog = stage / 'campaign.json'
    if output.exists() or watchdog.exists():
        raise ValueError('use a fresh complete qualification stage')
    report = dict(status='FAIL', watchdog_seconds=1200,
                  runner_sha256=m5_run.sha256_file(Path(__file__)),
                  checked_runner_sha256=m5_run.sha256_file(Path(m5_run.__file__)))
    started = time.monotonic()
    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(1200)
    try:
        sys.argv = ['m5_run.py', '--stage', str(stage), '--output', str(output),
                    '--timeout', '600']
        m5_run.main()
        report['status'] = 'PASS'
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        report['elapsed_seconds'] = time.monotonic() - started
        watchdog.write_text(json.dumps(report, indent=2) + '\n')
    print('M5 FAST COMPLETE CAMPAIGN PASS', flush=True)


if __name__ == '__main__':
    main()
