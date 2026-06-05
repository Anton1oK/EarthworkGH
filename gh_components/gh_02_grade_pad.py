"""Grasshopper component: edit a terrain mesh with a flat grading pad."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("terrain_mesh", "mesh", "item"),
    ("pad_boundary", "curve", "item"),
    ("pad_elevation_m", "number", "item"),
    ("slope_ratio", "number", "item", True),
    ("resolution_m", "number", "item", True),
)

COMPONENT_OUTPUTS = (
    ("proposed_mesh", "mesh", "item"),
    ("edited_vertex_count", "number", "item"),
    ("report_ru", "string", "item"),
    ("warnings", "string", "list"),
)


import os
try:
    PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    PROJECT_FOLDER = globals().get("PROJECT_FOLDER", "")
if PROJECT_FOLDER and PROJECT_FOLDER not in sys.path:
    sys.path.append(PROJECT_FOLDER)

import rhino_adapter
import standards

rhino_adapter = importlib.reload(rhino_adapter)
standards = importlib.reload(standards)
STANDARD = standards.get_standard()

_raw_terrain = globals().get("terrain_mesh")
_raw_boundary = globals().get("pad_boundary")
terrain = rhino_adapter.coerce_mesh(_raw_terrain)
boundary = rhino_adapter.coerce_curve(_raw_boundary)
if terrain is None:
    raise ValueError(
        "Connect a 2.5D terrain mesh. "
        + rhino_adapter.input_diagnostic(
            globals(), "terrain_mesh", _raw_terrain, "a 2.5D terrain mesh"
        )
    )
if boundary is None:
    raise ValueError(
        "Connect a closed grading-pad boundary curve. "
        + rhino_adapter.input_diagnostic(
            globals(), "pad_boundary", _raw_boundary, "a closed planar curve"
        )
    )
if globals().get("pad_elevation_m") is None:
    raise ValueError(
        "Connect the proposed pad elevation. "
        + rhino_adapter.input_diagnostic(
            globals(), "pad_elevation_m", globals().get("pad_elevation_m"), "a number (metres)"
        )
    )

_ratio = globals().get("slope_ratio")
ratio = 1.5 if _ratio is None else float(_ratio)
_resolution = globals().get("resolution_m")
resolution_m = (0.5 if _resolution is None else float(_resolution)) * STANDARD.input_length_factor
pad_elevation_m = float(pad_elevation_m) * STANDARD.input_length_factor

# The mesh is in document units (e.g. millimetres); the pad elevation and grid
# resolution are given in metres, so convert them to document units. The slope
# ratio is dimensionless, so the transition band stays consistent. The pad is
# rebuilt on a regular grid, so the result does not depend on the irregular
# topology of the source mesh.
units_per_meter = rhino_adapter.document_units_per_meter()
pad_elevation_units = float(pad_elevation_m) * units_per_meter
resolution_units = resolution_m * units_per_meter
proposed_mesh, edited_vertex_count = rhino_adapter.grade_pad_mesh(
    terrain,
    boundary,
    pad_elevation_units,
    ratio,
    resolution_units,
)
report_ru, warnings = STANDARD.grade_pad_report(
    float(pad_elevation_m), ratio, resolution_m, edited_vertex_count
)

