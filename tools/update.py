"""Downloads the latest HSL fare zones and GTFS into raw/, then rebuilds data/ with prep.py.

Run from the project folder:  python -I tools/update.py
"""
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)

ARCGIS = "https://services1.arcgis.com/sswNXkUiRoWtrx0t/arcgis/rest/services"
GTFS_URL = "https://infopalvelut.storage.hsldev.com/gtfs/hsl.zip"
UA = {"User-Agent": "hsl-vyohykekartta/1.0"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def newest_zone_service():
    """HSL publishes a yearly layer (HSL_taksavyohykkeet_2026, ...); pick the newest one."""
    services = json.loads(get(f"{ARCGIS}?f=json"))["services"]
    yearly = sorted(
        (int(m.group(1)), s["name"])
        for s in services
        if s["type"] == "FeatureServer" and (m := re.fullmatch(r"HSL_taksavy(?:ö|o)hykkeet_(\d{4})", s["name"]))
    )
    if yearly:
        return yearly[-1][1]
    return "HSL_taksavyöhykkeet"


service = newest_zone_service()
query = urllib.parse.urlencode({"where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson"})
zones = json.loads(get(f"{ARCGIS}/{urllib.parse.quote(service)}/FeatureServer/0/query?{query}"))
found = sorted({f["properties"].get("zone") or f["properties"].get("Zone") for f in zones["features"]})
if not set("ABCD") <= set(found):
    sys.exit(f"Zone layer {service} looks wrong, zones found: {found}")
(RAW / "zones2026.geojson").write_text(json.dumps(zones), encoding="utf-8")
print(f"zones: {service} -> {found}")

data = get(GTFS_URL)
if len(data) < 10_000_000:
    sys.exit(f"GTFS download looks too small ({len(data)} bytes)")
(RAW / "hsl.zip").write_bytes(data)
print(f"gtfs: {len(data) / 1e6:.1f} MB")

subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "prep.py"), str(ROOT)], check=True)
