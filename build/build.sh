#!/usr/bin/env bash
# Rebuild the two visualisation pages from the CLEETS-KG Turtle file.
#
#   ./build.sh            build dataset-map.html and entity-explorer.html in the repository root
#   ./build.sh --check    also run the SPARQL cross-checks and the headless browser checks
#                         (needs `npm install` in this directory and `playwright install chromium`)
#   ./build.sh --bake     re-run the VOWL force layout headlessly and store the settled positions
#                         in layout/vowl_pos.json before building (do this after changing the ontology)
#
# The Turtle file is data/index.ttl. If it is missing it is downloaded from the CLEETS repository at the
# commit recorded in source.txt; set CLEETS_TTL to build from another copy of the graph instead.
#
# The layouts are cached so that builds are reproducible: layout/vowl_pos.json holds the settled
# positions of the VOWL graph, layout/entity_force.json the igraph DrL coordinates of the entity graph.
# Delete entity_force.json to recompute it (about a minute); a changed graph triggers it by itself.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
WORK="$HERE/work"
mkdir -p "$WORK" "$ROOT/data"

# the source graph: repository, commit and commit date, from source.txt
SRC_REPO="$(sed -n 's/^repo=//p' "$HERE/source.txt")"
COMMIT="$(sed -n 's/^commit=//p' "$HERE/source.txt")"
COMMIT_DATE="$(sed -n 's/^date=//p' "$HERE/source.txt")"
TTL="${CLEETS_TTL:-$ROOT/data/index.ttl}"
if [ ! -s "$TTL" ]; then
  url="https://raw.githubusercontent.com/${SRC_REPO#https://github.com/}/$COMMIT/index.ttl"
  echo "== fetching $url"
  curl -fsSL "$url" -o "$TTL"
fi

check=0; bake=0
for arg in "$@"; do
  case "$arg" in
    --check) check=1 ;;
    --bake) bake=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ "$bake" = 1 ]; then
  echo "== baking the VOWL layout"
  python3 "$HERE/build_kg_map.py" "$TTL" "$HERE/template.html" "$WORK/map_unbaked.html" \
    --commit "$COMMIT" --commit-date "$COMMIT_DATE"
  python3 "$HERE/bake_layout.py" "$WORK/map_unbaked.html" "$HERE/layout/vowl_pos.json" 1100 700
fi

echo "== dataset map"
python3 "$HERE/build_kg_map.py" "$TTL" "$HERE/template.html" "$ROOT/dataset-map.html" \
  --json "$WORK/map_model.json" --vowl-pos "$HERE/layout/vowl_pos.json" \
  --commit "$COMMIT" --commit-date "$COMMIT_DATE" --entities-url entity-explorer.html --standalone

echo "== entity explorer"
python3 "$HERE/build_entities.py" "$TTL" "$HERE/entities_template.html" "$ROOT/entity-explorer.html" \
  --json "$WORK/entities_model.json" --force-layout "$HERE/layout/entity_force.json" \
  --commit "$COMMIT" --commit-date "$COMMIT_DATE" --map-url dataset-map.html --standalone

if [ "$check" = 1 ]; then
  echo "== cross-checks against the Turtle"
  python3 "$HERE/tests/verify_sparql.py" "$TTL" "$WORK/map_model.json"
  python3 "$HERE/tests/verify_vowl.py" "$TTL" "$WORK/map_model.json"
  python3 "$HERE/tests/verify_entities.py" "$TTL" "$WORK/entities_model.json"
  echo "== headless browser checks"
  python3 "$HERE/tests/itest.py" "$ROOT/dataset-map.html" "$WORK"
  python3 "$HERE/tests/vtest.py" "$ROOT/dataset-map.html" "$WORK"
  python3 "$HERE/tests/etest.py" "$ROOT/entity-explorer.html" "$WORK"
fi
echo "done"
