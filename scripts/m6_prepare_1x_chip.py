"""Bind the already-tested single-clock assembly to the existing digital loader.

Keep the legacy clk_mem_i port name for harness compatibility, but drive the
system clock directly: no divider, doubled clock or lower-rate compute domain.
Neither staging nor RTL simulation qualifies pads or physical 100-MHz timing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembly", type=Path)
    parser.add_argument("soc", type=Path)
    parser.add_argument("chip", type=Path)
    args = parser.parse_args()
    assembly, soc, chip = (p.resolve() for p in (args.assembly, args.soc, args.chip))
    for path in (assembly, soc, chip):
        if path.parent != ROOT / "build" or not path.name.startswith("m6_"):
            parser.error("direct build/m6_* paths required")
    if soc.exists() or chip.exists() or soc == chip:
        parser.error("fresh distinct output directories required")
    # Restrict this integration to the qualified binary candidate identity.
    records = (assembly / "inputs.sha256").read_text().splitlines()
    adapter = ROOT / "asic/m6/rtl/pa_m6_sram_1x_candidate.sv"
    if not any(line.split()[0] == digest(adapter) and line.split()[1] == str(adapter.relative_to(ROOT))
               for line in records):
        raise ValueError("assembly is not bound to the tested single-clock adapter")
    design = json.loads((assembly / "portable.json").read_text())
    ports = design["modules"]["pa_m6_portable"]["ports"]
    excluded = {"s_axi_aclk", "m6_clk_mem_i", "m6_mem_rst_ni"}
    declarations = ["input wire clk_mem_i", "output wire clk_sys_o"]
    for name, port in ports.items():
        if name not in excluded:
            width = len(port["bits"])
            span = f"[{width-1}:0] " if width > 1 else ""
            declarations.append(f"{port['direction']} wire {span}{name}")
    connections = {name: name for name in ports}
    connections.update(s_axi_aclk="clk_sys_o", m6_clk_mem_i="clk_sys_o", m6_mem_rst_ni="s_axi_aresetn")
    text = "// Single-clock digital boundary; clk_mem_i is the 1x system input.\n"
    text += "module pa_m6_soc(\n  " + ",\n  ".join(declarations) + "\n);\n"
    text += "  assign clk_sys_o = clk_mem_i;\n  pa_m6_portable u_core(\n    "
    text += ",\n    ".join(f".{name}({net})" for name, net in connections.items())
    text += "\n  );\nendmodule\n"
    soc.mkdir()
    (soc / "pa_m6_soc.sv").write_text(text)
    (soc / "portable.v").write_bytes((assembly / "portable.v").read_bytes())
    # The original digital-chip staging helper expects this file. It contains
    # no instantiated divider or logic in this single-clock integration.
    (soc / "pa_m6_clocking.sv").write_text("// Intentionally empty: pa_m6_soc directly binds the 1x clock.\n")
    subprocess.run([sys.executable, str(ROOT / "scripts/m6_prepare_chip.py"), str(soc), str(chip)], check=True)
    harness_source = ROOT / "tests/m6/chip_smoke.cc"
    harness = harness_source.read_text()
    substitutions = {"context.timeInc(10)": "context.timeInc(5000)",
                     "uart_wait=48": "uart_wait=24", "uart_wait=32": "uart_wait=16",
                     "Simulation sim;": 'Simulation sim;\n    check(sim.context.timeprecision()==-12,"expected 1ps simulation precision");',
                     "top.eval(); ++ticks;": 'top.eval(); ++ticks;\n      check(top.clk_sys_o==top.clk_mem_i,"direct 1x clock binding");'}
    for old, new in substitutions.items():
        if harness.count(old) != 1:
            raise ValueError("review changed chip smoke clock/UART sampling before staging")
        harness = harness.replace(old, new)
    (chip / "chip_smoke_1x.cc").write_text(harness)
    manifest = {"status": "STAGED_1X_DIGITAL_CHIP_NOT_PHYSICAL_QUALIFICATION",
                "simulated_clock_period_ns": 10, "system_to_input_clock_ratio": 1,
                "clock_input_legacy_name": "clk_mem_i", "physical_timing_pass": None,
                "harness_changes": substitutions,
                "sources": {str(path.relative_to(ROOT)): digest(path) for path in
                    (Path(__file__).resolve(), ROOT / "scripts/m6_prepare_chip.py", harness_source,
                     assembly / "inputs.sha256", assembly / "portable.v", assembly / "portable.json")},
                "staged": {path.name: digest(path) for path in chip.iterdir() if path.is_file()}}
    (chip / "single_clock_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    print("M6 1X CHIP STAGED: unchanged firmware/oracles; direct clock and matching UART sampling")


if __name__ == "__main__":
    main()
