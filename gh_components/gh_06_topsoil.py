"""Grasshopper component: topsoil-removal plan and volume statement."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("boundary", "curve", "item"),
    ("existing_mesh", "mesh", "item", True),
    ("strip_depth_m", "number", "item", True),
    ("hatch_spacing_m", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("strip_boundary", "curve", "item"),
    ("hatch_lines", "curve", "list"),
    ("label", "generic", "item"),
    ("area_m2", "number", "item"),
    ("volume_m3", "number", "item"),
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


strip_boundary = rhino_adapter.coerce_curve(globals().get("boundary"))
if strip_boundary is None:
    raise ValueError(
        "Connect a closed stripping-area boundary curve. "
        + rhino_adapter.input_diagnostic(
            globals(), "boundary", globals().get("boundary"), "a closed planar curve"
        )
    )
existing = rhino_adapter.coerce_mesh(globals().get("existing_mesh"))

units_info = rhino_adapter.document_unit_info()  # read model units before volumes
units_per_meter = units_info.units_per_meter
meters_per_unit = units_info.meters_per_unit

_depth = globals().get("strip_depth_m")
strip_depth_m = 0.2 if _depth is None else float(_depth)
_spacing = globals().get("hatch_spacing_m")
hatch_spacing_m = 1.0 if _spacing is None else float(_spacing)

_polygon = earthwork_core.normalize_polygon(
    rhino_adapter.curve_polygon_xy(strip_boundary)
)
strip = earthwork_core.topsoil_strip(_polygon, strip_depth_m, units_per_meter)
area_m2 = strip.area_m2
volume_m3 = strip.volume_m3

_segments = earthwork_core.hatch_polygon(
    _polygon, hatch_spacing_m * units_per_meter, angle_deg=45.0
)


def _flat_sampler(_x, _y):
    return 0.0


if existing is not None:
    _raw = rhino_adapter.mesh_vertical_sampler(
        existing, max_horizontal_gap=float(existing.GetBoundingBox(True).Diagonal.Length)
    )

    def _sampler(x, y):
        try:
            return _raw(x, y)
        except Exception:
            return None
else:
    _sampler = _flat_sampler

hatch_lines = rhino_adapter.drape_segments(
    _segments, _sampler, unit_scale=units_per_meter, lift=0.02
)

# Label at the polygon centroid.
_cx = sum(point[0] for point in _polygon) / len(_polygon)
_cy = sum(point[1] for point in _polygon) / len(_polygon)
_cz = _sampler(_cx, _cy)
if _cz is None:
    _cz = 0.0
import Rhino.Geometry as _rg

label = rhino_adapter.text_tag(
    STANDARD.topsoil_label(strip_depth_m, area_m2, volume_m3),
    _rg.Point3d(_cx, _cy, _cz + 0.05 * units_per_meter),
    0.5 * units_per_meter,
)

report_ru = STANDARD.topsoil_report(strip_depth_m, area_m2, volume_m3)
if not units_info.reliable:
    report_ru = rhino_adapter.units_status_line(units_info, STANDARD.volume_label) + "\n" + report_ru

bake_status = "Set 'bake' to true to write the topsoil plan onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {
                "boundary": [strip_boundary],
                "hatch": hatch_lines,
                "label": [label],
            },
            STANDARD.topsoil_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) onto {} layer(s).".format(_baked, len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
