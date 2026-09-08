"""Conservative linked-image stack bound, including callback and libgcc frames."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from scripts.m5_sweep_policy import sha


def check(build, kind):
    elf = build/f'm5_{kind}.elf'
    disassembly = subprocess.check_output(['riscv64-unknown-elf-objdump', '-d', str(elf)], text=True)
    functions = {}
    for line in disassembly.splitlines():
        match = re.match(r'^[0-9a-f]+ <([^>]+)>:', line)
        if match:
            name = match[1]; functions[name] = []
        elif re.match(r'^\s+[0-9a-f]+:', line): functions[name].append(line)
    frames, edges, indirect = {}, {}, {}
    for name, lines in functions.items():
        frames[name] = 0; edges[name] = set()
        for line in lines:
            fields = line.split('\t')
            if len(fields) < 4: continue
            op, arg = fields[-2].strip(), fields[-1].strip()
            if name != 'reset_handler':
                frame = re.match(r'sp,sp,(-?\d+)', arg)
                if op in ('add', 'addi') and frame:
                    frames[name] += max(0, -int(frame[1]))
                elif re.match(r'sp[,\s]', arg) and op not in ('sw', 'sd'):
                    raise ValueError('unreviewed stack adjustment: '+line)
            if op in ('jal', 'jalr', 'j', 'jr', 'call', 'tail'):
                target = re.search(r'<([^>+]+)(?:\+[^>]+)?>', arg)
                if target and target[1] != name:
                    edges[name].add(target[1])
                elif not target and op in ('jalr', 'jr') and arg not in ('ra', '0(ra)'):
                    indirect.setdefault(name, []).append(line.strip())
    # .su catches compiler-level frames; the disassembly additionally covers
    # linked libgcc functions which have no application .su file.
    for path in build.glob(f'm5_{kind}.elf-*.su'):
        for line in path.read_text().splitlines():
            origin, size, qualifier = line.split('\t')
            if qualifier != 'static': raise ValueError('dynamic stack frame: '+line)
            name = origin.rsplit(':', 1)[1]
            for symbol in functions:
                if symbol == name or re.sub(r'\.\d+$', '', symbol) == name:
                    frames[symbol] = max(frames[symbol], int(size))
    generated = '\n'.join(p.read_text() for p in (build/'generated').glob('*.c'))
    sources = generated + '\n' + (Path('runtime/m5_context/score_parallel.c').read_text())
    leaves = set(re.findall(r'pa_context_parallel\((\w+),', sources)) & functions.keys()
    # Context's compiled helper sources contain additional score leaves.
    for path in (Path('runtime/m5_context')).glob('*.c'):
        leaves.update(set(re.findall(r'pa_context_parallel\((\w+),', path.read_text())) & functions.keys())
    backend = {'hardware_gemm', 'hardware_sfpu'}
    if kind in ('profile', 'detail'): backend = {'prof_gemm', 'prof_sfpu'}
    assignments = {}
    for name in indirect:
        if name in ('pa_context_parallel', 'pa_context_parallel_execute'):
            assignments[name] = leaves
        elif name == 'pa_m5_forward_chunk':
            assignments[name] = {'capture_trace'} if kind in ('runtime', 'trace') else {'checkpoint'}
        elif name == 'prof_gemm': assignments[name] = {'hardware_gemm'}
        elif name == 'prof_sfpu': assignments[name] = {'hardware_sfpu'}
        elif name in ('pa_scalar_uniform_affine', 'pa_search_project_affine',
                      'pa_iter_attention_affine',
                      'pa_context_attention_legacy',
                      'pa_m5_apply_norm', 'pa_m5_gelu', 'pa_m5_attention',
                      'pa_m5_project', 'pa_m5_smooth') or name.startswith('affine_row.constprop'):
            assignments[name] = backend
        elif name == '__divdf3':
            # GCC soft-f64 division's internal switch jump table; no call/new
            # frame. Direct call/tail edges elsewhere are still followed.
            if len(indirect[name]) != 1 or '\tjr\t' not in indirect[name][0]:
                raise ValueError('changed libgcc dispatch')
            assignments[name] = set()
        else: raise ValueError(kind+' '+name+' unreviewed indirect dispatch: '+repr(indirect[name]))
        if assignments[name] - functions.keys(): raise ValueError('callback missing from linked image')
        edges[name].update(assignments[name])
    memo = {}
    def bound(name, visiting=()):
        if name in visiting: raise ValueError('recursive stack path: '+repr(visiting+(name,)))
        if name not in functions: raise ValueError('unresolved linked callee '+name)
        if name in memo: return memo[name]
        child = max((bound(x, visiting+(name,)) for x in edges[name]), default=(0, []))
        result = (frames[name]+child[0], [name]+child[1]); memo[name] = result
        return result
    normal, path = bound('m5_memory_main')
    trap, trap_path = bound('m5_memory_trap')
    total = normal+trap
    if total > 4096: raise ValueError(f'{kind} conservative stack bound {total} > 4096: {path}')
    return dict(kind=kind, elf_sha256=sha(elf), firmware_sha256=sha(build/f'm5_{kind}.bin'),
        shared_per_hart_bound_bytes=total,
        normal_bytes=normal, path=path, trap_bytes=trap, trap_path=trap_path,
        limit_bytes=4096, frames=frames,
        indirect_targets={n: sorted(v) for n, v in assignments.items()},
        note='Conservative: both hart branches and all legitimate callbacks; tail frames overcounted; includes one nonreturning trap.')


def main():
    p = argparse.ArgumentParser(__doc__); p.add_argument('build', type=Path)
    p.add_argument('--output', type=Path)
    a = p.parse_args(); result = [check(a.build, kind) for kind in ('runtime', 'profile', 'detail', 'trace')]
    if a.output:
        with a.output.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    for r in result: print('STARTUP STACK PASS', r['kind'], r['shared_per_hart_bound_bytes'], '/ 4096', r['path'])


if __name__ == '__main__': main()
