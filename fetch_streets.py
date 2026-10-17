#!/usr/bin/env python3
"""Download street names from OpenStreetMap (Overpass API) for a GML plan.

Computes the plan's bounding box, converts it to WGS84, queries Overpass for
named highways inside it, and saves a GeoJSON file with street geometries in
the plan's coordinate system (ready for `gml_viewer.py --streets`).

    python fetch_streets.py plan.gml -o streets.geojson
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
DEFAULT_HIGHWAYS = ("motorway|trunk|primary|secondary|tertiary|unclassified|"
                    "residential|living_street")


def _epsg_from_srs(srs: str | None) -> int | None:
    if not srs:
        return None
    codes = re.findall(r"(\d{4,5})", srs)
    for c in codes:
        if 2000 <= int(c) < 100000:
            return int(c)
    return None


def _overpass_query(url: str, query: str, timeout: int):
    data = urllib.parse.urlencode({"data": query}).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"User-Agent": "gml-map-viewer/1.0"})
            with urllib.request.urlopen(req, timeout=timeout + 30) as resp:
                return json.loads(resp.read())
        except Exception as e:
            print(f"  attempt {attempt + 1} on {url} failed: {e}", file=sys.stderr)
            time.sleep(5)
    return None


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Fetch named streets from OpenStreetMap for a GML plan.")
    p.add_argument("gml", help="GML plan file (used for bounds and CRS)")
    p.add_argument("-o", "--output", default="streets.geojson",
                   help="output GeoJSON file (default: streets.geojson)")
    p.add_argument("--highways", default=DEFAULT_HIGHWAYS,
                   help="regex of highway types to include")
    p.add_argument("--buffer", type=float, default=0.0,
                   help="buffer around plan bounds in meters (default 0)")
    p.add_argument("--timeout", type=int, default=180,
                   help="Overpass timeout in seconds (default 180)")
    p.add_argument("--overpass", help="Overpass API URL "
                   "(default: try known mirrors in order)")
    args = p.parse_args(argv)

    from gml_map import parse_input
    import pyproj

    feats = parse_input(args.gml)
    if not feats:
        sys.exit("Error: no features found in the GML.")
    srs = next((f.srs for f in feats if f.srs), None)
    epsg = _epsg_from_srs(srs) or 2177
    print(f"Plan CRS: EPSG:{epsg} (from {srs or 'assumed'})")

    geoms = [f.geom for f in feats if not f.geom.is_empty]
    b = (min(g.bounds[0] for g in geoms), min(g.bounds[1] for g in geoms),
         max(g.bounds[2] for g in geoms), max(g.bounds[3] for g in geoms))
    if args.buffer:
        b = (b[0] - args.buffer, b[1] - args.buffer,
             b[2] + args.buffer, b[3] + args.buffer)

    fwd = pyproj.Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lons, lats = [], []
    for x, y in [(b[0], b[1]), (b[0], b[3]), (b[2], b[1]), (b[2], b[3])]:
        lon, lat = fwd.transform(x, y)
        lons.append(lon)
        lats.append(lat)
    south, west = min(lats), min(lons)
    north, east = max(lats), max(lons)
    print(f"Query bbox (WGS84): S{south:.4f} W{west:.4f} N{north:.4f} E{east:.4f}")

    query = (f'[out:json][timeout:{args.timeout}];'
             f'way["highway"~"^({args.highways})$"]["name"]'
             f'({south:.6f},{west:.6f},{north:.6f},{east:.6f});'
             f'out geom;')

    urls = [args.overpass] if args.overpass else MIRRORS
    data = None
    for url in urls:
        print(f"Querying {url} ...")
        data = _overpass_query(url, query, args.timeout)
        if data is not None:
            break
    if data is None:
        sys.exit("Error: all Overpass mirrors failed.")

    inv = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    features = []
    names = set()
    for el in data.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        coords = []
        for pt in geom:
            x, y = inv.transform(pt["lon"], pt["lat"])
            coords.append([round(x, 2), round(y, 2)])
        name = el.get("tags", {}).get("name", "")
        if not name:
            continue
        names.add(name)
        features.append({
            "type": "Feature",
            "properties": {"name": name,
                           "highway": el.get("tags", {}).get("highway", "")},
            "geometry": {"type": "LineString", "coordinates": coords},
        })

    out = {"type": "FeatureCollection",
           "name": "streets",
           "crs": {"type": "name", "properties": {"name": f"EPSG:{epsg}"}},
           "features": features}
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(f"Saved {len(features)} streets ({len(names)} unique names) "
          f"-> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
