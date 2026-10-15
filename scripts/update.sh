#!/usr/bin/env bash
# Updates the server checkout to the latest main and recreates the comida container. Run it on the server, from
# the checkout: scripts/update.sh
# A plain `git pull` fails once the app has rewritten a tracked file such as mappings.json; this keeps those edits.
#
# UPDATE_WAIT_MIN  how long to wait for a running week analysis before giving up (default 15)
set -euo pipefail

wait_min=${UPDATE_WAIT_MIN:-15}
dir=$(cd "$(dirname "$0")/.." && pwd)
cd "$dir"

# Tracked files the app rewrites while it runs (mounted into the container in docker-compose.yml). On the server
# they hold the household's real state, so the server copy wins over the one in git.
state=(mappings.json garde-manger.txt courses-hebdo.txt data/validation_session.json docs/index.html exports/semaine.txt)
excludes=()
for f in "${state[@]}"; do excludes+=(":(exclude)$f"); done

in_comida() { docker compose exec -T comida python -c "$1"; }

# The checkout must be main with no edits to tracked code, so the fast-forward can't fail halfway or overwrite them.
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "$dir is not on main"; exit 1; }
git diff --quiet HEAD -- . "${excludes[@]}" || { echo "$dir has uncommitted changes to tracked files"; exit 1; }

prev=$(git rev-parse HEAD)
git fetch --quiet origin main
sha=$(git rev-parse origin/main)
if git merge-base --is-ancestor "$sha" "$prev"; then
    echo "$dir already has $sha"
    exit 0
fi

# A restart kills a running week analysis, so wait for it to end.
deadline=$((SECONDS + wait_min * 60))
while :; do
    status=$(in_comida "import json, urllib.request as u; j = json.load(u.urlopen('http://127.0.0.1:8765/api/jobs', timeout=5))['job']; print(j['status'] if j else 'none')" 2>/dev/null || echo none)
    [ "$status" != running ] && break
    if [ $SECONDS -ge $deadline ]; then
        echo "a week analysis is still running after $wait_min min. Nothing updated; run this again once it finishes."
        exit 1
    fi
    echo "waiting for the week analysis to finish"
    sleep 20
done

# Copies of data/ and the state files, so a bad version that breaks them can be undone by hand. 10 kept.
mkdir -p data/backups
name="data/backups/preupdate-$(date +%Y-%m-%d-%H%M%S)-${prev:0:7}.tgz"
existing=()
for f in "${state[@]}"; do [ -e "$f" ] && existing+=("$f"); done
tar czf "$name" --exclude=data/backups data "${existing[@]}"
echo "backed up data/ and the state files to $name"
old=(data/backups/preupdate-*.tgz)  # sorted by name, which starts with the date
if [ ${#old[@]} -gt 10 ]; then rm -- "${old[@]:0:${#old[@]}-10}"; fi

# Set aside the state files the app changed, give git the committed versions, and put the server copies back
# after each checkout. Unchanged ones follow git.
keep=$(mktemp -d)
trap 'rm -rf "$keep"' EXIT
changed=()
for f in "${state[@]}"; do
    if [ -e "$f" ] && ! git diff --quiet HEAD -- "$f"; then
        changed+=("$f")
        mkdir -p "$keep/$(dirname "$f")"
        cp -p "$f" "$keep/$f"
    fi
done
restore() {
    for f in "${changed[@]}"; do mkdir -p "$(dirname "$f")"; cp -p "$keep/$f" "$f"; done
}
if [ ${#changed[@]} -gt 0 ]; then git checkout --quiet HEAD -- "${changed[@]}"; fi

echo "updating $prev -> $sha"
git merge --ff-only --quiet "$sha"
restore
# Checkout replaces files, and a file bind mount keeps pointing at the old one, so the container is always
# recreated. --wait returns once it passes its healthcheck, and fails if it doesn't within the timeout.
if docker compose up -d --build --force-recreate --wait --wait-timeout 180; then
    docker image prune -f >/dev/null  # each build leaves the previous image behind
    echo "updated to $sha"
    exit 0
fi

echo "the new version failed its healthcheck, rolling back to $prev"
git reset --hard --quiet "$prev"
restore
docker compose up -d --build --force-recreate --wait --wait-timeout 180 || echo "the rollback is unhealthy too, check: docker compose logs"
exit 1
