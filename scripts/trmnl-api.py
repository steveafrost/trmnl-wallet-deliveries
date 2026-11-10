#!/usr/bin/env python3
"""Talk to the TRMNL API using the key trmnlp already saved.

Reads ~/.config/trmnlp/config.yml (or $TRMNL_API_KEY) and never prints the key.
Standard library only, so it runs on any macOS python3.

Usage:
  scripts/trmnl-api.py settings                     # my plugin settings (instances)
  scripts/trmnl-api.py plugins                      # plugins available to install (find private_plugin)
  scripts/trmnl-api.py details <plugin_setting_id>  # one instance's details, incl. webhook uuid
  scripts/trmnl-api.py data <plugin_setting_id> <sample.json>
  scripts/trmnl-api.py merge-vars <plugin_setting_id>
  scripts/trmnl-api.py refresh <plugin_setting_id>
  scripts/trmnl-api.py screenshot <plugin_setting_id>
"""
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://trmnl.com/api"
CONFIG = pathlib.Path.home() / ".config" / "trmnlp" / "config.yml"


def api_key() -> str:
    if os.environ.get("TRMNL_API_KEY"):
        return os.environ["TRMNL_API_KEY"].strip()
    if not CONFIG.exists():
        sys.exit("no API key: run `trmnlp login` or set TRMNL_API_KEY")
    match = re.search(r"api_key:\s*['\"]?([^'\"\s]+)", CONFIG.read_text())
    if not match:
        sys.exit("could not parse api_key from ~/.config/trmnlp/config.yml")
    return match.group(1)


def call(method: str, path: str, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "trmnl-wallet-deliveries/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            raw = json.loads(raw)
        except Exception:
            pass
        return exc.code, raw


def find_instance(psid: str):
    _, listing = call("GET", "/plugin_settings")
    for item in (listing or {}).get("data", listing if isinstance(listing, list) else []):
        if str(item.get("id")) == str(psid):
            return item
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]

    if cmd == "settings":
        status, body = call("GET", "/plugin_settings")
        print("HTTP", status)
        rows = body.get("data", body) if isinstance(body, dict) else body
        for item in rows or []:
            print(f"  {item.get('id')}\t{item.get('name')}\tstrategy={item.get('strategy')}\tuuid={item.get('uuid')}")
        return 0

    if cmd == "plugins":
        status, body = call("GET", "/plugins")
        print("HTTP", status)
        rows = body.get("data", body) if isinstance(body, dict) else body
        for item in rows or []:
            if "private" in str(item.get("keyname", "")):
                print(f"  {item.get('id')}\t{item.get('keyname')}\t{item.get('name')}")
        print(f"  (total plugins: {len(rows or [])})")
        return 0

    if cmd == "details":
        psid = sys.argv[2]
        status, body = call("GET", f"/plugin_settings/{psid}/details")
        print("HTTP", status)
        print(json.dumps(body, indent=2)[:3000])
        return 0

    if cmd == "data":
        psid, sample = sys.argv[2], sys.argv[3]
        payload = json.load(open(sample))
        status, body = call("POST", f"/plugin_settings/{psid}/data", {"merge_variables": payload})
        print("HTTP", status, json.dumps(body)[:400] if body else "")
        return 0 if status in (200, 201, 204) else 1

    if cmd == "merge-vars":
        status, body = call("GET", f"/plugin_settings/{sys.argv[2]}/merge_variables")
        print("HTTP", status)
        print(json.dumps(body, indent=2)[:2500])
        return 0

    if cmd == "refresh":
        status, body = call("POST", f"/plugin_settings/{sys.argv[2]}/refreshes", {})
        print("HTTP", status, json.dumps(body)[:400] if body else "")
        return 0

    if cmd == "screenshot":
        psid = sys.argv[2]
        out = sys.argv[3] if len(sys.argv) > 3 else "screen-preview.png"
        status, body = call("POST", f"/plugin_settings/{psid}/screenshots", {})
        print("start HTTP", status, json.dumps(body)[:300] if body else "")
        sid = (
            (body or {}).get("id")
            or ((body or {}).get("data") or {}).get("id")
            or ((body or {}).get("data") or {}).get("job_id")
        )
        if not sid:
            return 1
        for _ in range(20):
            time.sleep(3)
            st, res = call("GET", f"/plugin_settings/{psid}/screenshots/{sid}")
            blob = ((res or {}).get("data") or {}).get("preview_base64") or (res or {}).get("preview_base64")
            if blob:
                import base64
                raw = base64.b64decode(blob)
                pathlib.Path(out).write_bytes(raw)
                print(f"render ready: wrote {out} ({len(raw)} bytes)")
                return 0
            status_text = ((res or {}).get("data") or {}).get("status") or (res or {}).get("status")
            if status_text in ("failed", "error"):
                print("render failed:", json.dumps(res)[:400])
                return 1
        print("timed out waiting for render")
        return 1

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
