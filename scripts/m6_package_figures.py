"""Package reviewed, source-traceable M6 figure artifacts without rerunning EDA."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs/figures/m6"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    copies = {}
    for name in ("architecture", "platforms"):
        for suffix in (".pdf", ".svg"):
            copies[name+suffix] = "build/m6_tikz_figures_v3/"+name+suffix
    for suffix in (".pdf", ".svg"):
        copies["asic_floorplan"+suffix] = "build/m6_asic_vector_v1/asic_floorplan"+suffix
    copies.update({"vivado_system.svg": "build/m6_vivado_figure_v4/vivado_system.svg",
                   "vivado_system.pdf": "build/m6_vivado_figure_v4/vivado_system_cropped.pdf",
                   "asic_openroad.png": "build/m6_asic_figure_v8/asic_floorplan.png",
                   "asic_macros.tsv": "build/m6_asic_figure_v8/macros.tsv"})
    for manifest, source_key in (("build/m6_tikz_figures_v3/manifest.json", "sources"),):
        for path, sha in json.loads((ROOT/manifest).read_text())[source_key].items():
            assert digest(ROOT/path) == sha, f"figure source changed: {path}"
    assert "M6 VIVADO" in (ROOT/"build/m6_vivado_figure_v4.log").read_text()
    assert "M6 ASIC ACTUAL DATABASE VIEW EXPORTED" in (ROOT/"build/m6_asic_figure_v8/export.log").read_text()
    sources = ["asic/m6/export_vivado_bd.tcl", "asic/m6/export_asic_view.tcl",
               "scripts/m6_render_tikz.py", "scripts/m6_render_asic_floorplan.py",
               "scripts/m6_package_figures.py", "docs/figures/m6/architecture.tex",
               "docs/figures/m6/platforms.tex", "docs/figures/m6/style.tex",
               "build/m6_vivado_figure_v4/cells.tsv", "build/m6_vivado_figure_v4/export.txt",
               "build/m6_vivado_figure_v4.log", "build/m6_asic_figure_v8/export.log",
               "build/m6_asic_figure_v8/macros.tsv",
               "build/m5_startup_data_direct_pynq_v2/m5_pynq.srcs/sources_1/bd/system/system.bd",
               "build/m6_core_physical_v4/runs/floorplan_v1/12-openroad-generatepdn/pa_m6_soc.odb"]
    for target, source in copies.items():
        if (TARGET/target).exists():
            assert digest(TARGET/target) == digest(ROOT/source), f"refuse changed figure overwrite: {target}"
        else:
            shutil.copyfile(ROOT/source, TARGET/target)
    result = {"schema": 1, "status": "REVIEWED_PRELIMINARY_FIGURES_NOT_M6_CLOSURE",
              "visual_review": "2026-09-08: native architecture/platform and ASIC geometry checked in color/grayscale; native Vivado crop and actual OpenROAD canvas checked visually",
              "vivado": {"source_release": "7405919", "read_only": True,
                         "export": "Vivado write_bd_layout, retained layout, SVG and vector-cropped PDF"},
              "asic": {"run": "m6_core_physical_v4/floorplan_v1", "macros": 292,
                       "stage": "MACRO_PLACEMENT_PDN_ONLY_HISTORICAL_2X_ADAPTER",
                       "standard_cells_placed": False, "routed": False, "timing_100mhz_pass": False,
                       "geometry_plot": "Labeled vector view of actual OpenDB-exported macro bounds",
                       "raw_tool_view": "asic_openroad.png; OpenROAD GUI highlighting only"},
              "sources": {s: digest(ROOT/s) for s in sources},
              "outputs": {t: {"source": s, "sha256": digest(TARGET/t)} for t, s in copies.items()}}
    encoded = json.dumps(result, indent=2, sort_keys=True)+"\n"
    if (TARGET/"manifest.json").exists():
        assert (TARGET/"manifest.json").read_text() == encoded, "review changed provenance before replacing manifest"
    else:
        (TARGET/"manifest.json").write_text(encoded)
    print("M6 reviewed preliminary figure package PASS; final routed ASIC figure pending")


if __name__ == "__main__":
    main()
