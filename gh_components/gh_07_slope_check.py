"""Grasshopper component: temporary-slope assessment aid (SP 45.13330.2017).

This is a working aid and a checklist, not a certification. It compares a
proposed temporary excavation slope against an allowable one and forces a review
when groundwater, edge surcharge or depth over 5 m apply.
"""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("proposed_slope_1_to", "number", "item"),
    ("depth_m", "number", "item"),
    ("soil_class", "number", "item", True, ("1", "2", "3", "4", "5", "6")),
    ("allowable_slope_1_to", "number", "item", True),
    ("groundwater", "boolean", "item", True),
    ("surcharge", "boolean", "item", True),
    ("geotech_confirmed", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("status", "string", "item"),
    ("within_allowable", "boolean", "item"),
    ("governing_allowable_1_to", "number", "item"),
    ("indicative_allowable_1_to", "number", "item"),
    ("soil_name", "string", "item"),
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


_proposed = globals().get("proposed_slope_1_to")
_depth = globals().get("depth_m")
if _proposed is None:
    raise ValueError("Connect the proposed slope as 1:m (e.g. from gh_03 max_slope_1_to).")
if _depth is None:
    raise ValueError("Connect the excavation depth in metres.")

_soil = globals().get("soil_class")
soil_class = None if _soil is None else int(_soil)
_allow = globals().get("allowable_slope_1_to")
allowable_override = None if _allow is None else float(_allow)
groundwater = _as_bool(globals().get("groundwater"))
surcharge = _as_bool(globals().get("surcharge"))
geotech_confirmed = _as_bool(globals().get("geotech_confirmed"))

check = STANDARD.assess_temporary_slope(
    proposed_1_to=float(_proposed),
    depth_m=float(_depth) * STANDARD.input_length_factor,
    soil_class=soil_class,
    allowable_override_1_to=allowable_override,
    groundwater=groundwater,
    surcharge=surcharge,
    geotech_confirmed=geotech_confirmed,
)

status = check.status
within_allowable = check.within_allowable
governing_allowable_1_to = (
    -1.0 if check.governing_allowable_1_to is None else check.governing_allowable_1_to
)
indicative_allowable_1_to = (
    -1.0 if check.indicative_allowable_1_to is None else check.indicative_allowable_1_to
)
soil_name = check.soil_name

report_ru = STANDARD.slope_check_report(check, groundwater, surcharge, geotech_confirmed)
