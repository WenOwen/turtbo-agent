
import re, math, json, sys
from pathlib import Path
ROOT = Path(r"D:\Project\Research\turtbo-agent")
G = ROOT / "cases/DF90-001/02-geometry/v8/autoblade"

def par_betas(par):
    lines = par.read_text(encoding="utf-8", errors="replace").splitlines()
    out = {}
    for i, line in enumerate(lines):
        m = re.search(r"NAME\s+S(\d+)_CAMBER_BETA([12])\s*$", line.strip())
        if not m: continue
        for j in range(i+1, min(i+8, len(lines))):
            vm = re.match(r"\s*VALUE\s+([-\d.eE+]+)\s*$", lines[j])
            if vm:
                out.setdefault(int(m.group(1)), {})[m.group(2)] = float(vm.group(1)); break
    return out

def par_simple(par, key):
    txt = par.read_text(encoding="utf-8", errors="replace")
    vals = re.findall(r"NAME\s+"+key+r"\s*\r?\n\s*VALUE\s+([-\d.eE+]+)", txt)
    return vals

for name in ("R1","R2"):
    par = G / (name+"_13span") / (name+".par")
    b = par_betas(par)
    print("===", name, "sections:", sorted(b))
    for k in sorted(b):
        print("  S%-2d beta1=%9.4f  beta2=%9.4f   turn=%8.4f" % (k, b[k].get("1",float('nan')), b[k].get("2",float('nan')), b[k].get("1",0)-b[k].get("2",0)))
    for key in ("ROTATION_SPEED","OMEGA","ROTATING","LEAN_BETA","STAGGER","SWEEP_BETA","BEZIER_BETA1_BETA2","NUMBER_OF_BLADES","PERIODICITY"):
        v = par_simple(par, key)
        if v: print("   ", key, "=", v[:4])
