# BWSI Racecar — Minecraft Server

Open building server. Anyone with a Minecraft account can join and build.

## Join

- **Address:** `66.94.124.157`
- **Server:** Paper 26.1.2 (newer clients work via ViaVersion)

No whitelist and no password. On your first moments in you are asked a couple
of questions; until you answer them the screen stays dark and you cannot move
or build. The questions and answers live in `data/plugins/EntryGate/config.yml`
on the server and are deliberately not in this repo — the shipped template is
empty, so a fresh checkout leaves the gate open.

## Racing

Write Python that drives the racecar, put it in a book, hold the book and run
`/race submit`. Your lap is simulated, replayed on the track in the `test`
world for everyone to watch, and your best time goes on the leaderboard.

```python
rc.set_speed(15.0, 1.91)   # metres per second, steering in degrees
rc.wait(120)               # hold those controls
```

`/race top` prints the ranking; the hologram in the lobby shows it too.

Submitted code never runs on the server. It runs on the host in a throwaway
container with no network, a read-only filesystem, and cpu, memory and time
limits — see `scripts/race-runner.sh`. The simulator behind it is pluggable:
`sim/README.md` documents the contract.

Regenerate the track (and the matching `sim/track.json`) with:

```bash
python3 scripts/gen_track.py
docker exec minecraft rcon-cli "minecraft:reload"
docker exec minecraft rcon-cli "execute in minecraft:test run function bwsi:track"
```

## Rules

Build anywhere except spawn. Every block change is logged by CoreProtect and can be
rolled back per player, so griefing is undone rather than prevented. The world is
backed up hourly and kept for 7 days.

## Contributing

Anyone can open a pull request.

1. Fork this repo
2. Write your plugin under `plugins-src/<name>/` (copy `example-plugin` to start)
3. Open a PR — CI compiles it and attaches the jar
4. A maintainer reviews and merges, then deploys with `scripts/deploy.sh`

Plugins run arbitrary Java inside the server, so merges need a maintainer's review.
Target Paper 26.1.2 and Java 21.

## Layout

```
docker-compose.yml         production server
data/BWSI Racecar/         the world, overworld + nether + end
plugins-src/               plugin sources
scripts/snapshot-world.sh  commit the current world
scripts/deploy.sh          build plugins and deploy to production
scripts/mc-isolation.sh    container network isolation (systemd unit)
```

The world is tracked here. Region files are binary, so git cannot delta them
well and the repo grows with every snapshot — move to Git LFS once it nears 1 GB.

Everything else under `data/` is ignored, including `server.properties`, which
holds the RCON password. `.env` is ignored for the same reason.

## Deployment

`mc-auto-deploy.timer` polls GitHub every 5 minutes and deploys new plugin
builds. Nothing listens on a port for this — the host reaches out — so this adds
no inbound attack surface. Three gates before anything runs:

1. the remote must fast-forward; a rewritten or force-pushed `main` is refused
2. CI must have succeeded for that exact commit
3. the build happens in a separate clone (`/root/mc-deploy`) as uid 1000 with all
   capabilities dropped, so the live world is never touched

Merging to `main` therefore puts code on the server within 5 minutes. Protect the
branch and require review, or that gate is only a convention.

Compose changes are not applied automatically — deploys restart the server, they
do not re-create it. Run `docker compose up -d` by hand for those.

```bash
systemctl start mc-auto-deploy      # deploy now instead of waiting
journalctl -u mc-auto-deploy -n 50  # what happened
./scripts/deploy.sh                 # build and deploy the local tree
```

## World snapshots

```bash
./scripts/snapshot-world.sh          # pauses saves, commits, resumes saves
```

Committing a running world without pausing saves can capture a half-written
region file, so use the script rather than `git add` directly.

## Admin

Run on the host:

```bash
docker exec minecraft rcon-cli                            # console
docker exec minecraft rcon-cli "co lookup u:NAME t:7d"    # what did NAME change
docker exec minecraft rcon-cli "co rollback u:NAME t:2h"  # undo NAME's last 2h
docker compose restart mc
```
