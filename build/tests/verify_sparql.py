"""Independent check: every count carried by the page model is re-derived with SPARQL on the Turtle."""
import sys, json, re, itertools
import rdflib
g=rdflib.Graph(); g.parse(sys.argv[1], format="turtle")
M=json.load(open(sys.argv[2], encoding="utf-8"))
PFX="""PREFIX cleets: <https://w3id.org/def/cleets#> PREFIX cd: <https://w3id.org/def/cleets/data#> PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX prov: <http://www.w3.org/ns/prov#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX sosa: <http://www.w3.org/ns/sosa/> PREFIX time: <http://www.w3.org/2006/time#> PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX dcat: <http://www.w3.org/ns/dcat#>"""
def one(q): return int(next(iter(g.query(PFX+q)))[0])
def ask(q): return bool(g.query(PFX+q).askAnswer)
def rows(q): return {tuple(str(x) for x in r) for r in g.query(PFX+q)}
DS=lambda d: f"<https://w3id.org/def/cleets/data#dataset/{d}>"
nodes={n["id"]:n for n in M["nodes"]}
fails=[]; checks=0
def check(name, got, want):
    global checks; checks+=1
    if got!=want: fails.append((name,got,want))
# which observable property identifies each series: read it from the node tip, then count by it
series={}
for n in M["nodes"]:
    if n["kind"]=="group" and n["gkind"]=="series":
        op=[l for l in n["tip"]["l"] if l.startswith("cleets:observesProperty ")][0].split(" ")[1]
        series[n["title"]]=op.replace("cleetsdata:","cd:")
        check("count "+n["title"], one(f"SELECT (COUNT(?s) AS ?n) WHERE {{ ?s cleets:observesProperty {series[n['title']]} }}"), n["count"])
for cls in ("Population","PopulationDensity","WelshLAD","EnglishLAD","Quarter"):
    check("count "+cls, one(f"SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ ?s a cleets:{cls} }}"), nodes["g:"+cls]["count"])
check("count Time (non-quarter)", one("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:Time FILTER NOT EXISTS { ?s a cleets:Quarter } }"), nodes["g:Time"]["count"])
check("triples", len(g), M["meta"]["triples"])
def members(gid):
    if gid in series: return f"?s cleets:observesProperty {series[gid]} ."
    if gid=="Time": return "?s a cleets:Time FILTER NOT EXISTS { ?s a cleets:Quarter }"
    return f"?s a cleets:{gid} ."
for e in M["edges"]:
    s,t,k=e["s"],e["t"],e["kind"]
    name=f"{k} {s} -> {t}"
    if k=="source":
        check(name, one(f"SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ {members(s[2:])} ?s dcterms:source {DS(t[3:])} }}"), e["n"])
        check(name+" (all members)", e["n"], nodes[s]["count"])
    elif k=="gen":
        check(name, one(f"SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ {members(s[2:])} ?s prov:wasGeneratedBy cd:{t[4:]} }}"), e["n"])
        check(name+" (all members)", e["n"], nodes[s]["count"])
    elif k=="used":
        check(name, ask(f"ASK {{ cd:{s[4:]} a prov:Activity ; prov:used {DS(t[3:])} }}"), True)
    elif k=="dim":
        pred=e["pred"]
        tgt = "?o a cleets:Quarter ." if t=="g:Quarter" else ("?o a cleets:WelshLAD ." if t=="g:WelshLAD" else "?o a cleets:Time FILTER NOT EXISTS { ?o a cleets:Quarter }")
        check(name, one(f"SELECT (COUNT(?s) AS ?n) WHERE {{ {members(s[2:])} ?s {pred} ?o . {tgt} }}"), e["n"])
        check(name+" (all members)", e["n"], nodes[s]["count"])
    elif k=="attr":
        check(name, one(f"SELECT (COUNT(?o) AS ?n) WHERE {{ ?s a cleets:{s[2:]} ; {e['pred']} ?o . ?o a cleets:{t[2:]} }}"), e["n"])
    elif k=="type" and s!="oplist":
        check(name, one(f"SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ {members(s[2:])} ?s a {t[2:]} }}"), e["n"])
    elif k=="sub":
        check(name, ask(f"ASK {{ {s[2:]} rdfs:subClassOf {t[2:]} }}"), True)
    elif k=="eq":
        check(name, ask(f"ASK {{ {s[2:]} owl:equivalentClass {t[2:]} }}"), True)
    elif k=="imp":
        check(name+" is NOT asserted in the file", ask(f"ASK {{ {s[2:]} rdfs:subClassOf {t[2:]} }}"), False)
        check("owl:imports OWL-Time", ask("ASK { ?o a owl:Ontology ; owl:imports <http://www.w3.org/2006/time> }"), True)
# no edge missing: every asserted subclass / equivalence among drawn classes is drawn
drawn={(e["s"][2:],e["t"][2:]) for e in M["edges"] if e["kind"] in ("sub","eq")}
nm=g.namespace_manager
for p in ("rdfs:subClassOf","owl:equivalentClass"):
    for a,b in rows(f"SELECT ?a ?b WHERE {{ ?a {p} ?b . FILTER(isIRI(?a) && isIRI(?b)) }}"):
        check(f"drawn {p}", (nm.normalizeUri(rdflib.URIRef(a)), nm.normalizeUri(rdflib.URIRef(b))) in drawn, True)
# observable property rows
for r in nodes["oplist"]["rows"]:
    op=r["id"][3:].replace("cleetsdata:","cd:")
    check("observed-by "+op, one(f"SELECT (COUNT(?s) AS ?n) WHERE {{ ?s cleets:observesProperty {op} }}"), r["used"])
check("observable property rows", one("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:ObservableProperty }"), len(nodes["oplist"]["rows"]))
# key sets per dataset, straight from dcterms:source (single-source individuals only)
def single(d): return f"?s dcterms:source {DS(d)} . FILTER NOT EXISTS {{ ?s dcterms:source ?other . FILTER(?other != {DS(d)}) }}"
lads={}; times={}; keys={}; dates={}
for d in [t["id"] for t in M["tabs"] if t["idx"]]:
    a=rows(f"SELECT DISTINCT ?l WHERE {{ {single(d)} ?s cleets:forLAD ?l }}")
    b=rows(f"SELECT DISTINCT ?l WHERE {{ {single(d)} ?l ?p ?s . ?l a ?c . ?c rdfs:subClassOf cleets:LAD }}")
    c=rows(f"SELECT DISTINCT ?s WHERE {{ {single(d)} ?s a ?c . ?c rdfs:subClassOf cleets:LAD }}")
    lads[d]=a|b|c
    times[d]=rows(f"SELECT DISTINCT ?t WHERE {{ {single(d)} ?s cleets:forTime ?t }}")
    keys[d]=rows(f"SELECT DISTINCT ?l ?t WHERE {{ {single(d)} ?s cleets:forLAD ?l ; cleets:forTime ?t . FILTER NOT EXISTS {{ ?s prov:wasGeneratedBy ?a }} }}")
    dates[d]=rows(f"SELECT DISTINCT ?t WHERE {{ {single(d)} ?s dcterms:date ?t }}")
num=lambda s: int(re.sub(r"[^\d]","",s.split(" ")[0])) if re.match(r"[\d,]+",s) else None
for d,p in M["panels"].items():
    if d=="all": continue
    card=[c for c in p["cards"] if c["h"]=="Links to other datasets"][0]
    if not card.get("table"): continue
    for r in card["table"]["rows"]:
        other=re.sub(r"[\[\]]","",r[0]["r"])
        check(f"districts in common {d}/{other}", len(lads[d]&lads[other]), num(r[1]["r"]))
        if len(r)<3: continue   # table without a time column
        cell=r[2]["r"]
        if num(cell) is not None: check(f"time individuals in common {d}/{other}", len(times[d]&times[other]), num(cell))
        elif cell.startswith("none;"): 
            check(f"no shared time individuals {d}/{other}", len(times[d]&times[other]), 0)
            check(f"dcterms:date values in common {d}/{other}", len(dates[d]&dates[other]), int(re.search(r"none; (\d+)",cell).group(1)))
        elif cell.startswith("none"): check(f"no shared time individuals {d}/{other}", len(times[d]&times[other]), 0)
ov=[c for c in M["panels"]["all"]["cards"] if c["h"]=="Where datasets meet"][0]["table"]
hd=ov["head"][1:]
for r in ov["rows"]:
    a=re.sub(r"[\[\]]","",r[0]["r"])
    for bname,cell in zip(hd,r[1:]): check(f"district-quarter pairs {a}/{bname}", len(keys[a]&keys[bname]), num(cell["r"]))
print(f"{checks} checks, {len(fails)} failures")
for f in fails: print("  FAIL", f)
