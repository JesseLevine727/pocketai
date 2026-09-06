#include "Vpa_m5_mmio_cancel.h"
#include "verilated.h"
#include <cstdint>
#include <cstdio>
#include <stdexcept>

int main(int argc, char **argv) {
  try {
    VerilatedContext context; context.commandArgs(argc, argv);
    Vpa_m5_mmio_cancel top(&context);
    top.clk_i = 0; top.rst_ni = 0; top.cancel_i = 0; top.req_i = 0;
    top.engine_rvalid_i = 0; top.engine_rdata_i = 0; top.engine_err_i = 0;
    top.eval(); top.clk_i = 1; top.eval(); top.clk_i = 0; top.eval(); top.rst_ni = 1;
    uint32_t seed = 0x4d354d4d, requests = 0, cancelled = 0, successful = 0;
    bool previous_request = false, previous_cancel = false;
    for (unsigned cycle = 0; cycle < 10000; ++cycle) {
      seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
      top.req_i = (seed & 3) != 0; top.cancel_i = (seed & 12) == 0;
      top.eval();
      // Cancellation can arrive between request capture and response sampling.
      if (bool(top.rvalid_o) != previous_request ||
          (previous_request && (previous_cancel || top.cancel_i) && (!top.err_o || top.rdata_o != 0)))
        throw std::runtime_error("pending response lost during cancellation");
      const bool request = top.req_i, cancel = top.cancel_i;
      if (bool(top.engine_req_o) != (request && !cancel))
        throw std::runtime_error("cancelled request reached engine");
      top.clk_i = 1; top.eval();
      // Independent fixed-latency engine model: synchronous reset on cancel.
      top.engine_rvalid_i = request && !cancel;
      top.engine_rdata_i = cancel ? 0 : seed;
      top.engine_err_i = !cancel && (seed & 32) != 0;
      top.eval(); top.clk_i = 0; top.eval();
      if (bool(top.rvalid_o) != request) throw std::runtime_error("response latency changed");
      if (request) {
        ++requests;
        const bool error = cancel || top.engine_err_i;
        if (bool(top.err_o) != error || top.rdata_o != (error ? 0u : seed))
          throw std::runtime_error("response data/error mismatch");
        if (cancel) ++cancelled; else ++successful;
      }
      previous_request = request; previous_cancel = cancel;
      context.timeInc(1);
    }
    std::printf("M5 MMIO CANCEL PASS cycles=10000 requests=%u cancelled=%u engine_responses=%u\n",
                requests, cancelled, successful);
    top.final(); return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "M5 MMIO CANCEL FAIL: %s\n", error.what()); return 1;
  }
}
