# M3 architecture and interface contract v1

Frozen before arithmetic RTL, 2026-09-04 local time. **Implemented and qualified
at 95 MHz, 2026-09-05.** Wide GEMM, all seven SFPU operators, shared stream
routing and actual-result chains have local and exact-overlay physical evidence
in `M3_VERIFICATION.md`, with two clean timing builds. Numerical semantics and fixed acceptance
limits are in [`NUMERICS.md`](NUMERICS.md); staged gates are in `M3_PLAN.md`.

## Integration and dataflow

Retain the two-hart cluster, five-host fair bus, 64 KiB scratchpad, console,
mailbox and legacy GEMM address map. Add an optional M3 configuration with
wide GEMM support and one descriptor-driven SFPU at fabric `0x00014000`
(A9 physical `0x43c14000`, 1 KiB decoded window). Legacy build configurations
remain available for the M1/M2 regression contracts.

The existing 32-bit AXI DMA is shared by GEMM and SFPU through an explicitly
controlled bidirectional stream mux. Route 0 is GEMM (reset default); route 1
is SFPU. Change route only with **both engines idle**, and software must first
quiesce both DMA channels. Hardware rejects a busy-route change. The inactive
engine sees no valid input and no ready output. This preserves the M2 stream
interface and avoids an implicit host-visible routing change.

One software owner (or a lock covering the entire staging/submission sequence)
owns descriptors, DMA and route. Multiword staging is not atomic. SFPU/GEMM
completion/error IRQs are ORed with the existing mailbox interrupt to both
harts, with accelerator IRQs disabled by reset. Core-only reset does not reset
accelerators or revoke the A9's programming access.

Initial M3 chains use DDR between GEMM and SFPU. There is **no implicit direct
GEMM→SFPU stream-forwarding path** in v1: their payload formats and parameter
planes differ. Avoid unnecessary round trips through LayerNorm's integrated
affine step and AFFINE_GELU fusion, reuse DMA allocations, and batch publication
as measured in G1. Do not claim that this removes dispatch/link costs or beats
the CPU. Measure complete chains again on the final overlay. Autonomous
KV management and a queued full-model runtime remain M4/M5 work.

Implementation uses three synchronous 3072x32 inferred vector RAMs (X/G/B),
with one explicit X write port selected between load and compute. X is reused
for finalized output. The output holding register is stable under backpressure;
the shell currently delivers one word every three cycles without stalls. Input
and output stalls are excluded from `LAST_CYCLES`, not from wall latency.

The shared unsigned ALU uses 64 cycles for multiply/divide and 40 for an 80-bit
floor square root. The controller computes `1/sqrt(variance+epsilon)` implicitly
through the exact frozen normalized numerator/divisor equation; it does not
materialize a prematurely rounded reciprocal. Wide rounding, sign, bias and
clipping are pipelined independently. Current compute-cycle accounting is in
`ref/sfpu_stream.py`: GELU `6L`, LayerNorm `281L+313`, softmax `15L+137P`,
AFFINE/REQUANT8 `75L`, AFFINE_GELU `77L`, ADD `4L`, where P is the number of
valid entries whose max-subtracted raw difference is below 4096. These are
microarchitecture counters verified in simulation, not delivered-throughput
claims. Timing closure may change cycles without changing numerical v1.

## GEMM extension

Keep ID `0x50414732`, legacy CAPS `0x03001010`, all old register offsets and
flag-zero behavior. Add `EXT_CAPS` at 0x44 (bit 0: WideResultV1 supported),
`MAX_WIDE_K` at 0x48 (=3072), and `EXT_VERSION` at 0x4c (=0x00030001) in the M3
configuration. In a legacy-only configuration these extension reads return 0.
No new supported flag is enabled without the extension capability.

Flag `0x100` enables direct K<=3072 accumulation and int32 results; all other
nonzero flag patterns remain invalid. Flag zero still rejects K>768 even when
the larger memories exist. Increase A/B storage and accumulator width for the
extended configuration, while preserving two independent, ordered slots and
all M2 error/reset/abort semantics. Both output formats use TKEEP=0xf and TLAST
only on the final output word. Slot metadata includes format and full output
word count; 256 wide output words require a 9-bit count, not an 8-bit count.
Input counts need 15 bits for 24,576 words. Dimension checks use full 32-bit
staging values before any narrowing. Expose a busy indication for safe routing.

Memory and timing design: retain 4x16 physical soft MACs and the existing
operand/multiply pipeline, expand accumulation to 27 bits and C storage to 16
words per row. Legacy packing remains eight words per row. Expected no-stall
compute/pack cycles are `ceil(M/4)*(K+6)+M*(wide ? 16 : 8)`; validate counters
against simulation/board, do not assume a cycle-rate equals delivered speed.

## SFPU register map

Registers are aligned 32-bit little-endian words. Byte enables merge staging
and IRQ values; command/route bits are acted on only when their low byte is
enabled. Reserved register reads return zero; reserved writes have no effect.

| Offset | Register | Meaning |
|---:|---|---|
| 0x00 | ID | 0x50415333 (`PAS3`) |
| 0x04 | STATUS | bit0 ready, bit1 busy, bit2 sticky done, bit3 sticky error, bit4 input-ready, bit5 output-valid |
| 0x08 | OP | staged opcode |
| 0x0c | LENGTH | staged full-width vector length |
| 0x10 | SHIFT | staged 0..31 for affine/requantize, zero for other ops |
| 0x14 | MULTIPLIER | staged scalar 0..2^31-1 for REQUANT8, zero for other ops |
| 0x18 | TAG | staged opaque completion tag |
| 0x1c | COMMAND | 1 submit, 2 clear sticky done/error, 4 abort |
| 0x20 | COMPLETED_TAG | tag of last fully consumed output packet |
| 0x24 | LAST_CYCLES | compute cycles, excluding input/output stalls |
| 0x28 | LAST_ELEMENTS | length associated with last completion |
| 0x2c | INPUT_WORDS | expected count for valid staged descriptor, else 0 |
| 0x30 | OUTPUT_WORDS | staged length for valid descriptor, else 0 |
| 0x34 | COMPLETED_COUNT | modulo-2^32 count, increment at final output handshake |
| 0x38 | ERROR | sticky error code, zero when clear |
| 0x3c | CAPS | 0x01000c00: interface v1, maximum general length 3072 |
| 0x40 | IRQ_ENABLE | bit0 enables level `(done || error)` |
| 0x44 | SUPPORTED_OPS | bits 1..7 set (=0xfe) |
| 0x48 | VERSION | 0x00030001 |
| 0x4c | MAX_SOFTMAX | 1024 |
| 0x50 | STREAM_ROUTE | 0 GEMM, 1 SFPU; changes require both engines idle |

Unknown/combined nonzero command values are rejected as bad-command errors,
except any command containing abort (bit2) performs abort with highest priority.
Command zero is a no-op. Clear does not cancel an executing descriptor. Submit
requires no busy state and no sticky error; captures a validated descriptor
atomically. Staging may change afterward without changing in-flight behavior.
One SFPU slot is deliberately supported in v1; a second submit is an error,
not an overwrite. Ready means idle and error-free. Busy includes output stalls
and any framing-error drain state.

## SFPU operations and packet encoding

All input/output words use TKEEP=0xf. TLAST is required exactly on the final
word of a packet. Planes are contiguous and row-major; no input padding beyond
the specified length. There is one output word per vector element (not packed
halfwords/bytes). Multiplier/bias planes may repeat per-channel metadata over
multiple rows; software is responsible for that explicit expansion.

| OP | Name | Input planes, in order | Output |
|---:|---|---|---|
| 1 | GELU | X[L], canonical sign-extended int16 | sign-extended int16 |
| 2 | LAYERNORM | X[L], GAIN[L], BIAS[L], each canonical sign-extended int16 | sign-extended int16 |
| 3 | SOFTMAX | SCORE_MASK[L]: bits15:0 signed score, bit16 valid, bits31:17 zero | zero-extended uint16 |
| 4 | AFFINE | X[L] signed int32, MULT[L] nonnegative signed int32, BIAS[L] signed int32 | sign-extended int16 |
| 5 | REQUANT8 | X[L] signed int32; scalar descriptor multiplier/shift | sign-extended int8 |
| 6 | AFFINE_GELU | same three planes as AFFINE | sign-extended int16 |
| 7 | ADD | X[L], Y[L], canonical sign-extended int16 | sign-extended int16 |

Length is 1..3072 except softmax 1..1024. Noncanonical upper bits, negative
per-element multipliers, invalid masks and invalid descriptor fields are errors;
do not silently truncate them. For operations 1/2/3/7, SHIFT and MULTIPLIER must
be zero. AFFINE/AFFINE_GELU require scalar MULTIPLIER zero and SHIFT<=31.
REQUANT8 accepts SHIFT<=31 and scalar MULTIPLIER<=0x7fffffff. Output conversion
to GEMM's byte-packed A/B representation is explicit; unsigned probabilities
must first pass through int32-aware REQUANT8 when used as GEMM operands.

Examples: LayerNorm length768 transfers 9,216 input bytes and 3,072 output bytes;
GELU length3072 transfers 12,288 bytes in and out; softmax length1024 transfers
4,096 bytes in and out. These stream bytes are **not** the compact tensor
storage size. LayerNorm includes its gain/bias transfer; benchmark boundaries
must not silently assume they are resident in v1.

## Error, reset, abort and completion

| Code | Error |
|---:|---|
| 1 | Unsupported operator |
| 2 | Invalid length |
| 3 | Invalid descriptor mode/shift/multiplier or invalid route value |
| 4 | Submit while busy |
| 5 | Input TKEEP not 0xf |
| 6 | TLAST before expected final word |
| 7 | Missing TLAST on expected final word |
| 8 | Invalid payload encoding |
| 9 | Route change while either engine is busy |
| 10 | Invalid command |

First descriptor/control error stays sticky and blocks new submissions, but
does not cancel existing valid work or change the route. A framing/payload
error takes priority over simultaneous normal command/control errors, invalidates the
active descriptor and drains input to TLAST if it has not arrived. It produces
no successful completion for that descriptor. In all cases software must
quiesce/reset DMA before abort/retry, or a DMA transaction can be stranded.

System reset or abort invalidates the descriptor, reduction/ALU pipeline, pending
output and drain state unconditionally. Abort clears sticky flags; neither abort
nor core reset changes the route. System reset restores route 0 and IRQ disabled.
Reset/abort outrank framing errors as well: a stopped malformed stream must not
prevent unconditional recovery. This makes explicit the v1 unconditional-abort
rule before the SFPU controller implementation; formats and numerical limits
are unchanged.
Completed count/history reset only on system reset, not abort/clear. RAM contents
need no reset because only validated loaded elements may be read/exposed.
Output data/TLAST remain stable under backpressure. Done, tag, cycles, length
and completion count update together only when the final output word is accepted.
Reset/abort must never release a stale arithmetic result later.

## Resource-conscious implementation and validation

Use inferred synchronous memories for up to three 3072x32 input planes, reusing
the X plane for computed output after its original values are no longer needed.
Keep the complete vector while reductions run. SFPU output begins only after
compute completes; no provisional normalization result is published.

Use a shared iterative integer multiply/divide/square-root datapath with explicit
wide operands and deterministic handshakes. Serial arithmetic is acceptable;
the goal requires measured performance, not an invented per-element throughput.
Generate/pin LUTs from the reference. No vendor primitives, DSPs or floating
point in portable fabric RTL, and no division-by-zero behavior left unspecified.

Required local tests cover all opcodes, full scalar GELU domain, substantial
random/adversarial vectors, the frozen errors, exact output bits, width extremes,
K=3072 cancellation, stalls, concurrent hart traffic, all errors, byte writes,
staging immutability, counter association, IRQs, route changes and reset/abort
at every execution phase. Then independently qualify two clean 95 MHz full
builds and the exact physical overlay; G1's old bitstream does not qualify M3.

### Shared ALU implementation contract

`pa_sfpu_alu` accepts a request only while idle; other starts are ignored.
Opcode 0 multiplies two unsigned 64-bit operands in 64 cycles, returning the
low 64 bits and an overflow error if the upper product is nonzero. Opcode 1
performs unsigned floor division in 64 cycles with an exact remainder. Division
by zero and unsupported opcode 3 complete immediately with an error and zero
results. Opcode 2 returns floor sqrt of an unsigned 80-bit radicand in 40 cycles,
plus the exact radicand-minus-square remainder. Latencies exclude the request
acceptance edge. Done pulses once; results remain stable until next completion.
Reset or abort cancels all pending work with no late completion.

The multiply step adds only the upper 64-bit partial product and then shifts,
limiting that carry path to 65 bits. Division and square root use restoring
integer steps, no vendor arithmetic IP. Signed magnitude conversion, RNE using
the returned remainder, saturation and bounded-operand checks belong to the
SFPU operator controller. Its legal numerical domains must never trigger ALU
overflow/division-by-zero; this requirement is still to be integrated/tested.
