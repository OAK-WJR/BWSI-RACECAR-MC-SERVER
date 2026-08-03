#!/usr/bin/env bash
# Poll GitHub and deploy new plugin builds. Nothing listens on a port for this;
# the host reaches out, so there is no inbound attack surface.
#
# Three gates before anything is deployed:
#   1. the remote must fast-forward — a rewritten or force-pushed main is refused
#   2. CI must have succeeded for that exact commit
#   3. the build runs in a throwaway clone, so the live world is never touched
set -euo pipefail

LIVE=/root/minecraft
WORK=/root/mc-deploy
REMOTE=https://github.com/OAK-WJR/BWSI-RACECAR-MC-SERVER.git

# Region files are useless here and cost LFS bandwidth, so never fetch them.
export GIT_LFS_SKIP_SMUDGE=1

if [ ! -d "$WORK/.git" ]; then
    git clone --branch main "$REMOTE" "$WORK"
fi

cd "$WORK"
git fetch --quiet origin main

local_sha=$(git rev-parse HEAD)
remote_sha=$(git rev-parse origin/main)
[ "$local_sha" = "$remote_sha" ] && exit 0

# Gate 1: refuse anything that is not a fast-forward.
if ! git merge-base --is-ancestor "$local_sha" "$remote_sha"; then
    echo "refusing: origin/main is not a fast-forward of $local_sha"
    exit 1
fi

# Gate 2: refuse commits whose CI did not pass.
conclusion=$(gh run list --commit "$remote_sha" --limit 1 --json conclusion --jq '.[0].conclusion' 2>/dev/null || true)
if [ "$conclusion" != "success" ]; then
    echo "refusing: CI conclusion for $remote_sha is '${conclusion:-none}'"
    exit 1
fi

git merge --ff-only --quiet origin/main
echo "deploying $remote_sha"

# Builds run as uid 1000, so the container needs no capabilities at all.
# Only the sources are handed over; .git stays owned by root.
chown -R 1000:1000 "$WORK/plugins-src"

built=0
for d in plugins-src/*/; do
    [ -f "$d/build.gradle.kts" ] || [ -f "$d/build.gradle" ] || continue
    name=$(basename "$d")
    # Mount under the plugin's own name; Gradle takes the project name from it.
    docker run --rm \
        --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges \
        -v "$WORK/$d":"/build/$name" -w "/build/$name" \
        gradle:8-jdk21 gradle --no-daemon build
    built=1
done
[ "$built" = 1 ] || { echo "no plugins to build"; exit 0; }

find plugins-src -path '*/build/libs/*.jar' ! -name '*-sources.jar' \
    -exec install -o 1000 -g 1000 -m 644 {} "$LIVE/data/plugins/" \;

docker exec minecraft rcon-cli save-all
docker compose -f "$LIVE/docker-compose.yml" --project-directory "$LIVE" restart mc
echo "deployed $remote_sha"
