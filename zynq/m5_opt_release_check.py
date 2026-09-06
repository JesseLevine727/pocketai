"""Read-only post-close check: no allocation, overlay programming or model work."""
import argparse
import json
from pathlib import Path
import m5_run as m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('use a fresh release report')
    arena = m.DmaArena(Path('/dev/pocketai_m5'), {})
    try:
        info = arena.info()
    finally:
        arena.close()
    report = {'status': 'PASS' if info['allocated_pages'] == 0 and info['owner'] == 0 else 'FAIL',
              'info_after_close_reopen': info, 'runner_sha256': m.sha256_file(Path(__file__))}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    if report['status'] != 'PASS':
        raise RuntimeError('retained allocation or device ownership')
    print('M5 OPT RELEASE PASS', json.dumps(info), flush=True)


if __name__ == '__main__':
    main()
