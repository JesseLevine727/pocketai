# Instrument the exact pinned repair stage; preserve every clock/library limit.
proc pa_m6_report_rc {label} {
    puts "M6-RC-DIAGNOSTIC $label BEGIN"
    foreach corner [sta::corners] {
        puts "M6-RC-CORNER [$corner name]"
        report_checks -corner [$corner name] -path_delay max -digits 9
    }
    report_check_types -max_slew -max_capacitance
    puts "M6-RC-DIAGNOSTIC $label END"
}
proc pa_m6_read_extracted {} {
    foreach corner [sta::corners] {
        set name [$corner name]
        read_spef -corner $name $::env(M6_REPAIR_SPEF_$name)
    }
}
proc pa_m6_prepare_route_copy {} {
    remove_fillers
    # Reusing detailed wires after cell resizing confuses incremental antenna
    # routing. Remove SIGNAL/CLOCK dbWires only from this new in-memory copy;
    # preserve every original artifact, cell, net, connection and PG dbSWire.
    set count 0
    foreach net [[ord::get_db_block] getNets] {
        if {[$net getSigType] ni {SIGNAL CLOCK}} { continue }
        set wire [$net getWire]
        if {$wire ne "NULL"} {
            odb::dbWire_destroy $wire
            incr count
        }
    }
    puts "M6 REROUTE COPY: cleared $count signal/clock detailed wires; PG unchanged"
}
proc pa_m6_compare_rc {} {
    puts "M6-RC-DIAGNOSTIC ESTIMATED BEGIN"
    pa_m6_report_rc ESTIMATED_ALL_CORNERS
    puts "M6-RC-DIAGNOSTIC ESTIMATED END"
    if {$::env(M6_REPAIR_USE_SPEF)} {
        pa_m6_read_extracted
        puts "M6-RC-DIAGNOSTIC EXTRACTED BEGIN"
        pa_m6_report_rc EXTRACTED_ALL_CORNERS
        puts "M6-RC-DIAGNOSTIC EXTRACTED END"
    }
}
proc pa_m6_selective_drivers {} {
    set block [ord::get_db_block]
    set db [ord::get_db]
    set corner [sta::find_corner max_ss_100C_1v60]
    set plan {}
    # Capture the plan before changing any loads. Receiver/other-corner checks
    # remain mandatory after routing; this plan is an SS optimization input.
    foreach cell [get_cells -hierarchical -filter {ref_name =~ sky130_fd_sc_hd__*}] {
        set name [get_full_name $cell]
        if {[string match m6_leaf_* $name] || [string match clkbuf_* $name]} { continue }
        foreach pin [get_pins -of_objects $cell] {
            if {[sta::pin_direction $pin] ne "output"} { continue }
            set vertex [lindex [$pin vertices] 0]
            if {$vertex eq ""} { continue }
            set slew [expr {max([$vertex slew_corner rise $corner max],[$vertex slew_corner fall $corner max])*1e9}]
            if {$slew <= 0.33} { continue }
            set master [get_property $cell ref_name]
            set cap [expr {[[$pin net] capacitance $corner max]*1e12}]
            lappend plan [list $name [get_full_name $pin] $master $slew $cap]
        }
    }
    set stream [open $::env(STEP_DIR)/selective_drivers.tsv w]
    puts $stream "instance\tpin\tmaster\tslew_ns\tload_pf\taction\treplacement"
    set count 0
    foreach row $plan {
        lassign $row name pin master slew cap
        set replacement ""
        if {[regexp {^(sky130_fd_sc_hd__[a-z0-9]+)_([0-9]+)$} $master -> family strength]} {
            foreach size {4 8 12 16} {
                if {$size <= $strength || $size < min(16,4*$strength)} { continue }
                if {[$db findMaster ${family}_$size] ne "NULL"} {
                    set replacement ${family}_$size
                    break
                }
            }
        }
        if {$replacement ne ""} {
            replace_cell $name $replacement
            puts $stream [join [concat $row [list upsize $replacement]] "\t"]
        } else {
            set source [$block findInst $name]
            if {$source eq "NULL"} { error "missing planned driver" }
            set port [lindex [split $pin /] end]
            set terminal [$source findITerm $port]
            set original [[$terminal getNet] getName]
            set buffer $::env(M6_REPAIR_PREFIX)_$count
            set local ${buffer}_local
            if {[$block findInst $buffer] ne "NULL" || [$block findNet $local] ne "NULL"} {
                error "selective driver names already present"
            }
            set box [$source getBBox]
            set bx [expr {[$box xMax]+920}]
            set by [$box yMin]
            make_instance $buffer sky130_fd_sc_hd__buf_16
            make_net $local
            disconnect_pin $original $pin
            connect_pin $local $pin
            connect_pin $local $buffer/A
            connect_pin $original $buffer/X
            set instance [$block findInst $buffer]
            $instance setOrient [$source getOrient]
            $instance setLocation $bx $by
            $instance setPlacementStatus PLACED
            foreach {pg supply} {VPWR vdd VPB vdd VGND vss VNB vss} {
                [$instance findITerm $pg] connect [$block findNet $supply]
            }
            set_dont_touch $local
            puts $stream [join [concat $row [list isolate_load sky130_fd_sc_hd__buf_16]] "\t"]
        }
        incr count
    }
    close $stream
    puts "M6 SELECTIVE DRIVERS: $count measured output drivers repaired; original plan in selective_drivers.tsv"
}
proc pa_m6_compress_read_chains {} {
    set block [ord::get_db_block]
    set corner [sta::find_corner max_ss_100C_1v60]
    set plan [dict create]
    # Only combinational, non-inverting read-return chains after the mandatory
    # local SRAM output receiver. Never remove a clock, state element, explicit
    # hold delay, logic gate, or the load-contract isolation receiver itself.
    foreach start [get_cells m6_out_*] {
        set current [[ord::get_db_block] findInst [get_full_name $start]]
        set selected 0
        for {set depth 0} {$depth < 12 && $selected < 2} {incr depth} {
            set master [[$current getMaster] getName]
            if {![regexp {^sky130_fd_sc_hd__(?:clkbuf|buf)_([0-9]+)$} $master -> drive]} { break }
            set net [[$current findITerm X] getNet]
            if {[llength [$net getBTerms]]} { break }
            set sinks {}
            foreach term [$net getITerms] {
                if {[[$term getMTerm] getIoType] ne "INPUT"} { continue }
                if {[string match *diode* [[[$term getInst] getMaster] getName]]} { continue }
                lappend sinks $term
            }
            if {[llength $sinks] != 1} { break }
            set next [[lindex $sinks 0] getInst]
            set next_name [$next getName]
            set next_master [[$next getMaster] getName]
            if {![regexp {^sky130_fd_sc_hd__(?:clkbuf|buf)_([0-9]+)$} $next_master -> size]} { break }
            set input_pin [lindex [get_pins [get_full_name $start]/X] 0]
            # Resolve these unescaped repair-generated names directly in STA.
            set a [lindex [get_pins [$current getName]/X] 0]
            set b [lindex [get_pins $next_name/X] 0]
            set cap [expr {([[$a net] capacitance $corner max]+[[$b net] capacitance $corner max])*1e12}]
            if {$drive >= 8 && $size <= 6 && $cap < 0.10 && [regexp {^wire[0-9]+$} $next_name]} {
                dict set plan $next_name [list [$current getName] $cap]
                incr selected
            }
            set current $next
        }
    }
    foreach name [dict keys $plan] {
        unset_dont_touch $name
        remove_buffers [get_cells $name]
        puts "M6 READ CHAIN: removed combinational $name, upstream/load [dict get $plan $name]; all-corner hold recheck required"
    }
    puts "M6 READ CHAIN: [dict size $plan] low-strength buffers removed from read-return chains"
}
proc pa_m6_upsize_return_chains {} {
    set block [ord::get_db_block]
    set plan [dict create]
    # Walk the single-fanout buffer chains that follow each mandatory local SRAM
    # output receiver and upsize the repair-inserted wire buffers. Upsizing
    # keeps the topology (no slew risk from removing a long-wire buffer) while
    # shortening the read-return delay. The SRAM output load is set by the
    # receiver, not these downstream buffers, so the load contract is unchanged.
    foreach start [get_cells m6_out_*] {
        set current [$block findInst [get_full_name $start]]
        if {$current eq "NULL"} { continue }
        for {set depth 0} {$depth < 16} {incr depth} {
            set master [[$current getMaster] getName]
            if {![regexp {^sky130_fd_sc_hd__buf_([0-9]+)$} $master -> size]} { break }
            set net [[$current findITerm X] getNet]
            if {$net eq "NULL"} { break }
            set sinks {}
            foreach term [$net getITerms] {
                if {[[$term getMTerm] getIoType] ne "INPUT"} { continue }
                if {[string match *diode* [[[$term getInst] getMaster] getName]]} { continue }
                lappend sinks $term
            }
            if {[llength $sinks] != 1} { break }
            set next [[lindex $sinks 0] getInst]
            set next_name [$next getName]
            set next_master [[$next getMaster] getName]
            if {![regexp {^sky130_fd_sc_hd__buf_([0-9]+)$} $next_master -> nsize]} { break }
            if {[string match wire* $next_name] && $nsize < 16} {
                dict set plan $next_name $nsize
            }
            set current $next
        }
    }
    foreach name [dict keys $plan] {
        unset_dont_touch $name
        replace_cell $name sky130_fd_sc_hd__buf_16
        set_dont_touch $name
        puts "M6 RETURN UPSIZE: $name buf_[dict get $plan $name]->buf_16"
    }
    puts "M6 RETURN UPSIZE: [dict size $plan] read-return buffers upsized"
}
proc pa_m6_split_high_fanout {} {
    set block [ord::get_db_block]
    set max_fanout 16
    set index 0
    while {[$block findInst "m6_fs_$index"] ne "NULL"} { incr index }
    set split {}
    # Only single-driver signal/clock nets are split, by inserting one reviewed
    # buffer and moving the excess input sinks onto it. Placement is finalized
    # by the following detailed placement; all-corner STA rechecks skew.
    foreach net [$block getNets] {
        set net_name [$net getName]
        if {[string match m6_fs_* $net_name]} { continue }
        set sinks {}
        set driver ""
        foreach term [$net getITerms] {
            set io [[$term getMTerm] getIoType]
            if {$io eq "INPUT"} { lappend sinks $term } elseif {$io eq "OUTPUT"} { set driver $term }
        }
        if {$driver eq ""} { continue }
        set count [llength $sinks]
        if {$count <= $max_fanout} { continue }
        set dmaster [[[$driver getInst] getMaster] getName]
        set cell "sky130_fd_sc_hd__buf_16"
        if {[string match *clk* $dmaster] || [string match *clk* $net_name]} {
            set cell "sky130_fd_sc_hd__clkbuf_16"
        }
        # The inserted buffer input is itself one new load on the original net,
        # so move one extra sink to land at the limit.
        set move [expr {$count - $max_fanout + 1}]
        set selected [lrange $sinks 0 [expr {$move-1}]]
        set bname "m6_fs_$index"
        set bnet "m6_fs_${index}_net"
        if {[$block findInst $bname] ne "NULL" || [$block findNet $bnet] ne "NULL"} {
            error "fanout-split names already present"
        }
        make_instance $bname $cell
        make_net $bnet
        connect_pin $net_name "$bname/A"
        connect_pin $bnet "$bname/X"
        foreach term $selected {
            set iname [[$term getInst] getName]
            set pname [[$term getMTerm] getName]
            disconnect_pin $net_name "$iname/$pname"
            connect_pin $bnet "$iname/$pname"
        }
        set binst [$block findInst $bname]
        lassign [[lindex $selected 0] getInst] ignored
        lassign [[[lindex $selected 0] getInst] getLocation] fx fy
        $binst setLocation [expr {$fx+1840}] $fy
        $binst setPlacementStatus PLACED
        foreach {pg supply} {VPWR vdd VPB vdd VGND vss VNB vss} {
            [$binst findITerm $pg] connect [$block findNet $supply]
        }
        lappend split "$net_name->$bname"
        incr index
    }
    puts "M6 FANOUT SPLIT: [llength $split] nets split: $split"
}
proc pa_m6_upsize_input_receivers {} {
    # The long met4 input nets violate the antenna ratio at the small buf_4
    # gate of the m6_in receivers. Upsizing the receiver increases its gate
    # area, which lowers the ratio, and drives the SRAM input more strongly.
    set count 0
    foreach cell [get_cells -hierarchical -filter {ref_name =~ sky130_fd_sc_hd__buf_*}] {
        set name [get_full_name $cell]
        if {![string match *m6_in_* $name]} { continue }
        unset_dont_touch $name
        replace_cell $name sky130_fd_sc_hd__buf_16
        set_dont_touch $name
        incr count
    }
    puts "M6 ANTENNA BUFFERS: $count m6_in receivers upsized to buf_16"
}
# Preserve the pinned stage's libraries, constraints, repair margins and final
# legalization/routing. Deliberately do NOT estimate routing parasitics before
# loading SPEF: replacing an already-estimated model did not reproduce the
# untouched extracted model in the retained v2 diagnostic.
source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
source $::env(SCRIPTS_DIR)/openroad/common/resizer.tcl
load_rsz_corners
read_current_odb
# The pinned DRT writer's dbAccessPoint::destroy follows its stored ITerm IDs.
# Cell removal can leave those IDs stale. Clear only derived pin-access cache
# before *any* cell/net edits, while all original terminals are still valid.
# Pin access is regenerated by detailed routing; original ODB remains intact.
set m6_access_points [[ord::get_db_block] getAccessPoints]
foreach point $m6_access_points { odb::dbAccessPoint_destroy $point }
puts "M6 REROUTE COPY: cleared [llength $m6_access_points] cached pin-access points before cell edits"
set_propagated_clock [all_clocks]
set_dont_touch_objects
source $::env(SCRIPTS_DIR)/openroad/common/set_rc.tcl
if {$::env(M6_REPAIR_USE_SPEF)} {
    if {$::env(M6_REPAIR_PRIME_ESTIMATE)} { estimate_parasitics -placement }
    pa_m6_read_extracted
    pa_m6_report_rc DIRECT_EXTRACTED
} else {
    pa_m6_prepare_route_copy
    source $::env(SCRIPTS_DIR)/openroad/common/grt.tcl
    estimate_parasitics -global_routing
    pa_m6_report_rc ESTIMATED_ONLY
}
if {$::env(M6_REPAIR_CLOCK_PREDRIVER) ne ""} {
    set master $::env(M6_REPAIR_CLOCK_PREDRIVER)
    if {$master ni {sky130_fd_sc_hd__clkinv_4 sky130_fd_sc_hd__clkinv_8 sky130_fd_sc_hd__clkinv_16}} {
        error "reviewed paired-clock predriver required"
    }
    for {set index 0} {$index < 8} {incr index} {
        set name m6_leaf_${index}_pre
        set instance [[ord::get_db_block] findInst $name]
        if {$instance eq "NULL" || [[$instance getMaster] getName] ni {sky130_fd_sc_hd__clkinv_2 sky130_fd_sc_hd__clkinv_4 sky130_fd_sc_hd__clkinv_8}} {
            error "expected original clock predriver"
        }
        unset_dont_touch $name
        replace_cell $name $master
        set_dont_touch $name
    }
    puts "M6 CLOCK PREDRIVER: eight reviewed predrivers replaced by $master; paired polarity retained"
}
if {$::env(M6_REPAIR_CLOCK_LEAF_CELL) ne ""} {
    set master $::env(M6_REPAIR_CLOCK_LEAF_CELL)
    if {$master ni {sky130_fd_sc_hd__clkbuf_4 sky130_fd_sc_hd__clkbuf_8 sky130_fd_sc_hd__clkbuf_16 sky130_fd_sc_hd__clkinv_4 sky130_fd_sc_hd__clkinv_8 sky130_fd_sc_hd__clkinv_16}} {
        error "reviewed clock leaf cell required"
    }
    # Replace both leaf cells together so the leaf polarity is preserved
    # (two inverters and zero buffers are both non-inverting).
    for {set index 0} {$index < 8} {incr index} {
        foreach name [list m6_leaf_${index}_pre m6_leaf_${index}_drive] {
            set instance [[ord::get_db_block] findInst $name]
            if {$instance eq "NULL"} { error "missing local clock leaf instance $name" }
            unset_dont_touch $name
            replace_cell $name $master
            set_dont_touch $name
        }
    }
    puts "M6 CLOCK LEAF CELL: sixteen leaf cells replaced by $master; polarity preserved"
}
if {$::env(M6_REPAIR_MACRO_LOADS)} {
    set corner [sta::find_corner max_ss_100C_1v60]
    set plan {}
    foreach cell [get_cells -hierarchical -filter {ref_name == sram22_512x32m4w8}] {
        foreach pin [get_pins -of_objects $cell] {
            if {[sta::pin_direction $pin] ne "output"} { continue }
            set cap [expr {[[$pin net] capacitance $corner max]*1e12}]
            if {$cap <= 0.013} { continue }
            set net [[ord::get_db_block] findNet [get_full_name [$pin net]]]
            set receivers {}
            foreach term [$net getITerms] {
                if {[[$term getMTerm] getIoType] eq "INPUT"} { lappend receivers $term }
            }
            if {[llength $receivers] != 1} { error "expected one local SRAM receiver" }
            set receiver [[lindex $receivers 0] getInst]
            set rmaster [[$receiver getMaster] getName]
            if {![regexp {^sky130_fd_sc_hd__buf_([0-9]+)$} $rmaster -> rsize] || ![string match m6_out_* [$receiver getName]]} {
                error "unexpected overloaded SRAM receiver"
            }
            set next_size ""
            foreach {from to} {16 12 12 8 8 6 6 4 4 3 3 2 2 1} {
                if {$rsize == $from} { set next_size $to; break }
            }
            if {$next_size eq ""} { error "no smaller reviewed receiver for $rmaster" }
            lappend plan [list [$receiver getName] $rmaster $next_size $cap]
        }
    }
    foreach row $plan {
        lassign $row name master next_size cap
        unset_dont_touch $name
        replace_cell $name sky130_fd_sc_hd__buf_$next_size
        set_dont_touch $name
        puts "M6 MACRO LOAD: $name $master->buf_$next_size, original SS load $cap pF; re-extracted 7-13 fF checks required"
    }
}
if {$::env(M6_REPAIR_SELECTIVE)} { pa_m6_selective_drivers }
if {$::env(M6_REPAIR_READ_CHAINS)} { pa_m6_compress_read_chains }
if {$::env(M6_REPAIR_RETURN_CHAINS)} { pa_m6_upsize_return_chains }
if {$::env(M6_REPAIR_SPLIT_FANOUT)} { pa_m6_split_high_fanout }
if {$::env(M6_REPAIR_ANTENNA_BUFFERS)} { pa_m6_upsize_input_receivers }
set m6_before_instances [dict create]
foreach instance [[ord::get_db_block] getInsts] {
    dict set m6_before_instances [$instance getName] 1
}
if {$::env(M6_REPAIR_ELECTRICAL)} {
    repair_design -verbose \
        -max_wire_length $::env(GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH) \
        -slew_margin $::env(GRT_DESIGN_REPAIR_MAX_SLEW_PCT) \
        -cap_margin $::env(GRT_DESIGN_REPAIR_MAX_CAP_PCT)
}
if {$::env(M6_REPAIR_NEW_BUFFER_MIN8)} {
    set count 0
    foreach instance [[ord::get_db_block] getInsts] {
        set name [$instance getName]
        if {[dict exists $m6_before_instances $name]} { continue }
        set master [[$instance getMaster] getName]
        if {[regexp {^(sky130_fd_sc_hd__(?:clkbuf|buf))_(1|2|3|4|6)$} $master -> family]} {
            replace_cell $name ${family}_8
            incr count
        }
    }
    puts "M6 NEW WIRE BUFFER STRENGTH: $count new buffers raised to drive-8"
}
if {$::env(M6_REPAIR_TIMING)} {
    repair_timing -setup -setup_margin 0.25 -repair_tns 100 -max_passes 40 \
        -skip_gate_cloning -skip_buffering
    repair_timing -hold -hold_margin 0.15 -max_passes 40 -max_buffer_percent 20
}
if {$::env(M6_LOCAL_CLOCK_NDR)} {
    # Existing minimum widths are 0.14 um. Wider physical routes must still
    # pass detailed routing, extraction and all original electrical limits.
    # DEF round-trip for per-corner RCX requires a rule on every routing layer.
    # Keep each other layer's real technology width, including li1 access.
    set widths {}
    set tech [[ord::get_db] getTech]
    set units [[ord::get_db_block] getDbUnitsPerMicron]
    foreach layer [$tech getLayers] {
        if {[$layer getRoutingLevel] == 0} { continue }
        set name [$layer getName]
        set width [expr {double([$layer getWidth])/$units}]
        if {$name in {met1 met2}} { set width 0.28 }
        lappend widths $name $width
    }
    create_ndr -name m6_local_clock_2w -width $widths
    for {set index 0} {$index < 8} {incr index} {
        set name m6_leaf_${index}_local
        if {[[ord::get_db_block] findNet $name] eq "NULL"} { error "missing local clock net" }
        assign_ndr -ndr m6_local_clock_2w -net $name
    }
    puts "M6 LOCAL CLOCK NDR: eight local clock nets, 0.28-um met1/met2 width"
}
pa_m6_prepare_route_copy
if {$::env(M6_REPAIR_ELECTRICAL) || $::env(M6_REPAIR_TIMING) || $::env(M6_REPAIR_SELECTIVE) || $::env(M6_REPAIR_READ_CHAINS) || $::env(M6_REPAIR_RETURN_CHAINS) || $::env(M6_REPAIR_SPLIT_FANOUT) || $::env(M6_REPAIR_ANTENNA_BUFFERS) || $::env(M6_REPAIR_MACRO_LOADS) || $::env(M6_REPAIR_CLOCK_PREDRIVER) ne "" || $::env(M6_REPAIR_CLOCK_LEAF_CELL) ne ""} {
    source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
} else {
    check_placement -verbose
}
unset_dont_touch_objects
source $::env(SCRIPTS_DIR)/openroad/common/grt.tcl
if {$::env(M6_REPAIR_ANTENNA)} {
    # Detailed wires were already ripped up by pa_m6_prepare_route_copy, so the
    # diodes inserted here can be placed and globally routed cleanly; the
    # following detailed-routing step then wires them without stale conflicts.
    set diode_split [split $::env(DIODE_CELL) "/"]
    repair_antennas "[lindex $diode_split 0]" \
        -iterations $::env(GRT_ANTENNA_ITERS) -ratio_margin $::env(GRT_ANTENNA_MARGIN)
    source $::env(SCRIPTS_DIR)/openroad/common/dpl.tcl
    source $::env(SCRIPTS_DIR)/openroad/common/grt.tcl
    puts "M6 REPAIR ANTENNA: diode insertion after rip-up completed"
}
write_views
