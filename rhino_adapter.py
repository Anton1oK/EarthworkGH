"""RhinoCommon adapters for the earthwork calculation core."""

from __future__ import annotations

import math

import Rhino.Geometry as rg
import Rhino.Geometry.Intersect as rgi
from System.Drawing import Color

from earthwork_core import (
    CutFillResult,
    DocumentUnits,
    EarthworkCell,
    classify_units,
    grade_pad_grid,
    graded_pad_elevation,
    normalize_polygon,
    point_in_polygon,
)


def coerce_mesh(value):
    """Return a Rhino mesh from common Grasshopper wrappers."""

    return _coerce_geometry(value, rg.Mesh, ("Mesh",))


def coerce_curve(value):
    """Return a Rhino curve from common Grasshopper wrappers."""

    return _coerce_geometry(
        value,
        rg.Curve,
        ("Curve", "ToPolylineCurve", "ToNurbsCurve"),
    )


def input_diagnostic(component_globals, name, value, expected):
    """Build a self-describing error suffix for a missing or invalid GH input.

    Reports whether the named socket exists, the type that was delivered, and
    the full list of input sockets, so a vague "connect a curve" failure points
    straight at the real cause (empty socket, wrong type, or an IO-setup build
    issue that left the sockets unnamed). Never raises.
    """

    parts = []
    if value is None:
        parts.append("socket '{}' delivered no value".format(name))
    else:
        try:
            parts.append("socket '{}' delivered a {}".format(name, type(value).__name__))
        except Exception:
            parts.append("socket '{}' delivered an unrecognized value".format(name))

    try:
        ghenv = component_globals.get("ghenv")
        socket_names = [param.NickName for param in ghenv.Component.Params.Input]
        parts.append("input sockets present: [{}]".format(", ".join(socket_names)))
        if name not in socket_names:
            parts.append(
                "no socket named '{}' exists - the dynamic loader did not rename "
                "inputs on this Rhino build; rename the socket or wire the value "
                "into the correct one".format(name)
            )
    except Exception:
        pass

    parts.append("expected {}".format(expected))
    return ". ".join(parts) + "."


def _coerce_geometry(value, geometry_type, conversion_methods):
    """Unwrap a Rhino geometry value from Grasshopper and document wrappers."""

    current = value
    for _index in range(10):
        if current is None:
            return None
        if isinstance(current, geometry_type):
            return current

        converted = _converted_geometry(current, geometry_type, conversion_methods)
        if converted is not None:
            return converted

        unwrapped = _unwrapped_geometry_value(current)
        if unwrapped is not current:
            current = unwrapped
            continue
        break
    return None


def _converted_geometry(value, geometry_type, conversion_methods):
    for method_name in conversion_methods:
        method = getattr(value, method_name, None)
        if method is None or not callable(method):
            continue
        try:
            converted = method()
        except Exception:
            continue
        if isinstance(converted, geometry_type):
            return converted
    return None


def _unwrapped_geometry_value(value):
    document_geometry = _active_document_geometry(value)
    if document_geometry is not None and document_geometry is not value:
        return document_geometry

    for attribute_name in ("Geometry", "ScriptVariable", "Value"):
        try:
            unwrapped = getattr(value, attribute_name)
            if callable(unwrapped):
                unwrapped = unwrapped()
        except Exception:
            continue
        if unwrapped is not None and unwrapped is not value:
            return unwrapped

    if isinstance(value, (list, tuple)) and len(value) == 1:
        return value[0]

    return value


def _active_document_geometry(value):
    """Resolve Rhino object IDs and referenced Grasshopper geometry."""

    try:
        import System

        object_id = value if isinstance(value, System.Guid) else None
        if object_id is None:
            reference_id = getattr(value, "ReferenceID", None)
            if isinstance(reference_id, System.Guid) and reference_id != System.Guid.Empty:
                object_id = reference_id
        if object_id is None or object_id == System.Guid.Empty:
            return None

        for document in _candidate_documents():
            try:
                rhino_object = document.Objects.FindId(object_id)
            except Exception:
                rhino_object = None
            if rhino_object is not None and rhino_object.Geometry is not None:
                return rhino_object.Geometry
        return None
    except Exception:
        return None


def _candidate_documents():
    """Return the Rhino documents that may own a referenced-object GUID."""

    documents = []
    try:
        import Rhino

        active = Rhino.RhinoDoc.ActiveDoc
        if active is not None:
            documents.append(active)
    except Exception:
        pass
    try:
        import scriptcontext

        doc = getattr(scriptcontext, "doc", None)
        if doc is not None and doc not in documents and hasattr(doc, "Objects"):
            documents.append(doc)
    except Exception:
        pass
    return documents


def document_unit_info():
    """Read the active document's length unit before any calculation.

    Returns a DocumentUnits: it handles ANY Rhino unit system (mm, cm, m, inch,
    foot, ...) via ``UnitScale``, and flags ``reliable=False`` when there is no
    active document or the model is unitless - so components warn instead of
    silently assuming 1 unit = 1 m (a 1000x error for a mm model).
    """

    try:
        import Rhino
        import scriptcontext

        document = Rhino.RhinoDoc.ActiveDoc or getattr(scriptcontext, "doc", None)
        if document is None:
            return classify_units(0.0, "no active document", reliable=False)
        system = document.ModelUnitSystem
        meters_per_unit = Rhino.RhinoMath.UnitScale(system, Rhino.UnitSystem.Meters)
        return classify_units(meters_per_unit, str(system))
    except Exception:
        return classify_units(0.0, "units unavailable", reliable=False)


def document_units_per_meter():
    """Return how many active-document length units make up one metre.

    Millimetre models return 1000, centimetre 100, metre 1, inches ~39.37. Falls
    back to 1.0 when the document or unit system cannot be read. For the dangerous
    fallback case, read ``document_unit_info().reliable`` and warn the user.
    """

    return document_unit_info().units_per_meter


def units_status_line(info=None, volume_label="m3"):
    """A one-line, human-readable readout of the model units (or a loud warning)."""

    if info is None:
        info = document_unit_info()
    if not info.reliable:
        return (
            "WARNING: the Rhino model has no unit system set (got '{}'); assuming "
            "1 unit = 1 m. Set the document units (mm / m / inch / ft) so lengths "
            "and {} volumes are correct.".format(info.name, volume_label)
        )
    return "Model units: {} (1 m = {:g} {}); volumes in {}.".format(
        info.name, info.units_per_meter, info.label, volume_label
    )


def curve_points_xyz(curve, segment_count=64):
    """Return a curve's vertices as ``(x, y, z)`` (its polyline points or samples)."""

    if curve is None:
        raise ValueError("Connect a design polyline through the spot elevations.")
    success, polyline = curve.TryGetPolyline()
    if success:
        points = [(float(p.X), float(p.Y), float(p.Z)) for p in polyline]
        if len(points) >= 2 and points[0] == points[-1]:
            points.pop()
        return points
    parameters = curve.DivideByCount(int(segment_count), True)
    return [
        (float(curve.PointAt(t).X), float(curve.PointAt(t).Y), float(curve.PointAt(t).Z))
        for t in parameters
    ]


def _rectangle_curve_xyz(x0, y0, x1, y1, z):
    return rg.PolylineCurve(
        [
            rg.Point3d(x0, y0, z),
            rg.Point3d(x1, y0, z),
            rg.Point3d(x1, y1, z),
            rg.Point3d(x0, y1, z),
            rg.Point3d(x0, y0, z),
        ]
    )


def sheet_frame_geometry(width_mm, height_mm, origin, mm_scale):
    """Outer sheet border and inner frame (20 mm binding, 5 mm others)."""

    ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
    s = float(mm_scale)
    outer = _rectangle_curve_xyz(ox, oy, ox + width_mm * s, oy + height_mm * s, oz)
    inner = _rectangle_curve_xyz(
        ox + 20.0 * s, oy + 5.0 * s, ox + (width_mm - 5.0) * s, oy + (height_mm - 5.0) * s, oz
    )
    return [outer, inner]


def titleblock_geometry(rows, width_mm, height_mm, origin, mm_scale,
                        text_height_mm=3.0, stamp=None):
    """Simplified main title block (185 x 55 mm) at the sheet's bottom-right.

    ``rows`` is ``(label, value)`` top to bottom. ``stamp`` (optional) is a
    small provenance line placed just above the block. Returns
    ``(lines, text_tags)``.
    """

    ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
    s = float(mm_scale)
    block_w, block_h, label_w = 185.0, 55.0, 45.0
    bx = ox + (width_mm - 5.0 - block_w) * s
    by = oy + 5.0 * s

    lines = [_rectangle_curve_xyz(bx, by, bx + block_w * s, by + block_h * s, oz)]
    count = max(1, len(rows))
    row_h = block_h / count
    for k in range(1, count):
        y = by + k * row_h * s
        lines.append(rg.LineCurve(rg.Point3d(bx, y, oz), rg.Point3d(bx + block_w * s, y, oz)))
    lines.append(
        rg.LineCurve(
            rg.Point3d(bx + label_w * s, by, oz),
            rg.Point3d(bx + label_w * s, by + block_h * s, oz),
        )
    )

    tags = []
    th = text_height_mm * s
    for index, (label, value) in enumerate(rows):
        row_from_bottom = count - 1 - index
        cy = by + (row_from_bottom + 0.5) * row_h * s
        tags.append(_text_tag(str(label), rg.Point3d(bx + label_w * 0.5 * s, cy, oz), th))
        tags.append(
            _text_tag(
                str(value),
                rg.Point3d(bx + (label_w + (block_w - label_w) * 0.5) * s, cy, oz),
                th,
            )
        )
    if stamp:
        # Provenance line, 2 mm above the block's top-left, smaller than the form.
        tags.append(
            _text_tag(str(stamp), rg.Point3d(bx, by + (block_h + 2.0) * s, oz), 2.0 * s)
        )
    return lines, tags


def grid_mesh(points, columns, rows):
    """Build a quad mesh from a row-major ``(columns+1) x (rows+1)`` (x,y,z) grid."""

    mesh = rg.Mesh()
    for x, y, z in points:
        mesh.Vertices.Add(x, y, z)
    stride = columns + 1
    for row in range(rows):
        for column in range(columns):
            base = row * stride + column
            mesh.Faces.AddFace(base, base + 1, base + stride + 1, base + stride)
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


def curve_polygon_xy(curve, segment_count=128):
    """Approximate a closed boundary curve as an XY polygon."""

    if curve is None:
        raise ValueError("Connect a closed boundary curve.")
    if not curve.IsClosed:
        raise ValueError("Boundary curve must be closed.")

    success, polyline = curve.TryGetPolyline()
    if success:
        points = list(polyline)
    else:
        parameters = curve.DivideByCount(int(segment_count), True)
        points = [curve.PointAt(parameter) for parameter in parameters]
    return tuple((float(point.X), float(point.Y)) for point in points)


class AnalysisGrid:
    """A once-sampled elevation grid plus the metadata analyses need."""

    def __init__(self, units_per_meter, spacing, origin, columns, rows, sampler, inside):
        self.units_per_meter = units_per_meter
        self.meters_per_unit = 1.0 / units_per_meter
        self.spacing = spacing
        self.origin = origin
        self.columns = columns
        self.rows = rows
        self.sampler = sampler
        self.inside = inside


def analysis_grid(mesh, boundary_curve, grid_size_m, max_points=60000):
    """Build a once-sampled analysis grid shared by relief/contour/drainage/export.

    The mesh elevation is ray-sampled on the ``(columns+1) x (rows+1)`` node grid a
    single time into a cache; the returned ``sampler(x, y)`` is an O(1) lookup into
    that cache (no further ray casts), keyed by the nearest node. Several analyses
    over the same area therefore reuse one consistent, cheaply-read grid instead of
    each re-casting rays. Raises if the grid would need more than ``max_points``.
    """

    units_per_meter = document_units_per_meter()
    spacing = float(grid_size_m) * units_per_meter
    if spacing <= 0.0:
        raise ValueError("grid_size_m must be positive.")

    inside = None
    if boundary_curve is not None:
        polygon = normalize_polygon(curve_polygon_xy(boundary_curve))
        min_x = min(p[0] for p in polygon)
        min_y = min(p[1] for p in polygon)
        max_x = max(p[0] for p in polygon)
        max_y = max(p[1] for p in polygon)

        def inside(x, y, _poly=polygon):
            return point_in_polygon((x, y), _poly)
    else:
        bounds = mesh.GetBoundingBox(True)
        min_x, min_y = float(bounds.Min.X), float(bounds.Min.Y)
        max_x, max_y = float(bounds.Max.X), float(bounds.Max.Y)

    columns = max(1, int(math.ceil((max_x - min_x) / spacing)))
    rows = max(1, int(math.ceil((max_y - min_y) / spacing)))
    if (columns + 1) * (rows + 1) > max_points:
        raise ValueError(
            "Analysis grid needs {} sample points - too many to ray-sample "
            "interactively. Use a larger grid_size_m or a smaller boundary.".format(
                (columns + 1) * (rows + 1)
            )
        )

    raw = mesh_vertical_sampler(mesh, max_horizontal_gap=2.0 * spacing)
    cache = {}
    for j in range(rows + 1):
        for i in range(columns + 1):
            try:
                cache[(i, j)] = raw(min_x + i * spacing, min_y + j * spacing)
            except Exception:
                cache[(i, j)] = None

    def sampler(x, y):
        return cache.get(
            (
                int(round((x - min_x) / spacing)),
                int(round((y - min_y) / spacing)),
            )
        )

    return AnalysisGrid(units_per_meter, spacing, (min_x, min_y), columns, rows, sampler, inside)


def mesh_vertical_sampler(mesh, max_horizontal_gap=None, meters_per_unit=1.0):
    """Create an XY elevation sampler for a single-surface 2.5D mesh.

    A vertical ray is the primary, exact sampler. When a sample point falls just
    past the mesh footprint - which happens because the analysis grid snaps
    outward to whole grid lines - the nearest point on the mesh is used instead,
    as long as it is within `max_horizontal_gap` (document units). A larger gap
    means the mesh and the site boundary do not overlap (usually a misalignment
    or a mesh that is too small), so a diagnostic error is raised with the actual
    gap and mesh extent. `meters_per_unit` is used only to report distances in
    metres in that error message.
    """

    if mesh is None:
        raise ValueError("Terrain mesh is required.")
    bounds = mesh.GetBoundingBox(True)
    ray_start_z = float(bounds.Max.Z + max(bounds.Diagonal.Length, 1.0))
    mid_z = float((bounds.Min.Z + bounds.Max.Z) / 2.0)
    if max_horizontal_gap is None:
        diagonal_xy = math.hypot(bounds.Max.X - bounds.Min.X, bounds.Max.Y - bounds.Min.Y)
        gap_limit = max(diagonal_xy * 0.05, 1.0)
    else:
        gap_limit = float(max_horizontal_gap)
    mpu = float(meters_per_unit) if meters_per_unit else 1.0

    def sample(x, y):
        x = float(x)
        y = float(y)
        ray = rg.Ray3d(rg.Point3d(x, y, ray_start_z), -rg.Vector3d.ZAxis)
        distance = rgi.Intersection.MeshRay(mesh, ray)
        if distance >= 0.0:
            return float(ray.PointAt(distance).Z)

        try:
            nearest = mesh.ClosestPoint(rg.Point3d(x, y, mid_z))
        except Exception:
            nearest = None
        if nearest is not None and nearest.IsValid:
            gap = math.hypot(nearest.X - x, nearest.Y - y)
            if gap <= gap_limit:
                return float(nearest.Z)
            raise ValueError(
                "Terrain mesh does not cover analysis point ({:.3f}, {:.3f}); "
                "nearest mesh surface is {:.3f} m away (limit {:.3f} m). The mesh "
                "and the site boundary may be misaligned or the mesh is too small. "
                "Mesh XY extent (m): X[{:.3f}..{:.3f}] Y[{:.3f}..{:.3f}].".format(
                    x, y, gap * mpu, gap_limit * mpu,
                    bounds.Min.X * mpu, bounds.Max.X * mpu,
                    bounds.Min.Y * mpu, bounds.Max.Y * mpu,
                )
            )
        raise ValueError(
            "Terrain mesh has no vertical intersection at ({:.3f}, {:.3f}).".format(x, y)
        )

    return sample


def cartogram_geometry(result: CutFillResult, proposed_sampler, text_height=0.4,
                       meters_per_unit=1.0, volume_label="m3", volume_factor=1.0):
    """Build Rhino preview and drafting geometry from a cartogram result.

    Geometry is placed in document units (so it overlays the model), while
    elevation/work labels are shown in metres. ``meters_per_unit`` is the scale
    from one document unit to metres (e.g. 0.001 for a millimetre model); draft
    lift offsets are scaled by its inverse so they stay ~1 cm in any unit.
    ``volume_label`` is the (locale-specific) unit suffix on cell-volume tags.
    """

    meters_per_unit = float(meters_per_unit)
    unit_scale = 1.0 / meters_per_unit if meters_per_unit > 0.0 else 1.0
    cell_tag_height = text_height * unit_scale
    vertex_tag_height = 0.7 * text_height * unit_scale
    vertex_lift = 0.03 * unit_scale

    preview = rg.Mesh()
    grid_curves = []
    hatches = []
    cell_dots = []
    vertex_dots = []
    emitted_vertices = set()

    for cell in result.cells:
        _append_preview_cell(preview, cell, proposed_sampler)
        grid_curves.append(_cell_polyline(cell, proposed_sampler, unit_scale))
        if cell.classification in ("cut", "mixed"):
            hatches.extend(_cell_hatches(cell, proposed_sampler, unit_scale))
        if cell.classification != "zero":
            cell_dots.append(
                _cell_volume_tag(
                    cell, proposed_sampler, unit_scale, cell_tag_height,
                    volume_label, volume_factor
                )
            )
        for vertex in cell.corners:
            key = (round(vertex.x, 9), round(vertex.y, 9))
            if key in emitted_vertices:
                continue
            emitted_vertices.add(key)
            vertex_dots.append(
                _text_tag(
                    "{:.2f}\n{:.2f}\n{:+.2f}".format(
                        vertex.proposed_z * meters_per_unit,
                        vertex.existing_z * meters_per_unit,
                        vertex.work_mark * meters_per_unit,
                    ),
                    rg.Point3d(vertex.x, vertex.y, vertex.proposed_z + vertex_lift),
                    vertex_tag_height,
                )
            )

    preview.Normals.ComputeNormals()
    preview.Compact()
    zero_lift = 0.01 * unit_scale
    zero_lines = [
        rg.LineCurve(
            rg.Point3d(start[0], start[1], proposed_sampler(*start) + zero_lift),
            rg.Point3d(end[0], end[1], proposed_sampler(*end) + zero_lift),
        )
        for start, end in result.zero_work_segments
    ]
    return preview, grid_curves, zero_lines, hatches, cell_dots, vertex_dots


def grade_pad_mesh(mesh, boundary_curve, pad_elevation_m, slope_ratio, resolution):
    """Resample a 2.5D terrain onto a regular grid and form a flat grading pad.

    Rather than nudging the source mesh's vertices - which leaves the pad edge
    and slope hostage to an irregular triangulation - the existing surface is
    sampled vertically on a uniform `resolution`-spaced grid over its footprint,
    graded, and rebuilt. The result has clean pad edges and an even slope band at
    a predictable density. All lengths are in document units.
    """

    if not boundary_curve.IsClosed:
        raise ValueError("Pad boundary must be a closed curve.")
    resolution = float(resolution)
    if resolution <= 0.0:
        raise ValueError("Pad grid resolution must be positive.")

    bounds = mesh.GetBoundingBox(True)
    width = float(bounds.Max.X - bounds.Min.X)
    height = float(bounds.Max.Y - bounds.Min.Y)
    columns = max(1, int(math.ceil(width / resolution)))
    rows = max(1, int(math.ceil(height / resolution)))

    max_vertices = 250000
    if (columns + 1) * (rows + 1) > max_vertices:
        suggested = math.sqrt(max(width * height, 1.0) / float(max_vertices))
        raise ValueError(
            "Pad grid would need {} points at this resolution. Use a resolution "
            "of at least {:.3f} document units for this terrain extent.".format(
                (columns + 1) * (rows + 1), suggested
            )
        )

    # A generous gap means every grid point over the mesh footprint resolves to
    # a real or nearest-mesh elevation instead of aborting on a small hole.
    sampler = mesh_vertical_sampler(
        mesh, max_horizontal_gap=max(float(bounds.Diagonal.Length), resolution)
    )
    tolerance = 1e-7

    def inside_pad_at(x, y):
        containment = boundary_curve.Contains(
            rg.Point3d(x, y, 0.0), rg.Plane.WorldXY, tolerance
        )
        return containment != rg.PointContainment.Outside

    def distance_to_pad_at(x, y):
        point_xy = rg.Point3d(x, y, 0.0)
        success, parameter = boundary_curve.ClosestPoint(point_xy)
        if not success:
            return 0.0
        return point_xy.DistanceTo(boundary_curve.PointAt(parameter))

    points, edited = grade_pad_grid(
        existing_z=sampler,
        inside_pad_at=inside_pad_at,
        distance_to_pad_at=distance_to_pad_at,
        origin=(float(bounds.Min.X), float(bounds.Min.Y)),
        columns=columns,
        rows=rows,
        spacing=resolution,
        pad_elevation_m=float(pad_elevation_m),
        slope_ratio=float(slope_ratio),
    )

    output = rg.Mesh()
    for x, y, z in points:
        output.Vertices.Add(x, y, z)
    stride = columns + 1
    for row in range(rows):
        for column in range(columns):
            base = row * stride + column
            output.Faces.AddFace(base, base + 1, base + stride + 1, base + stride)
    output.Normals.ComputeNormals()
    output.Compact()
    return output, edited


def drape_segments(segments, sampler, unit_scale=1.0, lift=0.05):
    """Turn XY ``(start, end)`` segments into LineCurves draped on the surface.

    ``sampler(x, y)`` returns an elevation or ``None`` off the mesh; segments with
    no elevation at the start are skipped, and a missing end falls back to the
    start elevation. ``lift`` (metres, scaled by ``unit_scale``) keeps the lines
    just above the mesh.
    """

    lift_doc = float(lift) * float(unit_scale)
    curves = []
    for start, end in segments:
        start_z = sampler(start[0], start[1])
        if start_z is None:
            continue
        end_z = sampler(end[0], end[1])
        if end_z is None:
            end_z = start_z
        curves.append(
            rg.LineCurve(
                rg.Point3d(start[0], start[1], start_z + lift_doc),
                rg.Point3d(end[0], end[1], end_z + lift_doc),
            )
        )
    return curves


def flow_path_curves(paths, unit_scale=1.0, lift=0.04):
    """Turn 3D flow paths ``[(x, y, z), ...]`` into polylines on the surface.

    The elevations come from the drainage trace, so the mesh is not re-sampled.
    """

    lift_doc = float(lift) * float(unit_scale)
    curves = []
    for path in paths:
        if len(path) < 2:
            continue
        curves.append(
            rg.PolylineCurve([rg.Point3d(x, y, z + lift_doc) for x, y, z in path])
        )
    return curves


def drainage_points(points, unit_scale=1.0, lift=0.05):
    """Turn DrainagePoints (x, y, z) into Rhino Point3d objects on the surface."""

    lift_doc = float(lift) * float(unit_scale)
    return [rg.Point3d(p.x, p.y, p.z + lift_doc) for p in points]


def contour_curves(segments, unit_scale=1.0, lift=0.01):
    """Turn ``(level, start, end)`` contour segments into LineCurves at z=level."""

    lift_doc = float(lift) * float(unit_scale)
    curves = []
    for level, start, end in segments:
        curves.append(
            rg.LineCurve(
                rg.Point3d(start[0], start[1], level + lift_doc),
                rg.Point3d(end[0], end[1], level + lift_doc),
            )
        )
    return curves


def slope_arrow_curves(samples, sampler, arrow_length, unit_scale=1.0, min_steepness=0.0):
    """Build draped downhill arrows (shaft + two barbs) at relief samples.

    Each arrow is one polyline ``[start, tip, barb, tip, barb]`` draped on the
    surface, pointing downhill. Flat samples (steepness <= ``min_steepness``) are
    skipped. ``arrow_length`` is in document units.
    """

    lift = 0.05 * float(unit_scale)
    arrow_length = float(arrow_length)
    barb = arrow_length * 0.3
    curves = []
    for sample in samples:
        if sample.steepness <= min_steepness:
            continue
        start_z = sampler(sample.x, sample.y)
        if start_z is None:
            continue
        tip_x = sample.x + sample.downhill_x * arrow_length
        tip_y = sample.y + sample.downhill_y * arrow_length
        angle = math.atan2(sample.downhill_y, sample.downhill_x)
        barb1 = (tip_x + math.cos(angle + 2.618) * barb, tip_y + math.sin(angle + 2.618) * barb)
        barb2 = (tip_x + math.cos(angle - 2.618) * barb, tip_y + math.sin(angle - 2.618) * barb)

        def draped(point, fallback):
            z = sampler(point[0], point[1])
            return rg.Point3d(point[0], point[1], (z if z is not None else fallback) + lift)

        path = [
            draped((sample.x, sample.y), start_z),
            draped((tip_x, tip_y), start_z),
            draped(barb1, start_z),
            draped((tip_x, tip_y), start_z),
            draped(barb2, start_z),
        ]
        curves.append(rg.PolylineCurve(path))
    return curves


def spot_elevation_tags(samples, meters_per_unit, text_height, unit_scale=1.0):
    """Build elevation text tags (metres) at relief sample centres."""

    tags = []
    for sample in samples:
        tags.append(
            _text_tag(
                "{:.2f}".format(sample.z * meters_per_unit),
                rg.Point3d(sample.x, sample.y, sample.z + 0.05 * unit_scale),
                text_height,
            )
        )
    return tags


def section_stations(curve, existing_sampler, proposed_sampler, divisions):
    """Sample existing (and optional proposed) elevations along a section curve.

    Returns a list of ``(distance, x, y, existing_z, proposed_z)`` at evenly
    spaced stations; ``distance`` is the cumulative horizontal run. Stations with
    no existing elevation are dropped but still advance the distance.
    """

    parameters = curve.DivideByCount(int(divisions), True)
    parameters = list(parameters) if parameters is not None else []
    if len(parameters) < 2:
        parameters = [curve.Domain.T0, curve.Domain.T1]

    stations = []
    distance = 0.0
    previous = None
    for parameter in parameters:
        point = curve.PointAt(parameter)
        if previous is not None:
            distance += math.hypot(point.X - previous.X, point.Y - previous.Y)
        previous = point
        x, y = float(point.X), float(point.Y)
        existing_z = existing_sampler(x, y)
        if existing_z is None:
            continue
        proposed_z = proposed_sampler(x, y) if proposed_sampler is not None else None
        stations.append((distance, x, y, existing_z, proposed_z))
    return stations


def section_lines_along(baseline, spacing, half_width):
    """Build perpendicular section lines at intervals along a baseline curve.

    Returns ``(distance_along_baseline, line_curve)`` for each station, spaced by
    ``spacing`` (document units) along the baseline, each line reaching
    ``half_width`` either side. Distances are true arc lengths, so an uneven last
    gap still gives correct average-end-area volumes.
    """

    spacing = float(spacing)
    half_width = float(half_width)
    parameters = baseline.DivideByLength(spacing, True)
    parameters = list(parameters) if parameters is not None else []
    if len(parameters) < 1:
        parameters = [baseline.Domain.T0, baseline.Domain.T1]

    lines = []
    for parameter in parameters:
        point = baseline.PointAt(parameter)
        tangent = baseline.TangentAt(parameter)
        perpendicular = rg.Vector3d(-tangent.Y, tangent.X, 0.0)
        if not perpendicular.Unitize():
            continue
        start = rg.Point3d(
            point.X - perpendicular.X * half_width,
            point.Y - perpendicular.Y * half_width,
            0.0,
        )
        end = rg.Point3d(
            point.X + perpendicular.X * half_width,
            point.Y + perpendicular.Y * half_width,
            0.0,
        )
        distance = baseline.GetLength(rg.Interval(baseline.Domain.T0, parameter))
        lines.append((float(distance), rg.LineCurve(start, end)))
    return lines


def _distance_to_xy(station_xy):
    """Return a function mapping a distance to an interpolated XY on the line."""

    import bisect

    data = sorted((float(d), float(x), float(y)) for d, x, y in station_xy)
    distances = [row[0] for row in data]

    def at(distance):
        if distance <= distances[0]:
            return data[0][1], data[0][2]
        if distance >= distances[-1]:
            return data[-1][1], data[-1][2]
        index = bisect.bisect_right(distances, distance) - 1
        d0, x0, y0 = data[index]
        d1, x1, y1 = data[index + 1]
        ratio = 0.0 if d1 == d0 else (distance - d0) / (d1 - d0)
        return x0 + ratio * (x1 - x0), y0 + ratio * (y1 - y0)

    return at


def section_geometry(section, station_xy, unit_scale=1.0):
    """Build in-place 3D section geometry standing along the cut line.

    Maps each ``(distance, elevation)`` back onto the line's XY at real height, so
    the ground lines drape on the meshes and the cut/fill regions are vertical
    polygons on the section plane. Returns
    ``(existing_curve, proposed_curve, cut_curves, fill_curves)``.
    """

    at = _distance_to_xy(station_xy)
    lift = 0.02 * float(unit_scale)

    def point(distance_z, extra_lift=0.0):
        x, y = at(distance_z[0])
        return rg.Point3d(x, y, distance_z[1] + extra_lift)

    def polyline(profile, extra_lift):
        if len(profile) < 2:
            return None
        return rg.PolylineCurve([point(item, extra_lift) for item in profile])

    def region(polygon):
        cleaned = []
        for item in polygon:
            candidate = point(item)
            if not cleaned or cleaned[-1].DistanceTo(candidate) > 1e-9:
                cleaned.append(candidate)
        if len(cleaned) < 3:
            return None
        cleaned.append(cleaned[0])
        return rg.PolylineCurve(cleaned)

    existing_curve = polyline(section.existing_line, lift)
    proposed_curve = polyline(section.proposed_line, lift)
    cut_curves = [c for c in (region(p) for p in section.cut_regions) if c is not None]
    fill_curves = [c for c in (region(p) for p in section.fill_regions) if c is not None]
    return existing_curve, proposed_curve, cut_curves, fill_curves


def ditch_invert_curve(profile, station_xy, unit_scale=1.0, lift=0.02):
    """Polyline of the ditch invert along the centreline (at invert elevations)."""

    at = _distance_to_xy(station_xy)
    lift_doc = float(lift) * float(unit_scale)
    points = []
    for station in profile.stations:
        x, y = at(station.distance)
        points.append(rg.Point3d(x, y, station.invert_z + lift_doc))
    if len(points) < 2:
        return None
    return rg.PolylineCurve(points)


def ditch_invert_marks(profile, station_xy, label, meters_per_unit, text_height,
                       unit_scale=1.0, every=1):
    """Invert-elevation text tags along the ditch (``label`` formats metres)."""

    at = _distance_to_xy(station_xy)
    every = max(1, int(every))
    lift = 0.06 * float(unit_scale)
    tags = []
    for index, station in enumerate(profile.stations):
        if index % every:
            continue
        x, y = at(station.distance)
        tags.append(
            _text_tag(
                label(station.invert_z * meters_per_unit),
                rg.Point3d(x, y, station.invert_z + lift),
                text_height,
            )
        )
    return tags


def path_grade_marks(profile, station_xy, station_z, label, text_height, unit_scale=1.0):
    """Grade text tags at each path segment midpoint (draped at the centreline z).

    ``station_z`` maps a distance to the centreline elevation; ``label`` formats a
    grade percent. Returns one tag per segment.
    """

    at = _distance_to_xy(station_xy)
    lift = 0.06 * float(unit_scale)
    tags = []
    for grade in profile.grades:
        mid = 0.5 * (grade.from_distance + grade.to_distance)
        x, y = at(mid)
        tags.append(
            _text_tag(label(grade.grade_percent), rg.Point3d(x, y, station_z(mid) + lift), text_height)
        )
    return tags


def offset_curve_both(curve, distance, document=None):
    """Offset an open centreline to both sides; returns ``(left, right)`` or Nones."""

    import Rhino
    import scriptcontext

    try:
        active = document or Rhino.RhinoDoc.ActiveDoc or getattr(scriptcontext, "doc", None)
        tolerance = float(active.ModelAbsoluteTolerance) if active is not None else 1e-3
    except Exception:
        tolerance = 1e-3
    if tolerance <= 0.0:
        tolerance = 1e-3

    def one(signed):
        try:
            result = curve.Offset(
                rg.Plane.WorldXY, signed, tolerance, rg.CurveOffsetCornerStyle.Sharp
            )
        except Exception:
            result = None
        return result[0] if result else None

    return one(abs(float(distance))), one(-abs(float(distance)))


def offset_curve_outward(curve, distance, document=None):
    """Offset a closed planar curve outward by ``distance`` (document units).

    Tries both offset directions and returns the result enclosing the larger
    area (the outward one). Returns ``None`` if the offset fails, so callers can
    fall back to an area estimate without aborting.
    """

    import Rhino
    import scriptcontext

    try:
        active = document or Rhino.RhinoDoc.ActiveDoc or getattr(scriptcontext, "doc", None)
        tolerance = float(active.ModelAbsoluteTolerance) if active is not None else 1e-3
    except Exception:
        tolerance = 1e-3
    if tolerance <= 0.0:
        tolerance = 1e-3

    best = None
    best_area = -1.0
    for signed in (float(distance), -float(distance)):
        try:
            offsets = curve.Offset(
                rg.Plane.WorldXY, signed, tolerance, rg.CurveOffsetCornerStyle.Sharp
            )
        except Exception:
            offsets = None
        if not offsets:
            continue
        for candidate in offsets:
            try:
                properties = rg.AreaMassProperties.Compute(candidate)
                area = properties.Area if properties is not None else -1.0
            except Exception:
                area = -1.0
            if area > best_area:
                best_area = area
                best = candidate
    return best


def bake_group(geometry_by_key, layer_group, replace=True, document=None):
    """Bake categorised geometry onto a standard's layer group.

    ``geometry_by_key`` maps each layer spec ``key`` to a geometry item or list.
    ``layer_group`` carries ``parent`` and ``layers`` (each with key/name/color/
    plot_weight_mm), so all the names, colours and print weights come from the
    active standard rather than this module. When ``replace`` is true the managed
    layers are cleared first, so re-baking refreshes rather than duplicates.
    Returns ``(baked_object_count, layer_full_paths)``.
    """

    import Rhino
    import scriptcontext

    document = document or Rhino.RhinoDoc.ActiveDoc or getattr(scriptcontext, "doc", None)
    if document is None:
        raise ValueError("No active Rhino document to bake into.")

    parent_index = None
    if getattr(layer_group, "parent", None):
        parent_index = _ensure_layer(document, layer_group.parent, None, None, 0.0)

    baked = 0
    layer_paths = []
    for spec in layer_group.layers:
        layer_index = _ensure_layer(
            document, spec.name, parent_index, spec.color, spec.plot_weight_mm
        )
        layer_paths.append(document.Layers[layer_index].FullPath)
        if replace:
            _purge_layer_objects(document, layer_index)

        attributes = Rhino.DocObjects.ObjectAttributes()
        attributes.LayerIndex = layer_index
        for value in _as_list(geometry_by_key.get(spec.key)):
            if _add_geometry(document, value, attributes):
                baked += 1

    document.Views.Redraw()
    return baked, layer_paths


def _ensure_layer(document, name, parent_index, color, plot_weight_mm):
    """Find or create a (possibly child) layer and apply colour/print weight."""

    import Rhino
    from System.Drawing import Color

    layers = document.Layers
    if parent_index is not None and parent_index >= 0:
        full_path = "{}::{}".format(layers[parent_index].FullPath, name)
    else:
        full_path = name

    index = layers.FindByFullPath(full_path, -1)
    if index < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = name
        if parent_index is not None and parent_index >= 0:
            layer.ParentLayerId = layers[parent_index].Id
        if color is not None:
            layer.Color = Color.FromArgb(int(color[0]), int(color[1]), int(color[2]))
        if plot_weight_mm and plot_weight_mm > 0.0:
            layer.PlotWeight = float(plot_weight_mm)
        index = layers.Add(layer)
        return index

    layer = layers[index]
    changed = False
    if color is not None:
        layer.Color = Color.FromArgb(int(color[0]), int(color[1]), int(color[2]))
        changed = True
    if plot_weight_mm and plot_weight_mm > 0.0:
        layer.PlotWeight = float(plot_weight_mm)
        changed = True
    if changed:
        try:
            layers.Modify(layer, index, True)
        except Exception:
            pass
    return index


def _purge_layer_objects(document, layer_index):
    """Delete every object currently on a managed layer (for idempotent bakes)."""

    try:
        layer = document.Layers[layer_index]
        objects = document.Objects.FindByLayer(layer)
    except Exception:
        objects = None
    if not objects:
        return
    for rhino_object in objects:
        try:
            document.Objects.Delete(rhino_object, True)
        except Exception:
            pass


def _add_geometry(document, value, attributes):
    """Unwrap a Grasshopper value and add it to the document; return success."""

    import System

    geometry = _bake_unwrap(value)
    if geometry is None:
        return False
    objects = document.Objects
    try:
        if isinstance(geometry, rg.TextEntity):
            guid = objects.AddText(geometry, attributes)
        elif isinstance(geometry, rg.Mesh):
            guid = objects.AddMesh(geometry, attributes)
        elif isinstance(geometry, rg.Curve):
            guid = objects.AddCurve(geometry, attributes)
        elif isinstance(geometry, rg.Point3d):
            guid = objects.AddPoint(geometry, attributes)
        else:
            return False
    except Exception:
        return False
    return guid != System.Guid.Empty


def _bake_unwrap(value):
    """Resolve a Grasshopper-wrapped value down to RhinoCommon geometry."""

    current = value
    for _index in range(8):
        if current is None:
            return None
        if isinstance(current, (rg.GeometryBase, rg.Point3d)):
            return current
        unwrapped = _unwrapped_geometry_value(current)
        if unwrapped is current:
            break
        current = unwrapped
    if isinstance(current, (rg.GeometryBase, rg.Point3d)):
        return current
    return None


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _append_preview_cell(mesh, cell, proposed_sampler):
    color = {
        "cut": Color.FromArgb(210, 210, 66, 55),
        "fill": Color.FromArgb(210, 73, 156, 84),
        "mixed": Color.FromArgb(210, 232, 164, 56),
        "zero": Color.FromArgb(160, 170, 170, 170),
    }[cell.classification]
    indexes = []
    for vertex in cell.corners:
        indexes.append(mesh.Vertices.Add(vertex.x, vertex.y, proposed_sampler(vertex.x, vertex.y)))
        mesh.VertexColors.Add(color)
    mesh.Faces.AddFace(indexes[0], indexes[1], indexes[2], indexes[3])


def _cell_polyline(cell, proposed_sampler, unit_scale=1.0):
    lift = 0.015 * unit_scale
    points = [
        rg.Point3d(vertex.x, vertex.y, proposed_sampler(vertex.x, vertex.y) + lift)
        for vertex in cell.corners
    ]
    points.append(points[0])
    return rg.PolylineCurve(points)


def _cell_hatches(cell, proposed_sampler, unit_scale=1.0):
    vertices = cell.corners
    x0 = vertices[0].x
    y0 = vertices[0].y
    x1 = vertices[2].x
    y1 = vertices[2].y
    size = x1 - x0
    lift = 0.02 * unit_scale
    lines = []
    for offset_index in range(-3, 4):
        offset = offset_index * size / 4.0
        start_x = max(x0, x0 + offset)
        start_y = max(y0, y0 - offset)
        end_x = min(x1, x1 + offset)
        end_y = min(y1, y1 - offset)
        if end_x - start_x <= 1e-9:
            continue
        lines.append(
            rg.LineCurve(
                rg.Point3d(start_x, start_y, proposed_sampler(start_x, start_y) + lift),
                rg.Point3d(end_x, end_y, proposed_sampler(end_x, end_y) + lift),
            )
        )
    return lines


def _cell_volume_tag(cell, proposed_sampler, unit_scale=1.0, text_height=0.4,
                     volume_label="m3", volume_factor=1.0):
    x, y = cell.center
    z = proposed_sampler(x, y) + 0.025 * unit_scale
    return _text_tag(
        "{:+.1f} {}".format(cell.net_m3 * volume_factor, volume_label),
        rg.Point3d(x, y, z),
        text_height,
    )


def text_tag(text, point, height):
    """Public wrapper: a model-space text annotation at a point (document units)."""

    return _text_tag(text, point, height)


def _text_tag(text, point, height):
    """Create a model-space text annotation (Rhino TextEntity) at a point.

    TextEntity bakes and scales with the model, unlike a fixed-size TextDot, so
    it suits drawing production. Falls back through API variants because the
    TextEntity constructor differs across Rhino builds.
    """

    plane = rg.Plane(point, rg.Vector3d.ZAxis)
    entity = None
    try:
        style = rg.DimensionStyle()
        style.TextHeight = height
        entity = rg.TextEntity.Create(text, plane, style, False, 0.0, 0.0)
    except Exception:
        entity = None
    if entity is None:
        entity = rg.TextEntity()
        try:
            entity.Plane = plane
        except Exception:
            pass
        for attribute in ("PlainText", "Text"):
            try:
                setattr(entity, attribute, text)
                break
            except Exception:
                continue
    try:
        entity.TextHeight = height
    except Exception:
        pass
    try:
        entity.Justification = rg.TextJustification.MiddleCenter
    except Exception:
        pass
    return entity


def cartogram_table_geometry(table, origin, text_height, unit_scale=1.0):
    """Draw an earth-mass quantity table as Rhino lines and centred text tags.

    ``table`` is a ``QuantityTable``; ``origin`` is the top-left ``(x, y, z)`` in
    document units; ``text_height`` is in document units. Column widths follow
    the longest cell, so the table scales with the text height. Returns
    ``(line_curves, text_tags)``.
    """

    rows = [tuple(table.header)] + [tuple(row) for row in table.rows]
    columns = len(table.header)
    char_width = 0.62 * text_height
    padding = 0.4 * text_height
    row_height = 1.8 * text_height
    column_widths = [
        max(len(rows[r][c]) for r in range(len(rows))) * char_width + 2.0 * padding
        for c in range(columns)
    ]

    origin_x, origin_y, origin_z = float(origin[0]), float(origin[1]), float(origin[2])
    z = origin_z + 0.02 * unit_scale
    total_width = sum(column_widths)
    total_height = row_height * len(rows)

    edges_x = [origin_x]
    for width in column_widths:
        edges_x.append(edges_x[-1] + width)

    lines = []
    for r in range(len(rows) + 1):
        y = origin_y - r * row_height
        lines.append(
            rg.LineCurve(
                rg.Point3d(origin_x, y, z), rg.Point3d(origin_x + total_width, y, z)
            )
        )
    for x in edges_x:
        lines.append(
            rg.LineCurve(
                rg.Point3d(x, origin_y, z), rg.Point3d(x, origin_y - total_height, z)
            )
        )

    tags = []
    text_z = z + 0.01 * unit_scale
    for r in range(len(rows)):
        center_y = origin_y - (r + 0.5) * row_height
        for c in range(columns):
            center_x = edges_x[c] + column_widths[c] / 2.0
            tags.append(
                _text_tag(rows[r][c], rg.Point3d(center_x, center_y, text_z), text_height)
            )
    return lines, tags
