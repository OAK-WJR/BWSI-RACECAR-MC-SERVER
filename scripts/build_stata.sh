#!/usr/bin/env bash
# Generate every Stata floor and place it in the campus world.
#
# Floors stack 5 blocks apart, which matches the real building: OSM puts Stata
# at 43.1 m over 9 levels. Level 1-3 are the base; from level 4 up the building
# splits into the Dreyfoos (D) and Gates (G) towers, so those floors sit at the
# same height as each other.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

GROUND_Y=64
STOREY=5
PACK="data/BWSI Racecar/datapacks/campus"
FUNCS="$PACK/data/campus/function"
SCHEMS="data/plugins/WorldEdit/schematics"

mkdir -p "$FUNCS" "$SCHEMS"

# floor file -> storey number (1-based)
FLOORS="32-1:1 32-2:2 32-3:3 32-D4:4 32-G4:4 32-D5:5 32-G5:5 32-D6:6 32-G6:6 \
32-D7:7 32-G7:7 32-D8:8 32-G8:8 32-D9:9 32-G9:9"

names=()
for entry in $FLOORS; do
    file="${entry%%:*}"
    storey="${entry##*:}"
    y=$((GROUND_Y + (storey - 1) * STOREY))
    name="stata_$(echo "$file" | tr 'A-Z-' 'a-z_')"
    echo "== $file  storey $storey  y=$y"
    python3 scripts/stata_floorplan_to_schem.py "campus-data/floorplans/$file.xml" \
        -o "$SCHEMS/$name.schem" \
        --mcfunction "$FUNCS/$name.mcfunction" \
        --base-y "$y" | sed 's/^/   /'
    names+=("$name")
done

chown -R 1000:1000 "$PACK" "$SCHEMS"
# minecraft:reload, not /reload -- Paper's /reload reloads plugins and leaves
# the datapack registry untouched, so new functions stay unknown.
docker exec minecraft rcon-cli "minecraft:reload" >/dev/null
sleep 15

# Each floor is placed on its own: one combined call would blow past
# maxCommandChainLength.
for name in "${names[@]}"; do
    echo "placing $name"
    docker exec minecraft rcon-cli "execute in minecraft:campus run function campus:$name" >/dev/null
done

docker exec minecraft rcon-cli "save-all" >/dev/null
echo "done - ${#names[@]} floors placed in the campus world"
