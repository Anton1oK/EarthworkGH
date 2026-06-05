"""Grasshopper component: serial cross-sections and average-end-area volumes."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("existing_mesh", "mesh", "item"),
    ("proposed_mesh", "mesh", "item", True),
    ("baseline", "curve", "item"),
    ("spacing_m", "number", "item", True),
    ("half_width_m", "number", "item", True),
    ("divisions", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("section_lines", "curve", "list"),
    ("existing_profiles", "curve", "list"),
    ("proposed_profiles", "curve", "list"),
    ("cut_volume_m3", "number", "item"),
    ("fill_volume_m3", "number", "item"),
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


existing = rhino_adapter.coerce_mesh(globals().get("existing_mesh"))
baseline = rhino_adapter.coerce_curve(globals().get("baseline"))
proposed = rhino_adapter.coerce_mesh(globals().get("proposed_mesh"))
if existing is None:
    raise ValueError(
        "Connect the existing terrain mesh. "
        + rhino_adapter.input_diagnostic(
            globals(), "existing_mesh", globals().get("existing_mesh"), "a mesh"
        )
    )
if baseline is None:
    raise ValueError(
        "Connect a baseline curve for the sections. "
        + rhino_adapter.input_diagnostic(
            globals(), "baseline", globals().get("baseline"), "a curve"
        )
    )

units_per_meter = rhino_adapter.document_units_per_meter()
meters_per_unit = 1.0 / units_per_meter

_spacing = globals().get("spacing_m")
spacing_m = (5.0 if _spacing is None else float(_spacing)) * STANDARD.input_length_factor
_half = globals().get("half_width_m")
half_width_m = (10.0 if _half is None else float(_half)) * STANDARD.input_length_factor
_divisions = globals().get("divisions")
divisions = 30 if _divisions is None else max(2, int(_divisions))


def _safe(mesh):
    if mesh is None:
        return None
    raw = rhino_adapter.mesh_vertical_sampler(
        mesh, max_horizontal_gap=float(mesh.GetBoundingBox(True).Diagonal.Length)
    )

    def sample(x, y):
        try:
            return raw(x, y)
        except Exception:
            return None

    return sample


_existing_sampler = _safe(existing)
_proposed_sampler = _safe(proposed)

_lines = rhino_adapter.section_lines_along(
    baseline, spacing_m * units_per_meter, half_width_m * units_per_meter
)

section_lines = []
existing_profiles = []
proposed_profiles = []
_area_stations = []
for _distance_units, _line in _lines:
    _stations = rhino_adapter.section_stations(
        _line, _existing_sampler, _proposed_sampler, divisions
    )
    if len(_stations) < 2:
        continue
    _section = earthwork_core.build_section(
        [(d, ez, pz) for d, _x, _y, ez, pz in _stations]
    )
    _existing_curve, _proposed_curve, _cut, _fill = rhino_adapter.section_geometry(
        _section, [(d, x, y) for d, x, y, _ez, _pz in _stations], unit_scale=units_per_meter
    )
    section_lines.append(_line)
    if _existing_curve is not None:
        existing_profiles.append(_existing_curve)
    if _proposed_curve is not None:
        proposed_profiles.append(_proposed_curve)
    _area_stations.append(
        (
            _distance_units * meters_per_unit,
            _section.cut_area * meters_per_unit * meters_per_unit,
            _section.fill_area * meters_per_unit * meters_per_unit,
        )
    )

if _area_stations:
    _result = earthwork_core.serial_section_volumes(_area_stations)
    cut_volume_m3 = _result.cut_volume
    fill_volume_m3 = _result.fill_volume
    report_ru = STANDARD.serial_section_report(_result, spacing_m)
else:
    cut_volume_m3 = 0.0
    fill_volume_m3 = 0.0
    report_ru = STANDARD.serial_section_empty_report()

bake_status = "Set 'bake' to true to write the sections onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {
                "lines": section_lines,
                "existing": existing_profiles,
                "proposed": proposed_profiles,
            },
            STANDARD.serial_section_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) across {} section(s).".format(
            _baked, len(section_lines)
        )
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
