#include <verilated.h>
#include "Vpa_sfpu.h"
#include "Vpa_sfpu___024root.h"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

struct TestCase {
  uint32_t op, length, shift, multiplier, tag, cycles;
  std::vector<uint32_t> input, expected;
};
static uint32_t random_state = 0x53465033;
static uint32_t random32() {
  random_state ^= random_state << 13; random_state ^= random_state >> 17;
  random_state ^= random_state << 5; return random_state;
}
static uint32_t word(std::ifstream& file) {
  uint32_t v = 0; file.read(reinterpret_cast<char*>(&v), 4);
  if (!file) throw std::runtime_error("truncated vector file"); return v;
}
static std::vector<TestCase> vectors(const char* path) {
  std::ifstream file(path, std::ios::binary);
  if (word(file) != 0x33504653) throw std::runtime_error("bad SFPU vector magic");
  const auto count = word(file); random_state = word(file);
  std::vector<TestCase> result;
  for (unsigned i = 0; i < count; ++i) {
    TestCase t{};
    t.op = word(file); t.length = word(file); t.shift = word(file);
    t.multiplier = word(file); t.tag = word(file);
    const auto in = word(file), out = word(file); t.cycles = word(file);
    for (unsigned j = 0; j < in; ++j) t.input.push_back(word(file));
    for (unsigned j = 0; j < out; ++j) t.expected.push_back(word(file));
    result.push_back(t);
  }
  if (file.peek() != std::ifstream::traits_type::eof()) throw std::runtime_error("trailing vector bytes");
  return result;
}

class Harness {
 public:
  Vpa_sfpu dut;
  uint64_t clocks = 0;
  std::set<uint32_t> trace;
  bool recording = false;
  Harness() {
    dut.clk_i = 0; dut.rst_ni = 0; dut.req_i = 0; dut.we_i = 0; dut.be_i = 0;
    dut.addr_i = 0; dut.wdata_i = 0; dut.s_axis_data_i = 0;
    dut.s_axis_keep_i = 15; dut.s_axis_last_i = 0; dut.s_axis_valid_i = 0;
    dut.m_axis_ready_i = 0; dut.gemm_busy_i = 0;
    tick(); tick(); dut.rst_ni = 1; tick();
  }
  ~Harness() { dut.final(); }
  uint32_t key() const {
    const auto* r = dut.rootp;
    const uint32_t shell = r->pa_sfpu__DOT__state_q;
    if (shell != 2 && shell != 3) return shell;
    const uint32_t state = r->pa_sfpu__DOT__u_compute__DOT__state_q;
    uint32_t value = shell | (r->pa_sfpu__DOT__u_compute__DOT__phase_q << 3) | (state << 6);
    if (state == 5 || state == 6) value |=
        (r->pa_sfpu__DOT__u_compute__DOT__return_q << 12) |
        (r->pa_sfpu__DOT__u_compute__DOT__alu_op_q << 18);
    const auto index = r->pa_sfpu__DOT__u_compute__DOT__index_q;
    const auto length = r->pa_sfpu__DOT__length_q;
    const unsigned bucket = index == 0 ? 0 : index + 1 == length ? 2 : 1;
    return value | (bucket << 20);
  }
  void tick() {
    dut.clk_i = 0; dut.eval(); dut.clk_i = 1; dut.eval(); dut.clk_i = 0; dut.eval();
    ++clocks;
    if (recording && dut.busy_o) trace.insert(key());
  }
  void reset() {
    dut.req_i = 0; dut.we_i = 0; dut.s_axis_valid_i = 0; dut.m_axis_ready_i = 0;
    dut.gemm_busy_i = 0; dut.rst_ni = 0; tick(); tick(); dut.rst_ni = 1; tick();
  }
  void write(uint32_t reg, uint32_t data, unsigned be = 15) {
    dut.addr_i = reg; dut.wdata_i = data; dut.be_i = be; dut.we_i = 1; dut.req_i = 1;
    tick(); dut.req_i = 0; dut.we_i = 0; dut.be_i = 0; tick();
  }
  uint32_t read(uint32_t reg) {
    dut.addr_i = reg; dut.we_i = 0; dut.req_i = 1; tick();
    if (!dut.rvalid_o || dut.err_o) throw std::runtime_error("bad MMIO response");
    uint32_t value = dut.rdata_o; dut.req_i = 0; tick(); return value;
  }
  void error(unsigned code) {
    if (read(0x38) != code || !(read(4) & 8)) throw std::runtime_error("wrong sticky SFPU error code=" + std::to_string(code));
  }
  void empty() {
    if (dut.busy_o || dut.m_axis_valid_o || read(4) != 1) throw std::runtime_error("SFPU not empty/clean");
  }
  void stage(const TestCase& t) {
    write(8, t.op); write(12, t.length); write(16, t.shift);
    write(20, t.multiplier); write(24, t.tag);
  }
  void submit(const TestCase& t) {
    stage(t);
    if (read(0x2c) != t.input.size() || read(0x30) != t.expected.size())
      throw std::runtime_error("SFPU staged word-count mismatch");
    write(0x1c, 1);
  }
  void raw(uint32_t data, unsigned keep, bool last) {
    dut.s_axis_data_i = data; dut.s_axis_keep_i = keep; dut.s_axis_last_i = last;
    dut.s_axis_valid_i = 1; dut.eval();
    if (!dut.s_axis_ready_o) throw std::runtime_error("input not ready");
    tick(); dut.s_axis_valid_i = 0; dut.s_axis_last_i = 0;
  }
  void feed(const TestCase& t) {
    size_t index = 0;
    const uint64_t limit = clocks + t.input.size() * 8 + 100;
    bool pending = false;
    while (index < t.input.size()) {
      if (clocks > limit) throw std::runtime_error("SFPU input timeout");
      const bool present = pending || (random32() & 3) != 0;
      dut.s_axis_valid_i = present; dut.s_axis_keep_i = 15;
      dut.s_axis_data_i = t.input[index]; dut.s_axis_last_i = index + 1 == t.input.size();
      dut.eval(); const bool accepted = present && dut.s_axis_ready_o;
      tick(); if (accepted) ++index; pending = present && !accepted;
    }
    dut.s_axis_valid_i = 0; dut.s_axis_last_i = 0;
  }
  void receive(const TestCase& t, unsigned allowed_error = 0) {
    const uint64_t limit = clocks + t.cycles * 3 + t.length * 20 + 1000;
    size_t index = 0;
    bool stalled = false, last = false;
    uint32_t held = 0;
    while (index < t.expected.size()) {
      if (clocks > limit) throw std::runtime_error("SFPU output timeout op=" + std::to_string(t.op));
      dut.m_axis_ready_i = (random32() & 3) != 0; dut.eval();
      if (stalled && (!dut.m_axis_valid_o || dut.m_axis_data_o != held ||
                      bool(dut.m_axis_last_o) != last || dut.m_axis_keep_o != 15))
        throw std::runtime_error("SFPU output changed under backpressure");
      if (dut.m_axis_valid_o && dut.m_axis_ready_i) {
        if (dut.m_axis_keep_o != 15 || bool(dut.m_axis_last_o) != (index + 1 == t.expected.size()))
          throw std::runtime_error("SFPU output framing mismatch");
        if (dut.m_axis_data_o != t.expected[index])
          throw std::runtime_error("SFPU mismatch tag=" + std::to_string(t.tag) +
              " op=" + std::to_string(t.op) + " index=" + std::to_string(index) +
              " got=" + std::to_string(dut.m_axis_data_o) + " expected=" + std::to_string(t.expected[index]));
        ++index;
      }
      stalled = dut.m_axis_valid_o && !dut.m_axis_ready_i;
      held = dut.m_axis_data_o; last = dut.m_axis_last_o; tick();
    }
    dut.m_axis_ready_i = 0;
    const auto cycles = read(0x24);
    if (read(0x20) != t.tag || read(0x28) != t.length || cycles != t.cycles ||
        read(0x38) != allowed_error || !(read(4) & 4))
      throw std::runtime_error("SFPU completion/counters mismatch op=" + std::to_string(t.op) +
                               " cycles=" + std::to_string(cycles) + " expected=" + std::to_string(t.cycles));
    write(0x1c, 2);
  }
  void hold(const TestCase& t) {
    const uint64_t limit = clocks + t.cycles * 3 + 1000;
    while (!dut.m_axis_valid_o) {
      if (clocks > limit) throw std::runtime_error("output did not become valid"); tick();
    }
    const auto data = dut.m_axis_data_o;
    const bool last = dut.m_axis_last_o;
    for (unsigned i = 0; i < 100; ++i) {
      tick();
      if (!dut.m_axis_valid_o || dut.m_axis_data_o != data || bool(dut.m_axis_last_o) != last)
        throw std::runtime_error("prolonged output stall corrupted payload");
    }
  }
};

static TestCase tiny() { return {1, 3, 0, 0, 0xabc123, 18, {0, 2048, 0xfffff800}, {0, 2048, 0}}; }

static void protocol(Harness& h) {
  if (h.read(0) != 0x50415333 || h.read(0x3c) != 0x01000c00 ||
      h.read(0x44) != 0xfe || h.read(0x48) != 0x30001 || h.read(0x4c) != 1024 || h.read(0x80))
    throw std::runtime_error("SFPU identification/capability/reserved register mismatch");
  if (h.dut.irq_o || h.read(0x40) || h.read(0x50)) throw std::runtime_error("unsafe reset state");
  const TestCase t = tiny();
  h.write(0x50, 1); h.dut.gemm_busy_i = 1; h.write(0x50, 0); h.error(9);
  if (h.read(0x50) != 1) throw std::runtime_error("busy GEMM route changed");
  h.dut.gemm_busy_i = 0; h.write(0x1c, 2); h.write(0x50, 0);
  h.write(0x50, 2); h.error(3); h.write(0x1c, 2);
  for (const auto reg : {8u, 12u, 16u, 20u}) {
    for (const uint32_t bad : {0x80000001u, 0xffffffffu}) {
      h.stage(t); h.write(reg, bad);
      if (h.read(reg) != bad) throw std::runtime_error("staging truncated full-width input");
      h.write(0x1c, 1); h.error(reg == 8 ? 1 : reg == 12 ? 2 : 3);
      if (h.read(0x2c) || h.read(0x30)) throw std::runtime_error("invalid descriptor exposed word counts");
      h.write(0x1c, 4);
    }
  }
  for (unsigned length : {0u, 3073u, 0x10000c00u}) {
    h.stage(t); h.write(12, length); h.write(0x1c, 1); h.error(2); h.write(0x1c, 4);
  }
  h.stage(t); h.write(8, 3); h.write(12, 1025); h.write(0x1c, 1); h.error(2); h.write(0x1c, 4);
  h.write(12, 0xff000003); h.write(12, 0, 8);
  if (h.read(12) != 3) throw std::runtime_error("staging byte enables broken");
  h.write(0x1c, 1, 0); h.empty();
  h.write(0x1c, 3); h.error(10); h.write(0x1c, 4);
  h.write(0x1c, 0x80000000); h.error(10); h.write(0x1c, 0xffffffff); h.empty();

  h.write(0x40, 1); h.submit(t); h.write(0x1c, 1); h.error(4);
  if (!h.dut.irq_o) throw std::runtime_error("error IRQ missing");
  h.write(8, 0); h.write(0x1c, 1); h.error(4); // first error preserved
  h.feed(t); h.hold(t);
  if (h.read(0x34) != 0) throw std::runtime_error("unconsumed output counted complete");
  h.receive(t, 4); // queued work survives descriptor errors
  if (h.dut.irq_o) throw std::runtime_error("IRQ did not clear");
  h.submit(t); h.stage({7, 1, 0, 0, 99, 4, {1, 1}, {2}});
  h.feed(t); h.receive(t); // staging cannot mutate active descriptor
  h.submit(t); h.write(0x50, 1); h.error(9); h.feed(t); h.receive(t, 9);

  for (unsigned code : {5u, 6u, 8u}) {
    h.submit(t);
    h.raw(code == 8 ? 0x0000ffff : 0, code == 5 ? 7 : 15, code == 6);
    h.error(code);
    if (code != 6 && !h.dut.busy_o) throw std::runtime_error("malformed packet not draining");
    h.write(0x1c, 4); h.empty();
  }
  h.submit(t);
  for (auto value : t.input) h.raw(value, 15, false);
  h.error(7); h.raw(123, 15, false); h.raw(0, 15, true); h.write(0x1c, 2); h.empty();
  h.submit(t); for (auto value : t.input) h.raw(value, 15, false);
  h.error(7); h.write(0x1c, 4); h.empty(); // no terminator required for abort
  h.submit({3, 1, 0, 0, 1, 151, {0x10000}, {32768}});
  h.raw(0x20000, 15, true); h.error(8); h.write(0x1c, 4);
  h.submit({4, 1, 0, 0, 1, 71, {1, 1, 0}, {1}});
  h.raw(1, 15, false); h.raw(0x80000000, 15, false); h.error(8); h.write(0x1c, 4);
  // Protocol error overrides simultaneous normal command error.
  h.submit(t); h.dut.addr_i = 0x1c; h.dut.wdata_i = 3; h.dut.be_i = 15;
  h.dut.req_i = 1; h.dut.we_i = 1; h.raw(0, 7, true);
  h.dut.req_i = 0; h.dut.we_i = 0; h.error(5); h.write(0x1c, 4);
  h.submit(t); h.feed(t); h.hold(t);
  if (h.dut.irq_o) throw std::runtime_error("done IRQ before final handshake");
  // receive() clears done, so observe the IRQ manually at the final transfer.
  h.dut.m_axis_ready_i = 1;
  while (h.dut.busy_o) h.tick();
  h.dut.m_axis_ready_i = 0;
  if (!h.dut.irq_o) throw std::runtime_error("completion IRQ missing");
  h.write(0x1c, 2); h.reset(); h.empty();
  std::cout << "M3 SFPU PROTOCOL PASS\n";
}

static void lifecycle(Harness& h, const std::vector<TestCase>& tests) {
  unsigned phases = 0;
  for (unsigned op = 1; op <= 7; ++op) {
    const TestCase* selected = nullptr;
    for (const auto& t : tests) {
      if (t.op == op && (!selected || (t.length >= 3 && t.length <= 17))) {
        selected = &t;
        if (t.length >= 3 && t.length <= 17) break;
      }
    }
    if (!selected) throw std::runtime_error("missing lifecycle opcode");
    const auto& t = *selected;
    h.reset(); h.trace.clear(); h.recording = true;
    h.submit(t); h.feed(t); h.receive(t);
    h.recording = false; const auto keys = h.trace;
    for (const uint32_t target : keys) {
      for (const bool abort : {false, true}) {
        h.reset(); h.submit(t);
        size_t input = 0;
        const uint64_t deadline = h.clocks + t.input.size() + t.cycles * 3 + 200;
        while (h.key() != target) {
          if (h.clocks > deadline) throw std::runtime_error("lifecycle phase not reached key=" + std::to_string(target));
          if (input < t.input.size() && h.dut.s_axis_ready_o) {
            h.raw(t.input[input], 15, input + 1 == t.input.size()); ++input;
          } else h.tick();
        }
        h.dut.s_axis_valid_i = 0;
        if (abort) h.write(0x1c, 4); else h.reset();
        h.empty();
        const auto recovery = tiny(); h.submit(recovery); h.feed(recovery); h.receive(recovery);
        for (unsigned cycle = 0; cycle < 100; ++cycle) h.tick();
        h.empty(); ++phases;
      }
    }
    // Additional partial-load and partial-output recovery, not only state entry.
    h.reset(); h.submit(t);
    for (size_t i = 0; i < t.input.size() / 2; ++i) h.raw(t.input[i], 15, false);
    h.write(0x1c, 4); h.empty();
    h.submit(t); h.feed(t); h.hold(t);
    h.dut.m_axis_ready_i = 1; h.tick(); h.dut.m_axis_ready_i = 0;
    h.write(0x1c, 4); h.empty();
  }
  h.reset();
  std::cout << "M3 SFPU LIFECYCLE PASS reset_abort_checkpoints=" << phases << " ops=7\n";
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  try {
    if (argc != 2) throw std::runtime_error("usage: Vpa_sfpu VECTOR_FILE");
    const auto tests = vectors(argv[1]);
    if (tests.size() < 2000) throw std::runtime_error("insufficient SFPU coverage");
    Harness h; protocol(h);
    unsigned counts[8]{};
    for (const auto& t : tests) {
      h.submit(t); h.feed(t); h.receive(t); ++counts[t.op];
      if ((t.tag % 500) == 0) std::cout << "M3 SFPU checked=" << t.tag << '/' << tests.size() << std::endl;
    }
    if (h.read(0x34) != tests.size()) throw std::runtime_error("total SFPU completion count mismatch");
    lifecycle(h, tests);
    std::cout << "M3 SFPU RTL PASS cases=" << tests.size() << " clocks=" << h.clocks << " ops=";
    for (unsigned op = 1; op <= 7; ++op) std::cout << op << ':' << counts[op] << ',';
    std::cout << '\n'; return 0;
  } catch (const std::exception& e) {
    std::cerr << "M3 SFPU RTL FAIL: " << e.what() << '\n'; return 1;
  }
}
