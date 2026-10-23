# Narration script with timings

Total length 5 min 29 s. Times are where each sentence starts in the finished video; record each scene as one take and pause where the captions pause.

## title  (0:00.0, 11 s)

Screen: Title card with the site address.

- 0:00.7  This is a short guide to the CLEETS knowledge graph visualisations:
- 0:05.4  two web pages that let you read CLEETS-KG without reading its Turtle file.

## turtle  (0:11.4, 34 s)

Screen: The raw Turtle scrolling past.

- 0:12.1  CLEETS-KG is published as a Turtle file: 96,479 triples, about six megabytes of text.
- 0:18.8  Every fact is in there, but a file like this shows one triple at a time.
- 0:24.5  To see how the eight source datasets meet in the ontology,
- 0:29.1  or to find every observation about Cardiff,
- 0:32.5  you would have to write queries or scroll for a very long time.
- 0:37.5  The two pages do that reading for you.

## landing  (0:45.2, 22 s)

Screen: The landing page; the pointer moves over the two cards and opens the dataset map.

- 0:45.9  The landing page offers two views.
- 0:48.6  The dataset map shows the ontology and its sources.
- 0:52.5  The entity explorer shows every individual in the data.
- 0:56.7  Both are generated from the same Turtle file,
- 1:00.1  and every figure they show was cross-checked against it with SPARQL.

## map-vowl  (1:07.2, 37 s)

Screen: The VOWL graph; the pointer rests on a class, a datatype and a dataset record.

- 1:07.9  The dataset map draws the ontology in VOWL notation, the same notation used by WebVOWL.
- 1:14.6  Circles are classes, sized by the number of individuals they have in the graph.
- 1:20.7  Rectangles are datatypes.
- 1:22.6  Arrows are properties, labelled with their names.
- 1:26.4  The coloured boxes are the dataset records and the diamonds are the derivation activities.
- 1:33.3  These are an addition to the notation: they show where the data in each class comes from.

## map-tab  (1:43.8, 37 s)

Screen: The EVCI9001 tab is selected; the pointer opens the EVChargerCount class in the side panel.

- 1:44.5  Select a dataset and the map highlights what it contributes.
- 1:48.7  The public charging device statistics (EVCI9001) become 594 charger-count observations,
- 1:54.9  one per district and quarter.
- 1:56.9  The reading at the top says where the dataset meets the others:
- 2:01.3  with the vehicle licensing table (VEH0132) in the keepers-per-charger derivation,
- 2:07.1  and with the StatsWales population in chargers per hundred thousand residents.
- 2:12.6  Click any node for its definition, its restrictions, and the shapes that validate it.

## map-schematic  (2:21.1, 19 s)

Screen: Switching to the schematic view.

- 2:21.8  The schematic view is the same information as a fixed wiring diagram: the sources on the left,
- 2:28.4  the grouped individuals in the middle, and the ontology on the right.
- 2:33.2  It does not move, so it is the view to use in print or in a slide.

## explorer  (2:39.9, 42 s)

Screen: The explorer at full extent; a slow zoom into the centre and back out.

- 2:40.6  The entity explorer draws all 17,068 individuals and the 51,838 links between them.
- 2:47.0  The layout follows what the entities are.
- 2:50.1  The knowledge-graph record and the eight dataset records sit in the middle.
- 2:55.8  The 67 quarters form the inner ring, in order.
- 2:59.3  The 22 Welsh districts form the next ring,
- 3:02.5  each with a disc of its observations and population figures.
- 3:07.0  The 296 English districts form the outer ring with their population density series.
- 3:13.3  Links that leave a cluster are drawn as bundles, as wide as the number of links they stand for.

## explorer-tab  (3:21.8, 28 s)

Screen: The VEH0132 tab is selected.

- 3:22.5  Selecting a dataset fades everything it does not touch.
- 3:26.7  With the battery-electric vehicle counts (VEH0132) selected,
- 3:31.3  you see at once that they sit in every Welsh district for 57 quarters,
- 3:36.6  between late 2011 and late 2025, and nowhere in England.
- 3:40.8  The derived keeperships per thousand residents and keepers per charger light up with them.

## search  (3:49.5, 31 s)

Screen: Typing Cardiff, choosing the district, then following a link to one observation.

- 3:50.2  Search finds any entity by its label or its identifier (IRI).
- 3:54.4  Selecting Cardiff zooms to its disc and opens its record: the district code, the two labels,
- 4:00.8  and 289 links grouped by predicate.
- 4:03.3  Every link is a button, so you can walk the graph from here.
- 4:07.5  This one is the number of public charge points per hundred thousand residents in Cardiff in the fourth quarter of 2019:
- 4:15.8  twelve point six, with nine links of its own.

## neighbourhood  (4:20.8, 30 s)

Screen: Neighbourhood mode around the observation; the pointer visits the labelled links.

- 4:21.5  Neighbourhood mode isolates the selected entity with its neighbours and names every link.
- 4:27.5  This derived observation has its district, its quarter, the property it observes,
- 4:33.1  the derivation that produced it, the two datasets it was computed from,
- 4:37.9  and the fingerprint of the source row.
- 4:40.5  This is the view that answers the question a Turtle file makes hardest:
- 4:45.3  what is connected to this thing, and how.

## filters  (4:50.6, 22 s)

Screen: Hiding the source-row fingerprints, opening the relations menu, switching layouts.

- 4:51.3  The legend switches entity types on and off, the relations menu does the same for predicates,
- 4:57.3  and the layout toggle swaps the structured arrangement for a force-directed one.
- 5:02.4  Everything you see is drawn from the data at a fixed commit,
- 5:06.3  which is printed at the foot of each page.

## close  (5:12.5, 16 s)

Screen: Closing card with the site and repository addresses.

- 5:13.2  Both pages, the scripts that build them,
- 5:16.1  and the checks that verify them are in the GitHub repository.
- 5:20.5  Rebuilding from the Turtle file takes about a minute, so the pages can follow the graph as it grows.
