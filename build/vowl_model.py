#!/usr/bin/env python3
"""VOWL-style node-link model of CLEETS-KG: classes, properties, datatypes (the ontology, as
WebVOWL would draw it) plus the dataset records and derivations that populate it.

Everything here is read from the graph through kgmodel.KG; only the drawing conventions
(which kinds get which shape) are set by hand.
"""
import collections
import rdflib
from rdflib import RDF, RDFS, OWL, URIRef, BNode, Literal, Namespace

from kgmodel import C, DATA, DCT, PROV, SH, TIME, XSD

CLEETS_NS = str(C)


def n_(x):
    return f"{x:,}"


class VowlModel:
    def __init__(self, kg, tab_order, topic):
        self.kg = kg
        self.g = kg.g
        self.tab_order = tab_order
        self.topic = topic
        self.dsidx = {d: i + 1 for i, d in enumerate(tab_order)}
        self.nodes, self.links, self.info = [], [], {}
        self._classes()
        self._properties()
        self._class_axioms()
        self._data_layer()
        self._info()
        self.hl = {d: self._highlight(d) for d in tab_order}

    # ---------- helpers ---------------------------------------------------------
    def short(self, curie):
        return curie[len("cleets:"):] if curie.startswith("cleets:") else curie

    def add_node(self, id, kind, **kw):
        n = dict(id=id, kind=kind, **kw)
        self.nodes.append(n)
        return n

    def add_link(self, id, s, t, kind, **kw):
        l = dict(id=id, s=s, t=t, kind=kind, **kw)
        self.links.append(l)
        return l

    def restrictions(self, cls):
        """Anonymous superclasses of a class, rendered as short OWL-like phrases."""
        g = self.g
        out = []
        for sup in g.objects(cls, RDFS.subClassOf):
            if not isinstance(sup, BNode) or (sup, RDF.type, OWL.Restriction) not in g:
                continue
            p = self.kg.curie(g.value(sup, OWL.onProperty))
            if g.value(sup, OWL.qualifiedCardinality) is not None:
                n = str(g.value(sup, OWL.qualifiedCardinality))
                on = g.value(sup, OWL.onClass) or g.value(sup, OWL.onDataRange)
                out.append(f"{p} exactly {n} {self.kg.curie(on)}")
            elif g.value(sup, OWL.hasValue) is not None:
                out.append(f"{p} value {self.kg.curie(g.value(sup, OWL.hasValue))}")
            elif g.value(sup, OWL.someValuesFrom) is not None:
                sv = g.value(sup, OWL.someValuesFrom)
                members = []
                lst = g.value(sv, OWL.oneOf) if isinstance(sv, BNode) else None
                while lst and lst != RDF.nil:
                    members.append(self.kg.curie(g.value(lst, RDF.first)))
                    lst = g.value(lst, RDF.rest)
                out.append(f"{p} some {{ {', '.join(members)} }}" if members else f"{p} some {self.kg.curie(sv)}")
        return out

    # ---------- classes ------------------------------------------------------------
    def _classes(self):
        kg = self.kg
        self.cls_node = {}
        for cid, c in kg.classes.items():
            if c["external"]:
                continue
            nid = "c:" + cid
            self.cls_node[cid] = nid
            self.add_node(nid, "class", label=c["label"] or c["local"], name=self.short(cid), curie=cid, iri=str(c["node"]),
                          equiv=c["equiv"], count=c["direct"])
        # external classes that are drawn as their own node (referenced by subClassOf, not merged by equivalence)
        self.ext_node = {}
        for cid, c in kg.classes.items():
            if not c["external"]:
                continue
            nid = "x:" + cid
            self.ext_node[cid] = nid
            self.add_node(nid, "external", label=c["local"], name=cid, curie=cid, iri=str(c["node"]), equiv=[], count=c["direct"])
        for cid, c in kg.classes.items():
            for sup in c["supers"]:
                if sup not in self.cls_node and sup not in self.ext_node:
                    self.ext_node[sup] = "x:" + sup
                    local = sup.split(":", 1)[1]
                    iri = str(self.g.namespace_manager.expand_curie(sup))
                    self.add_node("x:" + sup, "external", label=local, name=sup, curie=sup, iri=iri, equiv=[], count=0)

    def node_for_class(self, cid):
        return self.cls_node.get(cid) or self.ext_node.get(cid)

    # ---------- properties ---------------------------------------------------------
    def _properties(self):
        kg = self.kg
        self.thing_n = 0
        self.dt_n = 0
        for pid, p in kg.props.items():
            local = self.short(pid)
            dom = self.node_for_class(p["domain"]) if p["domain"] else None
            if dom is None:
                self.thing_n += 1
                dom = f"thing:{self.thing_n}"
                self.add_node(dom, "thing", label="Thing", name="owl:Thing", curie="owl:Thing",
                              iri="http://www.w3.org/2002/07/owl#Thing", equiv=[], count=0, forProp=pid, end="domain")
            equiv = [self.kg.curie(o) for o in sorted(self.g.objects(p["node"], OWL.equivalentProperty), key=str)]
            supers = [self.kg.curie(o) for o in sorted(self.g.objects(p["node"], RDFS.subPropertyOf), key=str)]
            sub = "functional" if p["functional"] else ""
            if p["kind"] == "object":
                rng = self.node_for_class(p["range"]) if p["range"] else None
                if rng is None:
                    self.thing_n += 1
                    rng = f"thing:{self.thing_n}"
                    self.add_node(rng, "thing", label="Thing", name="owl:Thing", curie="owl:Thing",
                                  iri="http://www.w3.org/2002/07/owl#Thing", equiv=[], count=0, forProp=pid, end="range")
                self.add_link("p:" + pid, dom, rng, "object", label=p["label"] or local, name=local, curie=pid, iri=str(p["node"]),
                              sub=sub, equiv=equiv, supers=supers, uses=p["uses"])
            else:
                self.dt_n += 1
                dtid = f"dt:{pid}"
                rng_text = p["range"]
                if rng_text is None:
                    self.add_node(dtid, "literal", label="Literal", name="rdfs:Literal", curie="rdfs:Literal",
                                  iri="http://www.w3.org/2000/01/rdf-schema#Literal", equiv=[], count=0, forProp=pid)
                else:
                    base = rng_text.split(" [")[0]
                    self.add_node(dtid, "datatype", label=base, name=base, curie=base, iri=str(self.g.namespace_manager.expand_curie(base)),
                                  equiv=[], count=0, forProp=pid, restriction=(rng_text if " [" in rng_text else None))
                self.add_link("p:" + pid, dom, dtid, "datatype", label=p["label"] or local, name=local, curie=pid, iri=str(p["node"]),
                              sub=sub, equiv=equiv, supers=supers, uses=p["uses"])

    # ---------- subclass, disjointness -------------------------------------------
    def _class_axioms(self):
        kg, g = self.kg, self.g
        for cid, c in kg.classes.items():
            if c["external"]:
                continue
            for sup in c["supers"]:
                self.add_link(f"sub:{cid}>{sup}", self.cls_node[cid], self.node_for_class(sup), "subclass", label="Subclass of",
                              name="rdfs:subClassOf", curie="rdfs:subClassOf")
        pairs = set()
        for s, o in g.subject_objects(OWL.disjointWith):
            pairs.add(tuple(sorted((kg.curie(s), kg.curie(o)))))
        for ad in g.subjects(RDF.type, OWL.AllDisjointClasses):
            members, lst = [], g.value(ad, OWL.members)
            while lst and lst != RDF.nil:
                members.append(kg.curie(g.value(lst, RDF.first)))
                lst = g.value(lst, RDF.rest)
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    pairs.add(tuple(sorted((members[i], members[j]))))
        self.disjoint_pairs = sorted(pairs)
        for a, b in self.disjoint_pairs:
            self.add_link(f"dj:{a}|{b}", self.cls_node[a], self.cls_node[b], "disjoint", label="", name="owl:disjointWith", curie="owl:disjointWith",
                          via="owl:disjointWith" if (URIRef(str(g.namespace_manager.expand_curie(a))), OWL.disjointWith, None) in g
                              or (URIRef(str(g.namespace_manager.expand_curie(b))), OWL.disjointWith, None) in g else "owl:AllDisjointClasses")

    # ---------- the data layer: datasets and derivations --------------------------
    def _data_layer(self):
        kg, g = self.kg, self.g
        for did in self.tab_order:
            d = kg.datasets[did]
            self.add_node("ds:" + did, "dataset", label=did, name=did, curie=did, iri=d["iri"], equiv=[], count=0,
                          ds=self.dsidx[did], sub=self.topic[did])
        act_node = {}
        for aid, a in kg.activities.items():
            act_node[aid] = "act:" + aid
            self.add_node("act:" + aid, "activity", label=a["label"], name=aid, curie=a["curie"], iri=str(a["node"]), equiv=[], count=0)
            for did in a["used"]:
                self.add_link(f"used:{aid}>{did}", "act:" + aid, "ds:" + did, "used", label="prov:used", name="prov:used", curie="prov:used", ds=self.dsidx[did])
        # individuals typed with a CLEETS class, grouped by (class, dataset); the series each count belongs to is kept for the tooltip
        cite = collections.defaultdict(lambda: collections.Counter())
        gen = collections.defaultdict(lambda: collections.Counter())
        for gid, gr in kg.groups.items():
            if not gr["sources"] and not gr.get("activity"):
                continue
            for tc in gr["types"]:
                if tc not in self.cls_node:
                    continue
                for did in gr["sources"]:
                    cite[(tc, did)][gid] += gr["count"]
                if gr.get("activity"):
                    gen[(tc, gr["activity"])][gid] += gr["count"]
        self.cite = cite
        for (tc, did), per in sorted(cite.items()):
            total = sum(per.values())
            self.add_link(f"src:{tc}>{did}", self.cls_node[tc], "ds:" + did, "source", label="dcterms:source", name="dcterms:source",
                          curie="dcterms:source", ds=self.dsidx[did], n=total, series=dict(per))
        for (tc, aid), per in sorted(gen.items()):
            total = sum(per.values())
            self.add_link(f"gen:{tc}>{aid}", self.cls_node[tc], act_node[aid], "generated", label="prov:wasGeneratedBy", name="prov:wasGeneratedBy",
                          curie="prov:wasGeneratedBy", n=total, series=dict(per))

    # ---------- details for the side panel ---------------------------------------
    def _info(self):
        kg, g = self.kg, self.g
        by_id = {n["id"]: n for n in self.nodes}
        subs = collections.defaultdict(list)
        for l in self.links:
            if l["kind"] == "subclass":
                subs[l["t"]].append(l["s"])
        groups_by_class = collections.defaultdict(list)
        for gid, gr in kg.groups.items():
            for tc in gr["types"]:
                groups_by_class[tc].append(gr)

        def ref(nid):
            n = by_id[nid]
            return dict(id=nid, text=n["name"] if n["kind"] in ("dataset", "activity") else (n["curie"] if n["kind"] != "thing" else "owl:Thing"))

        for n in self.nodes:
            i = dict(k="", t=n.get("curie") or n["name"], label=n["label"], iri=n.get("iri"), rows=[], lists=[], comment=None)
            if n["kind"] in ("class", "external"):
                c = kg.classes.get(n["curie"])
                i["k"] = "External class (owl:Class)" if n["kind"] == "external" else "Class (owl:Class)"
                if c:
                    i["comment"] = c["comment"]
                    if c["equiv"]:
                        i["rows"].append(["Equivalent to", ", ".join(c["equiv"])])
                    if c["rationale"]:
                        i["rows"].append(["Mapping rationale", c["rationale"]])
                    if c["defined"]:
                        i["rows"].append(["Defined by", c["defined"]])
                    i["rows"].append(["Individuals", f"{n_(c['direct'])} typed with this class directly"])
                    allc = {c["node"]} | {x["node"] for x in kg.classes.values() if c["curie"] in [kg.curie(s) for s in kg.superclasses(x["node"])]}
                    total = sum(kg.classes[kg.curie(x)]["direct"] for x in allc)
                    if total != c["direct"]:
                        i["rows"].append(["With subclasses", n_(total)])
                    rs = self.restrictions(c["node"])
                    if rs:
                        i["lists"].append(dict(h="Restrictions on this class", items=[dict(text=r) for r in rs]))
                    sup = [self.node_for_class(s) for s in c["supers"]]
                    if sup:
                        i["lists"].append(dict(h="Superclasses", items=[ref(s) for s in sup]))
                if subs.get(n["id"]):
                    i["lists"].append(dict(h="Subclasses", items=[ref(s) for s in sorted(subs[n["id"]])]))
                dom = [l for l in self.links if l["kind"] in ("object", "datatype") and l["s"] == n["id"]]
                rng = [l for l in self.links if l["kind"] == "object" and l["t"] == n["id"]]
                if dom:
                    i["lists"].append(dict(h="Properties with this domain", items=[dict(id=l["id"], text=l["curie"]) for l in dom]))
                if rng:
                    i["lists"].append(dict(h="Properties with this range", items=[dict(id=l["id"], text=l["curie"]) for l in rng]))
                if n["curie"] == "cleets:ObservableProperty":
                    i["lists"].append(dict(h="Named individuals", items=[dict(text=o["curie"] + (f" ({n_(o['observed_by'])} observations)" if o["observed_by"] else " (not used)"))
                                                                        for o in kg.obsprops.values()]))
                srs = groups_by_class.get(n["curie"], [])
                if srs:
                    items = []
                    for gr in sorted(srs, key=lambda x: -x["count"]):
                        src = " and ".join(gr["sources"]) if gr["sources"] else "no dataset"
                        items.append(dict(text=f"{gr['id']}: {n_(gr['count'])} (source {src})"))
                    i["lists"].append(dict(h="Individuals by series", items=items))
                shapes = [s for s, targets in kg.shapes.items() if n["curie"] in targets]
                if shapes:
                    i["lists"].append(dict(h="SHACL shapes targeting this class", items=[dict(text=s) for s in shapes]))
            elif n["kind"] == "thing":
                i["k"] = "owl:Thing"
                i["t"] = "owl:Thing"
                i["comment"] = (f"Stands in for the missing rdfs:{n['end']} of {n['forProp']}. WebVOWL attaches every property end "
                                f"that has no declared domain or range to its own owl:Thing node.")
            elif n["kind"] in ("datatype", "literal"):
                i["k"] = "Datatype (rdfs:Datatype)" if n["kind"] == "datatype" else "rdfs:Literal"
                p = kg.props[n["forProp"]]
                i["rows"].append(["Range of", n["forProp"]])
                if n.get("restriction"):
                    i["rows"].append(["Declared range", n["restriction"]])
                if n["kind"] == "literal":
                    i["comment"] = f"{n['forProp']} declares no rdfs:range, so its values are plain literals here."
            elif n["kind"] == "dataset":
                d = kg.datasets[n["name"]]
                i["k"] = "Dataset record (dcat:Dataset, prov:Entity)"
                i["t"] = n["name"]
                i["label"] = d["title"]
                i["comment"] = d["comment"] or d["description"]
                i["rows"] += [["Publisher", d["publisher"]]]
                if d["start"]:
                    i["rows"].append(["Coverage in the record", f"{d['start']} to {d['end']}" + (f", {d['spatial']}" if d["spatial"] else "")])
                cited = [(tc, per) for (tc, did), per in self.cite.items() if did == n["name"]]
                if cited:
                    items = []
                    for tc, per in sorted(cited):
                        items.append(dict(id=self.cls_node[tc], text=f"{tc}: " + ", ".join(f"{gid} {n_(c)}" for gid, c in sorted(per.items()))))
                    i["lists"].append(dict(h="Cited with dcterms:source by", items=items))
                used = [a for a in kg.activities.values() if n["name"] in a["used"]]
                if used:
                    i["lists"].append(dict(h="Input to", items=[dict(id="act:" + a["id"], text=a["label"]) for a in used]))
                i["links"] = [["Landing page", d["landing"]]] if d["landing"] else []
            elif n["kind"] == "activity":
                a = kg.activities[n["name"]]
                i["k"] = "Derivation (prov:Activity)"
                i["t"] = a["curie"]
                i["comment"] = a["comment"]
                i["lists"].append(dict(h="Used", items=[dict(id="ds:" + d, text=d) for d in a["used"]]))
                outs = [l for l in self.links if l["kind"] == "generated" and l["t"] == n["id"]]
                i["lists"].append(dict(h="Generated", items=[dict(id=l["s"], text=f"{by_id[l['s']]['curie']}: " + ", ".join(f"{gid} {n_(c)}" for gid, c in sorted(l["series"].items()))) for l in outs]))
            self.info[n["id"]] = i

        for l in self.links:
            i = dict(k="", t=l["curie"], label=l.get("label") or "", iri=l.get("iri"), rows=[], lists=[], comment=None)
            if l["kind"] in ("object", "datatype"):
                p = kg.props[l["curie"]]
                i["k"] = "Object property (owl:ObjectProperty)" if l["kind"] == "object" else "Datatype property (owl:DatatypeProperty)"
                i["comment"] = p["comment"]
                i["rows"].append(["Domain", p["domain"] or "not declared (drawn from owl:Thing)"])
                i["rows"].append(["Range", p["range"] or ("not declared (drawn to owl:Thing)" if l["kind"] == "object" else "not declared (drawn to rdfs:Literal)")])
                if p["functional"]:
                    i["rows"].append(["Characteristics", "functional"])
                if l["equiv"]:
                    i["rows"].append(["Equivalent to", ", ".join(l["equiv"])])
                if l["supers"]:
                    i["rows"].append(["Subproperty of", ", ".join(l["supers"])])
                subp = [kg.curie(s) for s in sorted(g.subjects(RDFS.subPropertyOf, p["node"]), key=str)]
                if subp:
                    i["rows"].append(["Superproperty of", ", ".join(subp)])
                if p["rationale"]:
                    i["rows"].append(["Mapping rationale", p["rationale"]])
                i["rows"].append(["Triples in the graph", n_(p["uses"]) if p["uses"] else "none"])
            elif l["kind"] == "subclass":
                i["k"] = "rdfs:subClassOf"
                i["t"] = f"{by_id[l['s']]['curie']} ⊑ {by_id[l['t']]['curie']}"
                c = kg.classes[by_id[l["s"]]["curie"]]
                if c["rationale"]:
                    i["comment"] = c["rationale"]
            elif l["kind"] == "disjoint":
                i["k"] = l["via"]
                i["t"] = f"{by_id[l['s']]['curie']} disjoint with {by_id[l['t']]['curie']}"
                i["comment"] = ("Stated with owl:disjointWith." if l["via"] == "owl:disjointWith"
                                else "Stated once for all four observation subclasses with owl:AllDisjointClasses.")
            elif l["kind"] == "source":
                i["k"] = "dcterms:source"
                i["t"] = f"{by_id[l['s']]['curie']} → {by_id[l['t']]['name']}"
                i["rows"].append(["Individuals", n_(l["n"])])
                i["lists"].append(dict(h="By series", items=[dict(text=f"{gid}: {n_(c)}") for gid, c in sorted(l["series"].items())]))
                i["comment"] = "Each of these individuals carries this dataset record as its dcterms:source."
            elif l["kind"] == "used":
                i["k"] = "prov:used"
                i["t"] = f"{kg.activities[l['s'][4:]]['label']} → {by_id[l['t']]['name']}"
            elif l["kind"] == "generated":
                i["k"] = "prov:wasGeneratedBy"
                i["t"] = f"{by_id[l['s']]['curie']} → {kg.activities[l['t'][4:]]['label']}"
                i["rows"].append(["Individuals", n_(l["n"])])
                i["lists"].append(dict(h="By series", items=[dict(text=f"{gid}: {n_(c)}") for gid, c in sorted(l["series"].items())]))
            self.info[l["id"]] = i

    # ---------- highlight sets per dataset ----------------------------------------
    def _highlight(self, did):
        kg = self.kg
        by_id = {n["id"]: n for n in self.nodes}
        links_from = collections.defaultdict(list)
        links_to = collections.defaultdict(list)
        for l in self.links:
            links_from[l["s"]].append(l)
            links_to[l["t"]].append(l)
        on, ctx = set(), set()
        dsn = "ds:" + did
        on.add(dsn)
        core_classes = set()
        for l in links_to[dsn]:
            if l["kind"] == "source":
                on.update((l["id"], l["s"]))
                core_classes.add(l["s"])
            elif l["kind"] == "used":
                act = l["s"]
                on.update((l["id"], act))
                for l2 in links_from[act]:
                    if l2["kind"] == "used":
                        on.update((l2["id"], l2["t"]))
                for l2 in links_to[act]:
                    if l2["kind"] == "generated":
                        on.update((l2["id"], l2["s"]))
                        core_classes.add(l2["s"])

        def ancestors(cid, acc):
            """the class, its superclasses and the subclass links between them"""
            acc.add(cid)
            for l in links_from[cid]:
                if l["kind"] == "subclass" and l["id"] not in acc:
                    acc.add(l["id"])
                    ancestors(l["t"], acc)

        scope = set()
        for cid in core_classes:
            ancestors(cid, scope)
        on |= scope
        for cid in [x for x in scope if not x.startswith("sub:")]:
            for l in links_from[cid]:
                if l["kind"] in ("object", "datatype"):
                    on.update((l["id"], l["t"]))
                    if l["kind"] == "object":
                        ancestors(l["t"], on)
        # the subclasses that actually receive the instance-level links (districts, quarters)
        for cid in list(core_classes):
            for gr in kg.groups.values():
                if ("c:" + t for t in gr["types"]) and cid in ["c:" + t for t in gr["types"]]:
                    for t in gr.get("lad_types", []) + gr.get("time_types", []):
                        nid = self.cls_node.get(t)
                        if nid and nid not in on:
                            ctx.add(nid)
                            for l in links_from[nid]:
                                if l["kind"] == "subclass" and l["t"] in on:
                                    ctx.add(l["id"])
        # a dataset reached through a derivation partner stays "on"; everything else fades
        ctx -= on
        return dict(on=sorted(on), ctx=sorted(ctx))

    def as_dict(self):
        return dict(nodes=self.nodes, links=self.links, info=self.info, hl=self.hl,
                    stats=dict(classes=sum(1 for n in self.nodes if n["kind"] == "class"),
                               external=sum(1 for n in self.nodes if n["kind"] == "external"),
                               objectProps=sum(1 for l in self.links if l["kind"] == "object"),
                               datatypeProps=sum(1 for l in self.links if l["kind"] == "datatype"),
                               subclass=sum(1 for l in self.links if l["kind"] == "subclass"),
                               disjoint=sum(1 for l in self.links if l["kind"] == "disjoint"),
                               things=sum(1 for n in self.nodes if n["kind"] == "thing"),
                               datasets=sum(1 for n in self.nodes if n["kind"] == "dataset"),
                               activities=sum(1 for n in self.nodes if n["kind"] == "activity"),
                               individuals=sum(c["direct"] for c in self.kg.classes.values())))
