#include "Vpa_m6_chip_core.h"
#include "verilated.h"
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <vector>

static void check(bool value, const char* why) { if (!value) throw std::runtime_error(why); }
struct Simulation {
  VerilatedContext context;
  Vpa_m6_chip_core top{&context};
  uint64_t ticks=0, frames=0;
  bool previous_tx=true;
  int uart_wait=0, uart_bit=-1;
  uint8_t uart_byte=0;
  std::vector<uint8_t> uart;
  Simulation() {
    top.clk_mem_i=0; top.rst_ni=1;
    top.spi_cs_ni=1; top.spi_sclk_i=0; top.spi_mosi_i=0;
    top.m_axi_awready=0; top.m_axi_wready=0; top.m_axi_bresp=0;
    top.m_axi_bid=0; top.m_axi_bvalid=0; top.m_axi_arready=0;
    top.m_axi_rdata=0; top.m_axi_rresp=0; top.m_axi_rid=0;
    top.m_axi_rlast=0; top.m_axi_rvalid=0;
    top.eval(); top.rst_ni=0; top.eval(); step(40); top.rst_ni=1; step(40);
  }
  void step(unsigned count) {
    for(unsigned i=0;i<count;i++) {
      top.clk_mem_i=!top.clk_mem_i; context.timeInc(10); top.eval(); ++ticks;
      check(!top.m_axi_awvalid && !top.m_axi_arvalid, "unexpected external-memory request in SRAM-only smoke");
      bool tx=top.uart_tx_o;
      if(uart_bit<0 && previous_tx && !tx) { uart_bit=0; uart_wait=48; uart_byte=0; }
      else if(uart_bit>=0 && --uart_wait==0) {
        if(uart_bit<8) { uart_byte|=uint8_t(tx)<<uart_bit; ++uart_bit; uart_wait=32; }
        else { check(tx,"UART stop bit"); uart.push_back(uart_byte); uart_bit=-1; }
      }
      previous_tx=tx;
    }
  }
  uint64_t frame(uint8_t command, uint32_t address, uint32_t data) {
    uint64_t response=0;
    top.spi_sclk_i=0; top.spi_cs_ni=0; step(20);
    for(int bit=71;bit>=0;bit--) {
      top.spi_mosi_i=bit>=64 ? (command>>(bit-64))&1 :
                        bit>=32 ? (address>>(bit-32))&1 : (data>>bit)&1;
      step(20); top.spi_sclk_i=1; top.eval();
      if(bit>=32) response=(response<<1)|top.spi_miso_o;
      step(20); top.spi_sclk_i=0; top.eval();
    }
    step(20); top.spi_cs_ni=1; step(40); ++frames;
    return response;
  }
  uint32_t transaction(uint8_t command, uint32_t address, uint32_t data=0) {
    frame(command,address,data);
    for(unsigned n=0;n<20;n++) {
      uint64_t response=frame(0,0,0);
      if(response&(uint64_t(1)<<39)) {
        check((response>>32)==0x80,"SPI response error"); return uint32_t(response);
      }
    }
    throw std::runtime_error("SPI response timeout");
  }
  void write(uint32_t address,uint32_t data) { transaction(0x9f,address,data); }
  uint32_t read(uint32_t address) { return transaction(0x80,address); }
};
int main(int argc,char** argv) {
  try {
    check(argc==2,"firmware binary argument required");
    std::ifstream input(argv[1],std::ios::binary);
    check(bool(input),"firmware open");
    std::vector<uint8_t> firmware{std::istreambuf_iterator<char>(input),{}};
    check(firmware.size()>128 && firmware.size()<1024 && firmware.size()%4==0,"firmware bounds");
    Simulation sim;
    check(sim.read(0x20000)==0x10,"reset control readback");
    sim.write(0x20000,1); // Cluster accessible; harts remain held, abort released.
    sim.write(0x20010,8); // Fast finite UART check: system clock / 8.
    for(size_t offset=0;offset<firmware.size();offset+=4) {
      uint32_t word=uint32_t(firmware[offset]) | uint32_t(firmware[offset+1])<<8 |
                    uint32_t(firmware[offset+2])<<16 | uint32_t(firmware[offset+3])<<24;
      sim.write(uint32_t(offset),word);
      check(sim.read(uint32_t(offset))==word,"SPI-loaded SRAM firmware readback");
    }
    sim.write(0x1000,0); sim.write(0x1004,0);
    sim.write(0x20000,0x23); // Both harts released; UART drains original console.
    sim.step(80000);
    auto h0=sim.read(0x1000), h1=sim.read(0x1004);
    std::printf("M6 CHIP OBSERVED hart0=%u hart1=%u control=%08x status=%08x uart_bytes=%zu\n",
      h0,h1,sim.read(0x20000),sim.read(0x2000c),sim.uart.size());
    check(h0==123*45,"hart0 fast-MUL answer");
    check(h1==124*45,"hart1 fast-MUL answer");
    std::sort(sim.uart.begin(),sim.uart.end());
    check(sim.uart==std::vector<uint8_t>({'0','1'}),"both actual CPU console bytes via UART");
    std::printf("M6 CHIP LOADER PASS firmware_bytes=%zu spi_frames=%llu harts=2 fast_mul=2 uart_bytes=%zu memory_half_ticks=%llu\n",
      firmware.size(),(unsigned long long)sim.frames,sim.uart.size(),(unsigned long long)sim.ticks);
  } catch(const std::exception& e) { std::fprintf(stderr,"M6 CHIP LOADER FAIL: %s\n",e.what()); return 1; }
}
