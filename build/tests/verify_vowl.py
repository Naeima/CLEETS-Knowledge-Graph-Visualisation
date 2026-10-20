"""Independent check of the VOWL model against the Turtle with SPARQL."""
import sys, json, re
import rdflib
g=rdflib.Graph(); g.parse(sys.argv[1], format="turtle")
V=json.load(open(sys.argv[2], encoding="utf-8"))["vowl"]
PFX="""PREFIX cleets: <https://w3id.org/def/cleets#> PREFIX cd: <https://w3id.org/def/cleets/data#> PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX prov: <http://www.w3.org/ns/prov#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX sosa: <http://www.w3.org/ns/sosa/> PREFIX time: <http://www.w3.org/2006/time#> PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX dcat: <http://www.w3.org/ns/dcat#> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>"""
def one(q): return int(next(iter(g.query(PFX+q)))[0])
def ask(q): return bool(g.query(PFX+q).askAnswer)
def rows(q): return {tuple(str(x) for x in r) for r in g.query(PFX+q)}
nm=g.namespace_manager
cu=lambda u: nm.normalizeUri(rdflib.URIRef(u))
DS=lambda d: f"<https://w3id.org/def/cleets/data#dataset/{d}>"
nodes={n["id"]:n for n in V["nodes"]}; links={l["id"]:l for l in V["links"]}
fails=[]; checks=0
def check(name, got, want):
    global checks; checks+=1
    if got!=want: fails.append((name,got,want))
# classes and their individual counts, labels, equivalents
cls=rows("SELECT ?c WHERE { ?c a owl:Class FILTER(isIRI(?c) && STRSTARTS(STR(?c),'https://w3id.org/def/cleets#')) }")
check("class nodes", {n["curie"] for n in V["nodes"] if n["kind"]=="class"}, {cu(c) for (c,) in cls})
for (c,) in cls:
    n=nodes["c:"+cu(c)]
    check("direct individuals "+cu(c), n["count"], one(f"SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ ?s a <{c}> }}"))
    lab=rows(f"SELECT ?l WHERE {{ <{c}> rdfs:label ?l }}")
    check("label "+cu(c), n["label"], list(lab)[0][0] if lab else cu(c).split(":")[1])
    eq=rows(f"SELECT ?e WHERE {{ <{c}> owl:equivalentClass ?e FILTER(isIRI(?e)) }}")
    check("equivalents "+cu(c), set(n["equiv"]), {cu(e) for (e,) in eq})
# properties: domain/range/functional/equivalents
for kind,t in (("object","owl:ObjectProperty"),("datatype","owl:DatatypeProperty")):
    ps=rows(f"SELECT ?p WHERE {{ ?p a {t} }}")
    check(kind+" property links", {l["curie"] for l in V["links"] if l["kind"]==kind}, {cu(p) for (p,) in ps})
    for (p,) in ps:
        l=links["p:"+cu(p)]
        dom=rows(f"SELECT ?d WHERE {{ <{p}> rdfs:domain ?d FILTER(isIRI(?d)) }}")
        want_s = ("c:"+cu(list(dom)[0][0])) if dom else None
        check("domain end "+cu(p), l["s"] if dom else (None if l["s"].startswith("thing:") else l["s"]), want_s)
        if kind=="object":
            rng=rows(f"SELECT ?r WHERE {{ <{p}> rdfs:range ?r FILTER(isIRI(?r)) }}")
            check("range end "+cu(p), l["t"] if rng else (None if l["t"].startswith("thing:") else l["t"]), ("c:"+cu(list(rng)[0][0])) if rng else None)
        else:
            rng=rows(f"SELECT ?r WHERE {{ <{p}> rdfs:range ?r }}")
            tnode=nodes[l["t"]]
            if rng:
                r=list(rng)[0][0]
                base = r if r.startswith("http") else None
                if base is None:   # anonymous restricted datatype
                    base=list(rows(f"SELECT ?b WHERE {{ <{p}> rdfs:range ?r . ?r owl:onDatatype ?b }}"))[0][0]
                check("datatype box "+cu(p), tnode["curie"], cu(base))
            else:
                check("literal box "+cu(p), tnode["kind"], "literal")
        check("functional "+cu(p), l["sub"]=="functional", ask(f"ASK {{ <{p}> a owl:FunctionalProperty }}"))
        check("equivalent props "+cu(p), set(l["equiv"]), {cu(e) for (e,) in rows(f"SELECT ?e WHERE {{ <{p}> owl:equivalentProperty ?e }}")})
# subclass and disjoint
sub=rows("SELECT ?a ?b WHERE { ?a rdfs:subClassOf ?b FILTER(isIRI(?a) && isIRI(?b)) }")
check("subclass links", {(nodes[l["s"]]["curie"], nodes[l["t"]]["curie"]) for l in V["links"] if l["kind"]=="subclass"}, {(cu(a),cu(b)) for a,b in sub})
dj=set()
for a,b in rows("SELECT ?a ?b WHERE { ?a owl:disjointWith ?b }"): dj.add(tuple(sorted((cu(a),cu(b)))))
mem=[cu(x) for (x,) in rows("SELECT ?m WHERE { ?ad a owl:AllDisjointClasses ; owl:members ?l . ?l rdf:rest*/rdf:first ?m }".replace("rdf:","<http://www.w3.org/1999/02/22-rdf-syntax-ns#>".join(["",""])) if False else "SELECT ?m WHERE { ?ad a owl:AllDisjointClasses ; owl:members ?l . ?l <http://www.w3.org/1999/02/22-rdf-syntax-ns#rest>*/<http://www.w3.org/1999/02/22-rdf-syntax-ns#first> ?m }")]
for i in range(len(mem)):
    for j in range(i+1,len(mem)): dj.add(tuple(sorted((mem[i],mem[j]))))
check("disjoint pairs", {tuple(sorted((nodes[l["s"]]["curie"], nodes[l["t"]]["curie"]))) for l in V["links"] if l["kind"]=="disjoint"}, dj)
# dataset edges: individuals per (class, dataset)
got={(nodes[l["s"]]["curie"], nodes[l["t"]]["name"]): l["n"] for l in V["links"] if l["kind"]=="source"}
want={}
for c,d,n in g.query(PFX+"SELECT ?c ?d (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?c ; dcterms:source ?d . ?d a dcat:Dataset FILTER(STRSTARTS(STR(?c),'https://w3id.org/def/cleets#')) } GROUP BY ?c ?d"):
    want[(cu(c), str(d).split("/")[-1])]=int(n)
check("dcterms:source edges and counts", got, want)
got={(nodes[l["s"]]["curie"], l["t"][4:]): l["n"] for l in V["links"] if l["kind"]=="generated"}
want={}
for c,a,n in g.query(PFX+"SELECT ?c ?a (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?c ; prov:wasGeneratedBy ?a . ?a a prov:Activity FILTER(STRSTARTS(STR(?c),'https://w3id.org/def/cleets#')) } GROUP BY ?c ?a"):
    want[(cu(c), str(a).split("#")[-1])]=int(n)
check("prov:wasGeneratedBy edges and counts", got, want)
got={(l["s"][4:], l["t"][3:]) for l in V["links"] if l["kind"]=="used"}
want={(str(a).split("#")[-1], str(d).split("/")[-1]) for a,d in rows("SELECT ?a ?d WHERE { ?a a prov:Activity ; prov:used ?d }")}
check("prov:used edges", got, want)
check("Thing nodes = property ends without domain/range", sum(1 for n in V["nodes"] if n["kind"]=="thing"),
      one("SELECT (COUNT(?p) AS ?n) WHERE { ?p a owl:ObjectProperty FILTER NOT EXISTS { ?p rdfs:domain ?d } }") + one("SELECT (COUNT(?p) AS ?n) WHERE { ?p a owl:ObjectProperty FILTER NOT EXISTS { ?p rdfs:range ?r } }") + one("SELECT (COUNT(?p) AS ?n) WHERE { ?p a owl:DatatypeProperty FILTER NOT EXISTS { ?p rdfs:domain ?d } }"))
# info panels: restrictions per class
for (c,) in cls:
    i=V["info"]["c:"+cu(c)]
    rs=[x for L in i["lists"] if L["h"].startswith("Restrictions") for x in L["items"]]
    n_restr=one(f"SELECT (COUNT(?r) AS ?n) WHERE {{ <{c}> rdfs:subClassOf ?r . ?r a owl:Restriction }}")
    check("restrictions listed "+cu(c), len(rs), n_restr)
print(f"{checks} checks, {len(fails)} failures")
for f in fails: print("  FAIL", f[0], "| got", str(f[1])[:300], "| want", str(f[2])[:300])
