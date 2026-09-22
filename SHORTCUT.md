# iPhone side: Wallet → TRMNL

Nothing here runs on a server, and nothing here is hand-built: import the shortcut, paste one URL, add two automations. Requires iOS 27 on an Apple Intelligence iPhone (15 Pro or newer) and Wallet order tracking enabled: **Settings → Wallet & Apple Pay → Order Tracking → Mail** on. Leave Wallet's delivery notifications unmuted (per order: ⋯ → Mute Notifications) or there will be no events to forward.

## Part 1 — import the shortcut

`shortcuts/Wallet Deliveries.shortcut` in this repo. Open it on the phone (AirDrop, or Files → tap) → **Add Shortcut**.

Then edit the last action and replace `PASTE_YOUR_TRMNL_WEBHOOK_URL_HERE` with the **Webhook URL** from the plugin's settings page (`https://trmnl.com/api/custom_plugins/<uuid>`). That is the only field to touch.

### What the shortcut does

Four actions, in order:

1. **Text** — the notification text, taken from Shortcut Input.
2. **Match Text** — the status phrase (`out for delivery`, `delayed`, `delivered`, …).
3. **Match Text** — the merchant (the leading text before a colon).
4. **Match Text** ×2 — carrier and tracking number when the notification states them.
5. **Get Contents of URL** — POST to your webhook:

```json
{"merge_variables": {"events": [{"merchant": "Amazon", "phrase": "out for delivery",
                                 "carrier": "USPS", "tracking": "TBA123456789"}]},
 "merge_strategy": "stream", "stream_limit": 20}
```

One notification becomes one event. The shortcut keeps no state of its own — TRMNL appends each event to a rolling list of the last 20, and the plugin's markup reduces that list to one row per merchant, newest event winning. This is why the shortcut is four actions instead of the twenty-odd an on-phone array would need, and why nothing has to be seeded or migrated on first run.

## Part 2 — the automations

**A. Notification trigger**
- App: **Wallet**. Add a second copy for **Mail** — Amazon and some carriers only ever notify there.
- Filter: notification **contains any** of `shipped`, `out for delivery`, `arriving`, `delivered`, `delivery`, `package`, `order`.
- **Run Immediately** — turn off "Ask Before Running", or every package ping queues a prompt.

**B. Optional, Mail-only orders**
Nothing else is needed. There is deliberately no daily "refresh" automation: events carry no clock time, so reposting would only duplicate rows.

## Tuning without touching the shortcut

The plugin's settings page does the shaping:

| Field | Effect |
| --- | --- |
| Screen Title | Bottom bar label |
| Show Carrier | Carrier name on each row when the notification named one |
| Show Tracking | Tracking number tail — off by default, space is tight on e-ink |
| Hide Delivered | Drop delivered rows entirely |
| Max Deliveries | Row ceiling per column |

Status mapping lives in `src/shared.liquid`: `delayed`/`attempted` → issue, `out for delivery`/`arriving` → today, `shipped`/`in transit`/`on its way`/`order confirmed` → moving, `delivered` → delivered.

## Known limits

- **No backlog.** The first screen shows only what arrives after the automation is live. Wallet's history can't be imported — there's no export.
- **Wallet (or Mail) must be the notifier.** A package whose status only ever appeared in Mail produces no Wallet notification; that's what the second automation is for.
- **One row per merchant, newest event wins.** A merchant that ships three things shows once, with its latest status. That's a deliberate trade for the small screen — the stream keeps the history, the markup shows the headline.
- **Rate limit.** TRMNL accepts 12 posts/hour (30 on TRMNL+). Notification-driven posting sits far under it unless you're doing something unusual.
- **Regex, not a model.** The merchant is "text before the first colon" and the status is a keyword match, so an unusually-worded notification can produce a vague row (a status of "Update"). The plugin never invents data: a field the notification didn't state arrives empty and is not shown.
