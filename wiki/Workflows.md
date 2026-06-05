# Workflows

## The cut/fill loop

```
[existing terrain mesh] ─▶ [gh_02_grade_pad] ─▶ proposed_mesh
          │                                          │
          └────────────▶ [gh_01_cut_fill_cartogram] ◀┘   (bake = true → drawing layers)
```

1. Start with a 2.5D existing terrain mesh and a closed site boundary.
2. Author the proposed surface — either edit the mesh directly, or use
   [`gh_02_grade_pad`](Component-Reference#gh_02_grade_pad--flat-grading-pad) for a
   flat building pad, and/or
   [`gh_16_grading`](Component-Reference#gh_16_grading--grading-surface-from-spot-elevations)
   for design spot elevations.
3. Feed both meshes + the boundary into
   [`gh_01_cut_fill_cartogram`](Component-Reference#gh_01_cut_fill_cartogram--spds-square-grid-cutfill)
   for the cartogram, per-cell volumes, totals and the quantity table.

Set the country once with
[`gh_00_standard`](Component-Reference#gh_00_standard--select-the-country--standard).
Each component reads the model unit itself, so make sure the Rhino document units
are set (mm/cm/m/inch/foot) before you trust a volume — the volume components warn
on a unitless document.

## Baking to drawing layers

Most drawing components have a `bake` boolean. Set it to `true` and the component
writes its in-memory geometry straight onto the active standard's named SPDS layer
group (parent layer + styled child layers), replacing the previous bake so it is
idempotent. Baking happens inside each component (rather than a separate node)
because some Rhino builds will not give script inputs list access.

Sheet production: bake → **Make2D** → layout → print.

## Assembling a genplan / organization-of-relief (ПОР) sheet

The components compose into a sheet rather than needing a single "assemble" node:

0. Pick the standard once with
   [`gh_00_standard`](Component-Reference#gh_00_standard--select-the-country--standard).
1. Author the proposed grades with
   [`gh_16_grading`](Component-Reference#gh_16_grading--grading-surface-from-spot-elevations)
   and tune `±0.000` with
   [`gh_19_mass_haul`](Component-Reference#gh_19_mass_haul--0000--mass-haul-optimiser)
   to balance cut/fill.
2. Add detail:
   [`gh_17_blind_area`](Component-Reference#gh_17_blind_area--blind-area-отмостка),
   [`gh_18_driveway`](Component-Reference#gh_18_driveway--drivewaypath-grades--compliance),
   drainage ([gh_11](Component-Reference#gh_11_drainage--flow-traces--ponding),
   [gh_12](Component-Reference#gh_12_ditch--ditch--swale-with-invert-marks),
   [gh_21](Component-Reference#gh_21_foundation_drain--foundation-ring-drain)) and
   relief reading ([gh_09](Component-Reference#gh_09_relief--slope-arrows--spot-elevations)
   spot heights/arrows, [gh_10](Component-Reference#gh_10_contours--proposed-contours)
   contours).
3. Quantities: feed the cut/fill
   ([gh_01](Component-Reference#gh_01_cut_fill_cartogram--spds-square-grid-cutfill)/[gh_05](Component-Reference#gh_05_serial_sections--serial-cross-sections--volumes)),
   topsoil ([gh_06](Component-Reference#gh_06_topsoil--topsoil-removal-plan)),
   backfill ([gh_08](Component-Reference#gh_08_backfill--bedding-backfill--compaction-schedule))
   and ditch ([gh_12](Component-Reference#gh_12_ditch--ditch--swale-with-invert-marks))
   volumes into
   [gh_14](Component-Reference#gh_14_soil_balance--bulking--importexport)/[gh_15](Component-Reference#gh_15_quantities--combined-bill-of-quantities)
   for the balance and the bill;
   [gh_22](Component-Reference#gh_22_site_balance--site-area-balance-тэп) for the ТЭП.
4. Bake everything onto the SPDS layer groups, drop a
   [gh_23](Component-Reference#gh_23_titleblock--spds-sheet-frame--title-block)
   frame + title block, then Make2D + layout + print.

Each component bakes to its own named layer group, so the layers compose into one
coherent, print-ready drawing tree.

## Exchanging terrain with Revit

[`gh_13_revit_points`](Component-Reference#gh_13_revit_points--terrain-points-csv-revit)
writes terrain points as a comma-delimited X,Y,Z file in metres. In Revit, import
it as a Toposurface (*Create from Import → Specify Points File*) or a Toposolid,
choosing **Meters** in the import dialog. The same export is the basis for
setting-out coordinates.
