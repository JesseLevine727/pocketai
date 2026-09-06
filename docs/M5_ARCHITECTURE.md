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

## Translated memory bridge contract v1

`pa_m5_memory_bridge` composes those primitives into one serialized virtual
memory request interface. It latches a client's virtual address/count/direction,
walks the protected PTE table through the private AXI engine when needed, and
issues data access only after successful translation. Client write/read payload
and completion retain the buffered-engine handshake and cancellation contract.
PTE reads and data bursts cannot overlap or exchange response destinations.

Abort before a translation starts may cancel it without a bus access. Once a
translation is started, a requested PTE walk is completed/drained internally,
even if abort is asserted; only then is the translated operation discarded.
This avoids abandoning the translator with an unreturned PTE response. A data
operation already submitted to the AXI engine follows that engine's abort/drain
rules. New virtual requests remain blocked while abort is held. Bridge busy
includes both child engines; poison cannot be hidden by an idle parent state.
Bridge `quiesced` means abort is held and parent/children are all idle, not that
unrelated clients elsewhere in the overlay have stopped.

Flush blocks virtual request admission and is forwarded to the translator only
when the complete bridge is idle. The caller holds it until bridge flush-ready.
Protected configuration changes still require the system-wide disabled/drained
ownership boundary; this bridge does not make firmware a mapping administrator.

## Static arena/model serialization ABI v1

The original M4 pack remains the immutable source. M5 removes only `.npy` file
headers and places the same contiguous little-endian array bytes at 64-byte
aligned offsets. No requantization or weight/scale transformation is performed.
The exported `model.bin` covers the read-only model region, including its
65,536-byte header; the rest of the 256-MiB arena is provisioned separately.
The exporter refuses existing output directories and verifies every source
array hash, shape, dtype and the frozen M4 manifest/candidate identities.

Header words are little-endian uint32. Words 0..15 are: magic `0x354d4150`
(`PAM5` bytes), ABI 1, header bytes 65536, arena bytes 268435456, array count
248, array-entry bytes 32, array table offset 128, region count, region-entry
bytes 32, region table offset 8192, read-only model end offset, context 1024,
layers 12, heads 12, width 768, vocabulary 50257. Bytes 64..95 and 96..127
contain the raw SHA-256 digests of the frozen M4 pack manifest and adaptive-v3
candidate, respectively. Remaining unassigned header/padding bytes are zero.

Each 32-byte array entry contains eight uint32 values: ordinal ID, arena byte
offset, payload bytes, dtype code (1 signed int8, 2 signed int16, 3 float64),
rank, and three dimensions (unused dimensions are zero). All firmware addresses
are device-virtual base plus offset. IDs are assigned in this fixed order:

1. `embedding`, `position`.
2. For layers 0..11 in numerical order: `attn.c_attn`, `attn.c_proj`, `mlp.c_fc`,
   `mlp.c_proj`, each with `tiles`, `scale`, `bias`, `smooth`; then `ln_1` and
   `ln_2`, each with `gain`, `bias`.
3. `ln_f.gain`, `ln_f.bias`, then `lm_head.tiles`, `.scale`, `.bias`, `.smooth`.

Each 32-byte region entry contains ID, offset, bytes, PTE permission bits,
and four reserved-zero words. Regions partition the full arena, are page aligned
and have fixed IDs/order: model (read-only), guard, K, guard, V, guard, K8,
guard, K-units, guard, work, guard, trace, guard, unused tail. Guards and unused
tail have permission zero and **no mapped pages**. K/V are each int16
`[12,12,1024,64]`, K8 is int8 with that same shape and K-units is float64
`[12,12,1024]`. Work reserves 4 MiB and trace 8 MiB; these are upper bounds,
not a claim that an as-yet-unimplemented runtime fits its internal allocations.
All non-model payload regions are device-read/write. Each guard is 4 KiB.

The human-readable layout manifest records named arrays/regions, source-file
identities, raw payload digests, exported model digest and exact occupied/
unmapped sizes. Export acceptance compares all 248 delivered raw array payloads
against the independently hash-checked M4 pack and checks binary-header/layout
agreement, page permissions, guards and fit. This proves serialization/fit,
not a successful board allocation or complete working-memory liveness analysis.

## Core routing and multi-client memory contract v1

Each core instruction/data port gets an M5-only registered router. It accepts
one request into owned registers and grants that acceptance to Ibex, then holds
the selected downstream request through its grant and waits for its response.
Only `0x4xxxxxxx` routes to translated DDR; all other addresses retain the local
bus decode (and its errors). A port has at most one outstanding transaction,
so local and DDR responses cannot reorder. Other ports continue local BRAM
traffic while one port waits on DDR. Local/DDR downstream response latency is
at least one clock after grant. Core stop blocks **new** admission, not already
accepted requests; routers are not reset by core-only reset.

The OBI-to-DDR adapter requests exactly one aligned word and preserves the
captured write data/byte strobes. Ibex performs cross-word unaligned access
decomposition; no word request can itself straddle a translated page. It
collects read data before forwarding completion/error to the waiting OBI port.
Address low bits are removed only for DDR word transfers, not local peripherals.

A separate round-robin arbiter serializes four core ports plus the autonomous
bulk-transfer client into the translated bridge. A grant owns the captured
command until completion; payload/completion routing uses that registered owner,
not a changing arbitration result. Each granted burst advances round-robin
priority. Clients retain their valid command until grant and obey the buffered
stream/cancellation contract. There is no speculative multi-owner packet queue.

During global abort the arbiter drains any submitted bridge operation before
returning fault 11. It also consumes already-pending client commands and returns
fault 11 without issuing memory, so stopped cores' accepted router requests can
retire. Aborted completions need no cooperation from a halted consumer. Global
quiescence must include **all** routers/adapters, the bulk engine, arbiter,
translator and AXI bridge, and exclude pending requests—not merely an idle AXI
master between requests. Mapping flush occurs at that disabled/quiescent system
boundary. The platform integration must implement/test this combined condition
before a kernel helper may use it as authority to release pages.
