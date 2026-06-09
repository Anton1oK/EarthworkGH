# Component Reference

Every component, with its full inputs and outputs. All inputs use **item** access
(single value). In the input tables, **Req.** marks whether the input is required
(`yes`) or optional (`—`, has a default). Length inputs (grid sizes, depths,
widths, elevations) are entered in **metres** under RU/INT or **feet** under US;
volumes are reported in the active standard's unit (**m³** under RU/INT, **cubic
yards** under US). Inputs with a fixed option set come up as drop-downs that are
**standard-aware** (e.g. `soil_class` shows OSHA Type A/B/C under US). Most
drawing components have a
`bake` toggle that writes their output onto the active standard's SPDS layer
groups (see [Workflows](Workflows)). Reports are produced in the active standard's
language (`report_ru` for the default Russian standard).

Groups: [Setup](#setup) · [Earth-mass & cartogram](#earth-mass--cartogram) ·
[Excavation & slopes](#excavation--slopes) · [Sections](#sections) ·
[Relief & drainage](#relief--drainage) · [Design authoring](#design-authoring) ·
[Accounting & quantities](#accounting--quantities) ·
[Engineering checks](#engineering-checks) · [Sheets & exchange](#sheets--exchange)

---

## Setup

### gh_00_standard — select the country / standard

Sets which country's standard is active for every other component. The choice is
stored in `scriptcontext.sticky`, so it persists across components and recomputes;
recompute the downstream components after changing it.

| Input | Type | Req. | Description |
|---|---|---|---|
| `standard_code` | string | — | `RU`, `US` or `INT`; leave empty to read the current selection. |

| Output | Type | Description |
|---|---|---|
| `active_code` | string | Code of the active standard. |
| `active_name` | string | Human name of the active standard. |
| `available` | string (list) | `CODE - Name` for every registered standard. |
| `provenance` | string | Tool version + the active standard's regulation editions. |
| `status` | string | What was selected and a reminder to recompute. |

> **Model units are not a separate component.** Every component reads the active
> document's unit itself before calculating (mm/cm/m/inch/foot), and the
> volume-producing ones warn if the document is unitless. See
> [Home › Conventions](Home#conventions).

---

## Earth-mass & cartogram

### gh_01_cut_fill_cartogram — SPDS square-grid cut/fill

Calculates cut and fill on an SPDS square grid from existing and proposed terrain
meshes, and produces the cartogram drawing geometry and quantity table.

| Input | Type | Req. | Description |
|---|---|---|---|
| `boundary` | curve | yes | Closed site boundary. |
| `existing_mesh` | mesh | yes | Existing terrain mesh. |
| `proposed_mesh` | mesh | yes | Proposed terrain mesh. |
| `grid_size_m` | number | — | Square grid side in metres (default 20). |
| `samples_per_side` | number | — | Sub-samples per cell side (default 6). |
| `flat_tolerance_m` | number | — | Flatness dead-band; height differences below it read as untouched (default 0.005 m). |
| `bake` | boolean | — | Write the cartogram onto the SPDS layer group. |

| Output | Type | Description |
|---|---|---|
| `analysis_mesh` | mesh | Cut/fill preview mesh. |
| `grid_curves` | curve (list) | Square-grid lines. |
| `zero_work_lines` | curve (list) | Zero-work (balance) lines. |
| `cut_hatches` | curve (list) | 45° hatch on excavation cells. |
| `cell_volume_tags` | generic (list) | Per-cell volume text tags. |
| `vertex_mark_tags` | generic (list) | Corner elevation/work-mark text tags. |
| `column_totals` | generic (list) | Per-column fill/cut/balance. |
| `fill_m3`, `cut_m3`, `balance_m3` | number | Project totals (m³). |
| `report_ru` | string | Report (also flags an unreliable model unit). |
| `warnings` | string (list) | Off-grid / boundary / unit warnings. |
| `table_ru` | string | Earth-mass quantity table as text. |
| `bake_status` | string | Bake result. |

### gh_02_grade_pad — flat grading pad

Edits a terrain mesh by inserting a flat pad with `1:m` side slopes, resampled to
a regular grid so it is robust to irregular input meshes. The usual way to author
a `proposed_mesh` for `gh_01`.

| Input | Type | Req. | Description |
|---|---|---|---|
| `terrain_mesh` | mesh | yes | Existing terrain to edit. |
| `pad_boundary` | curve | yes | Footprint of the flat pad. |
| `pad_elevation_m` | number | yes | Pad level in metres. |
| `slope_ratio` | number | — | `1:m` side slope (default 1.5). |
| `resolution_m` | number | — | Resample grid size (default 0.5 m). |

| Output | Type | Description |
|---|---|---|
| `proposed_mesh` | mesh | Edited terrain with the pad. |
| `edited_vertex_count` | number | Vertices moved. |
| `report_ru` | string | Report. |
| `warnings` | string (list) | Warnings. |

---

## Excavation & slopes

### gh_03_slope_hachures — pit slope hachures

Draws crest-anchored slope hachures and a slope-extent outline from a terrain
mesh, with the steepest `1:m`. Geometry only.

| Input | Type | Req. | Description |
|---|---|---|---|
| `terrain_mesh` | mesh | yes | Mesh to read slopes from. |
| `boundary` | curve | — | Optional analysis boundary. |
| `grid_size_m` | number | — | Sampling grid (default 1.0 m). |
| `min_slope_1_to` | number | — | Only draw slopes steeper than `1:m` (default 5.0). |
| `hachure_length_m` | number | — | Hachure length. |
| `bake` | boolean | — | Write onto the excavation layer group. |

| Output | Type | Description |
|---|---|---|
| `slope_hachures` | curve (list) | Hachure ticks. |
| `slope_outline` | curve (list) | Slope-extent outline. |
| `max_slope_1_to` | number | Steepest slope as `1:m`. |
| `report_ru` | string | Report. |
| `bake_status` | string | Bake result. |

### gh_06_topsoil — topsoil-removal plan

Topsoil stripping surface and quantity over a boundary.

| Input | Type | Req. | Description |
|---|---|---|---|
| `boundary` | curve | yes | Strip area. |
| `existing_mesh` | mesh | — | For the strip surface. |
| `strip_depth_m` | number | — | Strip thickness (default 0.2 m). |
| `hatch_spacing_m` | number | — | Hatch spacing (default 1.0 m). |
| `bake` | boolean | — | Write onto the topsoil layer group. |

| Output | Type | Description |
|---|---|---|
| `strip_boundary` | curve | Strip outline. |
| `hatch_lines` | curve (list) | Strip hatch. |
| `label` | generic | Area/volume tag. |
| `area_m2` | number | Strip area. |
| `volume_m3` | number | Topsoil volume (m³). |
| `report_ru` | string | Report (flags an unreliable model unit). |
| `bake_status` | string | Bake result. |

### gh_07_slope_check — temporary-slope assessment aid

Compares a proposed temporary excavation slope against an allowable one (SP
45.13330.2017). **A working aid and checklist — it never certifies the slope** and
forces a review when groundwater, edge surcharge, or depth over 5 m apply.

| Input | Type | Req. | Description |
|---|---|---|---|
| `proposed_slope_1_to` | number | yes | Proposed slope as `1:m`. |
| `depth_m` | number | yes | Excavation depth. |
| `soil_class` | number | — | Soil class 1–6 (see [Standards](Standards#soil-classes)). |
| `allowable_slope_1_to` | number | — | Override the indicative allowable. |
| `groundwater` | boolean | — | Groundwater present → forces review. |
| `surcharge` | boolean | — | Edge surcharge present → forces review. |
| `geotech_confirmed` | boolean | — | Geotech inputs confirmed (required for "within allowable"). |

| Output | Type | Description |
|---|---|---|
| `status` | string | Verdict (in/over allowable, or review required). |
| `within_allowable` | boolean | Only true with confirmed geotech and no forcing condition. |
| `governing_allowable_1_to` | number | Allowable used (override or indicative). |
| `indicative_allowable_1_to` | number | From the depth/soil table. |
| `soil_name` | string | Soil name for the class. |
| `report_ru` | string | Report with the mandatory non-certification note. |

### gh_08_backfill — bedding, backfill & compaction schedule

Foundation working-space offset, bedding, backfill and a per-lift compaction
schedule.

| Input | Type | Req. | Description |
|---|---|---|---|
| `structure_boundary` | curve | yes | Foundation footprint. |
| `depth_m` | number | yes | Pit bottom to grade. |
| `working_space_m` | number | — | Working space offset (standard default 0.6 m). |
| `bedding_thickness_m` | number | — | Bedding layer (standard default 0.1 m). |
| `lift_thickness_m` | number | — | Compaction lift (standard default 0.3 m). |
| `bake` | boolean | — | Write the working-space outlines onto layers. |

| Output | Type | Description |
|---|---|---|
| `excavation_boundary` | curve | Working-space outline. |
| `bedding_volume_m3` | number | Bedding volume. |
| `backfill_volume_m3` | number | Backfill volume. |
| `layer_count` | number | Compaction lifts. |
| `report_ru` | string | Report + schedule (flags an unreliable model unit). |
| `bake_status` | string | Bake result. |

---

## Sections

### gh_04_section — sections (profile or serial)

Sections through the existing (and optional proposed) meshes. `serial = false`
(default) draws a single **profile** along `line` with cut/fill regions and
cross-sectional areas; `serial = true` lays **cross-sections** every `spacing_m`
along `line` (used as a baseline) and reports average-end-area volumes. (Combines
the former profile and serial-section tools.)

| Input | Type | Req. | Description |
|---|---|---|---|
| `existing_mesh` | mesh | yes | Existing ground. |
| `proposed_mesh` | mesh | — | Proposed ground. |
| `line` | curve | yes | Section line (a baseline when `serial`). |
| `serial` | boolean | — | false = single profile; true = serial cross-sections. |
| `spacing_m` | number | — | Serial: station spacing (default 5.0 m). |
| `half_width_m` | number | — | Serial: half-width of each section (default 10.0 m). |
| `divisions` | number | — | Samples (default 50 profile / 30 serial). |
| `bake` | boolean | — | Write onto the section layer group. |

| Output | Type | Description |
|---|---|---|
| `existing_profile`, `proposed_profile` | curve | Profile mode: ground lines. |
| `cut_regions`, `fill_regions` | curve (list) | Profile mode: cut/fill areas. |
| `cut_area_m2`, `fill_area_m2` | number | Profile mode: cross-sectional areas. |
| `section_lines` | curve (list) | Serial mode: section cut lines. |
| `existing_profiles`, `proposed_profiles` | curve (list) | Serial mode: ground per station. |
| `cut_volume_m3`, `fill_volume_m3` | number | Serial mode: average-end-area volumes. |
| `report_ru` | string | Report. |
| `bake_status` | string | Bake result. |

---

## Relief & drainage

### gh_09_relief — relief, contours & drainage

Reads the terrain grid **once** and produces slope arrows + spot elevations,
contours, and drainage flow traces / ponding points (D8). Combines the former
relief, contours and drainage tools — sampling the grid once is faster than three
separate components. Wire the outputs you need.

| Input | Type | Req. | Description |
|---|---|---|---|
| `terrain_mesh` | mesh | yes | Mesh to analyse. |
| `boundary` | curve | — | Analysis boundary. |
| `grid_size_m` | number | — | Sampling grid (default 2.0 m). |
| `min_slope_percent` | number | — | Hide slope arrows below this (default 0). |
| `arrow_length_m` | number | — | Arrow length (default 0.6 × grid spacing). |
| `interval_m` | number | — | Contour interval (default 0.5 m). |
| `major_every` | number | — | Index contour every N (default 5). |
| `seed_every` | number | — | Seed a flow path every N nodes (default 3). |
| `bake` | boolean | — | Write onto the relief / contour / drainage layer groups. |

| Output | Type | Description |
|---|---|---|
| `slope_arrows` | curve (list) | Downhill arrows. |
| `spot_elevations` | generic (list) | Spot-elevation tags. |
| `minor_contours`, `major_contours` | curve (list) | Contours. |
| `levels_m` | number (list) | Contour levels. |
| `flow_paths` | curve (list) | Descending flow traces. |
| `low_points`, `high_points` | point (list) | Ponding / local high points. |
| `max_slope_percent` | number | Steepest slope. |
| `report_ru` | string | Combined report (relief + contours + drainage). |
| `bake_status` | string | Bake result. |

### gh_12_ditch — ditch / swale with invert marks

Trapezoidal ditch along a centreline: invert curve, top edges, invert marks and
excavation volume, with a daylight warning.

| Input | Type | Req. | Description |
|---|---|---|---|
| `centerline` | curve | yes | Ditch alignment. |
| `existing_mesh` | mesh | yes | Ground to daylight against. |
| `depth_m` | number | — | Invert depth (default 0.5 m). |
| `start_invert_m` | number | — | Start invert level (draped from mesh if empty). |
| `longitudinal_slope_percent` | number | — | Invert grade (default 0). |
| `bottom_width_m` | number | — | Ditch bottom width (default 0.4 m). |
| `side_slope` | number | — | `1:m` side slope (default 1.5). |
| `divisions` | number | — | Samples along the line. |
| `mark_every` | number | — | Invert mark spacing. |
| `bake` | boolean | — | Write onto the drainage layer group. |

| Output | Type | Description |
|---|---|---|
| `invert_curve` | curve | Ditch invert. |
| `top_edges` | curve (list) | Top-of-bank edges. |
| `invert_marks` | generic (list) | Invert level marks. |
| `excavation_volume_m3` | number | Trapezoidal excavation volume. |
| `report_ru` | string | Report (flags an unreliable model unit). |
| `bake_status` | string | Bake result. |

---

## Design authoring

### gh_16_grading — grading surface from spot elevations

Interpolates a proposed grading surface from design spot elevations along a
polyline (IDW), relative to a building `±0.000` datum.

| Input | Type | Req. | Description |
|---|---|---|---|
| `design_curve` | curve | yes | Polyline whose vertices carry the design spot elevations. |
| `boundary` | curve | — | Surface extent. |
| `grid_size_m` | number | — | Output grid (default 1.0 m). |
| `datum_m` | number | — | `±0.000` datum in metres (default 0). |
| `power` | number | — | IDW power (default 2.0). |
| `bake` | boolean | — | Write onto the grading layer group. |

| Output | Type | Description |
|---|---|---|
| `grading_mesh` | mesh | Proposed grading surface. |
| `min_z`, `max_z` | number | Elevation range. |
| `report_ru` | string | Report. |
| `bake_status` | string | Bake result. |

### gh_17_blind_area — blind area (отмостка)

A blind-area band around a building footprint, sloping away from the building.

| Input | Type | Req. | Description |
|---|---|---|---|
| `building_footprint` | curve | yes | Building outline. |
| `top_elevation_m` | number | — | Edge-at-building level (default 0). |
| `width_m` | number | — | Band width (default 1.0 m). |
| `slope_percent` | number | — | Slope away from the building (default 3 %). |
| `bake` | boolean | — | Write onto the grading layer group. |

| Output | Type | Description |
|---|---|---|
| `inner_edge` | curve | Edge at the building. |
| `outer_edge` | curve | Outer edge. |
| `area_m2` | number | Blind-area area. |
| `report_ru` | string | Report (cites the standard's slope range). |
| `bake_status` | string | Bake result. |

### gh_18_driveway — driveway/path grades & compliance

Path edges, grade marks (in ‰) and a max-grade compliance check.

| Input | Type | Req. | Description |
|---|---|---|---|
| `centerline` | curve | yes | Driveway/path alignment carrying elevations. |
| `width_m` | number | — | Path width (default 3.0 m). |
| `max_grade_percent` | number | — | Allowable longitudinal grade (standard default 8 %). |
| `bake` | boolean | — | Write onto the driveways layer group. |

| Output | Type | Description |
|---|---|---|
| `path_edges` | curve (list) | Path kerb lines. |
| `grade_marks` | generic (list) | Longitudinal grade marks (‰). |
| `max_grade_percent` | number | Steepest grade found. |
| `compliant` | boolean | Within the allowable grade. |
| `report_ru` | string | Report. |
| `bake_status` | string | Bake result. |

### gh_19_mass_haul — ±0.000 / mass-haul optimiser

Sweeps the platform elevation and reports cut/fill vs the platform level, plus the
zero-balance (`±0.000`) elevation.

| Input | Type | Req. | Description |
|---|---|---|---|
| `existing_mesh` | mesh | yes | Existing ground. |
| `boundary` | curve | — | Platform extent. |
| `grid_size_m` | number | — | Sampling grid (default 2.0 m). |
| `platform_m` | number | — | Platform level to evaluate (defaults to the balanced elevation). |
| `steps` | number | — | Sweep steps for the curve (default 12). |

| Output | Type | Description |
|---|---|---|
| `balanced_elevation_m` | number | Zero-balance platform level. |
| `cut_m3`, `fill_m3`, `net_m3` | number | At the chosen platform level. |
| `curve_levels_m` | number (list) | Swept platform levels. |
| `curve_cut_m3`, `curve_fill_m3` | number (list) | Cut/fill at each level. |
| `report_ru` | string | Report. |

---

## Accounting & quantities

### gh_14_soil_balance — bill of quantities + soil balance

Combined earth-mass accounting: a bill of quantities (topsoil + cut + fill +
backfill + ditch) **and** the per-soil bulking/shrinkage balance (import/export)
driven by cut + fill. Optional CSV. (Combines the former soil-balance and
quantities tools.)

| Input | Type | Req. | Description |
|---|---|---|---|
| `cut_m3` | number | — | Excavation volume in bank (in-situ). |
| `fill_m3` | number | — | Fill volume compacted. |
| `topsoil_m3` | number | — | Topsoil volume. |
| `backfill_m3` | number | — | Backfill volume. |
| `ditch_m3` | number | — | Ditch excavation volume. |
| `soil_class` | number | — | Soil class 1–6 (sets default bulking factors). |
| `initial_bulking` | number | — | Kр (loose) — overrides the soil default. |
| `residual_bulking` | number | — | Kор (compacted) — overrides the soil default. |
| `file_path` | string | — | Write the bill CSV to this path. |

| Output | Type | Description |
|---|---|---|
| `total_m3` | number | Sum of the bill items. |
| `import_m3` | number | Bank volume to import. |
| `export_m3` | number | Loose volume to export. |
| `cut_loose_m3` | number | Cut measured loose (after bulking). |
| `report_ru` | string | Bill table + soil-balance report. |
| `csv_text` | string | CSV of the bill. |
| `status` | string | Write status. |

---

## Engineering checks

### gh_20_foundation_check — frost-depth foundation check

Compares the foundation base depth against the design freezing depth on
frost-heaving soil (SP 22.13330.2016). **A working aid and checklist — it never
certifies.** Unconfirmed geotech is never adequate; groundwater forces review.

| Input | Type | Req. | Description |
|---|---|---|---|
| `base_depth_m` | number | yes | Foundation base depth. |
| `frost_depth_m` | number | — | Design freezing depth (or computed from below). |
| `soil_class` | number | — | Soil class 1–6 (sets `d0`). |
| `freezing_index` | number | — | `Mt` (sum of monthly sub-zero temps) to compute frost depth. |
| `thermal_factor` | number | — | `kh` thermal factor (default 1.1). |
| `heaving` | boolean | — | Frost-heaving soil (default true). |
| `groundwater` | boolean | — | Groundwater present → forces review. |
| `geotech_confirmed` | boolean | — | Required for an "adequate" verdict (default false). |

| Output | Type | Description |
|---|---|---|
| `adequate` | boolean | Only true with confirmed geotech and base below frost depth. |
| `design_frost_depth_m` | number | Used/derived freezing depth (−1 if unknown). |
| `status` | string | Verdict. |
| `report_ru` | string | Report with the mandatory non-certification note. |

### gh_21_foundation_drain — foundation ring drain

A foundation perimeter (ring) drain line offset around the footprint, set below a
reference level.

| Input | Type | Req. | Description |
|---|---|---|---|
| `foundation_footprint` | curve | yes | Foundation outline. |
| `offset_m` | number | — | Outward offset (default 0.4 m). |
| `depth_below_m` | number | — | Drop below the reference (default 0.3 m). |
| `reference_elevation_m` | number | — | Reference level (draped if empty). |
| `bake` | boolean | — | Write onto the subsoil-drain layer group. |

| Output | Type | Description |
|---|---|---|
| `drain_curve` | curve | Ring drain line. |
| `length_m` | number | Drain length. |
| `report_ru` | string | Report. |
| `bake_status` | string | Bake result. |

---

## Sheets & exchange

### gh_22_site_balance — site area balance (ТЭП)

Technical-economic indices: plot / building / paving / green areas and the
building coverage percentage.

| Input | Type | Req. | Description |
|---|---|---|---|
| `plot_boundary` | curve | yes | Plot outline (sets the plot area). |
| `building_area_m2` | number | — | Building footprint area. |
| `paving_area_m2` | number | — | Paving/hard-surface area. |
| `other_area_m2` | number | — | Other occupied area. |

| Output | Type | Description |
|---|---|---|
| `plot_area_m2` | number | Plot area from the boundary. |
| `building_percent` | number | Building coverage (%). |
| `green_area_m2` | number | Remaining (green) area. |
| `report_ru` | string | ТЭП table. |

### gh_23_titleblock — SPDS sheet frame + title block

A sheet frame and a simplified title block (GOST 21.101), stamped with the
[provenance](Standards#provenance) line.

| Input | Type | Req. | Description |
|---|---|---|---|
| `sheet` | string | — | Sheet size A4–A0 (default A3). |
| `origin` | point | — | Bottom-left placement. |
| `object_text` | string | — | Object field. |
| `title_text` | string | — | Sheet-title field. |
| `stage_scale_text` | string | — | Stage / scale field. |
| `sheet_number` | string | — | Sheet number field. |
| `author_text` | string | — | Author / date field. |
| `bake` | boolean | — | Write the frame onto the sheet layer group. |

| Output | Type | Description |
|---|---|---|
| `frame_curves` | curve (list) | Sheet border + inner frame. |
| `title_lines` | curve (list) | Title-block rules. |
| `title_tags` | generic (list) | Field text + provenance stamp. |
| `bake_status` | string | Bake result. |

### gh_13_revit_points — terrain points CSV (Revit)

Exports terrain points as a comma-delimited X,Y,Z file (in metres) for a Revit
Toposurface/Toposolid — also the basis for setting-out export.

| Input | Type | Req. | Description |
|---|---|---|---|
| `terrain_mesh` | mesh | yes | Mesh to sample. |
| `boundary` | curve | — | Sampling extent. |
| `grid_size_m` | number | — | Sample grid (default 2.0 m); uses mesh vertices otherwise. |
| `file_path` | string | — | Write the CSV to this path. |
| `recenter` | boolean | — | Recentre points near the origin (records the offset). |

| Output | Type | Description |
|---|---|---|
| `csv_text` | string | X,Y,Z point file (metres). |
| `point_count` | number | Number of points. |
| `origin_offset` | string | Applied recentre offset. |
| `status` | string | Write status. |

---

See [Standards](Standards) for the soil classes, rule tables and layer plans the
reports and bakes use, and [Workflows](Workflows) for how the components compose.
