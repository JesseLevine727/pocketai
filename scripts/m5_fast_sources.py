#!/usr/bin/env python3
"""Isolated, fail-closed fast-M derivation; never change a historical export."""
import argparse
import hashlib
from pathlib import Path
import re
import shlex

import yaml

try:
    from scripts.check_m5_sources import check as check_lsu
except ModuleNotFoundError:  # Direct absolute invocation inside Vivado's cwd.
    from check_m5_sources import check as check_lsu

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = 'src/pocketai_pa_pa_cluster_rtl_0.1/pa_ibex_wrapper.sv'
ORIGINAL = '573d62d1b3dc0e63c6af2a707bd013e356160258eace9e6b319994ed5a5e0d2e'
CLUSTER = '29bd91ee2b967404df2298ecae5ad358104cbc685a39a008df235457db6db78c'
MULTIPLIER = 'c86ca819b58b8ce2fc4ff5db887346bcd622b868fb7815fa07dd77119c68c04a'
OLD = '''    // The iterative unit avoids both DSP48 inference and the long soft
    // multiplier path of RV32MFast at the board's fixed 100 MHz PL clock.
    .RV32M             (ibex_pkg::RV32MSlow),'''
NEW = '''    // M5 fast-controller target: both harts use the multi-cycle fast unit.
    // The isolated 91-MHz implementation is constrained to zero DSPs.
    .RV32M             (ibex_pkg::RV32MFast),'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, expected):
    data = path.read_bytes()
    if digest(data) != expected:
        raise RuntimeError(f'unexpected source identity: {path}')
    return data


def derived_wrapper():
    original = pinned(ROOT / 'rtl/soc/pa_ibex_wrapper.sv', ORIGINAL).decode()
    if original.count(OLD) != 1:
        raise RuntimeError('ambiguous fast-M derivation')
    return original.replace(OLD, NEW).encode()


def pipelined_multiplier():
    source = pinned(ROOT / 'rtl/ibex-orig/rtl/ibex_multdiv_fast.sv', MULTIPLIER).decode()
    source = source.replace('  logic        multdiv_en;', '  logic        multdiv_en;\n  logic        mult_commit;')
    source = source.replace('assign multdiv_en = mult_en_internal | div_en_internal;',
                            'assign multdiv_en = (mult_en_internal & mult_commit) | div_en_internal;')
    source = source.replace('begin : gen_mult_single_cycle\n',
                            "begin : gen_mult_single_cycle\n    assign mult_commit = 1'b1;\n")
    prefix, fast = source.split('  end else begin : gen_mult_fast', 1)
    kernel_start = fast.index('    // The 2 MSBs of mac_res_ext')
    kernel_end = fast.index('    always_comb begin', kernel_start)
    fast = fast[:kernel_start] + (ROOT / 'rtl/m5_fast/pipelined_kernel.sv.inc').read_text() + '\n' + fast[kernel_end:]
    fast = fast.replace('      endcase // mult_state_q',
                        '      endcase // mult_state_q\n'
                        '      mult_valid = mult_valid & mult_commit;\n'
                        '      mult_hold = mult_hold & mult_commit;', 1)
    register_start = fast.index('    always_ff @(posedge clk_i or negedge rst_ni) begin')
    register_end = fast.index('    // States must be known/valid.', register_start)
    fast = fast[:register_start] + (ROOT / 'rtl/m5_fast/pipelined_registers.sv.inc').read_text() + '\n' + fast[register_end:]
    fast = fast.replace('assign sva_mul_fsm_idle = mult_state_q == ALBL;',
                        'assign sva_mul_fsm_idle = (mult_state_q == ALBL) && (mac_phase_q == 0);', 1)
    return (prefix + '  end else begin : gen_mult_fast' + fast).encode()


def prepare(work):
    # Only a fresh, explicitly marked new export can opt into this derivation.
    if not (work / 'M5_FAST_TARGET').is_file():
        raise RuntimeError('missing explicit M5_FAST_TARGET marker')
    target = work / WRAPPER
    if target.is_symlink() or target.resolve() != work / WRAPPER:
        raise RuntimeError('wrapper export escapes work root')
    expected = derived_wrapper()
    actual = target.read_bytes()
    if digest(actual) == ORIGINAL:
        target.write_bytes(expected)
    elif actual != expected:
        raise RuntimeError('unknown exported wrapper; refusing mutation')
    if (work / 'M5_FAST_PIPELINED').is_file():
        target = work / 'src/lowrisc_ibex_ibex_core_0.1/rtl/ibex_multdiv_fast.sv'
        if target.is_symlink() or target.resolve() != target:
            raise RuntimeError('multiplier export escapes work root')
        expected = pipelined_multiplier()
        actual = target.read_bytes()
        if digest(actual) == MULTIPLIER:
            target.write_bytes(expected)
        elif actual != expected:
            raise RuntimeError('unknown exported multiplier; refusing mutation')


def check(work, model=False):
    check_lsu(work)
    pinned(work / WRAPPER, digest(derived_wrapper()))
    pinned(work / 'src/pocketai_pa_pa_m5_rtl_0.1/pa_m5_cluster_top.sv', CLUSTER)
    pipeline = (work / 'M5_FAST_PIPELINED').is_file()
    multiplier_hash = digest(pipelined_multiplier()) if pipeline else MULTIPLIER
    pinned(work / 'src/lowrisc_ibex_ibex_core_0.1/rtl/ibex_multdiv_fast.sv', multiplier_hash)
    manifests = list(work.glob('*.eda.yml'))
    if len(manifests) != 1:
        raise RuntimeError('expected exactly one resolved source manifest')
    files = yaml.safe_load(manifests[0].read_text())['files']
    required = {Path(WRAPPER).name: WRAPPER,
                'pa_m5_cluster_top.sv': 'src/pocketai_pa_pa_m5_rtl_0.1/pa_m5_cluster_top.sv'}
    for name in ('ibex_multdiv_fast.sv', 'ibex_load_store_unit.sv', 'ibex_id_stage.sv'):
        required[name] = 'src/lowrisc_ibex_ibex_core_0.1/rtl/' + name
    for name, relative in required.items():
        matches = [f for f in files if Path(f['name']).name == name]
        if len(matches) != 1:
            raise RuntimeError(f'ambiguous or missing compiled source {name}')
        path = work / matches[0]['name']
        if not path.is_file() or path.resolve() != path.absolute() or not path.is_relative_to(work):
            raise RuntimeError(f'compiled path escapes export: {path}')
        if path != work / relative:
            raise RuntimeError(f'compiler does not use the qualified source: {name}')
    if model:
        headers = list(work.glob('Vpa_m5_cluster_top*.h'))
        text = '\n'.join(p.read_text() for p in headers)
        symbols = (work / 'Vpa_m5_cluster_top__Syms.h').read_text()
        for hart in (0, 1):
            instance = re.search(rf'(Vpa_m5_cluster_top_\w+)\s+TOP__pa_m5_cluster_top__DOT__u_core{hart}__DOT__u_ibex;', symbols)
            if not instance:
                raise RuntimeError(f'cannot resolve elaborated hart {hart} type')
            core = (work / (instance[1] + '.h')).read_text()
            if not re.search(r'gen_multdiv_fast__DOT__[^\n]*gen_mult_fast__DOT__mult_state_q', core):
                raise RuntimeError(f'elaborated hart {hart} is not multi-cycle fast M')
            if pipeline and 'gen_mult_fast__DOT__mac_phase_q' not in core:
                raise RuntimeError(f'pipeline missing from hart {hart}')
        if 'gen_multdiv_slow__DOT__' in text or 'gen_mult_single_cycle__DOT__' in text:
            raise RuntimeError('wrong elaborated multiplier present')
        print('M5 FAST ELABORATION PASS hart0=RV32MFast hart1=RV32MFast')
    print(f'M5 FAST SOURCE PASS wrapper={digest(derived_wrapper())} both_harts=fast pipeline={pipeline} multiplier={multiplier_hash}')


def compliance(output, pipeline=False):
    """Reuse the exact original suite/waivers, changing only M configuration."""
    source = pinned(ROOT / 'sim/run_m5_compliance.sh',
                    'f9174c73134582f4d60a1d0583aba80cb94f7d170aa0e4f146180bc439a70814').decode()
    source = source.replace('ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"',
                            'ROOT=' + shlex.quote(str(ROOT)))
    source = source.replace('RV32MSlow', 'RV32MFast').replace('gen_multdiv_slow', 'gen_multdiv_fast')
    source = source.replace('slow-M/FPGA', 'fast-M/FPGA').replace('m5_compliance.', 'm5_fast_compliance.')
    source = source.replace('M5 DERIVED-IBEX COMPLIANCE PASS', 'M5 FAST DERIVED-IBEX COMPLIANCE PASS')
    if pipeline:
        source = source.replace('make -C "$SIM_WORK" \\\n',
            'python3 -m scripts.m5_fast_sources "$SIM_WORK" --prepare-compliance\nmake -C "$SIM_WORK" \\\n', 1)
        source = source.replace('declare -A expected_total=(',
            'grep -Fq "gen_mult_fast__DOT__mac_phase_q" "$SIM_MODEL_HEADER"\ndeclare -A expected_total=(', 1)
    with output.open('x') as stream:
        stream.write(source)


def board_tcl(output):
    source = pinned(ROOT / 'zynq/build_m5.tcl',
                    '9c292f85fe8b19cde6323b6d62ddef90587dc3bd8930472a0a778beb9d099b36').decode()
    source = source.replace('set root_dir [file normalize [file dirname [file dirname [info script]]]]',
                            'set root_dir [file normalize $::env(M5_FAST_REPO_ROOT)]')
    source = source.replace('puts [exec python3 "$root_dir/scripts/check_m5_sources.py" [file dirname $source_tcl]]',
                            'puts [exec $::env(M5_FAST_PYTHON) -E "$root_dir/scripts/m5_fast_sources.py" [file dirname $source_tcl]]')
    marker = 'launch_runs impl_1 -to_step write_bitstream -jobs 8'
    extra = '''# Fast-target structural acceptance on actual synthesized cells.
open_run synth_1
set fast_fd [open "$reports_dir/m5_fast_synth_configuration.rpt" w]
foreach hart {0 1} {
  set fast_cells [get_cells -hierarchical -quiet -filter "NAME =~ *u_core${hart}*gen_multdiv_fast*gen_mult_fast*"]
  if {[llength $fast_cells] == 0} { error "No synthesized multi-cycle fast multiplier on hart $hart" }
  puts $fast_fd "hart=$hart multiplier=RV32MFast cells=[llength $fast_cells] example=[lindex $fast_cells 0]"
}
if {[llength [get_cells -hierarchical -quiet -filter {NAME =~ *gen_multdiv_slow* || NAME =~ *gen_mult_single_cycle*}]] != 0} {
  error "Unexpected slow or single-cycle multiplier in synthesized design"
}
if {[llength [get_cells -hierarchical -quiet -filter {PRIMITIVE_TYPE =~ DSP.*}]] != 0} { error "Fast target inferred DSPs" }
puts $fast_fd "dsp_count=0"
close $fast_fd
close_design
'''
    if source.count(marker) != 1:
        raise RuntimeError('ambiguous board derivation')
    with output.open('x') as stream:
        stream.write(source.replace(marker, extra + marker))


def finish_tail(output):
    source = pinned(ROOT / 'zynq/build_m5.tcl',
                    '9c292f85fe8b19cde6323b6d62ddef90587dc3bd8930472a0a778beb9d099b36').decode()
    tail = source[source.index('set fabric_clocks [get_clocks'):]
    tail = tail.replace('set bit_src "$build_dir/m5_pynq.runs/impl_1/system_wrapper.bit"',
                        'set bit_src "$build_dir/final.bit"')
    tail = tail.replace('set hwh_src "$build_dir/m5_pynq.gen/', 'set hwh_src "$source_build/m5_pynq.gen/')
    with output.open('x') as stream:
        stream.write(tail)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('work', type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--model', action='store_true')
    parser.add_argument('--emit-compliance', action='store_true')
    parser.add_argument('--emit-board-tcl', action='store_true')
    parser.add_argument('--pipeline', action='store_true')
    parser.add_argument('--prepare-compliance', action='store_true')
    parser.add_argument('--emit-finish-tail', action='store_true')
    args = parser.parse_args()
    if args.emit_compliance:
        compliance(args.work, args.pipeline)
    elif args.emit_board_tcl:
        board_tcl(args.work)
    elif args.emit_finish_tail:
        finish_tail(args.work)
    elif args.prepare_compliance:
        work = args.work.resolve()
        check_lsu(work)
        target = work / 'src/lowrisc_ibex_ibex_core_0.1/rtl/ibex_multdiv_fast.sv'
        if target.is_symlink() or target.resolve() != target:
            raise RuntimeError('unsafe compliance source')
        pinned(target, MULTIPLIER)
        target.write_bytes(pipelined_multiplier())
        print(f'M5 FAST PIPELINE COMPLIANCE DERIVATION {digest(target.read_bytes())}')
    else:
        work = args.work.resolve()
        if args.prepare:
            prepare(work)
        check(work, args.model)
