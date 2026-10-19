#!/usr/bin/env python3
"""Calculate how much of each plan-zone type overlaps OpenStreetMap green areas.

Reads the plan zones from a GML file and green areas from a GeoJSON produced
by `fetch_greens.py` (both in the plan CRS), intersects the polygons with
shapely, and reports the overlap surface per zone type and green class
(forest, meadow, park, ...), in hectares and as a percentage of the zone.

    python greens_overlap.py plan.gml greens.geojson
    python greens_overlap.py plan.gml greens.geojson --layer StrefaPlanistyczna
"""

from __future__ import annotations

import argparse
import json
import re
import sys

GREEN_COLORS = {
    "forest": "#add19e",
    "meadow": "#cdebb0",
    "park": "#c8facc",
    "scrub": "#adde8b",
    "wetland": "#b6d5c0",
}


def _epsg_from_str(s: str | None) -> int | None:
    if not s:
        return None
    codes = re.findall(r"(\d{4,5})", s)
    for c in codes:
        if 2000 <= int(c) < 100000:
            return int(c)
    return None


def _symbol(ozn: str) -> str:
    return re.sub(r"^\d+", "", ozn or "")


def load_greens(path: str, target_epsg: int):
    """Load green polygons from GeoJSON, reprojecting to EPSG:target_epsg."""
    import pyproj
    from shapely.geometry import shape

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    feats = (data.get("features", []) if isinstance(data, dict) else data)

    src = _epsg_from_str(
        (data.get("crs") or {}).get("properties", {}).get("name", "")
        if isinstance(data, dict) else "")
    src = src or 4326
    transformer = None
    if src != target_epsg:
        transformer = pyproj.Transformer.from_crs(
            f"EPSG:{src}", f"EPSG:{target_epsg}", always_xy=True)

    greens = []
    for f in feats:
        if not isinstance(f, dict) or not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        if transformer is not None and not g.is_empty:
            g = reproject(g, transformer)
        if g.is_valid is False:
            g = g.buffer(0)
        if g.is_empty:
            continue
        greens.append({"geom": g,
                       "class": (f.get("properties") or {}).get("class", "?"),
                       "name": (f.get("properties") or {}).get("name", "")})
    return greens


def reproject(geom, transformer):
    from shapely.ops import transform
    return transform(lambda x, y: transformer.transform(x, y), geom)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Overlap of plan zones with OSM green areas.")
    p.add_argument("gml", help="GML plan file (zones)")
    p.add_argument("greens", help="green areas GeoJSON (fetch_greens.py)")
    p.add_argument("--layer", default="StrefaPlanistyczna",
                   help="GML layer holding the zones "
                        "(default: StrefaPlanistyczna)")
    p.add_argument("--prop", default="oznaczenie",
                   help="zone attribute (default: oznaczenie)")
    p.add_argument("-o", "--output", default="greens_overlap.json",
                   help="output JSON file (default: greens_overlap.json)")
    p.add_argument("--by-zone", action="store_true",
                   help="also report per individual zone (oznaczenie)")
    p.add_argument("--intersections", metavar="GEOJSON",
                   help="export the zone x green intersection polygons "
                        "(for gml_viewer.py --greens)")
    p.add_argument("--stats", metavar="JSON",
                   help="export compact per-zone overlap stats "
                        "(for gml_viewer.py --greens-stats; shown in the "
                        "viewer tooltip)")
    p.add_argument("--simplify", type=float, default=1.0, metavar="TOL",
                   help="simplification tolerance in CRS units for "
                        "--intersections (0 = off; default 1)")
    p.add_argument("--plot", metavar="PNG",
                   help="save a PNG map of zones with green areas overlaid")
    args = p.parse_args(argv)

    from gml_map import parse_input
    from shapely.geometry import shape
    from shapely.ops import unary_union
    from shapely.strtree import STRtree

    feats = parse_input(args.gml)
    zones_feats = [f for f in feats
                   if f.layer == args.layer and not f.geom.is_empty
                   and f.geom.geom_type not in ("Point", "LineString",
                                                "MultiPoint", "MultiLineString",
                                                "LinearRing")]
    if not zones_feats:
        sys.exit(f"Error: no polygons found on layer '{args.layer}'. "
                 f"Layers present: {sorted({f.layer for f in feats})}")

    srs = next((f.srs for f in feats if f.srs), None)
    epsg = _epsg_from_str(srs) or 2177
    print(f"Plan CRS: EPSG:{epsg}; {len(zones_feats)} zone polygons "
          f"on layer '{args.layer}'")

    greens = load_greens(args.greens, epsg)
    if not greens:
        sys.exit(f"Error: no green polygons in {args.greens}")
    classes = sorted({g["class"] for g in greens})
    print(f"Green areas: {len(greens)} polygons "
          f"(classes: {', '.join(classes)})")

    tree = STRtree([g["geom"] for g in greens])
    green_union = unary_union([g["geom"] for g in greens])

    def _overlap(zone_geom, collect=None):
        idxs = tree.query(zone_geom)
        per_class = {c: 0.0 for c in classes}
        for i in idxs:
            g = greens[int(i)]
            if zone_geom.intersects(g["geom"]):
                inter = zone_geom.intersection(g["geom"])
                per_class[g["class"]] += inter.area
                if collect is not None and not inter.is_empty:
                    collect.setdefault(g["class"], []).append(inter)
        # dedupe across classes (a zone patch may match several classes)
        any_area = zone_geom.intersection(green_union).area
        return per_class, any_area

    def _report(zone_geom, per_class, any_area):
        area = zone_geom.area
        rep = {"zone_area_ha": round(area / 1e4, 2),
               "overlap": {}}
        for c in classes:
            ha = per_class[c] / 1e4
            rep["overlap"][c] = {
                "ha": round(ha, 2),
                "pct": round(100 * per_class[c] / area, 2) if area else 0.0}
        rep["any_green"] = {"ha": round(any_area / 1e4, 2),
                            "pct": round(100 * any_area / area, 2)
                            if area else 0.0}
        return rep

    by_symbol, by_zone = {}, {}
    sym_geoms: dict[str, list] = {}
    inter_features = []
    for f in zones_feats:
        ozn = str(f.props.get(args.prop, "")).strip()
        sym = _symbol(ozn) or ozn or "?"
        collected = {} if args.intersections else None
        per_class, any_area = _overlap(f.geom, collect=collected)
        rep = _report(f.geom, per_class, any_area)
        rep["zone"] = ozn
        by_zone.setdefault(ozn, []).append(rep)
        sym_geoms.setdefault(sym, []).append(f.geom)
        if collected:
            from shapely.geometry import mapping
            for cls, geoms in collected.items():
                g = unary_union(geoms)
                if args.simplify:
                    g = g.simplify(args.simplify,
                                   preserve_topology=True)
                if g.is_empty:
                    continue
                inter_features.append({
                    "type": "Feature",
                    "properties": {"class": cls, "sym": sym,
                                   "ozn": ozn},
                    "geometry": mapping(g)})
    if args.intersections:
        with open(args.intersections, "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "name": "greens_overlap",
                       "crs": {"type": "name",
                               "properties": {"name": f"EPSG:{epsg}"}},
                       "features": inter_features}, fh, ensure_ascii=False)
        print(f"Intersection polygons ({len(inter_features)}) "
              f"-> {args.intersections}")
    if args.stats:
        # compact per-zone stats for the viewer tooltip:
        # {ozn: {"ha": zone area, "green": overlap ha, "pct": overlap %,
        #         "by": {class: overlap %}}}
        stats = {}
        for ozn, reps in by_zone.items():
            rep = reps[0]
            by = {c: round(o["pct"], 1)
                  for c, o in rep["overlap"].items() if o["pct"] > 0}
            stats[ozn] = {"ha": rep["zone_area_ha"],
                          "green": rep["any_green"]["ha"],
                          "pct": rep["any_green"]["pct"],
                          "by": by}
        with open(args.stats, "w", encoding="utf-8") as fh:
            json.dump(stats, fh, ensure_ascii=False)
        print(f"Zone stats ({len(stats)}) -> {args.stats}")

    # aggregate per symbol (zone type) on the unioned geometry
    for sym, geoms in sym_geoms.items():
        union = unary_union(geoms) if len(geoms) > 1 else geoms[0]
        per_class, any_area = _overlap(union)
        by_symbol[sym] = _report(union, per_class, any_area)
        by_symbol[sym]["zones"] = len(geoms)

    result = {"crs": f"EPSG:{epsg}",
              "green_classes": classes,
              "by_symbol": by_symbol}
    if args.by_zone:
        result["by_zone"] = {k: (v[0] if len(v) == 1 else v)
                             for k, v in by_zone.items()}
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)

    # console table
    sym_w = max([len("zone")] + [len(s) for s in by_symbol])
    cls_w = max([len(c) for c in classes] + [9])
    print()
    print(f"{'zone':<{sym_w}}  {'area[ha]':>9}  " +
          "  ".join(f"{c:>{cls_w}}" for c in classes) +
          f"  {'any green':>{cls_w}}")
    for sym in sorted(by_symbol):
        r = by_symbol[sym]
        cells = []
        for c in classes:
            o = r["overlap"][c]
            cells.append(f"{o['ha']:.1f} ({o['pct']:.0f}%)")
        a = r["any_green"]
        print(f"{sym:<{sym_w}}  {r['zone_area_ha']:>9.1f}  " +
              "  ".join(f"{cell:>{cls_w}}" for cell in cells) +
              f"  {a['ha']:.1f} ({a['pct']:.0f}%)")
    print()
    print(f"Details -> {args.output}")
    print("Note: per-class percentages may overlap; 'any green' is the "
          "union of all classes.")

    if args.plot:
        _plot(zones_feats, greens, classes, epsg, args.plot)
        print(f"Map -> {args.plot}")
    return 0


def _plot(zones_feats, greens, classes, epsg, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    fig, ax = plt.subplots(figsize=(14, 14))
    for f in zones_feats:
        geoms = ([f.geom] if f.geom.geom_type == "Polygon"
                 else list(getattr(f.geom, "geoms", [])))
        for g in geoms:
            xs, ys = g.exterior.xy
            ax.fill(xs, ys, facecolor="#eeeeee", edgecolor="#999999",
                    linewidth=0.3, zorder=1)
    for g in greens:
        geoms = ([g["geom"]] if g["geom"].geom_type == "Polygon"
                 else list(getattr(g["geom"], "geoms", [])))
        color = GREEN_COLORS.get(g["class"], "#74c476")
        for geom in geoms:
            xs, ys = geom.exterior.xy
            ax.fill(xs, ys, facecolor=color, edgecolor=color,
                    linewidth=0.2, alpha=0.75, zorder=2)
    handles = [Patch(facecolor=GREEN_COLORS.get(c, "#74c476"),
                     edgecolor="none", label=c) for c in classes]
    ax.legend(handles=handles, loc="upper right", fontsize=9)
    ax.set_aspect("equal")
    ax.set_title(f"OSM green areas over the plan (EPSG:{epsg})")
    ax.set_axis_off()
    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
