"""Parse GML files (including Polish spatial-plan / MPZP exports) into features.

The parser is namespace-agnostic: it matches elements by local name, so it
works with GML 2.x (www.opengis.net/gml), GML 3.1/3.2 and any application
schema on top of them. Geometries supported:

    Point, LineString, Polygon,
    MultiPoint, MultiLineString, MultiCurve, MultiPolygon, MultiSurface,
    MultiGeometry, CompositeSurface, CompositeCurve, GeometricComplex

Features are grouped into layers named after the feature element (the element
directly under gml:featureMember, or the nearest non-wrapper ancestor of the
geometry if no featureMember wrapper exists).
"""

from __future__ import annotations

import gzip
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree
from shapely import transform as shapely_transform
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry

GEOMETRY_TAGS = {
    "Point", "LineString", "Polygon", "MultiPoint", "MultiLineString",
    "MultiCurve", "MultiPolygon", "MultiSurface", "MultiGeometry",
    "CompositeSurface", "CompositeCurve", "GeometricComplex",
}
SIMPLE_GEOM_TAGS = {"Point", "LineString", "Polygon"}
CONTAINER_TAGS = {"featureMember", "featureMembers", "member", "FeatureCollection", "boundedBy"}
_GML_NS_HINTS = ("gml", "opengis")

_PL_EPSG_ZONE = {"2177", "2178", "2179"}  # PL-2000 zones 6/7/8
_EPSG_4326_LIKE = {"4326", "4258"}


@dataclass
class Feature:
    layer: str
    props: dict
    geom: BaseGeometry
    srs: str | None = None
    source: str = ""

    @property
    def kind(self) -> str:
        t = self.geom.geom_type
        if "Point" in t:
            return "point"
        if "Line" in t or "Curve" in t:
            return "line"
        return "polygon"


def _local(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _ns(tag) -> str:
    if not isinstance(tag, str) or not tag.startswith("{"):
        return ""
    return tag[1:].split("}", 1)[0]


def _is_gml(el) -> bool:
    ns = _ns(el.tag).lower()
    return any(h in ns for h in _GML_NS_HINTS)


# ---------------------------------------------------------------------------
# input loading (.gml / .xml / .zip / .gz / directory)
# ---------------------------------------------------------------------------

def _iter_roots(source: str):
    path = Path(source)
    if path.is_dir():
        files = sorted({*path.glob("*.gml"), *path.glob("*.GML"), *path.glob("*.xml")})
        if not files:
            raise FileNotFoundError(f"No .gml/.xml files found in directory: {path}")
        for f in files:
            yield f.name, etree.parse(str(f)).getroot()
        return
    if not path.exists():
        raise FileNotFoundError(f"No such file or directory: {path}")
    suffix = path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith((".gml", ".xml"))]
            if not names:
                raise ValueError(f"No .gml/.xml members inside {path}")
            for n in names:
                yield f"{path.name}::{n}", etree.fromstring(zf.read(n))
    elif suffix in (".gz", ".gzip"):
        with gzip.open(path, "rb") as fh:
            yield path.name, etree.parse(fh).getroot()
    else:
        yield path.name, etree.parse(str(path)).getroot()


# ---------------------------------------------------------------------------
# geometry construction
# ---------------------------------------------------------------------------

def _to_float(v: str):
    try:
        return float(v)
    except ValueError:
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return None


def _srs_dim(el) -> int:
    node = el
    while node is not None:
        v = node.get("srsDimension") if isinstance(node.tag, str) else None
        if v:
            try:
                d = int(v)
                if d >= 2:
                    return d
            except ValueError:
                pass
        node = node.getparent()
    return 2


def _positions(el) -> list[tuple]:
    """Extract coordinate tuples from posList / pos / coordinates below el."""
    for d in el.iter():
        ln = _local(d.tag)
        if ln == "posList":
            raw = (d.text or "").split()
            if not raw:
                return []
            vals = [v for v in (_to_float(t) for t in raw) if v is not None]
            dim = _srs_dim(d)
            if not vals or len(vals) % dim != 0:
                for alt in (3, 2):
                    if len(vals) % alt == 0:
                        dim = alt
                        break
                else:
                    dim = 2
            n = (len(vals) // dim) * dim
            return [tuple(vals[i:i + dim]) for i in range(0, n, dim)]
        if ln == "pos":
            vals = [v for v in (_to_float(t) for t in (d.text or "").split()) if v is not None]
            if len(vals) < 2:
                return []
            return [tuple(vals[:max(2, _srs_dim(d))])]
        if ln == "coordinates":
            pts = []
            for tok in (d.text or "").split():
                xy = [v for v in (_to_float(p) for p in tok.split(",")) if v is not None]
                if len(xy) >= 2:
                    pts.append(tuple(xy[:3 if len(xy) >= 3 else 2]))
            return pts
    return []


def _first_desc(el, names):
    for d in el.iter():
        if d is not el and _local(d.tag) in names:
            return d
    return None


def _build_polygon(el) -> Polygon | None:
    ext = _first_desc(el, ("exterior", "outerBoundaryIs"))
    if ext is not None:
        ring = _first_desc(ext, ("LinearRing",))
        shell = _positions(ring if ring is not None else ext)
    else:
        ring = _first_desc(el, ("LinearRing",))
        shell = _positions(ring) if ring is not None else _positions(el)
    if len(shell) < 3:
        return None
    holes = []
    for holder in el.iter():
        if _local(holder.tag) in ("interior", "innerBoundaryIs"):
            r = _first_desc(holder, ("LinearRing",))
            hp = _positions(r if r is not None else holder)
            if len(hp) >= 3:
                holes.append(hp)
    try:
        return Polygon(shell, holes)
    except Exception:
        return None


def build_geometry(el) -> BaseGeometry | None:
    ln = _local(el.tag)
    if ln == "Point":
        pts = _positions(el)
        return Point(pts[0][:2]) if pts else None
    if ln == "LineString":
        pts = _positions(el)
        return LineString([p[:2] for p in pts]) if len(pts) >= 2 else None
    if ln == "Polygon":
        return _build_polygon(el)
    # Multi* / Composite* / GeometricComplex
    parts = []
    for d in el.iter():
        if d is el or _local(d.tag) not in SIMPLE_GEOM_TAGS:
            continue
        g = build_geometry(d)
        if g is not None and not g.is_empty:
            parts.append(g)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    if all(p.geom_type == "Polygon" for p in parts):
        return MultiPolygon(parts)
    return GeometryCollection(parts)


# ---------------------------------------------------------------------------
# feature discovery
# ---------------------------------------------------------------------------

def _is_wrapper(el) -> bool:
    """True if the element only carries geometry (no descriptive content)."""
    if (el.text or "").strip():
        return False
    for c in el:
        ln = _local(c.tag)
        if ln in GEOMETRY_TAGS or ln in CONTAINER_TAGS:
            continue
        if isinstance(c.tag, str) and _is_wrapper(c):
            continue
        return False
    return True


def _owning_feature(geom_el, root):
    """Find the feature element that owns a geometry element."""
    child = geom_el
    node = geom_el.getparent()
    while node is not None and isinstance(node.tag, str):
        ln = _local(node.tag)
        if ln in CONTAINER_TAGS:
            if _local(child.tag) in GEOMETRY_TAGS:
                return None
            return child
        if not _is_wrapper(node):
            return node
        child, node = node, node.getparent()
    return child


def _layer_name(feature_el) -> str:
    ln = _local(feature_el.tag)
    if not ln or ln in CONTAINER_TAGS or ln in GEOMETRY_TAGS:
        return "features"
    return ln


def _find_srs(el):
    node = el
    while node is not None:
        if isinstance(node.tag, str):
            v = node.get("srsName")
            if v:
                return v
        node = node.getparent()
    return None


def _props(feature_el) -> dict:
    """Collect text content of non-geometry descendants as attributes."""
    props: dict[str, str] = {}
    for el in feature_el.iter():
        if el is feature_el or not isinstance(el.tag, str):
            continue
        if _local(el.tag) in CONTAINER_TAGS or _is_gml(el):
            continue
        inside_geom = False
        a = el.getparent()
        while a is not None and isinstance(a.tag, str):
            if _local(a.tag) in GEOMETRY_TAGS:
                inside_geom = True
                break
            if a is feature_el:
                break
            a = a.getparent()
        if inside_geom:
            continue
        text = (el.text or "").strip()
        if not text:
            continue
        key = _local(el.tag)
        props[key] = f"{props[key]}; {text}" if key in props else text
    return props


def _geometry_elements(root):
    for el in root.iter():
        if not isinstance(el.tag, str) or _local(el.tag) not in GEOMETRY_TAGS:
            continue
        nested = False
        a = el.getparent()
        while a is not None:
            if isinstance(a.tag, str) and _local(a.tag) in GEOMETRY_TAGS:
                nested = True
                break
            a = a.getparent()
        if not nested:
            yield el


def parse_features(root, *, source: str = "") -> list[Feature]:
    owned: dict = {}
    for g in _geometry_elements(root):
        owner = _owning_feature(g, root)
        if owner is None:
            continue
        geom = build_geometry(g)
        if geom is None or geom.is_empty:
            continue
        owned.setdefault(owner, []).append(geom)
    features = []
    for owner, geoms in owned.items():
        geom = geoms[0] if len(geoms) == 1 else GeometryCollection(geoms)
        features.append(
            Feature(
                layer=_layer_name(owner),
                props=_props(owner),
                geom=geom,
                srs=_find_srs(g),
                source=source,
            )
        )
    return features


# ---------------------------------------------------------------------------
# axis orientation (EPSG handling for Polish systems)
# ---------------------------------------------------------------------------

def _in(v, lo, hi):
    return lo <= v <= hi


def _epsg_codes(srs: str | None) -> set[str]:
    if not srs:
        return set()
    return set(re.findall(r"(\d{4,5})", srs))


def _needs_swap(bounds, srs) -> bool:
    minx, miny, _, _ = bounds
    codes = _epsg_codes(srs)
    if codes & _PL_EPSG_ZONE:
        # PL-2000 zones 6/7/8: northing ~5.0-6.1M, easting 6.17-8.83M
        north = (4_900_000, 6_150_000)
        east = (6_160_000, 8_840_000)
        if _in(minx, *east) and _in(miny, *north):
            return False  # already easting,northing
        if _in(minx, *north) and _in(miny, *east):
            return True   # northing,easting -> swap
    if codes & _EPSG_4326_LIKE:
        lat = (47.0, 56.0)
        lon = (12.0, 26.0)
        if _in(minx, *lat) and _in(miny, *lon):
            return True   # lat,lon -> swap
    return False


def _flip_geom(geom):
    def _flip(arr):
        out = arr.copy()
        out[:, [0, 1]] = out[:, [1, 0]]
        return out
    return shapely_transform(geom, _flip)


def _apply_orientation(features: list[Feature], swap) -> list[Feature]:
    if not features:
        return features
    if swap is False:
        return features
    if swap is None:
        geoms = [f.geom for f in features if not f.geom.is_empty]
        if not geoms:
            return features
        srs = next((f.srs for f in features if f.srs), None)
        bounds = (
            min(g.bounds[0] for g in geoms),
            min(g.bounds[1] for g in geoms),
            max(g.bounds[2] for g in geoms),
            max(g.bounds[3] for g in geoms),
        )
        if not _needs_swap(bounds, srs):
            return features
    for f in features:
        if f.geom is not None and not f.geom.is_empty:
            f.geom = _flip_geom(f.geom)
    return features


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def parse_input(source: str, *, swap=None) -> list[Feature]:
    """Load a .gml/.xml/.zip/.gz file or a directory of GML files.

    swap: None = auto-detect axis order for known Polish/EPSG systems,
          True = always swap coordinate pairs, False = never swap.
    """
    features: list[Feature] = []
    for label, root in _iter_roots(source):
        features.extend(parse_features(root, source=label))
    return _apply_orientation(features, swap)


def group_layers(features: list[Feature]) -> dict[str, list[Feature]]:
    layers: dict[str, list[Feature]] = defaultdict(list)
    for f in features:
        layers[f.layer].append(f)
    return dict(layers)
