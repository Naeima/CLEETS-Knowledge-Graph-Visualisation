#!/usr/bin/env python3
"""Build the CLEETS-KG entity explorer: every individual in the Turtle as a node.

usage: build_entities.py <index.ttl> <template.html> <out.html> [--json model.json] [--force-layout cache.json]
"""
import sys, os, json, math, re, argparse, datetime, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kgmodel import KG, C, DCT, PROV, RDF, RDFS, TIME, URIRef, BNode  # noqa: E402
from entity_graph import EntityGraph  # noqa: E402
import build_kg_map as bk  # noqa: E402  (dataset order, topics and palette)

SERIES_ORDER = ["EVKeepership", "EVsPerThousandResidents", "PrivateVehicleStock", "EVChargerCount", "ChargersPer100kResidents",
                "KeepersPerCharger", "IncomeDeprivation", "Population", "PopulationDensity"]

# display kinds -> colour family (hue from the validated palette) and shade (0 base, 1 lighter, 2 darker)
KIND_STYLE = {
    "EVKeepership": ("blue", 0), "EVsPerThousandResidents": ("blue", 1), "PrivateVehicleStock": ("blue", 2),
    "EVChargerCount": ("magenta", 0), "ChargersPer100kResidents": ("magenta", 1), "KeepersPerCharger": ("magenta", 2),
    "Population": ("aqua", 0), "PopulationDensity": ("aqua", 1),
    "IncomeDeprivation": ("violet", 0),
    "WelshLAD": ("green", 0), "EnglishLAD": ("green", 1),
    "Quarter": ("yellow", 0), "Time": ("yellow", 2), "Instant": ("yellow", 1),
    "Dataset record": ("red", 0), "Knowledge graph": ("red", 2), "Dataset series": ("red", 1), "Distribution": ("red", 1), "Period of time": ("red", 1),
    "Derivation": ("orange", 0), "ObservableProperty": ("orange", 2),
    "Organisation": ("ink", 0), "Person": ("ink", 1), "Postal address": ("ink", 2),
    "Source-row fingerprint": ("grey", 0), "External resource": ("grey", 1), "Other": ("grey", 2),
}
KIND_GROUP = {  # legend sections
    "Observations": ["EVKeepership", "EVsPerThousandResidents", "PrivateVehicleStock", "EVChargerCount", "ChargersPer100kResidents", "KeepersPerCharger", "IncomeDeprivation"],
    "Population": ["Population", "PopulationDensity"],
    "Districts and time": ["WelshLAD", "EnglishLAD", "Quarter", "Time", "Instant"],
    "Datasets and provenance": ["Dataset record", "Knowledge graph", "Dataset series", "Distribution", "Period of time", "Derivation", "ObservableProperty", "Source-row fingerprint"],
    "Agents and other": ["Organisation", "Person", "Postal address", "External resource", "Other"],
}
HUB_KINDS = {"WelshLAD", "Quarter", "Time", "Dataset record", "Knowledge graph", "Derivation", "ObservableProperty", "Organisation"}


def hexmix(a, b, t):
    A = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    B = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(A, B))


def colour_for(kind, hexes, dark=False):
    """Light surface: shade 1 is a tint, shade 2 a shade. Dark surface: both stay bright enough to read on #10151b."""
    fam, shade = KIND_STYLE.get(kind, ("grey", 2))
    if dark:
        base = {"ink": "#b9c2cc", "grey": "#7b8691"}.get(fam) or hexes[fam]
        if shade == 1:
            return hexmix(base, "#ffffff", .40)
        if shade == 2:
            return hexmix(base, "#000000", .22)
        return base
    base = {"ink": "#4a5563", "grey": "#9aa4ae"}.get(fam) or hexes[fam]
    if shade == 1:
        return hexmix(base, "#ffffff", .42)
    if shade == 2:
        return hexmix(base, "#000000", .32)
    return base


# ----------------------------------------------------------------------------
def structured_layout(eg, kg):
    """Deterministic 'mandala' arrangement: the graph's hubs on rings, their satellites beside them."""
    g = eg.g
    pos = {}
    TAU = 2 * math.pi

    def polar(r, a):
        return (r * math.cos(a), r * math.sin(a))

    def phyllo(center, k, c=8.4):
        r = c * math.sqrt(k + 1)
        a = k * 2.399963229728653
        return (center[0] + r * math.cos(a), center[1] + r * math.sin(a))

    anchor = {}     # node -> the hub whose cluster it belongs to (for edge bundling)
    kinds = {n: eg.kind_of(n) for n in eg.order}
    by_kind = collections.defaultdict(list)
    for n in eg.order:
        by_kind[kinds[n]].append(n)
    ds_nodes = {str(n).split("/")[-1]: n for n in by_kind["Dataset record"]}
    ds_angle = {}
    # knowledge graph node at the centre, dataset records on a ring in tab order
    for n in by_kind["Knowledge graph"]:
        pos[n] = (0.0, 0.0)
    for i, d in enumerate(bk.TAB_ORDER):
        a = -TAU / 4 + TAU * i / len(bk.TAB_ORDER)
        ds_angle[d] = a
        pos[ds_nodes[d]] = polar(760, a)
    # dataset satellites: distribution, series, period, landing page, access page, licence
    for d, n in ds_nodes.items():
        sats = [o for p, o in g.predicate_objects(n) if o in eg.index and p != DCT.source and o not in pos]
        sats = sorted(set(sats), key=str)
        for j, o in enumerate(sats):
            a = ds_angle[d] + (j - (len(sats) - 1) / 2) * 0.11
            pos[o] = polar(760 + 95 + (j % 2) * 36, a)
            anchor[o] = n
    # derivations between their inputs; the citation activity next to the graph node
    for n in by_kind["Derivation"]:
        used = [str(o).split("/")[-1] for o in g.objects(n, PROV.used)]
        if used:
            angs = [ds_angle[u] for u in used if u in ds_angle]
            ax = sum(math.cos(a) for a in angs) / len(angs); ay = sum(math.sin(a) for a in angs) / len(angs)
            pos[n] = polar(450, math.atan2(ay, ax))
        else:
            pos[n] = (-220.0, 110.0)
    # observable property individuals: a ring at 1100, each near the datasets of its observations
    ops = sorted(by_kind["ObservableProperty"], key=str)
    for n in ops:
        angs = []
        for s in g.subjects(C.observesProperty, n):
            for d in eg.sources.get(s, []):
                if d in ds_angle:
                    angs.append(ds_angle[d])
                    break
        if angs:
            ax = sum(math.cos(a) for a in angs) / len(angs); ay = sum(math.sin(a) for a in angs) / len(angs)
            pos[n] = polar(1100, math.atan2(ay, ax))
        else:
            pos[n] = polar(1100, TAU * .62)
    # spread observable properties that landed on the same angle
    placed = sorted(ops, key=lambda n: math.atan2(pos[n][1], pos[n][0]))
    for i in range(1, len(placed)):
        a0 = math.atan2(pos[placed[i - 1]][1], pos[placed[i - 1]][0]); a1 = math.atan2(pos[placed[i]][1], pos[placed[i]][0])
        if a1 - a0 < 0.17:
            pos[placed[i]] = polar(1100, a0 + 0.17)
    # agents, people and addresses: a small cluster inside the time ring, at the top
    agents = sorted(by_kind["Organisation"] + by_kind["Person"] + by_kind["Postal address"], key=lambda n: (kinds[n], str(n)))
    for k, n in enumerate(agents):
        pos[n] = phyllo((0, -1500), k, 16)
    # the time ring, chronological from the top
    quarters = sorted(by_kind["Quarter"], key=lambda n: str(g.value(n, C.yearQuarter)))
    slots = quarters + by_kind["Time"]
    RQ = 1950
    for i, n in enumerate(slots):
        a = -TAU / 4 + TAU * i / (len(slots) + 1)
        pos[n] = polar(RQ, a)
        for p, off in ((TIME.hasBeginning, -0.018), (TIME.hasEnd, 0.018)):
            o = g.value(n, p)
            if o is not None and o in eg.index:
                pos[o] = polar(RQ + 60, a + off)
                anchor[o] = n
    # Welsh districts on a ring, each with its own disc of observations
    RL = 2950
    welsh = sorted(by_kind["WelshLAD"], key=lambda n: str(g.value(n, C.ladCode)))
    qidx = {n: i for i, n in enumerate(quarters)}
    sidx = {s: i for i, s in enumerate(SERIES_ORDER)}
    for i, lad in enumerate(welsh):
        a = -TAU / 4 + TAU * i / len(welsh)
        centre = polar(RL, a)
        pos[lad] = centre
        members = []
        for s in g.subjects(C.forLAD, lad):
            members.append(s)
        for p in (C.hasPopulation, C.hasPopulationDensity):
            members += list(g.objects(lad, p))
        def key(s):
            k = kinds[s]
            t = g.value(s, C.forTime)
            tq = qidx.get(t, 99) if t is not None else int(str(g.value(s, DCT.date) or "0")[:4])
            return (sidx.get(k, 50), tq, str(s))
        members = sorted(set(members), key=key)
        k = 0
        for s in members:
            pos[s] = phyllo(centre, k); k += 1; anchor[s] = lad
            for fp in g.objects(s, PROV.wasDerivedFrom):
                if fp in eg.index and kinds.get(fp) == "Source-row fingerprint":
                    pos[fp] = phyllo(centre, k); k += 1; anchor[fp] = lad
        for o in g.objects(lad, RDFS.seeAlso):
            if o in eg.index:
                pos[o] = polar(RL + 260, a); anchor[o] = lad
    # English districts on the outer ring, each with its density series on a short radial comb
    RE = 3780
    english = sorted(by_kind["EnglishLAD"], key=lambda n: str(g.value(n, C.ladCode)))
    for i, lad in enumerate(english):
        a = -TAU / 4 + TAU * i / len(english)
        pos[lad] = polar(RE, a)
        dens = sorted(g.objects(lad, C.hasPopulationDensity), key=lambda d: str(g.value(d, DCT.date)))
        for j, d in enumerate(dens):
            pos[d] = polar(RE + 30 + 7.5 * j, a); anchor[d] = lad
        for o in g.objects(lad, RDFS.seeAlso):
            if o in eg.index:
                pos[o] = polar(RE - 34, a); anchor[o] = lad
    # anything left (should be nothing): next to a neighbour, or at the centre
    adj = collections.defaultdict(list)
    for s, p, o in eg.edges:
        adj[s].append(o); adj[o].append(s)
    for n in eg.order:
        if n not in pos:
            nb = [m for m in adj[n] if m in pos]
            if nb:
                x, y = pos[nb[0]]
                pos[n] = (x + 18, y - 18); anchor[n] = anchor.get(nb[0], nb[0])
            else:
                pos[n] = (0.0, 120.0)
    return pos, anchor


def force_layout(eg, cache):
    """igraph DrL layout (slow); cached between builds, keyed by the node order and the edge list so that a stale
    cache is never applied to a graph it was not computed for."""
    import hashlib
    key = hashlib.sha1(("\n".join(eg.short_iri(n) for n in eg.order) + f"|{len(eg.edges)}").encode("utf-8")).hexdigest()
    if cache and os.path.exists(cache):
        data = json.load(open(cache))
        if data.get("key") == key:
            return {eg.order[i]: tuple(xy) for i, xy in enumerate(data["pos"])}
        print("force layout cache does not match this graph; recomputing (several minutes)")
    import igraph as ig
    idx = eg.index
    E = list({(idx[s], idx[o]) for s, p, o in eg.edges})
    deg = collections.Counter()
    for a, b in E:
        deg[a] += 1; deg[b] += 1
    G = ig.Graph(n=len(eg.order), edges=E)
    w = [1.0 / math.sqrt(max(deg[a], deg[b])) for a, b in G.get_edgelist()]
    L = G.layout_drl(weights=w)
    xs = [c[0] for c in L.coords]; ys = [c[1] for c in L.coords]
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    s = 3800 / max(max(xs) - min(xs), max(ys) - min(ys)) * 2
    pos = [[round((x - cx) * s, 1), round((y - cy) * s, 1)] for x, y in zip(xs, ys)]
    if cache:
        json.dump(dict(key=key, n=len(eg.order), pos=pos), open(cache, "w"))
    return {eg.order[i]: tuple(xy) for i, xy in enumerate(pos)}


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ttl"); ap.add_argument("template"); ap.add_argument("out")
    ap.add_argument("--json", default=""); ap.add_argument("--force-layout", default="")
    ap.add_argument("--commit", default=""); ap.add_argument("--commit-date", default="")
    ap.add_argument("--map-url", default="dataset-map.html", help="link target for the dataset map")
    ap.add_argument("--standalone", action="store_true", help="write a complete HTML document rather than an artifact body")
    a = ap.parse_args()

    kg = KG(a.ttl)
    eg = EntityGraph(kg)
    kinds = [eg.kind_of(n) for n in eg.order]
    kind_list = [k for grp in KIND_GROUP.values() for k in grp]
    assert set(kinds) <= set(kind_list), set(kinds) - set(kind_list)
    kind_idx = {k: i for i, k in enumerate(kind_list)}
    posS, anchor = structured_layout(eg, kg)
    posF = force_layout(eg, a.force_layout)
    preds = sorted({eg.curie(p) for s, p, o in eg.edges} | {p for n in eg.order for p, v in eg.literals[n]})
    pidx = {p: i for i, p in enumerate(preds)}
    ds_bit = {d: 1 << i for i, d in enumerate(bk.TAB_ORDER)}

    nodes_label = [eg.display_label(n) for n in eg.order]
    nodes_iri = [eg.short_iri(n) for n in eg.order]
    nodes_kind = [kind_idx[k] for k in kinds]
    nodes_src = []
    for n in eg.order:
        b = 0
        for d in eg.sources[n]:
            b |= ds_bit.get(d, 0)
        if kinds[eg.index[n]] == "Dataset record":
            b |= ds_bit.get(str(n).split("/")[-1], 0)
        nodes_src.append(b)
    types = [[t for t in eg.types[n]] for n in eg.order]
    attrs = [[[pidx[p], v] for p, v in eg.literals[n]] for n in eg.order]
    edges = []
    for s, p, o in sorted(eg.edges, key=lambda t: (eg.index[t[0]], eg.index[t[2]], str(t[1]))):
        edges += [eg.index[s], pidx[eg.curie(p)], eg.index[o]]
    deg = [0] * len(eg.order)
    for i in range(0, len(edges), 3):
        deg[edges[i]] += 1; deg[edges[i + 2]] += 1
    cl = [eg.index[anchor.get(n, n)] for n in eg.order]
    PS = []; PF = []
    for n in eg.order:
        x, y = posS[n]; PS += [round(x, 1), round(y, 1)]
        x, y = posF[n]; PF += [round(x, 1), round(y, 1)]

    counts = collections.Counter(kinds)
    pred_counts = collections.Counter(eg.curie(p) for s, p, o in eg.edges)
    legend = [dict(group=grp, kinds=[dict(name=k, n=counts.get(k, 0), c=colour_for(k, bk.HEX_LIGHT), cd=colour_for(k, bk.HEX_DARK, True), hub=k in HUB_KINDS)
                                      for k in ks if counts.get(k, 0)])
              for grp, ks in KIND_GROUP.items()]
    ds_nodes = {str(n).split("/")[-1]: eg.index[n] for n in eg.order if eg.kind_of(n) == "Dataset record"}
    assert set(bk.TAB_ORDER) <= set(ds_nodes), set(bk.TAB_ORDER) - set(ds_nodes)
    model = dict(
        meta=dict(label=kg.kg["label"], triples=kg.triples, onto=kg.onto["version"], modified=kg.kg["modified"],
                  commit=a.commit[:7], commitDate=a.commit_date[:10], built=datetime.date.today().isoformat(),
                  nodes=len(eg.order), edges=len(eg.edges), literals=sum(len(x) for x in attrs), mapUrl=a.map_url,
                  bnodes=sum(1 for n in eg.order if isinstance(n, BNode)), externals=len(eg.externals)),
        kinds=kind_list, legend=legend, preds=preds,
        relations=[dict(p=p, n=pred_counts[p]) for p in sorted(pred_counts, key=lambda p: (-pred_counts[p], p))],
        datasets=[dict(id=d, idx=i + 1, bit=ds_bit[d], topic=bk.TOPIC[d], node=ds_nodes[d]) for i, d in enumerate(bk.TAB_ORDER)],
        label=nodes_label, iri=nodes_iri, kind=nodes_kind, src=nodes_src, deg=deg, types=types, attrs=attrs,
        edges=edges, cl=cl, posS=PS, posF=PF,
    )
    js = json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = open(a.template, encoding="utf-8").read()

    def palette(hexes, surface, a_):
        out = ""
        for i, d in enumerate(bk.TAB_ORDER):
            h = hexes[bk.HUE[d]]
            out += f"--d{i + 1}:{h};--d{i + 1}t:{bk.mix(h, surface, a_)};"
        return out
    for key, val in (("/*__PALETTE_LIGHT__*/", palette(bk.HEX_LIGHT, bk.SURFACE_LIGHT, bk.TINT_LIGHT)),
                     ("/*__PALETTE_DARK__*/", palette(bk.HEX_DARK, bk.SURFACE_DARK, bk.TINT_DARK)),
                     ("/*__MODEL__*/", js)):
        assert key in tpl, key
        tpl = tpl.replace(key, val)
    if a.standalone:
        from standalone import wrap
        tpl = wrap(tpl, f"CLEETS-KG entity explorer: every individual in the knowledge graph ({len(eg.order):,} entities, {len(eg.edges):,} links) with its properties and links, searchable and highlightable by dataset.")
    open(a.out, "w", encoding="utf-8").write(tpl)
    if a.json:
        json.dump(model, open(a.json, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"wrote {a.out}: {len(tpl.encode()):,} bytes; {len(eg.order):,} nodes, {len(eg.edges):,} edges, {model['meta']['literals']:,} literals")


if __name__ == "__main__":
    main()
