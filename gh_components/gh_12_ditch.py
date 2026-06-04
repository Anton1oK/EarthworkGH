"""Grasshopper component: ditch / swale along a centreline with invert marks."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("centerline", "curve", "item"),
    ("existing_mesh", "mesh", "item"),
    ("depth_m", "number", "item", True),
    ("start_invert_m", "number", "item", True),
    ("longitudinal_slope_percent", "number", "item", True),
    ("bottom_width_m", "number", "item", True),
    ("side_slope", "number", "item", True),
    ("divisions", "number", "item", True),
    ("mark_every", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("invert_curve", "curve", "item"),
    ("top_edges", "curve", "list"),
    ("invert_marks", "generic", "list"),
    ("excavation_volume_m3", "number", "item"),
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
existing = rhino_adapter.coerce_mesh(globals().get("existing_mesh"))
if centerline is None:
    raise ValueError(
        "Connect a ditch centreline curve. "
        + rhino_adapter.input_diagnostic(
            globals(), "centerline", globals().get("centerline"), "a curve"
        )
    )
if existing is None:
    raise ValueError(
        "Connect the existing terrain mesh. "
        + rhino_adapter.input_diagnostic(
            globals(), "existing_mesh", globals().get("existing_mesh"), "a mesh"
        )
    )

units_info = rhino_adapter.document_unit_info()  # read model units before volumes
units_per_meter = units_info.units_per_meter
meters_per_unit = units_info.meters_per_unit


def _number(name, default):
    value = globals().get(name)
    return default if value is None else float(value)


depth_m = _number("depth_m", 0.5)
_start = globals().get("start_invert_m")
bottom_width_m = _number("bottom_width_m", 0.4)
side_slope = _number("side_slope", 1.5)
slope_percent = _number("longitudinal_slope_percent", 0.0)
divisions = max(2, int(_number("divisions", 30)))
mark_every = max(1, int(_number("mark_every", 5)))

_raw = rhino_adapter.mesh_vertical_sampler(
    existing, max_horizontal_gap=float(existing.GetBoundingBox(True).Diagonal.Length)
)


def _ground(x, y):
    try:
        return _raw(x, y)
    except Exception:
        return None


_stations = rhino_adapter.section_stations(centerline, _ground, None, divisions)
if len(_stations) < 2:
    raise ValueError("The centreline does not cross the existing mesh.")

ground_stations = [(d, gz) for d, _x, _y, gz, _pz in _stations]
station_xy = [(d, x, y) for d, x, y, _gz, _pz in _stations]

profile = earthwork_core.ditch_profile(
    ground_stations,
    depth=depth_m * units_per_meter,
    start_invert=None if _start is None else float(_start) * units_per_meter,
    longitudinal_slope=slope_percent / 100.0,
)
excavation_volume_m3 = (
    earthwork_core.ditch_volume(profile, bottom_width_m * units_per_meter, side_slope)
    * meters_per_unit
    * meters_per_unit
    * meters_per_unit
)

invert_curve = rhino_adapter.ditch_invert_curve(
    profile, station_xy, unit_scale=units_per_meter
)
invert_marks = rhino_adapter.ditch_invert_marks(
    profile, station_xy, STANDARD.ditch_invert_label, meters_per_unit,
    0.4 * units_per_meter, unit_scale=units_per_meter, every=mark_every,
)
# Top edges sit half the bottom width plus the slope run at the deepest section.
_top_half_width_units = (
    0.5 * bottom_width_m + side_slope * profile.max_depth * meters_per_unit
) * units_per_meter
_left, _right = rhino_adapter.offset_curve_both(centerline, _top_half_width_units)
top_edges = [edge for edge in (_left, _right) if edge is not None]

report_ru = STANDARD.ditch_report(
    profile, bottom_width_m, side_slope, excavation_volume_m3, meters_per_unit
)
if not units_info.reliable:
    report_ru = rhino_adapter.units_status_line(units_info, STANDARD.volume_label) + "\n" + report_ru

bake_status = "Set 'bake' to true to write the ditch onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {
                "invert": [invert_curve] if invert_curve else [],
                "edges": top_edges,
                "marks": invert_marks,
            },
            STANDARD.ditch_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) onto {} layer(s).".format(_baked, len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
