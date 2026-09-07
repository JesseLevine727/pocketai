    // Zero-DSP fast-M correction: split each signed 17x17 MAC into three
    // stages. Two 9x17 partial products, product assembly, then accumulation.
    // MUL uses 9 execute cycles; MULH uses 12 (plus external stalls).
    // The original ALBL/ALBH/AHBL/AHBH arithmetic and iterative divider stay.
    logic [1:0] mac_phase_q;
    logic signed [25:0] product_low_q, product_high_q;
    logic signed [33:0] product_q;
    assign mult_commit = mac_phase_q == 2;
    assign mac_res_signed = $signed(product_q) + $signed(accum);
    assign mac_res_ext = $unsigned(mac_res_signed);
    assign mac_res = mac_res_ext[33:0];
