# M5 autonomous accelerator transfer ABI v1

Status: contract frozen before implementation; standalone mover simulation
passes. Real-operator/queue/platform integration is not yet accepted.
The numerical packet formats remain those of M3. This document specifies the
new mover, not a replacement GEMM/SFPU algorithm or an A9 tensor worker.

## Packet mover

One accepted command owns one complete accelerator input/output packet. It
captures three source address/word-count pairs, one destination address/count,
a 32-bit tag and a nonzero 32-bit cycle deadline. Counts are numbers of 32-bit
words, not bytes. Addresses are device-virtual and word aligned. Each active
range must fit wholly within `0x40000000..0x4fffffff`; the memory translator
still enforces the configured smaller arena and PTE permissions on every burst.

Source 0 is nonempty; optional sources 1 and 2 form a nonempty prefix. Unused
source pairs are exactly zero. Each count and their combined source count are
1..65535; destination count is 1..65535. Invalid commands complete with fault
16, without a memory or accelerator handshake. Command fields are captured
atomically on valid/ready; changing staging fields cannot alter an owned packet.
The command interface is single-outstanding; an enclosing MMIO queue may retain
additional complete descriptors but cannot publish a partial descriptor.

The mover reads source segments in order, splitting at both 256 words and
4-KiB page boundaries. Segment/burst boundaries are invisible to the accelerator:
TKEEP is `f` throughout and TLAST is asserted **only** on the last word of the
last source. This directly streams a prepared A packet plane plus a static B
tile, or the one/two/three SFPU planes, without copying the static weight tile
into an expanded contiguous CPU packet. Firmware still owns dynamic quantization,
metadata and layout preparation. No in-run A9 buffer filling is permitted.

After the complete input packet, the mover receives the exact destination
word count, checking every TKEEP/TLAST, and writes sequentially to destination.
The existing private AXI buffer collects each entire write burst before AW, so
an issued physical burst can drain without accelerator/firmware cooperation.
Completion occurs only after the final memory completion, never merely after
the accelerator's final output beat. Tag, fault and input/output accepted-word
counters remain stable while normal completion waits for its consumer.

The original accelerator descriptor must be committed before starting its
transfer. Route selection must be held for the entire packet, through output
and completion. Queue/control integration must serialize route changes and
accelerator descriptor publication; merely queuing memory ranges cannot choose
or start an operator. The packet mover itself has no raw physical address or
operator-MMIO escape.

## Failure and lifetime

| Fault | Meaning |
|---|---|
| 0 | Success |
| 16 | Invalid packet descriptor; no side effects |
| 17 | External abort |
| 18 | Accelerator output TKEEP/TLAST violation |
| 19 | Internal memory-client beat/completion protocol violation |
| 20 | Packet cycle deadline expired |
| 32 + memory fault | Translation/AXI/arbiter error from the existing memory ABI |

The deadline counts active packet work, including input, compute wait, output,
arbitration and transfer stalls; it does not time normal completion consumption.
Its expiration requests **global abort**, not a fictitious successful drain.
Runtime errors also latch a global-abort request. A supervisor must OR that
request into the memory system's abort and hold a coordinated accelerator-stream
reset during cancellation. It must latch the stopped state until deliberate
recovery; automatically clearing the global abort on a transient condition is
not allowed.

An already-present memory command remains valid until the arbiter accepts it,
even after cancellation; the arbiter then returns the documented cancellation
completion. An accepted memory command stays owned until completion. Missing
memory completion keeps mover busy, even after deadline expiry or abort. No
reset, timeout or status bit fabricates returned DMA ownership. A packet that
has not yet offered a memory command may stop immediately.

After cancellation/drain, the mover enters sticky STOPPED, drops any abandoned
normal completion and admits no new command. Its busy indication may become
zero only after it owns no memory request. Global memory quiescence must still
include the arbiter/bridge, all core paths and any enclosing queue. Restart
requires drained ownership, stopped cores, reset accelerators/mover/queue, and
explicit supervisor release. An isolated mover reset is not an AXI cancellation.

Runtime failure may leave partial destination writes and a partially consumed
accelerator packet. They are **invalid**, not an atomic successful result.
Firmware must publish tensor/KV validity only after successful completion and
must not reuse in-flight storage. Locally rejected malformed descriptors promise
no side effects; later permission/bus failures do not promise rollback.

## Qualification before platform integration

Directed and deterministic randomized tests must check all source counts and
segment boundaries, destination tails, every page/burst split, captured fields,
both stream directions under stalls, completion stalls, invalid descriptors,
memory/stream faults, deadline expiry, abort in every issue/payload/completion
phase, missing-completion retention and recovery only after modeled drain.
Then compose the mover with the real translated memory system and M3 operators,
add MMIO queue/route/IRQ ownership and actual-hart scheduling, and qualify the
full platform lifecycle. This component alone cannot close G2 or prove model
autonomy, kernel ownership, timing or physical performance.

## Core-visible MMIO publication queue v1

The initial transfer queue has **one ownership credit**, including its pending
completion; staging registers are not a second queued command. Hart 1 is the
sole runtime producer/accelerator owner; hart 0 submits work through the existing
mailbox protocol. A9 must not publish runtime descriptors. The existing GEMM
two-slot hardware is preserved, but extra DMA queue depth/overlap is an optional
later optimization, not a requirement for autonomous complete-model execution.

New local window: `0x00015000`, 1 KiB. All offsets are word aligned. Data staging
writes honor byte enables. Read-only or unimplemented register writes, unaligned
accesses, invalid doorbells, START without credit, and ACK without completion
return an MMIO error without altering the currently owned command. They latch a
separate rejection code/counter, not a fabricated packet completion. START
captures every staging field atomically; invalid packet ranges are subsequently
returned by the mover as fault 16, with no transfer side effects.

| Offset | Register |
|---|---|
| 00 | ID, read-only `0x50415435` |
| 04 | STATUS: bit 0 ready, 1 busy, 2 done, 3 stopped, 4 mover fatal-abort request, 5 control abort request, 6 rejection pending |
| 08 / 0c | Source 0 address / words |
| 10 / 14 | Source 1 address / words |
| 18 / 1c | Source 2 address / words |
| 20 / 24 | Destination address / words |
| 28 / 2c | Tag / cycle deadline |
| 30 | COMMAND: full-word write of exactly 1 START, 2 ACK, 4 ABORT, or 8 CLEAR_REJECTION; reads return zero |
| 34 / 38 | Completed/current tag / packet fault, read-only |
| 3c / 40 | Input/output accepted-word counters, read-only |
| 44 | IRQ enable bit 0; reserved bits must remain zero |
| 48 | ABI version 1, read-only |
| 4c | Rejection code: 0 none, 1 no credit/no completion, 2 invalid doorbell, 3 invalid MMIO access |
| 50 / 54 / 58 | Accepted-command / observed-completion / rejected-access counters (wrapping uint32), read-only |
| 5c | Capability word `0x00030101`: three segments, one credit, ABI 1 |

IRQ is level-sensitive while enabled and done/stopped/rejection is pending.
ACK consumes only a real normal completion, clearing that IRQ source;
CLEAR_REJECTION clears only the rejection source. ABORT latches the control's
global-abort request; neither ACK nor CLEAR_REJECTION clears STOPPED/fatal state.
Recovery remains a supervisor-controlled drained reset. IRQ enable and staging
may be changed while busy, but do not modify the owned packet. STATUS ready is
false throughout normal completion backpressure or abort.

The MMIO responder must remain live across core-only reset so accepted local
accesses can retire. Packet-engine reset is permitted only after memory drain;
accelerator-stream reset may be asserted during cancellation to discard partial
packets. The supervisor must keep their distinct reset/lifetime contracts.
