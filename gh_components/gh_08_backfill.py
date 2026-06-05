"""Grasshopper component: foundation bedding, backfill and compaction schedule."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("structure_boundary", "curve", "item"),
    ("depth_m", "number", "item"),
    ("working_space_m", "number", "item", True),
    ("bedding_thickness_m", "number", "item", True),
    ("lift_thickness_m", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("excavation_boundary", "curve", "item"),
    ("bedding_volume_m3", "number", "item"),
    ("backfill_volume_m3", "number", "item"),
    ("layer_count", "number", "item"),
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


structure_boundary = rhino_adapter.coerce_curve(globals().get("structure_boundary"))
if structure_boundary is None:
    raise ValueError(
        "Connect a closed structure/foundation footprint curve. "
        + rhino_adapter.input_diagnostic(
            globals(), "structure_boundary", globals().get("structure_boundary"),
            "a closed planar curve",
        )
    )
if globals().get("depth_m") is None:
    raise ValueError("Connect the backfill depth in metres (pit bottom to grade).")

units_info = rhino_adapter.document_unit_info()  # read model units before volumes
units_per_meter = units_info.units_per_meter
meters_per_unit = units_info.meters_per_unit

depth_m = float(globals().get("depth_m")) * STANDARD.input_length_factor
_ws = globals().get("working_space_m")
working_space_m = STANDARD.working_space_default if _ws is None else float(_ws) * STANDARD.input_length_factor
_bed = globals().get("bedding_thickness_m")
bedding_thickness_m = STANDARD.bedding_thickness_default if _bed is None else float(_bed) * STANDARD.input_length_factor
_lift = globals().get("lift_thickness_m")
lift_thickness_m = STANDARD.lift_thickness_default if _lift is None else float(_lift) * STANDARD.input_length_factor

_polygon = earthwork_core.normalize_polygon(
    rhino_adapter.curve_polygon_xy(structure_boundary)
)
structure_area_m2 = abs(earthwork_core.polygon_area(_polygon)) * meters_per_unit * meters_per_unit
perimeter_m = earthwork_core.polygon_perimeter(_polygon) * meters_per_unit

estimate = earthwork_core.estimate_backfill(
    structure_area_m2=structure_area_m2,
    perimeter_m=perimeter_m,
    working_space_m=working_space_m,
    depth_m=depth_m,
    bedding_thickness_m=bedding_thickness_m,
    lift_thickness_m=lift_thickness_m,
)

excavation_boundary = rhino_adapter.offset_curve_outward(
    structure_boundary, working_space_m * units_per_meter
)
bedding_volume_m3 = estimate.bedding_volume_m3
backfill_volume_m3 = estimate.backfill_volume_m3
layer_count = len(estimate.layers)
report_ru = STANDARD.backfill_report(
    estimate, working_space_m, depth_m, bedding_thickness_m
)
if not units_info.reliable:
    report_ru = rhino_adapter.units_status_line(units_info, STANDARD.volume_label) + "\n" + report_ru

bake_status = "Set 'bake' to true to write the working-space outlines onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {
                "excavation": [excavation_boundary] if excavation_boundary else [],
                "structure": [structure_boundary],
            },
            STANDARD.working_space_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) onto {} layer(s).".format(_baked, len(_layers))
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
