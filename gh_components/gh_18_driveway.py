"""Grasshopper component: driveway/path grade design and compliance check."""

from __future__ import annotations

import bisect
import importlib
import math
import sys


COMPONENT_INPUTS = (
    ("centerline", "curve", "item"),
    ("width_m", "number", "item", True),
    ("max_grade_percent", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("path_edges", "curve", "list"),
    ("grade_marks", "generic", "list"),
    ("max_grade_percent", "number", "item"),
    ("compliant", "boolean", "item"),
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


def _as_bool(value):
    if value is None:
        return False
    return bool(getattr(value, "Value", value))


centerline = rhino_adapter.coerce_curve(globals().get("centerline"))
if centerline is None:
    raise ValueError(
        "Connect a 3D centreline (vertices at design elevations). "
        + rhino_adapter.input_diagnostic(
            globals(), "centerline", globals().get("centerline"), "a polyline"
        )
    )

units_per_meter = rhino_adapter.document_units_per_meter()

width_m = (3.0 if globals().get("width_m") is None else float(globals().get("width_m"))) * STANDARD.input_length_factor
_max = globals().get("max_grade_percent")
max_allowed = STANDARD.path_default_max_grade_percent if _max is None else float(_max)

_points = rhino_adapter.curve_points_xyz(centerline)
if len(_points) < 2:
    raise ValueError("The centreline needs at least two vertices.")

stations = []
distance = 0.0
previous = None
for x, y, z in _points:
    if previous is not None:
        distance += math.hypot(x - previous[0], y - previous[1])
    previous = (x, y, z)
    stations.append((distance, x, y, z))

profile = earthwork_core.path_grades([(d, z) for d, _x, _y, z in stations])
max_grade_percent = profile.max_abs_grade_percent
compliant = max_grade_percent <= max_allowed + 1e-9

station_xy = [(d, x, y) for d, x, y, _z in stations]
_dist = [d for d, _x, _y, _z in stations]
_zat = [z for _d, _x, _y, z in stations]


def _station_z(d):
    if d <= _dist[0]:
        return _zat[0]
    if d >= _dist[-1]:
        return _zat[-1]
    index = bisect.bisect_right(_dist, d) - 1
    d0, d1 = _dist[index], _dist[index + 1]
    ratio = 0.0 if d1 == d0 else (d - d0) / (d1 - d0)
    return _zat[index] + ratio * (_zat[index + 1] - _zat[index])


_left, _right = rhino_adapter.offset_curve_both(centerline, 0.5 * width_m * units_per_meter)
path_edges = [edge for edge in (_left, _right) if edge is not None]
grade_marks = rhino_adapter.path_grade_marks(
    profile, station_xy, _station_z, STANDARD.path_grade_label,
    0.4 * units_per_meter, unit_scale=units_per_meter,
)
report_ru = STANDARD.path_grade_report(profile, max_allowed, compliant)

bake_status = "Set 'bake' to true to write the path onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {"edges": path_edges, "marks": grade_marks},
            STANDARD.path_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) onto {} layer(s).".format(_baked, len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
