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
| `--geojson PATH` | Export features to GeoJSON |
| `--swap-xy` | Force swapping coordinate pairs (fix axis order manually) |
| `--no-swap` | Disable automatic axis-order correction |
| `--title TEXT` | Custom map title |
| `--dpi N` | PNG resolution (default 200) |
| `--no-show` | Do not open an interactive window |
| `--web [PORT]` | Serve the map in a browser with pan/zoom (default port 8988) |

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
    --zones zones.json --colors colors_oznaczenia.json
```

- `zones.json` holds groups (A, B, C, D), each a list of objects with a
  `name` and `zones`: an array of individual oznaczenia
  (`["1SU", "2SU", "254SU"]`, numerically sorted). A comma-separated
  string is also accepted for backward compatibility.
- `colors_oznaczenia.json` holds only group colors:

```json
{
  "A": "#4daf4a",
  "B": "#ff7f00",
  "C": "#377eb8",
  "D": "#984ea3",
  "_default": "#dddddd"
}
```

Oznaczenia not listed in any group (and features without `oznaczenie`, e.g.
the plan boundary) fall back to `_default`.

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
