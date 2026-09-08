"""Coherent local instruction mirror; preserve all frozen CPU/router/bus sources."""
import argparse
import json
from pathlib import Path
import sys
import yaml
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.m5_fast_sources import ROOT, WRAPPER, CLUSTER, derived_wrapper, pinned, digest, pipelined_multiplier
from scripts.m5_fast_sources import board_tcl as parent_board_tcl
from scripts.m5_iterate_sources import once
from scripts.check_m5_sources import check as check_lsu

TOP = 'src/pocketai_pa_pa_m5_rtl_0.1/pa_m5_cluster_top.sv'
MEMORY = Path(TOP).parent
ROUTER_SHA = '73e114d4902ed1ef4bce5bf5df108cd3c02caf402e84d7f5de49836419bdbbdb'
SYSTEM_SHA = 'ad235f2ad95ba0de0352e170f3e5f4e7111beda52284ac6a315cbe344bc125e9'


def direct_router(early=False, prefetch=False):
    if early and prefetch: raise ValueError('distinct instruction experiments')
    source = pinned(ROOT/'rtl/m5/pa_m5_obi_router.sv', ROUTER_SHA).decode()
    source = once(source, 'module pa_m5_obi_router (',
                  'module pa_m5_obi_router #(parameter bit DirectResponse = 1\'b0) (')
    source = once(source, 'assign host_gnt_o = state_q == Idle && host_req_i && !stop_i;',
        '''// Only instruction ports opt in. A completed owned response may hand
  // the single request slot directly to a new request at the SAME edge.
  // Stop/abort always prevents new admission, never discards old ownership.
  assign host_gnt_o = (state_q == Idle ||
      (DirectResponse && state_q == WaitResponse && target_rvalid_i[route_q])) &&
      host_req_i && !stop_i;''')
    source = once(source, 'assign host_rvalid_o = state_q == Respond;',
        'assign host_rvalid_o = DirectResponse ? (state_q == WaitResponse && target_rvalid_i[route_q]) : state_q == Respond;')
    source = once(source, 'assign host_rdata_o = response_q;',
        'assign host_rdata_o = DirectResponse ? target_rdata_i[route_q] : response_q;')
    source = once(source, 'assign host_err_o = error_q;',
        'assign host_err_o = DirectResponse ? target_err_i[route_q] : error_q;')
    source = once(source, '        state_q <= Respond;', '''        if (DirectResponse) begin
          if (host_gnt_o) begin
            route_q <= host_addr_i[31:28] == 4'h4;
            addr_q <= host_addr_i; data_q <= host_wdata_i;
            we_q <= host_we_i; be_q <= host_be_i;
            state_q <= Send;
          end else state_q <= Idle;
        end else state_q <= Respond;''')
    source = once(source, 'endmodule', '''`ifndef SYNTHESIS
  logic owned_q;
  always_ff @(posedge clk_i) begin
    if (!rst_ni) owned_q <= 0;
    else begin
      assert (!host_rvalid_o || owned_q);
      assert (!host_gnt_o || !owned_q || host_rvalid_o);
      assert (!host_gnt_o || !stop_i);
      if (host_gnt_o) owned_q <= 1;
      else if (host_rvalid_o) owned_q <= 0;
    end
  end
`endif
endmodule''')
    if early:
        source = once(source, "parameter bit DirectResponse = 1'b0",
                      "parameter bit DirectResponse = 1'b0, parameter bit EarlyLocal = 1'b0")
        source = once(source, '''  assign host_gnt_o = (state_q == Idle ||
      (DirectResponse && state_q == WaitResponse && target_rvalid_i[route_q])) &&
      host_req_i && !stop_i;''', '''  logic can_admit, early_local;
  initial assert (!EarlyLocal || DirectResponse);
  assign can_admit = state_q == Idle ||
      (DirectResponse && state_q == WaitResponse && target_rvalid_i[route_q]);
  // Only a RAM instruction may issue at admission. Its grant means the mirror
  // actually accepted the read, including write-priority backpressure. Other
  // addresses retain the registered Send stage and original owned lifetime.
  assign early_local = EarlyLocal && can_admit && host_addr_i[31:16] == 0;
  assign host_gnt_o = can_admit && host_req_i && !stop_i &&
      (!early_local || target_gnt_i[0]);''')
        source = once(source, "assign target_req_o[0] = state_q == Send && !route_q;",
            "assign target_req_o[0] = (state_q == Send && !route_q) || (early_local && host_req_i && !stop_i);")
        for signal, old, new in (('addr', 'addr_q', 'host_addr_i'), ('we', 'we_q', 'host_we_i'),
                                 ('be', 'be_q', 'host_be_i'), ('wdata', 'data_q', 'host_wdata_i')):
            source = once(source, f'assign target_{signal}_o = {old};',
                          f'assign target_{signal}_o = early_local ? {new} : {old};')
        if source.count('state_q <= Send;') != 2: raise ValueError('ambiguous admission states')
        source = source.replace('state_q <= Send;', 'state_q <= early_local ? WaitResponse : Send;')
    if prefetch:
        source = once(source, "parameter bit DirectResponse = 1'b0",
                      "parameter bit DirectResponse = 1'b0, parameter bit InstantLocal = 1'b0")
        source = source.replace('state_q == WaitResponse && target_rvalid_i[route_q]',
            '(state_q == WaitResponse || (InstantLocal && state_q == Send && !route_q && target_gnt_i[0])) && target_rvalid_i[route_q]')
        source = once(source, '      Send: if (target_gnt_i[route_q]) state_q <= WaitResponse;', '''      Send: if (target_gnt_i[route_q]) begin
        // A coherent lookahead hit returns at local admission. The upstream
        // slot was already owned before Send; misses retain WaitResponse.
        if (InstantLocal && !route_q && target_rvalid_i[0]) begin
          if (host_gnt_o) begin
            route_q <= host_addr_i[31:28] == 4'h4;
            addr_q <= host_addr_i; data_q <= host_wdata_i;
            we_q <= host_we_i; be_q <= host_be_i;
            state_q <= Send;
          end else state_q <= Idle;
        end else state_q <= WaitResponse;
      end''')
        source = once(source, '  logic route_q,',
                      '  initial assert (!InstantLocal || DirectResponse);\n  logic route_q,')
    return source.encode()


def direct_system(early=False, prefetch=False, direct_data=False):
    source = pinned(ROOT/'rtl/m5/pa_m5_memory_system.sv', SYSTEM_SHA).decode()
    parameter = ".DirectResponse(1'b1)" if direct_data else '.DirectResponse(h == 0 || h == 2)'
    if early: parameter += ', .EarlyLocal(h == 0 || h == 2)'
    if prefetch: parameter += ', .InstantLocal(h == 0 || h == 2)'
    return once(source, '    pa_m5_obi_router u_router (',
        '    pa_m5_obi_router #('+parameter+') u_router (').encode()


def cluster(registered_fallback=False, prefetch=False, sync_lookahead=False, data_read_mirror=False, direct_data=False):
    source = pinned(ROOT/'rtl/m5/pa_m5_cluster_top.sv', CLUSTER).decode()
    begin = source.index('  for (genvar h = 0; h < 4; h++) begin : g_local_hosts')
    end = source.index('  pa_m5_memory_system u_memory', begin)
    mirror = (ROOT/('runtime/m5_startup/fetch_prefetch.sv.inc' if prefetch else
                   'runtime/m5_startup/fetch_mirror.sv.inc')).read_text()
    if registered_fallback and not prefetch:
        # RAM instructions never request the shared local bus. Register the
        # rare non-RAM fallback response so its full crossbar/RAM data mux cannot
        # extend the direct BRAM-to-IF path. No false-path exception is added.
        mirror = once(mirror, '      logic selected;', '''      logic selected;
      logic fallback_valid_q, fallback_err_q;
      logic [31:0] fallback_data_q;
      always_ff @(posedge clk_sys or negedge rst_sys_n) begin
        if (!rst_sys_n) begin
          fallback_valid_q <= 0;
          fallback_err_q <= 0;
          fallback_data_q <= 0;
        end else begin
          fallback_valid_q <= host_rvalid[h+1];
          if (host_rvalid[h+1]) begin
            fallback_data_q <= host_rdata[h+1];
            fallback_err_q <= host_err[h+1];
          end
        end
      end''')
        for old, new in (
            ('mirror_valid[Port] || host_rvalid[h+1]', 'mirror_valid[Port] || fallback_valid_q'),
            ('mirror_data[Port] : host_rdata[h+1]', 'mirror_data[Port] : fallback_data_q'),
            ('!mirror_valid[Port] && host_err[h+1]', '!mirror_valid[Port] && fallback_err_q'),
            ('mirror_valid[Port] && host_rvalid[h+1]', 'mirror_valid[Port] && fallback_valid_q')):
            mirror = once(mirror, old, new)
    if sync_lookahead:
        if not prefetch: raise ValueError('sync lookahead requires prefetch')
        old = 'always_ff @(posedge clk_sys or negedge rst_sys_n)'
        if mirror.count(old) != 2: raise ValueError('lookahead reset blocks changed')
        # These controls now feed the BRAM address/enable cone. Like the
        # existing owned routers, reset them synchronously so reset assertion
        # cannot change an active RAM address between clock edges.
        mirror = mirror.replace(old, 'always_ff @(posedge clk_sys)')
        # Bridge the existing asynchronous system reset into this synchronous
        # island. Assertion clears the release synchronizer immediately, but
        # only clocked state drives BRAM addresses/enables. Admission waits for
        # release; requests already owned by the routers simply remain in Send.
        mirror = '''  (* ASYNC_REG = "TRUE" *) logic [1:0] startup_reset_release_q;
  logic startup_fetch_ready_q;
  always_ff @(posedge clk_sys or negedge rst_sys_n) begin
    if (!rst_sys_n) startup_reset_release_q <= 0;
    else startup_reset_release_q <= {startup_reset_release_q[0], 1'b1};
  end
  always_ff @(posedge clk_sys)
    startup_fetch_ready_q <= startup_reset_release_q[1];
''' + mirror.replace('if (!rst_sys_n)', 'if (!startup_reset_release_q[1])')
        # This is only a local speculative read, not another owned transaction.
        # It may harmlessly finish during drain. Do not put asynchronous core
        # reset/cancellation outputs in the BRAM address-selection cone.
        mirror = once(mirror, 'rst_core_n && !memory_abort_i &&',
                      'startup_fetch_ready_q &&')
        for port in range(2):
            mirror = once(mirror, f'assign mirror_gnt[{port}] = mirror_req[{port}] && !mirror_write;',
                          f'assign mirror_gnt[{port}] = mirror_req[{port}] && !mirror_write && startup_fetch_ready_q;')
        mirror = once(mirror, 'assign host_req[h+1] = local_req[h] && !selected;',
                      'assign host_req[h+1] = local_req[h] && !selected && startup_fetch_ready_q;')
    if data_read_mirror:
        if not sync_lookahead: raise ValueError('data mirror needs synchronous reset island')
        mirror += (ROOT/'runtime/m5_startup/data_read_mirror.sv.inc').read_text()
        mirror = once(mirror, '''    end else begin : g_data
      assign host_req[h+1] = local_req[h];
      assign local_gnt[h] = host_gnt[h+1];
      assign local_rvalid[h] = host_rvalid[h+1];
      assign local_rdata[h] = host_rdata[h+1];
      assign local_err[h] = host_err[h+1];''', '''    end else begin : g_data
      localparam int DataPort = h/2;
      logic selected;
      assign selected = local_addr[h][31:16] == 0 && !local_we[h];
      // Every accepted original RAM write updates both copies. Conservatively
      // stall both reads on any write, including a write to another address.
      assign startup_data_gnt[DataPort] = local_req[h] && selected &&
                                         !mirror_write && startup_fetch_ready_q;
      assign host_req[h+1] = local_req[h] && !selected;
      assign local_gnt[h] = selected ? startup_data_gnt[DataPort] : host_gnt[h+1];
      assign local_rvalid[h] = startup_data_valid[DataPort] || host_rvalid[h+1];
      assign local_rdata[h] = startup_data_valid[DataPort] ? startup_data_rdata[DataPort] : host_rdata[h+1];
      assign local_err[h] = !startup_data_valid[DataPort] && host_err[h+1];
      always_ff @(posedge clk_sys) begin
        if (startup_reset_release_q[1]) begin
          assert (!(startup_data_valid[DataPort] && host_rvalid[h+1]));
          assert (!(startup_data_gnt[DataPort] && (mirror_write || local_we[h])));
        end
      end''')
    if direct_data:
        if not data_read_mirror: raise ValueError('direct data response requires the dedicated read mirror')
        mirror = once(mirror, '      localparam int DataPort = h/2;', '''      localparam int DataPort = h/2;
      logic data_fallback_valid_q, data_fallback_err_q;
      logic [31:0] data_fallback_q;
      // Preserve the old effective response latency for shared-bus writes and
      // peripherals, and keep its wide shared-RAM mux out of the fast LSU path.
      always_ff @(posedge clk_sys) begin
        if (!startup_reset_release_q[1]) begin
          data_fallback_valid_q <= 0; data_fallback_err_q <= 0; data_fallback_q <= 0;
        end else begin
          data_fallback_valid_q <= host_rvalid[h+1];
          if (host_rvalid[h+1]) begin
            data_fallback_q <= host_rdata[h+1]; data_fallback_err_q <= host_err[h+1];
          end
        end
      end''')
        for old, new in (
            ('startup_data_valid[DataPort] || host_rvalid[h+1]', 'startup_data_valid[DataPort] || data_fallback_valid_q'),
            ('startup_data_rdata[DataPort] : host_rdata[h+1]', 'startup_data_rdata[DataPort] : data_fallback_q'),
            ('!startup_data_valid[DataPort] && host_err[h+1]', '!startup_data_valid[DataPort] && data_fallback_err_q'),
            ('startup_data_valid[DataPort] && host_rvalid[h+1]', 'startup_data_valid[DataPort] && data_fallback_valid_q')):
            mirror = once(mirror, old, new)
    return (source[:begin]+mirror+'\n'+source[end:]).encode()


def check(work):
    check_lsu(work)
    files = yaml.safe_load(next(work.glob('*.eda.yml')).read_text())['files']
    registered_fallback = (work/'M5_STARTUP_REGISTERED_FALLBACK').exists()
    prefetch = (work/'M5_STARTUP_PREFETCH').exists()
    sync_lookahead = (work/'M5_STARTUP_SYNC_LOOKAHEAD').exists()
    data_read_mirror = (work/'M5_STARTUP_DATA_READ_MIRROR').exists()
    direct_data = (work/'M5_STARTUP_DIRECT_DATA').exists()
    required = {WRAPPER: digest(derived_wrapper()), TOP: digest(cluster(registered_fallback, prefetch, sync_lookahead, data_read_mirror, direct_data)),
        'src/lowrisc_ibex_ibex_core_0.1/rtl/ibex_multdiv_fast.sv': digest(pipelined_multiplier())}
    for relative, expected in required.items():
        path = work/relative
        if path.resolve() != path.absolute(): raise ValueError('export escapes work')
        pinned(path, expected)
        matches = [f for f in files if Path(f['name']).name == path.name]
        if len(matches) != 1 or work/matches[0]['name'] != path:
            raise ValueError('wrong compiled source '+relative)
    direct = (work/'M5_STARTUP_DIRECT_RETURN').exists()
    early = (work/'M5_STARTUP_EARLY_LOCAL').exists()
    if early and not direct: raise ValueError('early local requires direct response')
    for name, expected in (('pa_m5_obi_router.sv', digest(direct_router(early, prefetch)) if direct else ROUTER_SHA),
                           ('pa_m5_memory_system.sv', digest(direct_system(early, prefetch, direct_data)) if direct else SYSTEM_SHA)):
        path = work/Path(TOP).parent/name
        pinned(path, expected)
    print('STARTUP FETCH MIRROR SOURCE PASS both_harts=qualified-fast no-icache direct_instruction_return='+
          str(direct)+' registered_fallback='+str(registered_fallback)+' early_local='+str(early)+' prefetch='+str(prefetch)+' sync_lookahead='+str(sync_lookahead)+' data_read_mirror='+str(data_read_mirror)+' direct_data='+str(direct_data))


def prepare(work, direct=False, registered_fallback=False, early=False, prefetch=False, sync_lookahead=False, data_read_mirror=False, direct_data=False):
    if not (work/'M5_STARTUP_FETCH').exists(): raise ValueError('explicit fetch experiment marker required')
    if early and not direct: raise ValueError('early local requires direct response')
    if prefetch and (early or not direct or not registered_fallback): raise ValueError('invalid prefetch configuration')
    if sync_lookahead and not prefetch: raise ValueError('sync lookahead requires prefetch')
    target = work/TOP
    if target.resolve() != target.absolute(): raise ValueError('cluster export escapes work')
    pinned(target, CLUSTER)
    target.write_bytes(cluster(registered_fallback, prefetch, sync_lookahead, data_read_mirror, direct_data))
    if registered_fallback:
        (work/'M5_STARTUP_REGISTERED_FALLBACK').touch(exist_ok=False)
    if direct:
        for name, old, new in (('pa_m5_obi_router.sv', ROUTER_SHA, direct_router(early, prefetch)),
                                ('pa_m5_memory_system.sv', SYSTEM_SHA, direct_system(early, prefetch, direct_data))):
            target = work/MEMORY/name
            if target.resolve() != target.absolute(): raise ValueError('router escapes work')
            pinned(target, old); target.write_bytes(new)
        (work/'M5_STARTUP_DIRECT_RETURN').touch(exist_ok=False)
    if early: (work/'M5_STARTUP_EARLY_LOCAL').touch(exist_ok=False)
    if prefetch: (work/'M5_STARTUP_PREFETCH').touch(exist_ok=False)
    if sync_lookahead: (work/'M5_STARTUP_SYNC_LOOKAHEAD').touch(exist_ok=False)
    if data_read_mirror: (work/'M5_STARTUP_DATA_READ_MIRROR').touch(exist_ok=False)
    if direct_data: (work/'M5_STARTUP_DIRECT_DATA').touch(exist_ok=False)
    check(work)
    (work/'startup_fetch_sources.json').write_text(json.dumps(dict(schema=1,
        cluster_sha256=digest(cluster(registered_fallback, prefetch, sync_lookahead, data_read_mirror, direct_data)), wrapper_sha256=digest(derived_wrapper()),
        extra_instruction_bram_bytes=65536, clock_mhz=91, cache_enabled=False,
        direct_instruction_return=direct, registered_fallback=registered_fallback,
        early_local=early, sequential_prefetch=prefetch, sync_lookahead=sync_lookahead,
        data_read_mirror=data_read_mirror, direct_data_response=direct_data,
        extra_data_bram_bytes=65536 if data_read_mirror else 0), indent=2)+'\n')


def board_tcl(output):
    parent = output.with_name('parent_fast.tcl')
    parent_board_tcl(parent)
    source = parent.read_text().replace('"$root_dir/scripts/m5_fast_sources.py"',
                                        '"$root_dir/scripts/m5_startup_fetch.py"')
    source = once(source, 'puts $fast_fd "dsp_count=0"', '''puts $fast_fd "dsp_count=0"
set fetch36 [get_cells -hierarchical -quiet -filter {NAME =~ *startup_instruction_mem* && REF_NAME =~ RAMB36*}]
set fetch18 [get_cells -hierarchical -quiet -filter {NAME =~ *startup_instruction_mem* && REF_NAME =~ RAMB18*}]
if {[llength $fetch36]*2+[llength $fetch18] != 32} { error "Expected one 64-KiB instruction mirror in block RAM" }
puts $fast_fd "fetch_mirror_bytes=65536 bram36=[llength $fetch36] bram18=[llength $fetch18]"
set data36 [get_cells -hierarchical -quiet -filter {NAME =~ *startup_data_read_mem* && REF_NAME =~ RAMB36*}]
set data18 [get_cells -hierarchical -quiet -filter {NAME =~ *startup_data_read_mem* && REF_NAME =~ RAMB18*}]
set data_expected [file exists "[file dirname $::env(M5_SOURCE_TCL)]/M5_STARTUP_DATA_READ_MIRROR"]
if {[llength $data36]*2+[llength $data18] != 32*$data_expected} { error "Unexpected local data-read mirror resource count" }
puts $fast_fd "data_read_mirror_bytes=[expr {65536*$data_expected}] bram36=[llength $data36] bram18=[llength $data18]"
if {[llength [get_cells -hierarchical -quiet -filter {NAME =~ *gen_icache*}]] != 0} {
  error "Instruction mirror candidate must retain qualified non-cache CPU"
}''')
    with output.open('x') as stream: stream.write(source)


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('work', type=Path)
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--emit-board-tcl', action='store_true')
    p.add_argument('--direct-return', action='store_true')
    p.add_argument('--registered-fallback', action='store_true')
    p.add_argument('--early-local', action='store_true')
    p.add_argument('--prefetch', action='store_true')
    p.add_argument('--sync-lookahead', action='store_true')
    p.add_argument('--data-read-mirror', action='store_true')
    p.add_argument('--direct-data', action='store_true')
    a = p.parse_args()
    if a.emit_board_tcl: board_tcl(a.work.resolve())
    elif a.prepare: prepare(a.work.resolve(), a.direct_return, a.registered_fallback, a.early_local, a.prefetch, a.sync_lookahead, a.data_read_mirror, a.direct_data)
    else: check(a.work.resolve())
