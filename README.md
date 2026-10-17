# GML Map Viewer

A Python application for viewing maps published in **GML (Geography Markup
Language)** format. Built with Polish spatial-planning exports in mind
(MPZP / plan ogólny, e.g. the Katowice general plan), but it parses any GML
file whose features use standard GML geometries.

It auto-detects layers and attributes, renders a color-coded map with a
legend, prints attribute tables, and can export everything to GeoJSON.

## Features

- **Any GML version / schema**: namespace-agnostic, works with GML 2.x, 3.1
  and 3.2 application schemas (Polish MPZP exports included).
- **Geometries**: `Point`, `LineString`, `Polygon` (with holes),
  `MultiPoint`, `MultiLineString`, `MultiCurve`, `MultiPolygon`,
  `MultiSurface`, `MultiGeometry`, `CompositeSurface`, `CompositeCurve`.
- **Layer discovery**: features are grouped into layers named after the
  feature element (the element under `gml:featureMember`, or the nearest
  attribute-bearing ancestor of the geometry).
- **Axis-order handling**: Polish PL-2000 systems (EPSG:2177/2178/2179) and
  EPSG:4326/4256 are auto-oriented so the map is north-up; override with
  `--swap-xy` / `--no-swap`.
- **Input types**: single `.gml`/`.xml`, a `.zip` archive of plans, a `.gz`
  file, or a directory (all GML files merged).
- **Outputs**: interactive matplotlib window (when a GUI is available), an
  interactive **browser map** via `--web` (works headless), a PNG image, an
  attribute dump, and a GeoJSON export.

## Install

Requires Python 3.10+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Dependencies: `lxml`, `shapely`, `matplotlib`.

## Usage

```bash
# Render the plan (opens a window on desktops, saves <name>_map.png headless)
.venv/bin/python gml_viewer.py plan.gml

# Save a PNG and annotate zones with their symbol
.venv/bin/python gml_viewer.py plan.gml -o mapa.png --label funkcjaSymbol

# Inspect what is inside the file
.venv/bin/python gml_viewer.py plan.gml --list-layers
.venv/bin/python gml_viewer.py plan.gml --attributes

# Render only chosen layers (case-insensitive substring match)
.venv/bin/python gml_viewer.py plan.gml --layer funkcje --layer linie

# Export to GeoJSON (keeps the original CRS, recorded in a "crs" member)
.venv/bin/python gml_viewer.py plan.gml --geojson plan.geojson

# Archive downloaded from a planning office (e.g. katowice plan ogólny)
.venv/bin/python gml_viewer.py plan_ogolny.zip -o katowice.png

# Interactive map in the browser (works on headless machines)
.venv/bin/python gml_viewer.py plan.gml --web          # serves on port 8988
.venv/bin/python gml_viewer.py plan.gml --web 8080      # custom port
```

### Interactive viewing on a headless machine

`--web` serves the map with the full matplotlib toolbar (pan, zoom, save) in
your browser, using a prefix-safe server: all asset URLs are relative and the
WebSocket address is computed by the browser, so it works both directly and
behind reverse proxies that add a path prefix (VS Code code-server
`/proxy/<port>/`, JupyterHub, nginx subpaths, SSH port forwarding).

```bash
.venv/bin/python gml_viewer.py plan.gml --web
# direct:     open http://127.0.0.1:8988/
# via VS Code code-server proxy:
#             open https://<host>/proxy/8988/
```

The URL path does not matter - the server accepts any prefix (e.g.
`https://host:8443/proxy/8988/`, `/gml/`, or a bare `/`), so you can open it
through whatever route your proxy exposes for the port. Stop the server with
Ctrl-C. Add `-o mapa.png` alongside `--web` to also save a static PNG.

### Static export (host anywhere)

`--export-static DIR` writes the same interactive viewer as a fully static
site: `index.html` (auto language) plus `en/index.html` and `pl/index.html`,
and `mapdata.json` (~8 MB for the Katowice plan). No Python or server-side
code is needed at serving time - any static file server works (nginx,
Apache, GitHub Pages, Netlify, S3, or even a file:// URL). The
matplotlib-specific link is dropped; everything else (layer toggles,
opacity, hover details, street names, descriptions, PNG download) works
identically. The panel is organized into sections ("GML layers",
"Environmental impact", "Streets") and the UI language follows the URL:
`/en/` (English), `/pl/` (Polish), or auto-detected from the browser at any
other path - use the EN/PL switcher in the panel to move between them:

```bash
.venv/bin/python gml_viewer.py plan.gml --zones zones.json \
    --colors group_definitions.json --overlay --streets streets.geojson \
    --descriptions zones_description.json \
    --page-title "Environmental impact on Katowice plan" \
    --page-note page_note.txt \
    --page-link "Environmental report=https://planogolnydlakatowic.pl/" \
    --export-static static_site

python3 -m http.server -d static_site 8000
# or upload the static_site/ folder to any static host
```

The page fetches `mapdata.json` relative to its own URL (one directory up
for the language folders), so it works at any path. The same language URLs
work with the live `--web` server. Pre-generate a preview PNG with
`-o map.png` in the same command.

For the Katowice plan there is a launcher that exports the static site
without starting any server:

```bash
./export_katowice.sh            # -> static_site/ (add -o map.png for a preview)
```

`run_katowice.sh` is the interactive-server counterpart.

### Interactive group viewer

When `--web` is combined with `--zones`/`--colors`, the browser page is a
custom canvas viewer with per-group controls:

- checkbox per layer/group to toggle it on/off,
- opacity slider per layer/group,
- drag the divider between the map and the panel to resize the panel
  (width is remembered),
- hover a shape to see its details (oznaczenie, layer, group, symbol, group
  description); click to pin the details, click again or Esc to unpin,
- drag to pan, mouse wheel to zoom,
- Download PNG button (renders the current view),
- the classic matplotlib WebAgg view stays available under `.../classic/`.

```bash
.venv/bin/python gml_viewer.py plan.gml --zones zones.json \
    --colors group_definitions.json --web
```

### Street names overlay

Street names can be overlaid from OpenStreetMap. First download them for the
plan's area (bounds are taken from the GML, converted to WGS84, results
transformed back to the plan's CRS):

```bash
.venv/bin/python fetch_streets.py plan.gml -o streets.geojson
```

Then add `--streets streets.geojson` to any command. In PNG output the
streets are drawn as gray lines with rotated, haloed name labels (long
streets only, to avoid clutter). In the interactive viewer the streets
appear as their own layer: checkbox to toggle, opacity slider, and a
"street names" checkbox controlling label display (labels appear when a
street is long enough at the current zoom).

```bash
.venv/bin/python gml_viewer.py plan.gml --zones zones.json \
    --colors group_definitions.json --streets streets.geojson --web
```

The streets file is plain GeoJSON (LineString/MultiLineString with a `name`
property), so any other source works too - it just has to be in the same
CRS as the plan. Options: `--highways` (regex of OSM highway types),
`--buffer` (meters around plan bounds), `--overpass` (custom API URL).

For remote machines without such a proxy, forward the port over SSH instead:

```bash
ssh -L 8988:127.0.0.1:8988 user@server
.venv/bin/python gml_viewer.py plan.gml --web    # on the server
# open http://127.0.0.1:8988/ in your local browser
```

Try it on the bundled synthetic example:

```bash
.venv/bin/python gml_viewer.py sample_data/mpzp_przyklad.gml
```

## Options

| Option | Description |
|---|---|
| `-o, --output PNG` | Save the rendered map to a PNG file |
| `--list-layers` | Print detected layers and exit |
| `--layer NAME` | Render only matching layers (repeatable, substring match) |
| `--attributes` | Print feature attribute tables (first 15 per layer) |
| `--label PROP` | Annotate polygons with a property value (e.g. zone symbol) |
| `--colors JSON` | Color schema file; see below |
| `--zones JSON` | Group definitions (`zones.json`); see below |
| `--color-prop PROP` | Property matched against the color schema (default: `oznaczenie`) |
| `--zone-definition JSON` | Paint zone-type features by symbol: fill `color` + `stroke` borders from `zone_definition.json` |
| `--overlay` | Paint groups as overlays on the original GML rendering |
| `--default-off GROUP` | Layer/group unchecked by default in the viewer (repeatable) |
| `--descriptions JSON` | Group descriptions shown in the viewer panel |
| `--page-title TEXT` | Page title (browser tab and panel header) |
| `--page-note FILE` | Plain text shown in a collapsible "Explanation" block |
| `--page-link NAME=URL` | Link shown at the top of the page (repeatable) |
| `--streets GEOJSON` | Overlay named streets (see fetch_streets.py) |
| `--geojson PATH` | Export features to GeoJSON |
| `--swap-xy` | Force swapping coordinate pairs (fix axis order manually) |
| `--no-swap` | Disable automatic axis-order correction |
| `--title TEXT` | Custom map title |
| `--dpi N` | PNG resolution (default 200) |
| `--no-show` | Do not open an interactive window |
| `--web [PORT]` | Serve the map in a browser with pan/zoom (default port 8988) |
| `--export-static DIR` | Export the interactive viewer as a static site (host anywhere) |

## Programmatic use

```python
from gml_map import parse_input, group_layers, render

features = parse_input("plan.gml")
layers = group_layers(features)          # {layer_name: [Feature, ...]}
for name, feats in sorted(layers.items()):
    print(name, len(feats), feats[0].props)
render(layers, out="map.png", show=False)
```

## Coloring areas by attribute

Two workflows are supported.

### Groups via zones.json (plan ogólny strefy)

Combine a group definition file with a group color schema:

```bash
.venv/bin/python gml_viewer.py katowice_plan_ogolny_26.gml \
    --zones zones.json --colors group_definitions.json
```

- `zones.json` holds groups (A, B, C, D), each a list of objects with a
  `name` and `zones`: an array of individual oznaczenia
  (`["1SU", "2SU", "254SU"]`, numerically sorted). A comma-separated
  string is also accepted for backward compatibility.
- `group_definitions.json` holds the group colors, the `_default` color
  for ungrouped oznaczenia, and the optional `global_hatch` configuration
  of the overlay hatch (line width and spacing in px; `alpha` is the
  opacity of the solid color between the hatch lines):

```json
{
  "global_hatch": {"width": 5, "spacing": 20, "alpha": 0.7},
  "A": "#4daf4a",
  "B": "#ff7f00",
  "C": "#377eb8",
  "D": "#984ea3",
  "_default": "#dddddd"
}
```

Oznaczenia not listed in any group (and features without `oznaczenie`, e.g.
the plan boundary) fall back to `_default`.
- `layer_names.json` maps raw GML layer names to display names in the viewer
  panel; the key order sets the order of the layer controls:

```json
{
  "StrefaPlanistyczna": "Strefa planistyczna",
  "ObszarUzupelnieniaZabudowy": "Obszar uzupełnienia zabudowy"
}
```

**Overlay mode.** By default the group colors *replace* the original
rendering, and `_default`-colored "other" covers everything not in a group.
With `--overlay`, the GML is drawn as the bottom layer in its original
per-layer colors, and the groups become semi-transparent overlays. In the
interactive viewer every GML layer (e.g. StrefaPlanistyczna,
ObszarUzupelnieniaZabudowy, ...) is a separate, individually toggleable and
fadeable base layer, with the A-D group overlays on top:

```bash
.venv/bin/python gml_viewer.py plan.gml --zones zones.json \
    --colors group_definitions.json --overlay --web
```

**Group descriptions.** `--descriptions zones_description.json` adds a
title and collapsible details to each group in the interactive panel:

```json
{
  "A": {"title": "Tereny, ktore beda wplywaly korzystnie na jakosc srodowiska.",
         "details": "Tereny te podnosza atrakcyjnosc krajobrazowa..."}
}
```

Plain string values are also accepted (shown as details only). The group
title also appears in the hover tooltip.

The `zones` strings are repaired automatically where possible; every token
is validated against the oznaczenia actually present in the GML:

- split on any non-alphanumeric separator (commas, periods, whitespace),
- fused designations: `219197SJ` -> `219SJ` + `197SJ`,
- stray leading letters: `D450SW` -> `450SW`,
- stray leading digits: `22249SP` -> `49SP`,
- bare numbers borrow the code of a neighbouring token: `187.190SW` ->
  `187SW` + `190SW`.

Tokens that cannot be repaired and oznaczenia appearing in several groups
are reported as warnings. Omit `--colors` to get an automatic palette per
group.

### Direct value schema

Without `--zones`, the `--colors` keys are matched directly against the
feature property (default `oznaczenie`): exact value first (`"244SU"`),
then the value with leading digits stripped (`"244SU"` -> `"SU"`), then
`_default`. Use `--color-prop symbol` to match a different attribute.

Any matplotlib color format works: hex (`"#ff0000"`), named (`"red"`), or
prefixed (`"tab:blue"`). The legend lists your schema, and the tool prints
how many features matched each key plus any unmatched values (which fall
back to `_default`).

## Notes and limitations

- Rendering uses the coordinates as authored; there is no reprojection, so
  all features in one map should share a CRS.
- GeoJSON export keeps the source CRS in a legacy `crs` member; note that
  strict RFC 7946 expects WGS84 (reproject in QGIS/GDAL if needed).
- `Curve`/`Surface` with arc segments (rare in planning documents) are not
  supported — only straight-line geometries (`posList`/`pos`/`coordinates`).
- For PL-2000 zone 5 (EPSG:2176) the easting and northing ranges overlap, so
  axis auto-detection is disabled there — use `--swap-xy` if the map comes
  out rotated 90 degrees.
