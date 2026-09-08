// Bounded transaction scoreboard for both original and direct-response modes.
#include "Vpa_m5_obi_router.h"
#include "verilated.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>

static void require(bool okay, const char *what) {
  if (!okay) throw std::runtime_error(what);
}
struct Transaction { uint32_t address, data; unsigned mask, write, route; };
static Transaction transaction(unsigned index) {
  uint32_t word = index * 0x9e3779b9u;
  unsigned region = index % 3;
  return {(region == 2 ? 0x40000000u : region == 1 ? 0x10000u : 0u) | (word & 0xfffcu),
          word ^ 0xa53f19e7u, (index % 15) + 1, (index >> 2) & 1, region == 2};
}
static uint32_t response(const Transaction &t) {
  return t.address ^ t.data ^ (t.mask << 12) ^ t.write;
}
int main(int argc, char **argv) {
  try {
    require(argc == 2, "mode argument required");
    const bool direct = std::atoi(argv[1]) != 0;
    const bool early = std::atoi(argv[1]) == 2;
    const bool instant = std::atoi(argv[1]) == 3;
    VerilatedContext context; context.commandArgs(argc, argv);
    Vpa_m5_obi_router top(&context);
    top.clk_i = 0; top.rst_ni = 0; top.stop_i = 1; top.host_req_i = 0;
    top.host_addr_i = 0; top.host_we_i = 0; top.host_be_i = 0; top.host_wdata_i = 0;
    for (unsigned k=0; k<2; ++k) {
      top.target_gnt_i[k] = 0; top.target_rvalid_i[k] = 0;
      top.target_rdata_i[k] = 0; top.target_err_i[k] = 0;
    }
    auto clock = [&] { top.clk_i=1; top.eval(); context.timeInc(1); top.clk_i=0; top.eval(); };
    top.eval(); for (unsigned i=0; i<4; ++i) clock(); top.rst_ni = 1;
    bool owned=false, downstream=false, offer=false;
    unsigned accepted=0, returned=0, delay=0, handovers=0, stopped_owned=0, cycles=0, early_issues=0, instant_completions=0;
    Transaction expected{}, active{};
    uint32_t random=0x791acf35u;
    for (; returned < 1000 && cycles < 50000; ++cycles) {
      random ^= random << 13; random ^= random >> 17; random ^= random << 5;
      offer = accepted < 1000 && (offer || (random & 3));
      const auto next = transaction(accepted);
      top.stop_i = (random & 31) < 5;
      top.host_req_i = offer; top.host_addr_i = next.address;
      top.host_we_i = next.write; top.host_be_i = next.mask; top.host_wdata_i = next.data;
      for (unsigned k=0; k<2; ++k) {
        top.target_gnt_i[k] = 0;
        top.target_rvalid_i[k] = downstream && !delay && active.route == k;
        top.target_rdata_i[k] = response(active);
        top.target_err_i[k] = (active.address >> 5) & 1;
      }
      top.eval();
      require(!(top.target_req_o[0] && top.target_req_o[1]), "both routes requested");
      bool issued=false, immediate=false;
      const bool early_offer = early && next.address < 65536 &&
          (!owned || (downstream && !delay));
      for (unsigned k=0; k<2; ++k) if (top.target_req_o[k]) {
        const auto &expected_issue = early_offer ? next : expected;
        require((early_offer ? (offer && !top.stop_i) : (owned && !downstream)) &&
                k == expected_issue.route && top.target_addr_o == expected_issue.address &&
                top.target_we_o == expected_issue.write && top.target_be_o == expected_issue.mask &&
                top.target_wdata_o == expected_issue.data,
                "downstream request differs from owned request");
        top.target_gnt_i[k] = (random >> 5) & 1;
        issued |= top.target_gnt_i[k];
        if (instant && k == 0 && expected_issue.address < 65536 && top.target_gnt_i[k] && (random & 4)) {
          immediate = true;
          top.target_rvalid_i[k] = 1;
          top.target_rdata_i[k] = response(expected_issue);
          top.target_err_i[k] = (expected_issue.address >> 5) & 1;
          ++instant_completions;
        }
      }
      top.eval();
      const bool grant=top.host_gnt_o, valid=top.host_rvalid_o;
      if (early_offer) {
        require(grant == issued, "early admission before actual mirror acceptance");
        if (issued) ++early_issues;
      }
      const bool response_retired=downstream && !delay;
      require(!grant || (offer && !top.stop_i), "admission under stop/no offer");
      require(!owned || top.busy_o, "false router quiescence");
      if (top.stop_i && owned) ++stopped_owned;
      if (valid) {
        require(owned && top.host_rdata_o == response(expected) &&
                top.host_err_o == ((expected.address >> 5) & 1), "lost/corrupt/unowned response");
        owned=false; ++returned;
      }
      if (grant) {
        require(!owned, "accepted overlapping ownership");
        expected=next; owned=true; offer=false; ++accepted;
        if (valid) ++handovers;
      }
      clock();
      if (response_retired) downstream=false;
      else if (downstream && delay) --delay;
      if (issued && !immediate) { active=expected; downstream=true; delay=random%8; }
    }
    top.host_req_i=0; top.stop_i=1;
    for (unsigned k=0; k<2; ++k) { top.target_gnt_i[k]=0; top.target_rvalid_i[k]=0; }
    for (unsigned i=0; i<4; ++i) clock();
    require(accepted == 1000 && returned == 1000 && !owned && !downstream &&
            !top.busy_o && stopped_owned > 100 && (direct ? handovers > 100 : handovers == 0) &&
            (early ? early_issues == 334 : early_issues == 0) &&
            (instant ? instant_completions > 100 : instant_completions == 0),
            "missing completion/stop/handover coverage");
    std::printf("STARTUP ROUTER SCOREBOARD PASS direct=%u early=%u instant=%u requests=%u responses=%u handovers=%u stopped_owned=%u early_issues=%u instant_completions=%u cycles=%u\n",
                direct, early, instant, accepted, returned, handovers, stopped_owned, early_issues, instant_completions, cycles);
    top.final(); return 0;
  } catch (const std::exception &e) {
    std::fprintf(stderr, "STARTUP ROUTER SCOREBOARD FAIL %s\n", e.what()); return 1;
  }
}
