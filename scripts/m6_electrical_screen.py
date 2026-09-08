"""Read-only, pinned-IP electrical screen; no Liberty edits or timing waiver.

Table interpolation is bounded to the characterized grid. Zero-wire driver
estimates are a screening aid, NOT an extracted clock network or chip pass.
The intentionally narrow parser rejects unreviewed output-pin overrides.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from scripts.m6_memory_feasibility import CORNERS, MACROS, NUMBER, ROOT, groups


def scalar(text, name):
    match = re.search(r"\b" + re.escape(name) + r"\s*:\s*(" + NUMBER + r")\s*;", text)
    if match is None or not math.isfinite(float(match[1])):
        raise ValueError(f"missing/non-finite {name}")
    return float(match[1])


def named_group(text, kind, name):
    match = re.search(r"\b" + re.escape(kind) + r'\s*\(\s*"?' + re.escape(name) + r'"?\s*\)\s*\{', text)
    if match is None:
        raise ValueError(f"missing {kind}({name})")
    return next(groups(text[match.start():], kind))


def units(text):
    if not re.search(r'\btime_unit\s*:\s*"1ns"\s*;', text) or not re.search(
            r'\bcapacitive_load_unit\s*\(\s*1(?:\.0+)?\s*,\s*"?pf"?\s*\)\s*;', text):
        raise ValueError("explicit 1ns/1pF units required")


def table(body):
    def numbers(name):
        match = re.search(r"\b" + name + r"\s*\((.*?)\)\s*;", body, re.S)
        if match is None:
            raise ValueError(f"missing table {name}")
        result = [float(x) for x in re.findall(NUMBER, match[1])]
        if not result or not all(math.isfinite(x) for x in result):
            raise ValueError(f"invalid table {name}")
        return result
    xs, ys, values = numbers("index_1"), numbers("index_2"), numbers("values")
    if len(values) != len(xs)*len(ys) or any(
            len(axis) < 2 or any(a >= b for a, b in zip(axis, axis[1:])) for axis in (xs, ys)):
        raise ValueError("invalid table dimensions/axes")
    return xs, ys, [values[i:i+len(ys)] for i in range(0, len(values), len(ys))]


def interpolate(sample, x, y):
    xs, ys, rows = sample
    def interval(axis, value):
        if not math.isfinite(value) or not axis[0] <= value <= axis[-1]:
            raise ValueError("extrapolation outside characterized domain forbidden")
        i = next(i for i in range(len(axis)-1) if axis[i] <= value <= axis[i+1])
        return i, (value-axis[i])/(axis[i+1]-axis[i])
    i, a = interval(xs, x)
    j, b = interval(ys, y)
    return ((1-a)*(1-b)*rows[i][j] + a*(1-b)*rows[i+1][j]
            + (1-a)*b*rows[i][j+1] + a*b*rows[i+1][j+1])


def slew_span(text, edge):
    span = scalar(text, f"slew_upper_threshold_pct_{edge}") - scalar(text, f"slew_lower_threshold_pct_{edge}")
    if not 0 < span <= 100 or scalar(text, "slew_derate_from_library") != 1:
        raise ValueError("only valid thresholds and unity slew derating supported")
    return span


def output_screen(text):
    units(text)
    body = named_group(text, "bus", "dout")
    if re.search(r"\bmax_transition\s*:", body):
        raise ValueError("unreviewed output override: do not assume library default applies")
    default = scalar(text, "default_max_transition")
    samples = [table(part) for kind in ("rise_transition", "fall_transition") for part in groups(body, kind)]
    if len(samples) != 2:
        raise ValueError("expected one shared rise and fall output timing table")
    values = [value for _, _, rows in samples for row in rows for value in row]
    return {"library_default_max_transition_ns": default,
            "minimum_characterized_output_transition_ns": min(values),
            "maximum_characterized_output_transition_ns": max(values),
            "characterized_table_entries": len(values),
            "any_characterized_output_transition_meets_default": min(values) <= default,
            "physical_timing_pass": None,
            "interpretation": "Library-contract screen, not proof of a physical SRAM defect or a waiver."}


def driver_screen(macro, std):
    units(macro)
    units(std)
    clk = named_group(macro, "pin", "clk")
    limit = scalar(clk, "max_transition")
    result = {}
    for name in ("clkbuf_16", "buf_16", "clkinv_16", "inv_16"):
        cell = named_group(std, "cell", "sky130_fd_sc_hd__" + name)
        row = {"inverting": "inv" in name, "clock_input_limit_ns": limit, "edges": {}}
        for edge in ("rise", "fall"):
            sample = table(next(groups(cell, edge + "_transition")))
            cap = scalar(clk, edge + "_capacitance")
            ratio = slew_span(macro, edge)/slew_span(std, edge)
            # Minimum over characterized input slews, same pin's edge-specific
            # capacitance, no wire. Linear threshold normalization, as in STA;
            # this is not a SPICE waveform measurement.
            best = min(interpolate(sample, slew, cap) for slew in sample[0]) * ratio
            typical = interpolate(sample, 0.15, cap) * ratio
            row["edges"][edge] = {"pin_capacitance_pf": cap,
                "threshold_normalization_ratio": ratio,
                "best_zero_wire_transition_at_macro_thresholds_ns": best,
                "transition_at_0p15ns_driver_input_slew_ns": typical,
                "best_zero_wire_meets_input_limit": best <= limit}
        row["physical_clock_pass"] = None
        result[name] = row
    return result


def collect(output):
    output = output.resolve()
    if output.parent != ROOT / "build" or not output.name.startswith("m6_") or output.exists():
        raise ValueError("fresh direct build/m6_* directory required")
    report = {"schema": 1, "status": "UNQUALIFIED_ELECTRICAL_SCREEN", "sources": {}, "macros": {}}
    def read(path):
        data = path.read_bytes()
        report["sources"][str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
        return data.decode()
    read(Path(__file__).resolve())
    for macro in MACROS:
        report["macros"][macro] = {}
        for corner in CORNERS:
            text = read(ROOT / "build/m6_memory_screen_v1" / f"{macro}_{corner}.lib")
            row = output_screen(text)
            if macro == MACROS[0]:
                std = read(ROOT / "build/m6_pdks/sky130A/libs.ref/sky130_fd_sc_hd/lib" /
                           f"sky130_fd_sc_hd__{corner}.lib")
                row["zero_wire_clock_driver_screen"] = driver_screen(text, std)
            report["macros"][macro][corner] = row
    report["all_screened_macros_have_output_default_conflict_at_all_corners"] = all(
        not row["any_characterized_output_transition_meets_default"]
        for corners in report["macros"].values() for row in corners.values())
    output.mkdir()
    (output / "electrical.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = collect(args.output)
    print(report["status"])
    print("All screened macros/corners conflict with output default:",
          report["all_screened_macros_have_output_default_conflict_at_all_corners"])


if __name__ == "__main__":
    main()
