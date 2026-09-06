// Actual M5 Ibex/DDR integration. Host model supplies memory, not a CPU tensor worker.
#include "Vpa_m5_cluster_top.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool condition, const std::string &message) {
  if (!condition) throw std::runtime_error(message);
}
static uint32_t pattern(unsigned hart, unsigned index) {
  return 0x51a00000u ^ (hart << 20) ^ (index * 0x10201u);
}

class Simulation {
 public:
  VerilatedContext context;
  Vpa_m5_cluster_top top;
  uint64_t cycles = 0, table_reads = 0, data_reads = 0, writes = 0;
  bool hold_responses = false;
  bool read_active = false, write_active = false, pending_b = false;
  std::array<uint32_t, 4> ptes{};
  std::array<uint32_t, 4096> memory{};

  Simulation(int argc, char **argv) : context(), top(&context) {
    context.commandArgs(argc, argv);
    // Establish a real falling reset edge before clocking. Starting a gated
    // core at reset=0 does not trigger its asynchronous flops in a two-state
    // simulator whose generated initial values are also zero.
    top.IO_CLK = 0; top.IO_RST_N = 1; top.CORE_RST_N = 1;
    top.awaddr_i = 0; top.awvalid_i = 0; top.wdata_i = 0; top.wstrb_i = 0;
    top.wvalid_i = 0; top.bready_i = 0; top.araddr_i = 0; top.arvalid_i = 0; top.rready_i = 0;
    top.gemm_s_axis_data_i = 0; top.gemm_s_axis_keep_i = 0;
    top.gemm_s_axis_last_i = 0; top.gemm_s_axis_valid_i = 0; top.gemm_m_axis_ready_i = 0;
    top.cfg_enable_i = 0; top.cfg_table_base_i = 0x02000000; top.cfg_arena_bytes_i = 16384;
    top.cfg_flush_i = 0; top.memory_abort_i = 1;
    top.bulk_busy_i = 0; top.bulk_req_valid_i = 0; top.bulk_req_addr_i = 0;
    top.bulk_req_words_i = 0; top.bulk_req_write_i = 0; top.bulk_in_valid_i = 0;
    top.bulk_in_data_i = 0; top.bulk_in_strb_i = 0; top.bulk_out_ready_i = 0; top.bulk_done_ready_i = 0;
    drive_memory(); top.eval();
    top.IO_RST_N = 0; top.CORE_RST_N = 0;
    for (unsigned i = 0; i < 4; ++i) tick();
    top.IO_RST_N = 1; tick();
  }

  void reset_quiescent() {
    require(top.memory_quiesced_o && !read_active && !write_active && !pending_b && !rvalid && !bvalid,
            "reset attempted before complete memory drain");
    top.IO_RST_N = 0;
    for (unsigned i = 0; i < 4; ++i) tick();
    top.IO_RST_N = 1; tick();
  }

  void configure(bool remap) {
    require(top.memory_quiesced_o, "mapping changed while live");
    top.cfg_enable_i = 0;
    ptes = {remap ? 0x10001003u : 0x10003003u, 0x10000003u, 0x10002001u, 0};
    memory.fill(0);
    memory[2048] = 0x00750513u; // addi a0,a0,7
    memory[2049] = 0x00008067u; // ret
    top.cfg_flush_i = 1; top.eval();
    require(top.flush_ready_o, "quiescent mapping flush not ready");
    tick(); top.cfg_flush_i = 0; top.cfg_enable_i = 1; tick();
  }

  void tick() {
    require(cycles < 30000000, "global simulation watchdog");
    drive_memory(); top.IO_CLK = 0; top.eval();
    const bool ar = top.m_arvalid_o && top.m_arready_i;
    const bool aw = top.m_awvalid_o && top.m_awready_i;
    const bool w = top.m_wvalid_o && top.m_wready_i;
    const bool r = top.m_rvalid_i && top.m_rready_o;
    const bool b = top.m_bvalid_i && top.m_bready_o;
    const uint32_t ar_addr = top.m_araddr_o, aw_addr = top.m_awaddr_o, wd = top.m_wdata_o;
    const unsigned ar_words = unsigned(top.m_arlen_o) + 1, aw_words = unsigned(top.m_awlen_o) + 1;
    const unsigned ws = top.m_wstrb_o;
    const bool wl = top.m_wlast_o;
    require(!(ar && aw), "overlapping AXI commands");
    if (ar) check_attributes(false);
    if (aw) check_attributes(true);
    top.IO_CLK = 1; top.eval();
    if (top.IO_RST_N) {
      if (ar) {
        require(!read_active && !write_active && !pending_b && !bvalid, "AR overlaps pending access");
        read_active = true; read_address = ar_addr; read_words = ar_words; read_index = 0;
        if (is_table(ar_addr)) { require(ar_words == 1, "burst PTE read"); ++table_reads; }
        else { check_region(ar_addr, ar_words, false); ++data_reads; }
      }
      if (aw) {
        require(!write_active && !read_active && !pending_b && !bvalid, "AW overlaps pending access");
        check_region(aw_addr, aw_words, true);
        write_active = true; write_address = aw_addr; write_words = aw_words; write_index = 0; ++writes;
      }
      if (w) {
        require(write_active && wl == (write_index + 1 == write_words), "invalid W beat/last");
        auto &dest = memory[(write_address - 0x10000000u) / 4 + write_index];
        for (unsigned lane = 0; lane < 4; ++lane) if (ws & (1u << lane)) {
          const uint32_t mask = 255u << (lane * 8);
          dest = (dest & ~mask) | (wd & mask);
        }
        if (++write_index == write_words) { write_active = false; pending_b = true; }
      }
      if (r) {
        require(read_active && rlast == (read_index + 1 == read_words), "invalid R retirement");
        rvalid = false;
        if (++read_index == read_words) read_active = false;
      }
      if (b) { require(bvalid, "unexpected B retirement"); bvalid = false; }
    } else {
      require(!read_active && !write_active && !pending_b && !rvalid && !bvalid,
              "IO reset does not cancel outstanding AXI");
    }
    ++cycles; context.timeInc(1);
    top.IO_CLK = 0; top.eval();
    require(!top.memory_poisoned_o, "memory AXI protocol poisoned");
    if (top.memory_quiesced_o)
      require(!read_active && !write_active && !pending_b && !rvalid && !bvalid,
              "false whole-cluster memory quiescence");
  }

  void write_ram(uint32_t address, uint32_t value) {
    top.awaddr_i = address; top.awvalid_i = 1; top.eval();
    wait_for([&] { return top.awready_o; }, 100, "AXI-Lite AW"); tick(); top.awvalid_i = 0;
    top.wdata_i = value; top.wstrb_i = 15; top.wvalid_i = 1; top.eval();
    wait_for([&] { return top.wready_o; }, 100, "AXI-Lite W"); tick(); top.wvalid_i = 0;
    wait_for([&] { return top.bvalid_o; }, 100, "AXI-Lite B");
    require(top.bresp_o == 0, "AXI-Lite write error");
    top.bready_i = 1; tick(); top.bready_i = 0; tick();
  }
  uint32_t read_ram(uint32_t address) {
    top.araddr_i = address; top.arvalid_i = 1; top.eval();
    wait_for([&] { return top.arready_o; }, 100, "AXI-Lite AR"); tick(); top.arvalid_i = 0;
    wait_for([&] { return top.rvalid_o; }, 100, "AXI-Lite R");
    require(top.rresp_o == 0, "AXI-Lite read error");
    const uint32_t data = top.rdata_o;
    top.rready_i = 1; tick(); top.rready_i = 0; tick(); return data;
  }
  void load(const std::vector<uint8_t> &image) {
    require(!top.CORE_RST_N && top.memory_quiesced_o && image.size() == 65536, "unsafe/bad firmware load");
    for (uint32_t address = 0; address < 65536; address += 4) write_ram(address, image_word(image, address));
    for (uint32_t address = 0; address < 65536; address += 4)
      require(read_ram(address) == image_word(image, address), "firmware RAM verification mismatch");
  }
  void start() {
    top.memory_abort_i = 0; tick(); top.CORE_RST_N = 1; tick();
  }
  void stop_and_drain() {
    top.CORE_RST_N = 0; top.memory_abort_i = 1;
    wait_for([&] { return top.memory_quiesced_o; }, 10000, "core/memory drain");
  }
  void complete(const char *label) {
    wait_for([&] { return top.software_done_o; }, 10000000, "dual-Ibex firmware completion");
    stop_and_drain();
    for (unsigned hart = 0; hart < 2; ++hart) {
      std::array<uint32_t, 16> result{};
      for (unsigned i = 0; i < result.size(); ++i) result[i] = read_ram(0xd000u + hart * 64u + i * 4u);
      std::printf("M5 IBEX %s hart=%u state=%u errors=%08x traps=%u last_cause=%u last_address=%08x last_pc=%08x unaligned_cases=%u cycles=%u\n",
                  label, hart, result[0], result[1], result[2], result[3], result[4], result[7], result[11], result[10] - result[9]);
      require(result[0] == (hart == 0 ? 3u : 2u) && result[1] == 0 && result[2] == 3 &&
              result[3] == 5 && result[4] == 0x4ffffffcu && result[11] == (hart == 0 ? 12u : 6u) && result[12] == 1,
              "firmware result/trap mismatch");
      uint32_t checksum = 0;
      const unsigned base = ((ptes[hart] & 0xfffff000u) - 0x10000000u) / 4;
      for (unsigned i = 0; i < 1024; ++i) {
        require(memory[base + i] == pattern(hart, i), "DDR final contents mismatch");
        checksum ^= pattern(hart, i);
      }
      require(result[8] == checksum, "firmware checksum mismatch");
    }
    require(memory[2048] == 0x00750513u && memory[2049] == 0x00008067u, "RO code page changed");
    for (unsigned i = 2050; i < 3072; ++i) require(memory[i] == 0, "RO padding changed");
  }
  template <typename Condition> void wait_for(Condition ready, uint64_t limit, const char *what) {
    uint64_t elapsed = 0;
    while (!ready()) {
      require(elapsed++ < limit, std::string("timeout: ") + what);
      tick();
    }
  }

 private:
  bool rvalid = false, rlast = false, bvalid = false;
  uint32_t rdata = 0, read_address = 0, write_address = 0;
  unsigned read_index = 0, write_index = 0, read_words = 0, write_words = 0;
  static uint32_t image_word(const std::vector<uint8_t> &image, unsigned address) {
    uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) value |= uint32_t(image[address + i]) << (i * 8);
    return value;
  }
  static bool is_table(uint32_t address) { return address >= 0x02000000 && address < 0x02000010; }
  void check_region(uint32_t address, unsigned words, bool writing) {
    require(address % 4 == 0 && words >= 1 && words <= 256 &&
              uint64_t(address & 4095u) + words * 4u <= 4096, "invalid AXI burst range");
    bool allowed = false;
    for (uint32_t pte : ptes)
      if ((pte & 1) && (pte & 0xfffff000u) == (address & 0xfffff000u) && (!writing || (pte & 2)))
        allowed = true;
    require(allowed, "AXI data access escaped owned/permissioned pages");
  }
  void check_attributes(bool writing) {
    if (writing) require(top.m_awid_o == 0 && top.m_awsize_o == 2 && top.m_awburst_o == 1 &&
                         top.m_awcache_o == 0 && top.m_awprot_o == 0, "bad AXI AW attributes");
    else require(top.m_arid_o == 0 && top.m_arsize_o == 2 && top.m_arburst_o == 1 &&
                  top.m_arcache_o == 0 && top.m_arprot_o == 0, "bad AXI AR attributes");
  }
  void drive_memory() {
    if (!rvalid && read_active && !hold_responses && cycles % 3 != 1) {
      rvalid = true; rlast = read_index + 1 == read_words;
      rdata = is_table(read_address) ? ptes[(read_address - 0x02000000u) / 4] :
              memory[(read_address - 0x10000000u) / 4 + read_index];
    }
    if (pending_b && !hold_responses && cycles % 3 == 0) { pending_b = false; bvalid = true; }
    top.m_arready_i = !read_active && !write_active && !pending_b && !bvalid && cycles % 3 != 0;
    top.m_awready_i = !read_active && !write_active && !pending_b && !bvalid && cycles % 4 != 0;
    top.m_wready_i = write_active && cycles % 3 != 0;
    top.m_rvalid_i = rvalid; top.m_rdata_i = rdata; top.m_rresp_i = 0; top.m_rid_i = 0; top.m_rlast_i = rlast;
    top.m_bvalid_i = bvalid; top.m_bresp_i = 0; top.m_bid_i = 0;
  }
};

int main(int argc, char **argv) {
  try {
    require(argc == 2, "usage: Vpa_m5_cluster_top firmware.bin");
    std::ifstream source(argv[1], std::ios::binary);
    require(bool(source), "firmware image missing");
    std::vector<uint8_t> image((std::istreambuf_iterator<char>(source)), std::istreambuf_iterator<char>());
    Simulation sim(argc, argv);
    sim.configure(false); sim.load(image); sim.start(); sim.complete("initial");
    sim.reset_quiescent(); sim.configure(false); sim.load(image); sim.start();
    sim.wait_for([&] { return sim.write_active; }, 1000000, "active AXI write for abort");
    sim.hold_responses = true;
    sim.top.CORE_RST_N = 0; sim.top.memory_abort_i = 1;
    for (unsigned i = 0; i < 32; ++i) {
      sim.tick(); require(!sim.top.memory_quiesced_o, "missing B treated as drained after core reset");
    }
    require(sim.pending_b, "abort did not drain buffered W data without running cores");
    sim.hold_responses = false; sim.stop_and_drain();
    sim.configure(true); sim.load(image); sim.start(); sim.complete("remapped_after_abort");
    std::printf("M5 ACTUAL DUAL-IBEX MEMORY SIMULATION PASS boots=2 aborted_boots=1 cycles=%llu pte_reads=%llu data_reads=%llu writes=%llu\n",
                static_cast<unsigned long long>(sim.cycles), static_cast<unsigned long long>(sim.table_reads),
                static_cast<unsigned long long>(sim.data_reads), static_cast<unsigned long long>(sim.writes));
    sim.top.final();
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "M5 ACTUAL DUAL-IBEX MEMORY FAIL: %s\n", error.what());
    return 1;
  }
}
