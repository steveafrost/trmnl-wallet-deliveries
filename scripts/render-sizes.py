#!/usr/bin/env python3
"""Preview-render every layout size of a TRMNL plugin instance.

Usage: scripts/render-sizes.py <plugin_setting_id> [prefix]
Writes preview-<size>.png for markup_full / half_horizontal / half_vertical / quadrant.
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

PSID = sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: render-sizes.py <plugin_setting_id> [prefix]")
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "preview"
SIZES = ["markup_full", "markup_half_horizontal", "markup_half_vertical", "markup_quadrant"]


def dims(raw: bytes):
    return struct.unpack(">II", raw[16:24])


for size in SIZES:
    status, res = tapi.call("POST", f"/plugin_settings/{PSID}/screenshots", {"size": size})
    job = (res or {}).get("data", {}).get("job_id") if isinstance(res, dict) else None
    if not job:
        print(f"{size:24s} HTTP {status} no job: {json.dumps(res)[:160]}")
        continue
    for _ in range(10):
        time.sleep(3)
        _, poll = tapi.call("GET", f"/plugin_settings/{PSID}/screenshots/{job}")
        blob = ((poll or {}).get("data") or {}).get("preview_base64")
        if blob:
            raw = base64.b64decode(blob)
            width, height = dims(raw)
            out = pathlib.Path(f"{PREFIX}-{size.replace('markup_', '')}.png")
            out.write_bytes(raw)
            print(f"{size:24s} {width}x{height}  {out.name} ({len(raw)} bytes)")
            break
        state = ((poll or {}).get("data") or {}).get("status")
        if state in ("failed", "error"):
            print(f"{size:24s} render failed: {json.dumps(poll)[:200]}")
            break
    else:
        print(f"{size:24s} timed out")
