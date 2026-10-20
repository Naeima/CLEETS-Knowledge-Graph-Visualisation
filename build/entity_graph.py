#!/usr/bin/env python3
"""Instance-level graph of CLEETS-KG: every individual, blank node and external resource as a node,
every object triple between them as an edge, literals kept as attributes.

Only the TBox (classes, properties, shapes, the ontology header and their anonymous parts) is left out.
"""
import re
import hashlib
import collections
import rdflib
from rdflib import RDF, RDFS, OWL, URIRef, BNode, Literal, Namespace

from kgmodel import KG, C, DATA, DCT, PROV, SH, TIME, SKOS, XSD

VOID = Namespace("http://rdfs.org/ns/void#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
SCHEMA = Namespace("https://schema.org/")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")

TBOX_TYPES = {OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, OWL.FunctionalProperty,
              OWL.Ontology, OWL.Restriction, RDFS.Datatype, SH.NodeShape, SH.PropertyShape, OWL.AllDisjointClasses, OWL.AllDifferent}
SKIP_PREDICATES = {RDF.type, RDFS.isDefinedBy, RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range,
                   OWL.equivalentClass, OWL.equivalentProperty, DCT.conformsTo}


class EntityGraph:
    def __init__(self, kg):
        self.kg = kg
        self.g = kg.g
        self._collect()

    def curie(self, u):
        return self.kg.curie(u)

    def _collect(self):
        g = self.g
        # 1. subjects that are individuals: typed with something other than a TBox type, or untyped data IRIs
        subjects = set()
        for s in set(g.subjects()):
            types = set(g.objects(s, RDF.type))
            if types & TBOX_TYPES:
                continue
            if isinstance(s, BNode):
                if not types:
                    continue        # RDF lists, restrictions' parts, SHACL property shapes, void partitions
                subjects.add(s)
            elif isinstance(s, URIRef):
                if types:
                    subjects.add(s)
                elif str(s).startswith("https://w3id.org/def/cleets") and not str(s).startswith("https://w3id.org/def/cleets#") \
                        and not str(s).startswith("https://w3id.org/def/cleets/shapes"):
                    subjects.add(s)
        # 2. edges between subjects, and external resources they point to
        self.nodes = {}
        self.edges = []
        externals = set()
        for s in subjects:
            for p, o in g.predicate_objects(s):
                if p in SKIP_PREDICATES or isinstance(o, Literal):
                    continue
                if o in subjects:
                    self.edges.append((s, p, o))
                elif isinstance(o, URIRef):
                    u = str(o)
                    if u.startswith("https://w3id.org/def/cleets#") or u.startswith("https://w3id.org/def/cleets/shapes"):
                        continue    # a TBox term (class, property) or the ontology
                    if u == "https://w3id.org/def/cleets":
                        continue
                    externals.add(o)
                    self.edges.append((s, p, o))
        self.subjects = subjects
        self.externals = externals
        # rdflib gives blank nodes fresh identifiers on every parse; a digest of each one's triples gives a stable
        # name and a stable order, so that builds are reproducible and #_:... links keep working
        self.bkey = {}
        for n in subjects:
            if isinstance(n, BNode):
                self.bkey[n] = self._bnode_digest(n)
        seen = collections.Counter()
        for n in sorted((n for n in subjects if isinstance(n, BNode)), key=lambda n: self.bkey[n]):
            k = self.bkey[n]
            if seen[k]:
                self.bkey[n] = f"{k}-{seen[k]}"
            seen[k] += 1
        key = lambda n: (1, self.bkey[n]) if isinstance(n, BNode) else (0, str(n))
        order = sorted(subjects, key=key) + sorted(externals, key=str)
        self.index = {n: i for i, n in enumerate(order)}
        self.order = order

        # 3. attributes, types, labels, series, datasets per node
        self.literals = {}
        self.types = {}
        self.labels = {}
        self.sources = {}
        self.series = {}
        for n in order:
            lits = []
            for p, o in sorted(g.predicate_objects(n), key=lambda t: (str(t[0]), str(t[1]))):
                if isinstance(o, Literal):
                    v = str(o)
                    if o.datatype and o.datatype not in (XSD.string,):
                        v = f"{v} ({self.curie(o.datatype)})"
                    elif o.language:
                        v = f"{v} @{o.language}"
                    lits.append((self.curie(p), v))
            self.literals[n] = lits
            self.types[n] = [self.curie(t) for t in sorted(g.objects(n, RDF.type), key=str)]
            lab = g.value(n, RDFS.label) or g.value(n, SKOS.prefLabel) or g.value(n, SCHEMA.name) or g.value(n, FOAF.name) or g.value(n, DCT.title)
            self.labels[n] = str(lab).strip() if lab is not None else None
            self.sources[n] = sorted(str(o).split("/")[-1] for o in g.objects(n, DCT.source) if str(o).startswith("https://w3id.org/def/cleets/data#dataset/"))
            op = g.value(n, C.observesProperty)
            self.series[n] = self.kg.local(op).replace("Property", "") if op is not None else None

    def _bnode_digest(self, n, depth=0, seen=None):
        """A digest of a blank node's own triples (and, through nested blank nodes, theirs), independent of its identifier."""
        g = self.g
        seen = set(seen or ()) | {n}
        parts = []
        for p, o in g.predicate_objects(n):
            if isinstance(o, BNode):
                parts.append((str(p), self._bnode_digest(o, depth + 1, seen) if depth < 3 and o not in seen else "_"))
            else:
                parts.append((str(p), str(o)))
        for s, p in g.subject_predicates(n):
            if isinstance(s, BNode):
                parts.append(("^" + str(p), self._bnode_digest(s, depth + 1, seen) if depth < 3 and s not in seen else "_"))
            else:
                parts.append(("^" + str(p), str(s)))
        return hashlib.sha1(repr(sorted(parts)).encode("utf-8")).hexdigest()[:10]

    # ---------- presentation grouping ---------------------------------------------
    def kind_of(self, n):
        """A display type for colouring and the legend."""
        ts = set(self.types.get(n, []))
        if n in self.externals:
            return "External resource"
        if "cleets:EVKeepership" in ts: return "EVKeepership"
        if "cleets:EVChargerCount" in ts: return "EVChargerCount"
        if "cleets:AdoptionRatioObservation" in ts: return "KeepersPerCharger"
        if "cleets:IncomeDeprivation" in ts: return "IncomeDeprivation"
        if "cleets:Observation" in ts: return self.series.get(n) or "Observation"
        if "cleets:Population" in ts: return "Population"
        if "cleets:PopulationDensity" in ts: return "PopulationDensity"
        if "cleets:WelshLAD" in ts: return "WelshLAD"
        if "cleets:EnglishLAD" in ts: return "EnglishLAD"
        if "cleets:Quarter" in ts: return "Quarter"
        if "cleets:Time" in ts: return "Time"
        if "time:Instant" in ts: return "Instant"
        if "cleets:ObservableProperty" in ts: return "ObservableProperty"
        if "void:Dataset" in ts: return "Knowledge graph"
        if "dcat:Dataset" in ts: return "Dataset record"
        if "dcat:DatasetSeries" in ts: return "Dataset series"
        if "dcat:Distribution" in ts: return "Distribution"
        if "prov:Activity" in ts: return "Derivation"
        if "dcterms:PeriodOfTime" in ts: return "Period of time"
        if "schema:Person" in ts or "foaf:Person" in ts: return "Person"
        if ts & {"schema:Organization", "schema:GovernmentOrganization", "schema:CollegeOrUniversity", "prov:Agent"}: return "Organisation"
        if "schema:PostalAddress" in ts: return "Postal address"
        if "prov:Entity" in ts: return "Source-row fingerprint"
        return "Other"

    def display_label(self, n):
        if self.labels.get(n):
            return self.labels[n]
        if isinstance(n, BNode):
            lits = dict(self.literals.get(n, []))
            for k in ("time:inXSDDateTimeStamp", "dcat:startDate", "foaf:name", "schema:name", "schema:addressLocality"):
                if k in lits:
                    return lits[k].split(" (")[0]
            return "_:" + self.bkey[n][:6]
        s = str(n)
        if s.startswith("https://w3id.org/def/cleets#data/"):
            return s.split("#data/")[1]
        if s.startswith("https://w3id.org/def/cleets/data#dataset/"):
            return s.split("/")[-1]
        return re.split(r"[#/]", s.rstrip("/"))[-1] or s

    def short_iri(self, n):
        if isinstance(n, BNode):
            return "_:" + self.bkey[n]
        c = self.curie(n)
        return c if not c.startswith("<") else str(n)
