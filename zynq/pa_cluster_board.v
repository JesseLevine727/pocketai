// PocketAI-T PYNQ-Z1 AXI4-Lite module-reference wrapper.
//
// Vivado presents addresses relative to the assigned 128 KiB slave segment.
// The cluster therefore sees the same 0x00000..0x1ffff map used in simulation.

module pa_cluster_board #(
  parameter integer C_S_AXI_ADDR_WIDTH = 17,
  parameter integer C_S_AXI_DATA_WIDTH = 32
) (
  (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 S_AXI_ACLK CLK" *)
  (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXI_CTRL, ASSOCIATED_RESET s_axi_aresetn" *)
  input wire s_axi_aclk,
  (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 S_AXI_ARESETN RST" *)
  (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
  input wire s_axi_aresetn,

  (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 CORE_ARESETN RST" *)
  (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
  input wire core_aresetn,

  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL AWADDR" *)
  (* X_INTERFACE_PARAMETER = "PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 17, FREQ_HZ 100000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 0, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, SUPPORTS_NARROW_BURST 0" *)
  input wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL AWVALID" *)
  input wire s_axi_awvalid,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL AWREADY" *)
  output wire s_axi_awready,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL WDATA" *)
  input wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_wdata,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL WSTRB" *)
  input wire [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL WVALID" *)
  input wire s_axi_wvalid,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL WREADY" *)
  output wire s_axi_wready,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL BRESP" *)
  output wire [1:0] s_axi_bresp,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL BVALID" *)
  output wire s_axi_bvalid,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL BREADY" *)
  input wire s_axi_bready,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL ARADDR" *)
  input wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL ARVALID" *)
  input wire s_axi_arvalid,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL ARREADY" *)
  output wire s_axi_arready,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL RDATA" *)
  output wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_rdata,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL RRESP" *)
  output wire [1:0] s_axi_rresp,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL RVALID" *)
  output wire s_axi_rvalid,
  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL RREADY" *)
  input wire s_axi_rready
);

  wire [31:0] cluster_awaddr =
      {{(32-C_S_AXI_ADDR_WIDTH){1'b0}}, s_axi_awaddr};
  wire [31:0] cluster_araddr =
      {{(32-C_S_AXI_ADDR_WIDTH){1'b0}}, s_axi_araddr};

  pa_cluster_top impl (
    .IO_CLK(s_axi_aclk),
    .IO_RST_N(s_axi_aresetn),
    .CORE_RST_N(core_aresetn),
    .awaddr_i(cluster_awaddr),
    .awvalid_i(s_axi_awvalid),
    .awready_o(s_axi_awready),
    .wdata_i(s_axi_wdata),
    .wstrb_i(s_axi_wstrb),
    .wvalid_i(s_axi_wvalid),
    .wready_o(s_axi_wready),
    .bresp_o(s_axi_bresp),
    .bvalid_o(s_axi_bvalid),
    .bready_i(s_axi_bready),
    .araddr_i(cluster_araddr),
    .arvalid_i(s_axi_arvalid),
    .arready_o(s_axi_arready),
    .rdata_o(s_axi_rdata),
    .rresp_o(s_axi_rresp),
    .rvalid_o(s_axi_rvalid),
    .rready_i(s_axi_rready),
    .console_char_valid_o(),
    .console_char_o(),
    .software_done_o()
  );

endmodule
