#!/usr/bin/env bash
# Extrude the OSM footprints of Stata's neighbours into the campus world.
#
# Building 32 is skipped: Gehry's massing does not survive a straight extrusion
# of its ground outline, so the Stata exterior is hand-built. Its interior comes
# from build_stata.sh.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

REFS="${REFS:-9,13,24,26,31,33,34,35,36,37,38,39,56,66,68}"
PACK="data/BWSI Racecar/datapacks/campus"
FUNCS="$PACK/data/campus/function"

mkdir -p "$FUNCS"

echo "== generating"
python3 scripts/osm_buildings_to_function.py campus-data/osm-buildings.json \
    --out-dir "$FUNCS" --refs "$REFS" --base-y 64

chown -R 1000:1000 "$PACK"

# forceload caps at 256 chunks per call, and the footprints span roughly
# 500 x 300 m, so cover it in strips.
echo "== loading chunks"
for x0 in -336 -176 -16; do
    x1=$((x0 + 159))
    docker exec minecraft rcon-cli \
        "execute in minecraft:campus run forceload add $x0 -96 $x1 96" >/dev/null
    docker exec minecraft rcon-cli \
        "execute in minecraft:campus run forceload add $x0 97 $x1 224" >/dev/null
done

# minecraft:reload, not /reload -- Paper's /reload only reloads plugins.
docker exec minecraft rcon-cli "minecraft:reload" >/dev/null
sleep 15

echo "== placing"
for f in "$FUNCS"/bldg_*.mcfunction; do
    name=$(basename "$f" .mcfunction)
    echo "   $name"
    docker exec minecraft rcon-cli \
        "execute in minecraft:campus run function campus:$name" >/dev/null
done

docker exec minecraft rcon-cli "save-all" >/dev/null
echo "done"
