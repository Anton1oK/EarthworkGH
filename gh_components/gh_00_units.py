"""Grasshopper component: read and verify the Rhino model units.

Drop this on the canvas and check it before running the earthwork components.
It reports the active document's length unit and the conversion the tools use,
so you can confirm calculations are based on the right unit (mm vs m vs inch).
It does no calculation and changes nothing - it only reads the document.

This is document-level, not country-specific: the standards (gh_00_standard)
stay a separate concern.
"""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = ()

COMPONENT_OUTPUTS = (
    ("unit_system", "string", "item"),
    ("units_per_meter", "number", "item"),
    ("meters_per_unit", "number", "item"),
    ("reliable", "boolean", "item"),
    ("status", "string", "item"),
)


import os
try:
    PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    PROJECT_FOLDER = globals().get("PROJECT_FOLDER", "")
if PROJECT_FOLDER and PROJECT_FOLDER not in sys.path:
    sys.path.append(PROJECT_FOLDER)

import rhino_adapter

rhino_adapter = importlib.reload(rhino_adapter)


info = rhino_adapter.document_unit_info()

unit_system = info.name
units_per_meter = info.units_per_meter
meters_per_unit = info.meters_per_unit
reliable = info.reliable

if reliable:
    status = (
        "{}\nExample: a 20 m analysis grid = {:g} {} in the model; "
        "1 model unit = {:g} m.".format(
            rhino_adapter.units_status_line(info),
            20.0 * units_per_meter, info.label, meters_per_unit,
        )
    )
else:
    status = rhino_adapter.units_status_line(info)
