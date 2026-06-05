"""Grasshopper component: SPDS-style earth-mass cartogram."""

from __future__ import annotations

import importlib
import os
import sys


COMPONENT_INPUTS = (
    ("boundary", "curve", "item"),
    ("existing_mesh", "mesh", "item"),
    ("proposed_mesh", "mesh", "item"),
    ("grid_size_m", "number", "item", True),
    ("samples_per_side", "number", "item", True),
    ("flat_tolerance_m", "number", "item", True),
    ("bake", "boolean", "item", True),
)

COMPONENT_OUTPUTS = (
    ("analysis_mesh", "mesh", "item"),
    ("grid_curves", "curve", "list"),
    ("zero_work_lines", "curve", "list"),
    ("cut_hatches", "curve", "list"),
    ("cell_volume_tags", "generic", "list"),
    ("vertex_mark_tags", "generic", "list"),
    ("column_totals", "generic", "list"),
    ("fill_m3", "number", "item"),
    ("cut_m3", "number", "item"),
    ("balance_m3", "number", "item"),
    ("report_ru", "string", "item"),
    ("warnings", "string", "list"),
    ("table_ru", "string", "item"),
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

_raw_boundary = globals().get("boundary")
_raw_existing = globals().get("existing_mesh")
_raw_proposed = globals().get("proposed_mesh")
boundary_curve = rhino_adapter.coerce_curve(_raw_boundary)
existing = rhino_adapter.coerce_mesh(_raw_existing)
proposed = rhino_adapter.coerce_mesh(_raw_proposed)
if boundary_curve is None:
    raise ValueError(
        "Connect a closed site boundary curve. "
        + rhino_adapter.input_diagnostic(
            globals(), "boundary", _raw_boundary, "a closed planar curve"
        )
    )
if existing is None:
    raise ValueError(
        "Connect the existing terrain mesh. "
        + rhino_adapter.input_diagnostic(
            globals(), "existing_mesh", _raw_existing, "a 2.5D terrain mesh"
        )
    )
if proposed is None:
    raise ValueError(
        "Connect the proposed terrain mesh. "
        + rhino_adapter.input_diagnostic(
            globals(), "proposed_mesh", _raw_proposed, "a 2.5D terrain mesh"
        )
    )

_grid = globals().get("grid_size_m")
_samples = globals().get("samples_per_side")
_flat = globals().get("flat_tolerance_m")
grid_size = 20.0 if _grid is None else float(_grid)
sample_count = 6 if _samples is None else int(_samples)
# Height differences (in metres) below this read as flat, not cut/fill. Raise it
# if sampling noise between two near-identical meshes still paints flat ground.
flat_tolerance = 0.005 if _flat is None else float(_flat)

# Read the model units up front so the cut/fill volumes are correct whatever the
# document unit is (mm, cm, m, inch...). Geometry stays in document units; the
# grid is specified in metres and volumes are reported in cubic metres.
units_info = rhino_adapter.document_unit_info()
units_per_meter = units_info.units_per_meter
meters_per_unit = units_info.meters_per_unit

# Tolerate grid corners that snap up to ~1.5 cells past the mesh edge (in
# document units); a larger gap is reported as a mesh/boundary misalignment.
_edge_gap = 1.5 * grid_size * units_per_meter
existing_sampler = rhino_adapter.mesh_vertical_sampler(
    existing, max_horizontal_gap=_edge_gap, meters_per_unit=meters_per_unit
)
proposed_sampler = rhino_adapter.mesh_vertical_sampler(
    proposed, max_horizontal_gap=_edge_gap, meters_per_unit=meters_per_unit
)

result = earthwork_core.calculate_cut_fill(
    boundary=rhino_adapter.curve_polygon_xy(boundary_curve),
    existing_z=existing_sampler,
    proposed_z=proposed_sampler,
    grid_size_m=grid_size,
    samples_per_side=sample_count,
    units_per_meter=units_per_meter,
    flat_tolerance_m=flat_tolerance,
)

(
    analysis_mesh,
    grid_curves,
    zero_work_lines,
    cut_hatches,
    cell_volume_tags,
    vertex_mark_tags,
) = rhino_adapter.cartogram_geometry(
    result, proposed_sampler, meters_per_unit=meters_per_unit,
    volume_label=STANDARD.volume_label, volume_factor=STANDARD.volume_factor,
)

column_totals = list(result.column_totals)
fill_m3 = result.fill_m3
cut_m3 = result.cut_m3
balance_m3 = result.balance_m3
report_ru = STANDARD.cartogram_report(result)
warnings = list(STANDARD.cartogram_warnings(grid_size))
# Surface an unreadable/unitless model loudly - the volumes would be wrong.
if not units_info.reliable:
    warnings.insert(0, rhino_adapter.units_status_line(units_info, STANDARD.volume_label))

# Earth-mass quantity table (per-column fill/cut/balance + totals), per standard.
_table = STANDARD.earth_mass_table(result)
table_ru = _table.render_text()


def _as_bool(value):
    if value is None:
        return False
    return bool(getattr(value, "Value", value))


def _table_origin():
    """Top-left placement for the table, just right of the cartogram extent."""
    corners = [vertex for cell in result.cells for vertex in cell.corners]
    if not corners:
        return (0.0, 0.0, 0.0)
    max_x = max(vertex.x for vertex in corners)
    max_y = max(vertex.y for vertex in corners)
    top_z = max(vertex.proposed_z for vertex in corners)
    return (max_x + 0.5 * grid_size * units_per_meter, max_y, top_z)


# Bake the in-memory geometry straight onto SPDS drawing layers when requested.
# Doing it here avoids round-tripping lists through script inputs, which some
# Rhino builds will not give list access.
bake_status = "Set 'bake' to true to write the cartogram onto drawing layers."
if _as_bool(globals().get("bake")):
    try:
        _table_height = 0.4 * units_per_meter
        _table_lines, _table_tags = rhino_adapter.cartogram_table_geometry(
            _table, _table_origin(), _table_height, unit_scale=units_per_meter
        )
        _baked_count, _baked_layers = rhino_adapter.bake_group(
            {
                "boundary": [boundary_curve],
                "grid_curves": grid_curves,
                "zero_work_lines": zero_work_lines,
                "cut_hatches": cut_hatches,
                "vertex_mark_tags": vertex_mark_tags,
                "cell_volume_tags": cell_volume_tags,
                "table": list(_table_lines) + list(_table_tags),
                "analysis_mesh": [analysis_mesh],
            },
            STANDARD.cartogram_layers(),
            replace=True,
        )
        bake_status = "Baked {} object(s) onto {} layer(s). Re-bake to refresh.".format(
            _baked_count, len(_baked_layers)
        )
    except Exception as _bake_error:  # pragma: no cover - Rhino-only path
        bake_status = "Bake failed: {}".format(_bake_error)

