"""Map normalized full-system Yosys memories to explicit two-phase SRAM banks.

Fail closed on unsupported ports, initialization, resets, clocks or masks.
The input remains immutable. The output is a new M6 trial, not chip closure.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from scripts.m6_memory_inventory import number

ROOT = Path(__file__).resolve().parents[1]
TOP = "pa_cluster_m5_board"
PORTS = {"clk_sys_i": "input", "clk_mem_i": "input", "rst_ni": "input",
         "rd_en_i": "input", "rd_addr_i": "input", "rd_data_o": "output",
         "wr_mask_i": "input", "wr_addr_i": "input", "wr_data_i": "input"}
EXTRA = ("m6_clk_mem_i", "m6_mem_rst_ni")


def memory_spec(cell):
    p, c = cell["parameters"], cell["connections"]
    width, depth = number(p["WIDTH"]), number(p["SIZE"])
    reads, writes = number(p["RD_PORTS"]), number(p["WR_PORTS"])
    if writes == 0:
        assert all(bit in "01" for bit in p["INIT"]), "uninitialized read-only memory"
        return None, "constant ROM implemented as logic"
    if number(p["RD_CLK_ENABLE"]) != (1 << reads)-1:
        assert depth <= 256 and width*depth <= 8192, "bulk asynchronous memory cannot silently become FFs"
        return None, "small asynchronous storage retained as logic"
    if width*depth < 4096:
        return None, "small synchronous control storage retained as logic"
    assert width in (32, 36) and reads in (1, 2) and writes == 1
    assert number(p["OFFSET"]) == 0 and number(p["ABITS"]) == (depth-1).bit_length()
    assert set(p["INIT"]) <= {"x"}, "writable SRAM cannot inherit FPGA INIT"
    for tag in ("RD_CLK_POLARITY", "RD_CLK_ENABLE"):
        assert number(p[tag]) == (1 << reads)-1, tag
    for tag in ("WR_CLK_POLARITY", "WR_CLK_ENABLE"):
        assert number(p[tag]) == 1, tag
    for tag in ("RD_TRANSPARENCY_MASK", "RD_WIDE_CONTINUATION",
                "WR_WIDE_CONTINUATION", "WR_PRIORITY_MASK"):
        assert number(p[tag]) == 0, tag
    # A collision marked don't-care by normalization may return the old value.
    # Never turn write-first/transparent semantics into read-before-write.
    collision_x = number(p["RD_COLLISION_X_MASK"])
    assert 0 <= collision_x < (1 << reads)
    assert c["RD_ARST"] == ["0"]*reads and c["RD_SRST"] == ["0"]*reads
    assert set(p["RD_INIT_VALUE"]) <= {"x"}, "read register initialization requires explicit handling"
    assert c["RD_CLK"] == c["WR_CLK"]*reads, "memory clocks differ"
    mask = []
    for lo in range(0, width, 8):
        bits = c["WR_EN"][lo:min(lo+8, width)]
        assert len(set(bits)) == 1, "sub-byte write enables unsupported"
        mask.append(bits[0])
    spec = dict(width=width, depth=depth, read_ports=reads, address_width=number(p["ABITS"]),
                source_collision_x_mask=collision_x,
                logical_bits=width*depth, macros=reads*((depth+511)//512)*((width+31)//32))
    spec["physical_bits"] = spec["macros"]*512*32
    spec["wrapper"] = f"pa_m6_ram_w{width}_d{depth}_p{reads}"
    spec["mask_bits"] = mask
    return spec, None


def add_port(module, name):
    assert name not in module["ports"]
    used = [bit for data in module.get("netnames", {}).values() for bit in data["bits"] if isinstance(bit, int)]
    used += [bit for data in module["ports"].values() for bit in data["bits"] if isinstance(bit, int)]
    used += [bit for cell in module.get("cells", {}).values() for bits in cell["connections"].values()
             for bit in bits if isinstance(bit, int)]
    bit = max(used, default=1)+1
    module["ports"][name] = {"direction": "input", "bits": [bit]}
    module.setdefault("netnames", {})[name] = {"hide_name": 0, "bits": [bit], "attributes": {}}
    return [bit]


def transform(source):
    result = copy.deepcopy(source)
    modules = result["modules"]
    mapped, retained, specs = {}, {}, {}
    needs_clock = set()
    for name, module in modules.items():
        for cell_name, cell in module.get("cells", {}).items():
            if cell["type"] != "$mem_v2":
                continue
            try:
                spec, reason = memory_spec(cell)
            except (AssertionError, ValueError) as error:
                raise ValueError(f"unsupported memory {name}/{cell_name}: {error}") from error
            key = (name, cell_name)
            if reason:
                retained[key] = dict(reason=reason, width=number(cell["parameters"]["WIDTH"]),
                    depth=number(cell["parameters"]["SIZE"]))
                continue
            needs_clock.add(name)
            mapped[key] = spec
            specs[spec["wrapper"]] = spec
    # Propagate the technology clock/reset only along hierarchies that use it.
    while True:
        parents = {name for name, module in modules.items()
            if any(cell["type"] in needs_clock for cell in module.get("cells", {}).values())}
        enlarged = needs_clock | parents
        if enlarged == needs_clock:
            break
        needs_clock = enlarged
    assert TOP in needs_clock and mapped, "no full-system memory mapping"
    clocks = {name: {port: add_port(modules[name], port) for port in EXTRA} for name in sorted(needs_clock)}
    for name, module in modules.items():
        for cell_name, cell in module.get("cells", {}).items():
            if cell["type"] in needs_clock:
                for port in EXTRA:
                    cell["connections"][port] = clocks[name][port]
                    cell["port_directions"][port] = "input"
            spec = mapped.get((name, cell_name))
            if spec is None:
                continue
            old = cell["connections"]
            cell["type"] = spec["wrapper"]
            cell["parameters"] = {}
            cell["port_directions"] = dict(PORTS)
            cell["connections"] = {"clk_sys_i": old["WR_CLK"],
                "clk_mem_i": clocks[name][EXTRA[0]], "rst_ni": clocks[name][EXTRA[1]],
                "rd_en_i": old["RD_EN"], "rd_addr_i": old["RD_ADDR"], "rd_data_o": old["RD_DATA"],
                "wr_mask_i": spec["mask_bits"], "wr_addr_i": old["WR_ADDR"], "wr_data_i": old["WR_DATA"]}
    instances, exceptions = [], []
    def visit(name, path, ancestors):
        assert name not in ancestors
        # Walk original hierarchy, before replacing memories with bank wrappers.
        for cname, cell in source["modules"][name].get("cells", {}).items():
            key, child = (name, cname), path + "/" + cname
            if key in mapped:
                instances.append({"instance": child, **{k:v for k,v in mapped[key].items() if k != "mask_bits"}})
            elif key in retained:
                exceptions.append({"instance": child, **retained[key]})
            elif cell["type"] in source["modules"]:
                visit(cell["type"], child, ancestors | {name})
            elif not cell["type"].startswith("$"):
                raise ValueError(f"unresolved cell {child}")
    visit(TOP, TOP, set())
    core_name = modules[TOP]["cells"]["impl"]["type"]
    assert "pa_m5_cluster_top" in core_name
    # Preserve the full cluster boundary for reuse of the qualified firmware
    # harness; the board wrapper remains the matched portable-system boundary.
    modules["pa_m6_cluster_core"] = modules.pop(core_name)
    for module in modules.values():
        for cell in module.get("cells", {}).values():
            if cell["type"] == core_name:
                cell["type"] = "pa_m6_cluster_core"
    modules["pa_m6_portable"] = modules.pop(TOP)
    return result, specs, instances, exceptions


def wrappers(specs):
    output = ["// Generated explicit SRAM wrappers; not black-boxed for timing.\n"]
    for name, spec in sorted(specs.items()):
        w, d, a, r = (spec[k] for k in ("width", "depth", "address_width", "read_ports"))
        output.append(f"""module {name} (
`ifdef USE_POWER_PINS
  inout wire vdd, vss,
`endif
  input wire clk_sys_i, clk_mem_i, rst_ni,
  input wire [{r-1}:0] rd_en_i,
  input wire [{r*a-1}:0] rd_addr_i,
  output wire [{r*w-1}:0] rd_data_o,
  input wire [{(w+7)//8-1}:0] wr_mask_i,
  input wire [{a-1}:0] wr_addr_i,
  input wire [{w-1}:0] wr_data_i
);
  pa_m6_sram_1w2r #(.WIDTH({w}), .DEPTH({d}), .ADDR_WIDTH({a}), .READ_PORTS({r})) impl (
`ifdef USE_POWER_PINS
    .vdd(vdd), .vss(vss),
`endif
    .clk_sys_i(clk_sys_i), .clk_mem_i(clk_mem_i), .rst_ni(rst_ni),
    .rd_en_i(rd_en_i), .rd_addr_i(rd_addr_i), .rd_data_o(rd_data_o),
    .wr_mask_i(wr_mask_i), .wr_addr_i(wr_addr_i), .wr_data_i(wr_data_i));
endmodule
""")
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != ROOT / "build" or not out.name.startswith("m6_") or out.exists():
        parser.error("new immediate build/m6_* directory required")
    raw = args.input.read_bytes()
    mapped, specs, instances, exceptions = transform(json.loads(raw))
    out.mkdir()
    (out / "mapped.json").write_text(json.dumps(mapped))
    (out / "wrappers.sv").write_text(wrappers(specs))
    report = dict(status="MAPPED_RTL_NOT_PHYSICAL_QUALIFICATION", top="pa_m6_portable",
        input_sha256=hashlib.sha256(raw).hexdigest(), memory_instances=instances, retained_logic=exceptions,
        total_macros=sum(s["macros"] for s in instances), logical_mapped_bits=sum(s["logical_bits"] for s in instances),
        physical_sram_bits=sum(s["physical_bits"] for s in instances), clocks="memory 2x system, falling-edge divide-by-two")
    (out / "mapping.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(f"M6 MEMORY MAP: {len(instances)} logical arrays -> {report['total_macros']} SRAM macros; {len(exceptions)} explicit logic-storage exceptions")


if __name__ == "__main__":
    main()
