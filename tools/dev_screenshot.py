"""dev_screenshot.py - 开发用截图。不参与工作流，只用来核对界面长什么样。

用法
----
  python tools/dev_screenshot.py                  # 整个工作台
  python tools/dev_screenshot.py --views          # 只截「看设计」卡片
  python tools/dev_screenshot.py --svg <file.svg> --out docs/x.png
"""
import argparse
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8899/")
    ap.add_argument("--views", action="store_true", help="只截 #view-card")
    ap.add_argument("--svg", help="直接打开一个 .svg 文件并截图")
    ap.add_argument("--out", default=str(ROOT / "docs" / "liveview-screenshot.png"))
    ap.add_argument("--wait", type=int, default=3000)
    args = ap.parse_args(argv)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1240, "height": 1200})
        if args.svg:
            src = pathlib.Path(args.svg).resolve()
            pg.goto(src.as_uri(), wait_until="load")
            pg.wait_for_timeout(500)
            (pg.query_selector("svg") or pg).screenshot(path=args.out)
        else:
            pg.goto(args.url, wait_until="load")
            pg.wait_for_timeout(args.wait)
            if args.views:
                el = pg.query_selector("#view-card")
                (el or pg).screenshot(path=args.out)
            else:
                pg.screenshot(path=args.out, full_page=True)
            print("title:", pg.title())
        print("saved:", args.out)
        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())