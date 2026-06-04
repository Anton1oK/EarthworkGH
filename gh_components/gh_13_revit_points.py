"""Grasshopper component: export terrain points (CSV) for a Revit toposurface.

Revit imports a comma-delimited X,Y,Z file as a Toposurface (Create from Import
-> Specify Points File) or a Toposolid. Points are written in metres; pick
"Meters" as the units in Revit's import dialog.
"""

from __future__ import annotations

import importlib
import math
import sys


COMPONENT_INPUTS = (
    ("terrain_mesh", "mesh", "item"),
    ("boundary", "curve", "item", True),
    ("grid_size_m", "number", "item", True),
    ("file_path", "string", "item", True),
    ("recenter", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("csv_text", "string", "item"),
    ("point_count", "number", "item"),
    ("origin_offset", "string", "item"),
    ("status", "string", "item"),
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

earthwork_core = importlib.reload(earthwork_core)
rhino_adapter = importlib.reload(rhino_adapter)


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

units_per_meter = rhino_adapter.document_units_per_meter()
meters_per_unit = 1.0 / units_per_meter

_grid = globals().get("grid_size_m")
grid_size_m = 2.0 if _grid is None else float(_grid)
recenter = _as_bool(globals().get("recenter"))
_path_value = globals().get("file_path")
file_path = None if not _path_value else str(getattr(_path_value, "Value", _path_value))

inside = None
if boundary_curve is not None:
    _polygon = earthwork_core.normalize_polygon(
        rhino_adapter.curve_polygon_xy(boundary_curve)
    )

    def inside(x, y, _poly=_polygon):
        return earthwork_core.point_in_polygon((x, y), _poly)

# Document-unit (x, y, z) points: a regular grid resample, or the mesh vertices.
_points_units = []
if grid_size_m > 0.0:
    spacing = grid_size_m * units_per_meter
    if boundary_curve is not None:
        min_x = min(p[0] for p in _polygon)
        min_y = min(p[1] for p in _polygon)
        max_x = max(p[0] for p in _polygon)
        max_y = max(p[1] for p in _polygon)
    else:
        bounds = terrain.GetBoundingBox(True)
        min_x, min_y = float(bounds.Min.X), float(bounds.Min.Y)
        max_x, max_y = float(bounds.Max.X), float(bounds.Max.Y)
    columns = max(1, int(math.ceil((max_x - min_x) / spacing)))
    rows = max(1, int(math.ceil((max_y - min_y) / spacing)))
    if (columns + 1) * (rows + 1) > 200000:
        raise ValueError(
            "Grid needs {} points - too many to ray-sample; use a larger "
            "grid_size_m.".format((columns + 1) * (rows + 1))
        )
    _raw = rhino_adapter.mesh_vertical_sampler(terrain, max_horizontal_gap=2.0 * spacing)
    for j in range(rows + 1):
        for i in range(columns + 1):
            x = min_x + i * spacing
            y = min_y + j * spacing
            if inside is not None and not inside(x, y):
                continue
            try:
                z = _raw(x, y)
            except Exception:
                z = None
            if z is not None:
                _points_units.append((x, y, z))
else:
    vertices = terrain.Vertices
    for index in range(vertices.Count):
        vertex = vertices[index]
        x, y, z = float(vertex.X), float(vertex.Y), float(vertex.Z)
        if inside is not None and not inside(x, y):
            continue
        _points_units.append((x, y, z))

# Convert to metres for Revit.
_points = [(x * meters_per_unit, y * meters_per_unit, z * meters_per_unit)
           for x, y, z in _points_units]

origin_offset = "0.000, 0.000"
if recenter and _points:
    off_x = min(p[0] for p in _points)
    off_y = min(p[1] for p in _points)
    _points = [(x - off_x, y - off_y, z) for x, y, z in _points]
    origin_offset = "{:.3f}, {:.3f}".format(off_x, off_y)

csv_text = earthwork_core.points_to_csv(_points, delimiter=",", decimals=3)
point_count = len(_points)

if not _points:
    status = "No points exported - check the mesh and boundary."
elif file_path:
    try:
        with open(file_path, "w", encoding="utf-8", newline="\n") as _file:
            _file.write(csv_text)
        status = "Wrote {} points (metres) to {}".format(point_count, file_path)
    except Exception as _write_error:  # pragma: no cover - IO path
        status = "Write failed: {}".format(_write_error)
else:
    status = (
        "{} points (metres) ready. Set file_path to write a CSV, then in Revit: "
        "Toposurface -> Create from Import -> Specify Points File (units: Meters)."
    ).format(point_count)
