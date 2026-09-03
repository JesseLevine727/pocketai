// PocketAI-T M1b cluster testbench (Verilator cc mode)
//
// Sequence (IMPORTANT -- see the reset note in pa_cluster_top.sv):
//   0. Load the cluster ELF into RAM (--meminit=ram,FILE).
//   1. Clock a few cycles with IO_RST_N released (reset must never be
//      asserted before the first clock edge in this Verilator build),
//      apply a short reset, and release.
//   2. Run the AXI4-Lite self-test through the slave port (two word writes
//      to RAM at 0xF000/0xF004 plus a read-back) while the firmware boots;
//      the firmware never touches those words.  Print "AXI OK" / "AXI FAIL".
//   3. The sim ends when the firmware writes the halt register ($finish in
//      the UART ctrl register).  Exit code is non-zero if the AXI self-test
//      failed or the sim did not finish.  The UART capture lands in
//      pa_cluster.log.
#include <cstdint>
#include <cstdio>

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
bool axi_w(pa_cluster_top &top, uint32_t data) {
  top.wdata_i = data;
  top.wstrb_i = 0xF;
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
bool axi_write(pa_cluster_top &top, uint32_t addr, uint32_t data) {
  if (!axi_aw(top, addr)) return false;
  if (!axi_w(top, data)) return false;
  for (int i = 0; i < 50 && !top.bvalid_o; ++i) {
    clock(top);
  }
  // bready_i is held high, so the B response is accepted on the next edge
  // (consumed by the following axi_idle).
  return top.bvalid_o;
}

// One AXI4-Lite read: AR, then R.
bool axi_read(pa_cluster_top &top, uint32_t addr, uint32_t &data) {
  if (!axi_ar(top, addr)) return false;
  for (int i = 0; i < 50 && !top.rvalid_o; ++i) {
    clock(top);
  }
  bool ok = top.rvalid_o;
  if (ok) data = top.rdata_o;
  // rready_i is held high, so the R response is accepted on the next edge
  // (consumed by the following axi_idle).
  return ok;
}

}  // namespace

int main(int argc, char **argv) {
  pa_cluster_top top;
  VerilatorMemUtil memutil;
  MemArea ram("TOP.pa_cluster_top.u_ram.u_ram", 64 * 1024 / 4, 4);
  memutil.RegisterMemoryArea("ram", 0x0, &ram);

  Verilated::commandArgs(argc, argv);

  // Load the ELF (--meminit=ram,FILE) before the first clock.
  bool exit_app = false;
  if (!memutil.ParseCLIArguments(argc, argv, exit_app)) {
    return 1;
  }
  if (exit_app) return 0;

  // Reset policy: IO_RST_N is released before the first clock edge (see
  // the reset note in pa_cluster_top.sv).  The AXI slave port is idle-ready
  // throughout.
  top.IO_CLK = 0;
  top.IO_RST_N = 1;             // released from the start (Verilator rule)
  top.awaddr_i = 0;
  top.awvalid_i = 0;
  top.wdata_i = 0;
  top.wstrb_i = 0xF;
  top.wvalid_i = 0;
  top.bready_i = 1;
  top.araddr_i = 0;
  top.arvalid_i = 0;
  top.rready_i = 1;
  top.eval();

  // A few idle cycles, then a short SoC reset (safe: never asserted before
  // the first clock edge), then release.
  for (int i = 0; i < 2; ++i) {
    clock(top);
  }
  top.IO_RST_N = 0;
  for (int i = 0; i < 4; ++i) {
    clock(top);
  }
  top.IO_RST_N = 1;

  // AXI4-Lite self-test: write two words to RAM through the slave port and
  // read them back.  The addresses must stay inside the 64 KB RAM (ram_1p
  // is a plain array indexed by addr[14:2] and the bus performs no bounds
  // check), and clear of the code (< 0x1000) and the stacks (hart 1's sp
  // starts at 0xE800).
  const uint32_t kAxAddr0 = 0xF000;
  const uint32_t kAxAddr1 = 0xF004;
  const uint32_t kAxAddr2 = 0xF008;
  const uint32_t kAxData0 = 0xDEADBEEF;
  const uint32_t kAxData1 = 0xCAFEBABE;
  const uint32_t kAxData2 = 0x12345678;
  uint32_t r0 = 0;
  uint32_t r1 = 0;
  uint32_t r2 = 0;
  uint32_t pre = 0;
  axi_idle(top);
  bool ok_pre = axi_read(top, kAxAddr1, pre);
  axi_idle(top);
  bool ok_w0 = axi_write(top, kAxAddr0, kAxData0);
  axi_idle(top);
  bool ok_w1 = axi_write(top, kAxAddr1, kAxData1);
  axi_idle(top);
  bool ok_w2 = axi_write(top, kAxAddr2, kAxData2);
  axi_idle(top);
  bool ok_r0 = axi_read(top, kAxAddr0, r0);
  axi_idle(top);
  bool ok_r1 = axi_read(top, kAxAddr1, r1);
  axi_idle(top);
  bool ok_r2 = axi_read(top, kAxAddr2, r2);
  bool axi_ok = ok_pre && ok_w0 && ok_w1 && ok_w2 && ok_r0 && ok_r1 && ok_r2 &&
                pre == 0 && r0 == kAxData0 && r1 == kAxData1 && r2 == kAxData2;
  std::printf(axi_ok ? "AXI OK\n"
                     : "AXI FAIL pre=%d w0=%d w1=%d w2=%d r0=%d r1=%d r2=%d pre=%08x r0=%08x r1=%08x r2=%08x\n",
              (int)ok_pre, (int)ok_w0, (int)ok_w1, (int)ok_w2,
              (int)ok_r0, (int)ok_r1, (int)ok_r2,
              pre, r0, r1, r2);

  // The firmware boots (in parallel with the AXI self-test) and runs the
  // ping-pong test.
  for (unsigned guard = 0; !Verilated::gotFinish(); ++guard) {
    clock(top);
    if (guard > 100000000) {
      std::fprintf(stderr, "simulation timed out\n");
      break;
    }
  }

  return (axi_ok && Verilated::gotFinish()) ? 0 : 1;
}
