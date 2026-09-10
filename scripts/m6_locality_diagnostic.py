"""Read-only pin/domain and buffer-location diagnostic using the run's exact SDC.

Reuse the retained all-pin Tcl extraction without changing historical helpers.
Report completion does not qualify timing, electrical limits or the full chip.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from scripts.m6_memory_feasibility import ROOT
from scripts.m6_report_contract_boundary import evaluate_rows


def classify_constant_resets(rows, neighbours, summary):
    """Exclude only structurally proved, non-switching constant reset pins.

    Keep the original raw-domain result. A zero slew alone, an arbitrary tie,
    an external port, or a disconnected PG terminal never supplies a proof.
    """
    by_pin = {}
    for row in neighbours:
        pin = row["macro"].replace("\\[", "[").replace("\\]", "]") + "/" + row["port"]
        by_pin.setdefault(pin, []).append(row)
    constants = []
    for pin, endpoints in by_pin.items():
        if not pin.endswith("/rstb"):
            continue
        if len(endpoints) != 1:
            raise ValueError("reset tie must have exactly one other endpoint")
        driver = endpoints[0]
        if any(driver[key] != value for key, value in {
            "master": "sky130_fd_sc_hd__conb_1", "neighbour_port": "HI",
            "neighbour_direction": "OUTPUT", "external_ports": "0",
            "pg": "VPWR=vdd,VPB=vdd,VGND=vss,VNB=vss",
        }.items()):
            raise ValueError("unproved SRAM reset tie")
        selected = [row for row in rows if row["pin"] == pin]
        if len(selected) != 3 or {row["corner"] for row in selected} != set(summary):
            raise ValueError("missing constant-pin corner coverage")
        for row in selected:
            if row["direction"] != "input" or any(float(row[key]) != 0 for key in
                    ("rise_min_ns", "rise_max_ns", "fall_min_ns", "fall_max_ns")):
                raise ValueError("constant reset unexpectedly has a switching waveform")
        constants.append(pin)
    if len(constants) != 8:
        raise ValueError("eight proved constant SRAM reset pins required")
    for corner in summary.values():
        corner["constant_non_switching_reset_pins"] = sorted(constants)
        corner["dynamic_input_slew_outside_domain"] = [
            pin for pin in corner["input_slew_outside_domain"] if pin not in constants]
    return summary


def collect(stage, run, output):
    stage, output = stage.resolve(), output.resolve()
    if any(p.parent != ROOT/"build" or not p.name.startswith("m6_") for p in (stage, output)) or output.exists():
        raise ValueError("fresh direct M6 output and existing M6 stage required")
    if not re.fullmatch(r"[a-zA-Z0-9_]+", run):
        raise ValueError("one run tag required")
    states = list((stage/"runs"/run).glob("*-openroad-stapostpnr/state_out.json"))
    if len(states) != 1:
        raise ValueError("one completed routed STA result required")
    resolved = stage/"runs"/run/"resolved.json"
    config = json.loads(resolved.read_text())
    state = json.loads(states[0].read_text())
    template = ROOT/"build/m6_contract_boundary_ss_v1/report.tcl"
    source = template.read_text()
    for pattern, replacement in ((r"^read_db .*$", "read_db "+state["odb"]),
            (r"^read_sdc .*$", "read_sdc "+config["SIGNOFF_SDC_FILE"])):
        source, count = re.subn(pattern, lambda _: replacement, source, flags=re.M)
        if count != 1:
            raise ValueError("unexpected retained diagnostic template")
    for corner in config["STA_CORNERS"]:
        key = corner.split("_", 1)[0]+"_*"
        source, count = re.subn(r"^read_spef -corner "+re.escape(corner)+r" .*$",
            lambda _: f"read_spef -corner {corner} {state['spef'][key]}", source, flags=re.M)
        if count != 1:
            raise ValueError("missing corner in retained template")
    source += r'''
foreach corner [sta::corners] {
    report_checks -corner [$corner name] -path_delay max -group_count 100 \
        -slack_max 0.60 -fields {capacitance slew input_pin net} -digits 9 \
        > /diagnostic/critical_[$corner name].rpt
}
set stream [open /diagnostic/neighbours.tsv w]
puts $stream "macro\tport\tnet\tneighbour\tmaster\tx_um\ty_um\tmacro_x_um\tmacro_y_um\tstatus\tneighbour_port\tneighbour_direction\texternal_ports\tpg\torientation\tbbox_xmin_um\tbbox_ymin_um\tbbox_xmax_um\tbbox_ymax_um"
set block [ord::get_db_block]
set units [$block getDbUnitsPerMicron]
foreach macro [$block getInsts] {
    if {[[$macro getMaster] getName] ne "sram22_512x32m4w8"} { continue }
    lassign [$macro getOrigin] mx my
    foreach term [$macro getITerms] {
        if {[[$term getMTerm] getIoType] ni {INPUT OUTPUT}} { continue }
        set net [$term getNet]
        if {$net eq "NULL"} { error "unconnected macro terminal" }
        foreach other [$net getITerms] {
            set inst [$other getInst]
            if {$inst eq $macro} { continue }
            lassign [$inst getOrigin] x y
            # Origin is the transformed placement origin, NOT the lower-left
            # corner for mirrored cells. Retain it for historical comparison
            # and report the actual placed bounding box and orientation.
            set box [$inst getBBox]
            set geometry [list [$inst getOrient]]
            foreach coordinate [list [$box xMin] [$box yMin] [$box xMax] [$box yMax]] {
                lappend geometry [expr {double($coordinate)/$units}]
            }
            set pg {}
            foreach pin {VPWR VPB VGND VNB} {
                set terminal [$inst findITerm $pin]
                set supply MISSING
                if {$terminal ne "NULL" && [$terminal getNet] ne "NULL"} {
                    set supply [[$terminal getNet] getName]
                }
                lappend pg "$pin=$supply"
            }
            puts $stream [join [concat [list [$macro getName] [[$term getMTerm] getName] [$net getName] [$inst getName] [[$inst getMaster] getName] [expr {double($x)/$units}] [expr {double($y)/$units}] [expr {double($mx)/$units}] [expr {double($my)/$units}] [$inst getPlacementStatus] [[$other getMTerm] getName] [[$other getMTerm] getIoType] [llength [$net getBTerms]] [join $pg ,]] $geometry] "\t"]
        }
    }
}
close $stream
'''
    output.mkdir()
    (output/"report.tcl").write_text(source)
    image = json.loads((ROOT/"asic/m6/tools.json").read_text())["container"]
    flow = stage/(run+"_flow")
    if not flow.is_dir():
        flow = ROOT/"asic/m6"
    cmd = ["docker", "run", "--rm", "--network", "none", "--cpus", "2", "--memory", "4g",
           "--user", f"{os.getuid()}:{os.getgid()}"]
    for path, target, ro in ((ROOT/"build/m6_bank_1x_probe_v2", "/work", True),
            (stage, "/candidate", True), (ROOT/"build/m6_pdks", "/pdk", True),
            (flow, "/m6_flow", True), (output, "/diagnostic", False)):
        cmd += ["--mount", f"type=bind,src={path},dst={target}"+(",readonly" if ro else "")]
    cmd += ["--entrypoint", "openroad", image, "-exit", "/diagnostic/report.tcl"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    (output/"run.log").write_text(result.stdout+result.stderr)
    if result.returncode:
        raise ValueError("diagnostic failed; retained run.log")
    with (output/"pins.tsv").open() as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    contract = json.loads((stage/"manifest.json").read_text())["contract"]["envelope"]
    summary = evaluate_rows(rows, contract)
    with (output/"neighbours.tsv").open() as stream:
        neighbours = list(csv.DictReader(stream, delimiter="\t"))
    summary = classify_constant_resets(rows, neighbours, summary)
    value = {"status": "READ_ONLY_LOCALITY_DIAGNOSTIC_NOT_PHYSICAL_PASS", "run": run,
             "period_ns": config["CLOCK_PERIOD"], "corners": summary,
             "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (states[0], resolved, template, Path(__file__).resolve())},
             "artifacts": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in output.iterdir() if p.is_file()}}
    (output/"diagnostic.json").write_text(json.dumps(value, indent=2, sort_keys=True)+"\n")
    print(json.dumps({c: {k: len(v) if isinstance(v,list) else v for k,v in row.items()}
                      for c,row in summary.items()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("run")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    collect(args.stage, args.run, args.output)
