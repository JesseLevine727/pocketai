#include "Vpa_m5_transfer_control.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <string>

static void require(bool ok, const std::string &why) { if (!ok) throw std::runtime_error(why); }
class ControlTest {
 public:
  Vpa_m5_transfer_control top;
  std::array<uint32_t, 10> staging{}, owned{};
  uint32_t accepted = 0, completed = 0, rejected = 0, accesses = 0;
  bool ready = true, busy = false, done = false, stopped = false, fatal = false, abort = false;
  uint32_t tag = 0, sent = 0, received = 0;
  unsigned fault = 0;
  ControlTest() {
    top.clk_i = 0; top.req_i = top.we_i = 0; top.addr_i = top.wdata_i = 0; top.be_i = 0;
    top.rst_ni = 0; tick(); tick(); top.rst_ni = 1; tick();
  }
  void tick() {
    top.abort_i = abort; top.cmd_ready_i = ready; top.busy_i = busy;
    top.done_valid_i = done; top.stopped_i = stopped; top.fault_abort_i = fatal;
    top.tag_i = tag; top.fault_i = fault; top.sent_words_i = sent; top.received_words_i = received;
    top.clk_i = 0; top.eval();
    const bool start = top.rst_ni && top.cmd_valid_o;
    const bool ack = top.rst_ni && top.done_ready_o;
    if (start) {
      require(ready && !abort && !top.abort_request_o, "publication without credit");
      for (unsigned i = 0; i < 3; ++i) {
        require(top.cmd_src_addr_o[i] == staging[2*i] && top.cmd_src_words_o[i] == staging[2*i+1], "partial source descriptor publication");
      }
      require(top.cmd_dst_addr_o == staging[6] && top.cmd_dst_words_o == staging[7] &&
        top.cmd_tag_o == staging[8] && top.cmd_deadline_o == staging[9], "partial destination/metadata publication");
      owned = staging;
    }
    if (ack) require(done, "ack without a real completion");
    top.clk_i = 1; top.eval();
    if (start) { ready = false; busy = true; tag = owned[8]; sent = received = fault = 0; ++accepted; }
    if (ack) { done = false; busy = false; ready = true; }
    top.clk_i = 0; top.eval();
  }
  uint32_t access(uint32_t offset, bool writing, uint32_t value, unsigned enables, bool error) {
    top.req_i = 1; top.we_i = writing; top.addr_i = 0x15000 + offset; top.wdata_i = value; top.be_i = enables;
    tick();
    require(top.rvalid_o && bool(top.err_o) == error,
      "MMIO response mismatch offset=" + std::to_string(offset) + " expected_error=" + std::to_string(error));
    uint32_t result = top.rdata_o; ++accesses;
    if (error) ++rejected;
    else if (writing && offset >= 8 && offset <= 0x2c) {
      auto &word = staging[(offset - 8) / 4];
      for (unsigned i = 0; i < 4; ++i) if (enables & (1u << i)) {
        const uint32_t mask = 255u << (8*i); word = (word & ~mask) | (value & mask);
      }
    }
    top.req_i = 0; tick(); require(!top.rvalid_o && !top.err_o, "MMIO response stretched beyond one clock");
    return result;
  }
  void write(uint32_t offset, uint32_t value, unsigned enables = 15, bool error = false) { access(offset, true, value, enables, error); }
  uint32_t read(uint32_t offset, bool error = false) { return access(offset, false, 0, 0, error); }
  void complete(unsigned packet_fault) {
    require(busy && !done, "test completed an unowned command");
    sent = owned[1] + owned[3] + owned[5]; received = owned[7]; fault = packet_fault;
    done = true; ++completed; tick();
  }
  void check_counters() {
    require(read(0x50) == accepted && read(0x54) == completed && read(0x58) == rejected, "MMIO event accounting");
  }
};

int main() {
  try {
    ControlTest sim;
    require(sim.read(0) == 0x50415435 && sim.read(0x48) == 1 && sim.read(0x5c) == 0x00030101, "ID/version/capabilities");
    require(sim.read(4) == 1 && !sim.top.irq_o, "reset status");
    uint32_t random = 0x95201234;
    auto rng = [&] { random ^= random << 13; random ^= random >> 17; random ^= random << 5; return random; };
    for (unsigned field = 0; field < 10; ++field)
      for (unsigned mask = 0; mask < 16; ++mask) {
        sim.write(8 + field * 4, rng(), mask);
        require(sim.read(8 + field * 4) == sim.staging[field], "staging byte-enable merge");
      }
    sim.write(0x44, 1);
    for (unsigned iteration = 0; iteration < 200; ++iteration) {
      for (unsigned field = 0; field < 10; ++field) sim.write(8 + field * 4, rng());
      sim.write(0x30, 1);
      require((sim.read(4) & 3) == 2 && !sim.top.irq_o, "running status");
      sim.write(0x30, 1, 15, true);
      require(sim.read(0x4c) == 1 && sim.top.irq_o, "full-credit rejection/IRQ");
      sim.write(0x30, 8); require(!sim.top.irq_o, "rejection IRQ did not clear");
      const auto owned = sim.owned;
      for (unsigned field = 0; field < 10; ++field) sim.write(8 + field * 4, rng(), iteration % 16);
      require(sim.read(0x34) == owned[8] && sim.owned == owned, "staging changed an owned tag/descriptor");
      sim.complete(iteration % 7 == 0 ? 16 : 0);
      require(sim.top.irq_o && (sim.read(4) & 7) == 6 && sim.read(0x38) == sim.fault &&
        sim.read(0x3c) == sim.sent && sim.read(0x40) == sim.received, "completion status/IRQ/results");
      for (unsigned stall = 0; stall < 5; ++stall) sim.tick();
      sim.write(0x30, 8); require(sim.top.irq_o, "clear rejection consumed a completion");
      sim.write(0x30, 2); require(!sim.top.irq_o && (sim.read(4) & 7) == 1, "completion ACK/credit/IRQ");
      sim.write(0x30, 2, 15, true); require(sim.read(0x4c) == 1, "empty completion ACK accepted");
      sim.write(0x30, 8); sim.check_counters();
    }
    for (unsigned mask = 0; mask < 15; ++mask) {
      sim.write(0x30, 1, mask, true); require(sim.read(0x4c) == 2, "partial doorbell accepted");
    }
    for (uint32_t command : {0u, 3u, 5u, 6u, 7u, 9u, 0xffffffffu}) sim.write(0x30, command, 15, true);
    sim.read(0x60, true); sim.write(0x60, 0, 15, true); sim.write(0, 0, 15, true);
    const uint32_t stage0 = sim.read(8);
    sim.write(9, 0, 15, true); require(sim.read(8) == stage0, "unaligned write altered staging");
    sim.write(0x44, 2, 15, true); require(sim.read(0x44) == 1, "reserved IRQ bits altered enable");
    sim.write(0x44, 0); require(!sim.top.irq_o, "IRQ disable");
    sim.write(0x44, 0xffffffff, 0); require(sim.read(0x44) == 0, "zero byte enables altered IRQ");
    sim.abort = true; sim.tick(); sim.write(0x30, 1, 15, true);
    require(!(sim.read(4) & 1), "START ready during external abort");
    sim.abort = false; sim.write(0x30, 8); sim.write(0x44, 1);
    sim.write(0x30, 4); require(sim.top.abort_request_o && !(sim.read(4) & 1), "control abort not latched");
    sim.write(0x30, 8); require(sim.top.abort_request_o, "clear rejection released global abort");
    sim.stopped = true; sim.ready = false; sim.fatal = true; sim.fault = 20; sim.tick();
    require(sim.top.irq_o && (sim.read(4) & 0x38) == 0x38, "stopped/fatal state or IRQ");
    sim.write(0x30, 2, 15, true); sim.write(0x30, 8);
    require(sim.top.irq_o && sim.read(0x38) == 20, "ACK cleared fatal stopped state");
    sim.check_counters();
    std::printf("M5 TRANSFER CONTROL PASS accesses=%u accepted=%u completed=%u rejected=%u byte_enable_cases=160\n",
      sim.accesses, sim.accepted, sim.completed, sim.rejected);
    sim.top.final(); return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "M5 TRANSFER CONTROL FAIL: %s\n", error.what()); return 1;
  }
}
