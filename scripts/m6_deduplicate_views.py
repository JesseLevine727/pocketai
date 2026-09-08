"""Hard-link byte-identical, completed M6 physical views; preserve every path.

Default is read-only. --apply replaces redundant copies atomically only after
full-content comparison, then verifies all hashes. Never use on a running flow:
these selected completed run directories must remain immutable afterwards.
No M1-M5 artifacts, user files, logs, or non-M6 paths are targets.
"""
import argparse
from collections import defaultdict
import filecmp
import os
from pathlib import Path
import tempfile

from scripts.m6_preflight_evidence import ROOT, digest

TRIAL=ROOT/"build/m6_core_physical_v3"
RUNS=("floorplan_v2","placement_v3","placement_v4","clocks_v1",
      "clocks_v2","clockcheck_v1","clocks_v3","clocks_v6")
SUFFIXES=(".v",".odb",".def",".sdf",".spef",".gds",".json")
EXTRA_RUNS=(ROOT/"build/m6_core_physical_v4/runs/synth_v2",
            ROOT/"build/m6_core_physical_v4/runs/floorplan_v1")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    by_size=defaultdict(list)
    for directory in [TRIAL/"runs"/run for run in RUNS] + list(EXTRA_RUNS):
        assert directory.is_dir() and not directory.is_symlink()
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.is_symlink() or path.suffix not in SUFFIXES: continue
            stat=path.stat()
            if stat.st_size<100000: continue
            assert stat.st_uid==os.getuid(),path
            by_size[stat.st_size].append(path)
    pairs=[]
    bytes_saved=0
    hashes={}
    for size,paths in by_size.items():
        if len(paths)<2: continue
        by_hash={}
        seen_inodes=set()
        for path in paths:
            stat=path.stat(); inode=(stat.st_dev,stat.st_ino)
            if inode in seen_inodes: continue
            seen_inodes.add(inode)
            sha=digest(path); hashes[path]=sha
            if sha not in by_hash: by_hash[sha]=path; continue
            canonical=by_hash[sha]
            assert filecmp.cmp(canonical,path,shallow=False)
            pairs.append((canonical,path,stat))
            bytes_saved+=stat.st_blocks*512
    print(f"M6 IDENTICAL VIEW COPIES: {len(pairs)} replacements, {bytes_saved} allocated bytes recoverable")
    if not args.apply:
        print("READ-ONLY: no files changed")
        return
    for canonical,path,before in pairs:
        now=path.stat()
        assert (now.st_ino,now.st_size,now.st_mtime_ns)==(before.st_ino,before.st_size,before.st_mtime_ns),path
        assert digest(path)==hashes[path]==digest(canonical)
        fd,tempname=tempfile.mkstemp(prefix=".m6-identical-view-",dir=path.parent)
        os.close(fd)
        temporary=Path(tempname)
        temporary.unlink()  # Only this just-created empty temporary file.
        os.link(canonical,temporary)
        os.replace(temporary,path)  # Atomic replacement by identical retained data.
        assert digest(path)==hashes[path]
    for path,sha in hashes.items(): assert digest(path)==sha,path
    print("M6 VIEW DEDUPLICATION PASS: all original paths and full-content hashes preserved")


if __name__=="__main__": main()
