# M6 architecture and implementation figures

These figures accompany [PPA_REPORT.md](../../PPA_REPORT.md). They are
preliminary evidence, not a routed 100-MHz ASIC or fabricated-silicon result.
The [manifest](manifest.json) binds native sources, primary EDA artifacts,
exports and reviewed deliverables to SHA-256 hashes.

| Figure | Editable/native source | Deliverables |
|---|---|---|
| High-level architecture | `architecture.tex`, `style.tex` | SVG and PDF |
| FPGA/ASIC boundaries | `platforms.tex`, `style.tex` | SVG and PDF |
| Vivado system | Actual frozen `system.bd`, `export_vivado_bd.tcl` | Native SVG and vector-cropped PDF |
| ASIC macro floorplan | Actual retained OpenDB, `export_asic_view.tcl` | Actual OpenROAD PNG and exported macro-coordinate TSV |
| Labeled ASIC geometry | `m6_render_asic_floorplan.py` + actual TSV | Vector SVG and PDF, with grayscale-readable owner letters |

The architecture and platform diagrams are native TikZ, not generated raster
art. The ASIC geometry plot preserves every macro's position and dimensions;
labels and colors explain ownership. It does not invent standard-cell
placement or signal routing. The raw OpenROAD canvas is retained separately;
its native highlight colors differ from the publication palette.

## Native TikZ

With TeX Live, Poppler and Inkscape installed, from the repository root:

```sh
python3 scripts/m6_render_tikz.py build/m6_tikz_new
```

This copies the native sources into a fresh build directory, invokes
`pdflatex -no-shell-escape`, and produces vector PDF/SVG plus color/grayscale
review PNGs. The retained reviewed run is `build/m6_tikz_figures_v3`.

## Actual Vivado block-design export

Use Vivado 2025.1 with an available X display. The source project is opened
read-only and its stored layout is retained. No IP regeneration or BD save is
performed. The script checks that actual image files were produced; a zero
Vivado exit code alone is insufficient.

```sh
DISPLAY=:1 vivado -mode batch -source asic/m6/export_vivado_bd.tcl -tclargs \
  build/m5_startup_data_direct_pynq_v2/m5_pynq.xpr \
  build/m5_startup_data_direct_pynq_v2/m5_pynq.srcs/sources_1/bd/system/system.bd \
  build/m6_vivado_new
inkscape build/m6_vivado_new/vivado_system.svg --export-type=pdf \
  --export-area-drawing --export-filename=build/m6_vivado_new/vivado_system_cropped.pdf
```

The retained successful export is `build/m6_vivado_figure_v4`. The vector crop
removes empty page margins without editing the circuit drawing. The FPGA
release's timing evidence comes from its qualified routed DCP, not this BD image.

## Actual ASIC macro-placement view

The source is the read-only database at
`build/m6_core_physical_v4/runs/floorplan_v1/12-openroad-generatepdn/pa_m6_soc.odb`.
Use the container pinned in `asic/m6/tools.json`, with `openroad -gui -exit`
and `QT_QPA_PLATFORM=offscreen`. Mount that physical-stage directory read-only
at `/input`, `asic/m6` read-only at `/scripts`, and a fresh M6 output directory
at `/output`. Set:

```text
M6_FIGURE_ODB=/input/runs/floorplan_v1/12-openroad-generatepdn/pa_m6_soc.odb
M6_FIGURE_IMAGE=/output/asic_floorplan.png
```

Run `/scripts/export_asic_view.tcl`. It exports the actual GUI canvas and all
292 macro coordinates/owners without saving changes to the database. The
retained successful run is `build/m6_asic_figure_v8`. For the labeled vector view:

```sh
python3 scripts/m6_render_asic_floorplan.py \
  build/m6_asic_figure_v8/macros.tsv build/m6_asic_vector_new
```

The retained reviewed vector run is `build/m6_asic_vector_v1`. The current
figure is macro placement plus PDN only, for the historical 2x adapter. It is
not the new 1x netlist. Replace it only with explicitly reviewed, source-bound
evidence from a later qualified physical implementation.

## Review and packaging

Color and grayscale geometry/TikZ views were inspected on 2026-09-08. Labels,
arrows, bounds, ownership counts and preliminary-stage captions were checked.
The actual Vivado crop and OpenROAD canvas were also visually inspected.
`scripts/m6_package_figures.py` packages those fixed reviewed runs and refuses
changed output overwrites. To publish a new figure revision, review new runs
and update the packaging selections/provenance explicitly; do not overwrite
old physical trials or imply that packaging itself qualifies M6.
