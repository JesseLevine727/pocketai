# One actual local buffer per macro output. No datapath latency/clock exception.
proc pa_m6_contract_output_buffers {} {
    set block [ord::get_db_block]
    if {[$block getName] ne "pa_m6_bank_probe"} { error "eight-macro probe only" }
    set macros {}
    foreach inst [$block getInsts] {
        if {[[$inst getMaster] getName] eq "sram22_512x32m4w8"} { lappend macros $inst }
    }
    if {[llength $macros] != 8} { error "expected eight SRAMs" }
    set index 0
    foreach macro $macros {
        if {[$macro getOrient] ne "R0"} { error "N macros required" }
        lassign [$macro getOrigin] dbx dby
        set units [$block getDbUnitsPerMicron]
        set x [expr {double($dbx)/$units}]
        set y [expr {double($dby)/$units}]
        for {set bit 0} {$bit < 32} {incr bit} {
            set port "dout\[$bit\]"
            set terminal [$macro findITerm $port]
            set original [[$terminal getNet] getName]
            set name "m6_out_${index}_$bit"
            set local "${name}_local"
            set pin "[$macro getName]/$port"
            make_instance $name sky130_fd_sc_hd__buf_12
            make_net $local
            disconnect_pin $original $pin
            connect_pin $local $pin
            connect_pin $local $name/A
            connect_pin $original $name/X
            # Exact pinned LEF pitch is 6.10 um. Alternate rows fit buf_12's
            # wider footprint while keeping pin-to-buffer wires local.
            set bx [expr {floor(($x+233.68+$bit*6.1)/0.46)*0.46}]
            set by [expr {floor(($y-5.44-($bit%2)*2.72)/2.72)*2.72}]
            place_cell -inst_name $name -origin [list $bx $by] -orient R0 -status PLACED
            set instance [$block findInst $name]
            foreach {pg supply} {VPWR vdd VPB vdd VGND vss VNB vss} {
                [$instance findITerm $pg] connect [$block findNet $supply]
            }
            set_dont_touch [list $name $local]
        }
        incr index
    }
    puts "M6 OUTPUT CONTRACT BUFFERS: 256 buf_12 cells, unchanged 8 SRAM macros"
}

proc pa_m6_contract_boundary {} {
    pa_m6_contract_output_buffers
    if {$::env(M6_CONTRACT_CLOCK_LEAVES)} {
        # Reuse the reviewed paired-clock/PG insertion procedure, not its
        # automatic CTS invocation. Here pairs precede CTS for tree balancing.
        set stream [open /m6_flow/leaf_probe_cts.tcl r]
        set source [read $stream]
        close $stream
        set marker {set original_path $::env(SCRIPTS_DIR)/openroad/cts.tcl}
        set stop [string first $marker $source]
        if {$stop < 0} { error "unexpected local-clock helper" }
        uplevel #0 [string range $source 0 [expr {$stop-1}]]
        pa_m6_local_clock_leaves
        # CTS must reconnect the upstream pins while building the clock tree.
        # Restore protection only after construction, not before its ECOs.
        for {set i 0} {$i < 8} {incr i} {
            unset_dont_touch [list m6_leaf_${i}_pre m6_leaf_${i}_drive m6_leaf_${i}_inverted m6_leaf_${i}_local]
        }
    }
    estimate_parasitics -placement
}
proc pa_m6_contract_protect_clocks {} {
    if {$::env(M6_CONTRACT_CLOCK_LEAVES)} {
        set block [ord::get_db_block]
        for {set i 0} {$i < 8} {incr i} {
            foreach name [list m6_leaf_${i}_pre m6_leaf_${i}_drive] {
                if {[$block findInst $name] eq "NULL"} { error "CTS removed a required clock inverter" }
            }
            set_dont_touch [list m6_leaf_${i}_pre m6_leaf_${i}_drive]
        }
    }
}
set stream [open $::env(SCRIPTS_DIR)/openroad/cts.tcl r]
set original [read $stream]
close $stream
set needle {clock_tree_synthesis {*}$arg_list}
if {[string first $needle $original] < 0 || [string first $needle $original] != [string last $needle $original]} {
    error "Unexpected pinned CTS source"
}
eval [string map [list $needle "pa_m6_contract_boundary\n${needle}\npa_m6_contract_protect_clocks"] $original]
