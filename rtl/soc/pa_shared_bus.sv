// PocketAI-T shared pipelined bus.
//
// Hosts hold req/address/control until gnt. A one-entry input buffer per host
// first captures each request; arbitration and address decode operate only on
// those registers. A second issue register isolates arbitration/decode from
// the device request path. These boundaries prevent a core's decode/execute
// path from propagating through arbitration into another core or a peripheral,
// and keep FPGA block-RAM address paths short. The selected device returns
// rvalid/rdata one cycle after issue. The round-robin pointer advances after
// every grant so instruction traffic cannot starve another host.

module pa_shared_bus #(
  parameter int unsigned NrDevices   = 1,
  parameter int unsigned NrHosts     = 1,
  parameter int unsigned DataWidth   = 32,
  parameter int unsigned AddressWidth = 32
) (
  input  logic                    clk_i,
  input  logic                    rst_ni,

  input  logic                    host_req_i    [NrHosts],
  output logic                    host_gnt_o    [NrHosts],
  input  logic [AddressWidth-1:0] host_addr_i   [NrHosts],
  input  logic                    host_we_i     [NrHosts],
  input  logic [DataWidth/8-1:0]  host_be_i     [NrHosts],
  input  logic [DataWidth-1:0]    host_wdata_i  [NrHosts],
  output logic                    host_rvalid_o [NrHosts],
  output logic [DataWidth-1:0]    host_rdata_o  [NrHosts],
  output logic                    host_err_o    [NrHosts],

  output logic                    device_req_o    [NrDevices],
  output logic [AddressWidth-1:0] device_addr_o   [NrDevices],
  output logic                    device_we_o     [NrDevices],
  output logic [DataWidth/8-1:0]  device_be_o     [NrDevices],
  output logic [DataWidth-1:0]    device_wdata_o  [NrDevices],
  input  logic                    device_rvalid_i [NrDevices],
  input  logic [DataWidth-1:0]    device_rdata_i  [NrDevices],
  input  logic                    device_err_i    [NrDevices],

  input logic [AddressWidth-1:0] cfg_device_addr_base [NrDevices],
  input logic [AddressWidth-1:0] cfg_device_addr_mask [NrDevices]
);

  localparam int unsigned HostSelWidth = NrHosts > 1 ? $clog2(NrHosts) : 1;
  localparam int unsigned DevSelWidth  = NrDevices > 1 ? $clog2(NrDevices) : 1;

  logic [HostSelWidth-1:0] rr_q;
  logic                    pending_q       [NrHosts];
  // One-cycle re-arm guard after issue. A host may legally keep req asserted
  // for a back-to-back transfer, so re-arming must not depend on req going
  // low. The guard merely prevents re-capturing the just-granted request on
  // the grant edge, before the host has advanced its address/control.
  logic                    rearm_q         [NrHosts];
  logic [AddressWidth-1:0] pending_addr_q  [NrHosts];
  logic                    pending_we_q    [NrHosts];
  logic [DataWidth/8-1:0]  pending_be_q    [NrHosts];
  logic [DataWidth-1:0]    pending_wdata_q [NrHosts];

  logic                    arb_valid;
  logic [HostSelWidth-1:0] arb_host;
  logic                    arb_device_valid;
  logic [DevSelWidth-1:0]  arb_device;

  logic                    issue_valid_q;
  logic [HostSelWidth-1:0] issue_host_q;
  logic                    issue_device_valid_q;
  logic [DevSelWidth-1:0]  issue_device_q;
  logic [AddressWidth-1:0] issue_addr_q;
  logic                    issue_we_q;
  logic [DataWidth/8-1:0]  issue_be_q;
  logic [DataWidth-1:0]    issue_wdata_q;

  logic                    resp_valid_q;
  logic [HostSelWidth-1:0] resp_host_q;
  logic [DevSelWidth-1:0]  resp_device_q;
  logic                    resp_decode_err_q;

  always_comb begin
    arb_valid = 1'b0;
    arb_host  = '0;
    for (int unsigned offset = 0; offset < NrHosts; offset++) begin
      int unsigned candidate;
      candidate = int'(rr_q) + offset;
      if (candidate >= NrHosts) candidate = candidate - NrHosts;
      if (!arb_valid && pending_q[candidate]) begin
        arb_valid = 1'b1;
        arb_host  = HostSelWidth'(candidate);
      end
    end
  end

  always_comb begin
    arb_device_valid = 1'b0;
    arb_device       = '0;
    if (arb_valid) begin
      for (int unsigned device = 0; device < NrDevices; device++) begin
        if ((pending_addr_q[arb_host] & cfg_device_addr_mask[device]) ==
            cfg_device_addr_base[device]) begin
          arb_device_valid = 1'b1;
          arb_device       = DevSelWidth'(device);
        end
      end
    end
  end

  always_comb begin
    for (int unsigned host = 0; host < NrHosts; host++) begin
      host_gnt_o[host]    = 1'b0;
      host_rvalid_o[host] = 1'b0;
      host_rdata_o[host]  = '0;
      host_err_o[host]    = 1'b0;
    end

    // A host is granted only when its registered request is actually issued
    // to a device. This preserves the Ibex memory-interface contract even
    // though arbitration happens one cycle earlier.
    if (issue_valid_q) host_gnt_o[issue_host_q] = 1'b1;

    if (resp_valid_q) begin
      host_rvalid_o[resp_host_q] =
          resp_decode_err_q | device_rvalid_i[resp_device_q];
      host_rdata_o[resp_host_q] = device_rdata_i[resp_device_q];
      host_err_o[resp_host_q] =
          resp_decode_err_q | device_err_i[resp_device_q];
    end
  end

  always_comb begin
    for (int unsigned device = 0; device < NrDevices; device++) begin
      device_req_o[device]   = 1'b0;
      device_addr_o[device]  = '0;
      device_we_o[device]    = 1'b0;
      device_be_o[device]    = '0;
      device_wdata_o[device] = '0;
    end

    if (issue_valid_q && issue_device_valid_q) begin
      device_req_o[issue_device_q]   = 1'b1;
      device_addr_o[issue_device_q]  = issue_addr_q;
      device_we_o[issue_device_q]    = issue_we_q;
      device_be_o[issue_device_q]    = issue_be_q;
      device_wdata_o[issue_device_q] = issue_wdata_q;
    end
  end

  // Keep this reset synchronous. These pipeline registers feed the inferred
  // scratchpad BRAM address/control pins; asynchronous controls in that cone
  // trigger REQP-1839 and can make reset assertion corrupt a BRAM access.
  // Other blocks intentionally consume rst_ni asynchronously, so suppress
  // the mixed-reset-net warning only around this reviewed exception.
  /* verilator lint_off SYNCASYNCNET */
  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      rr_q              <= '0;
      issue_valid_q     <= 1'b0;
      issue_host_q      <= '0;
      issue_device_valid_q <= 1'b0;
      issue_device_q    <= '0;
      issue_addr_q      <= '0;
      issue_we_q        <= 1'b0;
      issue_be_q        <= '0;
      issue_wdata_q     <= '0;
      resp_valid_q      <= 1'b0;
      resp_host_q       <= '0;
      resp_device_q     <= '0;
      resp_decode_err_q <= 1'b0;
      for (int unsigned host = 0; host < NrHosts; host++) begin
        pending_q[host]       <= 1'b0;
        rearm_q[host]         <= 1'b0;
        pending_addr_q[host]  <= '0;
        pending_we_q[host]    <= 1'b0;
        pending_be_q[host]    <= '0;
        pending_wdata_q[host] <= '0;
      end
    end else begin
      issue_valid_q        <= arb_valid;
      issue_host_q         <= arb_host;
      issue_device_valid_q <= arb_device_valid;
      issue_device_q       <= arb_device;
      if (arb_valid) begin
        issue_addr_q  <= pending_addr_q[arb_host];
        issue_we_q    <= pending_we_q[arb_host];
        issue_be_q    <= pending_be_q[arb_host];
        issue_wdata_q <= pending_wdata_q[arb_host];
      end

      resp_valid_q      <= issue_valid_q;
      resp_host_q       <= issue_host_q;
      resp_device_q     <= issue_device_q;
      resp_decode_err_q <= issue_valid_q & ~issue_device_valid_q;

      if (arb_valid) begin
        rr_q <= arb_host == HostSelWidth'(NrHosts - 1)
                    ? '0
                    : arb_host + HostSelWidth'(1);
      end

      for (int unsigned host = 0; host < NrHosts; host++) begin
        if (rearm_q[host]) rearm_q[host] <= 1'b0;
        if (arb_valid && arb_host == HostSelWidth'(host)) begin
          pending_q[host] <= 1'b0;
          rearm_q[host]   <= 1'b1;
        end else if (!pending_q[host] && !rearm_q[host] && host_req_i[host]) begin
          pending_q[host]       <= 1'b1;
          pending_addr_q[host]  <= host_addr_i[host];
          pending_we_q[host]    <= host_we_i[host];
          pending_be_q[host]    <= host_be_i[host];
          pending_wdata_q[host] <= host_wdata_i[host];
        end
      end
    end
  end
  /* verilator lint_on SYNCASYNCNET */

endmodule
