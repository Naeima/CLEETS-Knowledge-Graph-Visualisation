#!/usr/bin/env python3
"""Run the page's force layout headlessly and save the settled node positions."""
import sys, os, re, json, asyncio
from playwright.async_api import async_playwright
page_path, out_json = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
W, H = int(sys.argv[3]) if len(sys.argv) > 3 else 1000, int(sys.argv[4]) if len(sys.argv) > 4 else 720
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from localdeps import inline_d3, strip_font_link, page  # noqa: E402
body = strip_font_link(inline_d3(open(page_path, encoding="utf-8").read()))
body = re.sub(r'"pos":\{.*?\},"stats"', '"stats"', body, flags=re.S)   # drop any earlier bake so the layout starts fresh
f = os.path.join(os.path.dirname(out_json), "_bake.html")
open(f, "w", encoding="utf-8").write(page(body, extra_css=f".vcanvas{{width:{W}px!important;height:{H}px!important}}"))
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(); pg = await br.new_page(viewport=dict(width=W + 340, height=H + 300))
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + f); await pg.wait_for_timeout(300)
        await pg.evaluate("window.__vowlSettle()")
        pos = await pg.evaluate("window.__vowlLayout()")
        json.dump(pos, open(out_json, "w"), separators=(",", ":"))
        print("baked", len(pos), "positions; errors:", errs)
        await br.close()
asyncio.run(main())
