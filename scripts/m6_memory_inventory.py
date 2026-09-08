"""Enumerate every elaborated memory instance; never equate bits to ASIC area."""
import argparse
import hashlib
import json
from pathlib import Path


def number(value):
    if isinstance(value, int):
        return value
    if set(value) <= {"0", "1"}:
        return int(value, 2)
    raise ValueError(f"unknown/nonbinary memory parameter: {value!r}")


def inventory(netlist, top):
    modules = netlist["modules"]
    result = []

    def visit(module, path, ancestors):
        assert module not in ancestors, "recursive hierarchy"
        attributes = modules[module].get("attributes", {})
        if any(number(attributes.get(tag, 0)) for tag in ("blackbox", "whitebox")):
            raise ValueError(f"opaque module cannot prove complete memory scope: {path}")
        for name, cell in modules[module].get("cells", {}).items():
            child = path + "/" + name
            kind = cell["type"]
            if kind == "$mem_v2":
                p = cell["parameters"]
                width, depth = number(p["WIDTH"]), number(p["SIZE"])
                result.append(dict(instance=child, width=width, depth=depth,
                    bits=width*depth, read_ports=number(p["RD_PORTS"]),
                    write_ports=number(p["WR_PORTS"]),
                    clocked_read_mask=number(p["RD_CLK_ENABLE"]),
                    initialized_bits=sum(x in "01" for x in p["INIT"])))
            elif kind in modules:
                visit(kind, child, ancestors | {module})
            elif not kind.startswith("$"):
                raise ValueError(f"unresolved non-Yosys cell: {child} ({kind})")

    visit(top, top, set())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path)
    parser.add_argument("--top", default="pa_cluster_m5_board")
    args = parser.parse_args()
    raw = args.netlist.read_bytes()
    memories = inventory(json.loads(raw), args.top)
    print(json.dumps(dict(status="ELABORATED_RTL_MEMORY_INVENTORY_ONLY",
        netlist_sha256=hashlib.sha256(raw).hexdigest(), top=args.top,
        memory_instances=len(memories), memory_bits=sum(m["bits"] for m in memories),
        memories=memories), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
