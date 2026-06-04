# Development Plan

## Product Direction

Recreate the useful terrain workflow of Bison for a house earthwork project,
while generating Russian SPDS-oriented graphic outputs and explicit compliance
notes. Keep the engineering core testable outside Rhino and keep Grasshopper
scripts thin.

## Architecture

Three layers, so other countries' standards can be added without touching the
engineering or Rhino code:

- `earthwork_core.py` - universal geometry/math, language- and code-neutral,
  fully unit-tested outside Rhino.
- `rhino_adapter.py` - universal RhinoCommon plumbing (sampling, geometry,
  baking); takes layer plans and labels as parameters.
- `standards.py` - all country/code-specific rules, text, citations and SPDS
  layer plans behind a `Standard` interface (`RU` is the default). Add a country
  by subclassing `Standard` and registering it.

Components are thin glue: they read inputs, call the core/adapter for geometry,
and pull text/rules/layers from the active standard. All component inputs are
single-value (item access), because the user's Rhino build does not reliably set
list access on script inputs.

## Roadmap Priorities (assessment, 2026-06-03)

Feature coverage is broad (13 components across earth mass, excavation, relief,
drainage and Revit export). The weak spots now are platform and trust, not
features. Two cross-cutting tracks should run alongside - and ahead of - further
features.

### Platform track - make it shareable and fast

- Portability: DONE. The hardcoded `PROJECT_FOLDER` is gone from all 13
  components (they derive it from the loaded file's location) and the loader
  auto-detects it from the connected File Path. Copy the folder anywhere.
- Shared component runtime / one height grid: DONE for the grid analyses.
  `rhino_adapter.analysis_grid` ray-samples the surface once into a cached node
  grid and returns an O(1) sampler; relief, contours and drainage now share it
  (validated identical to per-point sampling). Collapsed the repeated grid setup.
- Distribution: a sample `.gh` and `.3dm`, a one-time setup, and a path to a
  packaged Grasshopper plugin (`.gha` / Yak). Pending.

### Trust track - make it defensible for documentation

- Versioning: DONE. A neutral `version.py` (`TOOL_NAME`, `__version__`,
  `tool_stamp()`, `provenance(standard)`) and `CHANGELOG.md`. Outputs are stamped
  with tool + standard edition, e.g. "Earthwork Studio GH v0.7.0 - standard RU:
  ГОСТ 21.508-2020, СП 45.13330.2017, ...; checked 2026-06".
- Standard editions: DONE. Each `Standard` declares `regulations` + `checked_on`
  and an `edition_stamp()` (national text). Surfaced by `gh_00_standard`
  (`provenance` output) and stamped onto the `gh_23_titleblock` sheet. The tool
  version stays neutral in `version.py`; only the editions live in the standard.
- Units: DONE. Every component reads the model unit before calculating
  (`classify_units` / `document_unit_info`), works for mm/cm/m/inch/foot, and
  flags a unitless/unreadable document instead of a silent 1000x error.
- Validation: one golden end-to-end example with a hand-computed answer.
- Multi-country proof: STARTED. A `gh_00_standard` selector sets the active
  country/standard, stored in `scriptcontext.sticky` so it persists across
  components and recomputes (each component reloads `standards`, so a module
  global would be wiped - sticky is the carrier). `set_active_standard` /
  `available_standards` / `get_standard()` registry added; the 23 other
  components need no change (they already call `get_standard()`). A second
  standard `INT` (International, generic metric, English layers + cut/fill
  report) is registered to catch leaks. Still pending: formalise the full
  `Standard` interface contract + a conformance test, and fully localise `INT`'s
  remaining report strings.
- Accuracy: exact polygon-clipped cartogram cells (replace the subsample boundary
  approximation) for documentation-grade quantities.

### Output track

- A combined earth-mass bill of quantities (topsoil + cut/fill + backfill +
  ditch) as one schedule/CSV.

Recommended next step: a hardening pass (Platform + Trust) before more 0.5
features.

## House-Project Completeness (domain gaps, 2026-06-03)

Walking a real private-house earthwork project end to end surfaces gaps beyond
the current analysis tools. The biggest are conceptual, not just missing features.

1. Author the design, not just analyze it. Every tool assumes the proposed mesh
   already exists; the design act - building +-0.000, finished spot elevations,
   blind area (отмостка), entrance/driveway grades - is unsupported (grade pad is
   the only authoring tool).
2. Volumes are neat-line geometric. No bulking/shrinkage; a real bill of
   quantities and soil haul/import-export need bank/loose/compacted volumes
   (factors per soil, from the standard).
3. Geometry, not sheets. No SPDS sheet frame or title block (штамп, ГОСТ Р
   21.101), no assembled organization-of-relief plan (ПОР) or general layout.
4. House essentials missing: frost-depth/bearing foundation check, site area
   balance (ТЭП), setting-out plan, foundation drainage.

These are scheduled as Releases 0.6 and 0.7 below, in build order (accounting
first so every volume is defensible, then design authoring, then checks, then
sheet production that presents the results).

## Release 0.1 - Working Earth-Mass Loop

Status: implemented and hardened.

- SPDS-style square-grid cut/fill cartogram.
- Existing, proposed and working elevation marks at cell corners (text tags).
- Zero-work lines, excavation hatch, per-cell volumes and column totals.
- Flat grading-pad mesh modifier with a configurable `1:m` slope ratio,
  resampled onto a regular grid so it is robust to irregular input meshes.
- Document-unit awareness (mm/cm/m): geometry in document units, volumes in m3.
- Flatness dead-band so sampling noise between two meshes does not read as work.
- Unit tests for grid totals, mixed cut/fill, units, dead-band and pad grading.

## Drawing Production (brought forward from Release 0.4)

Status: implemented. Prioritised to produce drawings from the existing loop.

- `standards.py`: SPDS layer names, colours and print line weights (and all
  other code-specific rules/text) behind the `Standard` interface.
- `gh_01` `bake` toggle: bakes cartogram output onto those layers; idempotent
  re-bake. Built into `gh_01` (not a separate component) because some Rhino
  builds will not give script inputs list access. Use Make2D + layout + print.
- SPDS earth-mass quantity table: `Standard.earth_mass_table` / `QuantityTable`,
  `table_ru` text output and a baked table on the "Ведомость объёмов" layer.
- Profile section: `build_section` / `SectionDrawing` in the core,
  `gh_04_section` produces existing/proposed ground lines, cut/fill regions and
  cross-sectional areas, baked onto a "Разрез" layer group.
- Serial sections: `serial_section_volumes` / `serial_section_table` in the
  core, `gh_05_serial_sections` lays cross-sections along a baseline and reports
  average-end-area cut/fill volumes with a station table.
- Still pending in Release 0.4: the topsoil-removal plan and volume statement.

## Release 0.2 - House Excavation

Status: largely implemented. Reworked around the actual workflow - the user
supplies existing and edited (pit) meshes, so the tools read those meshes rather
than generating pit grading from soil-profile inputs.

Done:

- Pit slope drawing from an existing mesh: `analyze_slopes` /
  `gh_03_slope_hachures` (crest-anchored hachures, slope-extent outline,
  steepest `1:m`), baked to a `Котлован` layer group. Geometry only.
- Temporary slope assessment based on `SP 45.13330.2017` (section 6, appendix V)
  with a geotechnical-input checklist: `gh_07_slope_check`. A working aid only -
  it never certifies the slope.
- Topsoil stripping surface and quantity (`gh_06_topsoil`).
- Foundation working-space offset, bedding, backfill and a layered compaction
  schedule: `estimate_backfill` / `backfill_layers` in the core,
  `gh_08_backfill`, with volumes and a per-lift schedule table.

Pending / deprioritised:

- Pit/trench grading generated from soil-profile inputs - deprioritised: the
  user models the pit mesh directly, so this is optional.
- Trench-specific cross-sections (the section tools already cover this when a
  trench mesh is supplied).

## Release 0.3 - Relief And Drainage

Started.

Done:

- Spot elevations and slope arrows (aspect): `slope_field` in the core,
  `gh_09_relief` (downhill arrows + spot-elevation tags + steepest-slope %),
  baked to a `Рельеф` layer group.
- Proposed contours (organization of relief): `contour_segments` (marching
  squares) in the core, `gh_10_contours` (minor/major horizontals at true
  elevations), baked to the `Рельеф` layer group.
- Flow traces and local high/low points with a ponding warning:
  `drainage_analysis` (D8) in the core, `gh_11_drainage`, baked to a `Водоотвод`
  layer group.
- Ditch / swale editor with invert marks: `ditch_profile` / `ditch_volume` in the
  core, `gh_12_ditch` (invert curve, top edges, `Дк` invert marks, trapezoidal
  excavation volume, daylight warning), baked to the `Водоотвод` layer group.

Pending:

- Elevation/slope/aspect preview mesh (coloured analysis mesh) - optional.

## Release 0.4 - Sections And Documentation

Status: implemented.

- Profile and serial section tools (`gh_04_section`, `gh_05_serial_sections`).
- Existing/proposed ground lines with cut/fill regions.
- SPDS-oriented earth-mass quantity table (`gh_01` + `earth_mass_table`).
- Topsoil-removal plan and volume statement (`gh_06_topsoil`).
- Layer naming, color presets and bake helpers (`standards.py` layer groups,
  per-component `bake` toggles writing to SPDS layer groups).

## Release 0.5 - Terrain Exchange

Started.

Done:

- Terrain points CSV export for Revit (toposurface / toposolid points file):
  `points_to_csv` in the core, `gh_13_revit_points` (grid resample or mesh
  vertices, metres, optional recentre). Also the basis for setting-out export.

Pending:

- LandXML TIN import.
- DEM/GeoTIFF import with coordinate-system warnings.
- Square and triangular resampling.
- CSV export of setting-out coordinates under a selected survey basis.

## Release 0.6 - Vertical Planning & Earthwork Accounting

Status: implemented (`gh_14`-`gh_19`).

Closes the "we analyse but don't author, and our volumes are neat-line" gaps.
Build order:

Earthwork accounting (first - makes every volume defensible):

1. `soil_balance` core + per-soil bulking/shrinkage factors in the standard:
   bank / loose / compacted volumes and the cut / fill / reuse / import / export
   balance. Component `gh_14_soil_balance`.
2. `bill_of_quantities` core + standard schedule + `gh_15_quantities`: one earth-
   mass bill (topsoil + cut + fill + backfill + ditch), bulking applied, CSV.

Vertical-planning authoring (turn the kit into a designer):

3. `grade_by_points` core: a building +-0.000 datum and finished spot elevations
   interpolated into a proposed grading surface. Component `gh_16_grading`.
4. Blind area (отмостка): slope away from the footprint. `gh_17_blind_area`.
5. Driveway / path grade design + compliance (max grade, cross-slope).
   `gh_18_driveway`.
6. +-0.000 / mass-haul optimiser: sweep the platform elevation, cut/fill vs FFL.
   `gh_19_mass_haul`.

## Release 0.7 - Engineering Checks & Sheet Production

Status: implemented (`gh_20`-`gh_23`); ПОР/genplan assembled by composing the
components (see README) rather than a single component.

Engineering checks (geotech-input driven; never auto-certify):

1. Frost-depth / bearing-layer foundation check (standard frost data + soil
   profile). `gh_20_foundation_check`.
2. Foundation perimeter drainage. `gh_21_foundation_drain`.

Sheet production (presents the results):

3. Site area balance / ТЭП table (plot / building / paving / green areas + %).
   `gh_22_site_balance`.
4. SPDS sheet frame + title block (ГОСТ Р 21.101 forms) from the standard.
   `gh_23_titleblock`.
5. Assembled organization-of-relief plan (ПОР) and general layout (генплан).

## Quality Gates

- Pure-Python unit tests for every calculation module.
- Rhino smoke tests for every Grasshopper adapter.
- Sample `.3dm` and `.gh` file for the house-site workflow.
- Regulatory review before any output is labelled suitable for working
  documentation.

