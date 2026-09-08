"""Make a labeled vector inventory from actual OpenDB-exported macro geometry.

This is a visualization of a retained macro-placement checkpoint, not a new
placement, completed standard-cell layout, routed chip or fabricated die.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "gemm": ("G", "GEMM", 112, "#0072B2"),
    "sfpu": ("S", "SFPU", 18, "#009E73"),
    "scratchpad": ("R", "Scratchpad", 32, "#E69F00"),
    "instruction_mirror": ("I", "Instruction mirror", 64, "#CC79A7"),
    "data_mirror": ("D", "Data mirror", 64, "#56B4E9"),
    "other": ("B", "Burst buffer", 2, "#D55E00"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != ROOT / "build" or not output.name.startswith("m6_") or output.exists():
        parser.error("fresh direct build/m6_* output required")
    rows = list(csv.DictReader(args.inventory.open(), delimiter="\t"))
    assert Counter(r["owner"] for r in rows) == Counter({k: v[2] for k, v in GROUPS.items()})
    assert len({r["instance"] for r in rows}) == 292
    # The pinned OpenDB uses 1000 DBU/um. Scale to a 9.1 x 9.9-mm frame.
    scale = 800 / 9_100_000
    x0, y0, height = 36, 110, 9_900_000 * scale
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="1080" viewBox="0 0 1180 1080">',
             '<rect width="1180" height="1080" fill="white"/>',
             '<g font-family="DejaVu Sans, sans-serif" fill="#273640">',
             '<text x="36" y="36" font-size="24" font-weight="bold">PocketAI: retained ASIC macro floorplan</text>',
             '<text x="36" y="68" font-size="17">Actual OpenDB coordinates · 292 SRAM macros · historical 2× adapter candidate</text>',
             f'<rect x="{x0}" y="{y0}" width="800" height="{height:.3f}" fill="#F6F7F8" stroke="#273640" stroke-width="2"/>']
    for row in rows:
        a, b, c, d = [int(row[k]) for k in ("x_min_dbu", "y_min_dbu", "x_max_dbu", "y_max_dbu")]
        assert 0 <= a < c <= 9_100_000 and 0 <= b < d <= 9_900_000
        code, _, _, color = GROUPS[row["owner"]]
        x, y, w, h = x0+a*scale, y0+height-d*scale, (c-a)*scale, (d-b)*scale
        lines.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="{color}" fill-opacity=".24" stroke="{color}" stroke-width="1.4"/>')
        lines.append(f'<text x="{x+w/2:.3f}" y="{y+h/2+5:.3f}" text-anchor="middle" font-size="15" font-weight="bold">{code}</text>')
    lines += ['<text x="874" y="137" font-size="19" font-weight="bold">Memory ownership</text>']
    for i, (code, label, count, color) in enumerate(GROUPS.values()):
        y = 178+i*62
        lines += [f'<rect x="874" y="{y-20}" width="25" height="25" fill="{color}" fill-opacity=".24" stroke="{color}"/>',
                  f'<text x="886.5" y="{y-2}" text-anchor="middle" font-size="15" font-weight="bold">{code}</text>',
                  f'<text x="910" y="{y}" font-size="17">{label}</text>',
                  f'<text x="910" y="{y+23}" font-size="15">{count} macros</text>']
    notes = ["9.1 × 9.9 mm core frame", "584 KiB physical SRAM", "Both read copies included", "", "Macro placement + PDN only", "Standard cells not placed", "Signal routing not complete", "No pads in this core view", "100-MHz closure: pending"]
    for i, note in enumerate(notes):
        lines.append(f'<text x="874" y="{610+i*31}" font-size="16">{note}</text>')
    lines += ['<text x="36" y="1028" font-size="16">Source: m6_core_physical_v4 / floorplan_v1 / OpenROAD.GeneratePDN</text>',
              '<text x="36" y="1057" font-size="16">Labels and colors identify ownership; all macro positions and dimensions come from the retained database.</text>',
              '</g></svg>']
    output.mkdir()
    (output / "asic_floorplan.svg").write_text("\n".join(lines)+"\n")
    subprocess.run(["inkscape", str(output / "asic_floorplan.svg"), "--export-type=pdf",
                    "--export-filename=" + str(output / "asic_floorplan.pdf")], check=True, timeout=30)
    for gray in (False, True):
        subprocess.run(["pdftoppm", *( ["-gray"] if gray else []), "-png", "-singlefile", "-scale-to", "2200",
                        str(output / "asic_floorplan.pdf"), str(output / ("asic_floorplan_gray" if gray else "asic_floorplan"))], check=True, timeout=30)
    manifest = {"status": "RENDERED_REQUIRES_VISUAL_REVIEW", "actual_geometry_not_new_placement": True,
                "source": str(args.inventory.resolve().relative_to(ROOT)),
                "source_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
                "macros": 292, "outputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                            for p in sorted(output.iterdir())}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")


if __name__ == "__main__":
    main()
