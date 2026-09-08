"""Wire the tested serial host to the complete clocked native-AXI core.

This stages a digital chip core for functional checks. Physical I/O cells and
pad-ring qualification are separate requirements, not implicit in this name.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("physical", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source, out = args.physical.resolve(), args.output.resolve()
    assert source.parent == out.parent == ROOT / "build"
    assert source.name.startswith("m6_") and out.name.startswith("m6_") and not out.exists()
    # The generated native-AXI wrapper has simple ANSI declarations only.
    import re
    soc_text = (source / "pa_m6_soc.sv").read_text()
    ports = re.findall(r"\b(input|output) wire (\[[^\]]+\] )?(\w+)(?:,|\n\);)", soc_text)
    assert len(ports) == 61, len(ports)
    external = {"clk_mem_i", "clk_sys_o"}
    declarations = [f"{direction} wire {width}{name}" for direction,width,name in ports
                    if name in external or name.startswith("m_axi_")]
    declarations += ["input wire rst_ni, spi_cs_ni, spi_sclk_i, spi_mosi_i",
                     "output wire spi_miso_o, uart_tx_o"]
    text = "// Complete digital chip core; physical I/O cells are not in this module.\n"
    text += "module pa_m6_chip_core(\n  " + ",\n  ".join(declarations) + "\n);\n"
    for _, width, name in ports:
        if name not in external and not name.startswith("m_axi_") and name != "s_axi_aresetn":
            text += f"  wire {width}{name};\n"
    text += """  wire req_valid, req_ready, req_write, rsp_valid;
  wire [3:0] req_mask;
  wire [31:0] req_addr, req_data, rsp_data;
  wire [1:0] rsp_error;
  pa_m6_spi u_spi(.clk_i(clk_sys_o), .rst_ni(rst_ni),
    .cs_ni(spi_cs_ni), .sclk_i(spi_sclk_i), .mosi_i(spi_mosi_i), .miso_o(spi_miso_o),
    .req_valid_o(req_valid), .req_write_o(req_write), .req_mask_o(req_mask),
    .req_addr_o(req_addr), .req_data_o(req_data), .req_ready_i(req_ready),
    .rsp_valid_i(rsp_valid), .rsp_error_i(rsp_error), .rsp_data_i(rsp_data));
  pa_m6_host u_host(.clk_i(clk_sys_o), .rst_ni(rst_ni),
    .req_valid_i(req_valid), .req_ready_o(req_ready), .req_write_i(req_write),
    .req_mask_i(req_mask), .req_addr_i(req_addr), .req_data_i(req_data),
    .rsp_valid_o(rsp_valid), .rsp_error_o(rsp_error), .rsp_data_o(rsp_data),
    .cluster_aresetn_o(cluster_aresetn), .core_aresetn_o(core_aresetn),
    .cfg_enable_o(cfg_enable), .cfg_flush_o(cfg_flush), .memory_abort_o(memory_abort),
    .cfg_table_base_o(cfg_table_base), .cfg_arena_bytes_o(cfg_arena_bytes), .status_i(status),
    .awaddr_o(s_axi_awaddr), .araddr_o(s_axi_araddr), .awvalid_o(s_axi_awvalid),
    .wvalid_o(s_axi_wvalid), .arvalid_o(s_axi_arvalid), .awready_i(s_axi_awready),
    .wready_i(s_axi_wready), .arready_i(s_axi_arready), .wdata_o(s_axi_wdata),
    .wstrb_o(s_axi_wstrb), .bresp_i(s_axi_bresp), .rresp_i(s_axi_rresp),
    .bvalid_i(s_axi_bvalid), .rvalid_i(s_axi_rvalid), .rdata_i(s_axi_rdata),
    .bready_o(s_axi_bready), .rready_o(s_axi_rready), .uart_tx_o(uart_tx_o));
  pa_m6_soc u_soc(
"""
    text += ",\n".join(f"    .{name}({'rst_ni' if name == 's_axi_aresetn' else name})"
                        for _, _, name in ports)
    text += "\n  );\nendmodule\n"
    out.mkdir()
    (out / "pa_m6_chip_core.sv").write_text(text)
    paths = [source / name for name in ("portable.v", "pa_m6_soc.sv", "pa_m6_clocking.sv")]
    paths += [ROOT / "asic/m6/rtl" / name for name in
              ("pa_m6_spi.sv", "pa_m6_host.sv", "pa_m6_uart_tx.sv")]
    for path in paths: shutil.copyfile(path, out / path.name)
    manifest = dict(status="STAGED_DIGITAL_CHIP_CORE_NOT_PAD_QUALIFICATION",
        external_memory="unchanged native 32-bit AXI; external controller and RAM required",
        sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        generated_sha256=hashlib.sha256(text.encode()).hexdigest())
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print("M6 DIGITAL CHIP CORE STAGED; serial control/UART plus full native-AXI core")


if __name__ == "__main__": main()
