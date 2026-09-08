"""Extract every SRAM pin's slew/load at all declared routed corners.

Read-only OpenSTA diagnostic. Reporting completed is not a passing envelope.
No timing exceptions or library limits are changed by this script.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from scripts.m6_memory_feasibility import ROOT

CORNERS = ("min_ff_n40C_1v95", "nom_tt_025C_1v80", "max_ss_100C_1v60")


def evaluate_rows(rows, contract):
    if len(rows) != 3*8*81 or len({(r["corner"], r["pin"]) for r in rows}) != len(rows):
        raise ValueError("1944 unique SRAM pin/corner rows required")
    summary = {}
    slew_keys = ("rise_min_ns", "rise_max_ns", "fall_min_ns", "fall_max_ns")
    for row in rows:
        if any(not math.isfinite(float(row[k])) or float(row[k]) < 0 for k in (*slew_keys, "load_min_pf", "load_max_pf")):
            raise ValueError("missing, negative or non-finite pin measurements")
    for corner in CORNERS:
        selected = [r for r in rows if r["corner"] == corner]
        inputs = [r for r in selected if r["direction"] == "input"]
        outputs = [r for r in selected if r["direction"] == "output"]
        if len(inputs) != 392 or len(outputs) != 256:
            raise ValueError("complete input/output coverage required at every corner")
        input_bad = [r["pin"] for r in inputs if any(not contract["input_slew_min_ns"] <= float(r[k]) <= contract["input_slew_max_ns"] for k in slew_keys)]
        output_bad = [r["pin"] for r in outputs if not (contract["output_load_min_pf"] <= float(r["load_min_pf"]) and float(r["load_max_pf"]) <= contract["output_load_max_pf"])]
        output_slew_bad = [r["pin"] for r in outputs if any(float(r[k]) > contract["design_transition_limit_ns"] for k in slew_keys)]
        summary[corner] = {"inputs": len(inputs), "outputs": len(outputs),
            "input_slew_outside_domain": input_bad, "output_load_outside_domain": output_bad,
            "output_slew_violations": output_slew_bad,
            "output_load_min_pf": min(float(r["load_min_pf"]) for r in outputs),
            "output_load_max_pf": max(float(r["load_max_pf"]) for r in outputs),
            "maximum_output_transition_ns": max(float(r[k]) for r in outputs for k in slew_keys)}
    return summary


def collect(stage, run, output):
    stage, output = stage.resolve(), output.resolve()
    if any(p.parent != ROOT/"build" or not p.name.startswith("m6_") for p in (stage, output)) or output.exists():
        raise ValueError("direct M6 directories and a fresh output required")
    if not re.fullmatch(r"[a-zA-Z0-9_]+", run):
        raise ValueError("one run tag required")
    states = list((stage/"runs"/run).glob("*-openroad-stapostpnr/state_out.json"))
    if len(states) != 1:
        raise ValueError("one completed post-route STA state required")
    state = json.loads(states[0].read_text())
    output.mkdir()
    commands = ["define_corners " + " ".join(CORNERS)]
    for corner in CORNERS:
        pvt = corner.split("_", 1)[1]
        commands += [f"read_liberty -corner {corner} /pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__{pvt}.lib",
                     f"read_liberty -corner {corner} /candidate/sram22_512x32m4w8_{pvt}.lib"]
    commands += [f"read_db {state['odb']}", "read_sdc /work/bank_probe.sdc"]
    for corner in CORNERS:
        key = corner.split("_",1)[0]+"_*"
        commands.append(f"read_spef -corner {corner} {state['spef'][key]}")
    commands += ["set_propagated_clock [all_clocks]", "report_checks -path_delay max",
                 r'''set macros [get_cells -hierarchical -filter {ref_name == sram22_512x32m4w8}]
if {[llength $macros] != 8} { error "expected 8 SRAMs" }
set stream [open /diagnostic/pins.tsv w]
puts $stream "corner\tpin\tdirection\trise_min_ns\trise_max_ns\tfall_min_ns\tfall_max_ns\tload_min_pf\tload_max_pf"
foreach corner_name {min_ff_n40C_1v95 nom_tt_025C_1v80 max_ss_100C_1v60} {
    set corner [sta::find_corner $corner_name]
    foreach macro $macros {
        foreach pin [get_pins -of_objects $macro] {
            set direction [sta::pin_direction $pin]
            if {$direction ni {input output}} { continue }
            set vertices [$pin vertices]
            if {[llength $vertices] != 1} { error "unexpected SRAM pin vertices" }
            set vertex [lindex $vertices 0]
            set row [list $corner_name [get_full_name $pin] $direction]
            foreach edge {rise fall} {
                foreach check {min max} {
                    lappend row [expr {[$vertex slew_corner $edge $corner $check]*1e9}]
                }
            }
            set net [$pin net]
            foreach check {min max} { lappend row [expr {[$net capacitance $corner $check]*1e12}] }
            puts $stream [join $row "\t"]
        }
    }
}
close $stream
puts "M6 SRAM PIN REPORT COMPLETE; envelope acceptance is checked separately"
''']
    tcl = output/"report.tcl"
    tcl.write_text("\n".join(commands)+"\n")
    image = json.loads((ROOT/"asic/m6/tools.json").read_text())["container"]
    cmd = ["docker", "run", "--rm", "--network", "none", "--cpus", "2", "--memory", "4g"]
    import os
    cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
    for source, destination, ro in ((ROOT/"build/m6_bank_1x_probe_v2", "/work", True),
            (stage, "/candidate", True), (ROOT/"build/m6_pdks", "/pdk", True), (output, "/diagnostic", False)):
        cmd += ["--mount", f"type=bind,src={source},dst={destination}" + (",readonly" if ro else "")]
    cmd += ["--entrypoint", "openroad", image, "-exit", "/diagnostic/report.tcl"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    (output/"run.log").write_text(result.stdout)
    if result.returncode:
        raise ValueError("pin report failed; inspect retained run.log")
    import csv
    rows = list(csv.DictReader((output/"pins.tsv").open(), delimiter="\t"))
    contract = json.loads((stage/"manifest.json").read_text())["contract"]["envelope"]
    summary = evaluate_rows(rows, contract)
    value = {"status": "ROUTED_BOUNDARY_REPORT_NOT_FULL_TIMING_PASS", "source_state": str(states[0].relative_to(ROOT)),
             "envelope_pass": all(not r["input_slew_outside_domain"] and not r["output_load_outside_domain"] and not r["output_slew_violations"] for r in summary.values()),
             "corners": summary, "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (states[0], stage/"manifest.json", Path(__file__).resolve())},
             "artifacts": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output/"boundary.json").write_text(json.dumps(value, indent=2, sort_keys=True)+"\n")
    print(value["status"], "envelope_pass=", value["envelope_pass"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("run")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    collect(args.stage, args.run, args.output)
