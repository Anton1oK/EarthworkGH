# Earthwork Studio GH

Grasshopper tools for early-stage house-site earthworks in Rhino 8. The project
uses one reusable dynamic Python loader and external component scripts, following
the `00 grasshopper_dynamic_component_template` pattern.

The aim is a focused Bison-like workflow for a private-house earthwork stage:

1. edit a 2.5D terrain mesh;
2. compare existing and proposed relief;
3. produce an earth-mass cartogram and drawing geometry;
4. add drainage, slope, excavation, section and export tools incrementally.

This is a design-assistance toolkit. It does not replace engineering surveys,
geotechnical input, a licensed designer, or approval of working documentation.

## Implemented Components

### `gh_00_standard.py` - select the country / standard

Sets which country's code is active for every other component. Optional
`standard_code` input (e.g. `RU` or `INT`); leave it empty to read the current
selection. Outputs the active code and name, the list of available standards,
and a status string. The choice is stored in `scriptcontext.sticky`, so it
persists across components and across recomputes without any extra wiring - the
other components keep calling `standards.get_standard()` and pick it up. After
changing it, recompute the downstream components so they re-pull layer names,
text and rules.

- `RU` - Russian SPDS (ГОСТ/СП), the default.
- `INT` - International (generic, metric): English layer names and cut/fill
  report, metric units, no GOST drawing-grid restriction. A starter second
  standard that proves another country plugs in; its remaining report strings
  still inherit the Russian text (a localisation to-do).

### `gh_00_units.py` - verify the model units

A read-only check (it changes nothing) that reports the active document's length
unit and the conversion the tools will use, so you can confirm the calculations
are based on the right unit. Outputs the unit-system name, `units_per_meter`,
`meters_per_unit`, a `reliable` flag and a status line. If the model is unitless
the status is a warning to set the document units. This is document-level, not
country-specific - separate from the `gh_00_standard` selector.

### `gh_01_cut_fill_cartogram.py`

Calculates cut and fill on an SPDS-style square grid from existing and proposed
terrain meshes. It produces:

- cut/fill preview mesh;
- square-grid curves;
- zero-work lines;
- 45-degree hatch lines for excavation cells;
- cell volume text tags and corner elevation/work-mark text tags
  (bakeable Rhino annotation text, in metres);
- per-column and project totals;
- a Russian-language report;
- an SPDS earth-mass quantity table (`table_ru` text output, and a baked
  table of per-column fill/cut/balance with a totals row).

The defaults follow `GOST 21.508-2020`, section 8: the square method is used,
with a default grid side of 20 m and supported drawing-grid sides of
10, 20, 25, 40 and 50 m. For a small house site, a finer analysis grid can be
used as a working aid; the report flags that it is outside the standard drawing
grid options.

The optional `flat_tolerance_m` input (default `0.005` m) is a flatness
dead-band: per-sample height differences below it count as neither cut nor fill,
so sampling noise between two near-identical terrain meshes does not paint
untouched ground as shallow cut/fill. Raise it if such noise is larger.

### `gh_02_grade_pad.py`

Forms a flat pad bounded by a closed curve, with a user-selected slope ratio
`1:m`. Instead of nudging the source mesh vertices - which leaves the pad edge
and slope hostage to an irregular triangulation - it resamples the existing
surface onto a regular grid (default `0.5 m`, set by `resolution_m`), grades each
node, and rebuilds a uniform mesh. This gives clean pad edges and an even slope
band regardless of the input mesh quality. The component reports the selected
ratio but does not claim that it is code-compliant: temporary excavation slopes
require soil, groundwater, depth, loading and safety inputs under
`SP 45.13330.2017`.

### Drawing production: the `bake` toggle

`gh_01_cut_fill_cartogram` has an optional `bake` boolean input. Flip it to
`true` and the component writes its geometry onto named, coloured,
print-weighted Rhino layers for drawing production: a parent layer
(`Картограмма земляных масс`) with one child layer per output - boundary, grid,
zero-work line, cut hatch, corner marks, cell volumes and the analysis preview
mesh - each with an SPDS-oriented colour and line weight from the active
standard (`standards.py`). Re-baking clears those layers first, so it refreshes the
drawing rather than duplicating it. From there, use Make2D, a layout and print
to produce the sheet. (Baking is built into `gh_01` rather than a separate
component because some Rhino builds do not give script inputs list access, which
a standalone bake component would need.)

### `gh_03_slope_hachures.py`

Draws excavation-pit slopes from a terrain/pit mesh you already have. It samples
the mesh gradient on a grid and, wherever the surface is steeper than a threshold
(`min_slope_1_to`, default `1:5`), emits downhill **slope hachures** (откосные
штрихи) of alternating length plus a **slope-extent outline** (top and toe of
the slope). It reports the steepest slope as `1:m`. With `bake` set to `true` it
writes the hachures and outline onto a `Котлован` layer group. All inputs are
single-value, so no list-access type hint is needed. It draws geometry only and
does not certify slope stability - that needs `SP 45.13330.2017` inputs.

### `gh_04_section.py`

Cuts a profile section through the terrain along a section line. Wire the
existing mesh, an optional proposed mesh and a `section_line` curve; it samples
both meshes along the line and returns the **existing and proposed ground lines**
plus **cut and fill regions** standing in place on the section plane, with their
cross-sectional areas in square metres. With `bake` set to `true` it writes them
onto a `Разрез` layer group (existing, proposed, cut, fill). All inputs are
single-value.

### `gh_05_serial_sections.py`

Takes a row of cross-sections along a baseline curve and computes **cut and fill
volumes** by the average-end-area method. Wire the existing mesh, an optional
proposed mesh and a `baseline`; set `spacing_m` (between sections) and
`half_width_m` (section reach each side). It returns the perpendicular section
lines, the existing/proposed ground lines at each, the total `cut_volume_m3` /
`fill_volume_m3`, and a station table (`report_ru`) listing each section's
cross-areas and the volume totals. `bake` writes them onto a `Серия разрезов`
layer group. All inputs are single-value.

### `gh_06_topsoil.py`

Topsoil-removal plan and volume statement. Wire a closed `boundary` (the
stripping area) and an optional `existing_mesh`; set `strip_depth_m` (default
`0.2`). It returns the stripping boundary, 45-degree hatch lines draped on the
terrain, a label, and the strip `area_m2` / `volume_m3` (area times depth). With
`bake` set to `true` it writes them onto a `Растительный слой` layer group.

### `gh_07_slope_check.py`

Temporary-slope assessment aid for excavations, referencing
`SP 45.13330.2017` (раздел 6, приложение В). Wire the proposed slope as `1:m`
(e.g. `gh_03`'s `max_slope_1_to`) and the excavation `depth_m`; optionally a
`soil_class` (1-6), an `allowable_slope_1_to` from the geotechnical report,
and `groundwater` / `surcharge` / `geotech_confirmed` flags. It compares the
proposed slope against the governing allowable (the report value when given,
otherwise an indicative table value) and returns a status, `within_allowable`,
the allowables and a Russian checklist. Groundwater, edge surcharge or depth over
5 m force a "review required" result, and nothing reads as acceptable until the
geotechnical inputs are confirmed. **It is a working aid and a checklist, not a
certification** - the final decision needs project geotechnical input and review.

### `gh_08_backfill.py`

Foundation bedding, backfill and a layered compaction schedule. Wire the
structure/foundation footprint and the backfill `depth_m`; optionally a
`working_space_m` (default `0.6`), `bedding_thickness_m` (default `0.1`) and
`lift_thickness_m` (compaction lift, default `0.3`). It offsets the footprint
outward by the working space to get the excavation-bottom outline, then reports
the bedding volume, the working-space backfill volume, and a per-lift schedule
table (`SP 45.13330.2017`, раздел 7). `bake` writes the outlines onto the
`Котлован` layer group. All inputs are single-value.

### `gh_09_relief.py`

Relief preview from a terrain mesh: it grid-samples the surface and returns
**downhill slope arrows** (aspect) and **spot-elevation tags** (metres), plus the
steepest slope as a percentage. Wire the mesh and optionally a `boundary`, a
`grid_size_m` (default `5`), an `arrow_length_m`, and `min_slope_percent` to hide
near-flat arrows. `bake` writes the arrows and spot heights onto a `Рельеф`
layer group. All inputs are single-value.

### `gh_10_contours.py`

Proposed contours (horizontals) from a terrain mesh by marching squares. Wire
the mesh and optionally a `boundary`; set the `interval_m` (default `0.5`),
`major_every` (bold every Nth, default `5`) and `grid_size_m` (sampling
resolution). It returns minor and major contour curves at their true elevations,
the list of `levels_m`, and a report. `bake` writes them onto the `Рельеф`
layer group (`Горизонтали` / `Горизонтали основные`). All inputs are
single-value. Join the segments in Rhino for continuous contour polylines.

### `gh_11_drainage.py`

Drainage analysis from a terrain mesh: D8 steepest-descent **flow traces**, plus
**local low points** (sinks where water ponds) and **high points** (peaks). Wire
the mesh and optionally a `boundary`; set `grid_size_m` and `seed_every` (flow
seed spacing). It returns the flow polylines, the low/high points, and a report
that **warns when ponding sinks exist**. `bake` writes them onto a `Водоотвод`
layer group. Geometry-only analysis aid; all inputs are single-value.

### `gh_12_ditch.py`

Ditch / swale along a centreline. Wire the `centerline` and the `existing_mesh`;
set either a fixed `depth_m` (invert follows the ground) or a designed
`start_invert_m` with `longitudinal_slope_percent`, plus `bottom_width_m` and
`side_slope` (`1:m`). It returns the **invert curve** along the centreline, the
two **top edges** (offset), **invert marks** (`Дк` bottom elevations) and the
**excavation volume** (trapezoidal channel by average end area), and warns where
the invert daylights above ground. `bake` writes them onto the `Водоотвод` layer
group. All inputs are single-value.

### `gh_13_revit_points.py`

Exports terrain points as a comma-delimited X,Y,Z CSV (in metres) for **Revit**.
Wire the `terrain_mesh` and optionally a `boundary`; set `grid_size_m` (resample
spacing, or `0` to use the mesh vertices) and a `file_path` to write the file.
`recenter` subtracts the minimum corner so the points sit near the origin (the
`origin_offset` output reports the shift, for georeferencing). In Revit: a
Toposurface or Toposolid via *Create from Import -> Specify Points File*, with
units set to **Meters**. (For a live link instead of a file, run these components
under Rhino.Inside.Revit and feed the meshes/curves into its Toposolid /
DirectShape components. For the 2D SPDS sheets, bake and export DWG, then link in
Revit.)

### Vertical planning, accounting, checks & sheets (Releases 0.6-0.7)

| Component | Purpose |
|---|---|
| `gh_14_soil_balance` | bulking/shrinkage + soil haul, import/export balance |
| `gh_15_quantities` | combined earth-mass bill of quantities (+ CSV) |
| `gh_16_grading` | design spot elevations (+ `+-0.000` datum) -> grading surface |
| `gh_17_blind_area` | blind area (отмостка) sloping away from the building |
| `gh_18_driveway` | driveway/path grades + max-grade compliance, ‰ marks |
| `gh_19_mass_haul` | balanced platform `+-0.000` + cut/fill-vs-FFL curve |
| `gh_20_foundation_check` | frost-depth foundation check (working aid, never certifies) |
| `gh_21_foundation_drain` | foundation perimeter (ring) drain line |
| `gh_22_site_balance` | site area balance / ТЭП table (building/paving/green %) |
| `gh_23_titleblock` | SPDS sheet frame + simplified title block (ГОСТ Р 21.101) |

### Producing a genplan / organization-of-relief sheet

The components compose into a sheet rather than needing a single "assemble"
button. A typical organization-of-relief (ПОР) / general-layout sheet:

0. Pick the standard once with `gh_00_standard` (default `RU`). Every later
   component reads the active standard's layer names, text and rules.
1. Author the proposed grades with `gh_16_grading` (corner spot elevations) and
   tune `+-0.000` with `gh_19_mass_haul` to balance cut/fill.
2. Add detail: `gh_17_blind_area`, `gh_18_driveway`, drainage (`gh_11`, `gh_12`,
   `gh_21`), and relief reading (`gh_09` spot heights/arrows, `gh_10` contours).
3. Quantities: feed the cut/fill (`gh_01`/`gh_05`), topsoil (`gh_06`), backfill
   (`gh_08`) and ditch (`gh_12`) volumes into `gh_14`/`gh_15` for the balance and
   the bill; `gh_22` for the ТЭП.
4. Bake everything (the `bake` toggles) onto the SPDS layer groups, drop a
   `gh_23` frame + title block, then Make2D + layout + print.

Each component bakes to its own named layer group, so the layers compose into one
coherent, print-ready drawing tree.

## Model Units

Every component reads the active Rhino document's unit system **before it
calculates**, via `Rhino.RhinoMath.UnitScale`, so a millimetre, centimetre,
metre, **inch or foot** model all compute correctly - horizontal areas scale by
the square of the conversion and vertical heights linearly. Drawing geometry
(preview mesh, grid, hatches, dots) is produced in document units and overlays
the model directly, while the grid side is entered in **metres** and all volumes
are reported in **cubic metres**. Elevation and working marks are shown in
metres. In `gh_02_grade_pad`, the pad elevation is entered in metres.

If the document has **no unit system set** (unitless), the unit cannot be
trusted; the tools fall back to "1 unit = 1 m" but flag it loudly rather than
silently producing a 1000x-wrong volume. Drop `gh_00_units` on the canvas to read
the detected unit, the conversion factor and a reliability flag, and the volume
components (`gh_01`, `gh_06`, `gh_08`, `gh_12`) prepend the same warning to their
report when the unit is unreliable. Set the Rhino document units (mm / m / inch)
and the warning clears.

## Grasshopper Setup

There are two ways to run a component: from a **local copy** of the repo, or
**straight from GitHub** (no checkout needed).

### Option A - local loader (`gh_dynamic_loader.py`)

1. Paste `gh_dynamic_loader.py` into one Rhino 8 Grasshopper Python 3 component.
2. Connect a Grasshopper File Path parameter to its first input.
3. Point the File Path to one of the scripts in `gh_components/`. The loader
   auto-detects the project folder from that path, so the kit is portable - copy
   the folder anywhere and the components resolve their own location (no paths to
   edit).
4. Recompute Grasshopper after edits.

### Option B - remote loader (`gh_remote_loader.py`, from GitHub)

Run a component directly from the GitHub repo - useful for sharing the kit
without sending files around.

1. Paste `gh_remote_loader.py` into one Rhino 8 Grasshopper Python 3 component.
2. Edit the two constants at the top once: `GITHUB_REPO = "owner/name"` and
   `GITHUB_REF` (a branch like `main`, or a release tag like `v0.8.0` for a
   reproducible pin).
3. Connect a text panel with the component name (e.g.
   `gh_01_cut_fill_cartogram`) to the **first** input.
4. Recompute. The first pass downloads the modules + component (cached under the
   OS temp folder) and sets the sockets; the second pass runs the component.
   After that, the `repo` / `ref` / `refresh` sockets let you override per
   instance; toggle `refresh` to pull the latest code.

The remote loader fetches `manifest.json` from the repo and mirrors every listed
module and component into the cache, so any component name resolves offline after
the first sync. Requires internet access from Rhino and a public repo (files
reachable via `raw.githubusercontent.com`).

Typical loop (either loader):

```text
[existing terrain mesh] -> [gh_02_grade_pad] -> proposed_mesh
          |                                      |
          +-----------> [gh_01_cut_fill_cartogram]  (bake=true -> drawing layers)
```

Use one loader component per script (each with its own File Path / component
name).

## Publishing to GitHub

The repo is ready to push. From the project folder:

```bash
git add -A
git commit -m "Earthwork Studio GH"      # already done on first import
git remote add origin https://github.com/<owner>/<name>.git
git branch -M main
git push -u origin main
```

Then set `GITHUB_REPO = "<owner>/<name>"` in `gh_remote_loader.py` and share that
one file - collaborators run the whole kit from your repo. Tag releases
(`git tag v0.8.0 && git push --tags`) so the remote loader can pin a fixed
version.

## Standards Layer

All country/code-specific content - regulation text, calculation rules, soil and
slope tables, report wording, and SPDS layer names/colours - lives in
`standards.py` behind a `Standard` interface. `RU` (Russian SPDS / GOST / SP) is
the first implementation and the default. The engineering core
(`earthwork_core.py`) and the Rhino plumbing (`rhino_adapter.py`) are deliberately
neutral: they compute geometry and volumes and bake whatever layer plan they are
given. To support another country, add a new `Standard` subclass in
`standards.py`, register it in `STANDARDS`, and have the components select it via
`standards.get_standard(code)` - no changes to the core or adapters.

## Provenance

Every output is traceable. The neutral tool version lives in `version.py`
(`Earthwork Studio GH v0.7.0`); each `Standard` declares the regulation editions
it encodes (`regulations`) and when they were last reviewed (`checked_on`).
`version.provenance(standard)` combines them into one line, e.g.
`Earthwork Studio GH v0.7.0 - standard RU: ГОСТ 21.508-2020, СП 45.13330.2017,
...; checked 2026-06`. It is shown by `gh_00_standard` and stamped onto the sheet
by `gh_23_titleblock`. The stamp records the encoded editions; it does not
replace engineer review (the kit never certifies geotechnical adequacy). Bump
`__version__` and add a `CHANGELOG.md` entry on each release.

## Local Verification

```powershell
python -m unittest discover -s tests -v
python -m compileall .
```

## Project Documents

- `DEVELOPMENT_PLAN.md` - staged feature roadmap.
- `REGULATORY_BASIS.md` - standards and implementation boundaries.
