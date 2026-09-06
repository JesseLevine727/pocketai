// PocketAI-T M5 PYNQ-Z1 wrapper: protected controls plus autonomous DDR master.
module pa_cluster_m5_board #(
  parameter integer C_S_AXI_ADDR_WIDTH = 17,
  parameter integer C_S_AXI_DATA_WIDTH = 32
) (
  (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 S_AXI_ACLK CLK" *)
  (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi:m_axi, ASSOCIATED_RESET s_axi_aresetn" *)
  input wire s_axi_aclk,
  (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 S_AXI_ARESETN RST" *)
  (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
  input wire s_axi_aresetn,
  input wire cluster_aresetn,
  input wire core_aresetn,
  input wire cfg_enable,
  input wire [31:0] cfg_table_base,
  input wire [31:0] cfg_arena_bytes,
  input wire cfg_flush,
  input wire memory_abort,
  output wire [7:0] status,

  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWADDR" *)
  (* X_INTERFACE_PARAMETER = "PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 17, FREQ_HZ 91000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 0, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, SUPPORTS_NARROW_BURST 0" *)
  input wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
  input wire s_axi_awvalid,
  output wire s_axi_awready,
  input wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_wdata,
  input wire [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
  input wire s_axi_wvalid,
  output wire s_axi_wready,
  output wire [1:0] s_axi_bresp,
  output wire s_axi_bvalid,
  input wire s_axi_bready,
  input wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,
  input wire s_axi_arvalid,
  output wire s_axi_arready,
  output wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_rdata,
  output wire [1:0] s_axi_rresp,
  output wire s_axi_rvalid,
  input wire s_axi_rready,

  (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 m_axi AWADDR" *)
  (* X_INTERFACE_PARAMETER = "PROTOCOL AXI4, DATA_WIDTH 32, ADDR_WIDTH 32, ID_WIDTH 1, FREQ_HZ 91000000, HAS_BURST 1, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 1, HAS_QOS 0, HAS_REGION 0, SUPPORTS_NARROW_BURST 0, MAX_BURST_LENGTH 256, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1" *)
  output wire [31:0] m_axi_awaddr,
  output wire [7:0] m_axi_awlen,
  output wire [2:0] m_axi_awsize,
  output wire [1:0] m_axi_awburst,
  output wire [3:0] m_axi_awcache,
  output wire [2:0] m_axi_awprot,
  output wire m_axi_awid,
  output wire m_axi_awvalid,
  input wire m_axi_awready,
  output wire [31:0] m_axi_wdata,
  output wire [3:0] m_axi_wstrb,
  output wire m_axi_wlast,
  output wire m_axi_wvalid,
  input wire m_axi_wready,
  input wire [1:0] m_axi_bresp,
  input wire m_axi_bid,
  input wire m_axi_bvalid,
  output wire m_axi_bready,
  output wire [31:0] m_axi_araddr,
  output wire [7:0] m_axi_arlen,
  output wire [2:0] m_axi_arsize,
  output wire [1:0] m_axi_arburst,
  output wire [3:0] m_axi_arcache,
  output wire [2:0] m_axi_arprot,
  output wire m_axi_arid,
  output wire m_axi_arvalid,
  input wire m_axi_arready,
  input wire [31:0] m_axi_rdata,
  input wire [1:0] m_axi_rresp,
  input wire m_axi_rid,
  input wire m_axi_rlast,
  input wire m_axi_rvalid,
  output wire m_axi_rready
);
  wire memory_busy, memory_quiesced, memory_poisoned, transfer_cancel;
  wire software_done, flush_ready;
  wire [31:0] cluster_awaddr = {{(32-C_S_AXI_ADDR_WIDTH){1'b0}}, s_axi_awaddr};
  wire [31:0] cluster_araddr = {{(32-C_S_AXI_ADDR_WIDTH){1'b0}}, s_axi_araddr};
  assign status = {2'b0, software_done, transfer_cancel, memory_poisoned,
                   memory_quiesced, memory_busy, flush_ready};

  pa_m5_cluster_top #(.EnableGemm(1'b1), .EnableSfpu(1'b1), .EnableTransfer(1'b1)) impl (
    .IO_CLK(s_axi_aclk), .IO_RST_N(s_axi_aresetn && cluster_aresetn),
    .CORE_RST_N(core_aresetn),
    .awaddr_i(cluster_awaddr), .awvalid_i(s_axi_awvalid), .awready_o(s_axi_awready),
    .wdata_i(s_axi_wdata), .wstrb_i(s_axi_wstrb), .wvalid_i(s_axi_wvalid),
    .wready_o(s_axi_wready), .bresp_o(s_axi_bresp), .bvalid_o(s_axi_bvalid),
    .bready_i(s_axi_bready), .araddr_i(cluster_araddr), .arvalid_i(s_axi_arvalid),
    .arready_o(s_axi_arready), .rdata_o(s_axi_rdata), .rresp_o(s_axi_rresp),
    .rvalid_o(s_axi_rvalid), .rready_i(s_axi_rready),
    .gemm_s_axis_data_i(32'b0), .gemm_s_axis_keep_i(4'b0),
    .gemm_s_axis_last_i(1'b0), .gemm_s_axis_valid_i(1'b0),
    .gemm_s_axis_ready_o(), .gemm_m_axis_data_o(), .gemm_m_axis_keep_o(),
    .gemm_m_axis_last_o(), .gemm_m_axis_valid_o(), .gemm_m_axis_ready_i(1'b0),
    .console_char_valid_o(), .console_char_o(), .software_done_o(software_done),
    .cfg_enable_i(cfg_enable), .cfg_table_base_i(cfg_table_base),
    .cfg_arena_bytes_i(cfg_arena_bytes), .cfg_flush_i(cfg_flush),
    .flush_ready_o(flush_ready), .memory_abort_i(memory_abort),
    .memory_busy_o(memory_busy), .memory_quiesced_o(memory_quiesced),
    .memory_poisoned_o(memory_poisoned), .transfer_cancel_o(transfer_cancel),
    .bulk_busy_i(1'b0), .bulk_req_valid_i(1'b0), .bulk_req_ready_o(),
    .bulk_req_addr_i(32'b0), .bulk_req_words_i(9'b0), .bulk_req_write_i(1'b0),
    .bulk_in_valid_i(1'b0), .bulk_in_ready_o(), .bulk_in_data_i(32'b0),
    .bulk_in_strb_i(4'b0), .bulk_out_valid_o(), .bulk_out_ready_i(1'b0),
    .bulk_out_data_o(), .bulk_out_last_o(), .bulk_done_valid_o(),
    .bulk_done_ready_i(1'b0), .bulk_done_fault_o(),
    .m_awaddr_o(m_axi_awaddr), .m_awlen_o(m_axi_awlen), .m_awsize_o(m_axi_awsize),
    .m_awburst_o(m_axi_awburst), .m_awcache_o(m_axi_awcache),
    .m_awprot_o(m_axi_awprot), .m_awid_o(m_axi_awid), .m_awvalid_o(m_axi_awvalid),
    .m_awready_i(m_axi_awready), .m_wdata_o(m_axi_wdata), .m_wstrb_o(m_axi_wstrb),
    .m_wlast_o(m_axi_wlast), .m_wvalid_o(m_axi_wvalid), .m_wready_i(m_axi_wready),
    .m_bresp_i(m_axi_bresp), .m_bid_i(m_axi_bid), .m_bvalid_i(m_axi_bvalid),
    .m_bready_o(m_axi_bready), .m_araddr_o(m_axi_araddr), .m_arlen_o(m_axi_arlen),
    .m_arsize_o(m_axi_arsize), .m_arburst_o(m_axi_arburst),
    .m_arcache_o(m_axi_arcache), .m_arprot_o(m_axi_arprot), .m_arid_o(m_axi_arid),
    .m_arvalid_o(m_axi_arvalid), .m_arready_i(m_axi_arready),
    .m_rdata_i(m_axi_rdata), .m_rresp_i(m_axi_rresp), .m_rid_i(m_axi_rid),
    .m_rlast_i(m_axi_rlast), .m_rvalid_i(m_axi_rvalid), .m_rready_o(m_axi_rready)
  );
endmodule
