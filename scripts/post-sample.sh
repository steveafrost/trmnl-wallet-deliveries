#!/usr/bin/env bash
# Post a sample payload to a live TRMNL private-plugin webhook, then read the
# merge variables back to prove the round trip. Verifies the 2KB ceiling first.
#
# Usage: scripts/post-sample.sh <webhook-url> [samples/mixed.json]
set -euo pipefail

URL="${1:?usage: post-sample.sh <webhook-url> [sample.json]}"
SAMPLE="${2:-samples/mixed.json}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="$ROOT/$SAMPLE"

[ -f "$FILE" ] || { echo "no such sample: $FILE" >&2; exit 1; }

BYTES=$(wc -c < "$FILE" | tr -d ' ')
echo "payload: $SAMPLE ($BYTES bytes)"
if [ "$BYTES" -gt 2048 ]; then
  echo "REFUSING: over TRMNL's 2048-byte webhook limit" >&2
  exit 1
fi

BODY=$(python3 -c 'import json,sys; print(json.dumps({"merge_variables": json.load(open(sys.argv[1]))}))' "$FILE")

echo "POST $URL"
CODE=$(curl -sS -o /tmp/trmnl-post-response.txt -w '%{http_code}' -X POST "$URL" \
  -H 'Content-Type: application/json' -d "$BODY")
echo "HTTP $CODE"
if [ "$CODE" = "429" ]; then
  echo "rate limited: 12 posts/hour (30 on TRMNL+). Enable Debug Logs or wait." >&2
fi
[ "$CODE" = "200" ] || { cat /tmp/trmnl-post-response.txt; exit 1; }

echo "GET merge variables back"
curl -sS "$URL" | python3 -m json.tool | head -40
