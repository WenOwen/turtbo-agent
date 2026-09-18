import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
out = r"D:\Project\Research\turtbo-agent\docs\liveview-screenshot.png"
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width":1240,"height":1000})
    pg.goto("http://127.0.0.1:8899/", wait_until="load")
    pg.wait_for_timeout(3000)
    pg.screenshot(path=out, full_page=True)
    print("saved:", out)
    print("title:", pg.title())
    b.close()
