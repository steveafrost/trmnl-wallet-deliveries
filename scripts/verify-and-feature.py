#!/usr/bin/env python3
"""Pre-submission checks + recipe listing image, over the TRMNL API.

1. POST /api/plugin_settings/custom_fields/verifications — validates the recipe's
   custom_fields YAML the way the publish flow will, without saving.
2. PUT  /api/plugin_settings/<id>/featured_image — queues a render and attaches it
   as the image the recipe listing shows (the recipe preview image).

Extraction note: `trmnlp push` rewrites src/settings.yml, so the key order — and
therefore where custom_fields sits — is not stable. Always parse the file; never
slice it by position.

Usage: python3 verify-and-feature.py <plugin_setting_id> [src/settings.yml]
Never prints the API key.
"""
import json
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

PSID = sys.argv[1] if len(sys.argv) > 1 else sys.exit(
    "usage: verify-and-feature.py <plugin_setting_id> [src/settings.yml]")
SETTINGS = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "src/settings.yml")
BASE = "https://trmnl.com/api"


def api_key() -> str:
    cfg = pathlib.Path.home() / ".config/trmnlp/config.yml"
    return re.search(r"api_key:\s*['\"]?([^'\"\s]+)", cfg.read_text()).group(1)


def call(method: str, path: str, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + api_key(),
                 "Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "trmnl-wallet-deliveries/1.0"},
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


def custom_fields_yaml(path: pathlib.Path) -> str:
    """Re-serialise just the custom_fields list (PyYAML, or ruby if unavailable)."""
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(path.read_text())
        if not data.get("custom_fields"):
            sys.exit("no custom_fields in " + str(path))
        return yaml.safe_dump(data["custom_fields"], sort_keys=False, allow_unicode=True)
    except ImportError:
        code = ('require "yaml"\nd = YAML.safe_load(File.read(ARGV[0]))\n'
                'abort("no custom_fields") unless d["custom_fields"]\n'
                'puts d["custom_fields"].to_yaml')
        out = subprocess.run(["ruby", "-e", code, str(path)],
                             capture_output=True, text=True)
        if out.returncode != 0:
            sys.exit("could not parse YAML: " + (out.stderr or "").strip())
        return out.stdout


block = custom_fields_yaml(SETTINGS)
print("custom_fields: {} entries".format(len(re.findall(r"^- keyname:", block, re.M))))

status, body = call("POST", "/plugin_settings/custom_fields/verifications",
                    {"custom_fields": block})
print("custom_fields verification -> HTTP", status)
print(json.dumps(body, indent=2)[:800])
valid = bool((body or {}).get("data", {}).get("valid"))

status, body = call("PUT", f"/plugin_settings/{PSID}/featured_image")
print()
print("featured_image (recipe listing image) -> HTTP", status)
print(json.dumps(body, indent=2)[:400] if body else "")

sys.exit(0 if valid else 1)
