#!/usr/bin/env bash
# Build every plugin in plugins-src/ and deploy to the running server.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

for d in plugins-src/*/; do
    [ -f "$d/build.gradle.kts" ] || [ -f "$d/build.gradle" ] || continue
    name=$(basename "$d")
    echo "building $name"
    docker run --rm --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges \
        -v "$PWD/$d":"/build/$name" -w "/build/$name" \
        gradle:8-jdk21 gradle --no-daemon build
done

jars=$(find plugins-src -path '*/build/libs/*.jar' ! -name '*-sources.jar')
[ -n "$jars" ] || { echo "nothing to deploy"; exit 0; }

docker exec minecraft rcon-cli save-all
for jar in $jars; do
    echo "deploying $(basename "$jar")"
    install -o 1000 -g 1000 -m 644 "$jar" data/plugins/
done

docker compose restart mc
