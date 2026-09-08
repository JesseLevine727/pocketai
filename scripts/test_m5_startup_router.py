"""Fast bounded protocol scoreboard, independent of the firmware integration test."""
import argparse
from pathlib import Path
from scripts.m5_startup_fetch import ROOT, direct_router
from scripts.test_m5_startup_icache_probe import run


def main():
    p=argparse.ArgumentParser(__doc__); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--early-local', action='store_true')
    p.add_argument('--prefetch', action='store_true')
    a=p.parse_args(); out=a.output.resolve()
    if out.exists() or not out.name.startswith('m5_startup_'): raise ValueError('fresh startup directory required')
    out.mkdir(); (out/'pa_m5_obi_router.sv').write_bytes(direct_router(a.early_local, a.prefetch))
    probe = out/'router_probe.cc'; probe.write_bytes((ROOT/'tests/m5_startup/router_probe.cc').read_bytes())
    for mode in ((0, 1, 2) if a.early_local else (0, 1, 3) if a.prefetch else (0, 1)):
        directory=out/f'mode_{mode}'
        parameters = [f"-GDirectResponse=1'b{int(mode != 0)}"]
        if a.early_local: parameters += [f"-GEarlyLocal=1'b{int(mode == 2)}"]
        if a.prefetch: parameters += [f"-GInstantLocal=1'b{int(mode == 3)}"]
        run(['verilator', '--cc', '--exe', '--build', '-j', '2', '--assert', '-Wall',
             '--top-module', 'pa_m5_obi_router', *parameters,
             '--Mdir', directory, '-CFLAGS', '-std=c++17 -O2', out/'pa_m5_obi_router.sv',
             probe], out/f'build_{mode}.log', timeout=60)
        run([directory/'Vpa_m5_obi_router', mode], out/f'test_{mode}.log', timeout=10)
        print((out/f'test_{mode}.log').read_text())


if __name__ == '__main__': main()
