"""Stage the single-clock 1x full-core physical trial; not pad/chip qualification.

clk_mem_i is bound directly to both the system and SRAM clocks (no divider).
Native AXI remains the explicit external-memory boundary. This stages the
complete 292-macro system for placement, CTS, routing and extraction.
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
    connections.update(s_axi_aclk="clk_sys_o", m6_clk_mem_i="clk_sys_o",
                       m6_mem_rst_ni="s_axi_aresetn")
    rtl = "// Single-clock digital boundary; clk_mem_i is the 1x system input.\n"
    rtl += "module pa_m6_soc(\n  " + ",\n  ".join(decls) + "\n);\n"
    rtl += "  assign clk_sys_o = clk_mem_i;\n  pa_m6_portable u_core(\n    "
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
        CLOCK_PORT="clk_mem_i", CLOCK_PERIOD=10.526315789474,
        FALLBACK_SDC_FILE="dir::soc_1x.sdc", PNR_SDC_FILE="dir::soc_1x.sdc",
        SIGNOFF_SDC_FILE="dir::soc_1x.sdc",
        SYNTH_HIERARCHY_MODE="deferred_flatten",
        DIE_AREA=[0, 0, 13000, 14000], FP_CORE_UTIL=30, PL_TARGET_DENSITY_PCT=25,
        # Timing-driven global placement diverges on this 292-macro design
        # (RePlAce GPL-0305); a lower target density removes the routing
        # congestion that a denser, timing-driven placement produced.
        PL_TIME_DRIVEN=False,
        PDN_MACRO_CONNECTIONS=[r".*u_sram vdd vss vdd vss"],
        FP_PDN_CFG="dir::sram_probe_pdn.tcl",
        PRIMARY_GDSII_STREAMOUT_TOOL="klayout", RUN_MAGIC_STREAMOUT=False,
        RUN_KLAYOUT_XOR=False, MAGIC_LEF_WRITE_USE_GDS=False,
        MAGIC_DRC_USE_GDS=False,
        MAGIC_EXT_ABSTRACT_CELLS=[MACRO])
    config.pop("FP_PDN_MACRO_HOOKS", None)
    config["MACROS"][MACRO]["gds"] = ["dir::sram22_512x32m4w8_boundary.gds.gz"]
    x_start = int((13000 - 17 * 620) / 2)
    y_start = int((14000 - 18 * 620) / 2)
    config["MACROS"][MACRO]["instances"] = {
        name: {"location": [x_start + (index % 17) * 620,
                            y_start + (index // 17) * 620],
               "orientation": "N"}
        for index, name in enumerate(macros)}
    output.mkdir()
    (output / "pa_m6_soc.sv").write_text(rtl)
    (output / "pa_m6_clocking.sv").write_text(
        "// Intentionally empty: pa_m6_soc directly binds the 1x clock.\n")
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    for source in [assembly / "portable.v", ROOT / "asic/m6/soc_1x.sdc",
                   ROOT / "asic/m6/sram_probe_pdn.tcl"]:
        shutil.copyfile(source, output / source.name)
    # Re-express the intentional lowRISC latch so lint still rejects any other
    # accidental latch; the transparent-low gate semantics are unchanged.
    portable = (output / "portable.v").read_text()
    latch = "  always @*\n    if (!clk_i) en_latch = _0_;"
    if portable.count(latch) == 1:
        (output / "portable.v").write_text(portable.replace(
            latch, "  always_latch\n    if (!clk_i) en_latch = _0_;"))
    for source in (ROOT / "build/m6_sram512_v1").iterdir():
        if source.is_file():
            shutil.copyfile(source, output / source.name)
    boundary = ROOT / "build/m6_sram_probe_v4/sram22_512x32m4w8_boundary.gds.gz"
    shutil.copyfile(boundary, output / boundary.name)
    manifest = dict(status="STAGED_SINGLE_CLOCK_CORE_NOT_CHIP_QUALIFICATION",
        system_clock_mhz=95, memory_clock_mhz=95,
        external_memory="native AXI; off-chip controller/PHY and arena excluded",
        pad_status="not included in this intermediate core trial",
        macros=len(macros), macro_instances=macros,
        sram_internal_verification="USER_DEFERRED_RESEARCH_ONLY",
        sources={str(p.relative_to(ROOT)): sha(p) for p in
            [assembly / "portable.v", assembly / "portable.json", boundary,
             ROOT / "scripts/m6_prepare_physical_1x.py", ROOT / "asic/m6/soc_1x.sdc"]},
        staged={p.name: sha(p) for p in output.iterdir() if p.is_file()})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(output), "macros": len(macros),
                      "status": manifest["status"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembly", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.assembly.resolve(), args.output.resolve())
