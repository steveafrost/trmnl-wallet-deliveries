#!/usr/bin/env python3
"""Generate a signed .shortcut for the optional Mail poller ("Delivery Poller").

Companion to make-shortcut.py (whose encoding helpers this imports — same
proven encodings, not reinvented). Where the notification shortcut is fed by
Wallet/Mail *notification* automations, the poller needs no notifications at
all: a Time of Day automation runs it, it searches Mail directly, and it
mute-immune.

Design (v1, deliberately simple):
  * One "Find Mail Messages" branch per status phrase, subject-only, last
    2 days, all accounts, limit 10.
  * Only the newest message of each branch becomes an event (the board is
    one-row-per-merchant newest-wins anyway, and skipping per-message loops
    avoids repeat-loop encodings).
  * Status phrase is the search term itself — no matching needed.
  * Merchant/carrier/tracking regexes are identical to the production
    shortcut's, run over the message.
  * One POST per branch (5 per poll) — far under TRMNL's 12 posts/hour cap
    at sane poll frequencies. Stream strategy appends; the plugin markup
    dedupes rows per merchant and stream_limit churns the repeats.

Unverified-action risk lives in two places (mail search params, message
stringification); the shortcut ends with Show Result so an editor run shows
what was posted, and the webhook URL can be read back anonymously to verify.

Usage:
  python3 make-poller.py <out.shortcut>
"""
import importlib.util
import pathlib
import plistlib
import subprocess
import sys
import uuid

_HERE = pathlib.Path(__file__).parent
_spec = importlib.util.spec_from_file_location("make_shortcut", _HERE / "make-shortcut.py")
assert _spec is not None and _spec.loader is not None  # sibling module always exists
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)

WEBHOOK_URL = "https://trmnl.com/api/custom_plugins/f6fc915d-e896-4a7a-97a0-a2317c33d9dd"
STREAM_LIMIT = 20
SEARCH_DAYS = 2
RESULT_LIMIT = 10

# (search text, display phrase) — display phrase maps to the plugin's buckets
# (delayed -> issue, out for delivery/arriving -> today, shipped -> moving,
# delivered -> delivered). Subject-only searching keeps marketing mail out.
BRANCHES = [
    ("out for delivery", "out for delivery"),
    ("arriving today", "arriving today"),
    ("has shipped", "shipped"),
    ("was delivered", "delivered"),
    ("delivery delayed", "delayed"),
]


def mail_search_action(u, phrase):
    return ms.act("mail.search", {
        "UUID": u,
        "WFActionParameterMailSearchAccount": "All Accounts",
        "WFActionParameterMailSearchAllAccounts": True,
        "WFActionParameterMailSearchMailboxes": [],
        "WFActionParameterMailSearchSubjects": True,
        "WFActionParameterMailSearchText": phrase,
        "WFActionParameterMailSearchFromDate": {
            "Value": {
                "Date": {"Type": "CurrentDate"},
                "WFTimeOffset": {"Type": "Add", "Value": "-%d.000000" % SEARCH_DAYS, "Unit": "days"},
            },
            "WFSerializationType": "WFTimeOffsetParameterState",
        },
        "WFSearchResultLimitEnabled": True,
        "WFSearchResultLimit": RESULT_LIMIT,
    })


def message_variable(u, name):
    """A variable referencing an action's output, as Match Text input."""
    return {"Value": ms.action_output(u, name),
            "WFSerializationType": "WFTextTokenAttachment"}


def branch(u_uid, search_text, display_phrase):
    """One status phrase -> find newest message -> POST one event."""
    u_mail, u_item, u_merchant, u_carrier, u_tracking, u_post = (str(uuid.uuid4())
                                                                 for _ in range(6))
    mail_out = message_variable(u_mail, "Mail Messages")
    item_out = message_variable(u_item, "Mail Message")

    actions = [
        mail_search_action(u_mail, search_text),
        ms.act("getitemfromlist", {"UUID": u_item, "WFInput": mail_out}),
        # First Item is the action's default, so no range param — one less
        # unverified encoding.
        ms.act("text.match", {"UUID": u_merchant, "WFInput": item_out,
                              "WFMatchTextCaseSensitive": False,
                              "WFMatchTextPattern": ms.MERCHANT_PATTERN}),
        ms.act("text.match", {"UUID": u_carrier, "WFInput": item_out,
                              "WFMatchTextCaseSensitive": False,
                              "WFMatchTextPattern": ms.CARRIER_PATTERN}),
        ms.act("text.match", {"UUID": u_tracking, "WFInput": item_out,
                              "WFMatchTextCaseSensitive": False,
                              "WFMatchTextPattern": ms.TRACKING_PATTERN}),
    ]

    event = ms.kv_dictionary(None, [
        ms.kv_string("merchant", "", variable=ms.action_output(u_merchant)),
        ms.kv_string("phrase", display_phrase),
        ms.kv_string("carrier", "", variable=ms.action_output(u_carrier)),
        ms.kv_string("tracking", "", variable=ms.action_output(u_tracking)),
    ])
    body = [
        ms.kv_dictionary("merge_variables", [ms.kv_array("events", [event])]),
        ms.kv_string("merge_strategy", "stream"),
        ms.kv_number("stream_limit", STREAM_LIMIT),
    ]
    actions.append(ms.act("downloadurl", {
        "UUID": u_post,
        "WFURL": ms.token(WEBHOOK_URL),
        "WFHTTPMethod": "POST",
        "WFHTTPBodyType": "JSON",
        "WFJSONValues": ms.dictionary_param(body),
    }))
    return actions


def build():
    actions = []
    for i, (search_text, display_phrase) in enumerate(BRANCHES):
        actions.extend(branch("%s-%d" % (search_text, i), search_text, display_phrase))
    actions.append(ms.act("showresult", {
        "UUID": str(uuid.uuid4()),
        "Text": ms.token("Delivery Poller finished: %d phrase branches posted" % len(BRANCHES)),
    }))
    return {
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "3300",
        "WFWorkflowIcon": {"WFWorkflowIconGlyphNumber": 59511,
                           "WFWorkflowIconStartColor": 4282601983},
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowTypes": [],
    }


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "shortcuts/Delivery Poller.shortcut")
    wf = build()
    unsigned = out.with_name(out.stem + ".unsigned.shortcut")
    with open(unsigned, "wb") as fh:
        plistlib.dump(wf, fh)
    res = subprocess.run(["shortcuts", "sign", "--mode", "anyone",
                          "--input", str(unsigned), "--output", str(out)],
                         capture_output=True, text=True)
    print("sign rc=%s %s" % (res.returncode, (res.stdout + res.stderr).strip()[:300]))
    if out.exists():
        print("wrote %s (%d bytes)" % (out, out.stat().st_size))
    return 0 if out.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
