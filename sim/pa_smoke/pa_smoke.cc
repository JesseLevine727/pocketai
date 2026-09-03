// PocketAI-T M1a boot smoke testbench (Verilator cc mode)
//
// Drives clock/reset via the lowRISC VerilatorSimCtrl, loads the boot ELF into
// RAM through VerilatorMemUtil (--meminit=ram,<file> at run time), and runs
// until the design calls $finish (i.e. the CPU halts via the UART ctrl reg).
//
// The program's UART output is captured by the `simulator_ctrl` module into a
// log file (pa_smoke.log); the run script prints it.
#include "verilator_sim_ctrl.h"
#include "verilator_memutil.h"
#include "verilated_toplevel.h"

int main(int argc, char **argv) {
  pa_smoke_top top;
  VerilatorMemUtil memutil;
  VerilatorSimCtrl &simctrl = VerilatorSimCtrl::GetInstance();
  simctrl.SetTop(&top, &top.IO_CLK, &top.IO_RST_N,
                 VerilatorSimCtrlFlags::ResetPolarityNegative);

  MemArea ram("TOP.pa_smoke_top.u_ram.u_ram", 32 * 1024 / 4, 4);
  memutil.RegisterMemoryArea("ram", 0x0, &ram);
  simctrl.RegisterExtension(&memutil);

  return simctrl.Exec(argc, argv).first;
}
