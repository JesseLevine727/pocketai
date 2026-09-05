#include <verilated.h>

#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "Vpa_gemm.h"

namespace {

constexpr uint32_t kMagic = 0x324d4547;
constexpr uint32_t kId = 0x50414732;
#ifdef PA_GEMM_WIDE_TEST
constexpr const char* kMilestone = "M3 WIDE";
#else
constexpr const char* kMilestone = "M2";
#endif

constexpr uint32_t kRegId = 0x00;
constexpr uint32_t kRegStatus = 0x04;
constexpr uint32_t kRegM = 0x08;
constexpr uint32_t kRegN = 0x0c;
constexpr uint32_t kRegK = 0x10;
constexpr uint32_t kRegFlags = 0x14;
constexpr uint32_t kRegTag = 0x18;
constexpr uint32_t kRegCommand = 0x1c;
constexpr uint32_t kRegCompletedTag = 0x20;
constexpr uint32_t kRegLastCycles = 0x24;
constexpr uint32_t kRegLastMacs = 0x28;
constexpr uint32_t kRegInputWords = 0x2c;
constexpr uint32_t kRegOutputWords = 0x30;
constexpr uint32_t kRegCompletedCount = 0x34;
constexpr uint32_t kRegErrorCode = 0x38;
constexpr uint32_t kRegCaps = 0x3c;
constexpr uint32_t kRegIrqEnable = 0x40;

struct TestCase {
  uint32_t m;
  uint32_t n;
  uint32_t k;
  uint32_t tag;
  uint32_t flags;
  std::vector<uint32_t> input;
  std::vector<uint32_t> expected;
};

template <typename T>
T read_binary(std::ifstream& stream) {
  T value{};
  stream.read(reinterpret_cast<char*>(&value), sizeof(value));
  if (!stream) throw std::runtime_error("truncated vector file");
  return value;
}

std::vector<TestCase> load_vectors(const std::string& path, uint32_t* seed) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) throw std::runtime_error("cannot open vector file: " + path);
  if (read_binary<uint32_t>(stream) != kMagic) {
    throw std::runtime_error("bad vector-file magic");
  }
  const uint32_t count = read_binary<uint32_t>(stream);
  *seed = read_binary<uint32_t>(stream);
  std::vector<TestCase> cases;
  cases.reserve(count);
  for (uint32_t index = 0; index < count; ++index) {
    TestCase test{};
    test.m = read_binary<uint32_t>(stream);
    test.n = read_binary<uint32_t>(stream);
    test.k = read_binary<uint32_t>(stream);
    test.tag = read_binary<uint32_t>(stream);
    test.flags = read_binary<uint32_t>(stream);
    const uint32_t input_words = read_binary<uint32_t>(stream);
    const uint32_t output_words = read_binary<uint32_t>(stream);
    test.input.resize(input_words);
    test.expected.resize(output_words);
    stream.read(reinterpret_cast<char*>(test.input.data()),
                static_cast<std::streamsize>(input_words * sizeof(uint32_t)));
    stream.read(reinterpret_cast<char*>(test.expected.data()),
                static_cast<std::streamsize>(output_words * sizeof(uint32_t)));
    if (!stream) throw std::runtime_error("truncated vector payload");
    cases.push_back(std::move(test));
  }
  if (stream.peek() != std::ifstream::traits_type::eof()) {
    throw std::runtime_error("unexpected bytes after vector cases");
  }
  return cases;
}

class Harness {
 public:
  Harness() {
    dut_.clk_i = 0;
    dut_.rst_ni = 0;
    dut_.req_i = 0;
    dut_.we_i = 0;
    dut_.be_i = 0;
    dut_.addr_i = 0;
    dut_.wdata_i = 0;
    dut_.s_axis_data_i = 0;
    dut_.s_axis_keep_i = 0xf;
    dut_.s_axis_last_i = 0;
    dut_.s_axis_valid_i = 0;
    dut_.m_axis_ready_i = 0;
    dut_.eval();
    for (int cycle_index = 0; cycle_index < 4; ++cycle_index) cycle();
    dut_.rst_ni = 1;
    cycle();
  }

  ~Harness() { dut_.final(); }

  void cycle() {
    dut_.clk_i = 0;
    dut_.eval();
    dut_.clk_i = 1;
    dut_.eval();
    dut_.clk_i = 0;
    dut_.eval();
    ++cycles_;
  }

  void reset() {
    dut_.req_i = 0;
    dut_.s_axis_valid_i = 0;
    dut_.m_axis_ready_i = 0;
    dut_.rst_ni = 0;
    cycle();
    cycle();
    dut_.rst_ni = 1;
    cycle();
  }

  void write(uint32_t address, uint32_t value, uint8_t strobes = 0xf) {
    dut_.addr_i = address;
    dut_.wdata_i = value;
    dut_.be_i = strobes;
    dut_.we_i = 1;
    dut_.req_i = 1;
    cycle();
    dut_.req_i = 0;
    dut_.we_i = 0;
    dut_.be_i = 0;
    cycle();
  }

  uint32_t read(uint32_t address) {
    dut_.addr_i = address;
    dut_.we_i = 0;
    dut_.req_i = 1;
    cycle();
    if (!dut_.rvalid_o) throw std::runtime_error("MMIO read lacked rvalid");
    const uint32_t value = dut_.rdata_o;
    dut_.req_i = 0;
    cycle();
    return value;
  }

  void submit(const TestCase& test) {
    write(kRegM, test.m);
    write(kRegN, test.n);
    write(kRegK, test.k);
    write(kRegFlags, test.flags);
    write(kRegTag, test.tag);
    const uint32_t expected_input = test.m * ((test.k + 3) / 4) + 4 * test.k;
    if (read(kRegInputWords) != expected_input) {
      throw std::runtime_error("hardware input-word count differs from contract");
    }
    if (read(kRegOutputWords) != test.m * (test.flags == 0x100 ? 16 : 8)) {
      throw std::runtime_error("hardware output-word count differs from contract");
    }
    write(kRegCommand, 1);
  }

  void feed(const TestCase& test, uint32_t* random_state) {
    size_t word = 0;
    bool pending = false;
    uint64_t deadline = cycles_ + test.input.size() * 8 + 100;
    while (word < test.input.size()) {
      if (cycles_ > deadline) throw std::runtime_error("input stream timeout");
      const bool present = pending || (next_random(random_state) & 3) != 0;
      dut_.s_axis_valid_i = present;
      dut_.s_axis_data_i = test.input[word];
      dut_.s_axis_keep_i = 0xf;
      dut_.s_axis_last_i = word + 1 == test.input.size();
      dut_.eval();
      const bool transfer = dut_.s_axis_valid_i && dut_.s_axis_ready_o;
      cycle();
      if (transfer) ++word;
      pending = present && !transfer;
    }
    dut_.s_axis_valid_i = 0;
    dut_.s_axis_last_i = 0;
  }

  void feed_before_submit(const TestCase& test, uint32_t* random_state) {
    write(kRegM, test.m);
    write(kRegN, test.n);
    write(kRegK, test.k);
    write(kRegFlags, test.flags);
    write(kRegTag, test.tag);
    dut_.s_axis_data_i = test.input.front();
    dut_.s_axis_keep_i = 0xf;
    dut_.s_axis_last_i = 0;
    dut_.s_axis_valid_i = 1;
    for (int i = 0; i < 32; ++i) {
      dut_.eval();
      if (dut_.s_axis_ready_o) {
        throw std::runtime_error("input accepted without a descriptor");
      }
      cycle();
    }
    dut_.addr_i = kRegCommand;
    dut_.wdata_i = 1;
    dut_.be_i = 0xf;
    dut_.we_i = 1;
    dut_.req_i = 1;
    cycle();  // Submit; input was stalled on this edge.
    dut_.req_i = 0;
    dut_.we_i = 0;
    dut_.be_i = 0;
    if (!dut_.s_axis_ready_o) {
      throw std::runtime_error("descriptor did not release input backpressure");
    }
    cycle();  // The held first word is accepted exactly once.
    dut_.s_axis_valid_i = 0;
    TestCase remaining = test;
    remaining.input.erase(remaining.input.begin());
    feed(remaining, random_state);
  }

  std::vector<uint32_t> drain(size_t words, uint32_t* random_state) {
    std::vector<uint32_t> observed;
    observed.reserve(words);
    uint64_t deadline = cycles_ + 20000;
    bool stalled = false;
    uint32_t stalled_data = 0;
    bool stalled_last = false;
    while (observed.size() < words) {
      if (cycles_ > deadline) throw std::runtime_error("output stream timeout");
      dut_.m_axis_ready_i = (next_random(random_state) & 3) != 0;
      dut_.eval();
      if (stalled && (!dut_.m_axis_valid_o ||
                      dut_.m_axis_data_o != stalled_data ||
                      static_cast<bool>(dut_.m_axis_last_o) != stalled_last ||
                      dut_.m_axis_keep_o != 0xf)) {
        throw std::runtime_error("output changed while stalled");
      }
      const bool transfer = dut_.m_axis_valid_o && dut_.m_axis_ready_i;
      if (transfer) {
        if (dut_.m_axis_keep_o != 0xf) {
          throw std::runtime_error("output TKEEP is not 0xf");
        }
        const bool expected_last = observed.size() + 1 == words;
        if (static_cast<bool>(dut_.m_axis_last_o) != expected_last) {
          throw std::runtime_error("output TLAST at wrong word");
        }
        observed.push_back(dut_.m_axis_data_o);
      }
      stalled = dut_.m_axis_valid_o && !dut_.m_axis_ready_i;
      stalled_data = dut_.m_axis_data_o;
      stalled_last = dut_.m_axis_last_o;
      cycle();
    }
    dut_.m_axis_ready_i = 0;
    return observed;
  }

  void check_case_completion(const TestCase& test) {
    if (read(kRegCompletedTag) != test.tag) {
      throw std::runtime_error("completed tag mismatch");
    }
    if (read(kRegLastMacs) != test.m * test.n * test.k) {
      throw std::runtime_error("active MAC count mismatch");
    }
    const uint32_t row_groups = (test.m + 3) / 4;
    const uint32_t expected_cycles = row_groups * (test.k + 6) +
                                     test.m * (test.flags == 0x100 ? 16 : 8);
    if (read(kRegLastCycles) != expected_cycles) {
      throw std::runtime_error("compute/pack cycle count mismatch");
    }
    if ((read(kRegStatus) & (1u << 2)) == 0) {
      throw std::runtime_error("completion flag was not sticky");
    }
    write(kRegCommand, 2);
  }

  void send_raw(uint32_t data, uint8_t keep, bool last) {
    dut_.s_axis_data_i = data;
    dut_.s_axis_keep_i = keep;
    dut_.s_axis_last_i = last;
    dut_.s_axis_valid_i = 1;
    dut_.eval();
    if (!dut_.s_axis_ready_o) throw std::runtime_error("raw input was not ready");
    cycle();
    dut_.s_axis_valid_i = 0;
    dut_.s_axis_last_i = 0;
  }

  uint64_t cycles() const { return cycles_; }

  bool irq() const { return dut_.irq_o; }

  void check_empty() {
    if ((read(kRegStatus) & 0x33f) != 1 || dut_.busy_o) {
      throw std::runtime_error("expected an empty, error-free engine");
    }
  }

  void hold_output() {
    const uint64_t deadline = cycles_ + 20000;
    while (!dut_.m_axis_valid_o) {
      if (cycles_ > deadline) throw std::runtime_error("output never became valid");
      cycle();
    }
    const uint32_t data = dut_.m_axis_data_o;
    const bool last = dut_.m_axis_last_o;
    for (int i = 0; i < 100; ++i) {
      cycle();
      if (!dut_.m_axis_valid_o || dut_.m_axis_data_o != data ||
          static_cast<bool>(dut_.m_axis_last_o) != last ||
          dut_.m_axis_keep_o != 0xf) {
        throw std::runtime_error("output unstable during prolonged backpressure");
      }
    }
  }

 private:
  static uint32_t next_random(uint32_t* state) {
    uint32_t value = *state;
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    *state = value;
    return value;
  }

  Vpa_gemm dut_;
  uint64_t cycles_ = 0;
};

void require_equal(const std::vector<uint32_t>& observed,
                   const std::vector<uint32_t>& expected,
                   uint32_t tag) {
  if (observed.size() != expected.size()) {
    throw std::runtime_error("output length mismatch");
  }
  for (size_t index = 0; index < expected.size(); ++index) {
    if (observed[index] != expected[index]) {
      std::ostringstream message;
      message << "tag 0x" << std::hex << tag << " output word " << std::dec
              << index << " got 0x" << std::hex << std::setw(8)
              << std::setfill('0') << observed[index] << " expected 0x"
              << std::setw(8) << expected[index];
      throw std::runtime_error(message.str());
    }
  }
}

TestCase tiny_case(uint32_t tag) {
  TestCase test{};
  test.m = 1;
  test.n = 1;
  test.k = 4;
  test.tag = tag;
  test.flags = 0;
  test.input.assign(17, 0);
  test.expected.assign(8, 0);
  return test;
}

void check_error(Harness& harness, uint32_t expected) {
  const uint32_t status = harness.read(kRegStatus);
  if ((status & (1u << 3)) == 0 || harness.read(kRegErrorCode) != expected) {
    throw std::runtime_error("sticky error code mismatch");
  }
}

void run_control_and_protocol_tests(Harness& harness) {
  if (harness.read(kRegId) != kId) throw std::runtime_error("bad hardware ID");
  if (harness.read(kRegCaps) != 0x03001010) {
    throw std::runtime_error("capability register mismatch");
  }
#ifdef PA_GEMM_WIDE_TEST
  if (harness.read(0x44) != 1 || harness.read(0x48) != 3072 ||
      harness.read(0x4c) != 0x00030001) {
    throw std::runtime_error("wide extension capability mismatch");
  }
  for (const uint32_t invalid : {0u, 3073u, 0x10000c00u, 0xffffffffu}) {
    harness.write(kRegM, 1);
    harness.write(kRegN, 1);
    harness.write(kRegK, invalid);
    harness.write(kRegFlags, 0x100);
    harness.write(kRegCommand, 1);
    check_error(harness, 1);
    harness.write(kRegCommand, 4);
  }
  for (const uint32_t flags : {0x101u, 0x200u, 0xffffffffu}) {
    harness.write(kRegK, 1);
    harness.write(kRegFlags, flags);
    harness.write(kRegCommand, 1);
    check_error(harness, 2);
    harness.write(kRegCommand, 4);
  }
  harness.write(kRegFlags, 0);
#else
  if (harness.read(0x44) || harness.read(0x48) || harness.read(0x4c)) {
    throw std::runtime_error("legacy configuration exposed unsupported extension");
  }
#endif

  TestCase test = tiny_case(0xabc00001);
  if (harness.read(kRegIrqEnable) != 0) {
    throw std::runtime_error("IRQ unexpectedly enabled after reset");
  }
  harness.write(kRegIrqEnable, 1);
  harness.write(kRegM, 0);
  harness.write(kRegCommand, 1);
  check_error(harness, 1);
  if (!harness.irq()) {
    throw std::runtime_error("enabled error IRQ did not assert");
  }
  harness.write(kRegCommand, 4);
  if (harness.irq()) throw std::runtime_error("IRQ remained set after clear");
  harness.write(kRegIrqEnable, 0);

  for (const uint32_t reg : {kRegM, kRegN, kRegK}) {
    for (const uint32_t invalid : {0u, 769u, 0x80000001u, 0xffffffffu}) {
      harness.write(kRegM, 1);
      harness.write(kRegN, 1);
      harness.write(kRegK, 1);
      harness.write(reg, invalid);
      if (harness.read(reg) != invalid) {
        throw std::runtime_error("dimension staging truncated a 32-bit write");
      }
      harness.write(kRegCommand, 1);
      check_error(harness, 1);
      harness.write(kRegCommand, 4);
    }
  }
  harness.write(kRegM, 0x80000001);
  harness.write(kRegM, 0, 0x8);
  if (harness.read(kRegM) != 1) {
    throw std::runtime_error("dimension byte enables not preserved");
  }

  test.flags = 1;
  harness.submit(test);
  check_error(harness, 2);
  harness.write(kRegCommand, 4);
  test.flags = 0;

  harness.submit(test);
  test.tag++;
  harness.submit(test);
  test.tag++;
  harness.write(kRegTag, test.tag);
  harness.write(kRegCommand, 1);
  check_error(harness, 3);
  harness.write(kRegCommand, 4);

  test = tiny_case(0xabc00010);
  harness.submit(test);
  harness.send_raw(0, 0xf, true);
  check_error(harness, 5);
  harness.write(kRegCommand, 4);

  harness.submit(test);
  harness.send_raw(0, 0x7, true);
  check_error(harness, 4);
  harness.write(kRegCommand, 4);

  harness.submit(test);
  for (size_t word = 0; word < test.input.size(); ++word) {
    harness.send_raw(0, 0xf, false);
  }
  check_error(harness, 6);
  harness.write(kRegCommand, 4);
  harness.check_empty();  // A stopped source may never deliver a trailing TLAST.

  harness.submit(test);
  for (size_t word = 0; word < test.input.size(); ++word) {
    harness.send_raw(0, 0xf, false);
  }
  check_error(harness, 6);
  harness.send_raw(0xfeedface, 0xf, false);
  harness.send_raw(0, 0xf, true);
  harness.write(kRegCommand, 4);

  harness.submit(test);
  harness.send_raw(0, 0xf, false);
  harness.reset();
  if ((harness.read(kRegStatus) & 0x30f) != 1) {
    throw std::runtime_error("reset did not restore an empty ready engine");
  }
}

void run_lifecycle_tests(Harness& harness, const TestCase& long_case,
                         uint32_t* random_state) {
  for (const bool abort : {false, true}) {
    // Interrupt a long K dot product while the arithmetic pipeline is live.
    harness.submit(long_case);
    harness.feed(long_case, random_state);
    for (int i = 0; i < 20; ++i) harness.cycle();
    if (abort) harness.write(kRegCommand, 4);
    else harness.reset();
    harness.check_empty();

    // Repeat with a completed result held by downstream backpressure.
    harness.submit(long_case);
    harness.feed(long_case, random_state);
    harness.hold_output();
    if (abort) harness.write(kRegCommand, 4);
    else harness.reset();
    harness.check_empty();
    if (harness.read(kRegCompletedCount) != 0) {
      throw std::runtime_error("aborted tile was reported complete");
    }
  }
  harness.write(kRegIrqEnable, 1);
  harness.submit(long_case);
  harness.feed(long_case, random_state);
  require_equal(harness.drain(long_case.expected.size(), random_state),
                long_case.expected, long_case.tag);
  if (!harness.irq()) throw std::runtime_error("completion IRQ did not assert");
  harness.check_case_completion(long_case);
  if (harness.irq()) throw std::runtime_error("completion IRQ did not clear");
  harness.reset();
}

#ifdef PA_GEMM_WIDE_TEST
void run_wide_phase_tests(Harness& harness, const TestCase& full,
                          uint32_t* random_state) {
  // Distinct descriptor formats in each slot must remain immutable even when
  // software restages every field while a full-length tile is loading.
  harness.submit(full);
  harness.write(kRegM, 1);
  harness.write(kRegN, 1);
  harness.write(kRegK, 1);
  harness.write(kRegFlags, 0);
  harness.write(kRegTag, 0xbadbad);
  harness.feed(full, random_state);
  require_equal(harness.drain(full.expected.size(), random_state), full.expected, full.tag);
  harness.check_case_completion(full);
  harness.reset();

  std::vector<unsigned> phases{0, 1, 2, 3, 4, 5, 6, 7, 20};
  for (unsigned group = 0; group < 4; ++group) {
    const unsigned base = group * (full.k + 6 + 64);
    for (unsigned offset : {0u, 1u, full.k, full.k + 5, full.k + 6,
                            full.k + 7, full.k + 38, full.k + 69}) {
      phases.push_back(base + offset);
    }
  }
  TestCase recovery = tiny_case(0xfeed1234);
  recovery.flags = 0x100;
  recovery.expected.assign(16, 0);
  unsigned interruptions = 0;
  for (bool abort : {false, true}) {
    for (unsigned phase : phases) {
      harness.submit(full);
      harness.feed(full, random_state);
      for (unsigned cycle = 0; cycle < phase; ++cycle) harness.cycle();
      if (abort) harness.write(kRegCommand, 4); else harness.reset();
      harness.check_empty();
      harness.submit(recovery);
      harness.feed(recovery, random_state);
      require_equal(harness.drain(recovery.expected.size(), random_state),
                    recovery.expected, recovery.tag);
      harness.check_case_completion(recovery);
      for (unsigned cycle = 0; cycle < 100; ++cycle) harness.cycle();
      harness.check_empty();
      harness.reset();
      ++interruptions;
    }
  }
  std::cout << "M3 WIDE LIFECYCLE PASS interruptions=" << interruptions
            << " staging_immutable=1\n";
}
#endif

}  // namespace

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  try {
    if (argc != 2) throw std::runtime_error("usage: Vpa_gemm VECTOR_FILE");
    uint32_t seed = 0;
    const std::vector<TestCase> cases = load_vectors(argv[1], &seed);
    if (cases.size() < 1007) throw std::runtime_error("insufficient test cases");
    Harness harness;
    run_control_and_protocol_tests(harness);

    uint32_t random_state = seed;
#ifdef PA_GEMM_WIDE_TEST
    // The wide vector file has a full 16x16x3072 tile at index five. The
    // independent legacy-vector run still exercises all original lifecycle tests.
    if (cases[5].flags == 0x100 && cases[5].m == 16 && cases[5].k == 3072)
      run_wide_phase_tests(harness, cases[5], &random_state);
#endif
    run_lifecycle_tests(harness, cases[2], &random_state);
    harness.feed_before_submit(cases[1], &random_state);
    require_equal(harness.drain(cases[1].expected.size(), &random_state),
                  cases[1].expected, cases[1].tag);
    harness.check_case_completion(cases[1]);
    harness.reset();
    harness.submit(cases[0]);
    harness.submit(cases[1]);
    harness.feed(cases[0], &random_state);
    harness.feed(cases[1], &random_state);
    require_equal(harness.drain(cases[0].expected.size(), &random_state),
                  cases[0].expected, cases[0].tag);
    harness.check_case_completion(cases[0]);
    require_equal(harness.drain(cases[1].expected.size(), &random_state),
                  cases[1].expected, cases[1].tag);
    harness.check_case_completion(cases[1]);

    for (size_t index = 2; index < cases.size(); ++index) {
      harness.submit(cases[index]);
      harness.feed(cases[index], &random_state);
      require_equal(harness.drain(cases[index].expected.size(), &random_state),
                    cases[index].expected, cases[index].tag);
      harness.check_case_completion(cases[index]);
    }

    const uint32_t completed = harness.read(kRegCompletedCount);
    if (completed != cases.size()) {
      throw std::runtime_error("completed descriptor count mismatch");
    }
    std::cout << kMilestone << " GEMM RTL PASS cases=" << cases.size()
              << " random=" << cases.size() - 7 << " seed=0x"
              << std::hex << seed << std::dec
              << " cycles=" << harness.cycles() << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << kMilestone << " GEMM RTL FAIL: " << error.what() << '\n';
    return 1;
  }
}
