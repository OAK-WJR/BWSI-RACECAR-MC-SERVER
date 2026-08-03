# BWSI Racecar — Minecraft Server

Open building server. Anyone with a Minecraft account can join and build.

## Join

- **Address:** `66.94.124.157`
- **Server:** Paper 26.1.2 (newer clients work via ViaVersion)

No registration, no password, no whitelist. Just connect.

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
docker-compose.yml       production server
data/BWSI Racecar/       the world, overworld + nether + end
plugins-src/             plugin sources
scripts/snapshot-world.sh  commit the current world
scripts/deploy.sh        build plugins and deploy to production
scripts/mc-isolation.sh  container network isolation (installed as a systemd unit)
```

The world is tracked here. Region files are binary, so git cannot delta them
well and the repo grows with every snapshot — move to Git LFS once it nears 1 GB.

Everything else under `data/` is ignored, including `server.properties`, which
holds the RCON password. `.env` is ignored for the same reason.

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
