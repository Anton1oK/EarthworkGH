"""Grasshopper component: frost-depth foundation check (SP 22.13330.2016).

A working aid and a checklist, not a certification. Compares the foundation base
depth against the design freezing depth on frost-heaving soil.
"""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("base_depth_m", "number", "item"),
    ("frost_depth_m", "number", "item", True),
    ("soil_class", "number", "item", True, ("1", "2", "3", "4", "5", "6")),
    ("freezing_index", "number", "item", True),
    ("thermal_factor", "number", "item", True),
    ("heaving", "boolean", "item", True),
    ("groundwater", "boolean", "item", True),
    ("geotech_confirmed", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("adequate", "boolean", "item"),
    ("design_frost_depth_m", "number", "item"),
    ("status", "string", "item"),
    ("report_ru", "string", "item"),
)


import os
try:
    PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    PROJECT_FOLDER = globals().get("PROJECT_FOLDER", "")
if PROJECT_FOLDER and PROJECT_FOLDER not in sys.path:
    sys.path.append(PROJECT_FOLDER)

import standards

standards = importlib.reload(standards)
STANDARD = standards.get_standard()


def _as_bool(value):
    if value is None:
        return False
    return bool(getattr(value, "Value", value))


if globals().get("base_depth_m") is None:
    raise ValueError("Connect the foundation base depth below grade in metres.")
base_depth_m = float(globals().get("base_depth_m")) * STANDARD.input_length_factor

_fd = globals().get("frost_depth_m")
frost_depth_m = None if _fd is None else float(_fd) * STANDARD.input_length_factor
_soil = globals().get("soil_class")
soil_class = None if _soil is None else int(_soil)
_mt = globals().get("freezing_index")
freezing_index = None if _mt is None else float(_mt)
_kh = globals().get("thermal_factor")
thermal_factor = 1.1 if _kh is None else float(_kh)
_heaving = globals().get("heaving")
heaving = True if _heaving is None else _as_bool(_heaving)
groundwater = _as_bool(globals().get("groundwater"))
geotech_confirmed = _as_bool(globals().get("geotech_confirmed"))

check = STANDARD.assess_foundation_frost(
    base_depth_m=base_depth_m,
    frost_depth_m=frost_depth_m,
    soil_class=soil_class,
    freezing_index=freezing_index,
    thermal_factor=thermal_factor,
    heaving=heaving,
    groundwater=groundwater,
    geotech_confirmed=geotech_confirmed,
)

adequate = check.adequate
design_frost_depth_m = -1.0 if check.frost_depth_m is None else check.frost_depth_m
status = check.status
report_ru = STANDARD.foundation_check_report(check, heaving, groundwater, geotech_confirmed)
