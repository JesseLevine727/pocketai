"""Compare identical extracted SS timing alone, multi-corner, and unique Lib names.

No implementation is modified. Only library identifiers differ in the third
case; every cell/timing/electrical attribute remains byte-identical.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from scripts.m6_memory_feasibility import ROOT

CORNERS = ("min_ff_n40C_1v95", "nom_tt_025C_1v80", "max_ss_100C_1v60")


def collect(output):
    output = output.resolve()
    if output.parent != ROOT/"build" or not output.name.startswith("m6_") or output.exists():
        raise ValueError("fresh direct M6 output required")
    stage = ROOT/"build/m6_contract_probe_v1"
    state_path = stage/"runs/close_halo_95_v1/44-openroad-stapostpnr/state_out.json"
    state = json.loads(state_path.read_text())
    output.mkdir()
    sources = {str(state_path.relative_to(ROOT)): hashlib.sha256(state_path.read_bytes()).hexdigest()}
    for corner in CORNERS:
        pvt = corner.split("_",1)[1]
        path = stage/f"sram22_512x32m4w8_{pvt}.lib"
        original = path.read_text()
        updated, count = re.subn(r"\Alibrary\s*\(sram22_512x32m4w8\)",
            f"library (sram22_512x32m4w8_{pvt})", original)
        if count != 1:
            raise ValueError("expected exactly one original library header")
        (output/path.name).write_text(updated)
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    image = json.loads((ROOT/"asic/m6/tools.json").read_text())["container"]
    results = {}
    for name, corners, unique in (("ss_alone", CORNERS[-1:], False),
                                 ("all_shared_names", CORNERS, False),
                                 ("all_unique_names", CORNERS, True)):
        commands = ["define_corners "+" ".join(corners)]
        for corner in corners:
            pvt = corner.split("_",1)[1]
            commands += [f"read_liberty -corner {corner} /pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__{pvt}.lib",
                         f"read_liberty -corner {corner} {'/audit' if unique else '/candidate'}/sram22_512x32m4w8_{pvt}.lib"]
        commands += ["read_db "+state["odb"], "read_sdc /m6_flow/bank_probe_95.sdc"]
        for corner in corners:
            commands.append("read_spef -corner "+corner+" "+state["spef"][corner.split("_",1)[0]+"_*"])
        commands += ["set_propagated_clock [all_clocks]", "report_checks -corner max_ss_100C_1v60 -path_delay max -digits 9",
                     "report_checks -corner max_ss_100C_1v60 -path_delay min -digits 9"]
        script = output/(name+".tcl")
        script.write_text("\n".join(commands)+"\n")
        cmd = ["docker", "run", "--rm", "--network", "none", "--cpus", "2", "--memory", "4g",
               "--user", f"{os.getuid()}:{os.getgid()}"]
        for path, target, ro in ((stage,"/candidate",True), (ROOT/"build/m6_pdks","/pdk",True),
                               (ROOT/"asic/m6","/m6_flow",True), (output,"/audit",False)):
            cmd += ["--mount",f"type=bind,src={path},dst={target}"+(",readonly" if ro else "")]
        cmd += ["--entrypoint","openroad",image,"-exit","/audit/"+script.name]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        log = result.stdout+result.stderr
        (output/(name+".log")).write_text(log)
        if result.returncode:
            raise ValueError("retained audit failed: "+name)
        slacks = {"max": [], "min": []}
        for block in log.split("Startpoint:")[1:]:
            kind = re.search(r"^Path Type: (max|min)$", block, re.M)
            value = re.search(r"^\s*(-?[0-9.]+)\s+slack \((?:MET|VIOLATED)\)", block, re.M)
            if kind is None or value is None:
                raise ValueError("missing explicit path type/slack")
            slacks[kind[1]].append(float(value[1]))
        if any(len(values) != 2 for values in slacks.values()):
            raise ValueError("both clock and asynchronous groups required for setup/hold")
        results[name] = {"setup_ns":min(slacks["max"]),"hold_ns":min(slacks["min"]),
                         "duplicate_library_warnings":log.count("STA-1140")}
    sources[str(Path(__file__).resolve().relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    value = {"status":"CORNER_BINDING_DIAGNOSTIC_NOT_PHYSICAL_PASS", "sources":sources,"results":results,
             "artifacts":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output/"binding.json").write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
    print(json.dumps(results,indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    collect(parser.parse_args().output)
