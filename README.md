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
  interactive **static web map** via `--export-static`, a PNG image, an
  attribute dump, and a GeoJSON export.

## Install

Requires Python 3.10+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Dependencies: `lxml`, `shapely`, `matplotlib` (plus `pyproj` for
`fetch_streets.py`).

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
```

### Static export (host anywhere)

`--export-static DIR` writes the same interactive viewer as a fully static
site: `index.html` (auto language) plus `en/index.html` and `pl/index.html`,
and `mapdata.json` (~8 MB for the Katowice plan). No Python or server-side
code is needed at serving time: for development, Python's simple built-in
server is enough; in production the site is plain static files handed out
by any web server (nginx, Apache, GitHub Pages, Netlify, S3, or even a
file:// URL) - no Python or Tornado involved. The
matplotlib-specific link is dropped; everything else (layer toggles,
opacity, hover details, street names, descriptions, PNG download) works
identically. The panel is organized into sections ("GML layers",
"Environmental impact", "Streets") and the UI language follows the URL:
`/en/` (English), `/pl/` (Polish), or auto-detected from the browser at any
other path (Polish by default, English for English browser locales) - use
the EN/PL switcher in the panel to move between them:

```bash
.venv/bin/python gml_viewer.py plan.gml --zones zones.json \
    --settings settings.json --overlay --streets streets.geojson \
    --descriptions zones_description.json \
    --page-title "Environmental impact on Katowice plan" \
    --page-note page_note.txt \
    --page-link "Environmental report=https://planogolnydlakatowic.pl/" \
    --export-static static_site

python3 -m http.server -d static_site 8000    # development preview
# production: upload the static_site/ folder to any web server
```

The page fetches `mapdata.json` relative to its own URL (one directory up
for the language folders), so it works at any path. Pre-generate a preview
PNG with `-o map.png` in the same command.

All viewer UI labels (panel section headers, buttons, tooltips, the load
error message) live in one config file, `i18n.json`, passed with `--i18n`
and layered over the built-in EN/PL set; without it the built-in set is
used. Page links translate as well: a `--page-link KEY=URL` entry shows
the current language's `link.KEY` label from `i18n.json`, falling back to
the raw name when there is no such entry. The language still follows the
URL (`/en/`, `/pl/`); auto-detected
visitors get Polish, except for English browser locales.

**Gzip compression (optional).** `mapdata.json` (~8 MB) gzips to about a
quarter of its size, and most hosts compress text responses
automatically. On Apache-based shared hosting where compression is off
by default (e.g. OVH), add these lines to the server's `.htaccess`
(Apache applies it recursively, so a directory above the site files
works too):

```apache
<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE application/json text/html text/css application/javascript image/svg+xml
</IfModule>
```

FTP clients hide dotfiles by default - enable "show hidden files" when
editing or uploading it. To verify that compression is active:

```bash
curl -s -o /dev/null -w '%{size_download} bytes\n' \
    -H 'Accept-Encoding: gzip' https://host/mapdata.json
```

About 2 MB means gzip is working; about 8 MB means the response is
uncompressed. If the lines are in the server's `.htaccess` and the size
stays at 8 MB, the host is ignoring the directive and compression must
be enabled host-side instead.

For the Katowice plan there is a launcher that exports the static site
without starting any server:

```bash
./export_katowice.sh            # -> static_site/ (add -o map.png for a preview)
```

`run_katowice.sh` rebuilds the static site (via `export_katowice.sh`) and
previews it locally with `python3 -m http.server`.

### Interactive group viewer

When `--export-static` is combined with `--zones`/`--colors`/`--settings`, the exported
page is a custom canvas viewer with per-group controls:

- checkbox per layer/group to toggle it on/off,
- opacity slider per layer/group,
- drag the divider between the map and the panel to resize the panel
  (width is remembered),
- hover a shape to see its details (oznaczenie with the zone-type title,
  layer, group, symbol, group description); the dashed zone outline
  reacts instantly, the details tooltip appears after the pointer rests
  for 200 ms and can be disabled with the "On-hover details" switch
  under the "GML layers" section header (the outline keeps working);
  click to pin the details, click again or Esc to unpin,
- drag to pan, mouse wheel to zoom,
- Download PNG button (renders the current view).

```bash
.venv/bin/python gml_viewer.py plan.gml --zones zones.json \
    --settings settings.json --export-static site
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
    --settings settings.json --streets streets.geojson --export-static site
```

The streets file is plain GeoJSON (LineString/MultiLineString with a `name`
property), so any other source works too - it just has to be in the same
CRS as the plan. Options: `--highways` (regex of OSM highway types),
`--buffer` (meters around plan bounds), `--overpass` (custom API URL).

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
| `--colors JSON` | Color schema file (or the `"group"` section of `settings.json`); see below |
| `--settings JSON` | Combined configuration (`settings.json`): `"group"` (color schema + optional `global_hatch`), `"zone"` (zone-type definitions), `"highlight"` (hovered-zone outline: `color`, `width`, `dash` px) |
| `--zones JSON` | Group definitions (`zones.json`); see below |
| `--color-prop PROP` | Property matched against the color schema (default: `oznaczenie`) |
| `--zone-definition JSON` | Paint zone-type features by symbol: fill `color` + `stroke` borders (or the `"zone"` section of `settings.json`) |
| `--overlay` | Paint groups as overlays on the original GML rendering |
| `--default-off GROUP` | Layer/group unchecked by default in the viewer (repeatable) |
| `--descriptions JSON` | Group descriptions shown in the viewer panel |
| `--page-title TEXT` | Page title (browser tab and panel header) |
| `--page-note FILE` | Plain text shown in a collapsible "Explanation" block |
| `--changelog FILE` | Markdown shown in the sidebar as a collapsible "Changelog" section (collapsed by default, not part of the shareable URL state) |
| `--page-link NAME=URL` | Link shown at the top of the page (repeatable) |
| `--streets GEOJSON` | Overlay named streets (see fetch_streets.py) |
| `--i18n JSON` | Viewer UI labels `{lang: {key: text}}` layered over the built-in EN/PL set (e.g. `i18n.json`) |
| `--geojson PATH` | Export features to GeoJSON |
| `--swap-xy` | Force swapping coordinate pairs (fix axis order manually) |
| `--no-swap` | Disable automatic axis-order correction |
| `--title TEXT` | Custom map title |
| `--dpi N` | PNG resolution (default 200) |
| `--no-show` | Do not open an interactive window |
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
    --zones zones.json --settings settings.json
```

- `zones.json` holds groups (A, B, C, D), each a list of objects with a
  `name` and `zones`: an array of individual oznaczenia
  (`["1SU", "2SU", "254SU"]`, numerically sorted). A comma-separated
  string is also accepted for backward compatibility.
- the `"group"` section of `settings.json` holds the group colors, the
  `_default` color for ungrouped oznaczenia, and the optional
  `global_hatch` configuration of the overlay hatch (line width and
  spacing in px; `alpha` is the opacity of the solid color between the
  hatch lines). The `"zone"` section holds zone-type definitions
  (`{symbol: {"title", "color", "stroke", "alpha"}}`) painting
  zone-type features by symbol, and `"highlight"` the hovered-zone
  outline style (`{"color": ..., "width": px, "dash": [on, off, ...] px}`):

```json
{
  "group": {
    "global_hatch": {"width": 5, "spacing": 20, "alpha": 0.7},
    "A": "#4daf4a",
    "B": "#ff7f00",
    "C": "#377eb8",
    "D": "#984ea3",
    "_default": "#dddddd"
  },
  "zone": {
    "SN": {"title": "Strefa zieleni i rekreacji", "color": "#4daf4a",
            "stroke": "#191919", "alpha": 1.0}
  },
  "highlight": {"color": "#111111", "width": 3.5, "dash": [16, 12]}
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
    --settings settings.json --overlay
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
