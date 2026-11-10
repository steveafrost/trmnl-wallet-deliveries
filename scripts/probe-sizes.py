#!/usr/bin/env python3
"""Probe whether TRMNL's preview render accepts a size selector.

Renders the instance several times with different candidate bodies and reports
the pixel dimensions of each returned PNG, saving them for visual review.
"""
import base64
import importlib.util
import json
import pathlib
import struct
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("tapi", HERE / "trmnl-api.py")
tapi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tapi)

PSID = sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: probe-sizes.py <plugin_setting_id>")
CANDIDATES = [
    ("default", {}),
    ("size-quadrant", {"size": "quadrant"}),
    ("view-quadrant", {"view": "quadrant"}),
    ("layout-quadrant", {"layout": "quadrant"}),
    ("sizes-quadrant", {"sizes": ["quadrant"]}),
    ("size-half_horizontal", {"size": "half_horizontal"}),
]


def dims(raw: bytes):
    return struct.unpack(">II", raw[16:24])


for label, body in CANDIDATES:
    status, res = tapi.call("POST", f"/plugin_settings/{PSID}/screenshots", body)
    job = (res or {}).get("data", {}).get("job_id") if isinstance(res, dict) else None
    if not job:
        print(f"{label:22s} HTTP {status} no job: {json.dumps(res)[:140]}")
        continue
    time.sleep(4)
    _, poll = tapi.call("GET", f"/plugin_settings/{PSID}/screenshots/{job}")
    blob = ((poll or {}).get("data") or {}).get("preview_base64")
    if not blob:
        print(f"{label:22s} no image: {json.dumps(poll)[:140]}")
        continue
    raw = base64.b64decode(blob)
    width, height = dims(raw)
    out = pathlib.Path(f"preview-{label}.png")
    out.write_bytes(raw)
    print(f"{label:22s} {width}x{height}  {out.name}  ({len(raw)} bytes)")
