# Area-only experiment uses the qualified clock target, without claiming timing.
create_clock -name sys_clk -period 10.989010989 [get_ports s_axi_aclk]
