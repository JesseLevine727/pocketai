"""Instrument explicit memory-use exclusions in an isolated 1x simulation.

These are runtime assertions plus a hash-bound source review, not a formal
equivalence proof. They do not modify the physical candidate or its oracles.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]


def instrument(text):
    checks = {
        "pa_m5_axi_burst": """
  always @(posedge clk_i) if (rst_ni)
    assert (!(mem_we && mem_re)) else $fatal(1,"AXI burst memory read/write overlap");
""",
        "pa_m6_cluster_core": r"""
  always @(posedge IO_CLK) if (IO_RST_N && mirror_write) begin
    assert (!(\actual_read[0]  || \actual_read[1]  ||
              \predict_read[0]  || \predict_read[1] ))
      else $fatal(1,"instruction mirror consumes a write-cycle read");
    assert (!(\startup_data_gnt[0]  || \startup_data_gnt[1] ))
      else $fatal(1,"data mirror consumes a write-cycle read");
  end
""",
        "pa_gemm": r"""
  always @(posedge clk_i) if (rst_ni && issue_valid) begin
    if (engine_slot_q == 0)
      assert (!(\a_we[0]  || \b_we[0] )) else $fatal(1,"active GEMM slot written while issuing read");
    else
      assert (!(\a_we[1]  || \b_we[1] )) else $fatal(1,"active GEMM slot written while issuing read");
  end
""",
        "pa_sfpu": """
  // Hash-bound enum review: Compute=3, OutputRead=4 in pa_sfpu;
  // ReadWait=2 in pa_sfpu_compute. These are pre-synthesis state encodings.
  always @(posedge clk_i) if (rst_ni) begin
    if (state_q == 3 && u_compute.state_q == 2)
      assert (!x_write && !load_memory) else $fatal(1,"SFPU operand read overwritten");
    if (state_q == 4)
      assert (!x_write) else $fatal(1,"SFPU output read overwritten");
  end
""",
    }
    found = {}
    def replace(match):
        header, body = match[1], match[2]
        key = next((name for name in checks
                    if re.search(r"(?:^|\\)" + name + r"(?:\s|\\|\()", header)), None)
        if key is None:
            return match[0]
        if key in found:
            raise ValueError(f"ambiguous consumer module: {key}")
        found[key] = header.strip()
        return "module " + header + body + checks[key] + "endmodule"
    result = re.sub(r"\bmodule\s+([^\n]+\n)(.*?)\bendmodule", replace, text, flags=re.S)
    if set(found) != set(checks):
        raise ValueError(f"missing consumer assertion targets: {set(checks)-set(found)}")
    return result, found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembly", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    assembly, output = args.assembly.resolve(), args.output.resolve()
    for path in (assembly, output):
        if path.parent != ROOT / "build" or not path.name.startswith("m6_"):
            parser.error("direct M6 build paths required")
    if output.exists():
        parser.error("retain prior trials; output must be fresh")
    original = (assembly / "portable.v").read_text()
    result, found = instrument(original)
    output.mkdir()
    (output / "portable.v").write_text(result)
    # Retain the exact uninstrumented netlist to establish candidate identity.
    shutil.copyfile(assembly / "portable.json", output / "portable.json")
    manifest = {"status": "INSTRUMENTED_NOT_RUN", "formal_proof": False,
                "assembly": str(assembly.relative_to(ROOT)),
                "input_sha256": hashlib.sha256(original.encode()).hexdigest(),
                "output_sha256": hashlib.sha256(result.encode()).hexdigest(),
                "assertion_targets": found,
                "scratchpad_contract": "Store response data is not an architectural load result; byte writes/acknowledgments retained.",
                "read_use_scope": "Runtime checks for mirror requests, GEMM active slot, SFPU operand/output issue, AXI burst exclusion"}
    (output / "consumer_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    print("M6 consumer assertions inserted in 4 module types; runtime qualification pending")


if __name__ == "__main__":
    main()
