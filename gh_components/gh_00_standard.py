"""Grasshopper component: select the active country/standard for all components.

Set this once. The choice is stored in scriptcontext.sticky, so every other
component picks it up via standards.get_standard() with no extra wiring. Recompute
the downstream components after changing it.
"""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("standard_code", "string", "item", True, ("RU", "INT")),
)

COMPONENT_OUTPUTS = (
    ("active_code", "string", "item"),
    ("active_name", "string", "item"),
    ("available", "string", "list"),
    ("provenance", "string", "item"),
    ("status", "string", "item"),
)


import os
try:
    PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    PROJECT_FOLDER = globals().get("PROJECT_FOLDER", "")
if PROJECT_FOLDER and PROJECT_FOLDER not in sys.path:
    sys.path.append(PROJECT_FOLDER)

import standards
import version

standards = importlib.reload(standards)
version = importlib.reload(version)


_code_value = globals().get("standard_code")
_code = None if not _code_value else str(getattr(_code_value, "Value", _code_value)).strip()

if _code:
    active = standards.set_active_standard(_code)
else:
    active = standards.get_standard()

active_code = active.code
active_name = active.name
available = ["{} - {}".format(code, name) for code, name in standards.available_standards()]
# Provenance stamp for documentation: tool version + the encoded editions.
provenance = version.provenance(active)

if _code and active.code != _code.upper():
    status = "Unknown code '{}'. Using default {}. Available: {}".format(
        _code, active.code, ", ".join(code for code, _n in standards.available_standards())
    )
else:
    status = "Active standard: {} ({}). Recompute downstream components to apply.\n{}".format(
        active.name, active.code, provenance
    )
