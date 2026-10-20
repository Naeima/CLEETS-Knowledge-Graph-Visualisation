#!/usr/bin/env python3
"""Interaction and layout checks for the built page (headless Chromium)."""
import sys, os, re, json, asyncio
from playwright.async_api import async_playwright
page_path = os.path.abspath(sys.argv[1]); outdir = os.path.abspath(sys.argv[2])
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the build directory
from localdeps import inline_d3, strip_font_link, page  # noqa: E402
body = strip_font_link(inline_d3(open(page_path, encoding="utf-8").read()))   # fallback fonts: the widest case
f = os.path.join(outdir, "_itest.html"); open(f, "w", encoding="utf-8").write(page(body))
M = json.loads(re.search(r'<script id="model" type="application/json">(.*?)</script>', body, re.S).group(1))
res = []
def ok(name, cond, info=""):
    res.append((name, bool(cond), info))

async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport=dict(width=1440, height=1000))
        pg = await ctx.new_page(); errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + f); await pg.wait_for_timeout(300); await pg.click("#view-schematic"); await pg.wait_for_timeout(100)
        ok("starts on All datasets", await pg.get_attribute("#tab-all", "aria-selected") == "true")
        ok("no selection class at start", not await pg.evaluate("document.querySelector('#kg').classList.contains('has-sel')"))
        ok("node count", await pg.evaluate("document.querySelectorAll('#kg .n').length") == len(M["nodes"]))
        ok("edge count", await pg.evaluate("document.querySelectorAll('#kg .e:not(.trunk)').length") == len(M["edges"]))
        # every tab: highlight set matches the model, strip names the dataset, cards render
        for t in M["tabs"][1:]:
            await pg.click(f"#tab-{t['id']}"); await pg.wait_for_timeout(60)
            hl = M["hl"][t["id"]]
            n_on = await pg.evaluate("document.querySelectorAll('#kg .on:not(.el)').length")
            n_ctx = await pg.evaluate("document.querySelectorAll('#kg .ctx:not(.el)').length")
            ok(f"{t['id']}: highlighted elements", n_on == len(hl["on"]) and n_ctx == len(hl["ctx"]), f"{n_on}/{len(hl['on'])} on, {n_ctx}/{len(hl['ctx'])} ctx")
            ok(f"{t['id']}: strip heading", (await pg.inner_text("#strip h2")).strip() == t["id"])
            ok(f"{t['id']}: cards", await pg.evaluate("document.querySelectorAll('#detail .card').length") == len(M["panels"][t["id"]]["cards"]))
            ok(f"{t['id']}: selected node ring", await pg.evaluate(f"document.querySelector('#kg [data-id=\"ds:{t['id']}\"]').classList.contains('sel')"))
            ok(f"{t['id']}: page does not scroll sideways", await pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
        # keyboard on the tab list
        await pg.click("#tab-all"); await pg.keyboard.press("ArrowRight")
        ok("ArrowRight moves to the first dataset tab", await pg.get_attribute(f"#tab-{M['tabs'][1]['id']}", "aria-selected") == "true")
        await pg.keyboard.press("End")
        ok("End moves to the last tab", await pg.get_attribute(f"#tab-{M['tabs'][-1]['id']}", "aria-selected") == "true")
        await pg.keyboard.press("Home")
        ok("Home returns to All datasets", await pg.get_attribute("#tab-all", "aria-selected") == "true")
        # click a dataset node in the map, then again to clear
        await pg.click('#kg [data-id="ds:EVCI9001"]')
        ok("clicking a dataset node selects its tab", await pg.get_attribute("#tab-EVCI9001", "aria-selected") == "true")
        ok("hash follows the selection", await pg.evaluate("location.hash") == "#EVCI9001")
        await pg.click('#kg [data-id="ds:EVCI9001"]')
        ok("clicking it again clears the selection", await pg.get_attribute("#tab-all", "aria-selected") == "true")
        # Enter on a focused dataset node
        await pg.focus('#kg [data-id="ds:WIMD2025"]'); await pg.keyboard.press("Enter")
        ok("Enter on a dataset node selects it", await pg.get_attribute("#tab-WIMD2025", "aria-selected") == "true")
        # a chip in the detail cards switches dataset
        await pg.click('#detail .chip[data-ds="ONSGeoLookup"]')
        ok("dataset chip switches tab", await pg.get_attribute("#tab-ONSGeoLookup", "aria-selected") == "true")
        # tooltip on hover and on focus, hidden on Escape
        await pg.hover('#kg [data-id="g:EVKeepership"]'); await pg.wait_for_timeout(80)
        ok("tooltip shows on hover", await pg.is_visible("#tip") and "EVKeepership" in await pg.inner_text("#tip"))
        tb = await pg.evaluate("(()=>{const r=document.querySelector('#tip').getBoundingClientRect();return [r.left,r.top,r.right,r.bottom,innerWidth,innerHeight]})()")
        ok("tooltip stays inside the viewport", tb[0] >= 0 and tb[1] >= 0 and tb[2] <= tb[4] and tb[3] <= tb[5], str(tb))
        await pg.mouse.move(5, 5); await pg.wait_for_timeout(60)
        ok("tooltip hides when the pointer leaves", not await pg.is_visible("#tip"))
        await pg.focus('#kg [data-id="c:cleets:Observation"]'); await pg.wait_for_timeout(60)
        ok("tooltip shows on keyboard focus", await pg.is_visible("#tip") and "cleets:Observation" in await pg.inner_text("#tip"))
        await pg.keyboard.press("Escape")
        ok("Escape hides the tooltip", not await pg.is_visible("#tip"))
        # trunk tooltip aggregates the shared line
        box = await pg.evaluate("(()=>{const p=[...document.querySelectorAll('#kg .e.trunk .hit')][0].getBoundingClientRect();return [p.left+p.width/2,p.top+p.height/2]})()")
        await pg.mouse.move(box[0], box[1]); await pg.wait_for_timeout(80)
        ok("shared line shows the summed tooltip", await pg.is_visible("#tip") and "observation series" in await pg.inner_text("#tip"), (await pg.inner_text("#tip"))[:60] if await pg.is_visible("#tip") else "hidden")
        await pg.mouse.move(5, 5)
        # zoom
        w0 = await pg.evaluate("document.querySelector('#kg').getBoundingClientRect().width")
        await pg.click("#zin"); await pg.click("#zin")
        w1 = await pg.evaluate("document.querySelector('#kg').getBoundingClientRect().width")
        ok("zoom in widens the map", abs(w1 / w0 - 1.5) < 0.02, f"{w0:.0f} -> {w1:.0f}")
        ok("zoomed map scrolls inside its own box", await pg.evaluate("(()=>{const c=document.querySelector('#canvas');return c.scrollWidth>c.clientWidth && document.documentElement.scrollWidth<=document.documentElement.clientWidth})()"))
        await pg.click("#zfit")
        w2 = await pg.evaluate("document.querySelector('#kg').getBoundingClientRect().width")
        ok("Fit restores the width", abs(w2 - w0) < 1)
        # text never wider than its box, even in fallback fonts
        over = await pg.evaluate("""[...document.querySelectorAll('#kg text[data-max]')].filter(t=>t.getComputedTextLength()>+t.dataset.max+0.6).map(t=>t.textContent)""")
        ok("no label wider than its node", not over, str(over))
        squeezed = await pg.evaluate("""[...document.querySelectorAll('#kg text[textLength]')].map(t=>t.textContent)""")
        print("  labels squeezed with fallback fonts:", squeezed)
        # geometry: node boxes never overlap; labels never sit on a node
        geo = await pg.evaluate("""(()=>{
          const bb=e=>{const r=e.getBBox();return [r.x,r.y,r.x+r.width,r.y+r.height]};
          const hit=(a,b)=>a[0]<b[2]-0.5&&b[0]<a[2]-0.5&&a[1]<b[3]-0.5&&b[1]<a[3]-0.5;
          const nodes=[...document.querySelectorAll('#kg .n')].map(n=>[n.dataset.id||'oplist',bb(n.querySelector('.box'))]);
          const out=[];
          for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++)if(hit(nodes[i][1],nodes[j][1]))out.push(nodes[i][0]+' x '+nodes[j][0]);
          const labs=[...document.querySelectorAll('#kg .el')].map(t=>{const r=t.getBoundingClientRect();return [t.textContent,[r.left,r.top,r.right,r.bottom]]});
          const nb=[...document.querySelectorAll('#kg .n .box')].map(n=>{const r=n.getBoundingClientRect();return [r.left,r.top,r.right,r.bottom]});
          for(const [t,r] of labs)for(const b of nb)if(hit(r,b))out.push('label '+t+' on a node');
          for(let i=0;i<labs.length;i++)for(let j=i+1;j<labs.length;j++)if(hit(labs[i][1],labs[j][1]))out.push('labels collide: '+labs[i][0]+' / '+labs[j][0]);
          const vb=document.querySelector('#kg').viewBox.baseVal;
          for(const [id,b] of nodes)if(b[0]<0||b[1]<0||b[2]>vb.width||b[3]>vb.height)out.push(id+' outside the drawing');
          return out})()""")
        ok("no overlapping nodes or labels", not geo, str(geo))
        ok("no console errors", not errs, str(errs[:5]))
        await ctx.close()
        # deep link
        ctx = await br.new_context(viewport=dict(width=1280, height=900)); pg = await ctx.new_page()
        await pg.goto("file://" + f + "#StatsWalesPopulation"); await pg.wait_for_timeout(250); await pg.click("#view-schematic"); await pg.wait_for_timeout(100)
        ok("deep link opens the named dataset", await pg.get_attribute("#tab-StatsWalesPopulation", "aria-selected") == "true")
        await pg.goto("file://" + f + "#nonsense"); await pg.reload(); await pg.wait_for_timeout(250)
        ok("unknown hash falls back to All datasets", await pg.get_attribute("#tab-all", "aria-selected") == "true")
        await ctx.close()
        # widths: the page body must never scroll sideways
        for w in (360, 400, 600, 768, 1024, 1280, 1920):
            ctx = await br.new_context(viewport=dict(width=w, height=900), has_touch=w < 800); pg = await ctx.new_page()
            await pg.goto("file://" + f); await pg.wait_for_timeout(200); await pg.click("#view-schematic"); await pg.wait_for_timeout(100)
            for tab in ("all", "VEH0132", "ONSOpenGeography"):
                await pg.click(f"#tab-{tab}"); await pg.wait_for_timeout(50)
                d = await pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                ok(f"width {w}, {tab}: no sideways page scroll", d[0] <= d[1], str(d))
            if w < 800:
                await pg.evaluate("document.querySelector('#kg [data-id=\"g:EnglishLAD\"]').scrollIntoView({block:'center',inline:'center'})"); await pg.wait_for_timeout(120)
                box = await pg.evaluate("(()=>{const r=document.querySelector('#kg [data-id=\"g:EnglishLAD\"]').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()")
                await pg.touchscreen.tap(box[0], box[1]); await pg.wait_for_timeout(120)
                ok(f"width {w}: tap shows a tooltip", await pg.is_visible("#tip"))
                tb = await pg.evaluate("(()=>{const r=document.querySelector('#tip').getBoundingClientRect();return [r.left,r.right,innerWidth]})()")
                ok(f"width {w}: tooltip fits the screen", tb[0] >= 0 and tb[1] <= tb[2], str(tb))
                await pg.touchscreen.tap(20, 20); await pg.wait_for_timeout(120)
                ok(f"width {w}: tap elsewhere hides it", not await pg.is_visible("#tip"))
            await ctx.close()
        await br.close()
    bad = [r for r in res if not r[1]]
    print(f"{len(res)} checks, {len(bad)} failures")
    for n, c, i in bad: print("  FAIL", n, i)
asyncio.run(main())
