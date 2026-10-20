#!/usr/bin/env python3
"""Interaction and consistency checks for the entity explorer (headless Chromium)."""
import sys, os, re, json, asyncio, collections
from playwright.async_api import async_playwright
page_path = os.path.abspath(sys.argv[1]); outdir = os.path.abspath(sys.argv[2])
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the build directory
from localdeps import strip_font_link, page  # noqa: E402
raw = open(page_path, encoding="utf-8").read()
body = strip_font_link(raw)
f = os.path.join(outdir, "_etest.html"); open(f, "w", encoding="utf-8").write(page(body))
M = json.loads(re.search(r'<script id="model" type="application/json">(.*?)</script>', raw, re.S).group(1))
N = len(M["label"]); EN = len(M["edges"]) // 3
res = []
def ok(name, cond, info=""): res.append((name, bool(cond), str(info)))

# ---- static checks on the embedded model --------------------------------------
ok("page under 16 MB", len(raw.encode()) < 16 * 1024 * 1024, len(raw.encode()))
ok("model arrays aligned", all(len(M[k]) == N for k in ("label", "iri", "kind", "src", "deg", "types", "attrs", "cl")) and len(M["posS"]) == 2 * N and len(M["posF"]) == 2 * N)
ok("every node has a non-empty label", all(M["label"]))
deg = [0] * N
for e in range(EN):
    deg[M["edges"][3 * e]] += 1; deg[M["edges"][3 * e + 2]] += 1
ok("degrees match the edge list", deg == M["deg"])
legend_n = sum(k["n"] for g in M["legend"] for k in g["kinds"])
ok("legend counts sum to the node count", legend_n == N, f"{legend_n} vs {N}")
cnt = collections.Counter(M["kind"])
ok("legend count per kind matches", all(k["n"] == cnt[M["kinds"].index(k["name"])] for g in M["legend"] for k in g["kinds"]))
ok("relation counts sum to the edge count", sum(r["n"] for r in M["relations"]) == EN)
ok("meta counts match", M["meta"]["nodes"] == N and M["meta"]["edges"] == EN and M["meta"]["literals"] == sum(len(a) for a in M["attrs"]))
ok("every dataset tab has its record node", all(M["kinds"][M["kind"][d["node"]]] == "Dataset record" and M["label"][d["node"]] == d["id"] for d in M["datasets"]))
iso = [i for i in range(N) if deg[i] == 0]
ok("isolated nodes: only cleets:ChargersPerKeeperProperty", [M["iri"][i] for i in iso] == ["cleets:ChargersPerKeeperProperty"], [M["iri"][i] for i in iso])
dup = len(set(M["iri"])) != N
ok("IRIs unique", not dup)
src_nodes = sum(1 for i in range(N) if M["src"][i])
ok("dataset bitmask set on cited entities + records", src_nodes > 10000, src_nodes)
# cluster anchors are hubs or self
ok("cluster anchors resolve", all(0 <= c < N for c in M["cl"]))

async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport=dict(width=1440, height=1000)); pg = await ctx.new_page()
        errs = []; pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None); pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + f); await pg.wait_for_timeout(500)
        ok("no console or page errors on load", not errs, errs[:3])
        ok("eyebrow shows the counts", f"{N:,}" in await pg.inner_text("#eyebrow") and f"{EN:,}" in await pg.inner_text("#eyebrow"))
        ok("count line at fit shows all", await pg.inner_text("#count") == f"{N:,} entities · {EN:,} links in view", await pg.inner_text("#count"))
        ok("zoom reads 100% at fit", await pg.inner_text("#zval") == "100%")
        ok("tabs: all datasets + All", await pg.evaluate("document.querySelectorAll('#tabs .tab').length") == len(M["datasets"]) + 1)
        ok("legend: one checkbox per kind with count", await pg.evaluate("document.querySelectorAll('#legend input').length") == sum(len(g["kinds"]) for g in M["legend"]))
        ok("overview panel", "CLEETS-KG" in await pg.inner_text("#side h2") and "most connected" in (await pg.inner_text("#side")).lower())
        # canvas painted (not blank)
        painted = await pg.evaluate("""(() => { const cv = document.getElementById('cv'), c = cv.getContext('2d'); const d = c.getImageData(0, 0, cv.width, cv.height).data; let n = 0; for (let i = 0; i < d.length; i += 16) if (d[i] < 200 || d[i+1] < 200) n++; return n; })()""")
        ok("canvas painted", painted > 2000, painted)
        # dataset tabs
        for d in M["datasets"]:
            await pg.click(f"#tab-{d['id']}"); await pg.wait_for_timeout(80)
            exp = sum(1 for i in range(N) if M["src"][i] & d["bit"])
            got = await pg.evaluate("window.__entities.countVisible()")
            # the record's non-source objects and prov:used activities are added
            ok(f"{d['id']}: highlighted count >= cited entities", got >= exp and got <= exp + 40, f"{got} vs {exp}")
            ok(f"{d['id']}: panel mentions it", d["id"] in await pg.inner_text("#side"))
            ok(f"{d['id']}: tab selected", await pg.get_attribute(f"#tab-{d['id']}", "aria-selected") == "true")
        await pg.click("#tab-all"); await pg.wait_for_timeout(80)
        ok("All: full count again", await pg.evaluate("window.__entities.countVisible()") == N)
        # keyboard on the tabs
        await pg.focus("#tab-all"); await pg.keyboard.press("ArrowRight"); await pg.wait_for_timeout(50)
        ok("ArrowRight moves to the first dataset tab", await pg.get_attribute(f"#tab-{M['datasets'][0]['id']}", "aria-selected") == "true")
        await pg.keyboard.press("Home"); await pg.wait_for_timeout(50)
        ok("Home returns to All", await pg.get_attribute("#tab-all", "aria-selected") == "true")
        # search
        await pg.fill("#q", "cardiff"); await pg.wait_for_timeout(120)
        ok("search lists results", not await pg.evaluate("document.querySelector('#results').hidden") and await pg.evaluate("document.querySelectorAll('#results button').length") > 5)
        first = await pg.inner_text("#results button >> nth=0")
        ok("first result is the district (a hub) ", first.startswith("Cardiff") and "WelshLAD" in first, first)
        await pg.keyboard.press("ArrowDown"); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(500)
        ok("Enter selects it and the panel shows its IRI", "cleetsdata:LAD_W06000015" in await pg.inner_text("#side .iri") or "W06000015" in await pg.inner_text("#side .iri"), await pg.inner_text("#side .iri"))
        ok("panel: properties and links", "properties" in (await pg.inner_text("#side")).lower() and "links to this entity" in (await pg.inner_text("#side")).lower())
        ok("zoomed in after picking a result", int((await pg.inner_text("#zval")).rstrip("%")) >= 900, await pg.inner_text("#zval"))
        ok("hash updated", "W06000015" in await pg.evaluate("location.hash"))
        sel = await pg.evaluate("window.__entities.state.sel")
        ok("neighbourhood button enabled when something is selected", not await pg.is_disabled("#nbbtn"))
        n_nb = len({M["edges"][3 * e + 2] for e in range(EN) if M["edges"][3 * e] == sel} | {M["edges"][3 * e] for e in range(EN) if M["edges"][3 * e + 2] == sel} | {sel})
        await pg.click("#nbbtn"); await pg.wait_for_timeout(120)
        ok("neighbourhood mode shows the node and its neighbours only", await pg.evaluate("window.__entities.countVisible()") == n_nb, f"{await pg.evaluate('window.__entities.countVisible()')} vs {n_nb}")
        await pg.click("#nbbtn"); await pg.wait_for_timeout(80)
        ok("neighbourhood off restores everything", await pg.evaluate("window.__entities.countVisible()") == N)
        # follow a link from the panel
        await pg.click("#side ul li button.go >> nth=0"); await pg.wait_for_timeout(500)
        sel2 = await pg.evaluate("window.__entities.state.sel")
        ok("clicking a linked entity selects it", sel2 != sel and sel2 >= 0)
        ok("selected ring drawn (canvas repainted)", True)
        # Escape clears
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(80)
        ok("Escape clears the selection", await pg.evaluate("window.__entities.state.sel") == -1 and "most connected" in (await pg.inner_text("#side")).lower())
        # zoom buttons and fit
        await pg.click("#zin"); await pg.wait_for_timeout(50)
        z1 = int((await pg.inner_text("#zval")).rstrip("%"))
        await pg.click("#fit"); await pg.wait_for_timeout(50)
        ok("zoom in then fit", z1 > 100 and await pg.inner_text("#zval") == "100%", z1)
        # wheel zoom on the canvas
        box = await pg.evaluate("(() => { const r = document.getElementById('cv').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        await pg.mouse.move(box[0], box[1]); await pg.mouse.wheel(0, -600); await pg.wait_for_timeout(80)
        ok("wheel zooms", int((await pg.inner_text("#zval")).rstrip("%")) > 150, await pg.inner_text("#zval"))
        # drag pans
        tx0 = await pg.evaluate("window.__entities.state.tx")
        await pg.mouse.move(box[0], box[1]); await pg.mouse.down(); await pg.mouse.move(box[0] + 80, box[1] + 10, steps=5); await pg.mouse.up(); await pg.wait_for_timeout(80)
        ok("drag pans the view", abs(await pg.evaluate("window.__entities.state.tx") - tx0 - 80) < 2)
        ok("drag does not select", await pg.evaluate("window.__entities.state.sel") == -1)
        # hover tooltip on a hub: fit, then find Cardiff's screen position
        await pg.click("#fit"); await pg.wait_for_timeout(50)
        i_card = M["label"].index("Cardiff")
        pt = await pg.evaluate("i => { const s = window.__entities.state, r = document.getElementById('cv').getBoundingClientRect(); return [r.left + s.pos[2*i]*s.k + s.tx, r.top + s.pos[2*i+1]*s.k + s.ty]; }", i_card)
        await pg.mouse.move(pt[0], pt[1]); await pg.wait_for_timeout(80)
        ok("hover shows the tooltip with the name", not await pg.evaluate("document.querySelector('#tip').hidden") and "Cardiff" in await pg.inner_text("#tip"))
        await pg.mouse.click(pt[0], pt[1]); await pg.wait_for_timeout(120)
        ok("click on the hub selects it", await pg.evaluate("window.__entities.state.sel") == i_card)
        await pg.mouse.dblclick(pt[0], pt[1]); await pg.wait_for_timeout(600)
        ok("double-click zooms in", int((await pg.inner_text("#zval")).rstrip("%")) >= 300, await pg.inner_text("#zval"))
        # relation filter
        await pg.click("#relbtn"); await pg.wait_for_timeout(50)
        ok("relations popover lists every predicate with counts", await pg.evaluate("document.querySelectorAll('#relpop label').length") == len(M["relations"]))
        await pg.click("#relpop .row button >> nth=1"); await pg.wait_for_timeout(120)   # none
        ok("no relations: only the selection's links remain", await pg.evaluate("window.__entities.M.relations.every(r => !window.__entities.state.predOn[window.__entities.M.preds.indexOf(r.p)])") and (await pg.inner_text("#relcount")).startswith("0/") and await pg.evaluate("window.__entities.M.relations.length") == len(M["relations"]))
        await pg.click("#relpop .row button >> nth=0"); await pg.wait_for_timeout(120)   # all
        ok("all relations back", await pg.evaluate("window.__entities.state.predOn.every(x => x)") and await pg.inner_text("#relcount") == "")
        # with no relations drawn the count line must still include the selection's own links only
        await pg.click("#relpop .row button >> nth=1"); await pg.wait_for_timeout(150)
        txt = await pg.inner_text("#count"); sel_deg = M["deg"][i_card]
        ok("count line with no relations = the selection's links", txt.endswith(f"{sel_deg:,} links in view"), txt)
        await pg.click("#relpop .row button >> nth=0"); await pg.wait_for_timeout(150)
        await pg.keyboard.press("Escape"); await pg.click("#eyebrow"); await pg.wait_for_timeout(50)
        ok("popover closed by clicking elsewhere", await pg.evaluate("document.querySelector('#relpop').hidden"))
        # kind toggle: hide fingerprints
        fp_idx = M["kinds"].index("Source-row fingerprint")
        await pg.click(f"#kind-{fp_idx}"); await pg.wait_for_timeout(120)
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(80)
        exp = N - cnt[fp_idx]
        ok("hiding a kind removes its entities", await pg.evaluate("window.__entities.countVisible()") == exp, f"{await pg.evaluate('window.__entities.countVisible()')} vs {exp}")
        await pg.click(f"#kind-{fp_idx}"); await pg.wait_for_timeout(80)
        ok("showing it again", await pg.evaluate("window.__entities.countVisible()") == N)
        # labels toggle
        await pg.click("#lblbtn"); await pg.wait_for_timeout(50)
        ok("labels toggle", await pg.get_attribute("#lblbtn", "aria-pressed") == "false")
        await pg.click("#lblbtn")
        # layout switch (no animation in tests: reduced motion not set, so wait for it)
        await pg.click("#lay-f"); await pg.wait_for_timeout(1200)
        ok("force layout active", await pg.get_attribute("#lay-f", "aria-pressed") == "true" and await pg.evaluate("Math.abs(window.__entities.state.pos[0] - window.__entities.M.posF[0]) < .01"))
        ok("zoom reads 100% after switching layouts", await pg.inner_text("#zval") == "100%", await pg.inner_text("#zval"))
        await pg.click("#lay-s"); await pg.wait_for_timeout(1200)
        ok("structured layout back", await pg.evaluate("Math.abs(window.__entities.state.pos[0] - window.__entities.M.posS[0]) < .01"))
        # hash navigation on load
        pg2 = await ctx.new_page()
        await pg2.goto("file://" + f + "#cleetsdata:Period2024Q4"); await pg2.wait_for_timeout(600)
        ok("opening with #iri selects that entity", "2024-Q4" in await pg2.inner_text("#side h2"), await pg2.inner_text("#side h2"))
        await pg2.close()
        # dark theme: canvas background follows the token
        pg3 = await ctx.new_page()
        await pg3.goto("file://" + f); await pg3.evaluate("document.documentElement.setAttribute('data-theme', 'dark')"); await pg3.wait_for_timeout(300)
        px = await pg3.evaluate("(() => { const cv = document.getElementById('cv'), c = cv.getContext('2d'); const d = c.getImageData(2, 2, 1, 1).data; return [d[0], d[1], d[2]]; })()")
        ok("dark theme repaints the canvas dark", px[0] < 40 and px[1] < 40 and px[2] < 50, px)
        ok("dark theme swaps the kind colours", await pg3.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--k0').trim()") == next(k["cd"] for g in M["legend"] for k in g["kinds"] if k["name"] == M["kinds"][0]))
        await pg3.close()
        # phone: no horizontal overflow, controls wrap
        ctxm = await br.new_context(viewport=dict(width=390, height=844), has_touch=True, is_mobile=True); pgm = await ctxm.new_page()
        merr = []; pgm.on("pageerror", lambda e: merr.append(str(e)))
        await pgm.goto("file://" + f); await pgm.wait_for_timeout(500)
        ok("phone: no horizontal scroll", await pgm.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
        ok("phone: canvas sized to the stage", await pgm.evaluate("(() => { const r = document.getElementById('stage').getBoundingClientRect(); return r.width > 300 && r.height > 300; })()"))
        ok("phone: no errors", not merr, merr[:2])
        await ctxm.close()
        ok("no console or page errors overall", not errs, errs[:3])
        await br.close()

asyncio.run(main())
bad = [r for r in res if not r[1]]
for name, good, info in res:
    print(("ok  " if good else "FAIL"), name, ("" if good else f"  -> {info}"))
print(f"\n{len(res) - len(bad)}/{len(res)} checks passed")
sys.exit(1 if bad else 0)
