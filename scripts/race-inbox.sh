#!/usr/bin/env bash
# Turn Python files dropped in the inbox into race submissions.
#
#     scp my_racer.py root@server:/root/race-inbox/oakWJR.py
#
# The file name is the player: a book is fine for a few lines, but real lab
# code does not fit on a book page. The queue file this writes is picked up
# by mc-race-runner exactly like an in-game submission.
set -euo pipefail

INBOX=/root/race-inbox
QUEUE=/root/minecraft/data/plugins/Race/queue
USERCACHE=/root/minecraft/data/usercache.json

mkdir -p -- "$INBOX" "$QUEUE"

shopt -s nullglob
for file in "$INBOX"/*.py; do
    python3 - "$file" "$QUEUE" "$USERCACHE" <<'PYEOF'
import json, os, re, sys, time

path, queue, usercache = sys.argv[1], sys.argv[2], sys.argv[3]
name = os.path.basename(path)[:-3]
if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", name):
    raise SystemExit(f"skip {name}: not a Minecraft name")

code = open(path, encoding="utf-8", errors="replace").read()
if len(code.encode()) > 65536:
    raise SystemExit(f"skip {name}: over 64 KB")

players = {u["name"].lower(): u for u in json.load(open(usercache))}
player = players.get(name.lower())
if player is None:
    raise SystemExit(f"skip {name}: never seen on this server")

stamp = int(time.time() * 1000)
queue_name = f"{stamp}_{player['uuid']}.json"
payload = {"id": queue_name[:-5], "player_uuid": player["uuid"],
           "player_name": player["name"], "submitted_at": time.time(), "code": code}
tmp = os.path.join(queue, ".tmp-" + queue_name)
with open(tmp, "w") as fh:
    json.dump(payload, fh)
os.chown(tmp, 1000, 1000)
os.rename(tmp, os.path.join(queue, queue_name))
print(f"queued {queue_name} for {player['name']}")
PYEOF
    rm -f -- "$file"
done
