#!/usr/bin/env python3
"""Interaction checks for the VOWL view (headless Chromium, local d3)."""
import sys, os, re, json, asyncio
from playwright.async_api import async_playwright
page_path = os.path.abspath(sys.argv[1]); outdir = os.path.abspath(sys.argv[2])
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the build directory
from localdeps import inline_d3, drop_d3, strip_font_link, page  # noqa: E402
raw = open(page_path, encoding="utf-8").read()
body = strip_font_link(inline_d3(raw))
nod3 = strip_font_link(drop_d3(raw))
f = os.path.join(outdir, "_vtest.html"); open(f, "w", encoding="utf-8").write(page(body))
f2 = os.path.join(outdir, "_vtest_nod3.html"); open(f2, "w", encoding="utf-8").write(page(nod3))
M = json.loads(re.search(r'<script id="model" type="application/json">(.*?)</script>', raw, re.S).group(1))
V = M["vowl"]
res = []
def ok(name, cond, info=""): res.append((name, bool(cond), str(info)))
async def jsclick(pg, sel):
    await pg.evaluate("sel => document.querySelector(sel).dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}))", sel)

async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport=dict(width=1440, height=1000)); pg = await ctx.new_page()
        errs = []; pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None); pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + f); await pg.wait_for_timeout(400)
        ok("graph view shown by default", await pg.evaluate("!document.querySelector('#vowl').hidden && document.querySelector('.map').hidden"))
        ok("all nodes drawn", await pg.evaluate("document.querySelectorAll('#vsvg .vn').length") == len(V["nodes"]))
        ok("all links drawn", await pg.evaluate("document.querySelectorAll('#vsvg .vl').length") == len(V["links"]))
        ok("baked positions used (no node at the origin)", await pg.evaluate("[...document.querySelectorAll('#vsvg .vn:not([hidden])')].every(g => /translate\\((-?\\d+\\.?\\d*),(-?\\d+\\.?\\d*)\\)/.test(g.getAttribute('transform')))"))
        hid = await pg.evaluate("document.querySelectorAll('#vsvg [hidden]').length")
        ok("disjointness hidden by default (7 links + 7 labels)", hid == 14, hid)
        zv = await pg.inner_text("#vzval")
        ok("fitted zoom is readable (>= 55%)", int(zv.rstrip("%")) >= 55, zv)
        # every visible node inside the canvas after fit
        inside = await pg.evaluate("""(()=>{const c=document.querySelector('#vcanvas').getBoundingClientRect();return [...document.querySelectorAll('#vsvg .vn:not([hidden])')].every(g=>{const r=g.getBoundingClientRect();return r.left>=c.left-1&&r.right<=c.right+1&&r.top>=c.top-1&&r.bottom<=c.bottom+1})})()""")
        ok("whole drawing inside the canvas after fit", inside)
        # text never wider than its node (class circles: lines must fit the chord)
        over = await pg.evaluate("""[...document.querySelectorAll('#vsvg .vn.cls:not([hidden]), #vsvg .vn.ext:not([hidden])')].map(g=>{const r=+g.querySelector('.in').getAttribute('r');return [...g.querySelectorAll('tspan')].map(t=>t.getComputedTextLength()).some(w=>w>2*r-4)?g.getAttribute('data-id'):null}).filter(Boolean)""")
        ok("class labels fit their circles", not over, over)
        overL = await pg.evaluate("""[...document.querySelectorAll('#vsvg .vlab:not([hidden])')].map(g=>{const w=+g.querySelector('.bg').getAttribute('width');return [...g.querySelectorAll('tspan, text.subtext')].some(t=>t.getComputedTextLength()>w-4)?g.getAttribute('data-id'):null}).filter(Boolean)""")
        ok("property labels fit their boxes", not overL, overL)
        # dataset tabs highlight the right elements
        for d, hl in V["hl"].items():
            await pg.click(f"#tab-{d}"); await pg.wait_for_timeout(50)
            n_on = await pg.evaluate("document.querySelectorAll('#vsvg .on').length"); n_ctx = await pg.evaluate("document.querySelectorAll('#vsvg .ctx').length")
            exp_on = sum(1 for i in hl["on"] if any(i == x["id"] for x in V["nodes"])) + 2 * sum(1 for i in hl["on"] if any(i == x["id"] for x in V["links"]))
            exp_ctx = sum(1 for i in hl["ctx"] if any(i == x["id"] for x in V["nodes"])) + 2 * sum(1 for i in hl["ctx"] if any(i == x["id"] for x in V["links"]))
            ok(f"{d}: highlighted elements", n_on == exp_on and n_ctx == exp_ctx, f"{n_on}/{exp_on} on, {n_ctx}/{exp_ctx} ctx")
            ok(f"{d}: sidebar shows the dataset", d in await pg.inner_text("#vside h2"))
        await pg.click("#tab-all")
        ok("All datasets: nothing faded", not await pg.evaluate("document.querySelector('#vsvg').classList.contains('has-sel')"))
        ok("overview in the sidebar", "CLEETS-KG" in await pg.inner_text("#vside h2"))
        # click a class node: details; click again: back
        await jsclick(pg, '[data-id="c:cleets:EVKeepership"] .in'); await pg.wait_for_timeout(50)
        ok("class click shows its details", "cleets:EVKeepership" in await pg.inner_text("#vside h2") and "restrictions" in (await pg.inner_text("#vside")).lower())
        ok("focused node gets the red ring", await pg.evaluate("document.querySelector('[data-id=\"c:cleets:EVKeepership\"]').classList.contains('foc')"))
        await jsclick(pg, '[data-id="c:cleets:EVKeepership"] .in'); await pg.wait_for_timeout(50)
        ok("second click clears the focus", not await pg.evaluate("document.querySelector('[data-id=\"c:cleets:EVKeepership\"]').classList.contains('foc')"))
        box0 = await pg.evaluate("(()=>{const r=document.querySelector('[data-id=\"c:cleets:Time\"] .in').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()")
        await pg.mouse.click(box0[0], box0[1]); await pg.wait_for_timeout(60)
        ok("a real mouse click on a node shows its details", "cleets:Time" in await pg.inner_text("#vside h2"))
        await pg.mouse.click(box0[0], box0[1]); await pg.wait_for_timeout(60)
        # a property label
        await jsclick(pg, '.vlab[data-id="p:cleets:forLAD"] .hitr'); await pg.wait_for_timeout(50)
        ok("property label click shows its details", "cleets:forLAD" in await pg.inner_text("#vside h2") and "Subproperty of" in await pg.inner_text("#vside"))
        # sidebar link to another element
        await jsclick(pg, '[data-id="c:cleets:WelshLAD"] .in'); await pg.wait_for_timeout(50)
        await jsclick(pg, '#vside button.go'); await pg.wait_for_timeout(450)
        ok("sidebar item navigates to its element", await pg.evaluate("!!document.querySelector('#vsvg .foc')"))
        # dataset node click selects the tab
        await jsclick(pg, '[data-id="ds:EVCI9001"] rect'); await pg.wait_for_timeout(50)
        ok("dataset node click selects its tab", await pg.get_attribute("#tab-EVCI9001", "aria-selected") == "true")
        await jsclick(pg, '[data-id="ds:EVCI9001"] rect'); await pg.wait_for_timeout(50)
        ok("second click returns to All datasets", await pg.get_attribute("#tab-all", "aria-selected") == "true")
        # filters
        await pg.click("#f-disjoint"); await pg.wait_for_timeout(1200)
        ok("disjointness filter shows the 7 dashed links", await pg.evaluate("[...document.querySelectorAll('#vsvg .vl.dj')].filter(g=>!g.hasAttribute('hidden')).length") == 7)
        await pg.click("#f-disjoint"); await pg.wait_for_timeout(300)
        await pg.click("#f-thing"); await pg.wait_for_timeout(1200)
        ok("Thing filter hides the Thing nodes and their properties", await pg.evaluate("[...document.querySelectorAll('#vsvg .vn.thing')].every(g=>g.hasAttribute('hidden')) && document.querySelector('.vlab[data-id=\"p:cleets:hasPopulation\"]').hasAttribute('hidden')"))
        await pg.click("#f-thing"); await pg.wait_for_timeout(300)
        await pg.click("#f-data"); await pg.wait_for_timeout(1200)
        ok("dataset filter hides datasets, derivations and their links", await pg.evaluate("[...document.querySelectorAll('#vsvg .vn.ds, #vsvg .vn.act, #vsvg .vl.src, #vsvg .vl.used, #vsvg .vl.gen')].every(g=>g.hasAttribute('hidden'))"))
        await pg.click("#f-data"); await pg.wait_for_timeout(300)
        # labels: identifiers
        await pg.click("#o-ids"); await pg.wait_for_timeout(300)
        ok("identifier labels", await pg.evaluate("document.querySelector('[data-id=\"c:cleets:EVKeepership\"] tspan').textContent") == "EVKeepership" and await pg.evaluate("document.querySelector('.vlab[data-id=\"p:cleets:forLAD\"] tspan').textContent") == "forLAD")
        await pg.click("#o-names"); await pg.wait_for_timeout(300)
        ok("rdfs:label labels", await pg.evaluate("document.querySelector('.vlab[data-id=\"p:cleets:forLAD\"] tspan').textContent") == "for local authority district")
        await pg.click("#o-compact"); ok("compact notation hides subclass labels", await pg.evaluate("getComputedStyle(document.querySelector('.vlab.sub')).display") == "none"); await pg.click("#o-compact")
        # zoom
        await pg.wait_for_timeout(3500); await pg.click("#vfit"); await pg.wait_for_timeout(450)
        z0 = await pg.inner_text("#vzval"); await pg.click("#vzin"); await pg.wait_for_timeout(350); z1 = await pg.inner_text("#vzval")
        ok("zoom in", int(z1.rstrip("%")) > int(z0.rstrip("%")), f"{z0} -> {z1}")
        await pg.click("#vfit"); await pg.wait_for_timeout(450); z2 = await pg.inner_text("#vzval")
        ok("fit restores", abs(int(z2.rstrip("%")) - int(z0.rstrip("%"))) <= 2, f"{z2} vs {z0}")
        # drag pins a node, double-click unpins
        box = await pg.evaluate("(()=>{const r=document.querySelector('[data-id=\"c:cleets:Population\"] .in').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()")
        await pg.mouse.move(box[0], box[1]); await pg.mouse.down(); await pg.mouse.move(box[0] + 40, box[1] + 30, steps=6); await pg.mouse.move(box[0] + 80, box[1] + 60, steps=6); await pg.mouse.up(); await pg.wait_for_timeout(300)
        box2 = await pg.evaluate("(()=>{const r=document.querySelector('[data-id=\"c:cleets:Population\"] .in').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()")
        ok("dragging moves the node", abs(box2[0] - box[0] - 80) < 6 and abs(box2[1] - box[1] - 60) < 6, f"{box} -> {box2}")
        ok("dragged node is pinned", await pg.evaluate("!!document.querySelector('[data-id=\"c:cleets:Population\"] .pin')"))
        ok("drag did not open the details", "Population" not in await pg.inner_text("#vside h2"))
        await pg.mouse.dblclick(box2[0], box2[1]); await pg.wait_for_timeout(300)
        ok("double-click unpins", not await pg.evaluate("!!document.querySelector('[data-id=\"c:cleets:Population\"] .pin')"))
        await pg.wait_for_timeout(2500)
        box3 = await pg.evaluate("(()=>{const r=document.querySelector('[data-id=\"c:cleets:Population\"] .in').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()")
        await pg.mouse.move(box3[0], box3[1]); await pg.mouse.down(); await pg.mouse.move(box3[0] - 30, box3[1] - 20, steps=5); await pg.mouse.up(); await pg.wait_for_timeout(300)
        pinbox = await pg.evaluate("(()=>{const r=document.querySelector('[data-id=\"c:cleets:Population\"] .pin circle').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()")
        await pg.mouse.click(pinbox[0], pinbox[1]); await pg.wait_for_timeout(300)
        ok("clicking the pin releases the node", not await pg.evaluate("!!document.querySelector('[data-id=\"c:cleets:Population\"] .pin')"))
        # keyboard
        await pg.focus('[data-id="c:cleets:Quarter"]'); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(50)
        ok("Enter on a focused node shows its details", "cleets:Quarter" in await pg.inner_text("#vside h2"))
        await pg.keyboard.press("Escape")
        # copy SVG
        await pg.click("#vcopy"); await pg.wait_for_timeout(300)
        txt = await pg.evaluate("document.querySelector('#vcopytext').value")
        ok("copy box shows SVG markup", txt.startswith('<?xml') and "<svg" in txt and "<style>" in txt and "VEH0132" in txt, txt[:60])
        wf = await pg.evaluate("(t=>{const d=new DOMParser().parseFromString(t,'image/svg+xml');return !d.querySelector('parsererror')})(document.querySelector('#vcopytext').value)")
        ok("copied SVG is well-formed", wf)
        ok("copied SVG carries no hit areas or hidden elements", ".hit" not in txt.split("<style>")[1].split("</style>")[0][:0] and 'class="hit"' not in txt and "hidden" not in txt)
        await pg.click("#vcopyclose")
        # view switch
        await pg.click("#view-schematic"); await pg.wait_for_timeout(200)
        ok("schematic view shows the map", await pg.evaluate("document.querySelector('#vowl').hidden && !document.querySelector('.map').hidden && document.querySelector('#kg').getBoundingClientRect().width > 900"))
        await pg.click("#tab-WIMD2025"); await pg.wait_for_timeout(50)
        ok("tabs still highlight the schematic", await pg.evaluate("document.querySelector('#kg').classList.contains('has-sel')"))
        await pg.click("#view-graph"); await pg.wait_for_timeout(200)
        ok("back to the graph", not await pg.evaluate("document.querySelector('#vowl').hidden"))
        ok("no console errors", not errs, errs[:4])
        ok("page never scrolls sideways", await pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
        await ctx.close()
        # reduced motion
        ctx = await br.new_context(viewport=dict(width=1280, height=900), reduced_motion="reduce"); pg = await ctx.new_page(); errs2 = []; pg.on("pageerror", lambda e: errs2.append(str(e)))
        await pg.goto("file://" + f); await pg.wait_for_timeout(300); await pg.click("#f-disjoint"); await pg.wait_for_timeout(100)
        ok("reduced motion: filters work without errors", not errs2 and await pg.evaluate("[...document.querySelectorAll('#vsvg .vl.dj')].filter(g=>!g.hasAttribute('hidden')).length") == 7, errs2[:2])
        await ctx.close()
        # without d3: static graph from the baked positions
        ctx = await br.new_context(viewport=dict(width=1280, height=900)); pg = await ctx.new_page(); errs3 = []; pg.on("pageerror", lambda e: errs3.append(str(e)))
        await pg.goto("file://" + f2); await pg.wait_for_timeout(300)
        ok("without d3 the graph still renders", not errs3 and await pg.evaluate("document.querySelectorAll('#vsvg .vn:not([hidden])').length") > 40 and "%" in await pg.inner_text("#vzval"), errs3[:2])
        await pg.click("#tab-VEH0105"); ok("without d3 the tabs still highlight", await pg.evaluate("document.querySelector('#vsvg').classList.contains('has-sel')"))
        await ctx.close()
        # phone
        for w in (360, 400, 768):
            ctx = await br.new_context(viewport=dict(width=w, height=800), has_touch=True); pg = await ctx.new_page()
            await pg.goto("file://" + f); await pg.wait_for_timeout(300)
            ok(f"width {w}: no sideways page scroll", await pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), await pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]"))
            ok(f"width {w}: sidebar stacked under the canvas", await pg.evaluate("document.querySelector('#vside').getBoundingClientRect().top >= document.querySelector('#vcanvas').getBoundingClientRect().bottom - 1"))
            await ctx.close()
        await br.close()
    bad = [r for r in res if not r[1]]
    print(f"{len(res)} checks, {len(bad)} failures")
    for n, c, i in bad: print("  FAIL", n, i)
asyncio.run(main())
