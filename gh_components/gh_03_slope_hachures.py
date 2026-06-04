"""Grasshopper component: excavation-pit slope hachures from a terrain mesh."""

from __future__ import annotations

import importlib
import math
import sys


COMPONENT_INPUTS = (
    ("terrain_mesh", "mesh", "item"),
    ("boundary", "curve", "item", True),
    ("grid_size_m", "number", "item", True),
    ("min_slope_1_to", "number", "item", True),
    ("hachure_length_m", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("slope_hachures", "curve", "list"),
    ("slope_outline", "curve", "list"),
    ("max_slope_1_to", "number", "item"),
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
        "Connect a 2.5D terrain/pit mesh. "
        + rhino_adapter.input_diagnostic(
            globals(), "terrain_mesh", globals().get("terrain_mesh"), "a mesh"
        )
    )
boundary_curve = rhino_adapter.coerce_curve(globals().get("boundary"))

units_per_meter = rhino_adapter.document_units_per_meter()

_grid = globals().get("grid_size_m")
grid_size_m = 1.0 if _grid is None else float(_grid)
spacing = grid_size_m * units_per_meter

_min_slope = globals().get("min_slope_1_to")
min_slope_1_to = 5.0 if _min_slope is None else float(_min_slope)
min_steepness = 1.0 / min_slope_1_to if min_slope_1_to > 0.0 else 0.2

_hachure = globals().get("hachure_length_m")
hachure_length = (
    0.8 * spacing if _hachure is None else float(_hachure) * units_per_meter
)

# Analysis region: the boundary's extent when given, otherwise the whole mesh.
inside = None
if boundary_curve is not None:
    _polygon = earthwork_core.normalize_polygon(
        rhino_adapter.curve_polygon_xy(boundary_curve)
    )
    _min_x = min(point[0] for point in _polygon)
    _min_y = min(point[1] for point in _polygon)
    _max_x = max(point[0] for point in _polygon)
    _max_y = max(point[1] for point in _polygon)

    def inside(x, y, _poly=_polygon):
        return earthwork_core.point_in_polygon((x, y), _poly)
else:
    _bounds = terrain.GetBoundingBox(True)
    _min_x, _min_y = float(_bounds.Min.X), float(_bounds.Min.Y)
    _max_x, _max_y = float(_bounds.Max.X), float(_bounds.Max.Y)

columns = max(1, int(math.ceil((_max_x - _min_x) / spacing)))
rows = max(1, int(math.ceil((_max_y - _min_y) / spacing)))
if (columns + 1) * (rows + 1) > 250000:
    raise ValueError(
        "Slope grid would need too many points; use a larger grid_size_m."
    )

# Tolerant gap so cells at the pit rim (the mesh footprint edge) still resolve to
# the nearest mesh point. With a zero gap those slope cells would be skipped and
# the outputs would come back empty.
_raw_sampler = rhino_adapter.mesh_vertical_sampler(
    terrain, max_horizontal_gap=2.0 * spacing
)


def _sampler(x, y):
    try:
        return _raw_sampler(x, y)
    except Exception:
        return None


analysis = earthwork_core.analyze_slopes(
    sampler=_sampler,
    origin=(_min_x, _min_y),
    columns=columns,
    rows=rows,
    spacing=spacing,
    min_steepness=min_steepness,
    hachure_length=hachure_length,
    inside=inside,
)

slope_hachures = rhino_adapter.drape_segments(
    analysis.hachures, _sampler, unit_scale=units_per_meter
)
slope_outline = rhino_adapter.drape_segments(
    analysis.outline, _sampler, unit_scale=units_per_meter, lift=0.06
)
max_slope_1_to = analysis.max_slope_1_to

report_ru = STANDARD.slope_report(
    grid_size_m, columns, rows, analysis.slope_cell_count,
    min_slope_1_to, max_slope_1_to, len(analysis.hachures),
)

bake_status = "Set 'bake' to true to write the pit slopes onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {"hachures": slope_hachures, "outline": slope_outline},
            STANDARD.pit_slope_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) onto {} layer(s).".format(_baked, len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
