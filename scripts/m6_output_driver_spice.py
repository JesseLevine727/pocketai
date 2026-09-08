"""Bounded transistor sanity check of the supplied SRAM output inverter only.

This is NOT SRAM recharacterization: no bitcell, clock-to-output, extracted
macro parasitics or internal sense-amplifier behavior is qualified here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from scripts.m6_memory_feasibility import ROOT


def collect(output):
    output = output.resolve()
    if output.parent != ROOT/"build" or not output.name.startswith("m6_") or output.exists():
        raise ValueError("fresh direct build/m6_* output required")
    source = ROOT/"build/m6_sram512_v1/sram22_512x32m4w8.spice"
    text = source.read_text()
    definitions = []
    for name in ("mos_w1000_l150_m1_nf1_id1", "mos_w600_l150_m1_nf1_id0", "folded_inv_9"):
        match = re.search(r"^\.SUBCKT " + name + r"\b.*?^\.ENDS " + name + r"\s*$", text, re.M|re.S)
        if match is None:
            raise ValueError(f"missing original output-driver definition {name}")
        definitions.append(match[0])
    executable = ROOT/"build/m6_ngspice_v1/root/usr/bin/ngspice"
    models = ROOT/"build/m6_pdks/sky130A/libs.tech/ngspice/sky130.lib.spice"
    output.mkdir()
    (output/"output_driver.spice").write_text("\n\n".join(definitions)+"\n")
    # Bind the model trees, not just the top-level .lib include file. The broad
    # fingerprint includes unused corners too; it does not claim they ran.
    model_paths = sorted(set((ROOT/"build/m6_pdks/sky130A/libs.tech/ngspice").rglob("*.spice")) |
                         set((ROOT/"build/m6_pdks/sky130A/libs.ref/sky130_fd_pr/spice").rglob("*.spice")))
    model_list = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT)}\n" for p in model_paths)
    (output/"model_sources.sha256").write_text(model_list)
    version = subprocess.run([str(executable), "--version"], capture_output=True, text=True, check=True)
    (output/"ngspice_version.txt").write_text(version.stdout)
    report = {"status": "OUTPUT_INVERTER_SCHEMATIC_SANITY_ONLY_NOT_MACRO_CHARACTERIZATION",
              "scope": "Original folded_inv_9 transistor topology, ideal internal input, lumped output load",
              "extracted_macro_parasitics": False, "full_sram_pass": False, "results": [],
              "model_tree_files_fingerprinted": len(model_paths),
              "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (source, executable, models, Path(__file__).resolve())}}
    for corner, temperature, voltage in (("ss",100,1.60),("tt",25,1.80),("ff",-40,1.95)):
        for slew in (0.002, 0.351):
            for load in (0.007, 0.013):
                name = f"{corner}_s{slew:g}_c{load:g}"
                deck = f"""* Isolated supplied output inverter, not complete SRAM
.lib {models} {corner}
.include output_driver.spice
.option scale=1e-6
.temp {temperature}
VDD vdd 0 {voltage}
VIN in 0 PULSE(0 {voltage} 1n {slew/0.8:g}n {slew/0.8:g}n 3n 8n)
XOUT vdd 0 in out folded_inv_9
CLOAD out 0 {load:g}p
.tran 1p 12n
.meas tran fall_s TRIG v(out) VAL={0.9*voltage:g} FALL=1 TARG v(out) VAL={0.1*voltage:g} FALL=1
.meas tran rise_s TRIG v(out) VAL={0.1*voltage:g} RISE=1 TARG v(out) VAL={0.9*voltage:g} RISE=1
.end
"""
                path = output/(name+".spice")
                path.write_text(deck)
                run = subprocess.run([str(executable), "-b", str(path)], cwd=output,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
                (output/(name+".log")).write_text(run.stdout)
                if run.returncode != 0:
                    raise ValueError(f"SPICE failed; retained {name}.log")
                values = {}
                for edge in ("rise", "fall"):
                    match = re.search(r"^"+edge+r"_s\s*=\s*([0-9.eE+-]+)", run.stdout, re.M)
                    if match is None:
                        raise ValueError(f"missing transition measurement {name}/{edge}")
                    values[edge+"_transition_ns"] = float(match[1])*1e9
                report["results"].append({"corner": corner, "voltage_v": voltage,
                    "temperature_c": temperature, "ideal_internal_input_slew_ns": slew,
                    "output_load_pf": load, **values})
    report["artifacts"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    (output/"sanity.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(report["status"])
    print("12 finite SPICE cases completed; no complete-memory timing claim")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    collect(parser.parse_args().output)
