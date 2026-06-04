"""
Example external Grasshopper component.

Inputs:
    value
    scale

Outputs:
    result
    report
"""

from __future__ import annotations


COMPONENT_INPUTS = (
    ("value", "number", "item"),
    ("scale", "number", "item", True),
)

COMPONENT_OUTPUTS = (
    ("result", "number", "item"),
    ("report", "string", "item"),
)


value_in = globals().get("value", 0.0)
scale_in = globals().get("scale", 1.0)

if value_in is None:
    value_in = 0.0
if scale_in is None:
    scale_in = 1.0

result = float(value_in) * float(scale_in)
report = "{} x {} = {}".format(value_in, scale_in, result)
