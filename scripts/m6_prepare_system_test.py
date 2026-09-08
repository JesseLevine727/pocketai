"""Reuse the frozen dual-hart accelerator test with only clock/top adaptation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != ROOT / "build" or not out.name.startswith("m6_") or out.exists():
        parser.error("new immediate build/m6_* output required")
    evidence = json.loads((ROOT / "docs/m5_startup_evidence.json").read_text())
    base = ROOT / evidence["selection"]["accelerators"]
    hashes = {}
    for name in ("test.cc", "test.bin"):
        path = base / name
        key = str(path.relative_to(ROOT))
        hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert hashes[key] == evidence["artifacts"][key], key
    original = (base / "test.cc").read_text()
    changes = [
        ("Vpa_m5_cluster_top", "Vpa_m6_cluster_core", 3),
        ("top.IO_CLK = 0; top.IO_RST_N = 1; top.CORE_RST_N = 1;",
         "top.m6_clk_mem_i = 0; top.m6_mem_rst_ni = 1;\n    top.IO_CLK = 0; top.IO_RST_N = 1; top.CORE_RST_N = 1;", 1),
        ("drive_memory(); top.IO_CLK = 0; top.eval();", """drive_memory(); top.IO_CLK = 0;
    top.m6_mem_rst_ni = top.IO_RST_N; top.eval();
    // Complete the previous cycle's pending write while system clock is low.
    top.m6_clk_mem_i = 1; context.timeInc(10); top.eval();
    top.m6_clk_mem_i = 0; context.timeInc(10); top.eval();""", 1),
        ("++cycles; context.timeInc(1);\n    top.IO_CLK = 0; top.eval();", """++cycles;
    // Service captured reads while the system clock is high. At the next
    // system edge all consumers see the same data as the original memory.
    top.m6_clk_mem_i = 1; context.timeInc(10); top.eval();
    top.m6_clk_mem_i = 0; context.timeInc(10); top.eval();
    top.IO_CLK = 0; top.eval();""", 1),
    ]
    content = original
    for before, after, count in changes:
        assert content.count(before) == count, before
        content = content.replace(before, after)
    out.mkdir()
    (out / "test.cc").write_text(content)
    shutil.copyfile(base / "test.bin", out / "test.bin")
    (out / "manifest.json").write_text(json.dumps(dict(status="PREPARED_NOT_RUN",
        inputs=hashes, modifications=[dict(before=b, after=a, occurrences=n) for b,a,n in changes],
        output_sha256=hashlib.sha256(content.encode()).hexdigest(),
        oracle_changes=False, firmware_changes=False, rtl_scope="full SRAM-backed pa_m6_cluster_core",
        exclusions="not timing simulation, chip pads or external serial interface"), indent=2, sort_keys=True)+"\n")
    print("M6 SYSTEM TEST PREPARED: frozen firmware/oracles, explicit two-phase clock adaptation")


if __name__ == "__main__":
    main()
