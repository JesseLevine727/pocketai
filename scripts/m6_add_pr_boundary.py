"""Add only the missing nonmanufacturing Sky130 PR boundary to a macro copy.

The original downloaded view is retained. All other geometry and instance
transforms are compared after writing; this is not an SRAM DRC/LVS waiver.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import klayout.db as db


def fingerprint(layout):
    rows = []
    for cell in sorted(layout.each_cell(), key=lambda c: c.name):
        for layer in layout.layer_indices():
            info = layout.get_info(layer)
            if (info.layer, info.datatype) == (235, 4):
                continue
            values = sorted(s.to_s() for s in cell.shapes(layer).each())
            if values:
                rows.append((cell.name, info.layer, info.datatype,
                             hashlib.sha256("\n".join(values).encode()).hexdigest()))
        for inst in cell.each_inst():
            rows.append((cell.name, "instance", inst.cell.name, str(inst.cplx_trans),
                         str(inst.a), str(inst.b), inst.na, inst.nb))
    return hashlib.sha256(json.dumps(sorted(rows, key=str)).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("lef", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() == args.source.resolve():
        parser.error("new output copy required")
    text = args.lef.read_text()
    name = re.search(r"^MACRO (\S+)", text, re.M)[1]
    size = re.search(r"\bSIZE ([\d.]+) BY ([\d.]+)\s*;", text)
    width, height = float(size[1]), float(size[2])
    layout = db.Layout()
    layout.read(str(args.source))
    top = layout.cell(name)
    assert top is not None and top in layout.top_cells()
    before = fingerprint(layout)
    boundary_layer = layout.layer(235, 4)
    assert top.shapes(boundary_layer).is_empty(), "PR boundary already exists"
    boundary = db.DBox(0, 0, width, height).to_itype(layout.dbu)
    top.shapes(boundary_layer).insert(boundary)
    layout.write(str(args.output))
    reread = db.Layout()
    reread.read(str(args.output))
    assert layout.dbu == reread.dbu and before == fingerprint(reread), "non-boundary geometry changed"
    shapes = list(reread.cell(name).shapes(reread.layer(235, 4)).each())
    assert len(shapes) == 1 and shapes[0].is_box() and shapes[0].box == boundary
    print(json.dumps(dict(status="BOUNDARY_METADATA_ONLY_PASS", macro=name,
        source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
        output_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        lef_sha256=hashlib.sha256(args.lef.read_bytes()).hexdigest(),
        nonboundary_geometry_sha256=before, width_um=width, height_um=height,
        layer=235, datatype=4, drc_qualified=False), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
