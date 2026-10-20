#!/usr/bin/env python3
"""Independent SPARQL cross-checks of the entity explorer model against index.ttl."""
import sys, json, collections, rdflib
g = rdflib.Graph(); g.parse(sys.argv[1], format="turtle")
M = json.load(open(sys.argv[2]))
kinds = M["kinds"]; cnt = collections.Counter(kinds[k] for k in M["kind"])
rel = {r["p"]: r["n"] for r in M["relations"]}
P = """PREFIX cleets: <https://w3id.org/def/cleets#> PREFIX dcat: <http://www.w3.org/ns/dcat#> PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX dcterms: <http://purl.org/dc/terms/> PREFIX time: <http://www.w3.org/2006/time#> PREFIX void: <http://rdfs.org/ns/void#>
PREFIX schema: <https://schema.org/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX owl: <http://www.w3.org/2002/07/owl#> PREFIX sh: <http://www.w3.org/ns/shacl#> """
def n(q): return int(next(iter(g.query(P + q)))[0])
res = []
def ok(name, a, b): res.append((name, a == b, f"{a} vs {b}"))
ok("WelshLAD", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:WelshLAD }"), cnt["WelshLAD"])
ok("EnglishLAD", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:EnglishLAD }"), cnt["EnglishLAD"])
ok("Quarter", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:Quarter }"), cnt["Quarter"])
ok("time:Instant (blank nodes)", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a time:Instant }"), cnt["Instant"])
ok("Population", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:Population }"), cnt["Population"])
ok("PopulationDensity", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:PopulationDensity }"), cnt["PopulationDensity"])
ok("EVKeepership", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:EVKeepership }"), cnt["EVKeepership"])
ok("EVChargerCount", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:EVChargerCount }"), cnt["EVChargerCount"])
ok("IncomeDeprivation", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:IncomeDeprivation }"), cnt["IncomeDeprivation"])
ok("KeepersPerCharger (AdoptionRatioObservation)", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:AdoptionRatioObservation }"), cnt["KeepersPerCharger"])
for series in ("EVsPerThousandResidents", "PrivateVehicleStock", "ChargersPer100kResidents"):   # derived series: property individuals in the data namespace
    ok(series, n(f"SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ ?s cleets:observesProperty <https://w3id.org/def/cleets/data#{series}Property> }}"), cnt[series])
ok("all observations (cleets:Observation or a subclass)", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?t . ?t rdfs:subClassOf* cleets:Observation }"), sum(cnt[k] for k in ("EVKeepership","EVsPerThousandResidents","PrivateVehicleStock","EVChargerCount","ChargersPer100kResidents","KeepersPerCharger","IncomeDeprivation")))
ok("dcat:Dataset records (+ the graph itself, typed void:Dataset too)", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a dcat:Dataset }"), cnt["Dataset record"] + cnt["Knowledge graph"])
ok("dcat:DatasetSeries", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a dcat:DatasetSeries }"), cnt["Dataset series"])
ok("dcat:Distribution", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a dcat:Distribution }"), cnt["Distribution"])
ok("prov:Activity", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a prov:Activity }"), cnt["Derivation"])
ok("void:Dataset", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a void:Dataset }"), cnt["Knowledge graph"])
ok("ObservableProperty individuals", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a cleets:ObservableProperty }"), cnt["ObservableProperty"])
ok("Persons (schema:Person IRIs + foaf:Person blank nodes)", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { { ?s a schema:Person } UNION { ?s a <http://xmlns.com/foaf/0.1/Person> } }"), cnt["Person"])
ok("Postal addresses", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a schema:PostalAddress }"), cnt["Postal address"])
ok("fingerprints (prov:Entity only)", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a prov:Entity . FILTER NOT EXISTS { ?s a ?t . FILTER(?t != prov:Entity) } }"), cnt["Source-row fingerprint"])
ok("dcterms:PeriodOfTime", n("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a dcterms:PeriodOfTime }"), cnt["Period of time"])
# edges
ok("forLAD edges", n("SELECT (COUNT(*) AS ?n) WHERE { ?s cleets:forLAD ?o }"), rel["cleets:forLAD"])
ok("forTime edges", n("SELECT (COUNT(*) AS ?n) WHERE { ?s cleets:forTime ?o }"), rel["cleets:forTime"])
ok("observesProperty edges", n("SELECT (COUNT(*) AS ?n) WHERE { ?s cleets:observesProperty ?o }"), rel["cleets:observesProperty"])
ok("hasPopulationDensity edges", n("SELECT (COUNT(*) AS ?n) WHERE { ?s cleets:hasPopulationDensity ?o }"), rel["cleets:hasPopulationDensity"])
ok("hasPopulation edges", n("SELECT (COUNT(*) AS ?n) WHERE { ?s cleets:hasPopulation ?o }"), rel["cleets:hasPopulation"])
ok("wasGeneratedBy edges", n("SELECT (COUNT(*) AS ?n) WHERE { ?s prov:wasGeneratedBy ?o }"), rel["prov:wasGeneratedBy"])
ok("hasBeginning edges", n("SELECT (COUNT(*) AS ?n) WHERE { ?s time:hasBeginning ?o }"), rel["time:hasBeginning"])
ok("dcterms:source edges from individuals (any IRI object)", n("SELECT (COUNT(*) AS ?n) WHERE { ?s dcterms:source ?o . FILTER(isIRI(?o)) FILTER NOT EXISTS { ?s a ?t . FILTER(?t IN (owl:Class, owl:ObjectProperty, owl:DatatypeProperty, owl:AnnotationProperty, owl:Ontology, sh:NodeShape, sh:PropertyShape)) } }"), rel["dcterms:source"])
ok("wasDerivedFrom edges from individuals", n("SELECT (COUNT(*) AS ?n) WHERE { ?s prov:wasDerivedFrom ?o . FILTER NOT EXISTS { ?s a owl:Ontology } }"), rel["prov:wasDerivedFrom"])
ok("seeAlso edges from individuals (the graph's link to the ontology excluded)", n("SELECT (COUNT(*) AS ?n) WHERE { ?s rdfs:seeAlso ?o . FILTER NOT EXISTS { ?s a owl:Ontology } FILTER NOT EXISTS { ?s a owl:Class } FILTER NOT EXISTS { ?s a sh:NodeShape } FILTER(?o != <https://w3id.org/def/cleets>) }"), rel["rdfs:seeAlso"])
# literals on a sample: Cardiff
i = M["label"].index("Cardiff")
lits = n("SELECT (COUNT(*) AS ?n) WHERE { <https://w3id.org/def/cleets/data#W06000015> ?p ?o . FILTER(isLiteral(?o)) }")
ok("Cardiff literal attributes", lits, len(M["attrs"][i]))
ok("Cardiff degree (all object links in or out, excl. rdf:type/isDefinedBy)", n("SELECT (COUNT(*) AS ?n) WHERE { { <https://w3id.org/def/cleets/data#W06000015> ?p ?o . FILTER(!isLiteral(?o)) FILTER(?p NOT IN (rdf:type, rdfs:isDefinedBy, dcterms:conformsTo)) } UNION { ?s ?p <https://w3id.org/def/cleets/data#W06000015> } }".replace("rdf:type", "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>")), M["deg"][i])
bad = [r for r in res if not r[1]]
for name, good, info in res: print(("ok  " if good else "FAIL"), name, info)
print(f"\n{len(res)-len(bad)}/{len(res)} checks passed")
sys.exit(1 if bad else 0)
