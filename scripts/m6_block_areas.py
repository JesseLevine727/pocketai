"""Trace synthesis-only block areas without conflating them with routed PPA."""
import argparse
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def block(name):
    for needle, owner in (("u_core0", "hart0"), ("u_core1", "hart1"),
                          ("u_gemm", "gemm"), ("u_sfpu", "sfpu"),
                          ("startup_instruction_mem", "instruction_mirror"),
                          ("startup_data_read_mem", "data_mirror"), ("u_ram", "scratchpad")):
        if re.search(r"(?:^|[./])"+needle+r"(?:[./]|$)",name): return owner
    return "other_control_and_boundary"


def extract_asic(netlist, liberty, macro_lef):
    cell_areas={}
    text=liberty.read_text()
    for match in re.finditer(r'\bcell\s*\("([^"]+)"\)\s*\{(.*?)(?=\n    cell\s*\(|\Z)',text,re.S):
        area=re.search(r'\barea\s*:\s*([0-9.]+)\s*;',match[2])
        assert area,match[1]
        cell_areas[match[1]]=Decimal(area[1])
    assert len(cell_areas)>100
    size=re.search(r"SIZE\s+([0-9.]+)\s+BY\s+([0-9.]+)",macro_lef.read_text())
    macro_area=Decimal(size[1])*Decimal(size[2])
    design=json.loads(netlist.read_text())["modules"]["pa_m6_soc"]
    groups=defaultdict(lambda:dict(standard_cells=0,macros=0,standard_cell_um2=Decimal(0),sram_um2=Decimal(0)))
    for name,cell in design["cells"].items():
        group=groups[block(name)]
        if cell["type"]=="sram22_512x32m4w8":
            group["macros"]+=1; group["sram_um2"]+=macro_area
        else:
            assert cell["type"] in cell_areas,cell["type"]
            group["standard_cells"]+=1; group["standard_cell_um2"]+=cell_areas[cell["type"]]
    for group in groups.values():
        group["total_instance_um2"]=group["standard_cell_um2"]+group["sram_um2"]
    total={key:sum(g[key] for g in groups.values()) for key in next(iter(groups.values()))}
    assert total["macros"]==292
    return dict(status="SYNTHESIS_ONLY_NOT_ROUTED_CHIP_AREA",groups=dict(sorted(groups.items())),total=total)


def extract_fpga(report):
    rows={}
    for line in report.read_text().splitlines():
        fields=[x.strip() for x in line.split("|")]
        if len(fields)!=12 or not fields[3].isdigit(): continue
        name=fields[1]
        if name in ("pa_cluster_m5_board","u_core0","u_core1","u_gemm","u_sfpu","u_ram"):
            assert name not in rows
            rows[name]=dict(zip(("LUT","logic_LUT","LUTRAM","SRL","FF","BRAM36","BRAM18","DSP"),
                                map(int,fields[3:11])))
    total=rows.pop("pa_cluster_m5_board")
    assert {"u_core0","u_core1","u_gemm","u_sfpu"} <= set(rows), "missing mandatory block row"
    assert total["DSP"]==0
    groups={block(name):row for name,row in rows.items()}
    groups["other_control_and_mirrors"]={key:total[key]-sum(g[key] for g in groups.values()) for key in total}
    assert all(value>=0 for value in groups["other_control_and_mirrors"].values())
    return dict(status="SEPARATE_HIERARCHICAL_OOC_SYNTHESIS_NOT_QUALIFIED_ROUTED_BUILD",
        note="fast multiplier has explicit no-DSP synthesis attribute; original functional RTL unchanged",
        groups=groups,total=total)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    netlist=ROOT/"build/m6_core_physical_v4/runs/synth_v2/06-yosys-synthesis/pa_m6_soc.nl.v.json"
    liberty=ROOT/"build/m6_pdks/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
    macro_lef=ROOT/"build/m6_sram512_v1/sram22_512x32m4w8.lef"
    fpga=ROOT/"build/m6_fpga_blocks_v2/hierarchy.rpt"
    result=dict(status="AREA_EXPERIMENTS_ONLY_NOT_M6_CLOSURE",asic=extract_asic(netlist,liberty,macro_lef),
        fpga=extract_fpga(fpga),artifacts={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in (netlist,liberty,macro_lef,fpga)})
    encoded=json.dumps(result,indent=2,sort_keys=True,default=lambda d:float(d))+"\n"
    if args.output:
        assert not args.output.exists(),"retain previous result; use a new M6 output"
        assert args.output.resolve().parent.name.startswith("m6_")
        args.output.write_text(encoded)
    else: print(encoded,end="")


if __name__=="__main__": main()
