#!/usr/bin/env bash
# Commit the current world to git.
# Writes are paused while the files are read, otherwise a snapshot can catch
# a half-written region file.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

docker exec minecraft rcon-cli save-all
docker exec minecraft rcon-cli save-off
trap 'docker exec minecraft rcon-cli save-on' EXIT
sleep 3

git add "data/BWSI Racecar"
if git diff --cached --quiet; then
    echo "world unchanged"
    exit 0
fi

git commit -m "World snapshot ${1:-$(date -u '+%Y-%m-%d %H:%M UTC')}"
echo "committed. run: git push"
