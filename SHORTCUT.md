# iPhone side: Wallet → TRMNL

Nothing here runs on a server. One Shortcut plus two automations. Requires iOS 27, an Apple Intelligence iPhone (15 Pro or newer), and Wallet order tracking enabled: **Settings → Wallet & Apple Pay → Order Tracking → Mail** on. Also leave Wallet's delivery notifications unmuted (per order: ⋯ → Mute Notifications) or there will be no events to forward.

## Part 1 — the shortcut

Name it **Wallet Delivery Sync**.

**1. Get Value for "wallet_deliveries"** (Storage action, iOS 27)
→ variable `Stored`. First run returns nothing; treat that as an empty list.

**2. If `Stored` has any value → Get Dictionary from Input → Get value for key `deliveries`**
→ variable `Existing`. Seed it once by hand with an empty list; Storage keeps any type, lists included.

**3. Text** — build the model prompt input:
```
Title: [Shortcut Input Title]
Subtitle: [Shortcut Input Subtitle]
Body: [Shortcut Input Body]
```

**4. Use Model** (Apple Intelligence, iOS 27) with prompt:
```
Extract one delivery from this notification. Reply with JSON only, no prose, no code fence:
{"merchant":"short store name","status":"ordered|in_transit|out_for_delivery|delayed|delivered","eta":"short human text, e.g. Today by 9 PM or Sep 24","carrier":"USPS|UPS|FedEx|OnTrac|DHL|Amazon","tracking":"last 4 digits, prefixed with …","note":"max 6 words"}
Use an empty string for anything the notification does not state. Never invent a tracking number.
```
→ variable `Parsed Text`.

**5. Get Dictionary from Input** on `Parsed Text` → variable `New`. If this returns nothing (model emitted prose), fall back to the keyword mapping in Part 3 and continue with whatever fields you have.

**6. Set `New`'s `at` to** Current Date (ISO 8601) so the trim step can age entries out.

**7. Repeat with Each** in `Existing`, and inside the repeat:
- **If** the item's `tracking` equals `New`'s `tracking` **and** `tracking` is not empty → skip (this is the status-update case; the new entry replaces it)
- **Otherwise If** the item's `merchant` equals `New`'s `merchant` **and** `tracking` is empty for both → skip
- **Otherwise** → Add item to `Kept`

**8. Add `New`** to the front of `Kept` (newest first).

**9. Trim to 8** — Get First 8 Items of `Kept` → variable `Trimmed`.
(Dropping aged-out "delivered" rows is cheapest on the daily sweep, step 12.)

**10. Set Value for "wallet_deliveries"** = `Trimmed`.

**11. Get Contents of URL**
- URL: the plugin's **Webhook URL** (`https://trmnl.com/api/custom_plugins/<uuid>`)
- Method: **POST**, Request Body: **JSON**
- Body, exactly two keys:
  - `merge_variables` → dictionary with
    - `updated` → Current Date formatted `MMM d, h:mm a`
    - `deliveries` → `Trimmed`
- No `merge_strategy` key: the Shortcut owns the whole array, so TRMNL should replace, not append.

**12. Optional rate guard** (recommended: TRMNL allows 12 posts/hour, 30 on TRMNL+)
Store `last_post_at` alongside; if fewer than 5 minutes have passed, end the shortcut after step 10 — storage is already current, and the next event reposts.

## Part 2 — the automations

**A. Notification trigger** (iOS 27)
- App: **Wallet**. Add a second copy for **Mail** if your carriers notify there instead.
- Filter: notification **contains any** of `shipped`, `out for delivery`, `arriving`, `delivered`, `delivery`, `package`, `order`.
- **Run Immediately** — turn off "Ask Before Running", or every package ping queues a prompt.

**B. Time of Day trigger** (7:30 AM)
Same shortcut. Reposting the stored array daily refreshes relative ETAs ("Today" → "Sep 24" → "Delivered") even when no notification fires, and guarantees a fresh screen each morning.

## Part 3 — fallback mapping without Apple Intelligence

If you'd rather skip step 4, map the notification text with plain If/Contains and build the same dictionary:

| notification text contains | status |
| --- | --- |
| `delivered` | `delivered` |
| `out for delivery` | `out_for_delivery` |
| `delayed`, `weather`, `attempted` | `delayed` |
| `shipped`, `in transit`, `on its way` | `in_transit` |
| `order confirmed`, `we got your order` | `ordered` |

Merchant = first word of the notification title when it isn't `UPS`/`USPS`/`FedEx`. Cruder, but it removes the model call and works on any iPhone.

## Known limits

- **No backlog.** The first render shows only what arrives after the automation is live. Wallet's history can't be imported — there's no export.
- **Wallet must be the notifier.** A package whose status only ever appeared in Mail (Amazon, most often) produces no Wallet notification; add the Mail automation to catch those.
- **Array-of-one.** Shortcuts sometimes collapses a single-item list into a bare object. This plugin only ever reads arrays, so keep the body wrapped as a list (Storage's list type or an explicit List action).
- **2KB payload.** 8 deliveries with short fields runs ~1.2KB; if you widen the fields, re-run `scripts/validate-plugin.rb`, which fails on oversize samples.
