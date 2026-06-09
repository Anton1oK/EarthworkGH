"""Grasshopper component: earthwork accounting - bill of quantities + soil
balance (bulking, import/export).

Combines the former gh_14 (soil balance) and gh_15 (bill of quantities). Feed the
volumes you have (topsoil, cut, fill, backfill, ditch); cut + fill also drive the
bulking/import-export balance. Optional CSV export of the bill.
"""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("cut_m3", "number", "item", True),
    ("fill_m3", "number", "item", True),
    ("topsoil_m3", "number", "item", True),
    ("backfill_m3", "number", "item", True),
    ("ditch_m3", "number", "item", True),
    ("soil_class", "number", "item", True, ("1", "2", "3", "4", "5", "6")),
    ("initial_bulking", "number", "item", True),
    ("residual_bulking", "number", "item", True),
    ("file_path", "string", "item", True),
)

COMPONENT_OUTPUTS = (
    ("total_m3", "number", "item"),
    ("import_m3", "number", "item"),
    ("export_m3", "number", "item"),
    ("cut_loose_m3", "number", "item"),
    ("report_ru", "string", "item"),
    ("csv_text", "string", "item"),
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
import standards

earthwork_core = importlib.reload(earthwork_core)
standards = importlib.reload(standards)
STANDARD = standards.get_standard()


def _number(name):
    value = globals().get(name)
    return 0.0 if value is None else float(value)


cut_m3 = _number("cut_m3")
fill_m3 = _number("fill_m3")
topsoil_m3 = _number("topsoil_m3")
backfill_m3 = _number("backfill_m3")
ditch_m3 = _number("ditch_m3")

_soil = globals().get("soil_class")
soil_class = None if _soil is None else int(_soil)
_default_kp, _default_kor = STANDARD.bulking_factors(soil_class)
_kp = globals().get("initial_bulking")
initial_bulking = _default_kp if _kp is None else float(_kp)
_kor = globals().get("residual_bulking")
residual_bulking = _default_kor if _kor is None else float(_kor)

# Bill of quantities (combined earth-mass schedule).
_items = earthwork_core.bill_of_quantities(
    [
        (STANDARD.bill_label("topsoil"), topsoil_m3),
        (STANDARD.bill_label("cut"), cut_m3),
        (STANDARD.bill_label("fill"), fill_m3),
        (STANDARD.bill_label("backfill"), backfill_m3),
        (STANDARD.bill_label("ditch"), ditch_m3),
    ]
)
_table = STANDARD.bill_of_quantities_table(_items)
total_m3 = sum(item.volume_m3 for item in _items)
csv_text = "\n".join(",".join(cell for cell in row) for row in [_table.header] + list(_table.rows))

# Soil balance (bulking / import-export) driven by cut + fill.
balance = earthwork_core.soil_balance(
    cut_m3, fill_m3, initial_bulking=initial_bulking, residual_bulking=residual_bulking
)
import_m3 = balance.import_bank_m3
export_m3 = balance.export_bank_m3
cut_loose_m3 = balance.cut_loose_m3

report_ru = "\n\n".join([
    _table.render_text(),
    STANDARD.soil_balance_report(balance, soil_class, initial_bulking, residual_bulking),
])

_path_value = globals().get("file_path")
file_path = None if not _path_value else str(getattr(_path_value, "Value", _path_value))
if file_path:
    try:
        with open(file_path, "w", encoding="utf-8", newline="\n") as _file:
            _file.write(csv_text)
        status = "Wrote the bill to {}".format(file_path)
    except Exception as _write_error:  # pragma: no cover - IO path
        status = "Write failed: {}".format(_write_error)
else:
    status = "Bill ready ({} item(s)). Set file_path to write a CSV.".format(len(_items))
