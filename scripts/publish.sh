#!/usr/bin/env bash
# Publish a public-safe snapshot of this recipe to GitHub.
#
# `trmnlp push` writes your live plugin's numeric id back into src/settings.yml.
# That id is a deployment detail for *your* instance, not part of the recipe, so
# it is stripped from the published tree — otherwise every clone would try to
# update your plugin instead of creating its own.
#
# This script deliberately contains no deployment values of its own: the tokens
# to scrub are read from DEPLOYMENT.local.md, which is gitignored and never
# published. Add your own ids, hostnames and handles there.
#
# Usage: scripts/publish.sh [owner/repo]   (default: steveafrost/trmnl-wallet-deliveries)
set -euo pipefail

REPO="${1:-steveafrost/trmnl-wallet-deliveries}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

rsync -a \
  --exclude .git --exclude _build --exclude .trmnlp \
  --exclude DEPLOYMENT.local.md --exclude 'preview-*.png' --exclude '__pycache__' \
  --exclude '*.unsigned.shortcut' \
  "$SRC"/ "$STAGE"/

# strip the deployment-only plugin id
sed -i '' '/^id: /d' "$STAGE/src/settings.yml"

# sanity: nothing personal or deployment-specific may survive into the public
# tree. Two tiers — values that are never legitimate anywhere, and the shapes a
# leaked instance id actually takes (an `id:` line, a plugin_settings URL). A
# blanket digit rule is deliberately avoided: realistic sample tracking numbers
# are digits too, and a guard that cries wolf gets switched off.
universal=( 'user_[A-Za-z0-9]{6}' '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' )
content=( '^id: [0-9]{4,}' 'plugin_settings/[0-9]{4,}' 'devices/[0-9]{3,}' )
if [[ -f "$SRC/DEPLOYMENT.local.md" ]]; then
  while IFS= read -r token; do
    [[ -n "$token" ]] && universal+=( "$token" )
  done < <(grep -oE '[0-9]{5,}|[a-z0-9-]+\.(ts\.net|local|lan|internal)|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+' \
             "$SRC/DEPLOYMENT.local.md" | sort -u)
fi

leak=0
for pattern in "${universal[@]}"; do
  if grep -rInE --exclude-dir=.git --exclude=publish.sh "$pattern" "$STAGE"; then leak=1; fi
done
for pattern in "${content[@]}"; do
  if grep -rInE --exclude-dir=.git --exclude=publish.sh \
       --include='*.yml' --include='*.liquid' --include='*.json' --include='*.md' \
       "$pattern" "$STAGE"; then leak=1; fi
done
if [[ "$leak" -ne 0 ]]; then
  echo "refusing to publish: the matches above are personal or deployment values" >&2
  exit 1
fi

cd "$STAGE"
git init -q -b main
git add -A
name="$(git config --get user.name || echo 'Steve Frost')"
email="$(git config --get user.email || echo 'steve@steveafrost.com')"
git -c user.name="$name" -c user.email="$email" \
    commit -q -m "Wallet Deliveries for TRMNL — $(date -u +%Y-%m-%d)"

if ! gh repo view "$REPO" >/dev/null 2>&1; then
  gh repo create "$REPO" --public \
    --description "TRMNL e-ink delivery board fed by Apple Wallet order tracking via an iPhone Shortcut"
fi

git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/${REPO}.git"
git push -f origin main

echo "published: https://github.com/${REPO}"
