#!/usr/bin/env bash
# Block the Minecraft container from reaching the host and other Docker networks.
# iptables rules do not survive a reboot, so mc-isolation.service reapplies this
# after Docker starts. Without it, community plugin code could reach the other
# services running on this host.
set -euo pipefail

NET=minecraft_mcnet

for _ in $(seq 1 30); do
    docker network inspect "$NET" >/dev/null 2>&1 && break
    sleep 2
done

subnet=$(docker network inspect "$NET" --format '{{(index .IPAM.Config 0).Subnet}}' 2>/dev/null || true)
gateway=$(docker network inspect "$NET" --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)
[ -n "$subnet" ] || { echo "network $NET not found"; exit 0; }

add() { iptables -C "$@" 2>/dev/null || iptables -I "$@"; }

add DOCKER-USER -s "$subnet" -d "$gateway" -p tcp -j DROP

for net in $(docker network ls --format '{{.Name}}' | grep -vE "^(host|none|$NET)$"); do
    for s in $(docker network inspect "$net" --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}' 2>/dev/null); do
        [ "$s" = "$subnet" ] || add DOCKER-USER -s "$subnet" -d "$s" -j DROP
    done
done

iptables -L DOCKER-USER -n
