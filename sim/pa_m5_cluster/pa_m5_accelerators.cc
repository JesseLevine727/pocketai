// Actual M5 Ibex/DDR integration. Host model supplies memory, not a CPU tensor worker.
#include "Vpa_m5_cluster_top.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool condition, const std::string &message) {
  if (!condition) throw std::runtime_error(message);
}

class Simulation {
 public:
  VerilatedContext context;
  Vpa_m5_cluster_top top;
  uint64_t cycles = 0, table_reads = 0, data_reads = 0, writes = 0;
  bool hold_responses = false;
  bool read_active = false, write_active = false, pending_b = false;
  unsigned response_delay = std::getenv("PA_M5_AXI_DELAY") ?
      unsigned(std::strtoul(std::getenv("PA_M5_AXI_DELAY"), nullptr, 0)) : 0;
  uint64_t response_after = 0;
  std::vector<uint32_t> ptes = std::vector<uint32_t>(128);
  std::array<uint32_t, 262144> memory{};

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
    top.cfg_enable_i = 0; top.cfg_table_base_i = 0x02000000; top.cfg_arena_bytes_i = 524288;
    // Cancellation also resets the cores in autonomous mode. Keep it low
    // while establishing the initial high reset level, then assert it below.
    top.cfg_flush_i = 0; top.memory_abort_i = 0;
    top.bulk_busy_i = 0; top.bulk_req_valid_i = 0; top.bulk_req_addr_i = 0;
    top.bulk_req_words_i = 0; top.bulk_req_write_i = 0; top.bulk_in_valid_i = 0;
    top.bulk_in_data_i = 0; top.bulk_in_strb_i = 0; top.bulk_out_ready_i = 0; top.bulk_done_ready_i = 0;
    drive_memory(); top.eval();
    top.IO_RST_N = 0; top.CORE_RST_N = 0; top.memory_abort_i = 1;
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
    for (unsigned i = 0; i < ptes.size(); ++i)
      ptes[i] = (0x10000000u + (((i * 37u + (remap ? 7u : 0u)) % 128u) * 8192u)) | 3u;
    memory.fill(0xdeadbeefu);
    top.cfg_flush_i = 1; top.eval();
    require(top.flush_ready_o, "quiescent mapping flush not ready");
    tick(); top.cfg_flush_i = 0; top.cfg_enable_i = 1; tick();
  }

  void runtime_startup(const std::vector<uint8_t> &image, const char *model_path) {
    // Exact production firmware/header; deliberately truncate workspace so
    // startup terminates with a precise store fault only after header binding.
    ptes.assign(65536, 0);
    top.cfg_arena_bytes_i = 0x10000000;
    memory.fill(0);
    for (unsigned i = 0; i < 16; ++i) ptes[i] = (0x10000000 + i * 4096) | 1;
    for (unsigned i = 0; i < 4; ++i) {
      ptes[0xf1f9 + i] = (0x10010000 + i * 4096) | 3;
      ptes[0xf5fa + i] = (0x10014000 + i * 4096) | 3;
    }
    std::ifstream model(model_path, std::ios::binary);
    require(bool(model), "model header missing");
    model.read(reinterpret_cast<char *>(memory.data()), 65536);
    require(model.gcount() == 65536, "short model header");
    const uint32_t control[] = {0x35545250, 1, 1, 1, 1, 1, 0, 100000000};
    for (unsigned i = 0; i < 8; ++i) put_virtual(0x4f1f9000 + i * 4, control[i]);
    top.cfg_enable_i = 1;
    load(image); start();
    wait_for([&] { return top.software_done_o; }, 5000000, "runtime startup");
    stop_and_drain();
    uint32_t state = virtual_word(0x4f1f9020), ready = virtual_word(0x4f1f905c);
    uint32_t cause = read_ram(0xd008), address = read_ram(0xd00c), pc = read_ram(0xd010);
    std::printf("M5 STARTUP state=%u ready=%u cause=%u address=%08x pc=%08x cycles=%llu\n",
                state, ready, cause, address, pc, static_cast<unsigned long long>(cycles));
    require(state == 3 && ready == 3 && cause == 7 && address == 0x4f201a00,
            "production startup failed before intentional truncated-workspace store fault");
    std::puts("M5 PRODUCTION STARTUP PASS");
  }

  void tick() {
    require(cycles < 200000000, "global simulation watchdog");
    drive_memory(); top.IO_CLK = 0; top.eval();
    if (top.CORE_RST_N)
      require(!top.awvalid_i && !top.arvalid_i && !top.wvalid_i,
              "host transaction during firmware execution");
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
        response_after = cycles + response_delay;
        if (is_table(ar_addr)) { require(ar_words == 1, "burst PTE read"); ++table_reads; }
        else { check_region(ar_addr, ar_words, false); ++data_reads; }
      }
      if (aw) {
        require(!write_active && !read_active && !pending_b && !bvalid, "AW overlaps pending access");
        check_region(aw_addr, aw_words, true);
        write_active = true; write_address = aw_addr; write_words = aw_words; write_index = 0; ++writes;
        response_after = cycles + response_delay;
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
    require(!top.bulk_req_ready_o && !top.bulk_in_ready_o && !top.bulk_out_valid_o &&
            !top.bulk_done_valid_o && !top.gemm_s_axis_ready_o && !top.gemm_m_axis_valid_o,
            "autonomous configuration exposed an external payload/client handshake");
    if (top.memory_quiesced_o)
      require(!read_active && !write_active && !pending_b && !rvalid && !bvalid,
              "false whole-cluster memory quiescence");
  }

  void write_ram(uint32_t address, uint32_t value) {
    require(!top.CORE_RST_N, "in-run host MMIO write forbidden");
    top.awaddr_i = address; top.awvalid_i = 1; top.eval();
    wait_for([&] { return top.awready_o; }, 100, "AXI-Lite AW"); tick(); top.awvalid_i = 0;
    top.wdata_i = value; top.wstrb_i = 15; top.wvalid_i = 1; top.eval();
    wait_for([&] { return top.wready_o; }, 100, "AXI-Lite W"); tick(); top.wvalid_i = 0;
    wait_for([&] { return top.bvalid_o; }, 100, "AXI-Lite B");
    require(top.bresp_o == 0, "AXI-Lite write error");
    top.bready_i = 1; tick(); top.bready_i = 0; tick();
  }
  uint32_t read_ram(uint32_t address) {
    require(!top.CORE_RST_N, "in-run host MMIO read forbidden");
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
  void start_engines() {
    require(top.memory_quiesced_o && !top.CORE_RST_N, "start before drain");
    require(top.awready_o && top.arready_o && !top.awvalid_i && !top.arvalid_i &&
            !top.wvalid_i && !top.bvalid_o && !top.rvalid_o,
            "cluster reset before provisioning AXI-Lite host retired");
    // Match the physical helper START sequence: PREPARE has latched the
    // mover's Stopped state. Lower abort under reset, release IO with FLUSH
    // and cores held, complete the flush, then allow the caller to run.
    top.IO_RST_N = 0; top.memory_abort_i = 0;
    for (unsigned i = 0; i < 4; ++i) tick();
    top.cfg_flush_i = 1; top.IO_RST_N = 1; tick();
    wait_for([&] { return top.flush_ready_o; }, 100, "supervisor START flush");
    top.cfg_flush_i = 0; tick();
    require(!top.transfer_cancel_o && !top.memory_poisoned_o && !top.memory_busy_o,
            "supervisor START retained cancellation or traffic");
  }
  void start() {
    start_engines();
    // Try the disconnected development ports throughout autonomous execution.
    top.gemm_s_axis_valid_i = 1; top.gemm_s_axis_data_i = 0x11223344;
    top.gemm_s_axis_keep_i = 15; top.gemm_m_axis_ready_i = 1;
    top.bulk_req_valid_i = 1; top.bulk_req_words_i = 1; top.bulk_req_addr_i = 0x40000000;
    top.bulk_in_valid_i = 1; top.bulk_in_strb_i = 15; top.bulk_out_ready_i = 1;
    top.bulk_done_ready_i = 1; top.bulk_busy_i = 1;
    top.CORE_RST_N = 1; tick();
  }
  void stop_and_drain() {
    top.CORE_RST_N = 0; top.memory_abort_i = 1;
    wait_for([&] { return top.memory_quiesced_o; }, 10000, "core/memory drain");
  }
  uint32_t virtual_word(uint32_t address) const {
    unsigned page = (address - 0x40000000u) / 4096;
    require(page < ptes.size() && (ptes[page] & 1), "test virtual read outside map");
    return memory[((ptes[page] & 0xfffff000u) - 0x10000000u + (address & 4095u)) / 4];
  }
  bool packet_write() const { return write_active && write_words > 1; }
  bool packet_read() const { return read_active && read_words > 1; }
  void put_virtual(uint32_t address, uint32_t value) {
    require(!top.CORE_RST_N && top.memory_quiesced_o, "test provisioning while owned");
    unsigned page = (address - 0x40000000u) / 4096;
    require(page < ptes.size() && (ptes[page] & 1), "invalid provisioned test page");
    memory[((ptes[page] & 0xfffff000u) - 0x10000000u + (address & 4095u)) / 4] = value;
  }
  void prepare_add() {
    for (unsigned i = 0; i < 600; ++i) {
      put_virtual(0x40000ffcu + i * 4, uint32_t(int32_t(i % 201) - 100));
      put_virtual(0x4000dffcu + i * 4, uint32_t(int32_t(i % 129) - 64));
    }
  }
  void launch_add(unsigned deadline, bool invalid = false) {
    write_ram(0x14050, 1); write_ram(0x14008, 7); write_ram(0x1400c, 600);
    write_ram(0x14018, 0x1234); write_ram(0x1401c, 1);
    write_ram(0x15008, invalid ? 0 : 0x40000ffc); write_ram(0x1500c, 600);
    write_ram(0x15010, 0x4000dffc); write_ram(0x15014, 600);
    write_ram(0x15020, 0x40020ffc); write_ram(0x15024, 600);
    write_ram(0x15028, 0x1234); write_ram(0x1502c, deadline); write_ram(0x15030, 1);
  }
  void check_cancel(unsigned fault) {
    wait_for([&] { return top.transfer_cancel_o; }, 100000, "runtime cancellation");
    stop_and_drain();
    require(read_ram(0x15038) == fault && (read_ram(0x15004) & 8), "fault/stopped status mismatch");
    top.memory_abort_i = 0;
    for (unsigned i = 0; i < 10; ++i) tick();
    require(top.transfer_cancel_o && top.memory_quiesced_o, "cancellation was not sticky");
    top.memory_abort_i = 1;
  }
  // These are explicitly host-driven component/lifecycle tests, separate from
  // the no-host-service actual-hart runs. They are not model autonomy evidence.
  void component_tests() {
    unsigned cases = 0;
    for (unsigned engine = 0; engine < 2; ++engine) for (unsigned delay = 0; delay < 4; ++delay) {
      configure(false); start_engines();
      top.araddr_i = engine == 0 ? 0x13000 : 0x14000; top.arvalid_i = 1; top.eval();
      require(top.arready_o, "host read not ready"); tick(); top.arvalid_i = 0;
      for (unsigned i = 0; i < delay; ++i) tick();
      top.memory_abort_i = 1;
      wait_for([&] { return top.rvalid_o; }, 100, "MMIO response spanning accelerator reset");
      if (delay <= 1) require(top.rresp_o == 2, "cancelled MMIO read did not return bus error");
      // Keep R pending deliberately. Memory drain does not retire AXI-Lite R.
      for (unsigned i = 0; i < 8; ++i) {
        tick(); require(top.rvalid_o, "host response withdrawn by memory cancellation");
      }
      top.rready_i = 1; tick(); top.rready_i = 0; tick(); stop_and_drain(); ++cases;
    }
    // Local descriptor rejection has no physical-memory side effects.
    configure(false); prepare_add(); start_engines();
    uint64_t before = table_reads + data_reads + writes;
    launch_add(100000, true);
    wait_for([&] { return (read_ram(0x15004) & 4) != 0; }, 100, "invalid descriptor completion");
    require(read_ram(0x15038) == 16 && !top.transfer_cancel_o &&
            before == table_reads + data_reads + writes, "invalid descriptor had effects");
    write_ram(0x15030, 2); stop_and_drain(); ++cases;
    // Invalid source translation and late write protection (partial result invalid).
    configure(false); prepare_add(); ptes[0] = 0; start_engines(); launch_add(100000);
    check_cancel(38); ++cases;
    configure(false); prepare_add(); ptes[0x21] &= ~2u; start_engines(); launch_add(100000);
    check_cancel(39);
    require(virtual_word(0x40020ffc) == uint32_t(-164) && virtual_word(0x40021000) == 0xdeadbeefu,
            "late write fault did not preserve documented partial-write boundary"); ++cases;
    // Timeout cannot release an already-issued physical write lacking B.
    configure(false); prepare_add(); start_engines(); launch_add(40000);
    wait_for([&] { return write_active; }, 30000, "SFPU output write"); hold_responses = true;
    wait_for([&] { return top.transfer_cancel_o; }, 50000, "deadline with missing B");
    for (unsigned i = 0; i < 64; ++i) {
      tick(); require(!top.memory_quiesced_o && top.memory_busy_o, "deadline fabricated AXI drain");
    }
    require(pending_b, "buffered write did not drain after deadline");
    hold_responses = false; check_cancel(20); ++cases;
    // External abort during a stalled multi-beat read must retain its R owner.
    configure(false); prepare_add(); start_engines(); launch_add(100000);
    wait_for([&] { return packet_read(); }, 30000, "packet read for abort");
    hold_responses = true; top.memory_abort_i = 1;
    for (unsigned i = 0; i < 64; ++i) {
      tick(); require(!top.memory_quiesced_o, "missing R was treated as returned ownership");
    }
    hold_responses = false; check_cancel(17); ++cases;
    // The MMIO ABORT doorbell itself still completes through the live responder.
    configure(false); start_engines(); write_ram(0x15030, 4); check_cancel(17); ++cases;
    std::printf("M5 ACCEL COMPONENT LIFECYCLE PASS cases=%u\n", cases);
  }
  void complete(const char *label) {
    wait_for([&] { return top.software_done_o; }, 50000000, "dual-Ibex accelerator completion");
    stop_and_drain();
    bool firmware_ok = true;
    for (unsigned hart = 0; hart < 2; ++hart) {
      std::array<uint32_t, 16> result{};
      for (unsigned i = 0; i < result.size(); ++i) result[i] = read_ram(0xd000u + hart * 64u + i * 4u);
      std::printf("M5 ACCEL %s hart=%u state=%u errors=%08x mailbox_irqs=%u dma_irqs=%u jobs=%u checks=%u route_checks=%u cause=%08x address=%08x pc=%08x cycles=%u gemm_irqs=%u sfpu_irqs=%u unexpected_irqs=%u\n",
                  label, hart, result[0], result[1], result[2], result[3], result[5], result[6], result[7],
                  result[8], result[9], result[10], result[12] - result[11], result[13], result[14], result[15]);
      firmware_ok &= result[0] == (hart == 0 ? 3u : 2u) && result[1] == 0 && result[2] == 9 &&
              result[3] == (hart == 0 ? 0u : 9u) && result[5] == 9 &&
              result[6] == (hart == 0 ? 9633u : 0u) && result[7] == (hart == 0 ? 0u : 9u) &&
              result[13] == (hart == 0 ? 0u : 5u) && result[14] == (hart == 0 ? 0u : 4u) && result[15] == 0;
    }
    unsigned checked = 0;
    for (unsigned job = 1; job <= 9; ++job) {
      const unsigned ms[] = {1, 3, 3, 3, 16}, ks[] = {1, 3, 7, 768, 3072};
      const unsigned count = job <= 5 ? ms[job-1] * 16 : job == 9 ? 1 : 3072;
      for (unsigned i = 0; i < count; ++i) {
        int32_t expected = 0;
        if (job <= 5) {
          // Direct independent sum, not firmware's periodic closed form.
          if (i % 16 < 13)
            for (unsigned k = 0; k < ks[job-1]; ++k)
              expected += int32_t(i / 16 + 1) * (int32_t(k % 4) - 2) * (int32_t((i % 16) % 7) - 3);
        } else {
          const int32_t x = int32_t(i % 201) - 100, y = int32_t(i % 129) - 64;
          if (job == 6) expected = x + y;
          else if (job == 9) expected = 32768;
          else {
            const int32_t numerator = x * (job == 7 ? 3 : 7), divisor = job == 7 ? 2 : 8;
            int32_t quotient = numerator / divisor, remainder = numerator % divisor;
            if (remainder < 0) remainder = -remainder;
            if (2 * remainder > divisor || (2 * remainder == divisor && quotient % 2 != 0))
              quotient += numerator < 0 ? -1 : 1;
            expected = quotient + (job == 7 ? int32_t(i % 17) - 8 : 0);
          }
        }
        uint32_t got = virtual_word(0x40030000u + (job - 1) * 0x4000u + i * 4);
        require(got == uint32_t(expected), "independent full result mismatch job=" + std::to_string(job) +
                " word=" + std::to_string(i) + " got=" + std::to_string(int32_t(got)) +
                " expected=" + std::to_string(expected));
        ++checked;
      }
      require(virtual_word(0x40030000u + (job - 1) * 0x4000u + count * 4) == 0xdeadbeefu,
              "result trace tail mutated");
    }
    require(firmware_ok, "firmware result/IRQ mismatch");
    std::printf("M5 ACCEL %s independent_words=%u PASS\n", label, checked);
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
  bool is_table(uint32_t address) const {
    return address >= 0x02000000 && address < 0x02000000 + ptes.size() * 4;
  }
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
    if (!rvalid && read_active && !hold_responses && cycles >= response_after && cycles % 3 != 1) {
      rvalid = true; rlast = read_index + 1 == read_words;
      rdata = is_table(read_address) ? ptes[(read_address - 0x02000000u) / 4] :
              memory[(read_address - 0x10000000u) / 4 + read_index];
    }
    if (pending_b && !hold_responses && cycles >= response_after && cycles % 3 == 0) { pending_b = false; bvalid = true; }
    top.m_arready_i = !read_active && !write_active && !pending_b && !bvalid && cycles % 3 != 0;
    top.m_awready_i = !read_active && !write_active && !pending_b && !bvalid && cycles % 4 != 0;
    top.m_wready_i = write_active && cycles % 3 != 0;
    top.m_rvalid_i = rvalid; top.m_rdata_i = rdata; top.m_rresp_i = 0; top.m_rid_i = 0; top.m_rlast_i = rlast;
    top.m_bvalid_i = bvalid; top.m_bresp_i = 0; top.m_bid_i = 0;
  }
};

int main(int argc, char **argv) {
  try {
    require(argc == 2 || argc == 3, "usage: Vpa_m5_cluster_top firmware.bin [model.bin for startup test]");
    std::ifstream source(argv[1], std::ios::binary);
    require(bool(source), "firmware image missing");
    std::vector<uint8_t> image((std::istreambuf_iterator<char>(source)), std::istreambuf_iterator<char>());
    Simulation sim(argc, argv);
    if (argc == 3) {
      sim.runtime_startup(image, argv[2]);
      sim.top.final(); return 0;
    }
    sim.configure(false); sim.load(image); sim.start(); sim.complete("initial");
    sim.configure(true); sim.load(image); sim.start();
    sim.wait_for([&] { return sim.packet_write(); }, 5000000, "mover-owned AXI write");
    sim.hold_responses = true; sim.top.memory_abort_i = 1;
    // Core reset is requested by cancellation itself; host has not held CORE_RST yet.
    for (unsigned i = 0; i < 64; ++i) {
      sim.tick(); require(sim.top.transfer_cancel_o && !sim.top.memory_quiesced_o,
                          "cancel/missing B lost ownership");
    }
    require(sim.pending_b, "private W buffer did not drain after accelerator reset");
    sim.hold_responses = false; sim.stop_and_drain();
    sim.configure(true); sim.load(image); sim.start(); sim.complete("remapped_after_packet_abort");
    sim.component_tests();
    std::printf("M5 ACTUAL DUAL-IBEX ACCELERATOR PASS boots=2 packet_abort=1 cycles=%llu pte_reads=%llu data_reads=%llu writes=%llu\n",
                static_cast<unsigned long long>(sim.cycles), static_cast<unsigned long long>(sim.table_reads),
                static_cast<unsigned long long>(sim.data_reads), static_cast<unsigned long long>(sim.writes));
    sim.top.final(); return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "M5 ACTUAL DUAL-IBEX ACCELERATOR FAIL: %s\n", error.what()); return 1;
  }
}
