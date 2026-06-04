# Changelog

All notable changes to Earthwork Studio GH. Dates are ISO (YYYY-MM-DD).

## [Unreleased]

### Changed
- Project restructured for GitHub: docs under `docs/`, the pasted-in loaders
  under `loaders/`, CI workflow + PR template under `.github/`, `pytest.ini` and
  `CONTRIBUTING.md` added. Importable modules and `gh_components/` stay at the
  repository root (the loaders import them by bare name and the remote loader
  mirrors them into its cache root - see `docs/STRUCTURE.md`).
- Branching model documented: `main` (released) / `develop` (integration) /
  feature branches.

## [0.8.0] - 2026-06-04

### Added
- **Run components straight from GitHub.** `gh_remote_loader.py` downloads the
  plugin's modules and the requested component from a GitHub repo, caches them
  under the OS temp folder (per repo + ref), then runs the component - no local
  checkout needed. Set `GITHUB_REPO`/`GITHUB_REF`, name the component, recompute;
  toggle `refresh` to pull the latest. Pin a release tag (e.g. `v0.8.0`) for
  reproducibility.
- **`gh_remote.py`** - pure, Rhino-free helpers (URL building, repo/component
  normalisation, cache paths, manifest handling, schema parse, `sync`) with the
  network fetch injected, so the whole sync is unit-tested offline.
- **`manifest.json`** - lists the modules and components the remote loader pulls;
  a test asserts it matches the files on disk so it cannot drift.
- Repository prepared for upload: `LICENSE` (proprietary, all rights reserved),
  expanded `.gitignore`, and an Install section in the README covering both the
  local loader and the GitHub remote loader.

## [0.7.0] - 2026-06-04

### Added
- **Provenance stamping.** A neutral `version.py` (`TOOL_NAME`, `__version__`,
  `tool_stamp()`, `provenance()`); each `Standard` declares the regulation
  editions it encodes (`regulations`, `checked_on`) and an `edition_stamp()`.
  Every output can be traced to a tool version + the exact standard editions.
  Surfaced by `gh_00_standard` and stamped into the `gh_23_titleblock` sheet.
- **Country / standard selector.** `gh_00_standard` sets the active standard,
  persisted in `scriptcontext.sticky` so it survives every component's
  `importlib.reload`. Registry: `set_active_standard`, `available_standards`,
  `get_standard()`. A second standard `INT` (generic metric, English) proves the
  multi-country architecture; its remaining report strings inherit Russian text.
- **Unit-system hardening.** `earthwork_core.classify_units` +
  `rhino_adapter.document_unit_info` read the model units before any calculation
  for any system (mm/cm/m/inch/foot) and flag unitless/unreadable documents
  loudly instead of silently assuming 1 unit = 1 m. New read-only `gh_00_units`
  check; the volume components warn when the unit is unreliable.

### Notes
- The kit is a working aid and never certifies geotechnical adequacy; the
  provenance stamp records the encoded editions but does not replace engineer
  review.

## [0.6.0] - 2026-06-03

- Vertical-planning authoring and earthwork accounting (`gh_14`-`gh_19`):
  soil balance with bulking/shrinkage, combined bill of quantities, design spot
  elevations, blind area, driveway grades, mass-haul / `+-0.000` optimiser.
- Engineering checks and sheet production (`gh_20`-`gh_23`): frost-depth
  foundation check, foundation ring drain, site area balance (ТЭП), SPDS sheet
  frame + title block.

## [0.1.0 - 0.5.0]

- Earth-mass cartogram, drawing production, excavation, relief and drainage,
  sections and documentation, and Revit terrain-points export. See
  `docs/DEVELOPMENT_PLAN.md` for the per-release detail.
