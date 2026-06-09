"""Grasshopper component: relief analysis - slope arrows, spot elevations,
contours and drainage in one pass.

Combines the former gh_09 (relief), gh_10 (contours) and gh_11 (drainage): they
all ray-sample the same terrain grid, so doing it once is faster. Wire the
outputs you need; leave the rest.
"""

from __future__ import annotations

import importlib
import math
import sys


COMPONENT_INPUTS = (
    ("terrain_mesh", "mesh", "item"),
    ("boundary", "curve", "item", True),
    ("grid_size_m", "number", "item", True),
    ("min_slope_percent", "number", "item", True),
    ("arrow_length_m", "number", "item", True),
    ("interval_m", "number", "item", True),
    ("major_every", "number", "item", True),
    ("seed_every", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("slope_arrows", "curve", "list"),
    ("spot_elevations", "generic", "list"),
    ("minor_contours", "curve", "list"),
    ("major_contours", "curve", "list"),
    ("levels_m", "number", "list"),
    ("flow_paths", "curve", "list"),
    ("low_points", "point", "list"),
    ("high_points", "point", "list"),
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
grid_size_m = (2.0 if _grid is None else float(_grid)) * STANDARD.input_length_factor

# One ray-sampled grid feeds all three analyses.
grid = rhino_adapter.analysis_grid(terrain, boundary_curve, grid_size_m)
units_per_meter = grid.units_per_meter
meters_per_unit = grid.meters_per_unit

# --- Slope arrows + spot elevations ---------------------------------------
_arrow = globals().get("arrow_length_m")
arrow_length = (
    0.6 * grid.spacing if _arrow is None
    else float(_arrow) * STANDARD.input_length_factor * units_per_meter
)
_min_pct = globals().get("min_slope_percent")
min_steepness = 0.0 if _min_pct is None else float(_min_pct) / 100.0

samples = earthwork_core.slope_field(
    grid.sampler, grid.origin, grid.columns, grid.rows, grid.spacing, inside=grid.inside
)
max_slope_percent = max((s.steepness for s in samples), default=0.0) * 100.0
slope_arrows = rhino_adapter.slope_arrow_curves(
    samples, grid.sampler, arrow_length, unit_scale=units_per_meter,
    min_steepness=min_steepness,
)
spot_elevations = rhino_adapter.spot_elevation_tags(
    samples, meters_per_unit, 0.3 * units_per_meter, unit_scale=units_per_meter
)

# --- Contours -------------------------------------------------------------
_interval = globals().get("interval_m")
interval_m = (0.5 if _interval is None else float(_interval)) * STANDARD.input_length_factor
interval = interval_m * units_per_meter
_major = globals().get("major_every")
major_every = 5 if _major is None else max(1, int(_major))

_segments = earthwork_core.contour_segments(
    grid.sampler, grid.origin, grid.columns, grid.rows, grid.spacing,
    interval, base=0.0, inside=grid.inside,
)
_minor_seg = []
_major_seg = []
for level, start, end in _segments:
    step = int(round(level / interval)) if interval else 0
    (_major_seg if step % major_every == 0 else _minor_seg).append((level, start, end))
minor_contours = rhino_adapter.contour_curves(_minor_seg, unit_scale=units_per_meter)
major_contours = rhino_adapter.contour_curves(_major_seg, unit_scale=units_per_meter)
levels_m = sorted({round(level * meters_per_unit, 3) for level, _s, _e in _segments})

# --- Drainage -------------------------------------------------------------
_seed = globals().get("seed_every")
seed_every = 3 if _seed is None else max(1, int(_seed))

analysis = earthwork_core.drainage_analysis(
    grid.sampler, grid.origin, grid.columns, grid.rows, grid.spacing,
    inside=grid.inside, seed_every=seed_every,
)
flow_paths = rhino_adapter.flow_path_curves(analysis.flow_paths, unit_scale=units_per_meter)
low_points = rhino_adapter.drainage_points(analysis.low_points, unit_scale=units_per_meter)
high_points = rhino_adapter.drainage_points(analysis.high_points, unit_scale=units_per_meter)

report_ru = "\n\n".join([
    STANDARD.relief_report(grid_size_m, len(samples), max_slope_percent, len(slope_arrows)),
    STANDARD.contour_report(interval_m, len(_minor_seg), len(_major_seg), levels_m),
    STANDARD.drainage_report(
        grid_size_m, len(flow_paths), len(analysis.low_points), len(analysis.high_points)
    ),
])

bake_status = "Set 'bake' to true to write the relief analysis onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked_total = 0
        _layer_total = 0
        for _geometry, _group in (
            ({"arrows": slope_arrows, "spots": spot_elevations}, STANDARD.relief_layers()),
            ({"minor": minor_contours, "major": major_contours}, STANDARD.contour_layers()),
            ({"flow": flow_paths, "low": low_points, "high": high_points}, STANDARD.drainage_layers()),
        ):
            _b, _l = rhino_adapter.bake_group(_geometry, _group, replace=True)
            _baked_total += _b
            _layer_total += len(_l)
        bake_status = "Baked {} object(s) onto {} layer(s).".format(_baked_total, _layer_total)
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
