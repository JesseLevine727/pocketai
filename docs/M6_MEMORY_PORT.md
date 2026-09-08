# M6 memory-port implementation contract

This adaptation passes local and full-system RTL checks, but has not closed
physical timing. The [port ledger](m6_port_evidence.json) records those gates. It keeps
the full logical capacities and read/write concurrency of the FPGA design.
SRAM22 is accepted as third-party IP under the deferrals in M6_PLAN.md; its
behavioral and characterized timing views remain required at the boundary.

## Two-phase memory clock

The current adapter has a separate set-high `write_phase_q` register, toggled
on falling memory-clock edges. The reset-low system divider toggles on those
same edges, so the phase remains its logical complement without using the
clock-distribution signal as mux data. This lets physical implementation
buffer SRAM address/control data normally. The earlier direct-clock-as-phase
trial passed functional tests but caused spurious clock-tree discovery and
poor data-net buffering; its physical results are retained separately.

The public SRAM22 candidate has one read-or-write port. PocketAI requires
simultaneous synchronous reads and writes, including read-before-write on an
address collision. Do not remove reads during writes or assume that the memory
clients never overlap. Instead, run the SRAM clock at twice the system clock.

Generate the system clock with a falling-edge divide-by-two register from the
memory clock. Capture read addresses/enables and write address/data/byte enables
on each rising system edge. On the next rising memory edge, perform the read;
on the following rising memory edge, perform the pending write. Phase select
changes only at falling memory edges, away from the SRAM sampling edge.
The read completes before the next system sampling edge. Read data holds when
the read enable is low, including while the memory services a write.

Two-read memories use two physical SRAM copies with broadcast writes, one
copy for each read port. Capacity and coherence stay unchanged; the physical
duplication must appear in ASIC area and power scope. Depth banking and width
padding are explicit. Never claim padded or replicated physical bits as extra
model capacity, and never hide their area.

The initial 50-MHz memory / 25-MHz system trial failed setup timing. The
revised phase-data design is now constrained to 25 MHz memory / 12.5 MHz
system as a candidate, not an achieved result. Macro response, bank selection,
clock insertion delay and short memory-service phases must all be checked.
The user deferred the 100-MHz hard gate, not timing analysis. Both clocks and
their generated-clock relationship must be constrained and checked after route.
No PLL, free-running oscillator or external DDR controller is implied.

## Reset, small memories and checks

Memory contents are not reset. The chip-level reset initializes pending
commands and the clock divider; it is asserted during initial provisioning or
after transactions have been quiesced. Hart-only resets do not discard memory
contents or pending writes. This is distinct from the existing safe abort/drain
protocol, which remains in the portable system.

Bulk writable synchronous arrays map to actual SRAM macros. Constant ROMs
remain synthesized constant logic; small asynchronous result buffers, register
files and control arrays remain explicit logic storage unless a separately
tested adaptation preserves their interface. These exceptions must be listed
and included in area. They are not a smaller model or omitted storage.
Use Ibex's resettable flip-flop register-file implementation as a technology
binding, with both RV32MFast multipliers unchanged. Do not rely on FPGA-only
power-up initialization of ASIC registers.

Before full physical implementation, check all byte masks, simultaneous
read/write collisions, read-enable hold, bank boundaries, both read ports,
address/data changes between clock phases and reset/provisioning behavior.
Compare the observable data before each system sampling edge against the
qualified synchronous memory contract. Full-system firmware and numerical
checks remain necessary after these local tests; a memory-only test is not M6.
