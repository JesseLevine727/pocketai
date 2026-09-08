# M6 chip-interface contract (implementation in progress)

The chip retains the native 32-bit AXI master as its external-memory boundary.
An external controller must supply the full 266,289,152-byte arena and implement
the existing AXI burst, response, ID and abort/drain contracts. This is not an
on-chip DDR PHY or a claim that a commodity SPI flash can replace writable KV
memory. A controller/FPGA with external RAM is required for full-model operation.
The qualified functional test already models that memory endpoint; it does not
measure a physical ASIC-to-memory link.

Use a low-pin-count SPI slave to load firmware, access accelerator registers
and configure the memory boundary. A UART transmitter drains the existing CPU
console FIFO when enabled. These peripherals do not compute tensors or replace
either hart. The native-AXI physical core is an intermediate hardening boundary;
SPI/UART logic and actual Sky130 I/O cells still require chip-level integration.
No package, external controller, pad-ring or chip result is qualified here.

## SPI transport

Mode 0, most-significant bit first, one 72-bit frame per chip-select assertion.
SCLK must not exceed system clock / 8; chip select must remain high for at
least eight system cycles between frames. Allow at least four system cycles
from chip-select assertion to the first rising SCLK edge. SCLK, chip select and MOSI are
synchronized into the system clock. Clock and chip reset are separate pins.

A request frame is command (8 bits), byte address (32), data (32). Command
`0x80` reads a word; `0x90 | byte_mask` writes selected bytes. `0x00` polls
without starting an operation. Only aligned word addresses are accepted by the
register engine. The SPI receiver commits a command only when chip select
deasserts after exactly 72 bits, so a partial or oversized frame has no bus
side effect. A new command while busy is rejected and sets an overrun flag.

At frame start, the slave snapshots the previous response into MISO: status
(8), result (32), then 32 zero bits. Status bit 7 means a completed response is
available, bit 6 means busy, bit 5 reports rejected/invalid traffic, and bits
1:0 carry the AXI response. A newly accepted command clears response-valid;
poll until it returns. Only one command may be outstanding. Poll frames never
repeat writes. The response remains readable until another command is accepted.

Addresses `0x00000000..0x0001ffff` use the existing cluster AXI-Lite map.
Local control registers are:

| Address | Register |
|---|---|
| `0x20000` | Control: cluster reset released (0), harts released (1), translation enabled (2), flush (3), abort (4), UART console drain enabled (5) |
| `0x20004` | Page-table base, 32 bits |
| `0x20008` | External arena size in bytes, 32 bits |
| `0x2000c` | Read-only existing eight-bit cluster status |
| `0x20010` | UART system-clock cycles per bit; at least 8 |

Reset holds both harts and cluster in reset, translation disabled and memory
abort asserted. Firmware and page tables must be provisioned before release.
The external controller supplies the arena/model bytes directly; SPI loads
scratchpad firmware and can use the existing DMA to move weights into the
accelerator. Loading time and memory bandwidth must be reported separately
from compute-only throughput. Native AXI has a theoretical payload ceiling of
four bytes per system cycle; that is an interface bound, not measured bandwidth.

UART uses 8-N-1. Its divider resets to 217 cycles/bit (approximately 115.2 kbaud
at a 25-MHz system clock, or approximately 57.6 kbaud at the current 12.5-MHz
candidate). Software must set the divider for any other
qualified frequency. Automatic draining reads the original console status/data
registers through the same AXI-Lite master, yielding priority to SPI. Disable
automatic draining before using SPI to consume console DATA yourself.

The [reference supervisor](../scripts/m6_spi_host.py) accepts a user-supplied
SPI transport without opening hardware on import. `prepare()` holds the harts,
asserts abort and waits for actual memory quiescence before host MMIO access.
`start()` clears latched cancellation under cluster reset, completes the flush,
then releases both harts. Do not reset the cluster or alter page tables while
external memory still owns transactions. The raw control-register interface,
like the original FPGA GPIO, requires this software ownership discipline.

The first digital chip-core smoke used Verilator's default two-state initial
edge behavior, which did not trigger asynchronous reset initialization on
internally held-low hart reset nets. Enabling `--x-initial-edge` models the
initial X-to-low reset transition; the unchanged RTL and known answers then
pass. This simulator setting is not a hardware reset sequencer or a pad test.

## Required finite checks

Check complete/partial/oversized frames, busy rejection, asynchronous phase,
all byte masks, alignment and invalid addresses, independent AXI AW/W
backpressure, held responses, UART output order and reset. Then exercise the
loader against actual full-core scratchpad readback and a finite dual-hart
known-answer workload. Component-only tests do not replace the already-passing
full-system numerical/lifecycle oracle or future routed timing checks.
