"""Grasshopper component: relief preview - slope arrows and spot elevations."""

from __future__ import annotations

import importlib
import math
import sys


COMPONENT_INPUTS = (
    ("terrain_mesh", "mesh", "item"),
    ("boundary", "curve", "item", True),
    ("grid_size_m", "number", "item", True),
    ("arrow_length_m", "number", "item", True),
    ("min_slope_percent", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("slope_arrows", "curve", "list"),
    ("spot_elevations", "generic", "list"),
    ("max_slope_percent", "number", "item"),
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
grid_size_m = (5.0 if _grid is None else float(_grid)) * STANDARD.input_length_factor
grid = rhino_adapter.analysis_grid(terrain, boundary_curve, grid_size_m)
units_per_meter = grid.units_per_meter
meters_per_unit = grid.meters_per_unit

_arrow = globals().get("arrow_length_m")
arrow_length = 0.6 * grid.spacing if _arrow is None else float(_arrow) * STANDARD.input_length_factor * units_per_meter
_min_pct = globals().get("min_slope_percent")
min_steepness = 0.0 if _min_pct is None else float(_min_pct) / 100.0

samples = earthwork_core.slope_field(
    grid.sampler, grid.origin, grid.columns, grid.rows, grid.spacing, inside=grid.inside
)
max_slope_percent = (
    max((s.steepness for s in samples), default=0.0) * 100.0
)

slope_arrows = rhino_adapter.slope_arrow_curves(
    samples, grid.sampler, arrow_length, unit_scale=units_per_meter,
    min_steepness=min_steepness,
)
spot_elevations = rhino_adapter.spot_elevation_tags(
    samples, meters_per_unit, 0.3 * units_per_meter, unit_scale=units_per_meter
)
report_ru = STANDARD.relief_report(
    grid_size_m, len(samples), max_slope_percent, len(slope_arrows)
)

bake_status = "Set 'bake' to true to write the relief preview onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {"arrows": slope_arrows, "spots": spot_elevations},
            STANDARD.relief_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) onto {} layer(s).".format(_baked, len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
