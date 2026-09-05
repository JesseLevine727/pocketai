#include <verilated.h>
#include "Vpa_sfpu_alu.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>

using u128 = unsigned __int128;
static uint64_t random_state = 0x50415333414c55ull;
static uint64_t next_random() {
  random_state ^= random_state << 13;
  random_state ^= random_state >> 7;
  random_state ^= random_state << 17;
  return random_state;
}

class Harness {
 public:
  Vpa_sfpu_alu dut;
  Harness() {
    dut.clk_i = 0; dut.rst_ni = 0; dut.abort_i = 0; dut.start_i = 0;
    tick(); tick(); dut.rst_ni = 1; tick();
  }
  ~Harness() { dut.final(); }
  void tick() {
    dut.clk_i = 0; dut.eval(); dut.clk_i = 1; dut.eval(); dut.clk_i = 0; dut.eval();
  }
  void start(unsigned op, uint64_t a, uint64_t b, u128 rad) {
    dut.op_i = op; dut.a_i = a; dut.b_i = b;
    dut.radicand_i[0] = uint32_t(rad);
    dut.radicand_i[1] = uint32_t(rad >> 32);
    dut.radicand_i[2] = uint32_t(rad >> 64) & 0xffff;
    dut.start_i = 1; tick(); dut.start_i = 0;
  }
  void check(unsigned op, uint64_t a, uint64_t b, u128 rad) {
    start(op, a, b, rad);
    unsigned latency = 0;
    while (!dut.done_o && latency < 70) { tick(); ++latency; }
    uint64_t expected = 0, remainder = 0;
    bool error = false;
    if (op == 0) {
      const u128 product = u128(a) * b;
      expected = uint64_t(product); error = (product >> 64) != 0;
    } else if (op == 1) {
      if (!b) error = true;
      else { expected = a / b; remainder = a % b; }
    } else if (op == 2) {
      // Independent integer Newton iteration, not the RTL's restoring method.
      u128 root = u128(1) << 40;
      if (rad == 0) root = 0;
      else while (true) {
        const u128 update = (root + rad / root) / 2;
        if (update >= root) break;
        root = update;
      }
      expected = uint64_t(root); remainder = uint64_t(rad - root * root);
    } else error = true;
    const unsigned expected_latency = (op == 3 || (op == 1 && !b)) ? 0 : op == 2 ? 40 : 64;
    if (!dut.done_o || dut.busy_o || dut.error_o != error ||
        dut.result_o != expected || dut.remainder_o != remainder || latency != expected_latency) {
      throw std::runtime_error("ALU result/error/latency mismatch op=" + std::to_string(op));
    }
    tick();
    if (dut.done_o || dut.result_o != expected || dut.remainder_o != remainder)
      throw std::runtime_error("ALU completion not pulsed/result not retained");
  }
};

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  try {
    Harness h;
    unsigned cases = 0, aborts = 0;
    for (unsigned op = 0; op < 4; ++op) {
      for (uint64_t a : {0ull, 1ull, 2ull, 0x7fffffffffffffffull, 0x8000000000000000ull,
                         0xffffffffffffffffull}) {
        for (uint64_t b : {0ull, 1ull, 2ull, 0x7fffffffffffffffull, 0xffffffffffffffffull}) {
          h.check(op, a, b, (u128(b & 0xffff) << 64) | a); ++cases;
        }
      }
    }
    for (unsigned i = 0; i < 5000; ++i) {
      uint64_t a = next_random(), b = next_random();
      if (i & 1) { a >>= 32; b >>= 32; } // bounded and overflow products
      const u128 rad = (u128(next_random() & 0xffff) << 64) | next_random();
      for (unsigned op = 0; op < 3; ++op) { h.check(op, a, b, rad); ++cases; }
    }
    for (unsigned op = 0; op < 3; ++op) {
      for (unsigned phase = 0; phase < (op == 2 ? 40u : 64u); ++phase) {
        for (bool reset : {false, true}) {
          h.start(op, 0xffffffffffffffffull, 0x12345678,
                  (u128(0xabcd) << 64) | 0x9876543210123456ull);
          for (unsigned i = 0; i < phase; ++i) h.tick();
          if (reset) h.dut.rst_ni = 0; else h.dut.abort_i = 1;
          h.tick(); h.dut.rst_ni = 1; h.dut.abort_i = 0;
          for (unsigned i = 0; i < 70; ++i) {
            h.tick();
            if (h.dut.done_o || h.dut.busy_o) throw std::runtime_error("stale result after reset/abort");
          }
          h.check(op, 123, 7, 987654321); ++aborts;
        }
      }
    }
    // A spurious request while busy cannot replace the accepted operation.
    h.start(1, 1000, 7, 0);
    h.dut.start_i = 1; h.dut.op_i = 0; h.dut.a_i = 999; h.dut.b_i = 999;
    for (unsigned i = 0; i < 10; ++i) h.tick();
    h.dut.start_i = 0;
    for (unsigned i = 0; i < 54; ++i) h.tick();
    if (!h.dut.done_o || h.dut.result_o != 142 || h.dut.remainder_o != 6)
      throw std::runtime_error("busy request replaced an accepted operation");
    std::cout << "M3 ALU RTL PASS cases=" << cases << " reset_abort_phases=" << aborts << '\n';
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "M3 ALU RTL FAIL: " << e.what() << '\n'; return 1;
  }
}
