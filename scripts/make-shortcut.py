#!/usr/bin/env python3
"""Generate a signed .shortcut for the Wallet Deliveries plugin.

The shortcut is deliberately small and uses only long-standing actions (Text,
Match Text, Get Contents of URL) so it can also run on macOS 26 — which is what
makes it testable off an iPhone.

Every encoding here is copied from real exported shortcuts or from the
a2/swift-shortcuts generator, not invented:
  * variable reference    {"Type": "Variable", "VariableName": X}
  * shortcut input        {"Type": "Input", "VariableUUID": 00000000-...}
  * text with variables   WFTextTokenString + attachmentsByRange, U+FFFC mark
  * dictionary parameter  {"Value": {"WFDictionaryFieldValueItems": [...]},
                           "WFSerializationType": "WFDictionaryFieldValue"}
  * array item            {"WFItemType": 2,
                           "WFValue": {"Value": [...],
                                       "WFSerializationType": "WFArrayParameterState"}}
  * item types            0 string, 1 dictionary, 2 array, 3 number, 5 file

Payload posted (TRMNL stream strategy, so the plugin keeps the rolling list and
the phone needs no storage of its own):

  {"merge_variables": {"events": [{"merchant": …, "phrase": …}]},
   "merge_strategy": "stream", "stream_limit": 20}

Usage:
  python3 make-shortcut.py test <url> <out.shortcut> [--sample "text"]
  python3 make-shortcut.py production <out.shortcut>
"""
import plistlib
import subprocess
import sys
import uuid
import pathlib

A = "is.workflow.actions."
FFFC = "\ufffc"
INPUT_UUID = "00000000-0000-0000-0000-000000000000"
STREAM_LIMIT = 20

STATUS_PATTERN = ("delivered|out for delivery|delivery attempted|delayed|shipped|"
                  "in transit|on its way|arriving|order confirmed")
MERCHANT_PATTERN = "^[^:\\n,]{2,40}"
CARRIER_PATTERN = ("UPS|FedEx|USPS|DHL|OnTrac|LaserShip|Amazon Logistics|"
                   "Royal Mail|Canada Post")
TRACKING_PATTERN = "TBA[0-9]{9,}|[A-Z]{2}[0-9]{9}[A-Z]{2}|[0-9]{12,22}"


# ---------------------------------------------------------------- encodings
def act(identifier, params):
    return {"WFWorkflowActionIdentifier": A + identifier,
            "WFWorkflowActionParameters": params}


def text_action(u, value):
    return act("gettext", {"UUID": u, "WFTextActionText": value})


def token(value, variable=None):
    """A WFTextTokenString: literal text, optionally holding one variable."""
    if variable is None:
        return {"Value": {"string": value, "attachmentsByRange": {}},
                "WFSerializationType": "WFTextTokenString"}
    return {"Value": {"string": FFFC,
                      "attachmentsByRange": {"{0, 1}": variable}},
            "WFSerializationType": "WFTextTokenString"}


def action_output(u, name="Matches"):
    return {"Type": "ActionOutput", "OutputUUID": u, "OutputName": name}


def item(key, item_type, wf_value):
    entry = {"WFItemType": item_type, "WFValue": wf_value}
    if key is not None:
        entry["WFKey"] = token(key)
    return entry


def kv_string(key, value, variable=None):
    return item(key, 0, token(value, variable))


def kv_number(key, number):
    return item(key, 3, token(str(number)))


def kv_dictionary(key, entries):
    return item(key, 1, {"Value": {"WFDictionaryFieldValueItems": entries},
                         "WFSerializationType": "WFDictionaryFieldValue"})


def kv_array(key, elements):
    return item(key, 2, {"Value": elements,
                         "WFSerializationType": "WFArrayParameterState"})


def dictionary_param(entries):
    """A whole dictionary-typed action parameter (WFJSONValues and friends)."""
    return {"Value": {"WFDictionaryFieldValueItems": entries},
            "WFSerializationType": "WFDictionaryFieldValue"}


# ---------------------------------------------------------------- the shortcut
def build(sample_text, url, production):
    u_note, u_status, u_merchant, u_carrier, u_tracking = (str(uuid.uuid4())
                                                           for _ in range(5))
    actions = []

    # 1 - the notification text: Shortcut Input in production, a sample for tests
    if production:
        actions.append(text_action(u_note, {"Value": {"Type": "Input",
                                                      "VariableUUID": INPUT_UUID},
                                            "WFSerializationType": "WFTextTokenAttachment"}))
    else:
        actions.append(text_action(u_note, sample_text))

    note_out = {"Value": action_output(u_note, "Text"),
                "WFSerializationType": "WFTextTokenAttachment"}

    # 2-5 - pull the fields out of the notification text. Match Text returns an
    # empty list when nothing matches, which the token renders as an empty
    # string, so a missing carrier or tracking number is simply blank.
    for uid, pattern in ((u_status, STATUS_PATTERN), (u_merchant, MERCHANT_PATTERN),
                         (u_carrier, CARRIER_PATTERN), (u_tracking, TRACKING_PATTERN)):
        actions.append(act("text.match", {"UUID": uid, "WFInput": note_out,
                                          "WFMatchTextCaseSensitive": False,
                                          "WFMatchTextPattern": pattern}))

    # 6 - POST one event, streamed on TRMNL's side
    event = kv_dictionary(None, [
        kv_string("merchant", "", variable=action_output(u_merchant)),
        kv_string("phrase", "", variable=action_output(u_status)),
        kv_string("carrier", "", variable=action_output(u_carrier)),
        kv_string("tracking", "", variable=action_output(u_tracking)),
    ])

    body = [
        kv_dictionary("merge_variables", [kv_array("events", [event])]),
        kv_string("merge_strategy", "stream"),
        kv_number("stream_limit", STREAM_LIMIT),
    ]

    actions.append(act("downloadurl", {
        "UUID": str(uuid.uuid4()),
        "WFURL": url,
        "WFHTTPMethod": "POST",
        "WFHTTPBodyType": "JSON",
        "WFJSONValues": dictionary_param(body),
    }))

    return {
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "3300",
        "WFWorkflowIcon": {"WFWorkflowIconGlyphNumber": 59511,
                           "WFWorkflowIconStartColor": 4282601983},
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": ["WFStringContentItem",
                                              "WFDictionaryContentItem",
                                              "WFURLContentItem",
                                              "WFGenericFileContentItem"],
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowTypes": [],
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    mode, out = sys.argv[1], pathlib.Path(sys.argv[2])
    if mode == "test":
        url = sys.argv[3]
        sample = "Amazon: Your package is out for delivery, arriving today by 9 PM"
        if "--sample" in sys.argv:
            sample = sys.argv[sys.argv.index("--sample") + 1]
        wf = build(sample, url, production=False)
    elif mode == "production":
        wf = build("", "PASTE_YOUR_TRMNL_WEBHOOK_URL_HERE", production=True)
    else:
        print(__doc__)
        return 1

    unsigned = out.with_name(out.stem + ".unsigned.shortcut")
    with open(unsigned, "wb") as fh:
        plistlib.dump(wf, fh)
    res = subprocess.run(["shortcuts", "sign", "--mode", "anyone",
                          "--input", str(unsigned), "--output", str(out)],
                         capture_output=True, text=True)
    print("sign rc=%s %s" % (res.returncode, (res.stdout + res.stderr).strip()[:200]))
    if out.exists():
        print("wrote %s (%d bytes)" % (out, out.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
