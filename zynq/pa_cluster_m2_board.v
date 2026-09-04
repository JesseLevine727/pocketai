// PocketAI-T M2 PYNQ-Z1 wrapper: cluster AXI-Lite plus 32-bit GEMM streams.

module pa_cluster_m2_board #(
  parameter integer C_S_AXI_ADDR_WIDTH = 17,
  parameter integer C_S_AXI_DATA_WIDTH = 32
) (
  (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 S_AXI_ACLK CLK" *)
  (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXI_CTRL:S_AXIS_GEMM:M_AXIS_GEMM, ASSOCIATED_RESET s_axi_aresetn" *)
  input wire s_axi_aclk,
  (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 S_AXI_ARESETN RST" *)
  (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
  input wire s_axi_aresetn,
  (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 CORE_ARESETN RST" *)
  (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
  input wire core_aresetn,

  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI_CTRL AWADDR" *)
  (* X_INTERFACE_PARAMETER = "PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 17, FREQ_HZ 95000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 0, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, SUPPORTS_NARROW_BURST 0" *)
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
  input wire s_axi_rready,

  (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS_GEMM TDATA" *)
  (* X_INTERFACE_PARAMETER = "TDATA_NUM_BYTES 4, HAS_TKEEP 1, HAS_TLAST 1, FREQ_HZ 95000000" *)
  input wire [31:0] s_axis_gemm_tdata,
  (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS_GEMM TKEEP" *)
  input wire [3:0] s_axis_gemm_tkeep,
  (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS_GEMM TLAST" *)
  input wire s_axis_gemm_tlast,
  (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS_GEMM TVALID" *)
  input wire s_axis_gemm_tvalid,
  (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS_GEMM TREADY" *)
  output wire s_axis_gemm_tready,

  (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_GEMM TDATA" *)
  (* X_INTERFACE_PARAMETER = "TDATA_NUM_BYTES 4, HAS_TKEEP 1, HAS_TLAST 1, FREQ_HZ 95000000" *)
  output wire [31:0] m_axis_gemm_tdata,
  (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_GEMM TKEEP" *)
  output wire [3:0] m_axis_gemm_tkeep,
  (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_GEMM TLAST" *)
  output wire m_axis_gemm_tlast,
  (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_GEMM TVALID" *)
  output wire m_axis_gemm_tvalid,
  (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_GEMM TREADY" *)
  input wire m_axis_gemm_tready
);

  wire [31:0] cluster_awaddr =
      {{(32-C_S_AXI_ADDR_WIDTH){1'b0}}, s_axi_awaddr};
  wire [31:0] cluster_araddr =
      {{(32-C_S_AXI_ADDR_WIDTH){1'b0}}, s_axi_araddr};

  pa_cluster_top #(
    .EnableGemm(1'b1)
  ) impl (
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
    .gemm_s_axis_data_i(s_axis_gemm_tdata),
    .gemm_s_axis_keep_i(s_axis_gemm_tkeep),
    .gemm_s_axis_last_i(s_axis_gemm_tlast),
    .gemm_s_axis_valid_i(s_axis_gemm_tvalid),
    .gemm_s_axis_ready_o(s_axis_gemm_tready),
    .gemm_m_axis_data_o(m_axis_gemm_tdata),
    .gemm_m_axis_keep_o(m_axis_gemm_tkeep),
    .gemm_m_axis_last_o(m_axis_gemm_tlast),
    .gemm_m_axis_valid_o(m_axis_gemm_tvalid),
    .gemm_m_axis_ready_i(m_axis_gemm_tready),
    .console_char_valid_o(),
    .console_char_o(),
    .software_done_o()
  );

endmodule
