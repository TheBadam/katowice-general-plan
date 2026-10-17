"""Render parsed GML layers with matplotlib."""

from __future__ import annotations

import math

import matplotlib
from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path
from shapely.geometry.base import BaseGeometry

from .parser import Feature

_POLYGON_Z = 2
_LINE_Z = 3
_POINT_Z = 4


def _flatten(geom: BaseGeometry):
    if hasattr(geom, "geoms"):
        for p in geom.geoms:
            yield from _flatten(p)
    else:
        yield geom


def _kind(g: BaseGeometry) -> str:
    t = g.geom_type
    if "Point" in t:
        return "point"
    if "Line" in t or "Curve" in t:
        return "line"
    return "polygon"


def _poly_patch(poly, facecolor, edgecolor):
    verts, codes = [], []
    for ring in (poly.exterior, *poly.interiors):
        pts = list(ring.coords)
        if len(pts) < 3:
            continue
        verts.extend(pts)
        codes.append(Path.MOVETO)
        codes.extend([Path.LINETO] * (len(pts) - 2))
        codes.append(Path.CLOSEPOLY)
    if not verts:
        return None
    return PathPatch(Path(verts, codes), facecolor=facecolor,
                     edgecolor=edgecolor, linewidth=0.8, zorder=_POLYGON_Z)


def _add_scalebar(ax, xmin, ymin, width, height):
    if width < 1:  # degrees (geographic CRS) -> no metric bar
        return
    target = width / 8
    m = 10 ** math.floor(math.log10(target)) if target > 0 else 1
    candidates = [n * m for n in (1, 2, 5, 10)]
    bar = min(candidates, key=lambda v: abs(v - target))
    x0 = xmin + width * 0.04
    y0 = ymin + height * 0.06
    ax.plot([x0, x0 + bar], [y0, y0], color="black", lw=3,
            solid_capstyle="butt", zorder=_POINT_Z + 2)
    ax.text(x0 + bar / 2, y0 + height * 0.015, f"{bar:g} m",
            ha="center", fontsize=8, zorder=_POINT_Z + 2)


def render(layers: dict[str, list[Feature]], *, title="", subtitle="",
           label_prop=None, out=None, dpi=200, show=True, keep_open=False,
           color_fn=None, legend_entries=None):
    """Draw all layers; optionally save to `out` and/or show a window.

    Returns the path written (or None) and shows the window if requested.
    """
    fig, ax = plt.subplots(figsize=(12.5, 9))
    ax.set_axisbelow(True)
    cmap = plt.get_cmap("tab20")
    names = sorted(layers, key=str.lower)
    colors = {name: cmap(i % 20) for i, name in enumerate(names)}
    edge = {name: tuple(v * 0.55 for v in to_rgb(colors[name])) for name in names}

    xmin = ymin = math.inf
    xmax = ymax = -math.inf
    drawn: set[str] = set()

    for kind in ("polygon", "line", "point"):
        for name in names:
            for f in layers[name]:
                if color_fn is not None:
                    c = color_fn(f)
                    ec = tuple(v * 0.55 for v in to_rgb(c))
                    fc = (*to_rgb(c), 0.62)
                else:
                    c = colors[name]
                    ec = edge[name]
                    fc = (*to_rgb(c), 0.62)
                for g in _flatten(f.geom):
                    if _kind(g) != kind:
                        continue
                    b = g.bounds
                    xmin, ymin = min(xmin, b[0]), min(ymin, b[1])
                    xmax, ymax = max(xmax, b[2]), max(ymax, b[3])
                    drawn.add(name)
                    if kind == "polygon":
                        p = _poly_patch(g, fc, ec)
                        if p is not None:
                            ax.add_patch(p)
                    elif kind == "line":
                        ax.add_collection(LineCollection(
                            [list(g.coords)], colors=[ec],
                            linewidths=1.4, zorder=_LINE_Z))
                    else:
                        ax.scatter(g.x, g.y, s=22, color=c, edgecolor=ec,
                                   linewidths=0.7, zorder=_POINT_Z)

    if not drawn:
        plt.close(fig)
        raise ValueError("No drawable geometry found.")

    dx = (xmax - xmin) or 1.0
    dy = (ymax - ymin) or 1.0
    ax.set_xlim(xmin - dx * 0.03, xmax + dx * 0.03)
    ax.set_ylim(ymin - dy * 0.03, ymax + dy * 0.03)
    ax.set_aspect("equal")
    ax.grid(alpha=0.3, linestyle=":")
    ax.ticklabel_format(useOffset=False, style="plain")

    if legend_entries is not None:
        proxies = [
            Patch(facecolor=c, edgecolor=tuple(v * 0.55 for v in to_rgb(c)),
                  label=label)
            for label, c in legend_entries
        ]
    else:
        proxies = []
        for name in names:
            if name not in drawn:
                continue
            k = _kind(next(_flatten(layers[name][0].geom)))
            if k == "polygon":
                proxies.append(Patch(facecolor=colors[name], edgecolor=edge[name], label=name))
            elif k == "line":
                proxies.append(Line2D([0], [0], color=edge[name], lw=2, label=name))
            else:
                proxies.append(Line2D([0], [0], marker="o", color="none",
                                      markerfacecolor=colors[name],
                                      markeredgecolor=edge[name], markersize=7, label=name))
    ax.legend(handles=proxies, loc="upper right", fontsize=8,
              framealpha=0.85,
              title=None if legend_entries is not None else "Layers")

    if label_prop:
        for name in names:
            for f in layers[name]:
                val = f.props.get(label_prop)
                if not val:
                    continue
                for g in _flatten(f.geom):
                    if _kind(g) != "polygon":
                        continue
                    p = g.representative_point()
                    ax.annotate(val, (p.x, p.y), fontsize=7,
                                ha="center", va="center", zorder=_POINT_Z + 1)

    if title:
        ax.set_title(title, fontsize=13)
    if subtitle:
        ax.set_xlabel(subtitle, fontsize=9)

    _add_scalebar(ax, xmin, ymin, xmax - xmin, ymax - ymin)

    written = None
    if out:
        fig.savefig(out, dpi=dpi, bbox_inches="tight")
        written = out
    if show:
        plt.show()
    elif not keep_open:
        plt.close(fig)
    return fig if keep_open else written


def can_show_interactively() -> bool:
    backend = matplotlib.get_backend().lower()
    return backend not in ("agg", "pdf", "ps", "svg", "template", "cairo",
                          "cairopng", "png")
