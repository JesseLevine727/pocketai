# M2 GEMM architecture contract

## Scope

M2 adds a descriptor-driven 16x16 signed-int8 GEMM engine and an A9/DDR stream
path. It does not add the M3 SFPU or change the M1 firmware result ABI.

The engine exposes a logical 16x16 output tile and contains a 4x16 physical
array: 64 soft 8x8 multipliers and 64 signed 25-bit accumulators. The logical
rows are processed in consecutive groups of four. One K position may be
accepted per cycle, so a full tile performs 64 useful MACs per
compute cycle after pipeline fill. The 25-bit accumulator safely covers the
maximum M2 dot-product magnitude defined in `NUMERICS.md`. Vivado is required
to map every multiplier into LUT fabric; DSP48 use remains a hard failure.
Qualification covers `MaxM=16`, `MaxN=16`, `MaxK=768`, and `PhysicalRows=4`;
other elaboration parameter combinations have not been qualified.

An initial 16x16 physical-array implementation synthesized to 55,474 LUTs
(104.27% of the Zynq-7020) before placement and could not be implemented. A
pipelined 8x16 revision synthesized to 34,307 LUTs (64.49%). That exploratory
run was stopped before final routing and is not evidence of a timing limit.
The 4x16 physical array is the selected M2 architecture; it
preserves the 16x16 descriptor/tile contract and exact result while trading
peak throughput for routability and reproducible timing margin.

Two tile slots own independent A, B, and packed-C buffers. Loading one slot,
computing another, and draining a completed slot may overlap. Descriptors,
input packets, and output packets remain strictly ordered. AXI Stream
ready/valid backpressure may pause either transfer for an arbitrary number of
cycles without changing a result.

## Descriptor and MMIO ABI

The accelerator is a fourth M1 shared-bus device at fabric offset `0x00013000`
(A9 physical address `0x43c13000`). Registers are 32-bit:

| Offset | Access | Register |
|---|---|---|
| `+0x00` | RO | ID = `0x50414732` (`PAG2`) |
| `+0x04` | RO | Status |
| `+0x08` | RW | Staging M |
| `+0x0c` | RW | Staging N |
| `+0x10` | RW | Staging K |
| `+0x14` | RW | Staging flags; must be zero |
| `+0x18` | RW | Staging software tag |
| `+0x1c` | WO | Command strobes |
| `+0x20` | RO | Most recently completed tag |
| `+0x24` | RO | Most recently completed descriptor's compute/pack cycles |
| `+0x28` | RO | Most recently completed descriptor's active MACs (`M*N*K`) |
| `+0x2c` | RO | Input words implied by the staging dimensions |
| `+0x30` | RO | Output words implied by the staging dimensions |
| `+0x34` | RO | Completed descriptor count |
| `+0x38` | RO | Sticky error code |
| `+0x3c` | RO | Capabilities: max K, max N, max M |
| `+0x40` | RW | Interrupt enable, bit 0 |

Command bit 0 submits an atomic copy of the staging registers. Bit 1 clears the
sticky done flag. Bit 2 clears an error and aborts all queued/in-flight slots.
Software issues one command action per write.
The staging bank has one software owner at a time. Multiple producers (A9 or
either hart) must serialize the complete staging-and-submit sequence with a
software lock; shared-bus arbitration alone does not make a multiword
descriptor update atomic.
Dimension staging registers retain all 32 written bits and honor each byte
enable. Submission validates the full values before narrowing them to internal
indices, so high-bit values cannot alias a legal small dimension. Input/output
word counts are defined only when the staging dimensions are legal.

Status bits are:

| Bits | Meaning |
|---|---|
| 0 | A descriptor slot is available |
| 1 | One or more slots are occupied |
| 2 | Completion is sticky |
| 3 | Error is sticky |
| 4 | Input stream ready |
| 5 | Output stream valid |
| 9:8 | Occupied slot count |

The interrupt is level-sensitive and equals `(done || error) && irq_enable`.
It may be ORed with the existing mailbox external interrupt at each hart; M1 is
unchanged while the accelerator interrupt is disabled.

The error flag remains set until command bit 2 is written. A descriptor error
blocks new submissions but does not discard work already queued; a later
stream-framing error invalidates that work and replaces the descriptor error
code. A framing error takes precedence if both occur on the same cycle.

Error codes are:

| Code | Meaning |
|---:|---|
| 1 | Illegal M, N, or K |
| 2 | Nonzero reserved flags |
| 3 | Submit attempted with both slots occupied |
| 4 | Input word had `TKEEP != 0xf` |
| 5 | Input packet asserted `TLAST` early |
| 6 | Input packet omitted `TLAST` on its final word |

After a stream framing error, input is discarded through `TLAST` when needed.
Software must stop/reset both associated DMA channels before clearing the
error. Command bit 2 unconditionally clears the drain state as well as aborting
all slots, so recovery does not depend on a malformed source eventually sending
`TLAST`. System reset also restores the empty engine.

## Execution and performance counters

A submitted descriptor reserves the next empty slot. The matching input packet
loads that slot in submission order. A shared arithmetic pipeline consumes one
K position per cycle, then packs eight 32-bit output words per active row into
the slot's C buffer. Output packets drain in descriptor order.

`completed_tag`, `last_cycles`, and `last_macs` update together on the final
output-stream handshake. Counts belong to that completed descriptor even when
the next tile has already finished computing. They are retained across abort
and cleared by system reset. `completed_count` counts final output handshakes;
an aborted tile does not increment it.

`last_cycles` counts arithmetic pipeline and result-packing cycles, excluding
time waiting for input data or output backpressure. `last_macs` counts only
active `M*N*K` operations. Reported accelerator throughput is
`last_macs * fabric_hz / last_cycles`. End-to-end performance must separately
report DMA transfer time so computation and DDR/stream bottlenecks are visible.
For the fixed physical array and registered soft-multiply pipeline, the exact
no-stall counter value is `ceil(M/4)*(K+6) + 8*M` cycles. An operand-register
stage separates BRAM/slot/row/byte selection from the four arithmetic stages;
pipeline filling costs six cycles per row group including the BRAM read.

## PYNQ integration target

The A9 controls descriptors over the existing GP0 AXI-Lite path. An AXI DMA
reads packed A/B packets from DDR3 through a PS high-performance slave port and
streams them into the engine; the return channel writes packed C packets back
to DDR3. The Python runner uses physically contiguous PYNQ buffers, validates
every result against `ref/gemm_ref.py`. Simulation also checks padded output
lanes with deliberately nonzero input padding.

After each DMA result, the A9 publishes the packed values through GP0 into the
shared scratchpad. The complete 16x768 int16 result occupies fabric offsets
`0x4000..0x9fff` (`0x43c04000..0x43c09fff` physically), in row-major order with
a 1536-byte row stride. The runner verifies all 6144 shared words by readback.
This is an A9-mediated copy; the DMA does not directly address the scratchpad.
The region is disjoint from the M1 result block at `0xd000` and its stacks.
Both harts are held in reset during the projection board benchmark; the M1
board workload runs separately on the identical overlay. The cluster simulator
also computes a partial GEMM and publishes/reads its result over AXI while
both harts execute their normal acceptance firmware.

The representative board workload is a batch of 16 activation rows multiplied
by a 768x768 projection matrix. It is decomposed into 48 descriptors with
`M=16`, `N=16`, and `K=768`, so all 64 physical MAC lanes are active in four row
groups and every weight in
the projection is streamed exactly once. Timing, DMA bandwidth, accelerator
cycles, end-to-end latency, and achieved MAC/s are recorded independently.
MM2S timing includes PYNQ cache flush, transfer launch, and Python polling;
it is observed software-driven transfer throughput, not an isolated DDR3 peak.
End-to-end timing includes descriptor writes, input-buffer copies, DMA,
validation, and shared-memory publication, but excludes NumPy reference
generation, overlay programming, and allocation. Accelerator throughput uses
measured cycle counters and the qualified fabric frequency. At M=16, K=768,
each tile takes 3224 compute/pack cycles (154752 across all 48 tiles), giving
5.793 GMAC/s of accelerator throughput at 95 MHz before transfer overhead.
The original 256-lane estimate of approximately 25 GMAC/s is not an M2 result.

## Closure gates

- At least 1,000 deterministic randomized tiles plus directed extremes match
  the Python reference exactly.
- Reset, malformed descriptors, framing errors, descriptor capacity, and
  arbitrary input/output stalls are self-checked.
- The complete M1 local and compliance gates remain passing.
- The clean PYNQ-Z1 implementation is fully routed at exactly 95 MHz with
  setup WNS >= +0.250 ns, TNS zero, positive hold slack, no DSP48 primitives,
  no DRC errors, and no unreviewed warnings.
- The exact accepted overlay passes the 768x768 physical-board workload over
  SSH. The +0.500 ns margin and 100 MHz remain stretch targets.
