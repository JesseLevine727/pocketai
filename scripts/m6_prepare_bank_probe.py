"""Stage a small, full-periphery 100-MHz banked SRAM experiment, not the chip."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
MACRO = "sram22_512x32m4w8"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--onehot", action="store_true", help="stage the isolated one-hot return experiment")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != ROOT / "build" or not output.name.startswith("m6_") or output.exists():
        parser.error("fresh direct build/m6_* output required")
    output.mkdir()
    adapter = "pa_m6_sram_1x_onehot.sv" if args.onehot else "pa_m6_sram_1x_candidate.sv"
    sources = [ROOT / "asic/m6/rtl" / adapter,
               ROOT / "asic/m6/rtl/pa_m6_bank_probe.sv",
               ROOT / "asic/m6/bank_probe.sdc",
               ROOT / "asic/m6/sram_probe_pdn.tcl"]
    sources += list((ROOT / "build/m6_sram512_v1").glob("*"))
    sources += [ROOT / "build/m6_sram_probe_v4/sram22_512x32m4w8_boundary.gds.gz"]
    for source in sources:
        if source.is_file():
            shutil.copyfile(source, output / source.name)
    config = json.loads((ROOT / "asic/m6/sram_probe.json").read_text())
    config.update(DESIGN_NAME="pa_m6_bank_probe", CLOCK_PORT="clk", CLOCK_PERIOD=10,
                  VERILOG_FILES=["dir::" + adapter, "dir::pa_m6_bank_probe.sv"],
                  FALLBACK_SDC_FILE="dir::bank_probe.sdc", PNR_SDC_FILE="dir::bank_probe.sdc",
                  SIGNOFF_SDC_FILE="dir::bank_probe.sdc", DIE_AREA=[0, 0, 1200, 2200],
                  PRIMARY_GDSII_STREAMOUT_TOOL="klayout", RUN_MAGIC_STREAMOUT=False,
                  RUN_KLAYOUT_XOR=False, MAGIC_LEF_WRITE_USE_GDS=False, MAGIC_DRC_USE_GDS=False,
                  MAGIC_EXT_ABSTRACT_CELLS=[MACRO],
                  PDN_MACRO_CONNECTIONS=[r".*u_sram vdd vss vdd vss"],
                  SYNTH_HIERARCHY_MODE="deferred_flatten")
    config.pop("FP_PDN_MACRO_HOOKS", None)
    config["MACROS"][MACRO]["gds"] = ["dir::sram22_512x32m4w8_boundary.gds.gz"]
    config["MACROS"][MACRO]["instances"] = {
        f"u_memory.g_read[{port}].g_bank[{bank}].g_slice[0].u_sram":
            {"location": [100 + port*550, 100 + bank*500], "orientation": "N"}
        for port in range(2) for bank in range(4)}
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    manifest = {"status": "STAGED_NOT_QUALIFIED", "clock_mhz_target": 100,
                "scope": "2048x32 logical memory, two read copies, write-priority 1x candidate; not full PocketAI",
                "macro_count": 8, "external_inputs_and_outputs_registered": True,
                "bank_return": "onehot" if args.onehot else "binary",
                "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sources if p.is_file()}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("M6 banked memory probe staged: 8 real macros, 100-MHz single clock")


if __name__ == "__main__":
    main()
