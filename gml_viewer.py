#!/usr/bin/env python3
"""GML Map Viewer - view maps published in GML (Geography Markup Language).

Designed for Polish spatial-planning exports (MPZP / plan ogólny), but works
with any GML file containing Point / LineString / Polygon / Multi* geometries.

Usage examples:

    python gml_viewer.py plan.gml                     # render + save/show map
    python gml_viewer.py plan.gml -o mapa.png
    python gml_viewer.py plan.zip --list-layers
    python gml_viewer.py plan.gml --layer funkcje --label funkcjaSymbol
    python gml_viewer.py plan.gml --attributes --geojson plan.geojson
    python gml_viewer.py plan.gml --web               # browser view (headless OK)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_CODE_RE = re.compile(r"^(\d+)([A-Z]{2,3})$")


def split_zones_str(raw):
    return [t for t in re.split(r"[^0-9A-Za-z]+", raw.upper()) if t]


def build_zone_mapping(path, known):
    """Load zones.json into {oznaczenie: group}.

    Returns (mapping, groups, unresolved, conflicts). Tokens in the 'zones'
    strings are validated against `known` (the oznaczenia present in the GML);
    messy tokens are repaired when possible:

    - 'A, B' -> split on any non-alphanumeric separator (commas, periods,
      whitespace),
    - '219197SJ' (fused) -> split into two valid designations 219SJ, 197SJ,
    - 'D450SW' (stray leading letters) -> 450SW,
    - bare numbers take the code from a neighbouring token ('187.190SW').
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        sys.exit(f"Error: cannot read {path}: {e}")
    # tolerate full-line // comments (e.g. a file annotation marker)
    text = "\n".join(l for l in text.splitlines()
                     if not l.lstrip().startswith("//"))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        sys.exit(f"Error: {path} is not valid JSON: {e}")
    if not isinstance(data, dict) or not data:
        sys.exit(f"Error: {path} must contain a JSON object of groups, "
                 'each a list of {"name": ..., "zones": "1SU, 2SU, ..."}')

    def resolve(tok):
        if tok in known:
            return [tok]
        m = _CODE_RE.match(tok)
        if m:
            digits, code = m.groups()
            for i in range(1, len(digits)):  # fused: 219197SJ -> 219SJ + 197SJ
                left, right = digits[:i] + code, digits[i:] + code
                if left in known and right in known:
                    return [left, right]
            for i in range(1, len(digits)):  # stray prefix: 22249SP -> 49SP
                tail = digits[i:] + code
                if tail in known:
                    return [tail]
        stripped = re.sub(r"^[A-Z]+(?=\d)", "", tok)  # D450SW -> 450SW
        if stripped != tok and stripped in known:
            return [stripped]
        return []

    mapping, unresolved, conflicts = {}, [], {}
    for group, entries in data.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            zones = entry.get("zones", "")
            if isinstance(zones, list):  # proper JSON: ["1SU", "2SU", ...]
                tokens = [str(t).strip().upper() for t in zones
                          if str(t).strip()]
            else:  # legacy: comma-separated string
                tokens = split_zones_str(str(zones))
            for i, tok in enumerate(tokens):
                if tok.isdigit():  # bare number: borrow the code of a neighbour
                    for j in (i - 1, i + 1):
                        if 0 <= j < len(tokens):
                            m = _CODE_RE.match(tokens[j])
                            if m and (tok + m.group(2)) in known:
                                tok = tok + m.group(2)
                                break
                got = resolve(tok)
                if not got:
                    unresolved.append(tok)
                    continue
                for ozn in got:
                    if ozn in mapping and mapping[ozn] != group:
                        conflicts.setdefault(ozn, [mapping[ozn]]).append(group)
                    mapping[ozn] = group
    return mapping, list(data), unresolved, conflicts


def print_summary(layers, srs_hint=None):
    w_name = max([len(n) for n in layers] + [len("Layer")])
    print(f"{'Layer'.ljust(w_name)}  Features  Geometry")
    print("-" * (w_name + 30))
    total = 0
    for name in sorted(layers, key=str.lower):
        feats = layers[name]
        kinds = sorted({f.geom.geom_type for f in feats})
        srs = next((f.srs for f in feats if f.srs), "")
        total += len(feats)
        print(f"{name.ljust(w_name)}  {len(feats):>8}  {'+'.join(kinds)}"
              + (f"  [{srs}]" if srs else ""))
    print("-" * (w_name + 30))
    print(f"{str(total):>{len('Features') + w_name + 2}} features, "
          f"{len(layers)} layers")


def print_attributes(layers, max_rows=15):
    for name in sorted(layers, key=str.lower):
        feats = layers[name]
        print(f"\n=== {name} ({len(feats)} features, first {min(len(feats), max_rows)}) ===")
        for i, f in enumerate(feats[:max_rows], 1):
            if f.props:
                body = "  ".join(f"{k}={v}" for k, v in f.props.items())
            else:
                body = "(no attributes)"
            print(f"  [{i:>3}] {body}")
        if len(feats) > max_rows:
            print(f"  ... {len(feats) - max_rows} more")


def write_geojson(layers, path):
    fc = {
        "type": "FeatureCollection",
        "name": Path(path).stem,
        "features": [],
    }
    srs = None
    for name in sorted(layers, key=str.lower):
        for f in layers[name]:
            srs = srs or f.srs
            fc["features"].append({
                "type": "Feature",
                "properties": {"_layer": name, **f.props},
                "geometry": mapping(f.geom),
            })
    if srs:
        fc["crs"] = {"type": "name", "properties": {"name": srs}}
    Path(path).write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    return len(fc["features"])


def load_color_schema(path):
    """Load a JSON color schema: {"value": "color", ..., "_default": "color"}."""
    import json
    from matplotlib.colors import to_rgb
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"Error: {path} is not valid JSON: {e}")
    if not isinstance(data, dict) or not data:
        sys.exit(f"Error: {path} must contain a JSON object "
                 '{"value": "color", ...}')
    for key, color in data.items():
        try:
            to_rgb(color)
        except (ValueError, TypeError):
            sys.exit(f"Error: {path}: invalid color for key {key!r}: {color!r}")
    return data


def resolve_schema_key(value, schema, zone_mapping=None):
    """Map a property value to a schema key (group), or None.

    Group mode (zone_mapping given): value -> group via zones.json.
    Value mode: exact value, then value with leading digits stripped.
    """
    if value is not None:
        value = value.strip()
    if zone_mapping is not None:
        key = zone_mapping.get(value) if value else None
        if key is not None and key not in schema:
            key = None
        return key
    if value and value in schema:
        return value
    code = value.lstrip("0123456789") if value else ""
    return code if value and code and code in schema else None


def make_color_fn(schema, prop, zone_mapping=None, overlay=False):
    """Return (color_fn, report).

    overlay=False: color_fn returns the final color for each feature
    (group color or '_default').
    overlay=True: color_fn returns the overlay color for grouped features
    and None for ungrouped ones (which keep their original layer color).
    """
    from matplotlib.colors import to_rgb
    fallback = schema.get("_default", "#dddddd")
    stats = {"matched": 0, "unmatched": set(), "per_key": {}, "seen": set()}

    def record(f, value, key):
        if id(f) not in stats["seen"]:  # count each feature once
            stats["seen"].add(id(f))
            if key is None:
                stats["unmatched"].add((value or "").strip() or "(no value)")
            else:
                stats["matched"] += 1
                stats["per_key"][key] = stats["per_key"].get(key, 0) + 1

    def color_fn(f):
        value = f.props.get(prop)
        key = resolve_schema_key(value, schema, zone_mapping)
        color = fallback if key is None else to_rgb(schema[key])
        record(f, value, key)
        return color

    def overlay_fn(f):
        value = f.props.get(prop)
        key = resolve_schema_key(value, schema, zone_mapping)
        record(f, value, key)
        return to_rgb(schema[key]) if key is not None else None

    def report():
        keys = [k for k in schema if k != "_default"]
        print(f"\nColor schema (prop={prop}): {stats['matched']} features matched")
        for k in keys:
            n = stats["per_key"].get(k, 0)
            print(f"  {k:<12} {schema[k]:<8} {n} features")
        if "_default" in schema:
            print(f"  _default     {schema['_default']:<8} (unmatched values)")
        if stats["unmatched"]:
            shown = sorted(stats["unmatched"])
            cap = 5 if zone_mapping is not None else 10
            more = len(shown) - cap
            print(f"  unmatched values ({len(shown)}): "
                  + ", ".join(shown[:cap]) + (f" ... +{more}" if more > 0 else ""))

    return (overlay_fn if overlay else color_fn), report


def load_streets(path):
    """Load street overlays from a GeoJSON file (e.g. fetch_streets.py output).

    Returns a list of {"coords": [(x, y), ...], "name", "highway"} dicts in
    the same CRS as the plan (no reprojection is applied).
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"Error: {path} is not valid JSON: {e}")
    if isinstance(data, dict):
        feats = [data] if data.get("type") == "Feature" \
            else data.get("features", [])
    elif isinstance(data, list):
        feats = data
    else:
        sys.exit(f"Error: {path} is not a GeoJSON file")

    out = []

    def add_line(coords, props):
        if coords and len(coords) >= 2:
            out.append({"coords": [(float(x), float(y)) for x, y in coords],
                        "name": props.get("name", ""),
                        "highway": props.get("highway", "")})

    for f in feats:
        if not isinstance(f, dict):
            continue
        props = f.get("properties") or {}
        g = f.get("geometry") or {}
        t = g.get("type")
        if t == "LineString":
            add_line(g.get("coordinates"), props)
        elif t == "MultiLineString":
            for ln in g.get("coordinates", []):
                add_line(ln, props)
    return out


def load_zone_definition(path):
    """Load zone_definition.json: {symbol: {"title", "color", "stroke"}}."""
    from matplotlib.colors import to_rgb
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        sys.exit(f"Error: cannot load {path}: {e}")
    if not isinstance(data, dict):
        sys.exit(f"Error: {path} must map symbols to "
                 '{"title": ..., "color": ..., "stroke": ...}')
    for sym, z in data.items():
        if not isinstance(z, dict) or "title" not in z or "color" not in z:
            sys.exit(f"Error: {path}: entry {sym!r} needs title and color")
        try:
            to_rgb(z["color"])
            to_rgb(z.get("stroke", "#191919"))
        except (ValueError, TypeError):
            sys.exit(f"Error: {path}: invalid color in entry {sym!r}")
    return data


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="gml_viewer.py",
        description="View maps published in GML format (e.g. Polish MPZP plans).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage examples:")[1] if "Usage examples:" in __doc__ else None,
    )
    p.add_argument("input", help=".gml/.xml file, .zip/.gz archive, or directory")
    p.add_argument("-o", "--output", metavar="PNG",
                   help="save the rendered map to a PNG file")
    p.add_argument("--list-layers", action="store_true",
                   help="only list detected layers and exit")
    p.add_argument("--layer", action="append", default=[], metavar="NAME",
                   help="render only layers whose name contains NAME (repeatable)")
    p.add_argument("--attributes", action="store_true",
                   help="print feature attribute tables")
    p.add_argument("--label", metavar="PROP",
                   help="annotate polygons with the value of property PROP")
    p.add_argument("--colors", metavar="JSON",
                   help="JSON color schema; with --zones: group->color "
                        "(e.g. {'A': '#377eb8'}); without: oznaczenie/symbol "
                        "code -> color, plus optional '_default'")
    p.add_argument("--zones", metavar="JSON",
                   help="JSON group definitions: {group: [{'name': ..., "
                        "'zones': '1SU, 2SU, ...'}]}; groups are colored "
                        "via --colors")
    p.add_argument("--color-prop", default="oznaczenie", metavar="PROP",
                   help="property matched against the color schema "
                        "(default: oznaczenie)")
    p.add_argument("--descriptions", metavar="JSON",
                   help="JSON with {group: description} or "
                        "{group: {\"title\": ..., \"details\": ...}} shown in "
                        "the viewer panel")
    p.add_argument("--page-title", metavar="TEXT",
                   help="page title in the browser tab and the viewer "
                        "panel header")
    p.add_argument("--page-note", metavar="FILE",
                   help="plain text file shown on the page in a collapsible "
                        "'Explanation' block (methodology, sources...)")
    p.add_argument("--page-link", action="append", default=[],
                   metavar="NAME=URL",
                   help="link shown at the top of the page (repeatable), "
                        "e.g. --page-link 'Report=https://example.com'")
    p.add_argument("--default-off", action="append", default=[],
                   metavar="GROUP",
                   help="layer/group shown unchecked by default in the "
                        "interactive viewer (repeatable, exact name)")
    p.add_argument("--zone-definition", metavar="JSON",
                   help="zone_definition.json: paint zone-type features "
                        "(matched by the 'symbol' property) with their "
                        "fill color and stroke (border) color")
    p.add_argument("--overlay", action="store_true",
                   help="with --zones/--colors: paint groups as "
                        "semi-transparent overlays on top of the original "
                        "GML rendering instead of replacing its colors")
    p.add_argument("--streets", metavar="GEOJSON",
                   help="overlay named streets from a GeoJSON file "
                        "(see fetch_streets.py)")
    p.add_argument("--geojson", metavar="PATH", help="export features to GeoJSON")
    p.add_argument("--swap-xy", dest="swap", action="store_true", default=None,
                   help="force swapping coordinate pairs (axis order fix)")
    p.add_argument("--no-swap", dest="swap", action="store_false",
                   help="disable automatic axis-order correction")
    p.add_argument("--title", help="map title (default: file name)")
    p.add_argument("--dpi", type=int, default=200, help="output PNG DPI (default 200)")
    p.add_argument("--no-show", action="store_true",
                   help="do not open an interactive window")
    p.add_argument("--web", nargs="?", const=8988, metavar="PORT", type=int,
                   help="serve the map in a web browser (interactive pan/zoom); "
                        "headless-safe. Optional PORT (default 8988).")
    p.add_argument("--export-static", metavar="DIR",
                   help="export the interactive viewer as a static web page "
                        "(index.html + mapdata.json) to DIR; hostable on "
                        "any static file server, no Python needed")
    args = p.parse_args(argv)

    if args.web is not None:
        import matplotlib
        matplotlib.use("webagg")
        import matplotlib.pyplot as plt

    # Imported after the backend is chosen so WebAgg can take over pyplot.
    from gml_map import parse_input, group_layers, render
    from gml_map.render import can_show_interactively
    from shapely.geometry import mapping

    try:
        features = parse_input(args.input, swap=args.swap)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        sys.exit(f"Error: {e}")
    if not features:
        sys.exit("Error: no geometry features found in the input.")

    layers = group_layers(features)

    if args.layer:
        wanted = [l.lower() for l in args.layer]
        layers = {n: fs for n, fs in layers.items()
                  if any(w in n.lower() for w in wanted)}
        if not layers:
            sys.exit("Error: no layers match the --layer filter.")

    print_summary(layers)
    if args.attributes:
        print_attributes(layers)
    if args.list_layers:
        return 0
    if args.geojson:
        n = write_geojson(layers, args.geojson)
        print(f"\nGeoJSON: {n} features -> {args.geojson}")

    interactive = can_show_interactively() and not args.no_show
    out = args.output
    if out is None and not interactive and args.web is None:
        stem = Path(args.input).stem or "gml"
        out = f"{stem}_map.png"

    title = (args.title or args.page_title
             or Path(args.input).name)
    srs = next((f.srs for feats in layers.values() for f in feats if f.srs), None)
    subtitle = f"{sum(len(v) for v in layers.values())} features, {len(layers)} layers"
    if srs:
        subtitle += f"  |  {srs}"

    color_fn = None
    overlay_fn = None
    legend_entries = None
    color_report = None
    if args.zones or args.colors:
        zone_mapping = None
        if args.zones:
            known = {v.strip() for f in features
                     if (v := f.props.get(args.color_prop))}
            zone_mapping, groups, unresolved, conflicts = \
                build_zone_mapping(args.zones, known)
            if unresolved:
                print(f"\nWarning: {len(unresolved)} zone token(s) in "
                      f"{args.zones} could not be matched to any "
                      f"'{args.color_prop}' in the GML: "
                      + ", ".join(sorted(set(unresolved))))
            if conflicts:
                for ozn, gs in conflicts.items():
                    print(f"Warning: '{ozn}' appears in multiple groups "
                          f"({', '.join(gs)}); last one wins")
            if args.colors:
                schema = load_color_schema(args.colors)
            else:  # auto palette when no schema file given
                import matplotlib
                cmap = matplotlib.colormaps["tab10"]
                schema = {g: matplotlib.colors.to_hex(cmap(i % 10))
                          for i, g in enumerate(groups)}
        else:
            schema = load_color_schema(args.colors)
        paint_fn, color_report = make_color_fn(schema, args.color_prop,
                                               zone_mapping,
                                               overlay=args.overlay)
        if args.overlay:
            overlay_fn = paint_fn
        else:
            color_fn = paint_fn
        legend_entries = [(k if k != "_default" else "other", v)
                          for k, v in schema.items()]

    zone_definition = (load_zone_definition(args.zone_definition)
                       if args.zone_definition else None)
    streets = load_streets(args.streets) if args.streets else None
    descriptions = None
    if args.descriptions:
        try:
            descriptions = json.JSONDecoder(strict=False).decode(
                Path(args.descriptions).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"Error: {args.descriptions} is not valid JSON: {e}")
        if not isinstance(descriptions, dict):
            sys.exit(f"Error: {args.descriptions} must be a JSON object "
                     '{"group": "description", ...}')
    note = None
    if args.page_note:
        try:
            note = Path(args.page_note).read_text(encoding="utf-8").strip()
        except OSError as e:
            sys.exit(f"Error: cannot read {args.page_note}: {e}")
    links = []
    for spec in args.page_link:
        if "=" not in spec:
            sys.exit(f"Error: --page-link must be NAME=URL, got: {spec}")
        name, url = spec.split("=", 1)
        links.append({"name": name, "url": url})
    if streets:
        print(f"Streets: {len(streets)} lines "
              f"({len({s['name'] for s in streets if s['name']})} named) "
              f"from {args.streets}")

    def make_web_payload():
        """Build the interactive-viewer payload (None without a color mode)."""
        if color_fn is None and overlay_fn is None:
            return None
        from gml_map.webapp import build_map_payload
        resolve_key = lambda value: resolve_schema_key(
            value, schema, zone_mapping)
        return build_map_payload(
            [f for feats in layers.values() for f in feats],
            schema, args.color_prop, zone_mapping,
            title=title, srs=srs, resolve_key=resolve_key,
            streets=streets, overlay=args.overlay,
            zone_definition=zone_definition,
            descriptions=descriptions,
            page_title=args.page_title, note=note, links=links,
            src=Path(args.input).name,
            default_off=args.default_off or None)

    if args.export_static:
        from gml_map.webapp import export_static
        payload = make_web_payload()
        if payload is None:
            sys.exit("Error: --export-static requires --zones/--colors")
        index = export_static(payload, args.export_static)
        if color_report:
            color_report()
        if args.output:
            render(layers, title=title, subtitle=subtitle,
                   label_prop=args.label, out=args.output, dpi=args.dpi,
                   show=False, color_fn=color_fn,
                   legend_entries=legend_entries, streets=streets,
                   zone_definition=zone_definition,
                   overlay_fn=overlay_fn)
            print(f"\nMap saved -> {args.output}")
        size = sum(f.stat().st_size
                   for f in Path(args.export_static).iterdir())
        print(f"\nStatic site exported -> {index} "
              f"({len(payload['features'])} features, {size / 1e6:.1f} MB)")
        print("Host it with any static server, e.g.:")
        print(f"  python3 -m http.server -d {args.export_static} 8000")
        return 0

    if args.web is not None:
        from gml_map.webapp import serve
        payload = make_web_payload()
        fig = render(layers, title=title, subtitle=subtitle,
                     label_prop=args.label, out=out, dpi=args.dpi,
                     show=False, keep_open=True,
                     color_fn=color_fn, legend_entries=legend_entries,
                     streets=streets, overlay_fn=overlay_fn,
                     zone_definition=zone_definition)
        if color_report:
            color_report()
        print()
        serve(fig, port=args.web, title=title, data=payload)
        plt.close(fig)
        if out:
            print(f"\nMap saved -> {out}")
        return 0

    render(layers, title=title, subtitle=subtitle,
           label_prop=args.label, out=out, dpi=args.dpi, show=interactive,
           color_fn=color_fn, legend_entries=legend_entries, streets=streets,
                   zone_definition=zone_definition,
           overlay_fn=overlay_fn)
    if color_report:
        color_report()

    if out:
        print(f"\nMap saved -> {out}")
    elif interactive:
        print("\nClose the map window to exit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
