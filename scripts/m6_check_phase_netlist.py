"""Check that SRAM phase data survived synthesis separately from the clock."""
import argparse
import hashlib
import json
from pathlib import Path


def check(design):
    module = design["modules"]["pa_m6_soc"]
    cells = module["cells"]
    drivers = {}
    for name, cell in cells.items():
        for port, direction in cell["port_directions"].items():
            if direction == "output":
                for bit in cell["connections"][port]:
                    assert bit not in drivers, (name, port, bit)
                    drivers[bit] = (name, port, cell)
    root = [(name, cell) for name, cell in cells.items()
            if name.startswith("u_clock.") and "Q" in cell["connections"]]
    assert len(root) == 1, "exactly one system divider FF required"
    _, divider = root[0]
    assert divider["type"].startswith("sky130_fd_sc_hd__dfrtp_")
    sys_bit = divider["connections"]["Q"][0]
    mem_bit = module["ports"]["clk_mem_i"]["bits"][0]
    reset_bit = module["ports"]["s_axi_aresetn"]["bits"][0]

    def inverted_from(bit, source):
        _, port, cell = drivers[bit]
        assert port == "Y" and cell["type"].startswith("sky130_fd_sc_hd__inv_")
        assert cell["connections"]["A"] == [source]

    inverted_from(divider["connections"]["CLK"][0], mem_bit)
    inverted_from(divider["connections"]["D"][0], sys_bit)
    assert divider["connections"]["RESET_B"] == [reset_bit]
    phases = set()
    macros = [cell for cell in cells.values() if cell["type"] == "sram22_512x32m4w8"]
    assert len(macros) == 292, "full memory capacity required"
    for macro in macros:
        phase_bit = macro["connections"]["we"][0]
        assert phase_bit != sys_bit, "SRAM phase merged into system clock"
        name, port, phase = drivers[phase_bit]
        assert port == "Q" and phase["type"].startswith("sky130_fd_sc_hd__dfstp_"), \
            "SRAM write phase must be separate set-high FF data"
        assert phase["connections"]["SET_B"] == [reset_bit]
        inverted_from(phase["connections"]["CLK"][0], mem_bit)
        inverted_from(phase["connections"]["D"][0], phase_bit)
        phases.add(name)
    return dict(status="SEPARATE_PHASE_DATA_NETLIST_PASS_NOT_TIMING_QUALIFICATION",
                macros=len(macros), independent_phase_registers=len(phases),
                phase_reset_value=1, system_divider_reset_value=0,
                shared_falling_memory_edge=True, macro_write_enable_is_clock=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path)
    args = parser.parse_args()
    raw = args.netlist.read_bytes()
    result = check(json.loads(raw))
    result["input_sha256"] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
