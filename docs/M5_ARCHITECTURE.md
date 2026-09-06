# M5 architecture — initial memory-translation contract

Status: **G1 design in progress, no physical M5 qualification**. The translation
contract below is version 1, recorded before its RTL. Transfer/control and
firmware ABIs will be specified before those implementations; this is not a
claim that the complete autonomous architecture is implemented.

## Selected memory strategy and approval boundary

Use a bounded 256-MiB *device-virtual* arena backed by individually allocated,
kernel-owned ordinary DDR pages. The 195.763-MiB model plus 46.125-MiB full
cache leaves approximately 14.1 MiB for aligned headers, stacks/working tensors
and buffers; an actual exported layout must prove fit before acceptance.
Only a small page table/control allocation needs contiguous coherent memory.
This is a selected design to implement/test, not a measured successful allocation.

The memory helper must retain the pages and their Linux DMA mappings through
the complete autonomous access lifetime. Page-table entries contain DMA bus
addresses returned by the DMA API, not addresses guessed from pagemap. Use a
32-bit DMA mask, check all mapping failures, and explicitly transfer cache
ownership before and after noncoherent device access. These rules follow the
[Linux 6.6 DMA guide](https://www.kernel.org/doc/html/v6.6/core-api/dma-api-howto.html)
and [DMA API](https://www.kernel.org/doc/html/v6.6/core-api/dma-api.html).

Provisioning/readback should use bounded driver operations while host-owned;
no host tensor reads/writes while device-owned. On abort/close, pages must not
be unmapped/freed until hardware is blocked from new requests and outstanding
AXI accesses have drained. A timeout is not proof of drain: retain unsafe pages
and the responsible module references if quiescence cannot be proved.

Kernel build headers and `Module.symvers` for the actual board release exist.
The kernel was built using GCC 12.2.0; board userspace GCC is 11.2.0. Build and
symbol/version compatibility must be checked, not inferred from matching major
kernel version. **User approval is required before loading a new helper.** No
boot/CMA setting changes, kernel replacement, unowned DDR use or force-unload.

## Address/ownership separation

- Existing shared scratchpad/peripherals/accelerator register ABIs remain
  local. M5 additions should not modify frozen M1–M4 implementations merely to
  expose memory from a changed physical design.
- Device-virtual DDR window: `0x40000000..0x4fffffff`, maximum 256 MiB.
  Configured active arena size is a nonzero multiple of 4096, no larger than
  that window. A smaller arena is legal for isolated memory tests, not a
  smaller-context substitute for full-model acceptance.
- The A9/kernel provisioning interface owns page-table base, arena size,
  mapping enable and quiescence control. This configuration is **not writable
  through the Ibex-visible model/transfer command registers**. Faulty firmware
  must not be able to replace the page-table root with arbitrary DDR.
- Model pages become read-only to device writes. Cache/scratch pages are
  writable. The page table itself is not mapped inside the firmware's arena.
- RISC-V load/store and autonomous bulk-transfer clients both pass through
  the bounded translator; there is no raw-physical-address escape path.
- A9 may observe control/status and output tokens. It may not service model
  page faults or refill data on demand during autonomous execution.

## Translation ABI v1

Little-endian 32-bit page-table entries; 4096-byte pages. Entry index is
`(virtual_address - 0x40000000) >> 12`. Each entry has:

| Bits | Meaning |
|---|---|
| 31:12 | Aligned DMA bus page base |
| 11:2 | Reserved, must be zero |
| 1 | Write permitted |
| 0 | Entry valid; valid entries permit reads |

Physical DMA address zero is not automatically invalid: validity is bit 0.
The table contains exactly `arena_bytes/4096` entries and is immutable while
enabled for a run. Its base is word-aligned and its full byte range must fit
the 32-bit address space. The helper validates ownership of every mapped page;
the translator validates virtual bounds/permissions before downstream access.

Translation requests describe a **word-aligned** address and 1..256 32-bit
words plus read/write direction. Clients split bulk transfers at 4-KiB page
boundaries before requesting translation. Requests may not cross a page or
the configured arena end; additions are checked with widened arithmetic.
CPU byte/halfword operations use an aligned word request and separate byte
strobes. A cross-word unaligned access must be decomposed or rejected upstream.

The translator presents one table-read command with a valid/ready handshake,
then waits for exactly one response, no earlier than the clock cycle after
request acceptance. It returns translated address or a fault
through a separate valid/ready response held stable under backpressure. It has
at most one in-flight request. A small direct-mapped PTE cache is permitted;
permissions are checked on cache hits too. Flush is accepted only when idle;
the caller holds flush until `flush_ready`. Mapping registers change only
while disabled and all clients/AXI requests are drained, followed by flush.

| Fault code | Meaning |
|---|---|
| 0 | Success |
| 1 | Mapping disabled |
| 2 | Invalid arena/table configuration |
| 3 | Request outside arena or invalid word count |
| 4 | Unaligned request address |
| 5 | Request crosses a 4-KiB page |
| 6 | Invalid PTE |
| 7 | Write denied |
| 8 | Reserved PTE bits set |
| 9 | Page-table read error |

Disabled/bad/out-of-range requests return a fault without a table access.
Malformed/denied PTEs never yield a usable translated data address. A table
response error returns fault 9. A missing response keeps the request outstanding
and `busy` asserted; a supervisor timeout must not interpret that as safe to
free memory. The downstream AXI bridge/drain mechanism is a separate G2 gate.
Translator reset is permitted only when quiescent or as part of a coordinated
whole-interconnect reset that independently guarantees no outstanding access;
resetting this state machine alone is not cancellation of a page-table read.

## Planned implementation sequence

1. Independent translation/bounds/permission/stall/flush tests and portable RTL.
2. Variable-latency RISC-V path and bounded AXI bridge; table/data bus ownership
   and outstanding-access accounting. Keep scratchpad instruction execution
   from depending on DDR response latency where possible.
3. Autonomous stream-transfer engine and descriptor/lifecycle ABI, preserving
   M3 payload formats. Prefer direct scatter/gather of accepted A/B planes to
   firmware copying entire static weight packets, but qualify actual semantics.
4. Reviewed memory-helper allocation/ownership tests, then user-approved board
   loading and guarded physical memory/transfer round trips on an M5 overlay.
5. Complete numerical firmware, model qualification and final implementation/
   physical/performance gates in `M5_PLAN.md`.

No host-side page service, numeric fallback, truncated context or precomputed
full operator schedule is introduced as a substitute for these milestones.

## Private AXI burst engine contract v1

`pa_m5_axi_burst` is an internal physical-bus component, not a firmware-accessible
escape from translation. Its eventual caller may submit only a validated PTE
table read or a successfully translated arena access. One command describes
1..256 aligned 32-bit words within one 4-KiB page, direction and address.
The AXI port uses incrementing bursts, 4-byte beats, ID zero, non-cacheable,
non-bufferable normal data accesses. A second command cannot overlap.

A bounded 256-word data/strobe buffer collects **all** write input before AW
is issued. Reads collect all R beats before exposing successful read data to
the client. Thus, once an address is issued, neither an unresponsive firmware
producer nor an accelerator consumer is required to finish the AXI burst.
Input/output beats and the final completion use valid/ready handshakes.
Completion follows the last successful read-output handshake or the write B
response; an AXI response error produces no usable read payload.

Abort is an explicit client-stream cancellation boundary, not a transparent
pause: clients must stop using partial output. It blocks new commands, discards
an incomplete pre-AW write, finishes any already-present AW/AR handshake and
drains the complete issued burst using the internal buffer. It may discard
undelivered buffered read output and completion. Abort cannot retract an AXI
VALID under backpressure, fabricate a B/R response, or clear an outstanding
transaction. `busy=0` with abort held proves this engine has no pending AXI
access, but the enclosing controller must also quiesce translation and every
other client before exposing global quiescence. Normal reset is only permitted
at that global boundary; a core-only reset must use abort/drain instead.

Normal slave error responses drain and complete with fault 12. A malformed AXI
ID or RLAST poisons the engine: it stops issuing requests and stays busy until
a coordinated whole-interconnect recovery. No timeout/abort turns that unknown
bus state into a claim that mapped memory can be released.

| Internal completion fault | Meaning |
|---|---|
| 0 | Success |
| 10 | Invalid physical burst (count/alignment/page/range) |
| 11 | Aborted client operation |
| 12 | AXI data response error |
| 13 | Malformed AXI protocol; poisoned, no normal completion |

This component does not by itself establish Linux ownership, translation,
multi-client arbitration, autonomous operator scheduling or physical timing.
