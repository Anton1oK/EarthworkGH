r"""Manual Rhino-host smoke test for the Grasshopper-facing adapters.

Run from Rhino with (use your own path to this file):
    -_RunPythonScript "<project folder>\tests\rhino_smoke_test.py"
The project folder is auto-detected from this file's location.
"""

from __future__ import annotations

import os
import sys
import traceback


try:
    PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    PROJECT_FOLDER = os.getcwd()
RESULT_PATH = os.path.join(PROJECT_FOLDER, "tests", "rhino_smoke_result.txt")
if PROJECT_FOLDER not in sys.path:
    sys.path.append(PROJECT_FOLDER)


class _ValueWrapper:
    def __init__(self, value):
        self.Value = value


class _ScriptVariableWrapper:
    def __init__(self, value):
        self._value = value

    def ScriptVariable(self):
        return self._value


def _grid_mesh():
    import Rhino.Geometry as rg

    mesh = rg.Mesh()
    for y in (0.0, 10.0, 20.0):
        for x in (0.0, 10.0, 20.0):
            mesh.Vertices.Add(x, y, 0.0)
    for row in range(2):
        for column in range(2):
            a = row * 3 + column
            mesh.Faces.AddFace(a, a + 1, a + 4, a + 3)
    mesh.Normals.ComputeNormals()
    return mesh


def _rectangle_curve(x0, y0, x1, y1):
    import Rhino.Geometry as rg

    return rg.PolylineCurve(
        [
            rg.Point3d(x0, y0, 0.0),
            rg.Point3d(x1, y0, 0.0),
            rg.Point3d(x1, y1, 0.0),
            rg.Point3d(x0, y1, 0.0),
            rg.Point3d(x0, y0, 0.0),
        ]
    )


def _run_component(filename, **inputs):
    path = os.path.join(PROJECT_FOLDER, "gh_components", filename)
    env = dict(inputs)
    env["__file__"] = path
    env["__name__"] = "__rhino_smoke_component__"
    with open(path, "r", encoding="utf-8") as component_file:
        source = component_file.read()
    exec(compile(source, path, "exec"), env)
    return env


def run():
    import earthwork_core
    import rhino_adapter
    import standards

    STANDARD = standards.get_standard()
    mesh = _grid_mesh()
    site = _rectangle_curve(0.0, 0.0, 20.0, 20.0)
    pad = _rectangle_curve(5.0, 5.0, 15.0, 15.0)
    sample = rhino_adapter.mesh_vertical_sampler(mesh)
    assert abs(sample(5.0, 5.0)) <= 1e-9

    assert rhino_adapter.coerce_curve(site) is site
    assert rhino_adapter.coerce_curve(_ValueWrapper(site)) is site
    assert rhino_adapter.coerce_curve(_ScriptVariableWrapper(site)) is site
    assert rhino_adapter.coerce_curve([site]) is site
    assert rhino_adapter.coerce_mesh(_ValueWrapper(mesh)) is mesh

    proposed, edited_count = rhino_adapter.grade_pad_mesh(mesh, pad, 1.0, 2.0, 2.0)
    assert edited_count > 0
    # The pad is resampled onto a regular grid, so it no longer shares the source
    # mesh's vertex count; over a 20 m square at 2 m spacing that is an 11x11 grid.
    assert proposed.Vertices.Count == 121

    result = earthwork_core.calculate_cut_fill(
        boundary=rhino_adapter.curve_polygon_xy(site),
        existing_z=lambda _x, _y: 0.0,
        proposed_z=lambda _x, _y: 0.5,
        grid_size_m=20.0,
    )
    preview, grid, zero, hatch, cell_dots, vertex_dots = rhino_adapter.cartogram_geometry(
        result,
        lambda _x, _y: 0.5,
    )
    assert preview.Faces.Count == 1
    assert len(grid) == 1
    assert len(zero) == 0
    assert len(hatch) == 0
    assert len(cell_dots) == 1
    assert len(vertex_dots) == 4

    table = STANDARD.earth_mass_table(result)
    table_lines, table_tags = rhino_adapter.cartogram_table_geometry(
        table, (0.0, 0.0, 0.0), 0.4, 1.0
    )
    assert len(table_lines) > 0
    assert len(table_tags) == len(table.header) * (len(table.rows) + 1)

    # Slope hachures from the graded pad mesh (which has 1:2 transition slopes).
    pad_mesh, _ = rhino_adapter.grade_pad_mesh(mesh, pad, 1.0, 2.0, 1.0)

    def _safe_sampler(target_mesh):
        sampler = rhino_adapter.mesh_vertical_sampler(target_mesh, max_horizontal_gap=0.0)

        def sample(x, y):
            try:
                return sampler(x, y)
            except Exception:
                return None

        return sample

    pad_bounds = pad_mesh.GetBoundingBox(True)
    slope = earthwork_core.analyze_slopes(
        sampler=_safe_sampler(pad_mesh),
        origin=(pad_bounds.Min.X, pad_bounds.Min.Y),
        columns=int((pad_bounds.Max.X - pad_bounds.Min.X)) + 1,
        rows=int((pad_bounds.Max.Y - pad_bounds.Min.Y)) + 1,
        spacing=1.0,
        min_steepness=0.2,
    )
    assert slope.slope_cell_count > 0
    assert len(slope.hachures) > 0
    draped = rhino_adapter.drape_segments(slope.hachures, _safe_sampler(pad_mesh), 1.0)
    assert len(draped) > 0

    # Section across existing (flat) and proposed (raised pad): expect fill.
    import Rhino.Geometry as _rg

    section_line = _rg.LineCurve(_rg.Point3d(0.0, 10.0, 0.0), _rg.Point3d(20.0, 10.0, 0.0))
    section_stations = rhino_adapter.section_stations(
        section_line, _safe_sampler(mesh), _safe_sampler(pad_mesh), 20
    )
    assert len(section_stations) >= 2
    section = earthwork_core.build_section(
        [(d, ez, pz) for d, _x, _y, ez, pz in section_stations]
    )
    assert section.fill_area > 0.0
    existing_profile, proposed_profile, _cut, _fill = rhino_adapter.section_geometry(
        section, [(d, x, y) for d, x, y, _ez, _pz in section_stations], 1.0
    )
    assert existing_profile is not None
    assert proposed_profile is not None

    # Serial sections along a baseline across the pad: expect a fill volume.
    baseline = _rg.LineCurve(_rg.Point3d(2.0, 2.0, 0.0), _rg.Point3d(18.0, 18.0, 0.0))
    serial_lines = rhino_adapter.section_lines_along(baseline, 4.0, 8.0)
    assert len(serial_lines) >= 2
    area_stations = []
    for line_distance, cut_line in serial_lines:
        cut_stations = rhino_adapter.section_stations(
            cut_line, _safe_sampler(mesh), _safe_sampler(pad_mesh), 16
        )
        if len(cut_stations) < 2:
            continue
        cut_section = earthwork_core.build_section(
            [(d, ez, pz) for d, _x, _y, ez, pz in cut_stations]
        )
        area_stations.append((line_distance, cut_section.cut_area, cut_section.fill_area))
    serial = earthwork_core.serial_section_volumes(area_stations)
    assert serial.fill_volume > 0.0

    # Relief preview: slope field + arrows + spot elevations on the pad mesh.
    relief = earthwork_core.slope_field(
        _safe_sampler(pad_mesh), (pad_bounds.Min.X, pad_bounds.Min.Y),
        int((pad_bounds.Max.X - pad_bounds.Min.X)) + 1,
        int((pad_bounds.Max.Y - pad_bounds.Min.Y)) + 1, 1.0,
    )
    assert relief
    arrows = rhino_adapter.slope_arrow_curves(relief, _safe_sampler(pad_mesh), 0.6, 1.0)
    spots = rhino_adapter.spot_elevation_tags(relief, 1.0, 0.3, 1.0)
    assert len(arrows) > 0
    assert len(spots) == len(relief)

    # Shared once-sampled analysis grid (used by relief/contour/drainage).
    grid = rhino_adapter.analysis_grid(pad_mesh, None, 1.0)
    assert grid.columns >= 1 and grid.rows >= 1
    assert grid.sampler(grid.origin[0], grid.origin[1]) is not None
    assert earthwork_core.slope_field(
        grid.sampler, grid.origin, grid.columns, grid.rows, grid.spacing
    )

    # Contours of the graded pad (pad at z=1, slopes down to 0): expect levels.
    contour_segs = earthwork_core.contour_segments(
        _safe_sampler(pad_mesh), (pad_bounds.Min.X, pad_bounds.Min.Y),
        int((pad_bounds.Max.X - pad_bounds.Min.X)) + 1,
        int((pad_bounds.Max.Y - pad_bounds.Min.Y)) + 1, 1.0, 0.2, base=0.0,
    )
    assert len(contour_segs) > 0
    assert len(rhino_adapter.contour_curves(contour_segs, 1.0)) == len(contour_segs)

    # Drainage: D8 flow traces over the pad mesh.
    drainage = earthwork_core.drainage_analysis(
        _safe_sampler(pad_mesh), (pad_bounds.Min.X, pad_bounds.Min.Y),
        int((pad_bounds.Max.X - pad_bounds.Min.X)) + 1,
        int((pad_bounds.Max.Y - pad_bounds.Min.Y)) + 1, 1.0, seed_every=2,
    )
    assert drainage.flow_paths
    flow = rhino_adapter.flow_path_curves(drainage.flow_paths, 1.0)
    assert len(flow) > 0
    rhino_adapter.drainage_points(drainage.low_points, 1.0)

    # Ditch along a centreline across the flat mesh: 0.5 m deep invert.
    centerline = _rg.LineCurve(_rg.Point3d(2.0, 5.0, 0.0), _rg.Point3d(18.0, 5.0, 0.0))
    ditch_stations = rhino_adapter.section_stations(centerline, _safe_sampler(mesh), None, 16)
    ditch = earthwork_core.ditch_profile(
        [(d, gz) for d, _x, _y, gz, _pz in ditch_stations], depth=0.5
    )
    assert abs(earthwork_core.ditch_volume(ditch, 0.4, 1.5) - (0.4 * 0.5 + 1.5 * 0.25) * 16.0) < 1e-6
    ditch_xy = [(d, x, y) for d, x, y, _gz, _pz in ditch_stations]
    assert rhino_adapter.ditch_invert_curve(ditch, ditch_xy, 1.0) is not None
    assert len(rhino_adapter.ditch_invert_marks(
        ditch, ditch_xy, standards.get_standard().ditch_invert_label, 1.0, 0.4, every=4
    )) > 0

    # Topsoil strip over the site: 20 x 20 m at 0.2 m -> 80 m3, hatched.
    strip = earthwork_core.topsoil_strip(
        rhino_adapter.curve_polygon_xy(site), strip_depth_m=0.2
    )
    assert abs(strip.volume_m3 - 80.0) < 1e-6
    strip_segments = earthwork_core.hatch_polygon(
        rhino_adapter.curve_polygon_xy(site), 2.0, angle_deg=45.0
    )
    strip_hatch = rhino_adapter.drape_segments(strip_segments, _safe_sampler(mesh), 1.0)
    assert len(strip_hatch) > 0

    grade_component = _run_component(
        "gh_02_grade_pad.py",
        terrain_mesh=mesh,
        pad_boundary=_ValueWrapper(pad),
        pad_elevation_m=1.0,
        slope_ratio=2.0,
        resolution_m=2.0,
    )
    assert grade_component["proposed_mesh"].Vertices.Count > 0
    assert grade_component["edited_vertex_count"] > 0

    cartogram_component = _run_component(
        "gh_01_cut_fill_cartogram.py",
        boundary=_ValueWrapper(site),
        existing_mesh=mesh,
        proposed_mesh=grade_component["proposed_mesh"],
        grid_size_m=20.0,
        samples_per_side=4,
    )
    assert cartogram_component["analysis_mesh"].Faces.Count == 1
    assert len(cartogram_component["grid_curves"]) == 1
    assert cartogram_component["fill_m3"] > 0.0

    smoke_parent = "SMOKE Картограмма"
    geometry_by_key = {
        "boundary": [site],
        "grid_curves": cartogram_component["grid_curves"],
        "zero_work_lines": cartogram_component["zero_work_lines"],
        "cut_hatches": cartogram_component["cut_hatches"],
        "vertex_mark_tags": cartogram_component["vertex_mark_tags"],
        "cell_volume_tags": cartogram_component["cell_volume_tags"],
        "analysis_mesh": [cartogram_component["analysis_mesh"]],
    }
    smoke_group = standards.LayerGroup(
        parent=smoke_parent, layers=STANDARD.cartogram_layers().layers
    )
    try:
        baked, layer_paths = rhino_adapter.bake_group(
            geometry_by_key, smoke_group, replace=True
        )
        assert baked > 0
        assert layer_paths
    finally:
        _delete_layer_tree(smoke_parent)


def _delete_layer_tree(parent_full_path):
    import Rhino

    document = Rhino.RhinoDoc.ActiveDoc
    if document is None:
        return
    layers = document.Layers
    targets = [
        layer
        for layer in layers
        if layer.FullPath == parent_full_path
        or layer.FullPath.startswith(parent_full_path + "::")
    ]
    for layer in targets:
        objects = document.Objects.FindByLayer(layer)
        if objects:
            for rhino_object in objects:
                document.Objects.Delete(rhino_object, True)
    for layer in targets:
        try:
            layers.Delete(layer.Index, True)
        except Exception:
            pass


try:
    run()
    message = "PASS"
except Exception:
    message = "FAIL\n" + traceback.format_exc()

with open(RESULT_PATH, "w", encoding="utf-8") as file:
    file.write(message)

print(message)
