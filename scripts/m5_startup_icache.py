"""Isolated I-cache hypothesis; preserve all earlier fast-M exports."""
import argparse
import json
from pathlib import Path
import re
import sys
import yaml
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.m5_fast_sources import (ROOT, WRAPPER, CLUSTER, derived_wrapper,
    pinned, digest, pipelined_multiplier, board_tcl as parent_board_tcl)
from scripts.check_m5_sources import check as check_lsu
from scripts.m5_iterate_sources import once

XILINX_RAM = 'src/lowrisc_prim_xilinx_ram_1p_0/rtl/prim_ram_1p.sv'
XILINX_RAM_SHA = '99d8d9fd815d79d2a2dd1d72393146f9fe680d9366839528bee08e18aa04190a'


def block_ram():
    source = pinned(ROOT/'rtl/ibex-orig/vendor/lowrisc_ip/ip/prim_xilinx/rtl/prim_ram_1p.sv',
                    XILINX_RAM_SHA).decode()
    # Inference only: same synchronous one-cycle read, enables and write mask.
    return once(source, '    logic [Width-1:0]     mem [Depth];',
                '    (* ram_style = "block" *) logic [Width-1:0] mem [Depth];').encode()


def wrapper():
    return once(derived_wrapper().decode(), '.ICache            (1\'b0)', '.ICache            (1\'b1)').encode()


def start():
    source = pinned(ROOT/'firmware/m5/memory_test_start.S',
        '52765bdb2a6e093068b9258f3bce9c0681c85a200c0c6a04b5641f776dc3fd4b').decode()
    return once(source, '  csrw mie, zero', '''  csrw mie, zero
  /* CSR CPUCTRLSTS bit zero enables the instantiated instruction cache.
   * CSR state and cache validity reset per request; fills stay after START. */
  li t1, STARTUP_ICACHE_ENABLE
  csrs 0x7c0, t1''')


def required_start():
    """Fail closed on a physical image loaded on a cache-disabled overlay."""
    return start().replace('STARTUP_ICACHE_ENABLE', '1').replace(
        '  csrs 0x7c0, t1', '''  csrs 0x7c0, t1
  csrr t0, 0x7c0
  andi t0, t0, 1
  bnez t0, 2f
  ebreak
2:''')


def check_export(work, model=False):
    check_lsu(work)
    required = {
        WRAPPER: digest(wrapper()),
        'src/pocketai_pa_pa_m5_rtl_0.1/pa_m5_cluster_top.sv': CLUSTER,
        'src/lowrisc_ibex_ibex_core_0.1/rtl/ibex_multdiv_fast.sv': digest(pipelined_multiplier()),
    }
    if (work/XILINX_RAM).exists():
        required[XILINX_RAM] = (digest(block_ram()) if (work/'M5_STARTUP_BLOCK_RAM').exists()
                               else XILINX_RAM_SHA)
    manifests = list(work.glob('*.eda.yml'))
    if len(manifests) != 1: raise ValueError('one EDA manifest required')
    files = yaml.safe_load(manifests[0].read_text())['files']
    for relative, expected in required.items():
        path = work/relative
        if path.resolve() != path.absolute(): raise ValueError('source escapes export')
        pinned(path, expected)
        matches = [f for f in files if Path(f['name']).name == path.name]
        if len(matches) != 1 or work/matches[0]['name'] != path:
            raise ValueError('compiled source identity mismatch: '+relative)
    for name in ('ibex_top.sv', 'ibex_icache.sv', 'ibex_cs_registers.sv', 'ibex_pkg.sv'):
        matches = [f for f in files if Path(f['name']).name == name]
        if len(matches) != 1: raise ValueError('ambiguous I-cache source: '+name)
        path = work/matches[0]['name']
        if path.resolve() != path.absolute(): raise ValueError('I-cache source escapes export')
        pinned(path, digest((ROOT/'rtl/ibex-orig/rtl'/name).read_bytes()))
    if model:
        symbols = (work/'Vpa_m5_cluster_top__Syms.h').read_text()
        headers = '\n'.join(p.read_text() for p in work.glob('Vpa_m5_cluster_top*.h'))
        for hart in (0, 1):
            instance = re.search(rf'(Vpa_m5_cluster_top_\w+)\s+TOP__pa_m5_cluster_top__DOT__u_core{hart}__DOT__u_ibex;', symbols)
            if not instance: raise ValueError('elaborated hart missing')
            core = (work/(instance[1]+'.h')).read_text()
            for marker in ('gen_mult_fast__DOT__mac_phase_q', 'gen_icache'):
                if marker not in core: raise ValueError(f'hart {hart} missing {marker}')
        if 'gen_multdiv_slow__DOT__' in headers or 'gen_mult_single_cycle__DOT__' in headers:
            raise ValueError('wrong multiplier in compiled model')
    print('STARTUP ICACHE SOURCE PASS both_harts=ICache+RV32MFast pipeline=qualified')


def prepare_export(work, force_block=False):
    if not (work/'M5_STARTUP_ICACHE').is_file(): raise ValueError('explicit startup marker required')
    target = work/WRAPPER
    if target.resolve() != target.absolute() or target.read_bytes() != derived_wrapper():
        raise ValueError('unexpected or escaped fast wrapper')
    target.write_bytes(wrapper())
    if force_block:
        target = work/XILINX_RAM
        if target.resolve() != target.absolute(): raise ValueError('RAM export escapes stage')
        pinned(target, XILINX_RAM_SHA)
        target.write_bytes(block_ram())
        (work/'M5_STARTUP_BLOCK_RAM').touch(exist_ok=False)
    check_export(work)
    (work/'startup_icache_sources.json').write_text(json.dumps(dict(schema=1,
        wrapper_sha256=digest(wrapper()), multiplier_sha256=digest(pipelined_multiplier()),
        instruction_cache_bytes_per_hart=4096, instruction_cache_ways=2,
        clock_mhz=91, dsp_limit=0, force_block_ram=force_block), indent=2)+'\n')


def board_tcl(output, force_block=False):
    pinned(ROOT/'scripts/m5_fast_sources.py',
        'e75dd2a76ef2e4bfb145e0f85845a5c3c894524133122eff0cdc83b2787561c2')
    parent = output.with_name('parent_fast.tcl')
    parent_board_tcl(parent)
    source = parent.read_text().replace('"$root_dir/scripts/m5_fast_sources.py"',
        '"$root_dir/scripts/m5_startup_icache.py"')
    source = once(source, 'puts $fast_fd "dsp_count=0"', '''puts $fast_fd "dsp_count=0"
foreach hart {0 1} {
  set cache_cells [get_cells -hierarchical -quiet -filter "NAME =~ *u_core${hart}*gen_icache*"]
  set cache_rams [get_cells -hierarchical -quiet -filter "NAME =~ *u_core${hart}*gen_rams* && (REF_NAME =~ RAMB18* || REF_NAME =~ RAMB36*)"]
  if {[llength $cache_cells] == 0 || [llength $cache_rams] == 0} {
    error "Missing actual synthesized I-cache logic/BRAM on hart $hart"
  }
  puts $fast_fd "hart=$hart icache_cells=[llength $cache_cells] icache_brams=[llength $cache_rams]"
}''')
    if force_block:
        source = once(source, '  puts $fast_fd "hart=$hart icache_cells=',
            '''  set tag_rams [get_cells -hierarchical -quiet -filter "NAME =~ *u_core${hart}*tag_bank* && (REF_NAME =~ RAMB18* || REF_NAME =~ RAMB36*)"]
  if {[llength $tag_rams] != 2} { error "Expected two block-RAM tag banks on hart $hart" }
  puts $fast_fd "hart=$hart tag_brams=[llength $tag_rams]"
  puts $fast_fd "hart=$hart icache_cells=''')
    with output.open('x') as stream: stream.write(source)


def prepare(work):
    if not work.name.startswith('m5_startup_'):
        raise ValueError('fresh startup directory required')
    target = work/'sim'/WRAPPER
    if target.is_symlink() or target.resolve() != target.absolute():
        raise ValueError('exported wrapper must not escape stage')
    if target.read_bytes() != derived_wrapper(): raise ValueError('unexpected parent fast wrapper')
    target.write_bytes(wrapper())
    multiplier = work/'sim/src/lowrisc_ibex_ibex_core_0.1/rtl/ibex_multdiv_fast.sv'
    pinned(multiplier, digest(pipelined_multiplier()))
    (work/'start.S').write_text(start())
    (work/'icache_derivation.json').write_text(json.dumps(dict(schema=1,
        wrapper_sha256=digest(wrapper()), multiplier_sha256=digest(multiplier.read_bytes()),
        start_sha256=digest((work/'start.S').read_bytes()), clock_change=False,
        scope='simulation hypothesis only; not a qualified physical overlay'), indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('work', type=Path)
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--prepare-export', action='store_true')
    p.add_argument('--emit-board-tcl', action='store_true')
    p.add_argument('--emit-start', action='store_true')
    p.add_argument('--model', action='store_true')
    p.add_argument('--block-ram', action='store_true')
    a = p.parse_args(); work = a.work.resolve()
    if a.prepare: prepare(work)
    elif a.prepare_export: prepare_export(work, a.block_ram)
    elif a.emit_board_tcl: board_tcl(work, a.block_ram)
    elif a.emit_start:
        with work.open('x') as stream: stream.write(required_start())
    else: check_export(work, a.model)
