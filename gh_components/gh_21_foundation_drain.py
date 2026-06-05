"""Grasshopper component: foundation perimeter (ring) drain line."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("foundation_footprint", "curve", "item"),
    ("offset_m", "number", "item", True),
    ("depth_below_m", "number", "item", True),
    ("reference_elevation_m", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("drain_curve", "curve", "item"),
    ("length_m", "number", "item"),
    ("report_ru", "string", "item"),
    ("bake_status", "string", "item"),
)


import os
try:
    PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    PROJECT_FOLDER = globals().get("PROJECT_FOLDER", "")
if PROJECT_FOLDER and PROJECT_FOLDER not in sys.path:
    sys.path.append(PROJECT_FOLDER)

import earthwork_core
import rhino_adapter
import standards

earthwork_core = importlib.reload(earthwork_core)
rhino_adapter = importlib.reload(rhino_adapter)
standards = importlib.reload(standards)
STANDARD = standards.get_standard()

import Rhino.Geometry as _rg


def _as_bool(value):
    if value is None:
        return False
    return bool(getattr(value, "Value", value))


footprint = rhino_adapter.coerce_curve(globals().get("foundation_footprint"))
if footprint is None:
    raise ValueError(
        "Connect a closed foundation footprint curve. "
        + rhino_adapter.input_diagnostic(
            globals(), "foundation_footprint", globals().get("foundation_footprint"),
            "a closed planar curve",
        )
    )

units_per_meter = rhino_adapter.document_units_per_meter()
meters_per_unit = 1.0 / units_per_meter


def _number(name, default):
    value = globals().get(name)
    return default if value is None else float(value)


_LEN = STANDARD.input_length_factor
offset_m = _number("offset_m", 0.4) * _LEN
depth_below_m = _number("depth_below_m", 0.3) * _LEN
reference_m = _number("reference_elevation_m", 0.0) * _LEN
invert_m = reference_m - depth_below_m

drain_curve = None
length_m = 0.0
_offset = rhino_adapter.offset_curve_outward(footprint, offset_m * units_per_meter)
if _offset is not None:
    _xy = rhino_adapter.curve_polygon_xy(_offset)
    length_m = earthwork_core.polygon_perimeter(_xy) * meters_per_unit
    _z = invert_m * units_per_meter
    _points = [_rg.Point3d(x, y, _z) for x, y in _xy]
    _points.append(_points[0])
    drain_curve = _rg.PolylineCurve(_points)

report_ru = STANDARD.foundation_drain_report(offset_m, depth_below_m, length_m, invert_m)

bake_status = "Set 'bake' to true to write the drain line onto a layer."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {"drain": [drain_curve] if drain_curve else []},
            STANDARD.foundation_drain_layers(),
            replace=True,
        )
        bake_status = "Baked the drain line onto {} layer(s).".format(len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
