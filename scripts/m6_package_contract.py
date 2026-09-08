"""Package fixed primary extracts; preserve every previously retained bundle."""
import json
import shutil

from scripts.m6_contract_evidence import ROOT, STAGE, TRIALS
from scripts.m6_preflight_evidence import digest


def main():
    destination = ROOT/"docs/evidence/m6_sram_contract"
    sources = {
        "contract.json": "build/m6_sram_contract_v1/contract.json",
        "spice_sanity.json": "build/m6_output_spice_v2/sanity.json",
        "output_driver.spice": "build/m6_output_spice_v2/output_driver.spice",
        "ngspice_version.txt": "build/m6_output_spice_v2/ngspice_version.txt",
        "ss_pin_boundary.json": "build/m6_contract_boundary_ss_v1/boundary.json",
        "ss_pins.tsv": "build/m6_contract_boundary_ss_v1/pins.tsv",
        "ss_pin_report.tcl": "build/m6_contract_boundary_ss_v1/report.tcl",
        "probe_manifest.json": STAGE+"/manifest.json",
        "probe_config.json": STAGE+"/config.json",
    }
    for run in TRIALS:
        states = list((ROOT/STAGE/"runs"/run).glob("*-openroad-stapostpnr/state_out.json"))
        assert len(states) == 1
        prefix = str(states[0].parent.relative_to(ROOT))+"/"
        sources[run+"_state.json"] = prefix+"state_out.json"
        sources[run+"_summary.rpt"] = prefix+"summary.rpt"
        sources[run+"_resolved.json"] = STAGE+"/runs/"+run+"/resolved.json"
        sources[run+"_ss_checks.rpt"] = prefix+"max_ss_100C_1v60/checks.rpt"
        sources[run+"_ss_clock.rpt"] = prefix+"max_ss_100C_1v60/clock.rpt"
    for path in (ROOT/"build/m6_output_spice_v2").glob("*_s*_c*.spice"):
        sources["spice_"+path.name] = str(path.relative_to(ROOT))
        sources["spice_"+path.with_suffix(".log").name] = str(path.with_suffix(".log").relative_to(ROOT))
    destination.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        target = destination/name
        if target.exists():
            assert digest(target) == digest(ROOT/source), "preserve old primary extracts"
        else:
            shutil.copyfile(ROOT/source, target)
    value = {"schema": 1, "status": "PRIMARY_EXTRACTS_NOT_M6_CLOSURE",
        "files": {name: {"source": source, "sha256": digest(ROOT/source)}
                  for name, source in sorted(sources.items())}}
    encoded = json.dumps(value, indent=2, sort_keys=True)+"\n"
    manifest = destination/"manifest.json"
    if manifest.exists():
        assert manifest.read_text() == encoded
    else:
        manifest.write_text(encoded)
    print("SRAM-contract primary extracts packaged; M6 remains unqualified")


if __name__ == "__main__":
    main()
