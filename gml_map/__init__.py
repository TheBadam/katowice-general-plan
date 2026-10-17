"""gml_map: a small toolkit for parsing and rendering GML (Geography Markup
Language) files, with support for files produced by Polish spatial-planning
(MPZP / plan ogólny) systems."""

from .parser import Feature, parse_input, group_layers
from .render import render

__all__ = ["Feature", "parse_input", "group_layers", "render"]
