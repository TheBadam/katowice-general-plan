#!/usr/bin/env python3
"""Download green areas (forests, meadows, parks, ...) from OpenStreetMap
(Overpass API) for a GML plan.

Computes the plan's bounding box, converts it to WGS84, queries Overpass for
green-area polygons inside it (ways and multipolygon relations), and saves a
GeoJSON file with the geometries in the plan's coordinate system, ready for
`greens_overlap.py` or `gml_viewer.py --greens`.

    python fetch_greens.py plan.gml -o greens.geojson
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

# Green-class -> Overpass tag filters (key=value regex alternation).
# "plains" maps to meadow / grassland / farmland.
GREEN_CLASSES = {
    "forest":   {'landuse': r"^(forest|orchard)$",
                 'natural': r"^wood$"},
    "meadow":   {'landuse': r"^(meadow|grass|farmland|allotments)$"},
    "park":     {'leisure': r"^(park|garden|nature_reserve)$",
                 'landuse': r"^(village_green|recreation_ground)$"},
    "scrub":    {'natural': r"^(scrub|heath)$"},
    "wetland":  {'natural': r"^wetland$"},
}


def _epsg_from_srs(srs: str | None) -> int | None:
    if not srs:
        return None
    codes = re.findall(r"(\d{4,5})", srs)
    for c in codes:
        if 2000 <= int(c) < 100000:
            return int(c)
    return None


def _classify(tags: dict, classes: dict) -> str | None:
    for name, filters in classes.items():
        for key, pattern in filters.items():
            v = tags.get(key)
            if v and re.match(pattern, v):
                return name
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
            print(f"  attempt {attempt + 1} on {url} failed: {e}",
                  file=sys.stderr)
            time.sleep(5)
    return None


def _build_query(classes: dict, bbox: str, timeout: int) -> str:
    merged: dict[str, set[str]] = {}
    for filters in classes.values():
        for key, pattern in filters.items():
            merged.setdefault(key, set()).update(
                pattern.strip("^$()").split("|"))
    selectors = [
        f'["{key}"~"^({"|".join(sorted(vals))})$"]'
        for key, vals in merged.items()]
    body = "".join(
        f'{kind}{sel}({bbox});'
        for sel in selectors
        for kind in ("way", "relation"))
    return f"[out:json][timeout:{timeout}];({body});out geom;"


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Fetch green areas from OpenStreetMap for a GML plan.")
    p.add_argument("gml", help="GML plan file (used for bounds and CRS)")
    p.add_argument("-o", "--output", default="greens.geojson",
                   help="output GeoJSON file (default: greens.geojson)")
    p.add_argument("--classes", default="forest,meadow,park,scrub,wetland",
                   help="comma-separated green classes to fetch (default: "
                        "forest,meadow,park,scrub,wetland)")
    p.add_argument("--buffer", type=float, default=0.0,
                   help="buffer around plan bounds in meters (default 0)")
    p.add_argument("--timeout", type=int, default=180,
                   help="Overpass timeout in seconds (default 180)")
    p.add_argument("--overpass", help="Overpass API URL "
                   "(default: try known mirrors in order)")
    args = p.parse_args(argv)

    names = [c.strip() for c in args.classes.split(",") if c.strip()]
    classes = {}
    for n in names:
        if n not in GREEN_CLASSES:
            sys.exit(f"Error: unknown green class '{n}'. "
                     f"Known: {', '.join(GREEN_CLASSES)}")
        classes[n] = GREEN_CLASSES[n]

    from gml_map import parse_input
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.ops import unary_union
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

    fwd = pyproj.Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326",
                                      always_xy=True)
    lons, lats = [], []
    for x, y in [(b[0], b[1]), (b[0], b[3]), (b[2], b[1]), (b[2], b[3])]:
        lon, lat = fwd.transform(x, y)
        lons.append(lon)
        lats.append(lat)
    south, west = min(lats), min(lons)
    north, east = max(lats), max(lons)
    print(f"Query bbox (WGS84): S{south:.4f} W{west:.4f} "
          f"N{north:.4f} E{east:.4f}")

    bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    query = _build_query(classes, bbox, args.timeout)

    urls = [args.overpass] if args.overpass else MIRRORS
    data = None
    for url in urls:
        print(f"Querying {url} ...")
        data = _overpass_query(url, query, args.timeout)
        if data is not None:
            break
    if data is None:
        sys.exit("Error: all Overpass mirrors failed.")

    inv = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}",
                                      always_xy=True)

    def _ring(pts):
        coords = []
        for pt in pts:
            x, y = inv.transform(pt["lon"], pt["lat"])
            coords.append([round(x, 2), round(y, 2)])
        if len(coords) >= 3 and coords[0] != coords[-1]:
            coords.append(coords[0])
        if len(coords) < 4:
            return None
        try:
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
            return poly if not poly.is_empty else None
        except Exception:
            return None

    features, skipped = [], 0
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        cls = _classify(tags, classes)
        if not cls:
            continue
        props = {"class": cls, "name": tags.get("name", "")}
        for key in ("landuse", "natural", "leisure"):
            if key in tags:
                props[key] = tags[key]

        if el["type"] == "way":
            poly = _ring(el.get("geometry") or [])
            if poly is None:
                skipped += 1
                continue
            gtype = "Polygon"
            coords = [list(poly.exterior.coords)]
            coords += [list(r.coords) for r in poly.interiors]

        elif el["type"] == "relation":
            outers, inners = [], []
            for m in el.get("members", []):
                ring = _ring(m.get("geometry") or [])
                if ring is None:
                    continue
                if m.get("role") == "inner":
                    inners.append(ring)
                else:
                    outers.append(ring)
            if not outers:
                skipped += 1
                continue
            g = unary_union(outers)
            if inners:
                g = g.difference(unary_union(inners))
            if g.is_empty:
                skipped += 1
                continue
            if isinstance(g, MultiPolygon):
                gtype = "MultiPolygon"
                coords = [[list(p.exterior.coords)]
                          + [list(r.coords) for r in p.interiors]
                          for p in g.geoms]
            else:
                gtype = "Polygon"
                coords = [list(g.exterior.coords)]
                coords += [list(r.coords) for r in g.interiors]
        else:
            continue

        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": gtype, "coordinates": coords},
        })

    out = {"type": "FeatureCollection",
           "name": "greens",
           "crs": {"type": "name",
                   "properties": {"name": f"EPSG:{epsg}"}},
           "features": features}
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)

    per_class = {}
    for f in features:
        per_class[f["properties"]["class"]] = \
            per_class.get(f["properties"]["class"], 0) + 1
    print(f"Saved {len(features)} green areas "
          f"({', '.join(f'{k}: {v}' for k, v in sorted(per_class.items()))}; "
          f"{skipped} skipped) -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
