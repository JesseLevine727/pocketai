// M5 device-virtual DDR translation, ABI v1. See docs/M5_ARCHITECTURE.md.
// This module is not an AXI master: its table-read port is serviced by the
// separately qualified memory bridge. Missing responses keep busy asserted.
module pa_m5_page_translate #(
  parameter int unsigned CacheEntries = 16
) (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        cfg_enable_i,
  input  logic [31:0] cfg_table_base_i,
  input  logic [31:0] cfg_arena_bytes_i,
  input  logic        cfg_flush_i,
  output logic        flush_ready_o,

  input  logic        req_valid_i,
  output logic        req_ready_o,
  input  logic [31:0] req_addr_i,
  input  logic [ 8:0] req_words_i,
  input  logic        req_write_i,
  output logic        rsp_valid_o,
  input  logic        rsp_ready_i,
  output logic [31:0] rsp_addr_o,
  output logic [ 3:0] rsp_fault_o,
  output logic        busy_o,

  output logic        table_req_valid_o,
  input  logic        table_req_ready_i,
  output logic [31:0] table_req_addr_o,
  input  logic        table_rsp_valid_i,
  input  logic [31:0] table_rsp_data_i,
  input  logic        table_rsp_error_i
);
  localparam logic [31:0] ArenaBase = 32'h40000000;
  localparam logic [31:0] MaxArenaBytes = 32'h10000000;
  localparam int unsigned CacheIndexWidth = $clog2(CacheEntries);
  typedef enum logic [2:0] {Idle, Check, TableSend, TableWait, Decode, Respond} state_e;
  state_e state_q;
  logic enabled_q, write_q;
  logic [31:0] root_q, size_q, addr_q, pte_q, translated_q;
  logic [8:0] words_q;
  logic [15:0] page_q;
  logic [3:0] fault_q;
  logic [CacheEntries-1:0] cache_valid_q;
  logic [15:0] cache_tag_q [CacheEntries];
  logic [31:0] cache_pte_q [CacheEntries];
  logic [CacheIndexWidth-1:0] cache_index;
  logic [32:0] arena_end, request_end, table_end;
  logic [12:0] page_end;
  logic [3:0] request_fault, pte_fault;

  initial begin
    assert (CacheEntries >= 2 && CacheEntries <= 256 &&
            (CacheEntries & (CacheEntries - 1)) == 0);
  end

  assign cache_index = page_q[CacheIndexWidth-1:0];
  assign arena_end = {1'b0, ArenaBase} + {1'b0, size_q};
  assign request_end = {1'b0, addr_q} + ({24'b0, words_q} << 2);
  assign table_end = {1'b0, root_q} + ({1'b0, size_q} >> 10);
  assign page_end = {1'b0, addr_q[11:0]} + {2'b0, words_q, 2'b0};

  always_comb begin
    request_fault = 0;
    if (!enabled_q) request_fault = 1;
    else if (size_q == 0 || size_q > MaxArenaBytes || size_q[11:0] != 0 ||
             root_q[1:0] != 0 || table_end > 33'h100000000) request_fault = 2;
    else if (words_q == 0 || words_q > 256 || addr_q < ArenaBase ||
             {1'b0, addr_q} >= arena_end || request_end > arena_end) request_fault = 3;
    else if (addr_q[1:0] != 0) request_fault = 4;
    else if (page_end > 4096) request_fault = 5;

    pte_fault = 0;
    if (!pte_q[0]) pte_fault = 6;
    else if (pte_q[11:2] != 0) pte_fault = 8;
    else if (write_q && !pte_q[1]) pte_fault = 7;
  end

  assign req_ready_o = state_q == Idle && !cfg_flush_i;
  assign flush_ready_o = state_q == Idle;
  assign rsp_valid_o = state_q == Respond;
  assign rsp_addr_o = translated_q;
  assign rsp_fault_o = fault_q;
  assign busy_o = state_q != Idle;
  assign table_req_valid_o = state_q == TableSend;
  assign table_req_addr_o = root_q + {14'b0, page_q, 2'b0};

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      state_q <= Idle;
      enabled_q <= 0;
      write_q <= 0;
      root_q <= 0;
      size_q <= 0;
      addr_q <= 0;
      words_q <= 0;
      page_q <= 0;
      pte_q <= 0;
      translated_q <= 0;
      fault_q <= 0;
      cache_valid_q <= '0;
    end else begin
      case (state_q)
        Idle: begin
          if (cfg_flush_i) begin
            cache_valid_q <= '0;
          end else if (req_valid_i) begin
            enabled_q <= cfg_enable_i;
            root_q <= cfg_table_base_i;
            size_q <= cfg_arena_bytes_i;
            addr_q <= req_addr_i;
            words_q <= req_words_i;
            write_q <= req_write_i;
            page_q <= 16'((req_addr_i - ArenaBase) >> 12);
            translated_q <= 0;
            fault_q <= 0;
            state_q <= Check;
          end
        end
        Check: begin
          if (request_fault != 0) begin
            fault_q <= request_fault;
            state_q <= Respond;
          end else if (cache_valid_q[cache_index] && cache_tag_q[cache_index] == page_q) begin
            pte_q <= cache_pte_q[cache_index];
            state_q <= Decode;
          end else begin
            state_q <= TableSend;
          end
        end
        TableSend: begin
          if (table_req_ready_i) state_q <= TableWait;
        end
        TableWait: begin
          if (table_rsp_valid_i) begin
            if (table_rsp_error_i) begin
              fault_q <= 9;
              state_q <= Respond;
            end else begin
              pte_q <= table_rsp_data_i;
              state_q <= Decode;
            end
          end
        end
        Decode: begin
          fault_q <= pte_fault;
          if (pte_fault == 0) begin
            translated_q <= {pte_q[31:12], addr_q[11:0]};
            cache_valid_q[cache_index] <= 1;
            cache_tag_q[cache_index] <= page_q;
            cache_pte_q[cache_index] <= pte_q;
          end
          state_q <= Respond;
        end
        Respond: begin
          if (rsp_ready_i) state_q <= Idle;
        end
        default: state_q <= Idle;
      endcase
    end
  end
endmodule
