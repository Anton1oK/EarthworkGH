"""Grasshopper component: profile section through existing/proposed meshes."""

from __future__ import annotations

import importlib
import sys


COMPONENT_INPUTS = (
    ("existing_mesh", "mesh", "item"),
    ("proposed_mesh", "mesh", "item", True),
    ("section_line", "curve", "item"),
    ("divisions", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("existing_profile", "curve", "item"),
    ("proposed_profile", "curve", "item"),
    ("cut_regions", "curve", "list"),
    ("fill_regions", "curve", "list"),
    ("cut_area_m2", "number", "item"),
    ("fill_area_m2", "number", "item"),
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
section_curve = rhino_adapter.coerce_curve(globals().get("section_line"))
proposed = rhino_adapter.coerce_mesh(globals().get("proposed_mesh"))
if existing is None:
    raise ValueError(
        "Connect the existing terrain mesh. "
        + rhino_adapter.input_diagnostic(
            globals(), "existing_mesh", globals().get("existing_mesh"), "a mesh"
        )
    )
if section_curve is None:
    raise ValueError(
        "Connect a section line. "
        + rhino_adapter.input_diagnostic(
            globals(), "section_line", globals().get("section_line"), "a curve"
        )
    )

units_per_meter = rhino_adapter.document_units_per_meter()
meters_per_unit = 1.0 / units_per_meter

_divisions = globals().get("divisions")
divisions = 50 if _divisions is None else max(2, int(_divisions))


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


stations = rhino_adapter.section_stations(
    section_curve, _safe(existing), _safe(proposed), divisions
)
if len(stations) < 2:
    raise ValueError("The section line does not cross the existing mesh.")

section = earthwork_core.build_section(
    [(distance, existing_z, proposed_z) for distance, _x, _y, existing_z, proposed_z in stations]
)
station_xy = [(distance, x, y) for distance, x, y, _ez, _pz in stations]

existing_profile, proposed_profile, cut_regions, fill_regions = (
    rhino_adapter.section_geometry(section, station_xy, unit_scale=units_per_meter)
)

cut_area_m2 = section.cut_area * meters_per_unit * meters_per_unit
fill_area_m2 = section.fill_area * meters_per_unit * meters_per_unit

report_ru = STANDARD.section_report(
    section.length * meters_per_unit, len(stations),
    cut_area_m2, fill_area_m2, proposed is not None,
)

bake_status = "Set 'bake' to true to write the section onto layers."
if _as_bool(globals().get("bake")):
    try:
        _baked, _layers = rhino_adapter.bake_group(
            {
                "existing": [existing_profile] if existing_profile else [],
                "proposed": [proposed_profile] if proposed_profile else [],
                "cut": cut_regions,
                "fill": fill_regions,
            },
            STANDARD.section_layers(),
            replace=True,
        )
        bake_status = "Baked {} section object(s) onto {} layer(s).".format(
            _baked, len(_layers)
        )
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)
