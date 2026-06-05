"""Grasshopper component: blind area (otmostka) sloping away from a building."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("building_footprint", "curve", "item"),
    ("top_elevation_m", "number", "item", True),
    ("width_m", "number", "item", True),
    ("slope_percent", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("inner_edge", "curve", "item"),
    ("outer_edge", "curve", "item"),
    ("area_m2", "number", "item"),
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


def _closed_polyline(points_xy, z):
    points = [_rg.Point3d(x, y, z) for x, y in points_xy]
    points.append(points[0])
    return _rg.PolylineCurve(points)


footprint = rhino_adapter.coerce_curve(globals().get("building_footprint"))
if footprint is None:
    raise ValueError(
        "Connect a closed building footprint curve. "
        + rhino_adapter.input_diagnostic(
            globals(), "building_footprint", globals().get("building_footprint"),
            "a closed planar curve",
        )
    )

units_per_meter = rhino_adapter.document_units_per_meter()
meters_per_unit = 1.0 / units_per_meter


def _number(name, default):
    value = globals().get(name)
    return default if value is None else float(value)


top_elevation_m = _number("top_elevation_m", 0.0) * STANDARD.input_length_factor
width_m = _number("width_m", 1.0) * STANDARD.input_length_factor
slope_percent = _number("slope_percent", 3.0)

_inner_xy = rhino_adapter.curve_polygon_xy(footprint)
perimeter_m = earthwork_core.polygon_perimeter(_inner_xy) * meters_per_unit
area_m2 = earthwork_core.working_space_area(perimeter_m, width_m)
fall_m = width_m * slope_percent / 100.0

top_z = top_elevation_m * units_per_meter
outer_z = (top_elevation_m - fall_m) * units_per_meter

inner_edge = _closed_polyline(_inner_xy, top_z)
_offset = rhino_adapter.offset_curve_outward(footprint, width_m * units_per_meter)
if _offset is not None:
    outer_edge = _closed_polyline(rhino_adapter.curve_polygon_xy(_offset), outer_z)
else:
    outer_edge = None

report_ru = STANDARD.blind_area_report(width_m, slope_percent, perimeter_m, area_m2)

bake_status = "Set 'bake' to true to write the blind area onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {
                "outer": [outer_edge] if outer_edge else [],
                "inner": [inner_edge],
            },
            STANDARD.blind_area_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) onto {} layer(s).".format(_baked, len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
