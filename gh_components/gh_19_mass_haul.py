"""Grasshopper component: mass-haul / +-0.000 optimiser (balanced platform)."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("existing_mesh", "mesh", "item"),
    ("boundary", "curve", "item", True),
    ("grid_size_m", "number", "item", True),
    ("platform_m", "number", "item", True),
    ("steps", "number", "item", True),
)

COMPONENT_OUTPUTS = (
    ("balanced_elevation_m", "number", "item"),
    ("cut_m3", "number", "item"),
    ("fill_m3", "number", "item"),
    ("net_m3", "number", "item"),
    ("curve_levels_m", "number", "list"),
    ("curve_cut_m3", "number", "list"),
    ("curve_fill_m3", "number", "list"),
    ("report_ru", "string", "item"),
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


existing = rhino_adapter.coerce_mesh(globals().get("existing_mesh"))
if existing is None:
    raise ValueError(
        "Connect the existing terrain mesh. "
        + rhino_adapter.input_diagnostic(
            globals(), "existing_mesh", globals().get("existing_mesh"), "a mesh"
        )
    )
boundary_curve = rhino_adapter.coerce_curve(globals().get("boundary"))

_grid_size = globals().get("grid_size_m")
grid_size_m = 2.0 if _grid_size is None else float(_grid_size)
grid = rhino_adapter.analysis_grid(existing, boundary_curve, grid_size_m)
units_per_meter = grid.units_per_meter
meters_per_unit = grid.meters_per_unit
cubic = meters_per_unit ** 3

# Collect the once-sampled ground elevations inside the area.
_elev = []
for j in range(grid.rows + 1):
    y = grid.origin[1] + j * grid.spacing
    for i in range(grid.columns + 1):
        x = grid.origin[0] + i * grid.spacing
        if grid.inside is not None and not grid.inside(x, y):
            continue
        z = grid.sampler(x, y)
        if z is not None:
            _elev.append(z)
if not _elev:
    raise ValueError("No ground sampled inside the area.")

_cell_area = grid.spacing * grid.spacing
_balanced = earthwork_core.balanced_platform(_elev)
balanced_elevation_m = _balanced * meters_per_unit

_platform = globals().get("platform_m")
platform = _balanced if _platform is None else float(_platform) * units_per_meter
platform_m = platform * meters_per_unit

_cut, _fill = earthwork_core.platform_cut_fill(_elev, _cell_area, platform)
cut_m3 = _cut * cubic
fill_m3 = _fill * cubic
net_m3 = cut_m3 - fill_m3

steps = 12 if globals().get("steps") is None else max(2, int(globals().get("steps")))
_low, _high = min(_elev), max(_elev)
_levels = [_low + (_high - _low) * k / steps for k in range(steps + 1)]
_curve = earthwork_core.mass_haul_curve(_elev, _cell_area, _levels)
curve_levels_m = [level * meters_per_unit for level, _c, _f, _n in _curve]
curve_cut_m3 = [c * cubic for _l, c, _f, _n in _curve]
curve_fill_m3 = [f * cubic for _l, _c, f, _n in _curve]

report_ru = STANDARD.mass_haul_report(balanced_elevation_m, platform_m, cut_m3, fill_m3)
