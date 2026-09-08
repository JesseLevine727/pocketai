"""Stage hash-bound qualified RTL for ASIC feasibility without changing M5.

This is a source/elaboration stage, not a SRAM-mapped ASIC implementation.
The board wrapper exposes the matched portable core boundary (not chip pads).
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--generic-clock-gate", action="store_true",
                        help="bind the frozen simulation's lowRISC generic clock gate")
    parser.add_argument("--portable-syntax", action="store_true",
                        help="spell the packed zero I-cache configuration with replication")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != ROOT / "build" or not output.name.startswith("m6_"):
        parser.error("output must be a new build/m6_* directory")
    if output.exists():
        parser.error("output exists; retain it and choose a new trial name")
    evidence_path = ROOT / "docs/m5_startup_evidence.json"
    evidence = json.loads(evidence_path.read_text())
    assert evidence["status"] == "PASS"
    baseline = ROOT / evidence["selection"]["synthesis"] / "resolved_sources"
    listing = baseline / "pocketai_sources.tcl"
    text = listing.read_text()
    groups = {}
    for name, body in re.findall(r"set (pocketai_\w+) \[list (.*?)\n\]", text, re.S):
        groups[name] = [Path(x) for x in re.findall(r"\{([^{}]+)\}", body)]
    required = {"pocketai_rtl_files", "pocketai_verilog_files", "pocketai_include_files",
                "pocketai_include_dirs", "pocketai_memory_files"}
    assert set(groups) == required, "unexpected qualified source-list format"
    paths = [listing] + [p for k, values in groups.items() if k != "pocketai_include_dirs"
                          for p in values]
    records = {}
    for path in paths:
        key = str(path.relative_to(ROOT))
        assert digest(path) == evidence["artifacts"][key], key
        records[str(path.relative_to(baseline))] = {"source": key, "sha256": digest(path)}
    output.mkdir()
    for relative, record in records.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / record["source"], target)
    bindings = {}
    if args.generic_clock_gate:
        original = next(p for p in groups["pocketai_rtl_files"] if p.name == "prim_clock_gating.sv")
        candidates = list((ROOT / evidence["selection"]["model"] / "sim/src").glob(
            "lowrisc_prim_generic_clock_gating_*/rtl/prim_clock_gating.sv"))
        assert len(candidates) == 1, "qualified simulation clock-gate source missing"
        generic = candidates[0]
        key = str(generic.relative_to(ROOT))
        assert digest(generic) == evidence["artifacts"][key]
        target = output / original.relative_to(baseline)
        shutil.copyfile(generic, target)
        bindings[str(original.relative_to(baseline))] = {
            "source": key, "sha256": digest(generic),
            "reason": "Replace FPGA BUFGCE binding with qualified generic latch-based gate"}
    syntax_changes = {}
    if args.portable_syntax:
        original = next(p for p in groups["pocketai_rtl_files"] if p.name == "pa_ibex_wrapper.sv")
        target = output / original.relative_to(baseline)
        old = "'{default: prim_ram_1p_pkg::RAM_1P_CFG_REQ_DEFAULT}"
        new = "{ibex_pkg::IC_NUM_WAYS{prim_ram_1p_pkg::RAM_1P_CFG_REQ_DEFAULT}}"
        content = target.read_text()
        assert content.count(old) == 2
        target.write_text(content.replace(old, new))
        syntax_changes[str(original.relative_to(baseline))] = {
            "before": old, "after": new, "occurrences": 2, "sha256": digest(target),
            "reason": "Equivalent packed array replication; ICache remains disabled"}
    includes = ["-I" + str(p.relative_to(baseline)) for p in groups["pocketai_include_dirs"]]
    sources = [str(p.relative_to(baseline)) for k in ("pocketai_rtl_files", "pocketai_verilog_files")
               for p in groups[k]]
    (output / "elaborate.ys").write_text(
        "plugin -i synlig-sv\nread_systemverilog -defer -noassert " +
        " ".join(includes + sources) + "\nread_systemverilog -link\n" +
        "hierarchy -check -top pa_cluster_m5_board\n" +
        "proc\nopt_clean\nmemory_collect\nstat\nwrite_json elaborated.json\n")
    # A second front end is useful when Synlig cannot lower a legal SV pattern.
    # Conversion is a separate retained trial, not a rewrite of qualified RTL.
    (output / "sv2v.args").write_text("\n".join(
        ["--define=SYNTHESIS", "--top=pa_cluster_m5_board"] + includes + sources) + "\n")
    (output / "manifest.json").write_text(json.dumps({
        "status": "SOURCE_STAGE_ONLY", "baseline_commit": "7405919",
        "baseline_evidence_sha256": digest(evidence_path),
        "top": "pa_cluster_m5_board", "sources": records,
        "technology_bindings": bindings,
        "syntax_changes": syntax_changes,
        "asic_memory_mapping": False, "chip_pads": False,
        "elaboration_script_sha256": digest(output / "elaborate.ys"),
    }, indent=2, sort_keys=True) + "\n")
    print(f"M6 SOURCE STAGE PASS: {len(records)} hash-bound files -> {output}")


if __name__ == "__main__":
    main()
