"""Bounded, pinned SRAM Liberty screen. This is NOT a timing-closure result.

Download only small textual timing/physical views; never launch P&R. Preserve
all samples and hashes in a fresh M6 directory. Report table extrema as table
extrema, not as a realizable path or an achieved operating frequency.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REVISION = "75cbe961e18ee00d5a6c73fa455505f0bcdf4c05"
BASE = f"https://raw.githubusercontent.com/ucb-substrate/sram22_sky130_macros/{REVISION}"
MACROS = ("sram22_512x32m4w8", "sram22_256x32m4w8", "sram22_128x32m4w8")
CORNERS = ("ss_100C_1v60", "tt_025C_1v80", "ff_n40C_1v95")
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def groups(text, name):
    """Return balanced named Liberty group bodies; ignore braces in strings."""
    clean = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for match in re.finditer(r"\b" + re.escape(name) + r"\s*\([^)]*\)\s*\{", clean):
        start = match.end()
        depth, quoted, escaped = 1, False, False
        for i in range(start, len(clean)):
            char = clean[i]
            if escaped:
                escaped = False
            elif char == "\\" and quoted:
                escaped = True
            elif char == '"':
                quoted = not quoted
            elif not quoted:
                depth += (char == "{") - (char == "}")
                if depth == 0:
                    yield clean[start:i]
                    break
        else:
            raise ValueError(f"unclosed {name} group")


def values(text, names):
    result = []
    for name in names:
        for body in groups(text, name):
            for table in re.findall(r"\bvalues\s*\((.*?)\)\s*;", body, re.S):
                result.extend(float(x) for x in re.findall(NUMBER, table))
    if not result or not all(math.isfinite(x) for x in result):
        raise ValueError(f"missing/non-finite table values for {names}")
    return {"min": min(result), "max": max(result), "entries": len(result)}


def inspect_liberty(text):
    if not re.search(r'\btime_unit\s*:\s*"1ns"\s*;', text):
        raise ValueError("only explicit 1ns libraries are supported")
    timings = {}
    for body in groups(text, "timing"):
        kind = re.search(r"\btiming_type\s*:\s*(\w+)\s*;", body)
        if kind:
            timings.setdefault(kind[1], []).append(body)
    checks = {}
    for kind in ("minimum_period", "min_pulse_width", "setup_rising", "hold_rising"):
        if kind not in timings:
            raise ValueError(f"missing {kind} timing checks")
        checks[kind] = values("\n".join(timings[kind]),
                              ("rise_constraint", "fall_constraint"))
    if "rising_edge" not in timings:
        raise ValueError("missing clock-to-output arcs")
    checks["clock_to_output"] = values("\n".join(timings["rising_edge"]),
                                        ("cell_rise", "cell_fall"))
    return checks


def screen(libraries, period_ns):
    worst = max(lib["minimum_period"]["max"] for lib in libraries.values())
    return {"requested_period_ns": period_ns,
            "worst_table_minimum_period_ns": worst,
            "period_only_headroom_ns": period_ns - worst,
            "period_only_pass": period_ns >= worst,
            "full_timing_pass": None,
            "qualification": "UNQUALIFIED_PERIOD_SCREEN_ONLY"}


def collect(output):
    output = output.resolve()
    if output.parent != ROOT / "build" or not output.name.startswith("m6_") or output.exists():
        raise ValueError("use a fresh direct build/m6_* output directory")
    output.mkdir()
    report = {"schema": 1, "status": "LIBERTY_SCREEN_NOT_PHYSICAL_QUALIFICATION",
              "revision": REVISION, "system_clock_target_mhz": 100,
              "current_adapter_command_window_ns": 2.5,
              "current_adapter_read_return_window_ns": 7.5,
              "notes": ["Table extrema span loads/slews; they are not one timing path.",
                        "Setup/hold, wiring, skew, electrical limits and macro boundaries still need STA.",
                        "The internal-verification and unavailable-leakage research deferrals remain."],
              "macros": {}, "artifacts": {}}
    for macro in MACROS:
        corner_checks = {}
        for suffix in (".v", ".lef") + tuple(f"_{c}.lib" for c in CORNERS):
            name = macro + suffix
            url = f"{BASE}/{macro}/{name}"
            with urlopen(url, timeout=25) as response:
                data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError("unexpectedly large textual macro view")
            path = output / name
            path.write_bytes(data)
            report["artifacts"][name] = {"url": url, "sha256": hashlib.sha256(data).hexdigest()}
            if suffix.endswith(".lib"):
                corner_checks[suffix[1:-4]] = inspect_liberty(data.decode())
        lef = (output / (macro + ".lef")).read_text()
        size = re.search(r"\bSIZE\s+(" + NUMBER + r")\s+BY\s+(" + NUMBER + r")\s*;", lef)
        if size is None:
            raise ValueError(f"missing LEF dimensions: {macro}")
        width, height = map(float, size.groups())
        report["macros"][macro] = {"width_um": width, "height_um": height,
            "macro_area_um2": width * height, "corners": corner_checks,
            "memory_200mhz": screen(corner_checks, 5.0),
            "memory_100mhz": screen(corner_checks, 10.0)}
    (output / "screen.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = collect(args.output)
    for macro, row in report["macros"].items():
        print(macro, json.dumps(row["memory_200mhz"]))


if __name__ == "__main__":
    main()
