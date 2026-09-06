#include "Vpa_m5_stream_transfer.h"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool ok, const std::string &message) {
  if (!ok) throw std::runtime_error(message);
}
static uint32_t input_word(uint32_t address) { return address * 0x10201u ^ 0x35a6f081u; }
static uint32_t output_word(uint32_t tag, uint32_t index) { return 0x5d00a55au ^ tag ^ index * 0x10203u; }
struct Descriptor {
  std::array<uint32_t, 3> address{0x40000000, 0, 0}, words{1, 0, 0};
  uint32_t destination = 0x48000000, output_words = 1, tag = 0, deadline = 4000000;
};

class Simulation {
 public:
  Vpa_m5_stream_transfer top;
  uint64_t cycles = 0, commands = 0, sent = 0, received = 0, cases = 0;
  bool external_abort = false, hold_completion = false, hold_command = false;
  bool hold_input_consumer = false, hold_output_producer = false;
  unsigned memory_error = 0, stream_error = 0, memory_protocol_error = 0;
  unsigned error_on_command = 1, packet_commands = 0;
  enum MemoryState { Idle, Read, Write, Finish } memory_state = Idle;
  Descriptor expected;
  uint32_t tx_index = 0, rx_index = 0, write_index = 0;
  std::vector<uint32_t> stored;

  Simulation() { top.clk_i = 0; top.rst_ni = 0; reset(); }
  void reset() {
    require(memory_state == Idle, "reset would discard owned memory");
    external_abort = false; hold_completion = false; hold_command = false;
    hold_input_consumer = false; hold_output_producer = false;
    memory_error = stream_error = memory_protocol_error = 0;
    error_on_command = 1;
    top.cmd_valid_i = 0; top.done_ready_i = 0; top.abort_i = 0;
    top.rst_ni = 0; mem_valid = mem_done = rx_valid = false; output_enabled = false;
    previous_req_stall = previous_tx_stall = previous_done_stall = false;
    for (unsigned i = 0; i < 3; ++i) tick();
    top.rst_ni = 1; tick();
  }

  void submit(const Descriptor &d) {
    require(!top.busy_o && !top.stopped_o && memory_state == Idle, "submit while owned/stopped");
    expected = d; tx_index = rx_index = write_index = 0; tx_segment = tx_segment_index = 0;
    source_segment = source_offset = destination_offset = 0;
    packet_commands = 0;
    stored.clear(); output_enabled = false; rx_valid = false;
    for (unsigned i = 0; i < 3; ++i) { top.cmd_src_addr_i[i] = d.address[i]; top.cmd_src_words_i[i] = d.words[i]; }
    top.cmd_dst_addr_i = d.destination; top.cmd_dst_words_i = d.output_words;
    top.cmd_tag_i = d.tag; top.cmd_deadline_i = d.deadline;
    top.cmd_valid_i = 1; top.eval(); require(top.cmd_ready_o, "idle command not accepted");
    tick(); top.cmd_valid_i = 0;
    // No captured field may be sourced from changing staging pins afterwards.
    for (unsigned i = 0; i < 3; ++i) { top.cmd_src_addr_i[i] = 0xdead0001; top.cmd_src_words_i[i] = 0xffffffff; }
    top.cmd_dst_addr_i = 0; top.cmd_dst_words_i = 0; top.cmd_tag_i = ~d.tag; top.cmd_deadline_i = 0;
    ++cases;
  }

  void tick() {
    require(cycles < 30000000, "global watchdog");
    const bool cancel = external_abort || top.fault_abort_o;
    if (cancel) { mem_valid = false; rx_valid = false; }
    if (!cancel && memory_state == Read && !mem_valid && cycles % 4 != 1) {
      mem_valid = true; mem_data = input_word(mem_address + mem_index * 4);
      mem_last = mem_index + 1 == mem_words;
      if (memory_protocol_error == 1 && mem_index == 0) mem_last = !mem_last;
    }
    if (memory_state == Finish && !mem_done && !hold_completion && cycles % 4 == 0) mem_done = true;
    if (!cancel && memory_state == Finish && !mem_write && memory_protocol_error == 4) {
      mem_valid = true; mem_data = 0xbad00bad; mem_last = false;
    }
    if (!cancel && output_enabled && !hold_output_producer && !rx_valid && rx_index < expected.output_words && cycles % 3 != 1) {
      rx_valid = true; rx_data = output_word(expected.tag, rx_index);
      rx_last = rx_index + 1 == expected.output_words; rx_keep = 15;
      if (stream_error == 1 && rx_index == 0) rx_keep = 7;
      if (stream_error == 2 && rx_index == 0) rx_last = !rx_last;
      if (stream_error == 3 && rx_index + 1 == expected.output_words) rx_last = false;
    }
    top.abort_i = cancel;
    top.mem_req_ready_i = memory_state == Idle && !hold_command && cycles % 5 != 2;
    top.mem_in_ready_i = memory_state == Write && !cancel && cycles % 4 != 0;
    top.mem_out_valid_i = mem_valid; top.mem_out_data_i = mem_data; top.mem_out_last_i = mem_last;
    top.mem_done_valid_i = mem_done; top.mem_done_fault_i = cancel ? 11 : mem_fault;
    top.tx_ready_i = !cancel && !hold_input_consumer && cycles % 5 != 1;
    top.rx_valid_i = rx_valid; top.rx_data_i = rx_data; top.rx_keep_i = rx_keep; top.rx_last_i = rx_last;
    top.clk_i = 0; top.eval();
    if (top.rst_ni) {
      if (previous_req_stall) require(top.mem_req_valid_o && req_address == top.mem_req_addr_o &&
        req_words == top.mem_req_words_o && req_write == bool(top.mem_req_write_o), "request changed under stall/abort");
      if (previous_tx_stall && !cancel) require(top.tx_valid_o && last_tx == top.tx_data_o &&
        last_tx_last == bool(top.tx_last_o) && top.tx_keep_o == 15, "TX changed under backpressure");
      if (previous_done_stall && !cancel) require(top.done_valid_o && top.tag_o == expected.tag &&
        top.fault_o == previous_fault && top.sent_words_o == previous_sent && top.received_words_o == previous_received,
        "completion changed under stall");
    }
    previous_req_stall = top.rst_ni && top.mem_req_valid_o && !top.mem_req_ready_i;
    req_address = top.mem_req_addr_o; req_words = top.mem_req_words_o; req_write = top.mem_req_write_o;
    previous_tx_stall = top.rst_ni && top.tx_valid_o && !top.tx_ready_i;
    last_tx = top.tx_data_o; last_tx_last = top.tx_last_o;
    previous_done_stall = top.rst_ni && top.done_valid_o && !top.done_ready_i;
    previous_fault = top.fault_o; previous_sent = top.sent_words_o; previous_received = top.received_words_o;
    const bool request = top.mem_req_valid_o && top.mem_req_ready_i;
    const bool tx = top.tx_valid_o && top.tx_ready_i, rx = top.rx_valid_i && top.rx_ready_o;
    const bool mr = top.mem_out_valid_i && top.mem_out_ready_o;
    const bool mw = top.mem_in_valid_o && top.mem_in_ready_i;
    const bool md = top.mem_done_valid_i && top.mem_done_ready_o;
    const uint32_t write_data = top.mem_in_data_o;
    if (tx) {
      require(top.tx_keep_o == 15, "input packet TKEEP");
      require(tx_segment < 3 && top.tx_data_o == input_word(expected.address[tx_segment] + tx_segment_index * 4), "source data/order mismatch");
      const uint64_t total = uint64_t(expected.words[0]) + expected.words[1] + expected.words[2];
      require(bool(top.tx_last_o) == (tx_index + 1 == total), "packet TLAST leaked a segment/burst boundary");
      if (top.tx_last_o) output_enabled = true;
    }
    if (mw) require(top.mem_in_strb_o == 15 && write_data == output_word(expected.tag, write_index), "destination data/strobes");
    top.clk_i = 1; top.eval();
    if (top.rst_ni) {
      if (request) {
        require(memory_state == Idle && req_words >= 1 && req_words <= 256 &&
          req_address % 4 == 0 && (req_address & 4095u) + req_words * 4 <= 4096, "illegal/overlapping memory burst");
        uint32_t address, remaining;
        if (req_write) {
          require(output_enabled && tx_index == expected.words[0] + expected.words[1] + expected.words[2], "output requested before all input");
          address = expected.destination + destination_offset * 4;
          remaining = expected.output_words - destination_offset;
        } else {
          require(source_segment < 3 && expected.words[source_segment] != 0, "extra source read");
          address = expected.address[source_segment] + source_offset * 4;
          remaining = expected.words[source_segment] - source_offset;
        }
        const uint32_t wanted = std::min({remaining, 256u, (4096u - (address & 4095u)) / 4u});
        require(req_address == address && req_words == wanted, "memory split/order mismatch");
        mem_address = req_address; mem_words = req_words; mem_index = 0;
        mem_fault = ++packet_commands == error_on_command ? memory_error : 0;
        memory_state = cancel || mem_fault ? Finish : req_write ? Write : Read;
        mem_write = req_write; ++commands;
      }
      if (tx) {
        ++tx_index; ++sent;
        if (++tx_segment_index == expected.words[tx_segment]) { ++tx_segment; tx_segment_index = 0; }
      }
      if (rx) { ++rx_index; ++received; rx_valid = false; }
      if (mr) {
        require(memory_state == Read, "unexpected memory read consumption"); mem_valid = false;
        if (++mem_index == mem_words || memory_protocol_error == 2) memory_state = Finish;
      }
      if (mw) {
        require(memory_state == Write, "unexpected memory write consumption");
        stored.push_back(write_data); ++write_index;
        if (++mem_index == mem_words || memory_protocol_error == 3) memory_state = Finish;
      }
      if (md) {
        require(memory_state == Finish, "completion of unowned memory");
        if (!cancel && !mem_fault) {
          if (mem_write) destination_offset += mem_words;
          else if ((source_offset += mem_words) == expected.words[source_segment]) { ++source_segment; source_offset = 0; }
        }
        memory_state = Idle; mem_done = false;
      }
      if (cancel && memory_state != Idle) { memory_state = Finish; mem_valid = false; }
    }
    ++cycles; top.clk_i = 0; top.eval();
    if (top.stopped_o) require(!top.busy_o && memory_state == Idle && !top.mem_req_valid_o, "false mover drain");
  }

  template <typename Predicate> void until(Predicate predicate, unsigned limit, const char *what) {
    while (!predicate()) {
      require(limit-- != 0, std::string("timeout: ") + what + " case=" + std::to_string(cases) +
        " fault=" + std::to_string(top.fault_o) + " memory_state=" + std::to_string(memory_state) +
        " tx=" + std::to_string(tx_index) + " rx=" + std::to_string(rx_index));
      tick();
    }
  }
  void success(const Descriptor &d, unsigned completion_stall = 3) {
    submit(d); until([&] { return top.done_valid_o || top.stopped_o; }, 4000000, "normal packet");
    require(top.done_valid_o && top.fault_o == 0 && top.tag_o == d.tag, "normal packet fault");
    require(memory_state == Idle && tx_index == d.words[0] + d.words[1] + d.words[2] &&
      rx_index == d.output_words && stored.size() == d.output_words, "normal packet accounting");
    for (unsigned i = 0; i < completion_stall; ++i) tick();
    top.done_ready_i = 1; tick(); top.done_ready_i = 0; tick();
    require(!top.busy_o && top.cmd_ready_o, "normal completion did not release client");
  }
  void rejected(const Descriptor &d) {
    const uint64_t before = commands; submit(d);
    until([&] { return top.done_valid_o || top.stopped_o; }, 10, "bad descriptor");
    require(top.done_valid_o && top.fault_o == 16 && commands == before && tx_index == 0 && rx_index == 0 && !top.fault_abort_o,
      "descriptor rejection had side effects or wrong completion");
    top.done_ready_i = 1; tick(); top.done_ready_i = 0; tick();
  }
  void stopped(unsigned fault) {
    // Some faults occur only on the final accelerator output; include the
    // full 600-word input and 300-word output under independent stalls.
    until([&] { return top.stopped_o; }, 10000, "cancelled packet drain");
    require(top.fault_o == fault && !top.cmd_ready_o && !top.done_valid_o && memory_state == Idle, "stopped fault/ownership mismatch");
    for (unsigned i = 0; i < 10; ++i) tick();
    require(top.stopped_o && !top.cmd_ready_o, "stopped operation silently restarted");
  }

 private:
  bool mem_valid = false, mem_done = false, mem_last = false, mem_write = false;
  uint32_t mem_data = 0, mem_address = 0, mem_words = 0, mem_index = 0, mem_fault = 0;
  bool rx_valid = false, rx_last = false, output_enabled = false;
  uint32_t rx_data = 0, rx_keep = 15;
  uint32_t tx_segment = 0, tx_segment_index = 0, source_segment = 0, source_offset = 0, destination_offset = 0;
  bool previous_req_stall = false, previous_tx_stall = false, previous_done_stall = false;
  bool req_write = false, last_tx_last = false;
  uint32_t req_address = 0, req_words = 0, last_tx = 0, previous_fault = 0, previous_sent = 0, previous_received = 0;
};

int main() {
  try {
    Simulation sim;
    Descriptor d;
    for (uint32_t n = 1; n <= 256; ++n) {
      d.words = {n, 0, 0}; d.output_words = n; d.tag = n;
      d.address = {0x40000000u + ((n * 97) % 1024) * 4, 0, 0};
      d.destination = 0x48000000u + ((n * 67) % 1024) * 4;
      sim.success(d);
    }
    uint32_t random = 0x9520a5;
    auto rng = [&] { random ^= random << 13; random ^= random >> 17; random ^= random << 5; return random; };
    for (unsigned i = 0; i < 80; ++i) {
      for (unsigned s = 0; s < 3; ++s) { d.words[s] = 1 + rng() % 2048; d.address[s] = 0x40000000u + s * 0x100000 + 4 * (rng() % 1024); }
      d.output_words = 1 + rng() % 3072; d.destination = 0x48000000 + 4 * (rng() % 1024); d.tag = rng();
      sim.success(d);
    }
    d.address = {0x40000ffc, 0x41000ffc, 0x42000ffc}; d.words = {10000, 20000, 35535};
    d.output_words = 65535; d.destination = 0x48000ffc; sim.success(d, 100);
    d.words = {3072, 3072, 3072}; d.output_words = 3072; sim.success(d); // SFPU three planes.
    d.words = {12288, 12288, 0}; d.address[2] = 0; d.output_words = 256; sim.success(d); // M=16,K=3072 GEMM.
    d = Descriptor{}; d.address[0] = 0x4ffffffc; d.destination = 0x4ffffffc; sim.success(d);
    for (unsigned bad = 0; bad < 16; ++bad) {
      d = Descriptor{};
      switch (bad) {
        case 0: d.words[0] = 0; break;
        case 1: d.words[0] = 65536; break;
        case 2: d.words = {65535, 1, 0}; d.address[1] = 0x41000000; break;
        case 3: d.words[0] = 0xffffffff; break;
        case 4: d.address[0] |= 1; break;
        case 5: d.address[0] = 0x3ffffffc; break;
        case 6: d.address[0] = 0x4ffffffc; d.words[0] = 2; break;
        case 7: d.address[1] = 0x41000000; break;
        case 8: d.words[2] = 1; d.address[2] = 0x42000000; break;
        case 9: d.output_words = 0; break;
        case 10: d.output_words = 65536; break;
        case 11: d.destination |= 2; break;
        case 12: d.destination = 0x50000000; break;
        case 13: d.destination = 0x4ffffffc; d.output_words = 2; break;
        case 14: d.deadline = 0; break;
        case 15: d.words = {1, 1, 1}; d.address[1] = 0x41000000; d.address[2] = 0x42000002; break;
      }
      sim.rejected(d);
    }
    d = Descriptor{}; d.words[0] = 600; d.output_words = 300;
    for (unsigned fault : {6u, 7u, 9u, 12u})
      for (unsigned command : {1u, 2u, 4u, 5u}) {
        sim.reset(); sim.memory_error = fault; sim.error_on_command = command;
        sim.submit(d); sim.stopped(32 + fault);
      }
    for (unsigned fault = 1; fault <= 3; ++fault) {
      sim.reset(); sim.stream_error = fault; sim.submit(d); sim.stopped(18);
    }
    for (unsigned fault = 1; fault <= 4; ++fault) {
      sim.reset(); sim.memory_protocol_error = fault; sim.submit(d); sim.stopped(19);
    }
    for (unsigned phase = 0; phase < 9; ++phase) {
      sim.reset(); sim.submit(d);
      if (phase == 1) { sim.hold_command = true; sim.until([&] { return sim.top.mem_req_valid_o; }, 100, "stalled memory command"); }
      if (phase == 2) { sim.hold_input_consumer = true; sim.until([&] { return sim.top.tx_valid_o; }, 100, "stalled input packet"); }
      if (phase == 3) sim.until([&] { return sim.tx_index > 20; }, 1000, "partial input packet");
      if (phase == 4) sim.until([&] { return sim.rx_index > 20; }, 10000, "partial output packet");
      if (phase == 5) sim.until([&] { return sim.top.done_valid_o; }, 10000, "pending completion");
      if (phase == 6) sim.until([&] { return sim.rx_index == d.output_words; }, 10000, "last output before memory completion");
      if (phase == 7) sim.until([&] { return sim.tx_index == d.words[0]; }, 10000, "last input before memory completion");
      if (phase == 8) {
        sim.until([&] { return sim.top.mem_req_valid_o && sim.top.mem_req_write_o; }, 10000, "output memory command");
        sim.hold_command = true;
      }
      sim.external_abort = true; sim.hold_completion = true;
      for (unsigned i = 0; i < 32; ++i) sim.tick();
      if (phase != 0 && phase != 5) require(sim.top.busy_o && !sim.top.stopped_o, "abort fabricated memory completion");
      sim.hold_command = false; sim.hold_completion = false; sim.stopped(17);
    }
    sim.reset(); d.deadline = 1; sim.submit(d); sim.stopped(20);
    sim.reset(); d.deadline = 100; sim.hold_completion = true; sim.hold_input_consumer = true; sim.submit(d);
    for (unsigned i = 0; i < 200; ++i) sim.tick();
    require(sim.top.fault_abort_o && sim.top.fault_o == 20 && sim.top.busy_o && !sim.top.stopped_o, "deadline incorrectly claimed drain");
    sim.hold_completion = false; sim.stopped(20);
    sim.reset(); d.deadline = 2500; sim.hold_output_producer = true; sim.submit(d);
    sim.until([&] { return sim.memory_state == Simulation::Write; }, 10000, "accelerator compute wait");
    sim.hold_completion = true;
    sim.until([&] { return sim.top.fault_abort_o; }, 10000, "compute deadline");
    for (unsigned i = 0; i < 32; ++i) sim.tick();
    require(sim.top.busy_o && !sim.top.stopped_o, "compute timeout fabricated memory completion");
    sim.hold_completion = false; sim.stopped(20);
    sim.reset(); sim.success(Descriptor{});
    std::printf("M5 STREAM TRANSFER PASS cases=%llu memory_commands=%llu sent_words=%llu received_words=%llu cycles=%llu\n",
      static_cast<unsigned long long>(sim.cases), static_cast<unsigned long long>(sim.commands),
      static_cast<unsigned long long>(sim.sent), static_cast<unsigned long long>(sim.received), static_cast<unsigned long long>(sim.cycles));
    sim.top.final(); return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "M5 STREAM TRANSFER FAIL: %s\n", error.what()); return 1;
  }
}
