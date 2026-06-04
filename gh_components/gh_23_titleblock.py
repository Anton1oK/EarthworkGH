"""Grasshopper component: SPDS sheet frame + title block (simplified GOST 21.101)."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("sheet", "string", "item", True),
    ("origin", "point", "item", True),
    ("object_text", "string", "item", True),
    ("title_text", "string", "item", True),
    ("stage_scale_text", "string", "item", True),
    ("sheet_number", "string", "item", True),
    ("author_text", "string", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("frame_curves", "curve", "list"),
    ("title_lines", "curve", "list"),
    ("title_tags", "generic", "list"),
    ("bake_status", "string", "item"),
)


import os
try:
    PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    PROJECT_FOLDER = globals().get("PROJECT_FOLDER", "")
if PROJECT_FOLDER and PROJECT_FOLDER not in sys.path:
    sys.path.append(PROJECT_FOLDER)

import rhino_adapter
import standards
import version

rhino_adapter = importlib.reload(rhino_adapter)
standards = importlib.reload(standards)
version = importlib.reload(version)
STANDARD = standards.get_standard()


def _as_bool(value):
    if value is None:
        return False
    return bool(getattr(value, "Value", value))


def _as_str(value):
    if value is None:
        return ""
    return str(getattr(value, "Value", value))


units_per_meter = rhino_adapter.document_units_per_meter()
mm_scale = units_per_meter / 1000.0  # document units per millimetre

sheet_code = _as_str(globals().get("sheet")) or "A3"
width_mm, height_mm = STANDARD.sheet_size_mm(sheet_code)

_origin_value = globals().get("origin")
if _origin_value is not None:
    _origin_value = getattr(_origin_value, "Value", _origin_value)
try:
    origin = (float(_origin_value.X), float(_origin_value.Y), float(_origin_value.Z))
except Exception:
    origin = (0.0, 0.0, 0.0)

frame_curves = rhino_adapter.sheet_frame_geometry(width_mm, height_mm, origin, mm_scale)

_values = {
    "object": _as_str(globals().get("object_text")),
    "title": _as_str(globals().get("title_text")),
    "stage_scale": _as_str(globals().get("stage_scale_text")),
    "sheet_number": _as_str(globals().get("sheet_number")),
    "author": _as_str(globals().get("author_text")),
}
_rows = STANDARD.titleblock_rows(_values)
# Stamp the sheet with the tool version + the standard's regulation editions, so
# the drawing is traceable to what produced it.
_provenance = version.provenance(STANDARD)
title_lines, title_tags = rhino_adapter.titleblock_geometry(
    _rows, width_mm, height_mm, origin, mm_scale, stamp=_provenance
)

bake_status = "Set 'bake' to true to write the sheet frame onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {
                "frame": frame_curves,
                "titleblock": title_lines,
                "text": title_tags,
            },
            STANDARD.titleblock_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) onto {} layer(s).".format(_baked, len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
