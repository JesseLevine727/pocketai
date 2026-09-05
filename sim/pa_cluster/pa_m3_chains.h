// Included within pa_cluster.cc's test namespace after the AXI helpers.
bool m3_chain_tests(pa_cluster_top& top) {
  auto write = [&](uint32_t address, uint32_t value) {
    uint8_t response = 0xff;
    axi_idle(top);
    if (!axi_write(top, address, value, 15, &response) || response)
      throw std::runtime_error("M3 chain AXI write failed");
    axi_idle(top);
  };
  auto read = [&](uint32_t address) {
    uint32_t value = 0; uint8_t response = 0xff;
    axi_idle(top);
    if (!axi_read(top, address, value, &response) || response)
      throw std::runtime_error("M3 chain AXI read failed");
    axi_idle(top); return value;
  };
  try {
    if (read(0x14000) != 0x50415333 || read(0x13044) != 1 || read(0x13048) != 3072)
      throw std::runtime_error("M3 integration capabilities missing");
    // Exercise the real inter-engine route interlock, not a standalone mock.
    write(0x13008, 1); write(0x1300c, 1); write(0x13010, 1);
    write(0x13014, 0); write(0x1301c, 1);
    write(0x14050, 1);
    if (read(0x14038) != 9 || read(0x14050) != 0)
      throw std::runtime_error("GEMM-busy routing interlock failed");
    write(0x1301c, 4); write(0x1401c, 2); write(0x14050, 1);
    write(0x14008, 7); write(0x1400c, 1); write(0x1401c, 1);
    write(0x14050, 0);
    if (read(0x14038) != 9 || read(0x14050) != 1)
      throw std::runtime_error("SFPU-busy routing interlock failed");
    write(0x1401c, 4); write(0x14050, 0);

    const char* path = std::getenv("PA_M3_CHAIN_VECTORS");
    if (!path) throw std::runtime_error("PA_M3_CHAIN_VECTORS is missing");
    std::ifstream file(path, std::ios::binary);
    auto word = [&]() {
      uint32_t value = 0; file.read(reinterpret_cast<char*>(&value), 4);
      if (!file) throw std::runtime_error("truncated chain vectors"); return value;
    };
    if (word() != 0x334e4843) throw std::runtime_error("bad chain vector magic");
    const unsigned steps = word(); uint32_t rng = word();
    auto random = [&]() { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; };
    std::map<unsigned, std::vector<uint32_t>> tensors;
    unsigned gemms = 0, sfpus = 0, patches = 0;
    const auto gemm_base_count = read(0x13034), sfpu_base_count = read(0x14034);
    for (unsigned step = 0; step < steps; ++step) {
      uint32_t m[16]; for (auto& value : m) value = word();
      std::vector<uint32_t> input(m[6]), expected(m[7]), observed;
      for (auto& value : input) value = word();
      for (auto& value : expected) value = word();
      if (m[9]) {
        const auto golden_input = input;
        const auto& source = tensors.at(m[9]);
        if (source.size() < m[11]) throw std::runtime_error("chain source is incomplete");
        for (unsigned i = 0; i < m[11]; ++i) {
          if (m[10] == 1) input[i] = source[i];
          else if (m[10] == 2) {
            const unsigned shift = (i % 4) * 8;
            input[i / 4] = (input[i / 4] & ~(0xffu << shift)) | ((source[i] & 0xff) << shift);
          } else if (m[10] == 3) input[i] = (input[i] & 0x10000) | (source[i] & 0xffff);
          else throw std::runtime_error("invalid chain patch mode");
        }
        if (input != golden_input) throw std::runtime_error("actual intermediate differs from chain reference");
        ++patches;
      }
      const uint32_t base = m[0] ? 0x14000 : 0x13000;
      write(0x14050, m[0]);
      if (read(0x14050) != m[0] || read(0x14038)) throw std::runtime_error("route selection failed");
      for (unsigned field = 0; field < 4; ++field) write(base + 8 + field * 4, m[field + 1]);
      write(base + 24, m[5]);
      if (read(base + 0x2c) != input.size() || read(base + 0x30) != expected.size())
        throw std::runtime_error("chain packet count mismatch");
      write(base + 28, 1);
      for (unsigned i = 0; i < input.size(); ++i) {
        if ((random() & 3) == 0) clock(top);
        top.gemm_s_axis_data_i = input[i]; top.gemm_s_axis_keep_i = 15;
        top.gemm_s_axis_last_i = i + 1 == input.size(); top.gemm_s_axis_valid_i = 1;
        top.eval(); unsigned timeout = 0;
        while (!top.gemm_s_axis_ready_o && ++timeout < 10000) clock(top);
        if (!top.gemm_s_axis_ready_o) throw std::runtime_error("chain input timeout");
        clock(top); top.gemm_s_axis_valid_i = 0;
      }
      top.gemm_s_axis_last_i = 0;
      bool held = false, held_last = false; uint32_t held_data = 0;
      unsigned timeout = 0;
      while (observed.size() < expected.size()) {
        if (++timeout > m[8] * 3 + m[7] * 20 + 2000) throw std::runtime_error("chain output timeout");
        top.gemm_m_axis_ready_i = (random() & 3) != 0; top.eval();
        if (held && (!top.gemm_m_axis_valid_o || top.gemm_m_axis_data_o != held_data ||
                     bool(top.gemm_m_axis_last_o) != held_last))
          throw std::runtime_error("muxed output changed while stalled");
        if (top.gemm_m_axis_valid_o && top.gemm_m_axis_ready_i) {
          if (top.gemm_m_axis_keep_o != 15 ||
              bool(top.gemm_m_axis_last_o) != (observed.size() + 1 == expected.size()))
            throw std::runtime_error("chain output framing mismatch");
          observed.push_back(top.gemm_m_axis_data_o);
        }
        held = top.gemm_m_axis_valid_o && !top.gemm_m_axis_ready_i;
        held_data = top.gemm_m_axis_data_o; held_last = top.gemm_m_axis_last_o;
        clock(top);
      }
      top.gemm_m_axis_ready_i = 0;
      if (observed != expected) throw std::runtime_error("chain result mismatch step=" + std::to_string(step));
      if (read(base + 0x20) != m[5] || read(base + 0x24) != m[8] || read(base + 0x38))
        throw std::runtime_error("chain completion/counter mismatch step=" + std::to_string(step));
      write(base + 28, 2);
      auto& destination = tensors[m[12]];
      if (destination.size() < m[13] + m[14]) destination.resize(m[13] + m[14]);
      std::copy_n(observed.begin(), m[14], destination.begin() + m[13]);
      if (m[0]) ++sfpus; else ++gemms;
    }
    if (file.peek() != std::ifstream::traits_type::eof()) throw std::runtime_error("trailing chain bytes");
    if (read(0x13034) != gemm_base_count + gemms || read(0x14034) != sfpu_base_count + sfpus)
      throw std::runtime_error("chain completion totals differ");
    // Publish/read back compact int16 results in the shared scratchpad.
    for (unsigned tensor : {9u, 25u}) {
      const auto& values = tensors.at(tensor);
      for (unsigned i = 0; i < values.size(); i += 2) {
        const uint32_t packed = (values[i] & 0xffff) | ((values[i + 1] & 0xffff) << 16);
        const uint32_t address = (tensor == 9 ? 0x5000 : 0x6000) + i * 2;
        write(address, packed);
        if (read(address) != packed) throw std::runtime_error("chain shared publication mismatch");
      }
    }
    write(0x14050, 0);
    std::printf("M3 CLUSTER CHAINS PASS steps=%u gemm=%u sfpu=%u actual_result_patches=%u mlp=1x768x3072x768 attention=1x64x1024x16\n",
                steps, gemms, sfpus, patches);
    return true;
  } catch (const std::exception& error) {
    std::fprintf(stderr, "M3 CLUSTER CHAINS FAIL: %s\n", error.what()); return false;
  }
}
