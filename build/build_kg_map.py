#!/usr/bin/env python3
"""Build the CLEETS-KG dataset map: one self-contained HTML page.

usage: build_kg_map.py <index.ttl> <template.html> <out.html> [--commit HASH] [--commit-date ISO]

The graph model comes from kgmodel.KG (all counts are read from the Turtle).
This file adds the layout (which row each node sits on), the edge routes,
the per-dataset highlight sets and the text of the detail panels.
"""
import sys, os, json, re, datetime, itertools, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kgmodel import KG, C, DATA, DCT, PROV, RDF, RDFS, OWL, URIRef  # noqa: E402
from vowl_model import VowlModel  # noqa: E402

# ----------------------------------------------------------------------------
# presentation choices (the only hand-set values)
# ----------------------------------------------------------------------------
TAB_ORDER = ["VEH0132", "EVCI9001", "VEH0105", "StatsWalesPopulation", "ONSDensity",
             "ONSOpenGeography", "WIMD2025", "ONSGeoLookup"]
TOPIC = {  # short node captions, paraphrasing each record's dcterms:title
    "VEH0132": "Private battery-electric vehicles",
    "EVCI9001": "Public charging devices",
    "VEH0105": "Private licensed vehicles",
    "StatsWalesPopulation": "Mid-year population",
    "ONSDensity": "Population density",
    "ONSOpenGeography": "District codes and names",
    "WIMD2025": "Income deprivation deciles",
    "ONSGeoLookup": "LSOA to district lookup",
}
HUE = {"VEH0132": "green", "EVCI9001": "magenta", "StatsWalesPopulation": "blue", "VEH0105": "yellow",
       "ONSDensity": "orange", "WIMD2025": "violet", "ONSGeoLookup": "red", "ONSOpenGeography": "aqua"}
# categorical steps from the validated reference palette; the light column takes the
# darker documented step wherever the lighter one falls under 3:1 on the light surface
HEX_LIGHT = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#199e70", "yellow": "#c98500",
             "magenta": "#d55181", "green": "#008300", "violet": "#6250d6", "red": "#e34948"}
HEX_DARK = {"blue": "#3987e5", "orange": "#d95926", "aqua": "#199e70", "yellow": "#c98500",
            "magenta": "#d55181", "green": "#008300", "violet": "#9085e9", "red": "#e66767"}
SURFACE_LIGHT, SURFACE_DARK = "#f6f8fa", "#1a2027"   # band fill behind the nodes (--band in the template)
TINT_LIGHT, TINT_DARK = 0.15, 0.24

LICENCE_NAMES = {
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/": "Open Government Licence v3.0",
    "https://creativecommons.org/licenses/by/4.0/": "CC BY 4.0",
}

# ---- geometry ---------------------------------------------------------------
W, H = 1324, 798
ROW0, PITCH, NH = 86, 56, 40
S_X, S_W = 28, 176
LEFT_LANE = 14
D_CX, D_R = 250, 13
TEE_LANE = 221
M_X, M_W = 296, 224
HUB_SHIFT = 56
VX = 376
LANE_LAD, LANE_TIME, LANE_QT = 538, 556, 596
C1_X, C1_W = 618, 196
LANE_SUB, LANE_TOBS = 830, 850
C2_X, C2_W = 872, 206
X_X, X_W = 1130, 174
CH = 36  # class pill height

ROWS_S = {"ONSOpenGeography": 0, "ONSDensity": 1, "StatsWalesPopulation": 3, "VEH0132": 5,
          "EVCI9001": 7, "VEH0105": 9, "WIMD2025": 10, "ONSGeoLookup": 11}
ROWS_M = {"EnglishLAD": 0, "PopulationDensity": 1, "WelshLAD": 2, "Population": 3,
          "EVsPerThousandResidents": 4, "EVKeepership": 5, "KeepersPerCharger": 6, "EVChargerCount": 7,
          "ChargersPer100kResidents": 8, "PrivateVehicleStock": 9, "IncomeDeprivation": 10,
          "Time": 11, "Quarter": 12}
HUBS = {"WelshLAD", "Quarter"}
ROWS_C1 = {"cleets:EnglishLAD": 0, "cleets:PopulationDensity": 1, "cleets:WelshLAD": 2, "cleets:Population": 3,
           "cleets:EVKeepership": 5, "cleets:AdoptionRatioObservation": 6, "cleets:EVChargerCount": 7,
           "cleets:IncomeDeprivation": 10, "cleets:Time": 11, "cleets:Quarter": 12}
ROWS_C2 = {"cleets:LAD": 0.5, "cleets:ObservableProperty": 3, "cleets:Observation": 7}
ROWS_X = {"geo:Feature": 0.5, "sosa:ObservableProperty": 3, "sosa:Observation": 7,
          "time:TemporalEntity": 11, "time:Interval": 12}
OP_ORDER = ["cleets:EVKeepershipProperty", "cleets:EVChargerCountProperty", "cleets:KeeperChargerRatioProperty",
            "cleets:ChargersPerKeeperProperty", "cleets:IncomeDeprivationProperty",
            "cleetsdata:PrivateVehicleStockProperty", "cleetsdata:EVsPerThousandResidentsProperty",
            "cleetsdata:ChargersPer100kResidentsProperty"]


def ry(r):
    return ROW0 + r * PITCH


def n_(x):
    return f"{x:,}"


def words(n):
    """Small counts as words, for sentence openings."""
    w = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"]
    return w[n] if 0 <= n < len(w) else n_(n)


def short(c):
    """Graph labels drop the cleets: prefix; every other namespace keeps its own."""
    return c[len("cleets:"):] if c.startswith("cleets:") else c


def mix(fg, bg, a):
    f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a * x + (1 - a) * y):02x}" for x, y in zip(f, b))


# ----------------------------------------------------------------------------
class Builder:
    def __init__(self, kg):
        self.kg = kg
        self.nodes, self.edges, self.labels, self.trunks = {}, [], [], []
        self.dsidx = {d: i + 1 for i, d in enumerate(TAB_ORDER)}
        self._check_layout()
        self._nodes()
        self._edges()

    # ---------- sanity: the layout spec must cover exactly what the graph holds
    def _check_layout(self):
        kg = self.kg
        assert set(TAB_ORDER) == set(kg.datasets), f"dataset list changed: {sorted(kg.datasets)}"
        assert set(ROWS_S) == set(kg.datasets)
        assert set(ROWS_M) == set(kg.groups), f"group list changed: {sorted(kg.groups)}"
        cleets_classes = {c for c, v in kg.classes.items() if not v["external"]}
        assert set(ROWS_C1) | set(ROWS_C2) == cleets_classes, f"class list changed: {sorted(cleets_classes)}"
        assert set(OP_ORDER) == set(kg.obsprops), f"observable properties changed: {sorted(kg.obsprops)}"

    def node(self, id, kind, x, y, w, h, **kw):
        self.nodes[id] = dict(id=id, kind=kind, x=x, y=y, w=w, h=h, **kw)
        return self.nodes[id]

    # ---------- nodes ----------------------------------------------------------
    def _nodes(self):
        kg = self.kg
        for did, row in ROWS_S.items():
            d = kg.datasets[did]
            lines = [d["title"], "Publisher: " + d["publisher"]]
            if d["start"]:
                lines.append(f"Coverage in the record: {d['start']} to {d['end']}" + (f", {d['spatial']}" if d["spatial"] else ""))
            self.node("ds:" + did, "dataset", S_X, ry(row) - NH / 2, S_W, NH, title=did, sub=TOPIC[did],
                      ds=[self.dsidx[did]], dsid=did, row=row,
                      tip=dict(k="Dataset record (dcat:Dataset)", t=did, l=lines))
        for aid, a in kg.activities.items():
            grp = [g for g in kg.groups.values() if g.get("activity") == aid]
            assert len(grp) == 1
            row = ROWS_M[grp[0]["id"]]
            self.node("act:" + aid, "activity", D_CX - D_R, ry(row) - D_R, 2 * D_R, 2 * D_R, title="ƒ", row=row,
                      ds=[], tip=dict(k="Derivation (prov:Activity)", t=a["label"], l=[a["comment"]]))
        for gid, row in ROWS_M.items():
            g = kg.groups[gid]
            x = M_X + (HUB_SHIFT if gid in HUBS else 0)
            # colour by every dataset behind the group: its dcterms:source values plus
            # the inputs of its derivation; the upper dataset in the column comes first
            behind = set(g["sources"]) | set(kg.activities[g["activity"]]["used"] if g.get("activity") else [])
            ds = [self.dsidx[s] for s in sorted(behind, key=lambda s: ROWS_S[s])]
            sub, tip = self._group_text(g)
            self.node("g:" + gid, "group", x, ry(row) - NH / 2, M_W, NH, title=gid, sub=sub, count=g["count"],
                      ds=ds, gkind=g["kind"], derived=bool(g.get("activity")), hub=gid in HUBS, row=row, tip=tip)
        for cid, row in ROWS_C1.items():
            self._class_node(cid, C1_X, C1_W, row)
        for cid, row in ROWS_C2.items():
            self._class_node(cid, C2_X, C2_W, row)
        for cid, row in ROWS_X.items():
            known = kg.classes.get(cid)
            lines = ["External term, reused from " + {"sosa": "SOSA (W3C)", "time": "OWL-Time (W3C)", "geo": "GeoSPARQL (OGC)"}[cid.split(":")[0]]]
            if known and known["direct"] == 0:
                lines.append("Declared in the file as owl:Class; no direct instances")
            self.node("x:" + cid, "ext", X_X, ry(row) - CH / 2, X_W, CH, title=cid, row=row, ds=[],
                      tip=dict(k="Reused vocabulary term", t=cid, l=lines))
        # the named individuals of cleets:ObservableProperty, listed under the class
        rows = []
        for oc in OP_ORDER:
            o = kg.obsprops[oc]
            rows.append(dict(id="op:" + oc, text=o["local"], inonto=o["in_ontology"], used=o["observed_by"],
                             tip=dict(k="Observable property (named individual)", t=oc,
                                      l=[o["comment"] or "", f"Observed by {n_(o['observed_by'])} observations" if o["observed_by"] else "Not observed by any individual in this graph"])))
        n_in = sum(1 for r in rows if r["inonto"])
        hgt = 17 + 14.5 * n_in + 3 + 15 + 14.5 * (len(rows) - n_in) + 4
        self.node("oplist", "oplist", C2_X, ry(ROWS_C2["cleets:ObservableProperty"]) + CH / 2 + 8, C2_W, hgt, rows=rows, ds=[],
                  heads=["defined in the ontology", "defined with the data (cleetsdata:)"], n_in=n_in)

    def _class_node(self, cid, x, w, row):
        c = self.kg.classes[cid]
        lines = [c["comment"]] if c["comment"] else []
        lines.append(f"{n_(c['direct'])} direct instances" if c["direct"] else "No direct instances")
        if c["rationale"]:
            lines.append("Mapping rationale: " + c["rationale"])
        if c["disjoint"]:
            lines.append("Disjoint with " + ", ".join(c["disjoint"]))
        if not c["defined"]:
            lines.append("No rdfs:isDefinedBy on this term")
        self.node("c:" + cid, "class", x, ry(row) - CH / 2, w, CH, title=short(cid), row=row, ds=[],
                  tip=dict(k="CLEETS class (owl:Class)", t=cid, l=lines))

    def _group_text(self, g):
        kg = self.kg
        k = "Individuals in the graph"
        if g["kind"] == "series":
            val = g["values"][-1]["prop"] if g["id"] != "IncomeDeprivation" else "cleets:incomeDeprivationValue"
            nt = len(g["times"])
            when = f"{nt} quarters" if nt > 1 else g["t_first"]
            sub = f"{short(val)} · {when}"
            lines = ["rdf:type " + ", ".join(g["types"]), "cleets:observesProperty " + g["observes"],
                     "Value: " + "; ".join(f"{v['prop']} ({', '.join(v['dts'])})" for v in g["values"]),
                     f"{len(g['lads'])} districts × {nt} period{'s' if nt > 1 else ''} ({g['t_first']} to {g['t_last']})" if nt > 1
                     else f"{len(g['lads'])} districts, period {g['t_first']}",
                     "dcterms:source " + " and ".join(g["sources"])]
            if g.get("activity"):
                lines.append("prov:wasGeneratedBy " + kg.activities[g["activity"]]["curie"])
            t = f"{g['id']} × {n_(g['count'])}"
        elif g["kind"] == "attr":
            v = g["values"][0]
            y0, y1 = g["dates"][0][:4], g["dates"][-1][:4]
            sub = f"{short(v['prop'])} · mid-{y0} to {y1}"
            own = " and ".join(f"{n_(c)} {t}" for t, c in g["owner_counts"].items())
            lines = ["rdf:type " + g["types"][0], f"Value: {v['prop']} ({', '.join(v['dts'])})",
                     f"Attached by {g['link_prop']} from {own} individuals",
                     f"dcterms:date: {len(g['dates'])} mid-year dates, {g['dates'][0]} to {g['dates'][-1]}",
                     "dcterms:source " + " and ".join(g["sources"])]
            t = f"{g['id']} × {n_(g['count'])}"
        elif g["kind"] == "lad":
            sub = f"ladCode {g['codes'][0]} to {g['codes'][1]}"
            lines = ["rdf:type " + g["types"][0], f"cleets:ladCode {g['codes'][0]} to {g['codes'][1]}",
                     "rdfs:label, skos:prefLabel, rdfs:seeAlso to " + ", ".join(s.replace("https://", "") for s in g["see"]),
                     f"Target of {n_(g['obs_in'])} cleets:forLAD triples" if g["obs_in"] else "No observation points to these districts",
                     "dcterms:source " + " and ".join(g["sources"])]
            t = f"{g['id']} × {n_(g['count'])}"
        elif g["id"] == "Quarter":
            sub = f"{g['first']} to {g['last']} · also typed Time"
            lines = ["rdf:type " + ", ".join(g["types"]), f"cleets:yearQuarter {g['first']} to {g['last']}",
                     f"time:hasBeginning and time:hasEnd to {n_(g['instants'])} time:Instant nodes (not drawn)",
                     f"All {g['used']} quarters are the cleets:forTime target of at least one observation" if g["used"] == g["count"]
                     else f"{g['used']} of {g['count']} quarters are used by an observation",
                     "No dcterms:source: time entities are minted by the graph"]
            t = f"Quarter × {g['count']}"
        else:
            sub = ", ".join(short(n) for n in g["names"]) + " · not a Quarter"
            lines = ["rdf:type " + ", ".join(g["types"]), "Individuals: " + ", ".join(g["names"]),
                     "An annual period, used where the source has no quarterly breakdown"]
            t = f"Time × {g['count']}"
        return sub, dict(k=k, t=t, l=lines)

    # ---------- edge helpers -----------------------------------------------------
    @staticmethod
    def _path(pts, head, r=7):
        """Rounded orthogonal polyline; returns (d, head polygon or None)."""
        pts = [(float(x), float(y)) for x, y in pts]
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        L = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        poly = None
        if head:
            hl, hw = (7.5, 3.6) if head == "arrow" else (10, 5)
            bx, by = x2 - ux * hl, y2 - uy * hl
            poly = [(x2, y2), (bx - uy * hw, by + ux * hw), (bx + uy * hw, by - ux * hw)]
            pts[-1] = (x2 - ux * (hl - 0.5), y2 - uy * (hl - 0.5))
        d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
        for i in range(1, len(pts) - 1):
            (ax, ay), (bx_, by_), (cx, cy) = pts[i - 1], pts[i], pts[i + 1]
            l1 = ((bx_ - ax) ** 2 + (by_ - ay) ** 2) ** 0.5
            l2 = ((cx - bx_) ** 2 + (cy - by_) ** 2) ** 0.5
            rr = min(r, l1 / 2, l2 / 2)
            p1 = (bx_ - (bx_ - ax) / l1 * rr, by_ - (by_ - ay) / l1 * rr)
            p2 = (bx_ + (cx - bx_) / l2 * rr, by_ + (cy - by_) / l2 * rr)
            d.append(f"L{p1[0]:.1f},{p1[1]:.1f}Q{bx_:.1f},{by_:.1f} {p2[0]:.1f},{p2[1]:.1f}")
        d.append(f"L{pts[-1][0]:.1f},{pts[-1][1]:.1f}")
        return "".join(d), (" ".join(f"{x:.1f},{y:.1f}" for x, y in poly) if poly else None)

    def edge(self, s, t, kind, pts, head="arrow", ds=0, pred="", n=None, tip=None):
        d, poly = self._path(pts, head)
        eid = f"e{len(self.edges)}"
        self.edges.append(dict(id=eid, s=s, t=t, kind=kind, d=d, head=poly, headType=head, ds=ds, pred=pred, n=n, tip=tip))
        return eid

    def trunk(self, pts, tip):
        """Hover target for a stretch that several edges share, with a summed-up tip."""
        d, _ = self._path(pts, None)
        self.trunks.append(dict(d=d, tip=tip))

    def label(self, text, x, y, edges, rot=0, anchor="middle", always=True):
        self.labels.append(dict(text=text, x=x, y=y, rot=rot, anchor=anchor, always=always, edges=edges))

    def N(self, id):
        n = self.nodes[id]
        return n, n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"], n["y"] + n["h"] / 2

    def left_at(self, id, y):
        """x of the left outline of a node at height y (pills have round ends)."""
        n = self.nodes[id]
        if n["kind"] not in ("class", "ext"):
            return n["x"]
        r = n["h"] / 2
        dy = min(r, abs(y - (n["y"] + r)))
        return n["x"] + r - (r * r - dy * dy) ** 0.5

    # ---------- edges ------------------------------------------------------------
    def _edges(self):
        kg, g = self.kg, self.kg.g
        s_rows = set(ROWS_S.values())
        act_rows = {n["row"] for n in self.nodes.values() if n["kind"] == "activity"}

        # --- provenance side: group -> dataset, group -> derivation -> datasets
        for gid in ROWS_M:
            gr = kg.groups[gid]
            gn, gx, gy, gr_, gb, gcy = self.N("g:" + gid)
            if gr.get("activity"):
                a = kg.activities[gr["activity"]]
                an, ax, ay, ar, ab, acy = self.N("act:" + a["id"])
                self.edge("g:" + gid, "act:" + a["id"], "gen", [(gx, gcy), (ar, acy)], pred="prov:wasGeneratedBy", n=gr["count"],
                          tip=dict(k="prov:wasGeneratedBy", t=f"{gid} → {a['label']}", l=[f"{n_(gr['count'])} triples, one per derived observation"]))
                for did in a["used"]:
                    dn, dx, dy, dr, db, dcy = self.N("ds:" + did)
                    how = []
                    if did in gr["sources"]:
                        how.append("dcterms:source")
                    if did in gr["derived_from"]:
                        how.append("prov:wasDerivedFrom")
                    note = (f"Each {gid} observation also points to {did} with " + " and ".join(how)) if how else ""
                    dr_row = dn["row"] - an["row"]
                    if dr_row == 0:
                        pts = [(ax, acy), (dr, dcy)]
                    elif abs(dr_row) == 1:
                        ty = dcy + 10 if dr_row < 0 else dcy - 10
                        pts = [(ax, acy), (TEE_LANE, acy), (TEE_LANE, ty), (dr, ty)]
                    else:
                        assert an["row"] not in s_rows, "bracket route would cross a dataset node"
                        pts = [(ax, acy), (LEFT_LANE, acy), (LEFT_LANE, dcy), (dx, dcy)]
                    self.edge("act:" + a["id"], "ds:" + did, "used", pts, ds=self.dsidx[did], pred="prov:used",
                              tip=dict(k="prov:used", t=f"{a['label']} → {did}", l=[note] if note else []))
            else:
                for did in gr["sources"]:
                    dn, dx, dy, dr, db, dcy = self.N("ds:" + did)
                    extra = []
                    if gr.get("fingerprints"):
                        extra.append("prov:wasDerivedFrom points to the dataset as well, and to one source-row fingerprint (prov:Entity) per observation")
                    if dn["row"] == gn["row"]:
                        pts = [(gx, gcy), (dr, dcy)]
                    else:
                        assert gn["row"] not in s_rows and gn["row"] not in act_rows, "bracket route would cross a node"
                        pts = [(gx, gcy), (LEFT_LANE, gcy), (LEFT_LANE, dcy), (dx, dcy)]
                    self.edge("g:" + gid, "ds:" + did, "source", pts, ds=self.dsidx[did], pred="dcterms:source", n=gr["count"],
                              tip=dict(k="dcterms:source", t=f"{gid} → {did}", l=[f"{n_(gr['count'])} individuals cite {did}"] + extra))

        # --- shared dimensions: cleets:forLAD and cleets:forTime
        lad_edges, time_edges = [], []
        wn, wx, wy, wr, wb, wcy = self.N("g:WelshLAD")
        qn, qx, qy, qr, qb, qcy = self.N("g:Quarter")
        for gid in ROWS_M:
            gr = kg.groups[gid]
            if gr["kind"] != "series":
                continue
            gn, gx, gy, gr_, gb, gcy = self.N("g:" + gid)
            assert gr["lad_types"] == ["cleets:WelshLAD"], "series points outside the Welsh districts"
            lad_edges.append(self.edge("g:" + gid, "g:WelshLAD", "dim", [(gr_, gcy - 9), (LANE_LAD, gcy - 9), (LANE_LAD, wb)],
                                       pred="cleets:forLAD", n=gr["count"],
                                       tip=dict(k="cleets:forLAD", t=f"{gid} → WelshLAD", l=[f"{n_(gr['count'])} triples, one district per observation",
                                                                                           kg.props["cleets:forLAD"]["chain"]])))
            if "cleets:Quarter" in gr["time_types"]:
                time_edges.append(self.edge("g:" + gid, "g:Quarter", "dim", [(gr_, gcy + 9), (LANE_TIME, gcy + 9), (LANE_TIME, qy)],
                                            pred="cleets:forTime", n=gr["count"],
                                            tip=dict(k="cleets:forTime", t=f"{gid} → Quarter", l=[f"{n_(gr['count'])} triples to {len(gr['times'])} quarters ({gr['t_first']} to {gr['t_last']})",
                                                                                                kg.props["cleets:forTime"]["chain"]])))
            else:
                tn, tx, ty_, tr, tb, tcy = self.N("g:Time")
                assert tn["row"] == gn["row"] + 1
                eid = self.edge("g:" + gid, "g:Time", "dim", [(VX, gb), (VX, ty_)], pred="cleets:forTime", n=gr["count"],
                                tip=dict(k="cleets:forTime", t=f"{gid} → Time", l=[f"{n_(gr['count'])} triples to {', '.join(kg.groups['Time']['names'])}",
                                                                                 kg.props["cleets:forTime"]["chain"]]))
                self.label("forTime", VX + 8, (gb + ty_) / 2 + 3.4, [eid], anchor="start")
        self.label("forLAD", LANE_LAD + 11, (ry(3) + ry(4)) / 2, lad_edges, rot=-90)
        self.label("forTime", LANE_TIME + 11, (ry(10) + ry(11)) / 2, time_edges, rot=-90)
        ser = [kg.groups[k] for k in ROWS_M if kg.groups[k]["kind"] == "series"]
        to_q = [x for x in ser if "cleets:Quarter" in x["time_types"]]
        self.trunk([(LANE_LAD, max(self.N("g:" + x["id"])[5] for x in ser) - 9), (LANE_LAD, wb)],
                   dict(k="cleets:forLAD", t=f"{len(ser)} observation series → WelshLAD",
                        l=[f"{n_(sum(x['count'] for x in ser))} triples in total, one district per observation", kg.props["cleets:forLAD"]["chain"],
                           "Range cleets:LAD; every target here is a cleets:WelshLAD"]))
        self.trunk([(LANE_TIME, min(self.N("g:" + x["id"])[5] for x in to_q) + 9), (LANE_TIME, qy)],
                   dict(k="cleets:forTime", t=f"{len(to_q)} observation series → Quarter",
                        l=[f"{n_(sum(x['count'] for x in to_q))} triples in total, one quarter per observation", kg.props["cleets:forTime"]["chain"]]))

        # --- attribute nodes hang off the district
        for aid in ("PopulationDensity", "Population"):
            at = kg.groups[aid]
            an, ax, ay, ar, ab, acy = self.N("g:" + aid)
            for lid in ("EnglishLAD", "WelshLAD"):
                lad = kg.groups[lid]
                cnt = sum(1 for o in at["members"] for s in g.subjects(at["link_node"], o) if s in lad["members"])
                if not cnt:
                    continue
                ln, lx, ly, lr, lb, lcy = self.N("g:" + lid)
                assert abs(ln["row"] - an["row"]) == 1
                pts = [(VX, lb), (VX, ay)] if ln["row"] < an["row"] else [(VX, ly), (VX, ab)]
                p = kg.props[at["link_prop"]]
                eid = self.edge("g:" + lid, "g:" + aid, "attr", pts, pred=at["link_prop"], n=cnt,
                                tip=dict(k=at["link_prop"], t=f"{lid} → {aid}", l=[f"{n_(cnt)} triples",
                                                                                 f"Range {p['range']}; no rdfs:domain asserted" if not p["domain"] else f"Domain {p['domain']}, range {p['range']}"]))
                self.label(short(at["link_prop"]), VX + 8, (pts[0][1] + pts[1][1]) / 2 + 3.4, [eid], anchor="start")

        # --- rdf:type: individuals -> classes
        on_, ox, oy, or_, ob, ocy = self.N("c:cleets:Observation")
        for gid in ROWS_M:
            gr = kg.groups[gid]
            gn, gx, gy, gr_, gb, gcy = self.N("g:" + gid)
            for tc in gr["types"]:
                cn, cx, cy_, cr, cb, ccy = self.N("c:" + tc)
                tip = dict(k="rdf:type", t=f"{gid} → {tc}", l=[f"{n_(gr['count'])} individuals"])
                if abs(ccy - gcy) < 0.5:
                    pts = [(gr_, gcy), (cx, ccy)]
                elif tc == "cleets:Observation":
                    pts = [(gr_, gcy), (LANE_TOBS, gcy), (LANE_TOBS, ocy + 9), (self.left_at("c:cleets:Observation", ocy + 9), ocy + 9)]
                    tip["l"].append("No dedicated subclass: these observations are typed cleets:Observation only")
                else:
                    assert gid == "Quarter" and tc == "cleets:Time", (gid, tc)
                    pts = [(gr_, gcy - 10), (LANE_QT, gcy - 10), (LANE_QT, ccy + 10), (self.left_at("c:" + tc, ccy + 10), ccy + 10)]
                    tip["l"].append("Asserted on every quarter next to cleets:Quarter")
                self.edge("g:" + gid, "c:" + tc, "type", pts, pred="rdf:type", n=gr["count"], tip=tip)
        # the list of observable properties belongs to its class
        ln_ = self.nodes["oplist"]
        pn, px, py, pr, pb, pcy = self.N("c:cleets:ObservableProperty")
        self.edge("oplist", "c:cleets:ObservableProperty", "type", [(px + 26, ln_["y"]), (px + 26, pb)], head=None, pred="rdf:type",
                  tip=dict(k="rdf:type", t="8 named individuals → cleets:ObservableProperty", l=[]))

        # --- class hierarchy and alignments
        for cid, c in kg.classes.items():
            if c["external"]:
                continue
            cn, cx, cy_, cr, cb, ccy = self.N("c:" + cid)
            for sup in c["supers"]:
                tid = ("c:" if sup in ROWS_C1 or sup in ROWS_C2 else "x:") + sup
                tn, tx, ty_, tr, tb, tcy = self.N(tid)
                arrive = tcy - 9 if sup == "cleets:Observation" else tcy
                if abs(arrive - ccy) < 0.5:
                    pts = [(cr, ccy), (tx, arrive)]
                else:
                    pts = [(cr, ccy), (LANE_SUB, ccy), (LANE_SUB, arrive), (self.left_at(tid, arrive), arrive)]
                self.edge("c:" + cid, tid, "sub", pts, head="tri", pred="rdfs:subClassOf",
                          tip=dict(k="rdfs:subClassOf", t=f"{cid} ⊑ {sup}", l=["Mapping rationale: " + c["rationale"]] if c["rationale"] and tid.startswith("x:") else []))
            for eq in c["equiv"]:
                tn, tx, ty_, tr, tb, tcy = self.N("x:" + eq)
                assert abs(tcy - ccy) < 0.5
                eid = self.edge("c:" + cid, "x:" + eq, "eq", [(cr, ccy), (tx, tcy)], head=None, pred="owl:equivalentClass",
                                tip=dict(k="owl:equivalentClass", t=f"{cid} ≡ {eq}", l=["Mapping rationale: " + c["rationale"]] if c["rationale"] else []))
                self.label("≡", tx - 26, ccy + 4.5, [eid])
        for sup in ("cleets:Observation", "cleets:LAD"):
            subs = [cid for cid, c in kg.classes.items() if sup in c["supers"]]
            tn, tx, ty_, tr, tb, tcy = self.N("c:" + sup)
            arrive = tcy - 9 if sup == "cleets:Observation" else tcy
            ys = [self.N("c:" + x)[5] for x in subs]
            for y_end in {min(ys), max(ys)} - {arrive}:
                self.trunk([(LANE_SUB, y_end), (LANE_SUB, arrive), (self.left_at("c:" + sup, arrive), arrive)],
                           dict(k="rdfs:subClassOf", t=f"{len(subs)} subclasses of {sup}", l=[", ".join(subs)]))
        gen = [x for x in (kg.groups[k] for k in ROWS_M) if x["kind"] == "series" and x["types"] == ["cleets:Observation"]]
        ys = [self.N("g:" + x["id"])[5] for x in gen]
        for y_end in {min(ys), max(ys)}:
            self.trunk([(LANE_TOBS, y_end), (LANE_TOBS, ocy + 9), (self.left_at("c:cleets:Observation", ocy + 9), ocy + 9)],
                       dict(k="rdf:type", t=f"{len(gen)} series typed cleets:Observation directly",
                            l=[", ".join(f"{x['id']} ({n_(x['count'])})" for x in gen), "None of them has a dedicated subclass"]))
        # one axiom that comes with the imported OWL-Time ontology
        qc = kg.classes["cleets:Quarter"]
        assert "http://www.w3.org/2006/time" in kg.onto["imports"]
        i_n, ix, iy, ir, ib, icy = self.N("x:time:Interval")
        t_n, tx, ty_, tr, tb, tcy = self.N("x:time:TemporalEntity")
        self.edge("x:time:Interval", "x:time:TemporalEntity", "imp", [(ix + X_W / 2, iy), (ix + X_W / 2, tb)], head="tri",
                  pred="rdfs:subClassOf",
                  tip=dict(k="rdfs:subClassOf (through owl:imports)", t="time:Interval ⊑ time:TemporalEntity",
                           l=["Not asserted in this file. It belongs to OWL-Time, which the ontology imports.",
                              "cleets:Quarter mapping rationale: " + (qc["rationale"] or "")]))

    # ---------- highlight sets ---------------------------------------------------
    def _chain_up(self, nid, acc):
        for e in self.edges:
            if e["s"] == nid and e["kind"] in ("type", "sub", "eq", "imp") and e["id"] not in acc:
                acc.add(e["id"])
                acc.add(e["t"])
                self._chain_up(e["t"], acc)

    def highlight(self, did):
        kg = self.kg
        on, ctx = {"ds:" + did}, set()
        core = []
        for gid, gr in kg.groups.items():
            if gr["kind"] == "time":
                continue
            if gr.get("activity"):
                if did in kg.activities[gr["activity"]]["used"]:
                    core.append(gid)
            elif gr["sources"] == [did]:
                core.append(gid)
        core_ids = {"g:" + c for c in core}
        hubs = set()
        for gid in core:
            nid = "g:" + gid
            on.add(nid)
            gr = kg.groups[gid]
            if gr["kind"] == "series":
                on.add("op:" + gr["observes"])
            for e in self.edges:
                if e["s"] == nid and e["kind"] == "source":
                    on.update((e["id"], e["t"]))
                elif e["s"] == nid and e["kind"] == "gen":
                    on.update((e["id"], e["t"]))
                    for e2 in self.edges:
                        if e2["s"] == e["t"] and e2["kind"] == "used":
                            on.update((e2["id"], e2["t"]))
                elif e["s"] == nid and e["kind"] == "dim":
                    on.update((e["id"], e["t"]))
                    hubs.add(e["t"])
                elif e["t"] == nid and e["kind"] == "attr":
                    on.update((e["id"], e["s"]))
                    hubs.add(e["s"])
                elif e["s"] == nid and e["kind"] == "attr":
                    on.add(e["id"])
                    ctx.add(e["t"])
                    for e2 in self.edges:
                        if e2["s"] == e["t"] and e2["kind"] in ("source", "type"):
                            ctx.update((e2["id"], e2["t"]))
                elif e["t"] == nid and e["kind"] == "dim":
                    ctx.update((e["id"], e["s"]))
            self._chain_up(nid, on)
        for h in hubs - core_ids:
            self._chain_up(h, on)
            for e in self.edges:
                if e["s"] == h and e["kind"] == "source":
                    ctx.update((e["id"], e["t"]))
        if any(i.startswith("op:") for i in on):
            on.add("oplist")
            self._chain_up("oplist", on)
        ctx -= on
        return dict(on=sorted(on), ctx=sorted(ctx), core=core)


# ----------------------------------------------------------------------------
# text of the panels. Conventions for "rich" strings, rendered by the page:
#   `code`   **bold**   [[DatasetId]] (a chip that opens that dataset's tab)
# Text copied from the graph is passed as plain strings and never parsed.
# ----------------------------------------------------------------------------
def code(c):
    return f"`{c}`"


def chip(d):
    return f"[[{d}]]"


def R(s):
    return {"r": s}


def PL(s):
    return {"p": s}


class Panels:
    def __init__(self, kg, builder):
        self.kg, self.b = kg, builder

    def primary(self, did):
        return [self.kg.groups[k] for k in ROWS_M if self.kg.groups[k]["sources"] == [did]]

    def acts(self, did):
        a = [a for a in self.kg.activities.values() if did in a["used"]]
        return sorted(a, key=lambda a: ROWS_M[self.group_of(a)["id"]])

    def group_of(self, a):
        return next(g for g in self.kg.groups.values() if g.get("activity") == a["id"])

    # ---- small phrases -----------------------------------------------------
    def modelled_phrase(self, did):
        prim = self.primary(did)
        if not prim:
            return "No individuals of its own. It is an input to one derivation."
        if all(g["kind"] == "lad" for g in prim):
            return (f"**{n_(sum(g['count'] for g in prim))}** district individuals: "
                    + " and ".join(f"{n_(g['count'])} {code(g['id'])}" for g in sorted(prim, key=lambda g: -g['count'])))
        out = []
        for g in prim:
            if g["kind"] == "series":
                if len(g["times"]) > 1:
                    out.append(f"**{n_(g['count'])}** {code(g['id'])} observations, one per district and quarter ({len(g['lads'])} × {len(g['times'])})")
                else:
                    out.append(f"**{n_(g['count'])}** {code(g['id'])} observations, one per district for {g['t_first']}")
            else:
                out.append(f"**{n_(g['count'])}** {code(g['id'])} nodes, one per district and mid-year ({n_(len(g['owners']))} × {len(g['dates'])})")
        return "; ".join(out)

    def meets_phrase(self, did):
        prim = self.primary(did)
        parts = []
        for a in self.acts(did):
            g = self.group_of(a)
            others = " and ".join(chip(o) for o in a["used"] if o != did)
            if g in prim:
                parts.append(f"{others}, used to aggregate it into {code(g['id'])}")
            else:
                parts.append(f"{others} in {code(g['id'])} ({n_(g['count'])})")
        if parts:
            return " · ".join(parts)
        if prim and all(g["kind"] == "lad" for g in prim):
            obs = sum(g["obs_in"] for g in prim)
            return f"All {n_(obs)} observations and every population and density node hang off its district individuals"
        quarterly = any(g["kind"] == "series" and len(g["times"]) > 1 for g in prim)
        return ("No derivation combines it with another dataset. It joins the others through shared district"
                + (" and quarter" if quarterly else "") + " individuals.")

    def ontology_phrase(self, did):
        prim = self.primary(did)
        kg = self.kg
        if not prim:
            g = self.group_of(self.acts(did)[0])
            return f"None of its own. The derived {code(g['types'][0])} observations carry the link."
        chains, generic = [], False
        for g in prim:
            for t in g["type_nodes"]:
                ch = kg.class_chain(t)
                if ch not in chains:
                    chains.append(ch)
            if g["kind"] == "series" and g["types"] == ["cleets:Observation"]:
                generic = True
        txt = " · ".join(code(c) for c in chains)
        if generic:
            txt += ", with the observable property kept in the data namespace"
        return txt

    # ---- cards ---------------------------------------------------------------
    def card_record(self, did):
        d = self.kg.datasets[did]
        prim = self.primary(did)
        kv = [["Title", PL(d["title"])]]
        if d["alt"]:
            kv.append(["Extract used", PL(d["alt"])])
        kv.append(["Publisher", PL(d["publisher"])])
        if d["series"]:
            kv.append(["Collection", PL(d["series"])])
        if d["start"] or d["spatial"]:
            kv.append(["Coverage stated in the record",
                       PL(", ".join(x for x in [f"{d['start']} to {d['end']}" if d["start"] else None, d["spatial"]] if x))])
        cov = []
        for g in prim:
            if g["kind"] == "series":
                cov.append(f"{g['id']}: {g['t_first']} to {g['t_last']}, {len(g['lads'])} districts" if len(g["times"]) > 1
                           else f"{g['id']}: {g['t_first']}, {len(g['lads'])} districts")
            elif g["kind"] == "attr":
                cov.append(f"{g['id']}: {g['dates'][0]} to {g['dates'][-1]}, {n_(len(g['owners']))} districts")
            else:
                cov.append(f"{g['id']}: {n_(g['count'])} districts")
        kv.append(["Coverage held in the graph", PL("; ".join(cov) if cov else "No individuals cite it with dcterms:source")])
        kv.append(["Licence", PL(LICENCE_NAMES.get(d["license"], d["license"]))])
        for key in ("comment", "description", "provenance"):
            if d[key]:
                kv.append(["Note in the record", PL(d[key])])
        links, seen = [], set()
        for name, url in (("Landing page", d["landing"]), ("Access page", d["access"]), ("Licence text", d["license"])):
            if url and url not in seen:
                seen.add(url)
                links.append([name, url])
        return dict(h="Source record", sub=code("dcat:Dataset") + ", " + code("prov:Entity"), kv=kv, links=links,
                    cite=d["citation"], wide=False)

    def block_group(self, g, did):
        kg = self.kg
        kv = []
        if g["kind"] == "series":
            t = g["types"][0]
            kv.append(["Type", R(code(t) + (" only: there is no dedicated subclass" if t == "cleets:Observation" else ""))])
            op = kg.obsprops[g["observes"]]
            kv.append(["Observes", R(code(g["observes"]) + (", defined in the ontology" if op["in_ontology"] else ", defined in the data namespace, not in the ontology"))])
            kv.append(["Value", R("; ".join(code(v["prop"]) + " (" + ", ".join(code(d) for d in v["dts"]) + ")" for v in g["values"]))])
            kv.append(["District", R(f"{code('cleets:forLAD')} to {len(g['lads'])} {code(g['lad_types'][0])} individuals")])
            if len(g["times"]) > 1:
                kv.append(["Period", R(f"{code('cleets:forTime')} to {len(g['times'])} {code('cleets:Quarter')} individuals, {g['t_first']} to {g['t_last']}")])
            else:
                nm = kg.curie(next(iter(g["times"])))
                kv.append(["Period", R(f"{code('cleets:forTime')} to {code(nm)}, a {code('cleets:Time')} that is not a quarter")])
            if g["complete"]:
                kv.append(["Grid", R(f"complete: {len(g['lads'])} × {len(g['times'])} = {n_(g['count'])}")])
            prov = f"{code('dcterms:source')} to " + " and ".join(chip(s) for s in g["sources"])
            prov += f"; {code('prov:wasDerivedFrom')} to " + " and ".join(chip(s) for s in g["derived_from"])
            if g["fingerprints"]:
                prov += f", plus one source-row fingerprint ({code('prov:Entity')}) per observation"
            if g.get("activity"):
                prov += f"; {code('prov:wasGeneratedBy')} to {code(kg.activities[g['activity']]['curie'])}"
            kv.append(["Provenance", R(prov)])
        elif g["kind"] == "attr":
            kv.append(["Type", R(code(g["types"][0]) + ", not a subclass of " + code("cleets:Observation"))])
            kv.append(["Value", R("; ".join(code(v["prop"]) + " (" + ", ".join(code(d) for d in v["dts"]) + ")" for v in g["values"]))])
            own = " and ".join(f"{n_(c)} {code(t)}" for t, c in g["owner_counts"].items())
            kv.append(["District", R(f"reached by {code(g['link_prop'])} from {own} individuals")])
            kv.append(["Period", R(f"{code('dcterms:date')}: {len(g['dates'])} mid-year dates, {g['dates'][0]} to {g['dates'][-1]}. No {code('cleets:forTime')}.")])
            if g["complete"]:
                kv.append(["Grid", R(f"complete: {n_(len(g['owners']))} × {len(g['dates'])} = {n_(g['count'])}")])
            kv.append(["Provenance", R(f"{code('dcterms:source')} to {chip(did)}")])
        else:
            kv.append(["Type", R(code(g["types"][0]))])
            kv.append(["Identifier", R(f"{code('cleets:ladCode')}, {g['codes'][0]} to {g['codes'][1]}")])
            kv.append(["Names", R(f"{code('rdfs:label')} and {code('skos:prefLabel')}")])
            kv.append(["See also", R(f"{code('rdfs:seeAlso')} to " + ", ".join(s.replace('https://', '') for s in g["see"]))])
            carried = []
            for aid in ("Population", "PopulationDensity"):
                at = kg.groups[aid]
                c = sum(1 for o in at["members"] for s in kg.g.subjects(at["link_node"], o) if s in g["members"])
                if c:
                    carried.append(f"{n_(c)} {code(at['link_prop'])}")
            kv.append(["Used by", R((f"{n_(g['obs_in'])} {code('cleets:forLAD')} triples" if g["obs_in"] else "no observation")
                                    + ("; carries " + " and ".join(carried) if carried else ""))])
            kv.append(["Provenance", R(f"{code('dcterms:source')} to {chip(did)}")])
        return dict(h=f"{code(g['id'])} × {n_(g['count'])}", kv=kv)

    def card_modelled(self, did):
        prim = self.primary(did)
        if not prim:
            a = self.acts(did)[0]
            g = self.group_of(a)
            lead = (f"No individual cites {chip(did)} with {code('dcterms:source')}, so it has no nodes of its own in the data layer. "
                    f"It is named as an input ({code('prov:used')}) of {code(a['curie'])} and in {code('prov:wasDerivedFrom')} "
                    f"on the {n_(g['count'])} {code(g['id'])} observations.")
            return dict(h="How it is modelled", lead=lead, blocks=[])
        return dict(h="How it is modelled", blocks=[self.block_group(g, did) for g in prim])

    def time_cell(self, A, B):
        kg = self.kg
        tA = set().union(*[g["times"] for g in A]) if A else set()
        tB = set().union(*[g["times"] for g in B]) if B else set()
        dA = set().union(*[set(g.get("dates", [])) for g in A]) if A else set()
        dB = set().union(*[set(g.get("dates", [])) for g in B]) if B else set()
        if tA and tB:
            common = tA & tB
            if common:
                lab = sorted(kg.lit(t, RDFS.label) for t in common)
                return f"{len(common)} ({lab[0]} to {lab[-1]})" if len(common) > 1 else f"1 ({lab[0]})"
            return "none (an annual period against quarters)"
        if dA and dB:
            return f"none; {len(dA & dB)} {code('dcterms:date')} values in common"
        if (tA and dB) or (dA and tB):
            return f"none (one side is dated with {code('dcterms:date')})"
        return "not applicable"

    def card_links(self, did):
        kg = self.kg
        prim = self.primary(did)
        items = []
        for a in self.acts(did):
            g = self.group_of(a)
            others = " and ".join(chip(o) for o in a["used"] if o != did)
            val = g["values"][-1]["prop"] if g["id"] != "IncomeDeprivation" else "cleets:incomeDeprivationValue"
            items.append(dict(
                h=f"With {others}: {code(g['id'])} × {n_(g['count'])}",
                p=f"{a['label']}. The result is typed {code(g['types'][0])} and stored in {code(val)}.",
                quote=a["comment"], qsrc=f"rdfs:comment of {a['curie']}"))
        lead = None
        if not items:
            lead = (f"No derivation in the graph uses {chip(did)} together with another dataset."
                    if not (prim and all(g['kind'] == 'lad' for g in prim)) else
                    f"No derivation uses {chip(did)}. It supplies the district individuals that everything else points to.")
        table = None
        if prim:
            lA = set().union(*[g["lads"] for g in prim])
            rows = []
            for other in TAB_ORDER:
                if other == did:
                    continue
                po = self.primary(other)
                if not po:
                    continue
                lB = set().union(*[g["lads"] for g in po])
                rows.append([R(chip(other)), R(n_(len(lA & lB))), R(self.time_cell(prim, po))])
            head = ["Dataset", "Districts in common", "Time individuals in common"]
            if all(r[2]["r"] == "not applicable" for r in rows):   # nothing to say about time: drop the column
                head, rows = head[:2], [r[:2] for r in rows]
            table = dict(cap="Shared individuals between its own nodes and those of each other dataset", head=head, rows=rows)
        foot = None
        if did != "ONSOpenGeography" and prim:
            foot = f"The district individuals themselves cite {chip('ONSOpenGeography')}. Quarter individuals carry no source dataset."
        return dict(h="Links to other datasets", lead=lead, items=items, table=table, foot=foot)

    def card_ontology(self, did):
        kg = self.kg
        prim = self.primary(did)
        terms, seen, classes = [], set(), []

        def add(role, chain, note=None):
            if (role, chain) not in seen:
                seen.add((role, chain))
                terms.append(dict(role=role, chain=chain, note=note))

        def rng(p):
            pr = kg.props[p]
            bits = []
            if pr["domain"]:
                bits.append(f"domain {code(pr['domain'])}")
            bits.append(f"range {code(pr['range'])}" if pr["range"] else f"no {code('rdfs:range')}")
            if not pr["domain"]:
                bits.append(f"no {code('rdfs:domain')}")
            return ", ".join(bits)

        groups = prim
        lead = None
        if not prim:
            groups = [self.group_of(a) for a in self.acts(did)]
            lead = f"{chip(did)} has no individuals of its own. These are the terms used by the observations derived from it."
        for g in groups:
            for t in g["type_nodes"]:
                c = kg.classes[kg.curie(t)]
                classes.append(t)
                add("Class", c["chain"], PL(c["comment"]) if c["comment"] else None)
            if g["kind"] == "series":
                add("District", kg.props["cleets:forLAD"]["chain"], R(rng("cleets:forLAD") + f" ({code(kg.classes['cleets:LAD']['chain'])})"))
                add("Period", kg.props["cleets:forTime"]["chain"], R(rng("cleets:forTime") + f" ({code(kg.classes['cleets:Time']['chain'])})"))
                op = kg.obsprops[g["observes"]]
                add("Observes", kg.props["cleets:observesProperty"]["chain"],
                    R(f"here {code(g['observes'])}, " + ("one of the named individuals shipped with the ontology" if op["in_ontology"]
                                                        else "a named individual defined with the data")))
                for v in g["values"]:
                    add("Value", v["chain"], R(rng(v["prop"])))
            elif g["kind"] == "attr":
                add("Link from the district", kg.props[g["link_prop"]]["chain"], R(rng(g["link_prop"])))
                for v in g["values"]:
                    add("Value", v["chain"], R(rng(v["prop"])))
                add("Date", "dcterms:date", R(f"a Dublin Core term. {code('cleets:forTime')} is not used on these nodes; its domain is {code(kg.props['cleets:forTime']['domain'])}"))
            elif g["kind"] == "lad":
                for v in g["values"]:
                    add("Identifier", v["chain"], R(rng(v["prop"])))
        allc = set(classes)
        for c in classes:
            allc |= set(kg.superclasses(c))
        shapes = kg.shapes_for(allc)
        foot = ("Checked by the bundled SHACL shapes " + ", ".join(code(s) for s in shapes) + ".") if shapes else None
        return dict(h="Links to the ontology", lead=lead, terms=terms, foot=foot)

    def card_example(self, did):
        kg = self.kg
        prim = self.primary(did)
        if prim:
            g = prim[0] if not any(x["id"] == "WelshLAD" for x in prim) else kg.groups["WelshLAD"]
            lead = None
        else:
            g = self.group_of(self.acts(did)[0])
            lead = f"{chip(did)} appears only in {code('prov:wasDerivedFrom')} and {code('prov:used')}. One of the observations that name it:"
        ex = g["example"]
        cap = {"cleets:hasPopulation": 2, "cleets:hasPopulationDensity": 2}
        where = kg.lit(ex, RDFS.label) or ""
        return dict(h="One individual from the graph", lead=lead, code=kg.turtle(ex, cap=cap),
                    codecap=f"{kg.curie(ex)}, as stated in the Turtle source (label: “{where.strip()}”)", wide=True)

    def dataset_panel(self, did):
        d = self.kg.datasets[did]
        return dict(
            id=did, name=did, title=d["title"],
            strip=[["Modelled as", self.modelled_phrase(did)], ["Meets", self.meets_phrase(did)], ["Ontology", self.ontology_phrase(did)]],
            cards=[self.card_modelled(did), self.card_links(did), self.card_ontology(did), self.card_record(did), self.card_example(did)],
        )

    # ---- the overview ----------------------------------------------------------
    def overview_panel(self):
        kg = self.kg
        gs = kg.groups
        series = [gs[k] for k in ROWS_M if gs[k]["kind"] == "series"]
        attrs = [gs[k] for k in ROWS_M if gs[k]["kind"] == "attr"]
        lads = [gs[k] for k in ROWS_M if gs[k]["kind"] == "lad"]
        times = [gs[k] for k in ROWS_M if gs[k]["kind"] == "time"]
        n_obs = sum(g["count"] for g in series)
        agents = sorted({a for d in kg.datasets.values() for a in d["agents"]})
        vocab = {"http://www.w3.org/ns/sosa/": "SOSA", "http://www.w3.org/2006/time": "OWL-Time"}
        imports = [vocab.get(i, i) for i in kg.onto["imports"]]
        strip = [
            ["The graph", f"**{n_(kg.triples)}** triples: {n_(n_obs)} observations in {len(series)} series, "
                          f"{n_(sum(g['count'] for g in attrs))} population and density nodes, "
                          f"{n_(sum(g['count'] for g in lads))} districts, {sum(g['count'] for g in times)} time entities"],
            ["Sources", f"**{len(kg.datasets)}** dataset records, attributed to " + ", ".join(agents[:-1]) + " and " + agents[-1]],
            ["Ontology", f"CLEETS v{kg.onto['version']}: {kg.counts['classes']} classes, {kg.counts['object_props']} object and "
                         f"{kg.counts['datatype_props']} datatype properties; imports " + " and ".join(imports)],
        ]
        # where datasets meet
        items = []
        for a in sorted(kg.activities.values(), key=lambda a: ROWS_M[self.group_of(a)["id"]]):
            g = self.group_of(a)
            items.append(dict(h=" + ".join(chip(u) for u in sorted(a["used"], key=TAB_ORDER.index)) + f": {code(g['id'])} × {n_(g['count'])}",
                              p=a["label"] + "."))
        direct = [g for g in series if not g.get("activity")]
        head = [""] + [g["sources"][0] for g in direct]
        rows = []
        for a in direct:
            rows.append([R(chip(a["sources"][0]))] + [R(n_(len(a["keys"] & b["keys"]))) for b in direct])
        meet = dict(
            h="Where datasets meet",
            lead=(f"{words(len(kg.activities))} derivations ({code('prov:Activity')}) combine two datasets each. Everywhere else, datasets meet only "
                  f"through shared individuals: each observation points to one of {gs['WelshLAD']['count']} {code('cleets:WelshLAD')} "
                  f"districts with {code('cleets:forLAD')} and to one period with {code('cleets:forTime')}."),
            items=items,
            table=dict(cap="District and quarter pairs in common between the directly sourced series", head=head, rows=rows))
        # modelling patterns
        dedicated = [g for g in series if g["types"] != ["cleets:Observation"]]
        generic = [g for g in series if g["types"] == ["cleets:Observation"]]
        def lst(groups):
            return ", ".join(f"{code(g['id'])} ({n_(g['count'])})" for g in groups)
        patterns = dict(
            h="Three ways the data reach the ontology",
            items=[
                dict(h=f"Dedicated observation classes: {n_(sum(g['count'] for g in dedicated))} individuals",
                     p=f"{lst(dedicated)}. Each is typed with a subclass of {code('cleets:Observation')} and observes a property that the ontology defines."),
                dict(h=f"Generic {code('cleets:Observation')}: {n_(sum(g['count'] for g in generic))} individuals",
                     p=f"{lst(generic)}. They are told apart only by an observable property minted in the data namespace, and store the result in {code('cleets:hasSimpleResult')}."),
                dict(h=f"Attribute nodes on the district: {n_(sum(g['count'] for g in attrs))} individuals",
                     p=f"{lst(attrs)}. They are reached from the district ({', '.join(code(g['link_prop']) for g in attrs)}), dated with {code('dcterms:date')}, and are not observations."),
            ])
        unused_ops = [o["curie"] for o in kg.obsprops.values() if not o["observed_by"]]
        unused_dps = [p["curie"] for p in kg.props.values() if p["kind"] == "datatype" and not p["uses"]]
        left = dict(
            h="What the map leaves out",
            bullets=[
                f"{n_(kg.counts['fingerprints'])} source-row fingerprints ({code('prov:Entity')}), one behind each observation in "
                f"{sum(1 for g in series if g['fingerprints'])} of the {len(series)} series",
                f"{n_(gs['Quarter']['instants'])} {code('time:Instant')} nodes that bound the quarters",
                f"{n_(kg.counts['labels'])} {code('rdfs:label')} triples and other annotations",
                f"{kg.counts['shapes']} SHACL node shapes, {kg.counts['agents']} agent records, and the dataset series and distribution records",
                "Datatype properties, which appear inside the nodes instead of as edges",
            ] + ([f"Declared but not used by any individual: " + ", ".join(code(x) for x in unused_ops + unused_dps)] if unused_ops or unused_dps else []))
        cite = dict(
            h="Source and citation",
            kv=[["Graph", PL(kg.kg["citation"])], ["Ontology", PL(kg.onto["citation"])],
                ["Licence", PL(f"{LICENCE_NAMES.get(kg.kg['license'], kg.kg['license'])}. {kg.kg['rights']}")]],
            links=[["Turtle source on GitHub", "https://github.com/Naeima/cleets/blob/main/index.ttl"],
                   ["Repository", "https://github.com/Naeima/cleets"]])
        return dict(id="all", name="All datasets", title=kg.kg["title"], strip=strip, cards=[meet, patterns, left, cite])


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ttl")
    ap.add_argument("template")
    ap.add_argument("out")
    ap.add_argument("--commit", default="")
    ap.add_argument("--commit-date", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--vowl-pos", default="", help="baked node positions from bake_layout.py")
    ap.add_argument("--entities-url", default="entity-explorer.html", help="link target for the entity explorer")
    ap.add_argument("--standalone", action="store_true", help="write a complete HTML document rather than an artifact body")
    a = ap.parse_args()

    kg = KG(a.ttl)
    b = Builder(kg)
    p = Panels(kg, b)

    tabs = [dict(id="all", name="All datasets", idx=0)] + [dict(id=d, name=d, idx=i + 1, topic=TOPIC[d]) for i, d in enumerate(TAB_ORDER)]
    bands = [
        dict(x0=8, x1=S_X + S_W + 12, title="Sources", sub="dataset records"),
        dict(x0=S_X + S_W + 24, x1=LANE_QT + 12, title="CLEETS-KG data", sub="individuals, grouped; × gives the count"),
        dict(x0=C1_X - 8, x1=C2_X + C2_W + 38, title="CLEETS ontology", sub=f"classes and named individuals, v{kg.onto['version']}"),
        dict(x0=X_X - 8, x1=X_X + X_W + 12, title="Reused vocabularies", sub="SOSA, OWL-Time, GeoSPARQL"),
    ]
    vm = VowlModel(kg, TAB_ORDER, TOPIC)
    vowl = vm.as_dict()
    if a.vowl_pos and os.path.exists(a.vowl_pos):
        vowl["pos"] = json.load(open(a.vowl_pos, encoding="utf-8"))
    model = dict(
        vowl=vowl,
        meta=dict(W=W, H=H, label=kg.kg["label"], triples=kg.triples, onto=kg.onto["version"],
                  modified=kg.kg["modified"], commit=a.commit[:7], commitDate=a.commit_date[:10],
                  built=datetime.date.today().isoformat()),
        tabs=tabs, bands=bands, nodes=list(b.nodes.values()), edges=b.edges, labels=b.labels, trunks=b.trunks,
        hl={d: b.highlight(d) for d in TAB_ORDER},
        panels=dict(all=p.overview_panel(), **{d: p.dataset_panel(d) for d in TAB_ORDER}),
    )
    assert int(kg.kg["void_triples"]) == kg.triples, "void:triples disagrees with the parsed graph"

    def palette(hexes, surface, a_):
        out = []
        for i, d in enumerate(TAB_ORDER):
            h = hexes[HUE[d]]
            out.append(f"--d{i + 1}:{h};--d{i + 1}t:{mix(h, surface, a_)};")
        return "".join(out)

    js = json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = open(a.template, encoding="utf-8").read()
    for key, val in (("/*__PALETTE_LIGHT__*/", palette(HEX_LIGHT, SURFACE_LIGHT, TINT_LIGHT)),
                     ("/*__PALETTE_SVG__*/", palette(HEX_LIGHT, "#ffffff", TINT_LIGHT)),
                     ("/*__PALETTE_DARK__*/", palette(HEX_DARK, SURFACE_DARK, TINT_DARK)),
                     ("/*__MODEL__*/", js), ("__ENTITIES_URL__", a.entities_url)):
        assert key in tpl, key
        tpl = tpl.replace(key, val)
    if a.standalone:
        from standalone import wrap
        tpl = wrap(tpl, f"CLEETS-KG dataset map: how each source dataset populates the CLEETS ontology, drawn in VOWL notation and as a schematic ({kg.triples:,} triples).")
    open(a.out, "w", encoding="utf-8").write(tpl)
    if a.json:
        json.dump(model, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {a.out}: {len(tpl):,} bytes, {len(b.nodes)} nodes, {len(b.edges)} edges, {len(b.labels)} labels")


if __name__ == "__main__":
    main()
