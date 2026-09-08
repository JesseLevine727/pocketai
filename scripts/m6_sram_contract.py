"""Derive a restricted SRAM-output contract from unchanged characterized tables.

User-authorized project integration metadata correction, NOT new transistor
characterization, supplier approval or a physical pass. Preserve the original
library default, every input constraint and every timing/power table byte.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from scripts.m6_electrical_screen import named_group, table, units
from scripts.m6_memory_feasibility import CORNERS, ROOT, groups

MACRO = "sram22_512x32m4w8"


def derive_envelope(tables, limit_ns):
    if not tables or limit_ns <= 0:
        raise ValueError("positive design limit and tables required")
    xs, loads, _ = tables[0]
    if any(x != xs or y != loads for x, y, _ in tables):
        raise ValueError("review differing characterization grids")
    worst = [max(row[j] for _, _, rows in tables for row in rows) for j in range(len(loads))]
    safe = []
    for j, value in enumerate(worst):
        if value > limit_ns:
            break  # Use a safe contiguous interval, never an isolated safe sample.
        safe.append(j)
    if not safe:
        raise ValueError("no characterized operating point meets this limit")
    end = safe[-1]
    return {"input_slew_min_ns": xs[0], "input_slew_max_ns": xs[-1],
            "output_load_min_pf": loads[0], "output_load_max_pf": loads[end],
            "design_transition_limit_ns": limit_ns,
            "worst_characterized_transition_ns": max(worst[:end+1]),
            "table_transition_headroom_ns": limit_ns-max(worst[:end+1]),
            "grid_loads_pf": loads, "worst_transition_by_load_ns": worst}


def replacement(limit, lower, upper):
    return (f"max_capacitance : {upper:g};\n"
            f"        min_capacitance : {lower:g};\n"
            f"        max_transition : {limit:g};")


def patch_outputs(original, limit, lower, upper):
    body = named_group(original, "bus", "dout")
    pins = re.findall(r"\bpin\s*\(\s*dout\[(\d+)\]\s*\)", body)
    if sorted(map(int, pins)) != list(range(32)) or body.count("max_capacitance : 0.52;") != 32:
        raise ValueError("review changed output pin count or original capacitance")
    if re.search(r"\b(?:max_transition|min_capacitance)\s*:", body):
        raise ValueError("refuse a second/unreviewed output override")
    changed = body.replace("max_capacitance : 0.52;", replacement(limit, lower, upper))
    if original.count(body) != 1:
        raise ValueError("ambiguous output bus")
    return original.replace(body, changed)


def verify_patch(original, updated, limit, lower, upper):
    expected = patch_outputs(original, limit, lower, upper)
    if updated != expected:
        raise ValueError("changes outside reviewed output metadata")


def collect(output):
    output = output.resolve()
    if output.parent != ROOT / "build" or not output.name.startswith("m6_") or output.exists():
        raise ValueError("fresh direct build/m6_* output required")
    paths = [ROOT / "build/m6_sram512_v1" / f"{MACRO}_{corner}.lib" for corner in CORNERS]
    libraries = {path.name: path.read_text() for path in paths}
    sdc = ROOT / "asic/m6/bank_probe.sdc"
    match = re.findall(r"^set_max_transition ([0-9.]+) \[current_design\]$", sdc.read_text(), re.M)
    if len(match) != 1:
        raise ValueError("one existing design transition limit required")
    tables = []
    for text in libraries.values():
        units(text)
        body = named_group(text, "bus", "dout")
        for name in ("rise_transition", "fall_transition"):
            selected = list(groups(body, name))
            if len(selected) != 1:
                raise ValueError("expected one shared output timing arc per edge")
            tables.append(table(selected[0]))
    envelope = derive_envelope(tables, float(match[0]))
    output.mkdir()
    hashes = {}
    for name, original in libraries.items():
        updated = patch_outputs(original, envelope["design_transition_limit_ns"],
                                envelope["output_load_min_pf"], envelope["output_load_max_pf"])
        verify_patch(original, updated, envelope["design_transition_limit_ns"],
                     envelope["output_load_min_pf"], envelope["output_load_max_pf"])
        (output/name).write_text(updated)
        hashes[name] = hashlib.sha256(updated.encode()).hexdigest()
    paths += [sdc, Path(__file__).resolve(), ROOT / "scripts/m6_electrical_screen.py",
              ROOT / "scripts/m6_memory_feasibility.py"]
    result = {"schema": 1, "status": "TABLE_VALIDATED_PROJECT_CONTRACT_NOT_RECHARACTERIZATION",
              "macro": MACRO, "envelope": envelope,
              "authority": "User approved bounded SRAM-library correction/validation on 2026-09-08",
              "supplier_approved": False, "new_transistor_characterization": False,
              "physical_pass": False, "unchanged_timing_power_tables_and_input_constraints": True,
              "all_32_outputs_explicitly_constrained": True,
              "sources": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
              "outputs": hashes,
              "required_physical_checks": ["all input slews inside original characterization",
                  "all output loads inside restricted characterized envelope", "all receiver limits",
                  "setup, hold, period, pulse, DRC, antenna, connectivity and coverage"]}
    (output/"contract.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    result = collect(parser.parse_args().output)
    print(result["status"])
    print(json.dumps(result["envelope"], sort_keys=True))
