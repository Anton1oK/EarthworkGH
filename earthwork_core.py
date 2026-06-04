"""Rhino-free earthwork calculations for the Grasshopper adapters."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Iterable, Sequence


Point2 = tuple[float, float]
ElevationSampler = Callable[[float, float], float]


@dataclass(frozen=True)
class DocumentUnits:
    """The model's length unit, resolved so calculations convert correctly.

    ``units_per_meter`` converts model lengths to metres (1000 for a millimetre
    model, 1 for metres, ~39.37 for inches). ``reliable`` is False when the unit
    system could not be read or the document is unitless; callers must WARN
    rather than silently assume 1 unit = 1 m (a 1000x error for a mm model).
    """

    units_per_meter: float
    meters_per_unit: float
    name: str
    label: str
    reliable: bool


# Metres-per-unit -> (human name, short label) for the common length units, so a
# document's unit can be recognised from its scale even if its name is missing.
_KNOWN_UNIT_SCALES = (
    (1.0, "Meters", "m"),
    (0.001, "Millimeters", "mm"),
    (0.01, "Centimeters", "cm"),
    (0.1, "Decimeters", "dm"),
    (1000.0, "Kilometers", "km"),
    (0.0254, "Inches", "in"),
    (0.3048, "Feet", "ft"),
    (0.9144, "Yards", "yd"),
    (1609.344, "Miles", "mi"),
)


def classify_units(meters_per_unit, system_name=None, reliable=True) -> DocumentUnits:
    """Resolve a metres-per-unit (and optional unit-system name) to DocumentUnits.

    Pure and Rhino-free so it can be unit-tested. When ``reliable`` is False or
    the scale is missing/non-positive, returns a metre fallback flagged
    ``reliable=False`` so the caller warns instead of computing wrong volumes.
    """

    try:
        mpu = float(meters_per_unit)
    except (TypeError, ValueError):
        mpu = 0.0

    # A positive scale is itself evidence of real units, so an omitted name is
    # fine; only an explicitly unitless system (the Rhino "None"/"Unset" case),
    # a non-positive scale, or reliable=False is untrustworthy.
    clean_name = (system_name or "").strip()
    unitless = clean_name.lower() in ("none", "unset", "no unit system")
    if not reliable or mpu <= 0.0 or unitless:
        return DocumentUnits(1.0, 1.0, clean_name or "unset", "?", False)

    name, label = clean_name, ""
    for scale, known_name, known_label in _KNOWN_UNIT_SCALES:
        if abs(mpu - scale) <= scale * 1e-6:
            label = known_label
            if not name:
                name = known_name
            break
    if not name:
        name = "{:g} m/unit".format(mpu)
    if not label:
        label = "{:g} m".format(mpu)
    return DocumentUnits(1.0 / mpu, mpu, name, label, True)


@dataclass(frozen=True)
class GridVertex:
    x: float
    y: float
    existing_z: float
    proposed_z: float

    @property
    def work_mark(self) -> float:
        return self.proposed_z - self.existing_z


@dataclass(frozen=True)
class EarthworkCell:
    column: int
    row: int
    corners: tuple[GridVertex, GridVertex, GridVertex, GridVertex]
    area_m2: float
    fill_m3: float
    cut_m3: float

    @property
    def net_m3(self) -> float:
        return self.fill_m3 - self.cut_m3

    @property
    def center(self) -> Point2:
        return (
            sum(vertex.x for vertex in self.corners) / 4.0,
            sum(vertex.y for vertex in self.corners) / 4.0,
        )

    @property
    def work_mark(self) -> float:
        if self.area_m2 <= 0.0:
            return 0.0
        return self.net_m3 / self.area_m2

    @property
    def classification(self) -> str:
        tolerance = 1e-9
        if self.fill_m3 > tolerance and self.cut_m3 > tolerance:
            return "mixed"
        if self.fill_m3 > tolerance:
            return "fill"
        if self.cut_m3 > tolerance:
            return "cut"
        return "zero"


@dataclass(frozen=True)
class ColumnTotal:
    column: int
    fill_m3: float
    cut_m3: float


@dataclass(frozen=True)
class CutFillResult:
    cells: tuple[EarthworkCell, ...]
    zero_work_segments: tuple[tuple[Point2, Point2], ...]
    column_totals: tuple[ColumnTotal, ...]
    grid_size_m: float
    fill_m3: float
    cut_m3: float

    @property
    def balance_m3(self) -> float:
        return self.fill_m3 - self.cut_m3


@dataclass(frozen=True)
class QuantityTable:
    """SPDS earth-mass quantity table: header plus pre-formatted string rows."""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def render_text(self) -> str:
        """Render the table as aligned monospace text for a panel."""

        all_rows = [self.header, *self.rows]
        widths = [
            max(len(row[column]) for row in all_rows)
            for column in range(len(self.header))
        ]
        return "\n".join(
            "  ".join(cell.rjust(widths[column]) for column, cell in enumerate(row))
            for row in all_rows
        )


def _format_m3(value: float) -> str:
    """Format a cubic-metre figure, collapsing tiny noise (and -0.0) to 0.00."""

    rounded = round(float(value), 2) + 0.0
    return "{:.2f}".format(rounded)


def calculate_cut_fill(
    boundary: Sequence[Point2],
    existing_z: ElevationSampler,
    proposed_z: ElevationSampler,
    grid_size_m: float = 20.0,
    samples_per_side: int = 6,
    origin: Point2 | None = None,
    units_per_meter: float = 1.0,
    flat_tolerance_m: float = 0.005,
) -> CutFillResult:
    """Calculate a square-grid earth-mass cartogram.

    Positive working marks are fill and negative working marks are cut.
    Cell quantities use evenly distributed subcell samples so mixed cut/fill
    cells and irregular site boundaries remain useful during concept design.

    Geometry inputs (``boundary`` and the samplers) are in document length
    units; ``units_per_meter`` converts those units to metres (e.g. 1000 for a
    millimetre model). Gridding stays in document units so the result geometry
    overlays the model, while ``grid_size_m`` and all reported volumes/areas are
    in metres and cubic/square metres.

    ``flat_tolerance_m`` is a flatness dead-band in metres: per-sample height
    differences smaller than it count as neither cut nor fill. This keeps
    sampling noise between two near-identical terrain meshes from painting
    untouched ground as shallow cut/fill.
    """

    polygon = normalize_polygon(boundary)
    grid_size_m = float(grid_size_m)
    if grid_size_m <= 0.0:
        raise ValueError("grid_size_m must be positive.")
    units_per_meter = float(units_per_meter)
    if units_per_meter <= 0.0:
        raise ValueError("units_per_meter must be positive.")
    flat_tolerance_m = float(flat_tolerance_m)
    if flat_tolerance_m < 0.0:
        raise ValueError("flat_tolerance_m must not be negative.")
    meters_per_unit = 1.0 / units_per_meter
    grid_size = grid_size_m * units_per_meter  # gridding works in document units
    sample_count = int(samples_per_side)
    if sample_count < 2:
        raise ValueError("samples_per_side must be at least 2.")

    min_x, min_y, max_x, max_y = polygon_bounds(polygon)
    if origin is None:
        origin_x = math.floor(min_x / grid_size) * grid_size
        origin_y = math.floor(min_y / grid_size) * grid_size
    else:
        origin_x = float(origin[0])
        origin_y = float(origin[1])

    column_start = int(math.floor((min_x - origin_x) / grid_size))
    column_end = int(math.ceil((max_x - origin_x) / grid_size))
    row_start = int(math.floor((min_y - origin_y) / grid_size))
    row_end = int(math.ceil((max_y - origin_y) / grid_size))

    cells: list[EarthworkCell] = []
    zero_segments: list[tuple[Point2, Point2]] = []
    sample_area_m2 = (
        grid_size * grid_size / float(sample_count * sample_count)
    ) * (meters_per_unit * meters_per_unit)

    for column in range(column_start, column_end):
        x0 = origin_x + column * grid_size
        for row in range(row_start, row_end):
            y0 = origin_y + row * grid_size

            fill = 0.0
            cut = 0.0
            included_samples = 0
            for sample_x_index in range(sample_count):
                x = x0 + (sample_x_index + 0.5) * grid_size / sample_count
                for sample_y_index in range(sample_count):
                    y = y0 + (sample_y_index + 0.5) * grid_size / sample_count
                    if not point_in_polygon((x, y), polygon):
                        continue
                    included_samples += 1
                    delta_m = (
                        float(proposed_z(x, y)) - float(existing_z(x, y))
                    ) * meters_per_unit
                    if abs(delta_m) < flat_tolerance_m:
                        continue  # within the flatness dead-band: untouched ground
                    if delta_m >= 0.0:
                        fill += delta_m * sample_area_m2
                    else:
                        cut += -delta_m * sample_area_m2

            # Only cells that overlap the site boundary contribute. Sample the
            # corner elevations after this check so cells that are wholly outside
            # the boundary never probe the terrain mesh - their corners may fall
            # far from an irregular mesh footprint and would otherwise abort.
            if included_samples == 0:
                continue

            corners_xy = (
                (x0, y0),
                (x0 + grid_size, y0),
                (x0 + grid_size, y0 + grid_size),
                (x0, y0 + grid_size),
            )
            corners = tuple(
                GridVertex(x, y, float(existing_z(x, y)), float(proposed_z(x, y)))
                for x, y in corners_xy
            )

            cell = EarthworkCell(
                column=column,
                row=row,
                corners=corners,  # type: ignore[arg-type]
                area_m2=included_samples * sample_area_m2,
                fill_m3=fill,
                cut_m3=cut,
            )
            cells.append(cell)
            # The zero-work line only runs through cells that hold both cut and
            # fill; flat or single-sign cells must not produce a line.
            if cell.classification == "mixed":
                zero_segments.extend(_cell_zero_segments(cell))

    column_map: dict[int, list[float]] = {}
    for cell in cells:
        totals = column_map.setdefault(cell.column, [0.0, 0.0])
        totals[0] += cell.fill_m3
        totals[1] += cell.cut_m3

    return CutFillResult(
        cells=tuple(cells),
        zero_work_segments=tuple(zero_segments),
        column_totals=tuple(
            ColumnTotal(column, totals[0], totals[1])
            for column, totals in sorted(column_map.items())
        ),
        grid_size_m=grid_size_m,
        fill_m3=sum(cell.fill_m3 for cell in cells),
        cut_m3=sum(cell.cut_m3 for cell in cells),
    )


def graded_pad_elevation(
    existing_z: float,
    inside_pad: bool,
    distance_to_pad_m: float,
    pad_elevation_m: float,
    slope_ratio: float,
) -> float:
    """Return terrain elevation for a flat pad with a `1:m` transition slope."""

    if slope_ratio <= 0.0:
        raise ValueError("slope_ratio must be positive.")
    if inside_pad:
        return float(pad_elevation_m)
    delta = max(0.0, float(distance_to_pad_m)) / float(slope_ratio)
    lower = float(pad_elevation_m) - delta
    upper = float(pad_elevation_m) + delta
    return min(max(float(existing_z), lower), upper)


def grade_pad_grid(
    existing_z: ElevationSampler,
    inside_pad_at: Callable[[float, float], bool],
    distance_to_pad_at: Callable[[float, float], float],
    origin: Point2,
    columns: int,
    rows: int,
    spacing: float,
    pad_elevation_m: float,
    slope_ratio: float,
) -> tuple[list[tuple[float, float, float]], int]:
    """Resample existing terrain onto a regular grid and apply pad grading.

    Returns a row-major list of ``(columns + 1) x (rows + 1)`` ``(x, y, z)``
    points plus the count whose elevation differs from the existing surface.
    The flat pad, transition slope and untouched ground come out at a uniform
    resolution regardless of how irregular the source mesh is. All coordinates
    are in document units; the boundary callbacks decide pad membership and the
    horizontal distance to the boundary.
    """

    if columns < 1 or rows < 1:
        raise ValueError("Pad grid needs at least one column and one row.")
    if spacing <= 0.0:
        raise ValueError("Pad grid spacing must be positive.")

    origin_x, origin_y = float(origin[0]), float(origin[1])
    points: list[tuple[float, float, float]] = []
    edited = 0
    for row in range(rows + 1):
        y = origin_y + row * spacing
        for column in range(columns + 1):
            x = origin_x + column * spacing
            ground = float(existing_z(x, y))
            elevation = graded_pad_elevation(
                existing_z=ground,
                inside_pad=bool(inside_pad_at(x, y)),
                distance_to_pad_m=float(distance_to_pad_at(x, y)),
                pad_elevation_m=pad_elevation_m,
                slope_ratio=slope_ratio,
            )
            if abs(elevation - ground) > 1e-9:
                edited += 1
            points.append((x, y, elevation))
    return points, edited


def frost_depth(soil_d0: float, freezing_index: float) -> float:
    """Normative seasonal freezing depth dfn = d0 * sqrt(Mt).

    ``soil_d0`` is the soil coefficient (metres) and ``freezing_index`` is the
    absolute sum of mean monthly negative temperatures (Mt). Pure formula; the
    soil coefficient and the design factor come from the active standard.
    """

    soil_d0 = float(soil_d0)
    freezing_index = float(freezing_index)
    if soil_d0 <= 0.0:
        raise ValueError("soil_d0 must be positive.")
    if freezing_index < 0.0:
        raise ValueError("freezing_index must not be negative.")
    return soil_d0 * math.sqrt(freezing_index)


def platform_cut_fill(ground_elevations, cell_area, platform_z):
    """Cut and fill volumes to bring a sampled ground to a flat platform.

    ``ground_elevations`` is one elevation per grid node (same length unit as
    ``platform_z``); ``cell_area`` is the area each node represents. Returns
    ``(cut, fill)`` in those units cubed.
    """

    cut = 0.0
    fill = 0.0
    for ground in ground_elevations:
        delta = float(ground) - float(platform_z)
        if delta > 0.0:
            cut += delta * cell_area
        else:
            fill += -delta * cell_area
    return cut, fill


def balanced_platform(ground_elevations):
    """The flat platform elevation that balances cut and fill (neat, area-mean)."""

    values = [float(g) for g in ground_elevations]
    if not values:
        raise ValueError("Need at least one ground elevation.")
    return sum(values) / len(values)


def mass_haul_curve(ground_elevations, cell_area, platform_levels):
    """Sweep platform levels, returning ``(level, cut, fill, net)`` per level."""

    rows = []
    for level in platform_levels:
        cut, fill = platform_cut_fill(ground_elevations, cell_area, level)
        rows.append((float(level), cut, fill, cut - fill))
    return tuple(rows)


@dataclass(frozen=True)
class PathGrade:
    from_distance: float
    to_distance: float
    grade_percent: float


@dataclass(frozen=True)
class PathProfile:
    grades: tuple[PathGrade, ...]
    max_abs_grade_percent: float
    length: float


def path_grades(stations) -> PathProfile:
    """Longitudinal grades along a driveway/path centreline.

    ``stations`` is ``(distance, z)`` along the centreline; the grade of each
    segment is ``dz/ddistance * 100`` (percent, so unit-independent). The result
    carries the steepest absolute grade for a compliance check.
    """

    rows = [(float(d), float(z)) for d, z in stations]
    if len(rows) < 2:
        raise ValueError("A path needs at least two stations.")
    grades = []
    for (d0, z0), (d1, z1) in zip(rows, rows[1:]):
        span = d1 - d0
        grade = 0.0 if abs(span) < 1e-12 else (z1 - z0) / span * 100.0
        grades.append(PathGrade(d0, d1, grade))
    max_abs = max(abs(g.grade_percent) for g in grades)
    return PathProfile(tuple(grades), max_abs, rows[-1][0] - rows[0][0])


def grade_by_points(
    design_points,
    origin: Point2,
    columns: int,
    rows: int,
    spacing: float,
    power: float = 2.0,
    datum: float = 0.0,
):
    """Interpolate design spot elevations into a regular grading-surface grid.

    ``design_points`` are ``(x, y, z)`` finished elevations the engineer places.
    Each grid node takes the inverse-distance-weighted elevation of those points
    (exact at a coincident point), plus ``datum`` - a global vertical shift, e.g.
    the building +-0.000. Returns a row-major ``(columns+1) x (rows+1)`` list of
    ``(x, y, z)``. All values share one length unit.
    """

    points = [(float(x), float(y), float(z)) for x, y, z in design_points]
    if not points:
        raise ValueError("grade_by_points needs at least one design point.")
    if columns < 1 or rows < 1:
        raise ValueError("Grading grid needs at least one column and one row.")
    if spacing <= 0.0:
        raise ValueError("Grading grid spacing must be positive.")

    origin_x, origin_y = float(origin[0]), float(origin[1])
    power = float(power)
    datum = float(datum)
    grid = []
    for j in range(rows + 1):
        y = origin_y + j * spacing
        for i in range(columns + 1):
            x = origin_x + i * spacing
            exact = None
            numerator = 0.0
            denominator = 0.0
            for px, py, pz in points:
                distance_sq = (x - px) ** 2 + (y - py) ** 2
                if distance_sq < 1e-12:
                    exact = pz
                    break
                weight = 1.0 / (distance_sq ** (power / 2.0))
                numerator += weight * pz
                denominator += weight
            z = (exact if exact is not None else numerator / denominator) + datum
            grid.append((x, y, z))
    return grid


OptionalSampler = Callable[[float, float], "float | None"]


@dataclass(frozen=True)
class SlopeAnalysis:
    """Slope hachures and the outline of the sloped region, in XY."""

    hachures: tuple[tuple[Point2, Point2], ...]
    outline: tuple[tuple[Point2, Point2], ...]
    max_steepness: float
    min_steepness: float
    slope_cell_count: int

    @property
    def max_slope_1_to(self) -> float:
        """Steepest slope as the `m` in `1:m` (0.0 when effectively flat)."""

        if self.max_steepness <= 1e-9:
            return 0.0
        return 1.0 / self.max_steepness


def analyze_slopes(
    sampler: OptionalSampler,
    origin: Point2,
    columns: int,
    rows: int,
    spacing: float,
    min_steepness: float = 0.2,
    hachure_length: float | None = None,
    inside: Callable[[float, float], bool] | None = None,
) -> SlopeAnalysis:
    """Find slope faces on a sampled surface and build hachures for them.

    The surface is read on a ``columns x rows`` grid from ``origin`` at ``spacing``
    (document units). ``sampler(x, y)`` returns an elevation or ``None`` off the
    mesh. A cell is a slope when its gradient magnitude (rise/run, so unit-free)
    is at least ``min_steepness``; each such cell gets a downhill hachure of
    alternating length, and the boundary between slope and non-slope cells forms
    the slope outline (top and toe of the slope). ``inside`` optionally restricts
    cells to a boundary.
    """

    origin_x, origin_y = float(origin[0]), float(origin[1])
    spacing = float(spacing)
    if columns < 1 or rows < 1:
        raise ValueError("Slope grid needs at least one column and one row.")
    if spacing <= 0.0:
        raise ValueError("Slope grid spacing must be positive.")
    if hachure_length is None:
        hachure_length = spacing * 0.8

    slope_cells: dict[tuple[int, int], tuple[float, float, float, float]] = {}
    max_steepness = 0.0
    for row in range(rows):
        for column in range(columns):
            x0 = origin_x + column * spacing
            y0 = origin_y + row * spacing
            z00 = sampler(x0, y0)
            z10 = sampler(x0 + spacing, y0)
            z01 = sampler(x0, y0 + spacing)
            z11 = sampler(x0 + spacing, y0 + spacing)
            if z00 is None or z10 is None or z01 is None or z11 is None:
                continue
            center_x = x0 + spacing * 0.5
            center_y = y0 + spacing * 0.5
            if inside is not None and not inside(center_x, center_y):
                continue
            gradient_x = ((z10 + z11) - (z00 + z01)) / (2.0 * spacing)
            gradient_y = ((z01 + z11) - (z00 + z10)) / (2.0 * spacing)
            steepness = math.hypot(gradient_x, gradient_y)
            if steepness > max_steepness:
                max_steepness = steepness
            if steepness < min_steepness:
                continue
            inverse = 1.0 / steepness
            slope_cells[(column, row)] = (
                center_x,
                center_y,
                -gradient_x * inverse,
                -gradient_y * inverse,
            )

    hachures: list[tuple[Point2, Point2]] = []
    for (column, row), (center_x, center_y, down_x, down_y) in slope_cells.items():
        x0 = origin_x + column * spacing
        y0 = origin_y + row * spacing
        length = hachure_length if (column + row) % 2 == 0 else hachure_length * 0.5
        # The top edge (crest) is a cell side whose neighbour is non-slope AND
        # uphill. Hang a downhill tick off each such edge midpoint, so the ticks
        # sit on the crest of the slope and point down it - the slope convention -
        # instead of floating mid-slope.
        edges = (
            ((1, 0), (x0 + spacing, center_y)),
            ((-1, 0), (x0, center_y)),
            ((0, 1), (center_x, y0 + spacing)),
            ((0, -1), (center_x, y0)),
        )
        for (dx, dy), midpoint in edges:
            if (column + dx, row + dy) in slope_cells:
                continue
            if -(dx * down_x + dy * down_y) <= 1e-9:
                continue  # neighbour is downhill (the toe), not the crest
            hachures.append(
                (
                    midpoint,
                    (midpoint[0] + down_x * length, midpoint[1] + down_y * length),
                )
            )

    outline: list[tuple[Point2, Point2]] = []
    for (column, row) in slope_cells:
        x0 = origin_x + column * spacing
        y0 = origin_y + row * spacing
        if (column + 1, row) not in slope_cells:
            outline.append(((x0 + spacing, y0), (x0 + spacing, y0 + spacing)))
        if (column - 1, row) not in slope_cells:
            outline.append(((x0, y0), (x0, y0 + spacing)))
        if (column, row + 1) not in slope_cells:
            outline.append(((x0, y0 + spacing), (x0 + spacing, y0 + spacing)))
        if (column, row - 1) not in slope_cells:
            outline.append(((x0, y0), (x0 + spacing, y0)))

    return SlopeAnalysis(
        hachures=tuple(hachures),
        outline=tuple(outline),
        max_steepness=max_steepness,
        min_steepness=float(min_steepness),
        slope_cell_count=len(slope_cells),
    )


@dataclass(frozen=True)
class SlopeSample:
    """One relief sample: centre, elevation, downhill direction and steepness."""

    x: float
    y: float
    z: float
    downhill_x: float
    downhill_y: float
    steepness: float


def slope_field(
    sampler: OptionalSampler,
    origin: Point2,
    columns: int,
    rows: int,
    spacing: float,
    inside: Callable[[float, float], bool] | None = None,
) -> tuple[SlopeSample, ...]:
    """Sample the surface gradient at every grid cell centre for a relief preview.

    ``sampler(x, y)`` returns an elevation or ``None`` off the mesh. Returns a
    ``SlopeSample`` per cell whose four corners resolve (and whose centre is
    inside ``inside`` if given), with the mean elevation, the downhill unit
    direction (zero on flat ground) and the steepness (rise/run).
    """

    origin_x, origin_y = float(origin[0]), float(origin[1])
    spacing = float(spacing)
    if columns < 1 or rows < 1:
        raise ValueError("Slope field needs at least one column and one row.")
    if spacing <= 0.0:
        raise ValueError("Slope field spacing must be positive.")

    samples: list[SlopeSample] = []
    for row in range(rows):
        for column in range(columns):
            x0 = origin_x + column * spacing
            y0 = origin_y + row * spacing
            z00 = sampler(x0, y0)
            z10 = sampler(x0 + spacing, y0)
            z01 = sampler(x0, y0 + spacing)
            z11 = sampler(x0 + spacing, y0 + spacing)
            if z00 is None or z10 is None or z01 is None or z11 is None:
                continue
            center_x = x0 + spacing * 0.5
            center_y = y0 + spacing * 0.5
            if inside is not None and not inside(center_x, center_y):
                continue
            center_z = 0.25 * (z00 + z10 + z01 + z11)
            gradient_x = ((z10 + z11) - (z00 + z01)) / (2.0 * spacing)
            gradient_y = ((z01 + z11) - (z00 + z10)) / (2.0 * spacing)
            steepness = math.hypot(gradient_x, gradient_y)
            if steepness > 1e-12:
                down_x = -gradient_x / steepness
                down_y = -gradient_y / steepness
            else:
                down_x = down_y = 0.0
            samples.append(
                SlopeSample(center_x, center_y, center_z, down_x, down_y, steepness)
            )
    return tuple(samples)


@dataclass(frozen=True)
class DrainagePoint:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class DrainageAnalysis:
    low_points: tuple[DrainagePoint, ...]
    high_points: tuple[DrainagePoint, ...]
    flow_paths: tuple[tuple[Point2, ...], ...]


_NEIGHBORS8 = (
    (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1),
)


def _trace_descent(start, nodes, origin, spacing):
    """Walk D8 steepest descent from a node to a sink/flat.

    Returns ``(x, y, z)`` points (elevation carried from the node grid) so callers
    never have to re-sample the mesh to drape the path.
    """

    origin_x, origin_y = origin
    i, j = start
    path = []
    seen = set()
    while (i, j) not in seen:
        seen.add((i, j))
        z = nodes.get((i, j))
        if z is None:
            break
        path.append((origin_x + i * spacing, origin_y + j * spacing, z))
        best = None
        best_slope = 0.0
        for di, dj in _NEIGHBORS8:
            nz = nodes.get((i + di, j + dj))
            if nz is None:
                continue
            slope = (z - nz) / math.hypot(di, dj)
            if slope > best_slope + 1e-12:
                best_slope = slope
                best = (i + di, j + dj)
        if best is None:
            break
        i, j = best
    return tuple(path)


def drainage_analysis(
    sampler: OptionalSampler,
    origin: Point2,
    columns: int,
    rows: int,
    spacing: float,
    inside: Callable[[float, float], bool] | None = None,
    seed_every: int = 3,
) -> DrainageAnalysis:
    """Flow traces and local extrema of a sampled surface (D8 drainage).

    Samples a node grid, marks strict local minima (sinks where water ponds) and
    maxima (peaks), and traces steepest-descent flow paths from seed nodes spaced
    ``seed_every`` apart. ``sampler(x, y)`` returns an elevation or ``None``; an
    ``inside`` predicate optionally restricts to a boundary.
    """

    origin_x, origin_y = float(origin[0]), float(origin[1])
    spacing = float(spacing)
    if columns < 1 or rows < 1:
        raise ValueError("Drainage grid needs at least one column and one row.")
    if spacing <= 0.0:
        raise ValueError("Drainage grid spacing must be positive.")
    seed_every = max(1, int(seed_every))

    nodes = {}
    for j in range(rows + 1):
        for i in range(columns + 1):
            x = origin_x + i * spacing
            y = origin_y + j * spacing
            z = sampler(x, y)
            if z is not None and (inside is None or inside(x, y)):
                nodes[(i, j)] = z

    lows = []
    highs = []
    for (i, j), z in nodes.items():
        neighbours = [
            nodes[(i + di, j + dj)]
            for di, dj in _NEIGHBORS8
            if (i + di, j + dj) in nodes
        ]
        if not neighbours:
            continue
        if all(z < nz - 1e-9 for nz in neighbours):
            lows.append(DrainagePoint(origin_x + i * spacing, origin_y + j * spacing, z))
        elif all(z > nz + 1e-9 for nz in neighbours):
            highs.append(DrainagePoint(origin_x + i * spacing, origin_y + j * spacing, z))

    paths = []
    for (i, j) in nodes:
        if i % seed_every or j % seed_every:
            continue
        path = _trace_descent((i, j), nodes, (origin_x, origin_y), spacing)
        if len(path) >= 2:
            paths.append(path)

    return DrainageAnalysis(tuple(lows), tuple(highs), tuple(paths))


@dataclass(frozen=True)
class DitchStation:
    distance: float
    ground_z: float
    invert_z: float
    depth: float


@dataclass(frozen=True)
class DitchProfile:
    stations: tuple[DitchStation, ...]
    min_depth: float
    max_depth: float
    daylight_count: int  # stations where the invert is at or above ground


def ditch_profile(
    ground_stations,
    depth=0.5,
    start_invert=None,
    longitudinal_slope=0.0,
):
    """Compute a ditch/swale invert along a centreline.

    ``ground_stations`` is ``(distance, ground_z)`` in document units. With
    ``start_invert`` unset the invert follows the ground at a constant ``depth``;
    otherwise it runs from ``start_invert`` at ``longitudinal_slope`` (fall per
    unit length, dimensionless). ``daylight_count`` flags stations where the
    invert reaches or rises above the ground (an invalid/fill condition).
    """

    rows = [(float(d), float(gz)) for d, gz in ground_stations]
    if len(rows) < 2:
        raise ValueError("A ditch needs at least two ground stations.")

    base = rows[0][0]
    stations = []
    daylight = 0
    for distance, ground_z in rows:
        if start_invert is None:
            invert_z = ground_z - float(depth)
        else:
            invert_z = float(start_invert) - float(longitudinal_slope) * (distance - base)
        channel_depth = ground_z - invert_z
        if channel_depth <= 1e-9:
            daylight += 1
        stations.append(DitchStation(distance, ground_z, invert_z, channel_depth))

    depths = [s.depth for s in stations]
    return DitchProfile(tuple(stations), min(depths), max(depths), daylight)


def ditch_volume(profile: DitchProfile, bottom_width: float, side_slope: float) -> float:
    """Trapezoidal channel excavation volume by average end area.

    Cross-section area at depth ``h`` is ``bottom_width*h + side_slope*h^2`` (side
    slope ``1:side_slope``), counted only where ``h > 0``. ``bottom_width`` and the
    profile depths share the same length unit; the volume is in that unit cubed.
    """

    bottom_width = float(bottom_width)
    side_slope = float(side_slope)

    def area(depth):
        depth = max(0.0, depth)
        return bottom_width * depth + side_slope * depth * depth

    volume = 0.0
    for s0, s1 in zip(profile.stations, profile.stations[1:]):
        span = s1.distance - s0.distance
        volume += 0.5 * (area(s0.depth) + area(s1.depth)) * span
    return volume


def _cell_contour(level, x0, y0, spacing, z00, z10, z11, z01):
    """Marching-squares iso-segments for one cell at a given level."""

    values = (z00 - level, z10 - level, z11 - level, z01 - level)
    points = (
        (x0, y0),
        (x0 + spacing, y0),
        (x0 + spacing, y0 + spacing),
        (x0, y0 + spacing),
    )
    crossings = []
    for index in range(4):
        nxt = (index + 1) % 4
        a, b = values[index], values[nxt]
        if (a > 0.0) == (b > 0.0) or a == b:
            continue
        ratio = a / (a - b)
        if 0.0 <= ratio <= 1.0:
            pa, pb = points[index], points[nxt]
            crossings.append(
                (pa[0] + ratio * (pb[0] - pa[0]), pa[1] + ratio * (pb[1] - pa[1]))
            )
    if len(crossings) == 2:
        return ((crossings[0], crossings[1]),)
    if len(crossings) == 4:
        return ((crossings[0], crossings[1]), (crossings[2], crossings[3]))
    return ()


def contour_segments(
    sampler: OptionalSampler,
    origin: Point2,
    columns: int,
    rows: int,
    spacing: float,
    interval: float,
    base: float = 0.0,
    inside: Callable[[float, float], bool] | None = None,
) -> tuple[tuple[float, Point2, Point2], ...]:
    """Marching-squares contour segments of a sampled surface.

    Samples elevations on the ``(columns+1) x (rows+1)`` corner grid, then emits
    ``(level, start, end)`` segments at every ``interval`` step (aligned to
    ``base``) within the surface's range. ``interval`` and elevations are in the
    same units as the sampler. Cells with any missing corner are skipped.
    """

    interval = float(interval)
    if interval <= 0.0:
        raise ValueError("Contour interval must be positive.")
    if columns < 1 or rows < 1:
        raise ValueError("Contour grid needs at least one column and one row.")

    origin_x, origin_y = float(origin[0]), float(origin[1])
    corners = {}
    for j in range(rows + 1):
        for i in range(columns + 1):
            corners[(i, j)] = sampler(origin_x + i * spacing, origin_y + j * spacing)

    elevations = [z for z in corners.values() if z is not None]
    if not elevations:
        return ()
    first = math.ceil((min(elevations) - base) / interval)
    last = math.floor((max(elevations) - base) / interval)

    segments = []
    for step in range(first, last + 1):
        level = base + step * interval
        for j in range(rows):
            for i in range(columns):
                z00 = corners[(i, j)]
                z10 = corners[(i + 1, j)]
                z11 = corners[(i + 1, j + 1)]
                z01 = corners[(i, j + 1)]
                if z00 is None or z10 is None or z11 is None or z01 is None:
                    continue
                x0 = origin_x + i * spacing
                y0 = origin_y + j * spacing
                if inside is not None and not inside(
                    x0 + spacing * 0.5, y0 + spacing * 0.5
                ):
                    continue
                for start, end in _cell_contour(level, x0, y0, spacing, z00, z10, z11, z01):
                    segments.append((level, start, end))
    return tuple(segments)


@dataclass(frozen=True)
class SectionDrawing:
    """A profile section: ground lines, cut/fill regions and cross areas.

    Points are ``(distance_along_line, elevation)`` in input units. Cut is where
    the existing ground is above the proposed (excavation); fill is the reverse.
    ``cut_area`` / ``fill_area`` are cross-sectional areas in input units squared.
    """

    existing_line: tuple[Point2, ...]
    proposed_line: tuple[Point2, ...]
    cut_regions: tuple[tuple[Point2, ...], ...]
    fill_regions: tuple[tuple[Point2, ...], ...]
    cut_area: float
    fill_area: float
    length: float
    min_z: float
    max_z: float


def _section_piece(cut_regions, fill_regions, d0, e0, p0, d1, e1, p1):
    """Add the cut/fill polygon for one single-sign segment; return its areas."""

    polygon = ((d0, p0), (d0, e0), (d1, e1), (d1, p1))
    signed = 0.5 * ((e0 - p0) + (e1 - p1)) * (d1 - d0)
    if signed > 1e-12:
        cut_regions.append(polygon)
        return signed, 0.0
    if signed < -1e-12:
        fill_regions.append(polygon)
        return 0.0, -signed
    return 0.0, 0.0


def build_section(
    stations: Sequence[tuple[float, float, "float | None"]]
) -> SectionDrawing:
    """Build a section drawing from sampled ``(distance, existing_z, proposed_z)``.

    ``proposed_z`` may be ``None`` (existing ground only). Where existing and
    proposed cross within a segment, the segment is split so each cut/fill region
    is a clean polygon and the areas stay exact.
    """

    rows = [
        (float(d), float(ez), (None if pz is None else float(pz)))
        for d, ez, pz in stations
    ]
    if len(rows) < 2:
        raise ValueError("A section needs at least two stations.")

    existing_line = tuple((d, ez) for d, ez, _pz in rows)
    has_proposed = all(pz is not None for _d, _ez, pz in rows)
    proposed_line = tuple((d, pz) for d, _ez, pz in rows) if has_proposed else ()

    cut_regions: list[tuple[Point2, ...]] = []
    fill_regions: list[tuple[Point2, ...]] = []
    cut_area = 0.0
    fill_area = 0.0
    if has_proposed:
        for (d0, e0, p0), (d1, e1, p1) in zip(rows, rows[1:]):
            diff0 = e0 - p0
            diff1 = e1 - p1
            if diff0 * diff1 < 0.0:  # existing and proposed cross in this span
                ratio = diff0 / (diff0 - diff1)
                dc = d0 + ratio * (d1 - d0)
                zc = e0 + ratio * (e1 - e0)
                cut, fill = _section_piece(cut_regions, fill_regions, d0, e0, p0, dc, zc, zc)
                cut_area += cut
                fill_area += fill
                cut, fill = _section_piece(cut_regions, fill_regions, dc, zc, zc, d1, e1, p1)
                cut_area += cut
                fill_area += fill
            else:
                cut, fill = _section_piece(cut_regions, fill_regions, d0, e0, p0, d1, e1, p1)
                cut_area += cut
                fill_area += fill

    elevations = [ez for _d, ez, _pz in rows]
    elevations += [pz for _d, _ez, pz in rows if pz is not None]
    return SectionDrawing(
        existing_line=existing_line,
        proposed_line=proposed_line,
        cut_regions=tuple(cut_regions),
        fill_regions=tuple(fill_regions),
        cut_area=cut_area,
        fill_area=fill_area,
        length=rows[-1][0] - rows[0][0],
        min_z=min(elevations),
        max_z=max(elevations),
    )


@dataclass(frozen=True)
class SerialSectionResult:
    """Cut/fill volumes from a row of cross-sections (average end area)."""

    stations: tuple[tuple[float, float, float], ...]  # (distance, cut_area, fill_area)
    cut_volume: float
    fill_volume: float


def serial_section_volumes(
    area_stations: Sequence[tuple[float, float, float]]
) -> SerialSectionResult:
    """Volumes between cross-sections by the average-end-area method.

    ``area_stations`` is ``(distance, cut_area, fill_area)`` per station, sorted
    by distance, in metres and square metres; volumes come back in cubic metres.
    Between two stations the volume is the mean of their areas times the gap.
    """

    rows = [(float(d), float(cut), float(fill)) for d, cut, fill in area_stations]
    if not rows:
        raise ValueError("Serial sections need at least one station.")
    rows.sort(key=lambda row: row[0])

    cut_volume = 0.0
    fill_volume = 0.0
    for (d0, cut0, fill0), (d1, cut1, fill1) in zip(rows, rows[1:]):
        span = d1 - d0
        cut_volume += 0.5 * (cut0 + cut1) * span
        fill_volume += 0.5 * (fill0 + fill1) * span
    return SerialSectionResult(tuple(rows), cut_volume, fill_volume)


@dataclass(frozen=True)
class TopsoilStrip:
    """Topsoil stripping quantity for an area at a strip depth."""

    area_m2: float
    strip_depth_m: float
    volume_m3: float


def topsoil_strip(
    boundary: Sequence[Point2],
    strip_depth_m: float,
    units_per_meter: float = 1.0,
) -> TopsoilStrip:
    """Topsoil volume to strip = plan area times strip depth.

    ``boundary`` is in document units; ``strip_depth_m`` is in metres. The area
    and volume come back in square and cubic metres.
    """

    polygon = normalize_polygon(boundary)
    meters_per_unit = 1.0 / float(units_per_meter)
    area_m2 = abs(polygon_area(polygon)) * meters_per_unit * meters_per_unit
    depth = float(strip_depth_m)
    if depth < 0.0:
        raise ValueError("strip_depth_m must not be negative.")
    return TopsoilStrip(area_m2=area_m2, strip_depth_m=depth, volume_m3=area_m2 * depth)


def hatch_polygon(
    boundary: Sequence[Point2],
    spacing: float,
    angle_deg: float = 45.0,
) -> tuple[tuple[Point2, Point2], ...]:
    """Fill a polygon with parallel hatch segments clipped to its outline.

    Returns ``(start, end)`` segments at ``angle_deg`` spaced ``spacing`` apart
    (document units). Works for convex and simple concave polygons via even-odd
    interval pairing along each scan line.
    """

    polygon = normalize_polygon(boundary)
    spacing = float(spacing)
    if spacing <= 0.0:
        raise ValueError("Hatch spacing must be positive.")

    angle = math.radians(angle_deg)
    dir_x, dir_y = math.cos(angle), math.sin(angle)
    normal_x, normal_y = -dir_y, dir_x
    offsets = [px * normal_x + py * normal_y for px, py in polygon]
    projections = [px * dir_x + py * dir_y for px, py in polygon]
    offset = math.ceil(min(offsets) / spacing) * spacing
    proj_min, proj_max = min(projections) - spacing, max(projections) + spacing

    segments: list[tuple[Point2, Point2]] = []
    while offset <= max(offsets) + 1e-9:
        base_x, base_y = offset * normal_x, offset * normal_y
        a = (base_x + proj_min * dir_x, base_y + proj_min * dir_y)
        b = (base_x + proj_max * dir_x, base_y + proj_max * dir_y)
        params = sorted(_line_polygon_params(a, b, polygon))
        for index in range(0, len(params) - 1, 2):
            t0, t1 = params[index], params[index + 1]
            if t1 - t0 <= 1e-9:
                continue
            segments.append(
                (
                    (a[0] + t0 * (b[0] - a[0]), a[1] + t0 * (b[1] - a[1])),
                    (a[0] + t1 * (b[0] - a[0]), a[1] + t1 * (b[1] - a[1])),
                )
            )
        offset += spacing
    return tuple(segments)


def _line_polygon_params(a: Point2, b: Point2, polygon: Sequence[Point2]) -> list[float]:
    params: list[float] = []
    count = len(polygon)
    for index in range(count):
        param = _line_segment_param(a, b, polygon[index], polygon[(index + 1) % count])
        if param is not None:
            params.append(param)
    return params


def _line_segment_param(a: Point2, b: Point2, c: Point2, d: Point2) -> "float | None":
    """Parameter t in [0, 1] along a->b where it crosses segment c->d, or None."""

    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-12:
        return None
    t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / denominator
    u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / denominator
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
        return min(1.0, max(0.0, t))
    return None


def normalize_polygon(points: Sequence[Point2]) -> tuple[Point2, ...]:
    result = [(float(x), float(y)) for x, y in points]
    if len(result) >= 2 and _near(result[0], result[-1]):
        result.pop()
    if len(result) < 3:
        raise ValueError("Boundary polygon needs at least three distinct points.")
    if abs(polygon_area(result)) <= 1e-12:
        raise ValueError("Boundary polygon area must be greater than zero.")
    return tuple(result)


def polygon_bounds(points: Sequence[Point2]) -> tuple[float, float, float, float]:
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def polygon_area(points: Sequence[Point2]) -> float:
    return 0.5 * sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )


def points_to_csv(points, delimiter=",", decimals=3):
    """Format ``(x, y, z)`` points as delimited text with period decimals.

    Neutral of any locale: always a period decimal separator, so the output is a
    valid Revit / Civil points file regardless of the regional settings.
    """

    pattern = "{:." + str(int(decimals)) + "f}"
    lines = []
    for point in points:
        lines.append(delimiter.join(pattern.format(float(value)) for value in point[:3]))
    return "\n".join(lines)


@dataclass(frozen=True)
class SoilBalance:
    cut_bank_m3: float          # excavation, in-situ (bank) volume
    fill_compacted_m3: float    # design fill, compacted in place
    bank_for_fill_m3: float     # bank volume needed to make the compacted fill
    surplus_bank_m3: float      # + export, - import (bank)
    import_bank_m3: float
    export_bank_m3: float
    cut_loose_m3: float         # excavated soil handled loose (for haul)
    import_loose_m3: float
    export_loose_m3: float


def soil_balance(
    cut_bank_m3: float,
    fill_compacted_m3: float,
    initial_bulking: float = 1.2,
    residual_bulking: float = 1.05,
) -> SoilBalance:
    """Earthwork soil balance accounting for bulking and compaction.

    ``initial_bulking`` (Kp) is loose/bank; ``residual_bulking`` (Kor) is
    compacted/bank. Cut is measured in bank, design fill in compacted volume. The
    bank needed for the fill is ``fill / Kor``; the surplus (or deficit) of bank
    is exported (or imported). Haul volumes are loose (bank x Kp).
    """

    cut_bank_m3 = float(cut_bank_m3)
    fill_compacted_m3 = float(fill_compacted_m3)
    kp = float(initial_bulking)
    kor = float(residual_bulking)
    if kp <= 0.0 or kor <= 0.0:
        raise ValueError("Bulking factors must be positive.")
    if cut_bank_m3 < 0.0 or fill_compacted_m3 < 0.0:
        raise ValueError("Cut and fill volumes must not be negative.")

    bank_for_fill = fill_compacted_m3 / kor
    surplus_bank = cut_bank_m3 - bank_for_fill
    import_bank = max(0.0, -surplus_bank)
    export_bank = max(0.0, surplus_bank)
    return SoilBalance(
        cut_bank_m3=cut_bank_m3,
        fill_compacted_m3=fill_compacted_m3,
        bank_for_fill_m3=bank_for_fill,
        surplus_bank_m3=surplus_bank,
        import_bank_m3=import_bank,
        export_bank_m3=export_bank,
        cut_loose_m3=cut_bank_m3 * kp,
        import_loose_m3=import_bank * kp,
        export_loose_m3=export_bank * kp,
    )


@dataclass(frozen=True)
class AreaItem:
    key: str
    area_m2: float
    percent: float


def area_balance(plot_area_m2, item_areas, free_key="free"):
    """Site area balance: each item's share of the plot, plus a free remainder.

    ``item_areas`` is a list of ``(key, area)``; the remainder of the plot is
    appended under ``free_key``. Returns ``AreaItem`` with percentages.
    """

    plot = float(plot_area_m2)
    if plot <= 0.0:
        raise ValueError("Plot area must be positive.")
    items = [(str(key), float(area)) for key, area in item_areas]
    used = sum(area for _key, area in items)
    items.append((free_key, plot - used))
    return tuple(AreaItem(key, area, area / plot * 100.0) for key, area in items)


@dataclass(frozen=True)
class BillItem:
    name: str
    volume_m3: float


def bill_of_quantities(items: Sequence["tuple[str, float]"]) -> tuple[BillItem, ...]:
    """Normalise (name, volume) pairs into a bill, dropping empty rows."""

    rows = []
    for name, volume in items:
        volume = float(volume)
        if abs(volume) < 1e-9:
            continue
        rows.append(BillItem(str(name), volume))
    return tuple(rows)


def polygon_perimeter(points: Sequence[Point2]) -> float:
    polygon = normalize_polygon(points)
    count = len(polygon)
    return sum(
        math.hypot(
            polygon[(index + 1) % count][0] - polygon[index][0],
            polygon[(index + 1) % count][1] - polygon[index][1],
        )
        for index in range(count)
    )


def working_space_area(perimeter_m: float, working_space_m: float) -> float:
    """Plan area added by offsetting a footprint outward by a working width.

    Uses the Minkowski (rounded-corner) estimate ``perimeter*w + pi*w^2``, so it
    is a close, conservative approximation of the excavation-bottom annulus
    regardless of corner shape. Units are metres / square metres.
    """

    width = float(working_space_m)
    if width < 0.0:
        raise ValueError("working_space_m must not be negative.")
    return float(perimeter_m) * width + math.pi * width * width


@dataclass(frozen=True)
class BackfillLayer:
    index: int
    bottom_m: float
    top_m: float
    thickness_m: float


def backfill_layers(fill_depth_m: float, lift_thickness_m: float) -> tuple[BackfillLayer, ...]:
    """Split a backfill depth into compacted lifts, bottom to top.

    The last lift takes the remainder, so no lift exceeds ``lift_thickness_m``.
    """

    fill_depth_m = float(fill_depth_m)
    lift = float(lift_thickness_m)
    if fill_depth_m < 0.0:
        raise ValueError("fill_depth_m must not be negative.")
    if lift <= 0.0:
        raise ValueError("lift_thickness_m must be positive.")

    layers: list[BackfillLayer] = []
    bottom = 0.0
    index = 1
    while bottom < fill_depth_m - 1e-9:
        top = min(bottom + lift, fill_depth_m)
        layers.append(BackfillLayer(index, bottom, top, top - bottom))
        bottom = top
        index += 1
    return tuple(layers)


@dataclass(frozen=True)
class BackfillEstimate:
    structure_area_m2: float
    excavation_area_m2: float
    annulus_area_m2: float
    bedding_volume_m3: float
    backfill_volume_m3: float
    layers: tuple[BackfillLayer, ...]


def estimate_backfill(
    structure_area_m2: float,
    perimeter_m: float,
    working_space_m: float,
    depth_m: float,
    bedding_thickness_m: float,
    lift_thickness_m: float,
) -> BackfillEstimate:
    """Bedding and working-space backfill quantities for a foundation.

    The excavation bottom is the structure footprint plus a working-space annulus
    around it. Bedding fills the whole excavation bottom; backfill fills the
    working-space annulus over ``depth_m`` and is placed in compacted lifts. All
    inputs are metres / square metres; volumes come back in cubic metres.
    """

    annulus = working_space_area(perimeter_m, working_space_m)
    excavation_area = float(structure_area_m2) + annulus
    bedding_volume = excavation_area * float(bedding_thickness_m)
    backfill_volume = annulus * float(depth_m)
    layers = backfill_layers(depth_m, lift_thickness_m)
    return BackfillEstimate(
        structure_area_m2=float(structure_area_m2),
        excavation_area_m2=excavation_area,
        annulus_area_m2=annulus,
        bedding_volume_m3=bedding_volume,
        backfill_volume_m3=backfill_volume,
        layers=layers,
    )


def point_in_polygon(point: Point2, polygon: Sequence[Point2]) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if _point_on_segment(point, previous, current):
            return True
        crosses = (y1 > y) != (y2 > y)
        if crosses:
            hit_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < hit_x:
                inside = not inside
        previous = current
    return inside


def _cell_zero_segments(cell: EarthworkCell) -> Iterable[tuple[Point2, Point2]]:
    """Interpolate the work-mark=0 contour across a cell's edges.

    A crossing is recorded only where adjacent corner work marks fall on opposite
    sides of zero (zero itself counts as non-positive), so flat cells and cells
    that sit wholly in cut or fill produce no line.
    """

    values = [corner.work_mark for corner in cell.corners]
    points = [(corner.x, corner.y) for corner in cell.corners]
    crossings: list[Point2] = []
    for index in range(4):
        next_index = (index + 1) % 4
        value_a = values[index]
        value_b = values[next_index]
        if (value_a > 0.0) == (value_b > 0.0) or value_a == value_b:
            continue
        ratio = value_a / (value_a - value_b)
        if ratio < 0.0 or ratio > 1.0:
            continue
        point_a = points[index]
        point_b = points[next_index]
        crossings.append(
            (
                point_a[0] + ratio * (point_b[0] - point_a[0]),
                point_a[1] + ratio * (point_b[1] - point_a[1]),
            )
        )
    unique = _unique_points(crossings)
    if len(unique) == 2:
        return ((unique[0], unique[1]),)
    if len(unique) == 4:
        return ((unique[0], unique[1]), (unique[2], unique[3]))
    return ()


def _unique_points(points: Iterable[Point2]) -> list[Point2]:
    result: list[Point2] = []
    for point in points:
        if not any(_near(point, existing) for existing in result):
            result.append(point)
    return result


def _near(a: Point2, b: Point2, tolerance: float = 1e-9) -> bool:
    return abs(a[0] - b[0]) <= tolerance and abs(a[1] - b[1]) <= tolerance


def _point_on_segment(
    point: Point2,
    start: Point2,
    end: Point2,
    tolerance: float = 1e-9,
) -> bool:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > tolerance:
        return False
    return (
        min(x1, x2) - tolerance <= px <= max(x1, x2) + tolerance
        and min(y1, y2) - tolerance <= py <= max(y1, y2) + tolerance
    )

