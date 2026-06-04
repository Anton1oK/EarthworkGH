"""Grasshopper component: earthwork soil balance (bulking, import/export)."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("cut_m3", "number", "item"),
    ("fill_m3", "number", "item"),
    ("soil_class", "number", "item", True, ("1", "2", "3", "4", "5", "6")),
    ("initial_bulking", "number", "item", True),
    ("residual_bulking", "number", "item", True),
)

COMPONENT_OUTPUTS = (
    ("import_m3", "number", "item"),
    ("export_m3", "number", "item"),
    ("cut_loose_m3", "number", "item"),
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
import standards

earthwork_core = importlib.reload(earthwork_core)
standards = importlib.reload(standards)
STANDARD = standards.get_standard()


if globals().get("cut_m3") is None:
    raise ValueError("Connect the cut (excavation) volume in m3 (bank).")
if globals().get("fill_m3") is None:
    raise ValueError("Connect the fill volume in m3 (compacted).")

cut_m3 = float(globals().get("cut_m3"))
fill_m3 = float(globals().get("fill_m3"))
_soil = globals().get("soil_class")
soil_class = None if _soil is None else int(_soil)

_default_kp, _default_kor = STANDARD.bulking_factors(soil_class)
_kp = globals().get("initial_bulking")
initial_bulking = _default_kp if _kp is None else float(_kp)
_kor = globals().get("residual_bulking")
residual_bulking = _default_kor if _kor is None else float(_kor)

balance = earthwork_core.soil_balance(
    cut_m3, fill_m3, initial_bulking=initial_bulking, residual_bulking=residual_bulking
)

import_m3 = balance.import_bank_m3
export_m3 = balance.export_bank_m3
cut_loose_m3 = balance.cut_loose_m3
report_ru = STANDARD.soil_balance_report(
    balance, soil_class, initial_bulking, residual_bulking
)
