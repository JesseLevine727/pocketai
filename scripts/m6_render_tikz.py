"""Build editable M6 TikZ figures as vector PDFs/SVGs and review PNGs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/figures/m6"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != ROOT / "build" or not output.name.startswith("m6_") or output.exists():
        parser.error("use a fresh immediate build/m6_* directory")
    output.mkdir()
    sources = {}
    for path in sorted(SOURCE.glob("*.tex")):
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        shutil.copyfile(path, output / path.name)
    for name in ("architecture", "platforms"):
        commands = [["pdflatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", name + ".tex"],
                    ["pdftocairo", "-svg", name + ".pdf", name + ".svg"],
                    ["pdftoppm", "-png", "-singlefile", "-scale-to", "2200", name + ".pdf", name],
                    ["pdftoppm", "-gray", "-png", "-singlefile", "-scale-to", "1800", name + ".pdf", name + "_gray"]]
        for i, command in enumerate(commands):
            with (output / f"{name}_command_{i}.log").open("w") as log:
                subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=60)
    manifest = {"status": "RENDERED_REQUIRES_VISUAL_REVIEW", "native_format": "TikZ",
                "sources": sources,
                "outputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(output.iterdir()) if p.suffix in (".pdf", ".svg", ".png")}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("M6 native TikZ figures rendered; visual/architecture review still required")


if __name__ == "__main__":
    main()
