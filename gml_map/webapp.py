"""Payload builder and static exporter for the interactive map viewer.

build_map_payload() turns parsed GML features into the JSON the canvas
viewer page loads; export_static() writes that page (index.html, en/, pl/)
plus mapdata.json as a fully static site - hostable on any static file
server, no Python needed at serving time.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib as mpl
from matplotlib.colors import to_rgb
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry

# The interactive page script: lives in the viewer package (extracted
# verbatim from this template in phase 1 of the UI modernization plan).
# export_static() copies it into the site as viewer.js.
VIEWER_JS = (Path(__file__).resolve().parent.parent
             / "viewer" / "src" / "main.js")

_INTERACTIVE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GML map</title>
<style>
  html, body { margin: 0; height: 100%; font-family: system-ui, sans-serif;
               overflow: hidden; }
  body { display: flex; flex-direction: column; }
  #topbar { flex: none; display: flex; align-items: center; gap: 10px;
            padding: 8px 12px; background: #fff;
            border-bottom: 1px solid #ddd; }
  #titles { flex: 1; min-width: 0; }
  #topbar h1 { font-size: 15px; font-weight: 600; margin: 0;
               line-height: 1.4; }
  #psubtitle { font-size: 12px; color: #555; margin-top: 2px;
               line-height: 1.4; }
  #paneltoggle { width: 15px; flex: none; border: none;
                 border-left: 1px solid #ccc; background: #f7f7f7;
                 cursor: pointer; padding: 0; display: flex;
                 align-items: center; justify-content: center; }
  #paneltoggle:hover { background: #e8e8e8; }
  #paneltoggle svg { width: 8px; height: 12px; display: block;
                     transition: transform 0.15s; }
  #paneltoggle path { fill: none; stroke: #555; stroke-width: 2; }
  #paneltoggle.closed svg { transform: rotate(180deg); }
  #wrap { display: flex; flex: 1; min-height: 0; }
  #canvas { flex: 1; display: block; cursor: grab; min-width: 0;
            touch-action: none; }
  #canvas.dragging { cursor: grabbing; }
  #resizer { width: 6px; flex: none; cursor: col-resize;
             background: transparent; }
  #resizer:hover, #resizer.active { background: #0366d455; }
  #panel { width: 300px; flex: none; background: #f7f7f7;
           border-left: 1px solid #ccc; overflow-y: auto; padding: 10px;
           font-size: 13px; box-sizing: border-box;
           container-type: inline-size; }
  .group { margin-bottom: 10px; padding: 6px 8px; border: 1px solid #ddd;
           border-radius: 6px; background: #fff; }
  .group.off { opacity: 0.45; }
  .group .head { display: flex; align-items: center; gap: 6px; }
  .group .swatch { width: 12px; height: 12px; border: 1px solid #0006;
                   border-radius: 2px; flex: none; }
  .group label { flex: 1; cursor: pointer; font-weight: 600;
                 overflow: hidden; text-overflow: ellipsis;
                 white-space: nowrap; }
  .group .cnt { color: #666; font-weight: 400; font-size: 11px; }
  .group input[type=range] { width: 100%; margin: 6px 0 0; }
  .zgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 8px;
           margin-top: 6px; }
  .zrow { display: flex; align-items: flex-start; gap: 4px;
          font-size: 10.5px; cursor: pointer; user-select: none;
          color: #444; line-height: 1.3; padding: 1px 2px;
          border-radius: 3px; }
  .zrow:hover { background: #eee; }
  .zrow.off { opacity: 0.35; }
  .zsw { width: 9px; height: 9px; margin-top: 2px; flex: none;
         border: 1px solid #0004; border-radius: 2px; display: inline-block; }
  /* collapse the zone grid to one column in a narrow panel */
  @container (max-width: 280px) {
    .zgrid { grid-template-columns: 1fr; }
  }
  .group .hint { color: #777; font-size: 11px; margin-top: 2px; }
  .group .gtitle { color: #333; font-size: 11.5px; margin: 3px 0 2px;
                   line-height: 1.4; white-space: normal; }
  .group details.gdetails { margin-top: 4px; font-size: 11px; }
  .group details.gdetails summary { cursor: pointer; color: #0366d6;
                                    user-select: none; }
  .group details.gdetails div { color: #555; margin-top: 4px;
                                line-height: 1.5; white-space: normal; }
  .group .desc { color: #555; font-size: 11px; margin-top: 4px;
                 white-space: normal; line-height: 1.4; }
  .group .attrib { color: #555; font-size: 11px; margin-top: 4px;
                   white-space: normal; }
  .btns button { margin: 3px 0; padding: 5px 8px; font-size: 12px;
                 width: 100%; cursor: pointer; }
  #panel a { color: #0366d6; font-size: 12px; display: block; margin: 10px 0; }
  .src { color: #777; font-size: 11px; margin: -6px 0 8px;
         word-break: break-word; }
  .lang { margin: -4px 0 8px; font-size: 12px; }
  #langsel a { color: #0366d6; margin: 0 10px 0 0; font-weight: 600;
               display: inline-block; }
  #langsel a.cur { color: #000; pointer-events: none; }
  .plabel { color: #555; font-size: 10.5px; text-transform: uppercase;
            letter-spacing: 0.04em; }
  .lang .plabel { margin-right: 8px; }
  .plinks .plabel { display: block; margin-bottom: 3px; }

  .sechead { margin: 14px 0 6px; font-size: 11px; text-transform: uppercase;
             letter-spacing: 0.04em; color: #555;
             border-bottom: 1px solid #ddd; padding-bottom: 3px; }
  .sechead input { margin: 0 5px 0 0; vertical-align: middle; }
  .hoveropt { display: flex; align-items: center; gap: 6px;
              font-size: 11.5px; color: #444; margin: 2px 0 6px;
              cursor: pointer; user-select: none; }
  .plinks { margin: 0 0 8px; font-size: 12px; }
  #plinks a { color: #0366d6; display: inline-block; margin: 0 10px 4px 0; }
  .note { margin: 0 0 12px; font-size: 12px; color: #444; }
  .note summary { cursor: pointer; color: #0366d6; font-weight: 600; }
  .note div { margin-top: 6px; line-height: 1.5; white-space: normal; }
  #changelogtext p { margin: 4px 0; }
  #changelogtext ul { margin: 4px 0; padding-left: 18px; }
  #changelogtext li { margin: 2px 0; }
  #changelogtext .md-h { font-weight: 600; margin: 8px 0 2px; }
  #changelogtext .md-h:first-child { margin-top: 0; }
  #info { position: fixed; background: #fff; border: 1px solid #999;
          border-radius: 4px; padding: 6px 9px; font-size: 12px;
          pointer-events: none; display: none; z-index: 10;
          max-width: 280px; white-space: normal;
          box-shadow: 2px 2px 6px #0003; }
  #info .desc { color: #555; margin-top: 3px; display: block; }
  /* small screens: the panel overlays the map instead of squeezing it */
  @media (max-width: 700px) {
    #topbar { padding: 6px 10px; }
    #topbar h1 { font-size: 13px; }
    #psubtitle { font-size: 11px; }
    #wrap { position: relative; }
    #resizer { display: none; }
    #paneltoggle { position: absolute; top: 0; right: 0; bottom: 0;
                   z-index: 6; }
    #panel { position: absolute; top: 0; right: 15px; bottom: 0;
             z-index: 5; max-width: calc(85vw - 15px);
             box-shadow: -2px 0 10px #0003; }
    .zrow { padding: 5px 3px; }
    .group .head input[type=checkbox] { width: 16px; height: 16px; }
    .btns button { padding: 8px 6px; }
  }
</style>
</head>
<body>
<div id="topbar">
  <div id="titles">
    <h1 id="ptitle">Loading...</h1>
    <div id="psubtitle" style="display:none"></div>
  </div>
</div>
<div id="wrap">
  <canvas id="canvas"></canvas>
  <div id="resizer" title="drag to resize panel"></div>
  <button id="paneltoggle" title="toggle panel"><svg viewBox="0 0 8 12"><path d="M1 1l6 5-6 5"/></svg></button>
  <div id="panel">
    <div class="lang" id="langsel"></div>
    <div class="src" id="psrc"></div>
    <div class="plinks" id="plinks"></div>
    <details id="pnote" class="note" style="display:none">
      <summary id="notesum">Explanation</summary>
      <div id="notetext"></div>
    </details>
    <details id="pchangelog" class="note" style="display:none">
      <summary id="changelogsum">Changelog</summary>
      <div id="changelogtext"></div>
    </details>
    <div id="groups"></div>
    <div class="btns">
      <button id="zoomin"></button>
      <button id="zoomout"></button>
      <button id="fitbtn"></button>
      <button id="png"></button>
    </div>
    __CLASSIC_LINK__
  </div>
</div>
<div id="info"></div>
<script>window.I18N = __I18N__;</script>
<script src="__JS__viewer.js?v=__JSV__"></script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# interactive canvas viewer payload
# ---------------------------------------------------------------------------

def _darken(color):
    r, g, b = to_rgb(color)
    return "#{:02x}{:02x}{:02x}".format(int(r * 153), int(g * 153), int(b * 153))


def _flat_ring(ring):
    out = []
    for x, y in ring.coords:
        out.append(round(x, 2))
        out.append(round(y, 2))
    return out


def _kind_of(geom: BaseGeometry) -> str:
    t = geom.geom_type
    if "Point" in t:
        return "pt"
    if "Line" in t or "Curve" in t:
        return "l"
    return "p"


def _flatten_geom(geom: BaseGeometry):
    if hasattr(geom, "geoms"):
        for p in geom.geoms:
            yield from _flatten_geom(p)
    else:
        yield geom


def build_map_payload(features, schema, prop, zone_mapping,
                      title, srs=None, resolve_key=None, streets=None,
                      overlay=False, descriptions=None,
                      page_title=None, page_subtitle=None, note=None,
                      links=None, src=None, changelog=None, greens=None,
                      greens_stats=None,
                      default_off=None, zone_definition=None, hatch=None,
                      highlight=None, default_alpha=None, layer_names=None,
                      street_tolerance=None):
    """Build the JSON payload for the interactive canvas viewer.

    `resolve_key(value) -> schema key or None` decides the group of a feature
    (same logic as the CLI color matching); required.
    `streets`: list of {"coords": [(x, y), ...], "name", "highway"} overlays.
    `overlay`: if True, features keep their original per-layer colors as
    individually controllable base layers and groups are painted on top;
    if False, groups replace the colors.
    `descriptions`: optional {group name: description text} shown in the UI.
    `default_alpha`: optional {group/layer name: opacity 0..1} setting
    the initial position of the per-group opacity slider.
    `layer_names`: optional {raw layer name: display name}; the key order
    sets the display order of the layer controls in the viewer panel.
    `street_tolerance`: optional Douglas-Peucker tolerance (CRS units)
    simplifying street geometry in the payload; trims its size and the
    memory needed to load it in the browser.
    `hatch`: app-level hatch config for overlay groups (no UI control):
    {"width": line thickness in px, "spacing": line distance in px,
    "fill": opacity 0..1 of the solid color between the lines}. Defaults
    to the reserved "global_hatch" entry of `schema` (the group-definitions
    file), which names the fill opacity "alpha".
    """
    if resolve_key is None:
        raise ValueError("resolve_key callback is required")

    hcfg = hatch or (schema or {}).get("global_hatch") or {}
    hatch = {
        "width": float(hcfg.get("width", 2.5)),
        "spacing": float(hcfg.get("spacing", 16.0)),
        "fill": float(hcfg.get("alpha", hcfg.get("fill", 0.0))),
    }
    if hatch["width"] <= 0 or hatch["spacing"] <= 0:
        raise ValueError("hatch width and spacing must be positive")
    if not 0 <= hatch["fill"] <= 1:
        raise ValueError("hatch fill must be a number in [0, 1]")

    # hovered-zone outline style: app-level only (from settings.json), no
    # UI. Only the provided keys travel in the payload; the page's
    # built-in highlight defaults cover the rest, so settings.json is
    # the single config source for this style (no parallel defaults)
    hlight = highlight or {}
    if not isinstance(hlight, dict):
        raise ValueError("highlight must be an object")
    highlight = {}
    if "color" in hlight:
        try:
            to_rgb(hlight["color"])
        except (ValueError, TypeError):
            raise ValueError("highlight color must be a valid color")
        highlight["color"] = hlight["color"]
    if "width" in hlight:
        highlight["width"] = float(hlight["width"])
        if highlight["width"] <= 0:
            raise ValueError("highlight width must be positive")
    if "dash" in hlight:
        highlight["dash"] = [float(v) for v in hlight["dash"]]
        if (len(highlight["dash"]) < 2
                or not all(v > 0 for v in highlight["dash"])):
            raise ValueError("highlight dash must be two or more positive "
                             "numbers (px, on/off pattern)")

    if overlay:
        # the original per-layer colors form individually controllable
        # base layers; groups are painted on top as overlays
        cmap = mpl.colormaps["tab20"]
        raw = sorted({f.layer for f in features}, key=str.lower)
        lname = layer_names or {}
        # mapped layers first, in the file's key order; the rest after
        layer_order = [n for n in lname if n in raw] + \
                      [n for n in raw if n not in lname]
        base_color = {n: mpl.colors.to_hex(cmap(i % 20))
                      for i, n in enumerate(layer_order)}
        dalpha = default_alpha or {}
        groups = [{"name": n, "label": lname.get(n, n),
                   "color": base_color[n],
                   "edge": _darken(base_color[n]),
                   "alpha": dalpha.get(n, 0.62), "kind": "layer"}
                  for n in layer_order]
        groups += [{"name": k, "color": v, "edge": _darken(v),
                    "alpha": dalpha.get(k, 1.0), "kind": "group"}
                   for k, v in schema.items()
                   if k not in ("_default", "global_hatch")]
        color_by_group = {g["name"]: g["color"] for g in groups}
    else:
        dalpha = default_alpha or {}
        groups = [{"name": k, "color": v, "edge": _darken(v),
                   "alpha": dalpha.get(k, 0.62), "kind": "group"}
                   for k, v in schema.items()
                   if k not in ("_default", "global_hatch")]
        default_color = schema.get("_default", "#dddddd")
        groups.append({"name": "other", "color": default_color,
                       "edge": _darken(default_color), "alpha": 0.62,
                       "kind": "group"})
        color_by_group = {g["name"]: g["color"] for g in groups}
    if descriptions:
        for g in groups:
            d = descriptions.get(g["name"])
            if not d:
                continue
            if isinstance(d, dict):  # {"title": ..., "details": ...}
                if d.get("title"):
                    g["desc_title"] = str(d["title"]).strip()
                if d.get("details"):
                    g["desc"] = str(d["details"]).strip()
            elif str(d).strip():     # legacy: plain description string
                g["desc"] = str(d).strip()
    group_rank = {g["name"]: i for i, g in enumerate(groups)}
    kind_rank = {"p": 0, "l": 1, "pt": 2}

    entries = []
    zones_by_layer = {}  # layer -> {sym: {sym, title, color}} for the UI chips
    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")
    for f in features:
        key = resolve_key(f.props.get(prop))
        if overlay:
            group = key if key in group_rank else None
            bc = base_color.get(f.layer, "#cccccc")
            bg = f.layer
        else:
            group = key if key in group_rank else "other"
            bc = color_by_group.get(group, "#dddddd")
            bg = group
        be = None
        sym = (f.props.get("symbol") or "").strip()
        zdef = (zone_definition or {}).get(sym)
        if zdef:
            # zone-type feature: definition color + explicit stroke; the
            # optional "alpha" is its initial fill transparency (the UI
            # opacity slider scales this level)
            bc = zdef["color"]
            be = zdef.get("stroke", "#191919")
        base = {
            "g": group,
            "bc": bc,
            "be": be,
            "bg": bg,
            "layer": f.layer,
            "ozn": (f.props.get(prop) or "").strip(),
            "sym": f.props.get("symbol", ""),
        }
        if zdef:
            base["ba"] = round(float(zdef.get("alpha", 1.0)), 3)
            zl = zones_by_layer.setdefault(f.layer, {})
            if sym not in zl:
                zl[sym] = {"sym": sym, "title": zdef["title"],
                           "color": zdef["color"]}
        for g in _flatten_geom(f.geom):
            kind = _kind_of(g)
            if kind == "p":
                if g.exterior is None:
                    continue
                part = [_flat_ring(g.exterior)]
                part.extend(_flat_ring(r) for r in g.interiors)
                entry = dict(base, t="p", parts=[part])
            elif kind == "l":
                entry = dict(base, t="l", parts=[[_flat_ring(g)]])
            else:
                entry = dict(base, t="pt", x=round(g.x, 2), y=round(g.y, 2))
            b = g.bounds
            if b and all(v == v for v in b):  # non-empty
                xmin, ymin = min(xmin, b[0]), min(ymin, b[1])
                xmax, ymax = max(xmax, b[2]), max(ymax, b[3])
            entries.append(entry)

    entries.sort(key=lambda e: (group_rank[e["bg"]],
                                kind_rank[e["t"]]))

    # per-zone-type on/off chips for layer groups containing zone features
    for g in groups:
        zl = zones_by_layer.get(g["name"])
        if zl and g.get("kind") == "layer":
            g["zones"] = [zl[k] for k in sorted(zl)]

    payload = {
        "title": title,
        "crs": srs or "",
        "bounds": [xmin, ymin, xmax, ymax],
        "groups": groups,
        "features": entries,
        "hatch": hatch,
        "highlight": highlight or None,
    }
    if streets:
        # streets are not a color group feature; add their group for the UI
        payload["groups"].append({"name": "streets", "label": "Streets",
                                  "color": "#5a5a5a",
                                  "edge": "#3a3a3a", "alpha": 0.85,
                                  "attrib": "© OpenStreetMap contributors "
                                            "(ODbL)",
                                  "kind": "streets"})
        web_streets = []
        for s in streets:
            pts = s["coords"]
            if len(pts) < 2:
                continue
            if street_tolerance:  # simplify street geometry (memory)
                pts = list(LineString(pts).simplify(
                    street_tolerance, preserve_topology=False).coords)
                if len(pts) < 2:
                    continue
            flat = []
            length = 0.0
            best = None  # longest segment for the label
            for i, (x, y) in enumerate(pts):
                flat.append(round(x, 2))
                flat.append(round(y, 2))
                if i:
                    dx, dy = x - pts[i - 1][0], y - pts[i - 1][1]
                    d = (dx * dx + dy * dy) ** 0.5
                    length += d
                    if best is None or d > best[0]:
                        best = (d, pts[i - 1][0], pts[i - 1][1], x, y)
            web_streets.append({
                "parts": [flat],
                "name": s.get("name", ""),
                "hw": s.get("highway", ""),
                "len": round(length, 1),
                "lab": [best[1], best[2], best[3], best[4]],
            })
        payload["streets"] = web_streets
        for s in web_streets:  # include streets in the rebase extent
            r = s["parts"][0]
            for i in range(0, len(r), 2):
                xmin, ymin = min(xmin, r[i]), min(ymin, r[i + 1])
                xmax, ymax = max(xmax, r[i]), max(ymax, r[i + 1])
    if greens:
        # green x zone intersection polygons: a toggleable "Greens" layer
        # in the GML layers section; each part honors the zone-type
        # toggles via its zone symbol (`sym`)
        payload["groups"].append({"name": "greens", "i18n": "greens",
                                  "color": "#add19e",
                                  "edge": "#7aa86e", "alpha": 0.75,
                                  "kind": "layer",
                                  "attrib": "© OpenStreetMap contributors "
                                            "(ODbL)"})
        web_greens = []
        for g in greens:
            part = []
            for ring in g["rings"]:
                flat = []
                for x, y in ring:
                    flat.append(round(x, 2))
                    flat.append(round(y, 2))
                if len(flat) >= 8:
                    part.append(flat)
                    xmin, ymin = min(xmin, x), min(ymin, y)
                    xmax, ymax = max(xmax, x), max(ymax, y)
            if part:
                web_greens.append({"parts": [part],
                                   "sym": g.get("sym", ""),
                                   "c": g.get("cls", "")})
        payload["greens"] = web_greens
    if greens_stats is not None:
        payload["greens_stats"] = greens_stats

    # Rebase all coordinates to a local origin. Browsers store canvas
    # path points as 32-bit floats, so absolute coordinates of millions
    # of meters lose precision and visibly drift at deep zoom-out.
    ox, oy = xmin, ymin

    def _shift_ring(r):
        for i in range(0, len(r), 2):
            r[i] = round(r[i] - ox, 2)
            r[i + 1] = round(r[i + 1] - oy, 2)

    for e in entries:
        if e["t"] == "pt":
            e["x"] = round(e["x"] - ox, 2)
            e["y"] = round(e["y"] - oy, 2)
        else:
            for part in e["parts"]:
                if e["t"] == "p":
                    for ring in part:
                        _shift_ring(ring)
                else:
                    _shift_ring(part[0])
    if payload.get("streets"):
        for s in payload["streets"]:
            _shift_ring(s["parts"][0])
            s["lab"] = [round(v - (ox if i % 2 == 0 else oy), 2)
                        for i, v in enumerate(s["lab"])]
    if payload.get("greens"):
        for g in payload["greens"]:
            for ring in g["parts"][0]:
                _shift_ring(ring)

    payload["bounds"] = [0, 0, round(xmax - ox, 2), round(ymax - oy, 2)]
    payload["page_title"] = page_title or title
    payload["page_subtitle"] = page_subtitle or ""
    payload["src"] = src or title
    payload["note"] = note or ""
    payload["links"] = links or []
    payload["changelog"] = changelog or ""
    if default_off:
        for g in payload["groups"]:
            g["on"] = g["name"] not in default_off
    return payload


# UI labels for the viewer page are not built in: the i18n JSON file
# passed with --i18n (e.g. i18n.json) is the single source of truth and
# must define every label the page script looks up.


def merged_i18n(override=None):
    """The complete UI label set {lang: {key: text}} for the viewer page.

    The i18n JSON file (see --i18n / i18n.json) is the single source of
    truth: it must define every label the page script looks up.
    """
    return {lang: dict(labels) for lang, labels in (override or {}).items()}


def interactive_page_html(i18n=None, js_prefix="", js_ver=""):
    """The interactive viewer page for the static export.

    `i18n`: {lang: {key: text}} UI labels from the i18n JSON file (the
    single source of truth, passed via --i18n); embedded into the page
    as JSON on `window.I18N`, read by viewer.js (from viewer/src/main.js,
    copied into the site by export_static). The mapdata URL and the
    language are computed client-side from the page URL, so the same
    HTML works at any path (incl. /en/ and /pl/ subpaths).
    `js_prefix`: "" at the site root, "../" inside the language dirs.
    `js_ver`: cache-busting query appended to the script URL (the
    source file's mtime, so a new build means a new URL).
    """
    html = _INTERACTIVE_HTML.replace(
        "__I18N__", json.dumps(merged_i18n(i18n), ensure_ascii=False))
    html = html.replace("__JS__", js_prefix)
    html = html.replace("__JSV__", str(js_ver))
    return html.replace("__CLASSIC_LINK__", "")


def export_static(payload, out_dir, i18n=None):
    """Write a fully static copy of the interactive viewer to `out_dir`.

    Produces index.html (auto language) plus en/ and pl/ copies, and
    mapdata.json; hostable on any static file server (nginx, GitHub Pages,
    S3, ...). `i18n` carries the viewer UI labels ({lang: {key: text}},
    see i18n.json) - the single source of truth, so it is required.
    No Python is needed at serving time.
    Returns the index.html path.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # the gzip .htaccess belongs on the server, above the site files
    # (see README), never in the exported assets: drop a stale one so
    # the bundle cannot ship it
    stale = out / ".htaccess"
    if stale.exists():
        stale.unlink()
    # ship the page script with the site; its mtime doubles as the
    # cache-busting version, so browsers pick up every rebuild
    if not VIEWER_JS.exists():
        raise FileNotFoundError(
            f"viewer script not found: {VIEWER_JS} (run from the repo "
            "root, or see viewer/README.md)")
    ver = int(VIEWER_JS.stat().st_mtime)
    shutil.copyfile(VIEWER_JS, out / "viewer.js")
    (out / "index.html").write_text(
        interactive_page_html(i18n, "", ver), encoding="utf-8")
    for lang in ("en", "pl"):
        sub = out / lang
        sub.mkdir(exist_ok=True)
        (sub / "index.html").write_text(
            interactive_page_html(i18n, "../", ver), encoding="utf-8")
    # the greens layer is bulky, so it lives in its own file and is only
    # downloaded when the user toggles the layer on (or hovers a zone,
    # which needs the per-zone overlap stats for the tooltip)
    greens = payload.pop("greens", None)
    stats = payload.pop("greens_stats", None)
    (out / "mapdata.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if greens is not None or stats is not None:
        (out / "greens.json").write_text(
            json.dumps({"greens": greens or [], "stats": stats or {}},
                       ensure_ascii=False), encoding="utf-8")
    return out / "index.html"
