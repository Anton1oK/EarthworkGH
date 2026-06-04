# Earthwork Studio GH

Grasshopper tools for early-stage house-site earthworks in Rhino 8. The kit edits
a 2.5D terrain mesh, compares existing and proposed relief, produces an earth-mass
cartogram and drawing geometry, and adds drainage, slope, excavation, section,
accounting, checks, sheets and exchange tools — with Russian SPDS (ГОСТ/СП)
graphic outputs and explicit compliance notes.

> This is a design-assistance toolkit. It does **not** replace engineering
> surveys, geotechnical input, a licensed designer, or approval of working
> documentation. The engineering checks never certify adequacy.

## Documentation

Full documentation is in the **[project wiki](https://github.com/Anton1oK/EarthworkGH/wiki)**:

- **[Home](https://github.com/Anton1oK/EarthworkGH/wiki/Home)** — overview and conventions.
- **[Installation](https://github.com/Anton1oK/EarthworkGH/wiki/Installation)** — run a component from a local copy or straight from GitHub.
- **[Component Reference](https://github.com/Anton1oK/EarthworkGH/wiki/Component-Reference)** — every component with its full inputs and outputs.
- **[Workflows](https://github.com/Anton1oK/EarthworkGH/wiki/Workflows)** — the cut/fill loop, baking, and assembling a genplan / ПОР sheet.
- **[Standards](https://github.com/Anton1oK/EarthworkGH/wiki/Standards)** — citations, rule tables, checks and layer plans for the `RU` and `INT` standards.

## What's inside

25 components, grouped (see the
[Component Reference](https://github.com/Anton1oK/EarthworkGH/wiki/Component-Reference)
for every input and output):

- **Setup** — select the country/standard; verify the model units.
- **Earth-mass & cartogram** — SPDS square-grid cut/fill; flat grading pad.
- **Excavation & slopes** — pit slope hachures; topsoil strip; temporary-slope aid; backfill schedule.
- **Sections** — profile section; serial cross-sections with volumes.
- **Relief & drainage** — slope arrows; contours; flow traces; ditch/swale.
- **Design authoring** — grading from spot elevations; blind area; driveway grades; ±0.000 / mass-haul optimiser.
- **Accounting** — soil balance with bulking; combined bill of quantities.
- **Engineering checks** — frost-depth foundation check; foundation ring drain.
- **Sheets & exchange** — site area balance (ТЭП); SPDS sheet + title block; Revit points CSV.

## Architecture

Three layers, so other countries' standards can be added without touching the
engineering or Rhino code:

| Layer | File | Responsibility |
|---|---|---|
| Core | `earthwork_core.py` | Geometry/math, language- and country-neutral, unit-tested. |
| Adapter | `rhino_adapter.py` | Universal RhinoCommon plumbing; takes layer plans/labels as parameters. |
| Standards | `standards.py` | All country/code-specific rules, text, citations and SPDS layer plans behind a `Standard` interface. |

The components are thin glue. All inputs are single-value (item access). Geometry
is in document units; every component reads the model unit before calculating
(mm/cm/m/inch/foot), grid sizes are entered in **metres** and volumes reported in
**cubic metres**. Outputs are stamped with the tool version and the active
standard's regulation editions — see
[Standards › Provenance](https://github.com/Anton1oK/EarthworkGH/wiki/Standards#provenance).

## Quick start

Paste one loader into a Rhino 8 Grasshopper Python 3 component:

- **Local:** `loaders/gh_dynamic_loader.py` + a File Path pointing at a script in
  `gh_components/`.
- **From GitHub:** `loaders/gh_remote_loader.py` + a panel naming the component
  (e.g. `gh_01_cut_fill_cartogram`). It defaults to this repo.

Full steps and unit/type-hint notes are in the
[Installation guide](https://github.com/Anton1oK/EarthworkGH/wiki/Installation).

## Standards

Two standards ship: `RU` (Russian SPDS / ГОСТ / СП, the default) and `INT`
(generic metric, English — proves the multi-country design). Select one with the
`gh_00_standard` component. All country-specific rules, text and layer plans live
in `standards.py`; add a country by subclassing `Standard` and registering it. See
the [Standards page](https://github.com/Anton1oK/EarthworkGH/wiki/Standards).

## Project

- **Repository layout:** [docs/STRUCTURE.md](docs/STRUCTURE.md) — and why the
  importable modules stay at the repo root.
- **Roadmap:** [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md).
- **Standards boundaries:** [docs/REGULATORY_BASIS.md](docs/REGULATORY_BASIS.md).
- **Contributing & branches:** [CONTRIBUTING.md](CONTRIBUTING.md) — `main`
  (released) / `develop` (integration) / feature branches.
- **Changelog:** [CHANGELOG.md](CHANGELOG.md).
- **License:** [proprietary, all rights reserved](LICENSE).

## Local verification

```powershell
python -m pytest          # same suite CI runs (3.9 / 3.11 / 3.12)
python -m compileall .
```
