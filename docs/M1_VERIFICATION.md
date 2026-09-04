# M1 verification record

## Closure

M1 closed on 2026-09-04. The qualified design is a two-hart RV32IMC cluster
running at exactly 95 MHz on the PYNQ-Z1 programmable logic. It passed the
local RTL/firmware gate, the pinned ISA suites, two clean Vivado builds, and a
physical-board test of each clean overlay.

The mandatory timing gate is +0.250 ns setup WNS at 95 MHz, zero setup TNS,
positive hold slack, zero DSP48 primitives, and no DRC errors. The final routed
design has +0.330 ns setup WNS, 0.000 ns setup TNS, and +0.076 ns hold WNS.
The preferred +0.500 ns margin and the 100 MHz stretch target are not M1
claims.

## Acceptance matrix

| Gate | Required result | Recorded result |
|---|---|---|
| Dependency integrity | Exact pinned revisions and patches | PASS |
| Focused RTL tests | Shared-bus and mailbox tests | PASS |
| Firmware simulation | Single-core boot and dual-hart 10,000-round workload | PASS |
| RTL lint | Fatal warnings, with only the documented upstream waiver | PASS |
| ISA tests | All required tests pass; only four named expected failures | PASS |
| FPGA timing | 95 MHz, WNS >= +0.250 ns, TNS 0, hold positive | PASS: +0.330/0.000/+0.076 ns |
| FPGA implementation | Fully routed, DSP48 0, DRC errors 0 | PASS |
| Clean reproducibility | Two clean builds meet every implementation gate | PASS |
| Physical board | Exact clean-built overlay passes over SSH | PASS twice |

No M2 accelerator RTL is included in this qualification.

## Qualified configuration

The two harts use the same lowRISC Ibex configuration:

- base ISA RV32I with M and compressed Zca instructions (the M1 RV32IMC
  contract);
- slow iterative multiplier/divider, FPGA register file, and writeback stage;
- two-cycle branch handling;
- no branch predictor, instruction cache, PMP, SecureIbex, bit-manipulation
  extension, floating point, or DSP48 multiplication.

External inputs are locked and checked before every aggregate run:

| Dependency | Revision |
|---|---|
| lowRISC Ibex | `34b0705760ef3dfa00e99637432473d2be8f22f3` |
| riscv-compliance | `844c6660ef3f0d9b96957991109dfd80cc4938e2` |

The required local changes are represented by
`patches/ibex-34b0705.m1-timing.diff` and
`patches/riscv-compliance-844c6660.local-patches.diff`.
`scripts/check_deps.sh all` rejects a wrong revision, a partial patch, or any
unrecorded difference in either checkout.

Qualification tools were:

| Tool | Version |
|---|---|
| Vivado | 2025.1, build 6140274 |
| Verilator | 5.020 |
| FuseSoC | 2.4.6 |
| RISC-V GCC | 16.1.0 (`g6afcc4f6d`) |
| Python | 3.12.3 |
| PYNQ board image/library | PYNQ 3.1.1 |

## Architecture and bus contract

Five requesters share one registered, round-robin, 32-bit bus: the A9-side
AXI4-Lite bridge, the instruction and data ports of hart 0, and the instruction
and data ports of hart 1. Each requester may have one transaction captured by
the bus. Address/control are registered before device issue, so a requester may
legally present a new request immediately after a grant without duplicating or
losing the prior transfer.

The cluster contains one shared 64 KiB BRAM scratchpad, one 64-byte console
FIFO, and two one-word mailboxes. Mailbox pending state is sticky and drives a
level machine-external interrupt until software writes the direction's W1C
acknowledge bit.

The AXI-visible map is:

| A9 physical address | Fabric offset | Function |
|---|---|---|
| `0x43c00000..0x43c0ffff` | `0x00000000..0x0000ffff` | Shared 64 KiB scratchpad |
| `0x43c11000` | `0x00011000` | Console data: enqueue on write, dequeue on read |
| `0x43c11004` | `0x00011004` | Console status: count, overflow, software-done |
| `0x43c11008` | `0x00011008` | Console control: done/set and overflow/clear |
| `0x43c12000` | `0x00012000` | Mailbox hart 0 to hart 1 |
| `0x43c12004` | `0x00012004` | Mailbox hart 1 to hart 0 |
| `0x43c12008` | `0x00012008` | Mailbox pending status |
| `0x43c1200c` | `0x0001200c` | Mailbox W1C acknowledge |
| `0x43c20000` | n/a | AXI GPIO core-reset control |

The cluster AXI window is 128 KiB at `0x43c00000`. The reset GPIO is a separate
64 KiB window. Holding core reset low leaves the scratchpad and A9 AXI path
operational; the board runner loads and reads back all 65,536 firmware bytes
before releasing both harts.

## Result ABI

The result block occupies 13 words in shared scratchpad at fabric offset
`0x0000d000`. The board test accepts the run only if every word below has the
expected value.

| Offset | Name | Expected value |
|---|---|---|
| `0x0000d000` | `done0` | `0x4d314830` |
| `0x0000d004` | `done1` | `0x4d314831` |
| `0x0000d008` | `count0` | 10,000 |
| `0x0000d00c` | `count1` | 10,000 |
| `0x0000d010` | `msgsum0` | `0x468aad43` |
| `0x0000d014` | `msgsum1` | `0x85558c0a` |
| `0x0000d018` | `work0` | `0x29c4c2c2` |
| `0x0000d01c` | `work1` | `0xa3e316ec` |
| `0x0000d020` | `error0` | 0 |
| `0x0000d024` | `error1` | 0 |
| `0x0000d028` | `ready0` | `0x49525152` |
| `0x0000d02c` | `ready1` | `0x49525152` |
| `0x0000d030` | `host_ack` | host writes `0x484f5354` |

Each hart first runs a deterministic integer/stack-memory workload. Hart 0
then sends sequence values 1 through 10,000; hart 1 validates each interrupt
and returns the sequence XOR `0xa5a50000`. Both harts publish independent
counts, rolling message checksums, workload checksums, and error words. After
validating them, the A9 writes `host_ack`; hart 1 then sets the console-done
bit. This prevents an early or stale pair of done words from passing.

## Reproduction commands

From the repository root:

```bash
source env.sh
PA_CLEAN=1 bash sim/run_m1.sh
PA_CLEAN=1 bash scripts/run_compliance.sh

export PYNQ_BOARD_REPO=/path/to/board_files
PA_CLEAN=1 bash zynq/build_m1.sh

export PYNQ_HOST=xilinx@pynq-host-or-address
bash zynq/run_m1_board.sh
```

The board command copies the bitstream, hardware handoff, firmware, and Python
runner over SSH, then programs the overlay with the PYNQ API. The stock image
prompts for normal `sudo` authentication. JTAG is not used.

## Recorded evidence

The final local aggregate run printed:

```text
PA_SHARED_BUS PASS
MAILBOX PASS
PA M1 BOOT
AXI OK
M1 RESULTS OK count0=10000 count1=10000 msg0=468aad43 msg1=85558c0a work0=29c4c2c2 work1=a3e316ec
[run_cluster] PASS
M1 LINT PASS
M1 LOCAL PASS
```

The final compliance run printed:

```text
M1 COMPLIANCE PASS rv32imc=25/25 rv32im=8/8 rv32i=44/48+4-xfail rv32Zicsr=6/6 rv32Zifencei=1/1
```

The four explicit expected failures are `I-EBREAK-01`, `I-ECALL-01`,
`I-MISALIGN_JMP-01`, and `I-MISALIGN_LDST-01`. The runner fails if an
expected failure unexpectedly passes, if a non-whitelisted test fails, or if
the number of tests changes.

The final clean Vivado run printed:

```text
M1 VIVADO PASS clock_mhz=95.0 setup_wns_ns=0.330 setup_tns_ns=0 min_setup_slack_ns=0.250 hold_wns_ns=0.076 dsp48=0 drc_errors=0 reviewed_drc_warnings=1 preferred_margin_0p500ns=0
```

The routed design contains 10,740 routable nets, all fully routed, and no nets
with routing errors. Post-route utilization is:

| Resource | Used | Available | Utilization |
|---|---:|---:|---:|
| Slice LUTs | 7,436 | 53,200 | 13.98% |
| Slice registers | 4,110 | 106,400 | 3.86% |
| Block RAM tiles | 16 | 140 | 11.43% |
| DSPs | 0 | 220 | 0.00% |
| MMCM | 1 | 4 | 25.00% |

The exact final artifacts have these SHA-256 digests:

```text
6e63c6e4ee3d18c7136b878eae67716b54b2a63bb1c46a139f9fe16107d8fc18  m1_pynq.bit
d9c949f1210ac8c5ef0483acdecd0252a1f6950d49f131ef07af57b9b7061e47  m1_pynq.hwh
1c877c4ccf82060ae3dd71645fe5e1892215b03d95fad1edb2e020ca6f85dcc0  cluster.bin
```

The physical-board run of that overlay printed:

```text
M1 console:
H0 READY
H1 READY
M1 results: count0=10000 count1=10000 msg0=468aad43 msg1=85558c0a work0=29c4c2c2 work1=a3e316ec
M1 BOARD PASS elapsed_s=0.047
```

Two clean implementation runs independently produced +0.330 ns setup WNS,
0.000 ns setup TNS, +0.076 ns hold WNS, zero DRC errors, and a board-passing
overlay. Bit-for-bit reproducibility is not asserted because Vivado-generated
artifacts carry run metadata; reproducibility here means a clean checkout with
the pinned inputs repeatedly meets the declared gates.

## Timing method and reviewed warnings

The PS fabric clock remains at 100 MHz and drives a Clocking Wizard. The cluster,
AXI interfaces, SmartConnect, GPIO, and reset controller all use its exact
95 MHz output (10.526 ns period). During implementation only, the build applies
0.526315 ns of additional setup uncertainty to encourage a 100 MHz-equivalent
placement. It removes that artificial uncertainty before writing the
qualification reports and checking the exact 95 MHz result.

The final DRC has zero errors and zero critical warnings. It contains one
reviewed `RTSTAT-10` warning covering 15 unloaded SmartConnect-generated
`mi_handler_m_sc_areset_pipe` nets. The build gate permits only this exact DRC
warning and rejects any additional or different warning.

The batch log also contains these reviewed tool messages, which are separate
from the final DRC result:

- `PSU-1` and `PSU-2` report the negative DDR DQS values supplied by the
  Digilent PYNQ-Z1 board preset. The Linux/PYNQ board completed the physical
  acceptance test with that preset.
- `Designutils 20-1280` refers to a SmartConnect-generated board XDC whose only
  content is a physical-constraints comment for a module optimized away.
- `Timing 38-282` is emitted while opening the implementation run under the
  temporary 100 MHz-equivalent margin constraint. The constraint is then
  removed; the final exact-95-MHz report above has positive setup and hold slack.

The timing report has no unclocked registers, no constant-clock registers, no
unconstrained internal endpoints, no generated-clock errors, and no timing
loops.

## M1 boundary

M1 proves the shared-bus, scratchpad, console, mailbox/interrupt, two-hart
firmware, AXI host path, and physical PYNQ-Z1 integration. The console is an
AXI-readable synthesizable FIFO, not an external UART pin. The firmware workload
is CoreMark-lite-style coverage, not an official CoreMark score. Cache,
coherence, accelerator descriptors, GEMM, weight streaming, and all M2
performance claims remain outside M1.
