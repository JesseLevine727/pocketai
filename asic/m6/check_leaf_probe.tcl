# Post-route topology/PG regression for the experimental paired clock leaves.
# Read-only: all assertions inspect the retained OpenDB database.
read_db $::env(M6_LEAF_ODB)
set block [ord::get_db_block]
if {[$block getName] ne "pa_m6_bank_probe"} { error "wrong probe database" }
set macro_count 0
set leaf_count 0
set pg_count 0
foreach inst [$block getInsts] {
    if {[[$inst getMaster] getName] ne "sram22_512x32m4w8"} { continue }
    incr macro_count
    set local [[$inst findITerm clk] getNet]
    if {![regexp {^m6_leaf_([0-7])_local$} [$local getName] -> index]} { error "missing local macro clock" }
    if {[llength [$local getITerms]] != 2} { error "local clock must drive exactly one macro" }
    set pre [$block findInst "m6_leaf_${index}_pre"]
    set drive [$block findInst "m6_leaf_${index}_drive"]
    foreach {instance master} [list $pre sky130_fd_sc_hd__clkinv_2 $drive sky130_fd_sc_hd__clkinv_16] {
        if {[[$instance getMaster] getName] ne $master} { error "wrong clock inverter" }
        foreach {pin supply} {VPWR vdd VPB vdd VGND vss VNB vss} {
            set net [[$instance findITerm $pin] getNet]
            if {$net eq "NULL" || [$net getName] ne $supply} { error "clock leaf PG disconnected" }
            incr pg_count
        }
        incr leaf_count
    }
    if {[[$drive findITerm Y] getNet] ne $local} { error "wrong leaf polarity/output" }
    set inverted [[$drive findITerm A] getNet]
    if {[[$pre findITerm Y] getNet] ne $inverted || [llength [$inverted getITerms]] != 2} {
        error "two-inverter non-inverting clock path not preserved"
    }
    if {[[$pre findITerm A] getNet] eq "NULL"} { error "missing upstream clock" }
}
if {$macro_count != 8 || $leaf_count != 16 || $pg_count != 64} { error "clock-leaf count mismatch" }
puts "M6 CLOCK LEAF TOPOLOGY PASS macros=$macro_count inverters=$leaf_count pg_connections=$pg_count"
puts "M6 CLOCK LEAF TIMING REMAINS UNQUALIFIED; topology is not an electrical or STA pass"
