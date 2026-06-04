"""Grasshopper component: proposed contours (horizontals) from a terrain mesh."""

from __future__ import annotations

import importlib
import math
import sys


COMPONENT_INPUTS = (
    ("terrain_mesh", "mesh", "item"),
    ("boundary", "curve", "item", True),
    ("interval_m", "number", "item", True),
    ("major_every", "number", "item", True),
    ("grid_size_m", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("minor_contours", "curve", "list"),
    ("major_contours", "curve", "list"),
    ("levels_m", "number", "list"),
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


terrain = rhino_adapter.coerce_mesh(globals().get("terrain_mesh"))
if terrain is None:
    raise ValueError(
        "Connect a terrain mesh. "
        + rhino_adapter.input_diagnostic(
            globals(), "terrain_mesh", globals().get("terrain_mesh"), "a mesh"
        )
    )
boundary_curve = rhino_adapter.coerce_curve(globals().get("boundary"))

_grid = globals().get("grid_size_m")
grid_size_m = 2.0 if _grid is None else float(_grid)
grid = rhino_adapter.analysis_grid(terrain, boundary_curve, grid_size_m)
units_per_meter = grid.units_per_meter
meters_per_unit = grid.meters_per_unit

_interval = globals().get("interval_m")
interval_m = 0.5 if _interval is None else float(_interval)
interval = interval_m * units_per_meter
_major = globals().get("major_every")
major_every = 5 if _major is None else max(1, int(_major))

_segments = earthwork_core.contour_segments(
    grid.sampler, grid.origin, grid.columns, grid.rows, grid.spacing,
    interval, base=0.0, inside=grid.inside,
)

_minor = []
_major = []
for level, start, end in _segments:
    step = int(round(level / interval)) if interval else 0
    (_major if step % major_every == 0 else _minor).append((level, start, end))

minor_contours = rhino_adapter.contour_curves(_minor, unit_scale=units_per_meter)
major_contours = rhino_adapter.contour_curves(_major, unit_scale=units_per_meter)
levels_m = sorted({round(level * meters_per_unit, 3) for level, _s, _e in _segments})
report_ru = STANDARD.contour_report(interval_m, len(_minor), len(_major), levels_m)

bake_status = "Set 'bake' to true to write the contours onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {"minor": minor_contours, "major": major_contours},
            STANDARD.contour_layers(),
            replace=True,
        )
        bake_status = "Baked {} contour segment(s) onto {} layer(s).".format(
            _baked, len(_layers)
        )
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
