# Wallet Deliveries for TRMNL

An e-ink delivery board fed by **Apple Wallet's order tracking** on iOS 27 — no Parcel account, no email scanner, no server.

```
iPhone notification (Wallet / carrier)
        │  Shortcuts automation, runs immediately
        ▼
Shortcut: parse → merge into stored list → trim
        │  POST { merge_variables: ... }
        ▼
TRMNL private plugin (webhook strategy) → 800×480 screen
```

## Why this shape

Wallet's order tracking is on-device Apple Intelligence reading Mail. Apple exposes **no API and no Shortcuts action** that enumerates the Orders list, so nothing can pull Wallet's list directly. What iOS 27 does expose is the **notification automation**: when Wallet posts a delivery update, a Shortcut can read the notification's title/subtitle/body and forward it.

That means two consequences designed into this repo:

1. **The list lives on the phone.** iOS 27 Shortcuts' **Storage** actions persist a value across runs (synced via iCloud), so the Shortcut keeps the delivery array, upserts by tracking number, and posts the whole array each time. A naive `merge_strategy: stream` would stack duplicate copies of the same package instead of updating its status.
2. **Payloads stay small.** TRMNL accepts 2KB per webhook (5KB on TRMNL+) and 12 posts/hour (30 on TRMNL+). The sender caps at 8 deliveries with short fields; the plugin validates that ceiling in CI.

## Files

```text
src/settings.yml           plugin recipe: strategy, custom fields
src/full.liquid            800×480 — Arriving / On the way / Delivered
src/half_horizontal.liquid 800×240
src/half_vertical.liquid   400×480
src/quadrant.liquid        400×240
src/shared.liquid          shared templates (item, line, count, empty, title bar)
samples/                   payloads used for local rendering
scripts/validate-plugin.rb local render + payload size check
SHORTCUT.md                the iPhone side, action by action
.trmnlp.yml                local preview variables
```

## Payload contract

```json
{
  "merge_variables": {
    "updated": "Sep 22, 2:05 PM",
    "deliveries": [
      {
        "merchant": "Amazon",
        "status": "out_for_delivery",
        "eta": "Today by 9 PM",
        "carrier": "USPS",
        "tracking": "…4821",
        "note": "Out for delivery"
      }
    ]
  }
}
```

`status` is normalized to one of `ordered`, `in_transit`, `out_for_delivery`, `delayed`, `delivered`. Anything unrecognized renders as "Update" rather than breaking the screen.

## Local checks

```sh
ruby scripts/validate-plugin.rb   # renders every layout against every sample
trmnlp lint                       # TRMNL's own recipe lint
trmnlp serve                      # live preview at http://localhost:4567
trmnlp push --force               # upload to trmnl.com (needs TRMNL_API_KEY)
```

## Install

1. `trmnlp push` creates the private plugin on trmnl.com (`src/settings.yml` must **not** carry an `id` on first push; it does after that).
2. Open the plugin instance, copy the **Webhook URL**.
3. Build the Shortcut from `SHORTCUT.md` and paste the URL into the final POST action.
4. Add the plugin to a Playlist so the device requests it.
