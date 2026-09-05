# Read-only timing diagnostics for a saved implementation checkpoint.
open_checkpoint $::env(M3_DIAGNOSTIC_DCP)
report_timing -delay_type max -max_paths 100 -nworst 1 \
    -file $::env(M3_DIAGNOSTIC_REPORT)
report_timing_summary -file "$::env(M3_DIAGNOSTIC_REPORT).summary"
