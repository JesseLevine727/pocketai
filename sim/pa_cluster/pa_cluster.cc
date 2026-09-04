// PocketAI-T M1b cluster testbench (Verilator cc mode)
//
// Sequence:
//   0. Load the cluster ELF into RAM (--meminit=ram,FILE).
//   1. Create the active-low reset edge while the clock is low, hold reset
//      across the first four full clock cycles, then release it. This matches
//      the hardware contract while ensuring Verilator observes the async edge.
//   2. Exercise AXI RAM accesses, byte strobes, and unmapped-address errors.
//   3. Let both harts run the CPU checksum and 10,000 interrupt-driven mailbox
//      rounds. Poll their result block through AXI and validate every field.
//   4. Write host acknowledgement only after valid results; hart 1 then sets
//      the console done latch. Drain the same FIFO used by the board runner.
//      Any failed assertion produces a non-zero exit.
#include <cstdint>
#include <cstdio>
#include <string>
#include <utility>

#include "verilated.h"
#include "verilated_toplevel.h"
#include "verilator_memutil.h"

namespace {

// Advance the simulation by one full clock cycle (top must start with
// IO_CLK = 0).  A full cycle (not a single toggle) is required so that
// handshake "accept" clocks always contain a rising edge; flip-flops only
// update on the rising edge, so a single toggle can be a no-op depending on
// phase.
void clock(pa_cluster_top &top) {
  top.IO_CLK = 1;
  top.eval();
  top.IO_CLK = 0;
  top.eval();
}

// Deassert all request channels and give the bridge a couple of idle
// cycles.  Must be called between transactions.
void axi_idle(pa_cluster_top &top) {
  top.awvalid_i = 0;
  top.wvalid_i = 0;
  top.arvalid_i = 0;
  clock(top);
  clock(top);
}

// Drive one request channel until it is accepted: wait until the bridge is
// ready (checked before the clock), then clock the edge that completes the
// handshake and drop the valid.  Returns false on timeout.
// AW channel: returns false on timeout.
bool axi_aw(pa_cluster_top &top, uint32_t addr) {
  top.awaddr_i = addr;
  top.awvalid_i = 1;
  for (int i = 0; i < 50 && !top.awready_o; ++i) {
    clock(top);
  }
  if (!top.awready_o) return false;
  clock(top);  // the edge that accepts the AW
  top.awvalid_i = 0;
  return true;
}

// W channel: returns false on timeout.
bool axi_w(pa_cluster_top &top, uint32_t data, uint8_t strb) {
  top.wdata_i = data;
  top.wstrb_i = strb;
  top.wvalid_i = 1;
  for (int i = 0; i < 50 && !top.wready_o; ++i) {
    clock(top);
  }
  if (!top.wready_o) return false;
  clock(top);  // the edge that accepts the W
  top.wvalid_i = 0;
  return true;
}

// AR channel: returns false on timeout.
bool axi_ar(pa_cluster_top &top, uint32_t addr) {
  top.araddr_i = addr;
  top.arvalid_i = 1;
  for (int i = 0; i < 50 && !top.arready_o; ++i) {
    clock(top);
  }
  if (!top.arready_o) return false;
  clock(top);  // the edge that accepts the AR
  top.arvalid_i = 0;
  return true;
}

// One full-width AXI4-Lite write: AW, W, then B.
bool axi_write(pa_cluster_top &top, uint32_t addr, uint32_t data,
               uint8_t strb = 0xF, uint8_t *resp = nullptr) {
  if (!axi_aw(top, addr)) return false;
  if (!axi_w(top, data, strb)) return false;
  for (int i = 0; i < 50 && !top.bvalid_o; ++i) {
    clock(top);
  }
  if (top.bvalid_o && resp != nullptr) *resp = top.bresp_o;
  // bready_i is held high, so the B response is accepted on the next edge
  // (consumed by the following axi_idle).
  return top.bvalid_o;
}

// One AXI4-Lite read: AR, then R.
bool axi_read(pa_cluster_top &top, uint32_t addr, uint32_t &data,
              uint8_t *resp = nullptr) {
  if (!axi_ar(top, addr)) return false;
  for (int i = 0; i < 50 && !top.rvalid_o; ++i) {
    clock(top);
  }
  bool ok = top.rvalid_o;
  if (ok) {
    data = top.rdata_o;
    if (resp != nullptr) *resp = top.rresp_o;
  }
  // rready_i is held high, so the R response is accepted on the next edge
  // (consumed by the following axi_idle).
  return ok;
}

bool gemm_integration_test(pa_cluster_top &top) {
  // A = {{-128,7,3},{11,-4,127}}, B = {{-1,2},{3,-7},{-2,5}}.
  // Both harts continue executing throughout descriptor, stream, and shared
  // scratchpad transactions, exercising the complete integration seam.
  const uint32_t descriptor[][2] = {
      {0x08, 2}, {0x0c, 2}, {0x10, 3}, {0x14, 0},
      {0x18, 0x1234abcd}, {0x1c, 1}};
  for (const auto &entry : descriptor) {
    uint8_t response = 0xff;
    axi_idle(top);
    if (!axi_write(top, 0x13000 + entry[0], entry[1], 0xf, &response) ||
        response != 0) return false;
  }
  axi_idle(top);
  const uint32_t input[] = {0x00030780, 0x007ffc0b,
                            0x000002ff, 0, 0, 0,
                            0x0000f903, 0, 0, 0,
                            0x000005fe, 0, 0, 0};
  for (unsigned word = 0; word < 14; ++word) {
    top.gemm_s_axis_valid_i = 1;
    top.gemm_s_axis_data_i = input[word];
    top.gemm_s_axis_last_i = word == 13;
    top.eval();
    unsigned wait = 0;
    while (!top.gemm_s_axis_ready_o && wait++ < 1000) clock(top);
    if (!top.gemm_s_axis_ready_o) return false;
    clock(top);
  }
  top.gemm_s_axis_valid_i = 0;
  top.gemm_s_axis_last_i = 0;
  for (unsigned word = 0; word < 16; ++word) {
    top.gemm_m_axis_ready_i = 1;
    top.eval();
    unsigned wait = 0;
    while (!top.gemm_m_axis_valid_o && wait++ < 1000) clock(top);
    const uint32_t expected = word == 0 ? 0xfede008f :
                              word == 8 ? 0x02adfeeb : 0;
    if (!top.gemm_m_axis_valid_o || top.gemm_m_axis_keep_o != 0xf ||
        top.gemm_m_axis_data_o != expected ||
        static_cast<bool>(top.gemm_m_axis_last_o) != (word == 15)) return false;
    clock(top);
    top.gemm_m_axis_ready_i = 0;
    axi_idle(top);
    if (!axi_write(top, 0x4000 + 4 * word, expected)) return false;
    axi_idle(top);
    uint32_t observed = 0;
    if (!axi_read(top, 0x4000 + 4 * word, observed) || observed != expected) {
      return false;
    }
  }
  for (const auto &entry : {std::pair<uint32_t, uint32_t>{0x20, 0x1234abcd},
                           {0x24, 25}, {0x28, 12}, {0x34, 1}, {0x38, 0}}) {
    axi_idle(top);
    uint32_t value = 0;
    if (!axi_read(top, 0x13000 + entry.first, value) || value != entry.second) {
      return false;
    }
  }
  axi_idle(top);
  return true;
}

}  // namespace

int main(int argc, char **argv) {
  pa_cluster_top top;
  VerilatorMemUtil memutil;
  MemArea ram("TOP.pa_cluster_top.u_ram", 64 * 1024 / 4, 4);
  memutil.RegisterMemoryArea("ram", 0x0, &ram);

  Verilated::commandArgs(argc, argv);

  // Load the ELF (--meminit=ram,FILE) before the first clock.
  bool exit_app = false;
  if (!memutil.ParseCLIArguments(argc, argv, exit_app)) {
    return 1;
  }
  if (exit_app) return 0;

  // Establish inputs with reset inactive first so Verilator can observe the
  // subsequent asynchronous high-to-low reset edge. No clock edge occurs
  // while reset is inactive.
  top.IO_CLK = 0;
  top.IO_RST_N = 1;
  top.CORE_RST_N = 1;
  top.awaddr_i = 0;
  top.awvalid_i = 0;
  top.wdata_i = 0;
  top.wstrb_i = 0xF;
  top.wvalid_i = 0;
  top.bready_i = 1;
  top.araddr_i = 0;
  top.arvalid_i = 0;
  top.rready_i = 1;
  top.gemm_s_axis_data_i = 0;
  top.gemm_s_axis_keep_i = 0xf;
  top.gemm_s_axis_last_i = 0;
  top.gemm_s_axis_valid_i = 0;
  top.gemm_m_axis_ready_i = 0;
  top.eval();

  top.IO_RST_N = 0;
  top.CORE_RST_N = 0;
  top.eval();

  // Hold reset for four complete cycles, then release between cycles. No
  // design state observes a rising clock edge without reset having occurred.
  for (int i = 0; i < 4; ++i) {
    clock(top);
  }
  top.IO_RST_N = 1;
  top.CORE_RST_N = 1;

  // AXI4-Lite self-test. Keep this block clear of firmware (< 0x1000), the
  // result block (0xD000), and per-hart stacks (0xE800..0xFFFF).
  const uint32_t kAxAddr0 = 0xC000;
  const uint32_t kAxAddr1 = 0xC004;
  const uint32_t kAxAddr2 = 0xC008;
  const uint32_t kAxData0 = 0xDEADBEEF;
  const uint32_t kAxData1 = 0xCAFEBABE;
  const uint32_t kAxData2 = 0x12345678;
  const uint32_t kAxPartialData = 0xAABBCCDD;
  const uint32_t kAxPartialExpected = 0x12BB56DD;
  const uint32_t kUnmappedAddr = 0x00020000;
  const uint32_t kGemmIdAddr = 0x00013000;
  const uint32_t kGemmCapsAddr = 0x0001303c;
  uint32_t r0 = 0;
  uint32_t r1 = 0;
  uint32_t r2 = 0;
  uint32_t pre = 0;
  uint32_t invalid_data = 0;
  uint8_t invalid_bresp = 0;
  uint8_t invalid_rresp = 0;
  uint32_t gemm_id = 0;
  uint32_t gemm_caps = 0;
  axi_idle(top);
  bool ok_pre = axi_read(top, kAxAddr1, pre);
  axi_idle(top);
  bool ok_w0 = axi_write(top, kAxAddr0, kAxData0);
  axi_idle(top);
  bool ok_w1 = axi_write(top, kAxAddr1, kAxData1);
  axi_idle(top);
  bool ok_w2 = axi_write(top, kAxAddr2, kAxData2);
  axi_idle(top);
  bool ok_wp = axi_write(top, kAxAddr2, kAxPartialData, 0x5);
  axi_idle(top);
  bool ok_r0 = axi_read(top, kAxAddr0, r0);
  axi_idle(top);
  bool ok_r1 = axi_read(top, kAxAddr1, r1);
  axi_idle(top);
  bool ok_r2 = axi_read(top, kAxAddr2, r2);
  axi_idle(top);
  bool ok_bad_w = axi_write(top, kUnmappedAddr, 0, 0xF, &invalid_bresp);
  axi_idle(top);
  bool ok_bad_r = axi_read(top, kUnmappedAddr, invalid_data, &invalid_rresp);
  axi_idle(top);
  bool ok_gemm_id = axi_read(top, kGemmIdAddr, gemm_id);
  axi_idle(top);
  bool ok_gemm_caps = axi_read(top, kGemmCapsAddr, gemm_caps);
  bool axi_ok = ok_pre && ok_w0 && ok_w1 && ok_w2 && ok_wp && ok_r0 && ok_r1 &&
                ok_r2 && ok_bad_w && ok_bad_r && ok_gemm_id && ok_gemm_caps &&
                pre == 0 && r0 == kAxData0 &&
                r1 == kAxData1 && r2 == kAxPartialExpected &&
                invalid_bresp != 0 && invalid_rresp != 0 &&
                gemm_id == 0x50414732 && gemm_caps == 0x03001010;
  std::printf(axi_ok ? "AXI OK\n"
                     : "AXI FAIL pre=%d w0=%d w1=%d w2=%d wp=%d r0=%d r1=%d r2=%d badw=%d badr=%d gid=%d gcaps=%d pre=%08x r0=%08x r1=%08x r2=%08x bresp=%u rresp=%u gemm_id=%08x gemm_caps=%08x\n",
              (int)ok_pre, (int)ok_w0, (int)ok_w1, (int)ok_w2, (int)ok_wp,
              (int)ok_r0, (int)ok_r1, (int)ok_r2, (int)ok_bad_w,
              (int)ok_bad_r, (int)ok_gemm_id, (int)ok_gemm_caps, pre, r0, r1, r2,
              (unsigned)invalid_bresp, (unsigned)invalid_rresp, gemm_id, gemm_caps);

  const bool gemm_ok = gemm_integration_test(top);
  std::puts(gemm_ok ? "M2 CLUSTER GEMM PASS" : "M2 CLUSTER GEMM FAIL");

  // Firmware result block and independent golden values.
  const uint32_t kResultBase = 0x0000D000;
  const uint32_t kDone0Magic = 0x4D314830;
  const uint32_t kDone1Magic = 0x4D314831;
  const uint32_t kHostAckMagic = 0x484F5354;
  const uint32_t kExpectedRounds = 10000;
  const uint32_t kExpectedMsgsum0 = 0x468AAD43;
  const uint32_t kExpectedMsgsum1 = 0x85558C0A;
  const uint32_t kExpectedWork0 = 0x29C4C2C2;
  const uint32_t kExpectedWork1 = 0xA3E316EC;

  bool results_checked = false;
  bool results_ok = false;
  uint64_t guard = 0;
  while (!top.software_done_o && guard < 200000000) {
    for (unsigned i = 0; i < 512 && !top.software_done_o; ++i) {
      clock(top);
      ++guard;
    }
    if (top.software_done_o) break;

    uint32_t done0 = 0;
    uint32_t done1 = 0;
    uint8_t done0_resp = 0xff;
    uint8_t done1_resp = 0xff;
    axi_idle(top);
    bool done0_read = axi_read(top, kResultBase + 0x00, done0, &done0_resp);
    axi_idle(top);
    bool done1_read = axi_read(top, kResultBase + 0x04, done1, &done1_resp);
    if (!done0_read || !done1_read || done0_resp != 0 || done1_resp != 0) {
      std::fprintf(stderr, "result polling AXI failure\n");
      break;
    }

    if (done0 == kDone0Magic && done1 == kDone1Magic) {
      uint32_t values[8] = {};
      bool reads_ok = true;
      for (unsigned i = 0; i < 8; ++i) {
        uint8_t resp = 0xff;
        axi_idle(top);
        reads_ok &= axi_read(top, kResultBase + 0x08 + 4 * i, values[i], &resp);
        reads_ok &= resp == 0;
      }

      // count0, count1, message checksums, workload checksums, error flags.
      results_ok = reads_ok && values[0] == kExpectedRounds &&
                   values[1] == kExpectedRounds &&
                   values[2] == kExpectedMsgsum0 &&
                   values[3] == kExpectedMsgsum1 &&
                   values[4] == kExpectedWork0 &&
                   values[5] == kExpectedWork1 && values[6] == 0 &&
                   values[7] == 0;
      results_checked = true;
      std::printf(results_ok
                      ? "M1 RESULTS OK count0=%u count1=%u msg0=%08x msg1=%08x work0=%08x work1=%08x\n"
                      : "M1 RESULTS FAIL count0=%u count1=%u msg0=%08x msg1=%08x work0=%08x work1=%08x err0=%08x err1=%08x\n",
                  values[0], values[1], values[2], values[3], values[4],
                  values[5], values[6], values[7]);

      uint8_t ack_resp = 0xff;
      axi_idle(top);
      bool ack_ok = axi_write(top, kResultBase + 0x30, kHostAckMagic, 0xF,
                              &ack_resp);
      results_ok &= ack_ok && ack_resp == 0;
      break;
    }
  }

  while (!top.software_done_o && guard < 200000000) {
    clock(top);
    ++guard;
  }
  if (!top.software_done_o) {
    std::fprintf(stderr, "firmware timed out after %llu cycles\n",
                 static_cast<unsigned long long>(guard));
  }

  // Drain and validate the synthesizable console FIFO exactly as the board
  // host does. DATA reads dequeue one byte; STATUS[15:0] is the count.
  std::string console;
  bool console_reads_ok = true;
  for (unsigned reads = 0; reads < 256; ++reads) {
    uint32_t status = 0;
    axi_idle(top);
    if (!axi_read(top, 0x00011004, status) || (status & 0x10000u)) {
      console_reads_ok = false;
      break;
    }
    if ((status & 0xffffu) == 0) break;

    uint32_t data = 0;
    axi_idle(top);
    if (!axi_read(top, 0x00011000, data)) {
      console_reads_ok = false;
      break;
    }
    console.push_back(static_cast<char>(data & 0xffu));
  }

  if (FILE *log = std::fopen("pa_cluster.log", "w")) {
    std::fwrite(console.data(), 1, console.size(), log);
    std::fclose(log);
  } else {
    console_reads_ok = false;
  }

  const bool console_ok = console_reads_ok &&
      console.find("H0 READY\n") != std::string::npos &&
      console.find("H1 READY\n") != std::string::npos;

  return (axi_ok && gemm_ok && results_checked && results_ok && top.software_done_o &&
          console_ok) ? 0 : 1;
}
