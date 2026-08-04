#!/usr/bin/env bash
# Drain the race submission queue, oldest first, one sandbox at a time.
# Triggered by mc-race-runner.path whenever the queue directory is non-empty.
# Player code is hostile: it only ever runs inside the docker sandbox below,
# and nothing from the submission files is ever interpolated into a shell.
set -euo pipefail

QUEUE=/root/minecraft/data/plugins/Race/queue
RESULTS=/root/minecraft/data/plugins/Race/results
SIM=/root/minecraft/sim
WORK_ROOT=/root/mc-race-work
IMAGE=bwsi-race-sim          # built from sim/Dockerfile

mkdir -p -- "$QUEUE" "$RESULTS" "$WORK_ROOT"

while :; do
    name=$(ls -1 -- "$QUEUE" 2>/dev/null | grep -E '^[0-9]{10,16}_[0-9a-f-]{36}\.json$' | sort | head -1 || true)
    if [ -z "$name" ]; then
        # delete anything that is not a well-formed submission (dotfiles are
        # the plugin's in-progress tmp writes, leave those alone)
        find "$QUEUE" -maxdepth 1 -type f ! -name '.*' \
            ! -regex '.*/[0-9]{10,16}_[0-9a-f-]{36}\.json' -delete
        exit 0
    fi

    work=$(mktemp -d -p "$WORK_ROOT")
    # the sandbox runs as uid 1000 and must be able to write out.json here
    chown 1000:1000 -- "$work"
    chmod 700 -- "$work"
    mv -- "$QUEUE/$name" "$work/submission.json"

    # copy the code field out; the code is never executed on the host
    if ! python3 - "$work" <<'PYEOF'
import json, sys
work = sys.argv[1]
sub = json.load(open(f"{work}/submission.json"))
code = sub.get("code", "")
if not isinstance(code, str) or len(code.encode()) > 65536:
    raise SystemExit("bad code field")
open(f"{work}/code.py", "w").write(code)
PYEOF
    then
        python3 - "$work" "$RESULTS/$name" <<'PYEOF'
import json, sys
work, dest = sys.argv[1], sys.argv[2]
try:
    sub = json.load(open(f"{work}/submission.json"))
except Exception:
    sub = {}
out = {"id": sub.get("id"), "player_uuid": sub.get("player_uuid"),
       "player_name": sub.get("player_name"),
       "status": "error", "error": "invalid submission"}
json.dump(out, open(dest + ".tmp", "w"))
PYEOF
        mv -- "$RESULTS/$name.tmp" "$RESULTS/$name"
        chown 1000:1000 -- "$RESULTS/$name"
        rm -rf -- "$work"
        continue
    fi

    rc=0
    timeout --kill-after=5s 240s docker run --rm \
        --network none \
        --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges \
        --memory 1g --memory-swap 1g --cpus 1 --pids-limit 64 \
        --read-only --tmpfs /tmp:size=64m \
        -v "$SIM":/sim:ro \
        -v "$work":/job \
        "$IMAGE" \
        python /sim/simulate.py --code /job/code.py --track /sim/track_meta.json \
            --out /job/out.json >/dev/null 2>&1 || rc=$?

    python3 - "$work" "$RESULTS/$name" "$rc" <<'PYEOF'
import json, os, sys
work, dest, rc = sys.argv[1], sys.argv[2], int(sys.argv[3])
sub = json.load(open(f"{work}/submission.json"))
out_path = f"{work}/out.json"
if rc in (124, 137):
    result = {"status": "error", "error": "timeout: your run took too long to simulate"}
elif rc != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) > 5_000_000:
    result = {"status": "error", "error": "simulator crashed"}
else:
    try:
        result = json.load(open(out_path))
    except Exception:
        result = {"status": "error", "error": "simulator produced invalid output"}
result["id"] = sub.get("id")
result["player_uuid"] = sub.get("player_uuid")
result["player_name"] = sub.get("player_name")
json.dump(result, open(dest + ".tmp", "w"))
PYEOF
    mv -- "$RESULTS/$name.tmp" "$RESULTS/$name"
    chown 1000:1000 -- "$RESULTS/$name"
    rm -rf -- "$work"
done
