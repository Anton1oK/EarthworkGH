# Earthwork Studio GH

Grasshopper tools for early-stage house-site earthworks in Rhino 8. The kit edits
a 2.5D terrain mesh, compares existing and proposed relief, produces an earth-mass
cartogram and drawing geometry, and adds drainage, slope, excavation, section,
accounting, checks, sheets and exchange tools — with Russian SPDS (ГОСТ/СП)
graphic outputs and explicit compliance notes.

> This is a design-assistance toolkit. It does **not** replace engineering
> surveys, geotechnical input, a licensed designer, or approval of working
> documentation. The engineering checks never certify adequacy.

## Start here

- **[Installation](Installation)** — paste one loader into a Grasshopper Python 3
  component and run any tool straight from GitHub.
- **[Component Reference](Component-Reference)** — every component with its full
  inputs and outputs.
- **[Workflows](Workflows)** — the cut/fill loop, baking to drawing layers, and
  assembling a genplan / organization-of-relief (ПОР) sheet.
- **[Standards](Standards)** — what the `RU` (Russian SPDS), `US` (imperial) and
  `INT` (generic metric) standards implement: citations, rule tables, checks and
  layer plans.

## How it is built

Three layers, so other countries' standards can be added without touching the
engineering or Rhino code:

| Layer | File | Responsibility |
|---|---|---|
| Core | `earthwork_core.py` | Geometry/math, language- and country-neutral, unit-tested. |
| Adapter | `rhino_adapter.py` | Universal RhinoCommon plumbing; takes layer plans/labels as parameters. |
| Standards | `standards.py` | All country/code-specific rules, text, citations and SPDS layer plans behind a `Standard` interface. |

The 24 components are thin glue: they read inputs, call the core/adapter for
geometry, and pull text/rules/layers from the active standard. All component
inputs are single-value (item access).

## Conventions

- **Units:** geometry is in document units; **every component reads and checks
  the model unit itself** before calculating (mm/cm/m/inch/foot all work) — there
  is no separate units node. Grid sizes are entered in **metres** and volumes are
  reported in **cubic metres**; the volume components warn if the document is
  unitless.
- **Standard selection:** [`gh_00_standard`](Component-Reference#gh_00_standard--select-the-country--standard)
  sets the active country once; it persists across components.
- **Baking:** most drawing components have a `bake` toggle that writes their
  output onto named SPDS layer groups (idempotent re-bake). See
  [Workflows](Workflows).
- **Never-certify:** the slope and foundation checks are working aids with
  mandatory non-certification notes; they force a review when groundwater,
  surcharge or excessive depth apply.

## Provenance

Every output is traceable to a tool version plus the exact regulation editions a
standard encodes, e.g.
`Earthwork Studio GH v0.8.0 - standard RU: ГОСТ 21.508-2020, СП 45.13330.2017,
...; checked 2026-06`. See [Standards › Provenance](Standards#provenance).
