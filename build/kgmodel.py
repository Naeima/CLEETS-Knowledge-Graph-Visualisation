#!/usr/bin/env python3
"""Extract a schema-level model of CLEETS-KG from its Turtle source.

Everything the page shows (counts, coverage, chains, examples) is computed here
from the graph. Nothing is typed in by hand except short presentational labels.
"""
import re
import collections
import rdflib
from rdflib import RDF, RDFS, OWL, URIRef, BNode, Literal, Namespace

C = Namespace("https://w3id.org/def/cleets#")
DATA = Namespace("https://w3id.org/def/cleets/data#")
SH = Namespace("http://www.w3.org/ns/shacl#")
DCT = Namespace("http://purl.org/dc/terms/")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
PROV = Namespace("http://www.w3.org/ns/prov#")
VOID = Namespace("http://rdfs.org/ns/void#")
TIME = Namespace("http://www.w3.org/2006/time#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")

LOCAL_OK = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*\Z")


class KG:
    def __init__(self, path):
        self.g = g = rdflib.Graph()
        g.parse(path, format="turtle")
        self.prefixes = sorted(
            [(str(ns), p) for p, ns in g.namespaces() if p], key=lambda t: -len(t[0])
        )
        self._extract()

    # ---------- helpers -------------------------------------------------
    def curie(self, u):
        s = str(u)
        for ns, p in self.prefixes:
            if s.startswith(ns):
                local = s[len(ns):]
                if LOCAL_OK.match(local or ""):
                    return f"{p}:{local}"
        return f"<{s}>"

    def local(self, u):
        s = str(u)
        return re.split(r"[#/]", s)[-1]

    def lit(self, s, p, default=None):
        v = self.g.value(s, p)
        return str(v) if v is not None else default

    def lits(self, s, p):
        return sorted(str(o) for o in self.g.objects(s, p))

    def term(self, o):
        """Turtle rendering of one object term."""
        if isinstance(o, URIRef):
            return self.curie(o)
        if isinstance(o, BNode):
            return "[ ... ]"
        text = str(o).replace("\\", "\\\\").replace('"', '\\"')
        if o.language:
            return f'"{text}"@{o.language}'
        if o.datatype and o.datatype != XSD.string:
            return f'"{text}"^^{self.curie(o.datatype)}'
        return f'"{text}"'

    def turtle(self, s, cap=None):
        """Predicate-object list for one subject, rdf:type first.

        cap maps a predicate CURIE to the number of objects to print; the
        remainder is reported in a comment line so nothing is silently dropped.
        """
        g = self.g
        cap = cap or {}
        by = collections.defaultdict(list)
        for p, o in g.predicate_objects(s):
            by[p].append(o)
        order = sorted(by, key=lambda p: (p != RDF.type, self.curie(p)))
        lines = []
        for p in order:
            pc = "a" if p == RDF.type else self.curie(p)
            objs = sorted(by[p], key=lambda o: self.term(o))
            limit = cap.get(pc)
            shown = objs if limit is None else objs[:limit]
            terms = [self.term(o) for o in shown]
            one_line = ", ".join(terms)
            txt = one_line if len(pc) + len(one_line) <= 74 or len(terms) == 1 else (",\n        ".join(terms))
            lines.append((pc, txt, len(objs) - len(shown)))
        out = [self.curie(s)]
        for i, (pc, txt, more) in enumerate(lines):
            end = " ." if i == len(lines) - 1 else " ;"
            sep = "\n        " if "\n" in txt else " "
            out.append(f"    {pc}{sep}{txt}{end}")
            if more:
                out.append(f"    # ... and {more} more {pc} values")
        return "\n".join(out)

    def superclasses(self, c):
        """Named superclasses, nearest first (transitive)."""
        out, seen, frontier = [], {c}, [c]
        while frontier:
            nxt = []
            for x in frontier:
                for sup in sorted(self.g.objects(x, RDFS.subClassOf), key=str):
                    if isinstance(sup, URIRef) and sup not in seen:
                        seen.add(sup)
                        out.append(sup)
                        nxt.append(sup)
            frontier = nxt
        return out

    def class_chain(self, c):
        """e.g. cleets:EVKeepership ⊑ cleets:Observation ≡ sosa:Observation"""
        g = self.g
        parts = [self.curie(c)]
        cur = c
        guard = 0
        while guard < 8:
            guard += 1
            eq = sorted((o for o in g.objects(cur, OWL.equivalentClass) if isinstance(o, URIRef)), key=str)
            for e in eq:
                parts.append("≡ " + self.curie(e))
            sup = sorted((o for o in g.objects(cur, RDFS.subClassOf) if isinstance(o, URIRef)), key=str)
            if not sup:
                break
            cur = sup[0]
            parts.append("⊑ " + self.curie(cur))
        return " ".join(parts)

    def prop_chain(self, p):
        g = self.g
        parts = [self.curie(p)]
        cur = p
        guard = 0
        while guard < 8:
            guard += 1
            for e in sorted((o for o in g.objects(cur, OWL.equivalentProperty) if isinstance(o, URIRef)), key=str):
                parts.append("≡ " + self.curie(e))
            sup = sorted((o for o in g.objects(cur, RDFS.subPropertyOf) if isinstance(o, URIRef)), key=str)
            if not sup:
                break
            cur = sup[0]
            parts.append("⊑ " + self.curie(cur))
        return " ".join(parts)

    def range_text(self, p):
        g = self.g
        r = g.value(p, RDFS.range)
        if r is None:
            return None
        if isinstance(r, URIRef):
            return self.curie(r)
        base = g.value(r, OWL.onDatatype)
        lo = hi = None
        lst = g.value(r, OWL.withRestrictions)
        while lst and lst != RDF.nil:
            item = g.value(lst, RDF.first)
            lo = g.value(item, XSD.minInclusive) if g.value(item, XSD.minInclusive) is not None else lo
            hi = g.value(item, XSD.maxInclusive) if g.value(item, XSD.maxInclusive) is not None else hi
            lst = g.value(lst, RDF.rest)
        if base is not None:
            return f"{self.curie(base)} [{lo} to {hi}]"
        return "(anonymous range)"

    def shapes_for(self, classes):
        """SHACL node shapes whose sh:targetClass is one of the given classes."""
        out = []
        for shp in sorted(set(self.g.subjects(RDF.type, SH.NodeShape)), key=str):
            targets = set(self.g.objects(shp, SH.targetClass))
            if targets & set(classes):
                out.append(self.curie(shp))
        return out

    # ---------- extraction ----------------------------------------------
    def _extract(self):
        g = self.g
        self.triples = len(g)

        # the graph's own dataset record
        kg = [s for s in g.subjects(RDF.type, VOID.Dataset)]
        assert len(kg) == 1, "expected exactly one void:Dataset record"
        self.kg_iri = kg[0]
        self.kg = dict(
            label=self.lit(kg[0], RDFS.label),
            title=self.lit(kg[0], DCT.title),
            version=self.lit(kg[0], DCT.hasVersion),
            issued=self.lit(kg[0], DCT.issued),
            modified=self.lit(kg[0], DCT.modified),
            license=self.lit(kg[0], DCT.license),
            publisher=self.lit(kg[0], DCT.publisher),
            citation=self.lit(kg[0], DCT.bibliographicCitation),
            void_triples=self.lit(kg[0], VOID.triples),
            sources=sorted(self.local(o) for o in g.objects(kg[0], DCT.source)),
            rights=self.lit(kg[0], DCT.rights),
        )
        onto = list(g.subjects(RDF.type, OWL.Ontology))
        assert len(onto) == 1
        self.onto_iri = onto[0]
        self.onto = dict(
            title=self.lit(onto[0], DCT.title),
            version=self.lit(onto[0], OWL.versionInfo),
            citation=self.lit(onto[0], DCT.bibliographicCitation),
            imports=sorted(str(o) for o in g.objects(onto[0], OWL.imports)),
            license=self.lit(onto[0], DCT.license),
        )

        # source dataset records
        self.datasets = {}
        for s in sorted(set(g.subjects(RDF.type, DCAT.Dataset)), key=str):
            if s == self.kg_iri:
                continue
            ident = self.lit(s, DCT.identifier) or self.local(s)
            per = g.value(s, DCT.temporal)
            dist = g.value(s, DCAT.distribution)
            ser = g.value(s, DCAT.inSeries)
            self.datasets[ident] = dict(
                id=ident, iri=str(s), node=s,
                title=self.lit(s, DCT.title),
                alt=self.lit(s, DCT.alternative),
                publisher=self.lit(s, DCT.publisher),
                agents=sorted(self.lit(a, RDFS.label) or self.local(a) for a in g.objects(s, PROV.wasAttributedTo)),
                license=self.lit(s, DCT.license),
                landing=self.lit(s, DCAT.landingPage),
                access=self.lit(dist, DCAT.accessURL) if dist is not None else None,
                start=self.lit(per, DCAT.startDate) if per is not None else None,
                end=self.lit(per, DCAT.endDate) if per is not None else None,
                spatial=self.lit(s, DCT.spatial),
                citation=self.lit(s, DCT.bibliographicCitation),
                comment=self.lit(s, RDFS.comment),
                description=self.lit(s, DCT.description),
                provenance=self.lit(s, DCT.provenance),
                series=self.lit(ser, DCT.title) if ser is not None else None,
                issued=self.lit(s, DCT.issued),
                partition=sorted(self.curie(c) for bn in g.objects(s, VOID.classPartition) for c in g.objects(bn, VOID["class"])),
            )
        self.ds_by_node = {d["node"]: k for k, d in self.datasets.items()}

        # derivation activities (prov:Activity with prov:used)
        self.activities = {}
        for a in sorted(set(g.subjects(RDF.type, PROV.Activity)), key=str):
            used = sorted(self.ds_by_node[o] for o in g.objects(a, PROV.used) if o in self.ds_by_node)
            if not used:
                continue
            self.activities[self.local(a)] = dict(
                id=self.local(a), node=a, curie=self.curie(a), label=self.lit(a, RDFS.label),
                comment=self.lit(a, RDFS.comment), used=used,
                see=sorted(self.curie(o) for o in g.objects(a, RDFS.seeAlso)),
            )
        self.other_activities = [
            dict(curie=self.curie(a), label=self.lit(a, RDFS.label), comment=self.lit(a, RDFS.comment))
            for a in sorted(set(g.subjects(RDF.type, PROV.Activity)), key=str)
            if self.local(a) not in self.activities
        ]
        act_by_node = {a["node"]: k for k, a in self.activities.items()}

        dt_props = set(g.subjects(RDF.type, OWL.DatatypeProperty))
        self.groups = {}
        covered = set()

        def value_props(members):
            """CLEETS datatype properties used by the members, with literal datatypes."""
            found = collections.OrderedDict()
            for s in members:
                for p, o in g.predicate_objects(s):
                    if p in dt_props and isinstance(o, Literal):
                        found.setdefault(p, set()).add(o.datatype)
            return [dict(prop=self.curie(p), dts=sorted(self.curie(d) if d is not None else "xsd:string" for d in dts),
                         chain=self.prop_chain(p), node=p) for p, dts in sorted(found.items(), key=lambda t: str(t[0]))]

        def pick_example(members):
            pref = [s for s in members if "W06000015" in str(s)]
            pool = pref or list(members)
            return sorted(pool, key=str)[-1]

        # 1. observation series: individuals with cleets:forLAD, grouped by type set and observed property
        buckets = collections.defaultdict(list)
        for s in set(g.subjects(C.forLAD, None)):
            key = (tuple(sorted(str(t) for t in g.objects(s, RDF.type))), str(g.value(s, C.observesProperty)))
            buckets[key].append(s)
        for (types, op), members in sorted(buckets.items()):
            stems = {self.local(s).split("_")[0] for s in members}
            assert len(stems) == 1, f"mixed IRI stems in one series: {stems}"
            name = stems.pop()
            lads = {g.value(s, C.forLAD) for s in members}
            times = {g.value(s, C.forTime) for s in members}
            keys = {(g.value(s, C.forLAD), g.value(s, C.forTime)) for s in members}
            srcs = sorted({self.ds_by_node[o] for s in members for o in g.objects(s, DCT.source) if o in self.ds_by_node})
            der = sorted({self.ds_by_node[o] for s in members for o in g.objects(s, PROV.wasDerivedFrom) if o in self.ds_by_node})
            fps = sum(1 for s in members for o in g.objects(s, PROV.wasDerivedFrom) if o not in self.ds_by_node)
            gen = sorted({act_by_node[o] for s in members for o in g.objects(s, PROV.wasGeneratedBy) if o in act_by_node})
            assert len(gen) <= 1
            tlabels = sorted(self.lit(t, RDFS.label) for t in times)
            ttypes = sorted({self.curie(t) for x in times for t in g.objects(x, RDF.type)})
            ladtypes = sorted({self.curie(t) for x in lads for t in g.objects(x, RDF.type)})
            self.groups[name] = dict(
                id=name, kind="series", members=members, count=len(members),
                types=[self.curie(URIRef(t)) for t in types], type_nodes=[URIRef(t) for t in types],
                observes=self.curie(URIRef(op)), observes_node=URIRef(op),
                values=value_props(members), sources=srcs, derived_from=der, fingerprints=fps,
                activity=gen[0] if gen else None,
                lads=lads, times=times, keys=keys, complete=(len(keys) == len(lads) * len(times) == len(members)),
                t_first=tlabels[0], t_last=tlabels[-1], time_types=ttypes, lad_types=ladtypes,
                example=pick_example(members),
            )
            covered |= set(members)

        # 2. attribute nodes hung off districts (no cleets:forLAD of their own)
        for cls, name in ((C.Population, "Population"), (C.PopulationDensity, "PopulationDensity")):
            members = set(g.subjects(RDF.type, cls))
            assert members, f"no instances of {cls}"
            links = collections.Counter()
            owners = set()
            owner_types = collections.Counter()
            for s in members:
                for o, p in g.subject_predicates(s):
                    links[self.curie(p)] += 1
                    owners.add(o)
                    for t in g.objects(o, RDF.type):
                        owner_types[self.curie(t)] += 1
            assert len(links) == 1, f"{name}: expected one linking property, got {links}"
            dates = sorted({str(g.value(s, DCT.date)) for s in members})
            srcs = sorted({self.ds_by_node[o] for s in members for o in g.objects(s, DCT.source) if o in self.ds_by_node})
            self.groups[name] = dict(
                id=name, kind="attr", members=members, count=len(members),
                types=[self.curie(cls)], type_nodes=[cls], values=value_props(members), sources=srcs,
                link_prop=list(links)[0], link_node=[p for p in g.predicates(None, pick_example(members))][0],
                owners=owners, owner_types=dict(owner_types), dates=dates,
                owner_counts={self.curie(t): len({o for o in owners if (o, RDF.type, t) in g})
                              for t in sorted({t for o in owners for t in g.objects(o, RDF.type)}, key=str)},
                lads=owners, times=set(), keys=set(),
                complete=(len(members) == len(owners) * len(dates)),
                example=pick_example(members), activity=None, derived_from=[], fingerprints=0,
            )
            covered |= members

        # 3. district individuals
        for cls, name in ((C.WelshLAD, "WelshLAD"), (C.EnglishLAD, "EnglishLAD")):
            members = set(g.subjects(RDF.type, cls))
            codes = sorted(str(g.value(s, C.ladCode)) for s in members)
            srcs = sorted({self.ds_by_node[o] for s in members for o in g.objects(s, DCT.source) if o in self.ds_by_node})
            see = sorted({re.sub(r"^(https?://[^/]+)/.*$", r"\1", str(o)) for s in members for o in g.objects(s, RDFS.seeAlso)})
            labels_lead_space = sum(1 for s in members if (self.lit(s, RDFS.label) or "").startswith(" "))
            self.groups[name] = dict(
                id=name, kind="lad", members=members, count=len(members), types=[self.curie(cls)], type_nodes=[cls],
                values=value_props(members), sources=srcs, codes=(codes[0], codes[-1]), see=see,
                code_prefixes=sorted({c[:3] for c in codes}),
                lads=members, times=set(), keys=set(), example=pick_example(members), activity=None,
                derived_from=[], fingerprints=0, labels_lead_space=labels_lead_space,
                obs_in=sum(1 for s in members for _ in g.subjects(C.forLAD, s)),
            )
            covered |= members

        # 4. time entities
        quarters = set(g.subjects(RDF.type, C.Quarter))
        others = set(g.subjects(RDF.type, C.Time)) - quarters
        ql = sorted(self.lit(s, RDFS.label) for s in quarters)
        instants = sum(1 for s in quarters for p in (TIME.hasBeginning, TIME.hasEnd) for _ in g.objects(s, p))
        self.groups["Quarter"] = dict(
            id="Quarter", kind="time", members=quarters, count=len(quarters),
            types=sorted({self.curie(t) for s in quarters for t in g.objects(s, RDF.type)}),
            type_nodes=sorted({t for s in quarters for t in g.objects(s, RDF.type)}, key=str),
            values=value_props(quarters), sources=[], first=ql[0], last=ql[-1], instants=instants,
            lads=set(), times=quarters, keys=set(), example=sorted(quarters, key=str)[-1], activity=None,
            derived_from=[], fingerprints=0,
            used=sum(1 for s in quarters if (None, C.forTime, s) in g),
        )
        assert others, "expected at least one non-quarter cleets:Time"
        self.groups["Time"] = dict(
            id="Time", kind="time", members=others, count=len(others),
            types=sorted({self.curie(t) for s in others for t in g.objects(s, RDF.type)}),
            type_nodes=sorted({t for s in others for t in g.objects(s, RDF.type)}, key=str),
            values=value_props(others), sources=[], names=sorted(self.curie(s) for s in others),
            lads=set(), times=others, keys=set(), example=sorted(others, key=str)[-1], activity=None,
            derived_from=[], fingerprints=0,
        )
        covered |= quarters | others

        # completeness check: every individual typed with a CLEETS class is in exactly one group
        cleets_classes = {c for c in g.subjects(RDF.type, OWL.Class) if str(c).startswith(str(C))}
        typed = {s for c in cleets_classes for s in g.subjects(RDF.type, c)}
        obsprops = set(g.subjects(RDF.type, C.ObservableProperty))
        missing = typed - covered - obsprops
        assert not missing, f"individuals not assigned to a group: {list(missing)[:5]}"
        sizes = sum(gr["count"] for gr in self.groups.values())
        assert sizes == len(covered), "an individual sits in two groups"

        # ontology terms
        self.classes = {}
        for c in sorted(set(g.subjects(RDF.type, OWL.Class)), key=str):
            if not isinstance(c, URIRef):
                continue
            self.classes[self.curie(c)] = dict(
                curie=self.curie(c), node=c, local=self.local(c), external=not str(c).startswith(str(C)),
                label=self.lit(c, RDFS.label), comment=self.lit(c, RDFS.comment),
                defined=self.lit(c, RDFS.isDefinedBy), rationale=self.lit(c, C.mappingRationale),
                supers=[self.curie(o) for o in sorted(g.objects(c, RDFS.subClassOf), key=str) if isinstance(o, URIRef)],
                equiv=[self.curie(o) for o in sorted(g.objects(c, OWL.equivalentClass), key=str) if isinstance(o, URIRef)],
                disjoint=[self.curie(o) for o in sorted(g.objects(c, OWL.disjointWith), key=str)],
                direct=len(set(g.subjects(RDF.type, c))), chain=self.class_chain(c),
            )
        self.props = {}
        for kind, t in (("object", OWL.ObjectProperty), ("datatype", OWL.DatatypeProperty)):
            for p in sorted(set(g.subjects(RDF.type, t)), key=str):
                dom = g.value(p, RDFS.domain)
                self.props[self.curie(p)] = dict(
                    curie=self.curie(p), node=p, kind=kind, label=self.lit(p, RDFS.label), comment=self.lit(p, RDFS.comment),
                    domain=self.curie(dom) if isinstance(dom, URIRef) else None, range=self.range_text(p),
                    chain=self.prop_chain(p), uses=len(list(g.triples((None, p, None)))),
                    functional=(p, RDF.type, OWL.FunctionalProperty) in g, defined=self.lit(p, RDFS.isDefinedBy),
                    rationale=self.lit(p, C.mappingRationale),
                )
        self.obsprops = {}
        for o in sorted(obsprops, key=str):
            self.obsprops[self.curie(o)] = dict(
                curie=self.curie(o), node=o, local=self.local(o), label=self.lit(o, RDFS.label), comment=self.lit(o, RDFS.comment),
                in_ontology=str(o).startswith(str(C)), observed_by=len(list(g.subjects(C.observesProperty, o))),
            )
        self.shapes = {self.curie(s): sorted(self.curie(t) for t in g.objects(s, SH.targetClass))
                       for s in sorted(set(g.subjects(RDF.type, SH.NodeShape)), key=str)}
        self.counts = dict(
            classes=sum(1 for c in self.classes.values() if not c["external"]),
            object_props=sum(1 for p in self.props.values() if p["kind"] == "object"),
            datatype_props=sum(1 for p in self.props.values() if p["kind"] == "datatype"),
            shapes=len(self.shapes),
            fingerprints=sum(gr["fingerprints"] for gr in self.groups.values()),
            observations=sum(gr["count"] for gr in self.groups.values() if gr["kind"] == "series"),
            labels=len(list(g.triples((None, RDFS.label, None)))),
            agents=len({s for s in g.subjects() if isinstance(s, URIRef) and str(s).startswith("https://w3id.org/def/cleets/agent#")}),
        )
