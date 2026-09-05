#!/usr/bin/env python3
"""Convert FuseSoC's resolved EDAM source list into a Vivado Tcl fragment."""

from pathlib import Path
import sys
import yaml


def tcl_brace(path: Path) -> str:
    return "{" + str(path.resolve()).replace("}", "\\}") + "}"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: eda_to_vivado.py INPUT.eda.yml OUTPUT.tcl", file=sys.stderr)
        return 2

    eda_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2]).resolve()
    with eda_path.open(encoding="utf-8") as handle:
        eda = yaml.safe_load(handle)

    sources: list[Path] = []
    verilog_sources: list[Path] = []
    include_files: list[Path] = []
    include_dirs: set[Path] = set()
    memory_files: list[Path] = []
    for item in eda["files"]:
        file_type = item.get("file_type")
        if file_type == "user" and Path(item["name"]).suffix == ".mem":
            memory_files.append(eda_path.parent / item["name"])
            continue
        if file_type == "verilogSource":
            verilog_sources.append(eda_path.parent / item["name"])
            continue
        if file_type != "systemVerilogSource":
            continue
        path = eda_path.parent / item["name"]
        if item.get("is_include_file"):
            include_dirs.add(path.parent)
            # FuseSoC marks macro-bearing compilation units such as
            # prim_flop_macros.sv as include files. Vivado still requires
            # every include file in the project before it can elaborate a
            # module reference. Compile .sv units and register .svh headers.
            if path.suffix == ".sv":
                sources.append(path)
            else:
                include_files.append(path)
        else:
            sources.append(path)

    if not sources:
        raise RuntimeError("FuseSoC EDAM contained no SystemVerilog sources")

    lines = ["set pocketai_rtl_files [list \\"]
    lines.extend(f"  {tcl_brace(path)} \\" for path in sources)
    lines.append("]")
    lines.append("set pocketai_verilog_files [list \\")
    lines.extend(f"  {tcl_brace(path)} \\" for path in verilog_sources)
    lines.append("]")
    lines.append("set pocketai_include_files [list \\")
    lines.extend(f"  {tcl_brace(path)} \\" for path in include_files)
    lines.append("]")
    lines.append("set pocketai_include_dirs [list \\")
    lines.extend(f"  {tcl_brace(path)} \\" for path in sorted(include_dirs))
    lines.append("]")
    lines.append("set pocketai_memory_files [list \\")
    lines.extend(f"  {tcl_brace(path)} \\" for path in memory_files)
    lines.append("]")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[eda_to_vivado] {len(sources)} sources, "
          f"{len(verilog_sources)} Verilog sources, "
          f"{len(include_files)} headers, "
          f"{len(memory_files)} memory initializers, "
          f"{len(include_dirs)} include directories -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
