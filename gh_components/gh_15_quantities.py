"""Grasshopper component: combined earth-mass bill of quantities (+ CSV)."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("topsoil_m3", "number", "item", True),
    ("cut_m3", "number", "item", True),
    ("fill_m3", "number", "item", True),
    ("backfill_m3", "number", "item", True),
    ("ditch_m3", "number", "item", True),
    ("file_path", "string", "item", True),
)

COMPONENT_OUTPUTS = (
    ("total_m3", "number", "item"),
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


_items = earthwork_core.bill_of_quantities(
    [
        (STANDARD.bill_label("topsoil"), _number("topsoil_m3")),
        (STANDARD.bill_label("cut"), _number("cut_m3")),
        (STANDARD.bill_label("fill"), _number("fill_m3")),
        (STANDARD.bill_label("backfill"), _number("backfill_m3")),
        (STANDARD.bill_label("ditch"), _number("ditch_m3")),
    ]
)
_table = STANDARD.bill_of_quantities_table(_items)
total_m3 = sum(item.volume_m3 for item in _items)
report_ru = "Ведомость объёмов земляных работ\n" + _table.render_text()

csv_text = "\n".join(
    ",".join(cell for cell in row) for row in [_table.header] + list(_table.rows)
)

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
