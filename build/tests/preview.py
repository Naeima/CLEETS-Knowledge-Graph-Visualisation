#!/usr/bin/env python3
"""Wrap the artifact body in the publish skeleton and screenshot it with Chromium.
usage: preview.py <page.html> <outdir> [--fallback-fonts]
"""
import sys, os, re, json, base64, asyncio
from playwright.async_api import async_playwright

page_path, outdir = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
fallback = "--fallback-fonts" in sys.argv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the build directory
from localdeps import inline_d3, strip_font_link, fontsource_dir, page  # noqa: E402
FONTS = fontsource_dir()
faces = [("Barlow", "barlow", 400), ("Barlow", "barlow", 500), ("Barlow", "barlow", 600),
         ("Barlow Semi Condensed", "barlow-semi-condensed", 500), ("Barlow Semi Condensed", "barlow-semi-condensed", 600),
         ("IBM Plex Mono", "ibm-plex-mono", 400), ("IBM Plex Mono", "ibm-plex-mono", 500)]
css = ""
if not fallback:
    for fam, pkg, w in faces:
        b = base64.b64encode(open(os.path.join(FONTS, pkg, "files", f"{pkg}-latin-{w}-normal.woff2"), "rb").read()).decode()
        css += f"@font-face{{font-family:'{fam}';font-weight:{w};font-style:normal;src:url(data:font/woff2;base64,{b}) format('woff2')}}\n"
body = strip_font_link(inline_d3(open(page_path, encoding="utf-8").read()), f"<style>{css}</style>")

async def main():
    os.makedirs(outdir, exist_ok=True)
    shots = json.loads(os.environ.get("SHOTS", "[]")) or [
        dict(name="desk-light-all", w=1440, h=1000, theme="light", sel="all", full=True),
    ]
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for s in shots:
            html = page(body, theme=s["theme"])
            f = os.path.join(outdir, f"_{s['name']}.html")
            open(f, "w", encoding="utf-8").write(html)
            ctx = await br.new_context(viewport=dict(width=s["w"], height=s["h"]), device_scale_factor=s.get("dpr", 1),
                                       color_scheme=s["theme"], has_touch=s.get("touch", False))
            pg = await ctx.new_page()
            errs = []
            pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
            await pg.goto("file://" + f + ("#" + s["sel"] if s.get("sel") and s["sel"] != "all" and s.get("viahash") else ""))
            await pg.wait_for_timeout(350)
            if s.get("sel") and s["sel"] != "all" and not s.get("viahash"):
                await pg.click(f"#tab-{s['sel']}")
                await pg.wait_for_timeout(300)
            for js in s.get("eval", []):
                r = await pg.evaluate(js)
                if r is not None:
                    print(f"  [{s['name']}] eval ->", json.dumps(r)[:1500])
            if s.get("hover"):
                await pg.hover(s["hover"])
                await pg.wait_for_timeout(200)
            out = os.path.join(outdir, s["name"] + ".png")
            if s.get("clip"):
                el = await pg.query_selector(s["clip"])
                await el.screenshot(path=out)
            else:
                await pg.screenshot(path=out, full_page=s.get("full", False))
            ov = await pg.evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, h: document.documentElement.scrollHeight})")
            print(s["name"], ov, "errors:", errs[:6])
            await ctx.close()
        await br.close()

asyncio.run(main())
