"""Stage a bounded full-core physical trial; do not qualify a pad-level chip.

The only additional logic is the tested falling-edge clock divider. Native
AXI remains the explicit external-memory boundary in this intermediate run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
MACRO = "sram22_512x32m4w8"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(assembly, output):
    assembly, output = Path(assembly), Path(output)
    assert assembly.parent == output.parent == ROOT / "build"
    assert assembly.name.startswith("m6_") and output.name.startswith("m6_")
    assert not output.exists()
    design = json.loads((assembly / "portable.json").read_text())
    ports = design["modules"]["pa_m6_portable"]["ports"]
    excluded = {"s_axi_aclk", "m6_clk_mem_i", "m6_mem_rst_ni"}
    decls = ["input wire clk_mem_i", "output wire clk_sys_o"]
    for name, port in ports.items():
        if name in excluded:
            continue
        width = len(port["bits"])
        span = f"[{width-1}:0] " if width > 1 else ""
        decls.append(f"{port['direction']} wire {span}{name}")
    connections = {name: name for name in ports}
    connections.update(s_axi_aclk="clk_sys_o", m6_clk_mem_i="clk_mem_i",
                       m6_mem_rst_ni="s_axi_aresetn")
    rtl = "// Full native-AXI core boundary; this is not the pad-level chip.\n"
    rtl += "module pa_m6_soc(\n  " + ",\n  ".join(decls) + "\n);\n"
    rtl += "  pa_m6_clocking u_clock(.clk_mem_i(clk_mem_i), .rst_ni(s_axi_aresetn), .clk_sys_o(clk_sys_o));\n"
    rtl += "  pa_m6_portable u_core(\n    "
    rtl += ",\n    ".join(f".{name}({net})" for name, net in connections.items())
    rtl += "\n  );\nendmodule\n"

    macros = []
    def walk(module, path):
        for name, cell in sorted(design["modules"][module].get("cells", {}).items()):
            child = f"{path}.{name}"
            if cell["type"] == MACRO:
                macros.append(child)
            elif cell["type"] in design["modules"]:
                walk(cell["type"], child)
    walk("pa_m6_portable", "u_core")
    assert len(macros) == 292, len(macros)
    config = json.loads((ROOT / "asic/m6/sram_probe.json").read_text())
    config.update(DESIGN_NAME="pa_m6_soc",
        VERILOG_FILES=["dir::portable.v", "dir::pa_m6_clocking.sv", "dir::pa_m6_soc.sv"],
        CLOCK_PORT="clk_mem_i", CLOCK_PERIOD=40,
        FALLBACK_SDC_FILE="dir::soc.sdc", PNR_SDC_FILE="dir::soc.sdc", SIGNOFF_SDC_FILE="dir::soc.sdc",
        SYNTH_HIERARCHY_MODE="deferred_flatten",
        DIE_AREA=[0, 0, 9100, 9900], FP_CORE_UTIL=35, PL_TARGET_DENSITY_PCT=45,
        PDN_MACRO_CONNECTIONS=[r".*u_sram vdd vss vdd vss"],
        FP_PDN_CFG="dir::sram_probe_pdn.tcl",
        PRIMARY_GDSII_STREAMOUT_TOOL="klayout", RUN_MAGIC_STREAMOUT=False,
        RUN_KLAYOUT_XOR=False, MAGIC_LEF_WRITE_USE_GDS=False,
        MAGIC_DRC_USE_GDS=False,
        MAGIC_EXT_ABSTRACT_CELLS=[MACRO])
    config.pop("FP_PDN_MACRO_HOOKS", None)
    config["MACROS"][MACRO]["gds"] = ["dir::sram22_512x32m4w8_boundary.gds.gz"]
    config["MACROS"][MACRO]["instances"] = {
        name: {"location": [180+(index % 17)*520, 180+(index // 17)*530], "orientation": "N"}
        for index, name in enumerate(macros)}
    output.mkdir()
    (output / "pa_m6_soc.sv").write_text(rtl)
    (output / "config.json").write_text(json.dumps(config, indent=2)+"\n")
    for source in [assembly / "portable.v", ROOT / "asic/m6/rtl/pa_m6_clocking.sv",
                   ROOT / "asic/m6/soc.sdc", ROOT / "asic/m6/sram_probe_pdn.tcl",
                   ROOT / "asic/m6/clock_data_boundaries.tcl"]:
        shutil.copyfile(source, output / source.name)
    # Yosys writes the intentional lowRISC latch as always @*. Re-express
    # only that exact process as always_latch so lint still rejects any
    # accidental latch elsewhere. The transparent-low gate is unchanged.
    portable = (output / "portable.v").read_text()
    latch = "  always @*\n    if (!clk_i) en_latch = _0_;"
    assert portable.count(latch) == 1
    (output / "portable.v").write_text(portable.replace(latch,
        "  always_latch\n    if (!clk_i) en_latch = _0_;"))
    # Retain original macro views; boundary metadata was verified separately.
    for source in (ROOT / "build/m6_sram512_v1").iterdir():
        if source.is_file():
            shutil.copyfile(source, output / source.name)
    boundary = ROOT / "build/m6_sram_probe_v4/sram22_512x32m4w8_boundary.gds.gz"
    shutil.copyfile(boundary, output / boundary.name)
    manifest = dict(status="STAGED_INTERMEDIATE_CORE_NOT_CHIP_QUALIFICATION",
        system_clock_mhz=12.5, memory_clock_mhz=25,
        external_memory="native AXI; off-chip controller/PHY and 266289152-byte arena excluded",
        pad_status="not included in this intermediate core trial",
        syntax_changes=["qualified prim_clock_gating process: always @* to always_latch; identical latch semantics"],
        macros=len(macros), macro_instances=macros,
        sram_internal_verification="USER_DEFERRED_RESEARCH_ONLY",
        sources={str(p.relative_to(ROOT)): sha(p) for p in
            [assembly / "portable.v", assembly / "portable.json", boundary,
             ROOT / "scripts/m6_prepare_physical.py", ROOT / "asic/m6/soc.sdc",
             ROOT / "asic/m6/rtl/pa_m6_clocking.sv"]},
        staged={p.name: sha(p) for p in output.iterdir() if p.is_file()})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps({"output": str(output), "macros": len(macros), "status": manifest["status"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembly", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.assembly.resolve(), args.output.resolve())
