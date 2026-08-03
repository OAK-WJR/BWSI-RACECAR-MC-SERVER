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

## MIT campus (1:1)

A second world, `campus`, holds a 1:1 rebuild of MIT. One block is one metre.
Get there with `/mvtp campus`; it is creative and separate from the survival
world.

The Stata Center interior is generated, not hand-built. MIT CSAIL published the
as-built floor plans as part of the [Stata Center Data Set](https://projects.csail.mit.edu/stata/)
(CC BY 3.0): 15 floors of room polygons carrying the real MIT room numbers, room
types, and the doorways between them.

```bash
./scripts/build_stata.sh    # regenerate and place all 15 floors
```

Everything is anchored on one origin — the centroid of the Stata floor 1
outline. Use it for every other building or the pieces will not line up:

```
source CRS  EPSG:26786 (NAD27 / Massachusetts Mainland)
origin      x=710545.124 y=496378.473, mapped to campus (0, 64, 0)
storeys     5 blocks apart, ground floor slab at y=64
```

Going through the CRS matters: OSM is WGS84, and skipping the NAD27 datum shift
puts the floor plans 35 m east of the building.

Buildings 33 and 9 have no published interior data, so those are hand-built.
Only the CSAIL plans are CC BY — do not put MIT-internal floor plans in this
repo.

The campus world is deliberately **not** tracked in git: a 1:1 campus would burn
the LFS quota. The hourly backup container still covers it.

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
