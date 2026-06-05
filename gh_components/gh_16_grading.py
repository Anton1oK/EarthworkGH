"""Grasshopper component: proposed grading surface from design spot elevations."""

from __future__ import annotations

import importlib
import math
import sys


COMPONENT_INPUTS = (
    ("design_curve", "curve", "item"),
    ("boundary", "curve", "item", True),
    ("grid_size_m", "number", "item", True),
    ("datum_m", "number", "item", True),
    ("power", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("grading_mesh", "mesh", "item"),
    ("min_z", "number", "item"),
    ("max_z", "number", "item"),
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


design_curve = rhino_adapter.coerce_curve(globals().get("design_curve"))
if design_curve is None:
    raise ValueError(
        "Connect a design polyline whose vertices are the finished spot elevations. "
        + rhino_adapter.input_diagnostic(
            globals(), "design_curve", globals().get("design_curve"), "a polyline"
        )
    )
boundary_curve = rhino_adapter.coerce_curve(globals().get("boundary"))

units_per_meter = rhino_adapter.document_units_per_meter()
meters_per_unit = 1.0 / units_per_meter

design_points = rhino_adapter.curve_points_xyz(design_curve)
if len(design_points) < 1:
    raise ValueError("The design polyline has no vertices.")

_grid = globals().get("grid_size_m")
grid_size_m = (1.0 if _grid is None else float(_grid)) * STANDARD.input_length_factor
spacing = grid_size_m * units_per_meter
datum_m = (0.0 if globals().get("datum_m") is None else float(globals().get("datum_m"))) * STANDARD.input_length_factor
power = 2.0 if globals().get("power") is None else float(globals().get("power"))

if boundary_curve is not None:
    _poly = rhino_adapter.curve_polygon_xy(boundary_curve)
    min_x = min(p[0] for p in _poly)
    min_y = min(p[1] for p in _poly)
    max_x = max(p[0] for p in _poly)
    max_y = max(p[1] for p in _poly)
else:
    min_x = min(p[0] for p in design_points)
    min_y = min(p[1] for p in design_points)
    max_x = max(p[0] for p in design_points)
    max_y = max(p[1] for p in design_points)

columns = max(1, int(math.ceil((max_x - min_x) / spacing)))
rows = max(1, int(math.ceil((max_y - min_y) / spacing)))
if (columns + 1) * (rows + 1) > 90000:
    raise ValueError("Grading grid too fine; use a larger grid_size_m.")

_grid_points = earthwork_core.grade_by_points(
    design_points, (min_x, min_y), columns, rows, spacing,
    power=power, datum=datum_m * units_per_meter,
)
grading_mesh = rhino_adapter.grid_mesh(_grid_points, columns, rows)

_zs = [z for _x, _y, z in _grid_points]
min_z = min(_zs) * meters_per_unit
max_z = max(_zs) * meters_per_unit
report_ru = STANDARD.grading_report(len(design_points), datum_m, min_z, max_z)

bake_status = "Set 'bake' to true to write the grading surface onto a layer."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {"surface": [grading_mesh]}, STANDARD.grading_layers(), replace=True
        )
        bake_status = "Baked the grading surface onto {} layer(s).".format(len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
