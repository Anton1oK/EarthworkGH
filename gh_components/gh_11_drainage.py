"""Grasshopper component: drainage - flow traces and ponding (low) points."""

from __future__ import annotations

import importlib
import math
import sys


COMPONENT_INPUTS = (
    ("terrain_mesh", "mesh", "item"),
    ("boundary", "curve", "item", True),
    ("grid_size_m", "number", "item", True),
    ("seed_every", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("flow_paths", "curve", "list"),
    ("low_points", "point", "list"),
    ("high_points", "point", "list"),
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
grid_size_m = (2.0 if _grid is None else float(_grid)) * STANDARD.input_length_factor
grid = rhino_adapter.analysis_grid(terrain, boundary_curve, grid_size_m)
units_per_meter = grid.units_per_meter
_seed = globals().get("seed_every")
seed_every = 3 if _seed is None else max(1, int(_seed))

analysis = earthwork_core.drainage_analysis(
    grid.sampler, grid.origin, grid.columns, grid.rows, grid.spacing,
    inside=grid.inside, seed_every=seed_every,
)

flow_paths = rhino_adapter.flow_path_curves(
    analysis.flow_paths, unit_scale=units_per_meter
)
low_points = rhino_adapter.drainage_points(analysis.low_points, unit_scale=units_per_meter)
high_points = rhino_adapter.drainage_points(analysis.high_points, unit_scale=units_per_meter)
report_ru = STANDARD.drainage_report(
    grid_size_m, len(flow_paths), len(analysis.low_points), len(analysis.high_points)
)

bake_status = "Set 'bake' to true to write the drainage analysis onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {"flow": flow_paths, "low": low_points, "high": high_points},
            STANDARD.drainage_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) onto {} layer(s).".format(_baked, len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
