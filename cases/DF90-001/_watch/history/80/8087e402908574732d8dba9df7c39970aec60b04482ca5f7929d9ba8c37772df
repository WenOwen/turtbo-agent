# -*- coding: utf-8 -*-
"""v8 figures: hub line, spanwise section audit, lean+sweep adjustment.

Written in Python 2.7 syntax on purpose: the only interpreter on this machine
with numpy + matplotlib is the NUMECA FINE 16.1 admin python (2.7.12).
"""
import glob
import json
import math
import os
import re
import sys
from os.path import join

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\automation"
BUILD = join(HERE, "build-par")
MANIFEST = json.loads(open(join(BUILD, "v8_build_manifest.json"), "r").read())


class _B(object):
    HUB_POINTS = [(float(z), float(r)) for z, r in MANIFEST["hub_points"]]


B = _B()

V7 = r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\autoblade"
V8 = r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\autoblade"
FIG = r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\figures"


def read_zr(geom, name):
    text = open(geom, "r").read()
    for block in re.finditer(r"NI_BEGIN\s+basic_curve(.*?)NI_END\s+basic_curve", text, re.S):
        body = block.group(1)
        if re.search(r"NAME\s+%s\b" % name, body):
            zr = re.search(r"ZR\s*\n\s*\+?\d+\s*\n(.*?)NI_END\s+zrcurve", body, re.S).group(1)
            pts = []
            for line in zr.splitlines():
                t = line.split()
                if len(t) >= 2:
                    pts.append((float(t[0]), float(t[1])))
            return pts
    raise KeyError(name)


def read_sections(geom):
    lines = open(geom, "r").read().splitlines()
    out = {}
    for side in ("suction", "pressure"):
        idx = 0
        while lines[idx].strip() != side:
            idx += 1
        while lines[idx].strip() != "SECTIONAL":
            idx += 1
        idx += 1
        count = int(lines[idx].strip().lstrip("+"))
        idx += 1
        secs = {}
        for _ in range(count):
            while not lines[idx].strip().startswith("# section"):
                idx += 1
            si = int(lines[idx].strip().split()[-1])
            idx += 1
            assert lines[idx].strip() == "XYZ"
            idx += 1
            n = int(lines[idx].strip().lstrip("+"))
            idx += 1
            pts = []
            for _ in range(n):
                vals = lines[idx].split()
                x, y, z = float(vals[0]), float(vals[1]), float(vals[2])
                pts.append((math.hypot(x, y), math.atan2(y, x), z))
                idx += 1
            secs[si] = pts
        out[side] = secs
    return out


def metrics(section):
    pts = section["suction"] + section["pressure"]
    r = sum([q[0] for q in pts]) / len(pts)
    zmin = min([q[2] for q in pts])
    zmax = max([q[2] for q in pts])
    dz = zmax - zmin
    wrap = max([q[1] for q in pts]) - min([q[1] for q in pts])
    return r, dz, math.degrees(wrap), math.degrees(math.atan2(wrap * r, dz))


def main():
    if not os.path.isdir(FIG):
        os.makedirs(FIG)
    plt.rcParams.update({"figure.dpi": 140, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})

    hub8 = read_zr(join(V8, "R1_13span", "R1.geomTurbo"), "hub_crv_1")
    shr8 = read_zr(join(V8, "R1_13span", "R1.geomTurbo"), "shroud_crv_1")
    hub7 = read_zr(join(V7, "R1_5span", "R1.geomTurbo"), "hub_crv_1")

    # ---- figure 1: meridional flowpath
    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    ax.plot([z for z, _ in shr8], [r * 1000 for _, r in shr8], color="#1f4e79", lw=1.6, label="shroud (unchanged)")
    ax.plot([z for z, _ in hub7], [r * 1000 for _, r in hub7], color="#999999", lw=1.4, ls="--", label="v7 hub (5 pts)")
    ax.plot([z for z, _ in hub8], [r * 1000 for _, r in hub8], color="#c00000", lw=2.0, label="v8 hub (10 pts)")
    p = B.HUB_POINTS
    ax.plot([z for z, _ in p], [r * 1000 for _, r in p], "o", ms=4.5, color="#c00000")
    for i, (z, r) in enumerate(p, 1):
        ax.annotate("P%d" % i, (z, r * 1000), textcoords="offset points", xytext=(3, -11),
                    fontsize=7.5, color="#c00000")
    ax.axvspan(p[3][0], p[4][0], color="#ffd966", alpha=0.45)
    ax.annotate(u"motor housing\ndia. 188 mm x 84 mm\n|P5-P4| = %.1f mm" %
                (math.hypot(p[4][0] - p[3][0], p[4][1] - p[3][1]) * 1000),
                ((p[3][0] + p[4][0]) / 2, 112), ha="center", fontsize=8, color="#7f6000")
    for z0, z1, lab in ((0.0, 0.0742, "R1 (9 blades)"), (0.0984, 0.1768, "R2 (11 blades)")):
        ax.axvline(z0, color="#548235", lw=0.8, ls=":")
        ax.axvline(z1, color="#548235", lw=0.8, ls=":")
        ax.annotate(lab, ((z0 + z1) / 2, 292), ha="center", fontsize=8, color="#375623")
    ax.set_xlabel("axial z [m]")
    ax.set_ylabel("radius [mm]")
    ax.set_title("v8 ducted fan - meridional flowpath (AutoBlade 16.1 GeomTurbo)")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(join(FIG, "v8-flowpath-hub-line.png"))
    plt.close(fig)

    # ---- figure 2: section properties
    v7sec = read_sections(join(V7, "R1_5span", "R1.geomTurbo"))
    v8sec = read_sections(join(V8, "R1_13span", "R1.geomTurbo"))
    spans13 = [0.5 * (1 - math.cos(i * math.pi / 12)) for i in range(13)]
    m8 = [metrics({"suction": v8sec["suction"][i], "pressure": v8sec["pressure"][i]})
          for i in sorted(v8sec["suction"])]
    m7 = [metrics({"suction": v7sec["suction"][i], "pressure": v7sec["pressure"][i]})
          for i in sorted(v7sec["suction"])]
    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.6))
    specs = ((3, "stagger angle [deg]", 1.0), (1, "axial chord [mm]", 1000.0),
             (2, "theta wrap [deg]", 1.0))
    for ax, (idx, lab, scale) in zip(axes, specs):
        ax.plot(spans13, [m[idx] * scale for m in m8], "o-", ms=3.5, color="#c00000", lw=1.6,
                label="v8 (13 sections)")
        ax.plot([0, .25, .5, .75, 1], [m[idx] * scale for m in m7], "s--", ms=5,
                color="#1f4e79", lw=1.2, label="v7 (5 sections)")
        ax.set_xlabel("span fraction")
        ax.set_ylabel(lab)
        ax.set_title(lab)
    axes[0].legend(fontsize=8, loc="best")
    fig.suptitle("R1 blade sections - v8 13-section rebuild matches the v7 design at shared spans",
                 fontsize=10, y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(join(FIG, "v8-sections-vs-v7.png"))
    plt.close(fig)

    # ---- figure 3: lean / sweep delta
    delta = json.loads(open(join(HERE, "leansweep", "leansweep_delta.json"), "r").read())
    spans = [d["span"] for d in delta]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.6))
    axes[0].plot(spans, [d["dz_mm"] for d in delta], "o-", color="#2e75b6", ms=4)
    axes[0].set_xlabel("span fraction")
    axes[0].set_ylabel("delta z of LE [mm]")
    axes[0].set_title(u"sweep (lue) - simple Bezier SWEEP_BETA 0 -> 1.0 deg")
    axes[1].plot(spans, [d["d_tangential_mm"] for d in delta], "o-", color="#c55a11", ms=4)
    axes[1].set_xlabel("span fraction")
    axes[1].set_ylabel("delta tangential position [mm]")
    axes[1].set_title(u"lean (wan) - simple Bezier LEAN_BETA 0.371 -> 1.5 deg")
    fig.tight_layout()
    fig.savefig(join(FIG, "v8-lean-sweep-delta.png"))
    plt.close(fig)

    print("figures written to " + FIG)
    for f in sorted(glob.glob(join(FIG, "*.png"))):
        print("   %s  %d bytes" % (f, os.path.getsize(f)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
