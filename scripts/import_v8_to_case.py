import sys, os, json, hashlib, shutil
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

V8 = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8")
CASE = Path(r"D:\Project\Research\turtbo-agent\cases\DF90-001")

SKIP_EXT = {'.cgns', '.iec', '.res', '.mf', '.xmf', '.adf', '.zip', '.geom'}
SKIP_DIRS = {'__pycache__'}

# 映射：v8 子路径 -> 案例内目标
MAP = [
    ("autoblade", "02-geometry/v8/autoblade"),
    ("figures",   "02-geometry/v8/figures"),
    ("mesh/mesh-v1", "03-mesh/v1"),
    ("mesh/mesh-v2", "03-mesh/v2"),
    ("fine/v8-optimized", "04-solve/v1"),
    ("automation", "_automation/v8"),
]
TOP_FILES = [("README.md", "02-geometry/v8/README-v8.md")]

copied, skipped_big = [], []

def sha256(p, cap=None):
    h = hashlib.sha256()
    with p.open('rb') as fh:
        while True:
            b = fh.read(1 << 20)
            if not b: break
            h.update(b)
    return h.hexdigest()

for src_rel, dst_rel in MAP:
    src_root = V8 / src_rel
    if not src_root.exists():
        print("MISS", src_rel); continue
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            rel = p.relative_to(src_root)
            if p.suffix.lower() in SKIP_EXT:
                skipped_big.append(p)
                continue
            dst = CASE / dst_rel / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            copied.append((dst, p.stat().st_size))

for src_rel, dst_rel in TOP_FILES:
    p = V8 / src_rel
    if p.exists():
        dst = CASE / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        copied.append((dst, p.stat().st_size))

print("复制文件数:", len(copied), " 总字节:", sum(s for _, s in copied))
print("跳过的大二进制:", len(skipped_big), " 总字节:", sum(p.stat().st_size for p in skipped_big))

# 大二进制索引（外部引用，不复制）
index = {"note": "以下大二进制保留在 Ducted-Fan v8 原址，本案例只登记路径与哈希，不复制内容。",
         "source_root": str(V8), "generated_by": "tools/_import_v8.py", "files": []}
for p in sorted(skipped_big):
    st = p.stat()
    entry = {"path": str(p), "rel": str(p.relative_to(V8)).replace(os.sep, "/"),
             "bytes": st.st_size, "mtime": st.st_mtime}
    if st.st_size <= 300 * 1024 * 1024:
        entry["sha256"] = sha256(p)
    else:
        entry["sha256"] = "SKIPPED_OVER_300MB"
    index["files"].append(entry)

ext = CASE / "_external"
ext.mkdir(parents=True, exist_ok=True)
(ext / "v8-large-binaries.json").write_text(
    json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8', newline='')
print()
print("外部索引:", len(index["files"]), "项 ->", str(ext / "v8-large-binaries.json"))
for f in index["files"]:
    print("   %-58s %8.2f MB  %s" % (f["rel"], f["bytes"]/1048576, f["sha256"][:12]))
