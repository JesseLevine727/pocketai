// No PLL: an external memory clock drives a generated half-rate system clock.
module pa_m6_clocking (
  input wire clk_mem_i,
  input wire rst_ni,
  output reg clk_sys_o
);
  always @(negedge clk_mem_i or negedge rst_ni)
    if (!rst_ni) clk_sys_o <= 1'b0;
    else clk_sys_o <= !clk_sys_o;
endmodule
