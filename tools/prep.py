"""Builds data/zones.js and data/stops.js from raw/zones2026.geojson and raw/hsl.zip (HSL GTFS).

Run from the project folder:  python -I tools/prep.py
"""
import csv
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
RAW = ROOT / "raw"
OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)

MODES = {"0": "tram", "1": "metro", "3": "bus", "4": "ferry", "109": "train", "2": "train", "700": "bus", "704": "bus", "900": "tram"}


def point_in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def round_coords(c):
    if isinstance(c[0], (int, float)):
        return [round(c[0], 5), round(c[1], 5)]
    return [round_coords(x) for x in c]


# --- zones -----------------------------------------------------------------
zones = json.load(open(RAW / "zones2026.geojson", encoding="utf-8"))
features = []
for f in zones["features"]:
    g = f["geometry"]
    features.append({
        "type": "Feature",
        "properties": {"zone": f["properties"].get("zone") or f["properties"].get("Zone")},
        "geometry": {"type": g["type"], "coordinates": round_coords(g["coordinates"])},
    })
zone_fc = {"type": "FeatureCollection", "features": features}

# --- stops -----------------------------------------------------------------
z = zipfile.ZipFile(RAW / "hsl.zip")
raw_stops = list(csv.DictReader(io.TextIOWrapper(z.open("stops.txt"), encoding="utf-8-sig")))
stops = []
for s in raw_stops:
    if s["location_type"].strip() != "0" or s["zone_id"] not in "ABCDE" or len(s["zone_id"]) != 1:
        continue
    stops.append([
        s["stop_name"].strip(),
        s["stop_code"].strip(),
        round(float(s["stop_lat"]), 6),
        round(float(s["stop_lon"]), 6),
        s["zone_id"],
        MODES.get(s["vehicle_type"].strip(), "bus"),
        s["stop_id"].strip(),
    ])

# --- consistency check: polygon zone vs. GTFS zone --------------------------
def polygon_zones(lon, lat):
    hits = []
    for f in features:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            if point_in_ring(lon, lat, poly[0]) and not any(point_in_ring(lon, lat, h) for h in poly[1:]):
                hits.append(f["properties"]["zone"])
    return hits

agree = Counter()
mismatch = defaultdict(list)
for name, code, lat, lon, zone, mode, sid in stops:
    hits = polygon_zones(lon, lat)
    key = (zone, ",".join(sorted(set(hits))) or "-")
    agree[key] += 1
    if zone not in hits:
        mismatch[key].append(f"{name} {code}")

print("GTFS zone -> polygon hits:")
for k, v in sorted(agree.items()):
    print(f"  {k[0]} -> {k[1]:8} {v}")
for k, v in mismatch.items():
    print(" mismatch", k, len(v), v[:6])

# --- approximate area for E-zone stops the official layer does not cover (Järvenpää) ---
import math

def convex_hull(pts):
    pts = sorted(set(pts))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]

uncovered = [(lon, lat) for (_, _, lat, lon, zone, _, _) in stops if zone == "E" and "E" not in polygon_zones(lon, lat)]
if uncovered:
    lat0 = sum(p[1] for p in uncovered) / len(uncovered)
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    buffered = []
    for lon, lat in convex_hull(uncovered):
        for k in range(24):
            a = 2 * math.pi * k / 24
            buffered.append((lon + 600 * math.cos(a) / kx, lat + 600 * math.sin(a) / ky))
    ring = [[round(x, 5), round(y, 5)] for x, y in convex_hull(buffered)]
    ring.append(ring[0])
    features.append({
        "type": "Feature",
        "properties": {"zone": "E", "approx": True},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    })
    print("added approximate E area around", len(uncovered), "stops")

# --- label points: stops deepest inside their zone (far from other zones' stops) ---
import numpy as np

lat0 = 60.25
kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
xy = np.array([[s[3] * kx, s[2] * ky] for s in stops])
zone_arr = np.array([s[4] for s in stops])
labels = []
per_zone = {"A": 1, "B": 4, "C": 4, "D": 4, "E": 2}
for zone, n in per_zone.items():
    mine = np.where(zone_arr == zone)[0]
    other = xy[zone_arr != zone]
    depth = np.array([np.min(np.hypot(*(other - xy[i]).T)) for i in mine])
    picked = []
    for idx in np.argsort(-depth):
        p = xy[mine[idx]]
        if all(np.hypot(*(p - q)) > 14000 for q in picked):
            picked.append(p)
            s = stops[mine[idx]]
            labels.append([zone, s[2], s[3]])
        if len(picked) == n:
            break
print("labels", labels)
zone_fc["labels"] = labels

(OUT / "zones.js").write_text("window.HSL_ZONES=" + json.dumps(zone_fc, separators=(",", ":")) + ";\n", encoding="utf-8")
(OUT / "stops.js").write_text(
    "// [name, code, lat, lon, zone, mode, gtfsId]\nwindow.HSL_STOPS=" + json.dumps(stops, ensure_ascii=False, separators=(",", ":")) + ";\n",
    encoding="utf-8",
)
# --- meta: feed date and single-ticket prices, so the page never hard-codes them ---
feed = next(csv.DictReader(io.TextIOWrapper(z.open("feed_info.txt"), encoding="utf-8-sig")))
fares = {
    r["fare_id"]: float(r["price"])
    for r in csv.DictReader(io.TextIOWrapper(z.open("fare_attributes.txt"), encoding="utf-8-sig"))
}
meta = {
    "feedVersion": feed.get("feed_version", "").strip(),
    "prices": fares,
    "approxZones": sorted({f["properties"]["zone"] for f in features if f["properties"].get("approx")}),
}
(OUT / "meta.js").write_text("window.HSL_META=" + json.dumps(meta, separators=(",", ":")) + ";\n", encoding="utf-8")
print("meta", meta)

print(len(stops), "stops;", (OUT / "zones.js").stat().st_size, "B zones;", (OUT / "stops.js").stat().st_size, "B stops")
print(Counter(s[5] for s in stops))
print([s for s in stops if "Riipil" in s[0] or "ntie" in s[0]][:3])
