"""Grasshopper component: site area balance (ТЭП - technical-economic indices)."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("plot_boundary", "curve", "item"),
    ("building_area_m2", "number", "item", True),
    ("paving_area_m2", "number", "item", True),
    ("other_area_m2", "number", "item", True),
)

COMPONENT_OUTPUTS = (
    ("plot_area_m2", "number", "item"),
    ("building_percent", "number", "item"),
    ("green_area_m2", "number", "item"),
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
import rhino_adapter
import standards

earthwork_core = importlib.reload(earthwork_core)
rhino_adapter = importlib.reload(rhino_adapter)
standards = importlib.reload(standards)
STANDARD = standards.get_standard()


plot = rhino_adapter.coerce_curve(globals().get("plot_boundary"))
if plot is None:
    raise ValueError(
        "Connect a closed plot boundary curve. "
        + rhino_adapter.input_diagnostic(
            globals(), "plot_boundary", globals().get("plot_boundary"),
            "a closed planar curve",
        )
    )

units_per_meter = rhino_adapter.document_units_per_meter()
meters_per_unit = 1.0 / units_per_meter


def _number(name):
    value = globals().get(name)
    return 0.0 if value is None else float(value)


_polygon = rhino_adapter.curve_polygon_xy(plot)
plot_area_m2 = abs(earthwork_core.polygon_area(_polygon)) * meters_per_unit * meters_per_unit
building_area_m2 = _number("building_area_m2")
paving_area_m2 = _number("paving_area_m2")
other_area_m2 = _number("other_area_m2")

_table = STANDARD.tep_table(
    plot_area_m2,
    [
        ("building", building_area_m2),
        ("paving", paving_area_m2),
        ("other", other_area_m2),
    ],
)
report_ru = STANDARD.tep_report(_table)

building_percent = (building_area_m2 / plot_area_m2 * 100.0) if plot_area_m2 else 0.0
green_area_m2 = plot_area_m2 - building_area_m2 - paving_area_m2 - other_area_m2
