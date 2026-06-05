# Standards

All country/code-specific content — regulation text, calculation rules, soil and
slope tables, report wording, and SPDS layer names/colours — lives in
`standards.py` behind a `Standard` interface. The engineering core
(`earthwork_core.py`) and the Rhino plumbing (`rhino_adapter.py`) are neutral.

Three standards ship today; select one with
[`gh_00_standard`](Component-Reference#gh_00_standard--select-the-country--standard):

| Code | Name | Locale | Notes |
|---|---|---|---|
| `RU` | СПДС (ГОСТ/СП, Россия) | ru | Default. Full implementation. |
| `US` | United States (imperial) | en-US | Cubic yards / feet, OSHA / IBC / ADA. Full implementation. |
| `INT` | International (generic, metric) | en | English layers + cut/fill report; proves the multi-country design. |

---

## RU — Russian SPDS (default)

**Encoded editions (stamped on outputs):** ГОСТ 21.508-2020 · СП 45.13330.2017 ·
СП 82.13330.2016 · ГОСТ Р 21.101-2020 — *checked 2026-06*. Cut/fill volumes are
labelled `м3`. The cartogram uses the square method (ГОСТ 21.508-2020) with a
default 20 m grid; supported drawing-grid sides are **10, 20, 25, 40, 50 m** (a
finer grid is allowed as a working aid but flagged as off-standard).

### Soil classes

Used by the slope, frost and soil-balance tools.

| Class | Soil (RU) | Soil (EN) |
|---|---|---|
| 1 | Насыпные неслежавшиеся | Fill, uncompacted |
| 2 | Песчаные | Sand |
| 3 | Супесь | Sandy loam |
| 4 | Суглинок | Loam |
| 5 | Глина | Clay |
| 6 | Лёссовые | Loess |

### Bulking / shrinkage factors

`Кр` initial bulking (loose) and `Кор` residual bulking (compacted), used by
[`gh_14_soil_balance`](Component-Reference#gh_14_soil_balance--bulking--importexport).
Cut is measured in bank, fill in compacted; bank needed for fill = compacted ÷ Кор.

| Class | Кр (loose) | Кор (compacted) |
|---|---|---|
| 1 | 1.15 | 1.03 |
| 2 | 1.12 | 1.03 |
| 3 | 1.15 | 1.04 |
| 4 | 1.20 | 1.05 |
| 5 | 1.27 | 1.06 |
| 6 | 1.20 | 1.05 |

### Indicative temporary-slope table

Allowable slope as `1:m` (заложение) by excavation depth, used by
[`gh_07_slope_check`](Component-Reference#gh_07_slope_check--temporary-slope-assessment-aid)
(SP 45.13330.2017, indicative). Depths **over 5 m require a calculation** (no
indicative value). `0.0` means a vertical face is indicatively allowed at that
shallow depth.

| Class | ≤ 1.5 m | ≤ 3 m | ≤ 5 m |
|---|---|---|---|
| 1 | 0.67 | 1.00 | 1.25 |
| 2 | 0.50 | 1.00 | 1.00 |
| 3 | 0.25 | 0.67 | 0.85 |
| 4 | 0.00 | 0.50 | 0.75 |
| 5 | 0.00 | 0.25 | 0.50 |
| 6 | 0.00 | 0.50 | 0.50 |

### Frost depth

Design freezing depth `df = kh · d0 · √Mt`, where `Mt` is the freezing index (sum
of monthly sub-zero temperatures), `kh` the thermal factor (default 1.1), and `d0`
depends on soil. Used by
[`gh_20_foundation_check`](Component-Reference#gh_20_foundation_check--frost-depth-foundation-check)
(modelled on SP 22.13330.2016).

| Class | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| `d0`, m | 0.28 | 0.30 | 0.28 | 0.23 | 0.23 | 0.28 |

### Other rule values

- **Backfill** ([gh_08](Component-Reference#gh_08_backfill--bedding-backfill--compaction-schedule)):
  working space 0.6 m, bedding 0.1 m, compaction lift 0.3 m (defaults).
- **Blind area** ([gh_17](Component-Reference#gh_17_blind_area--blind-area-отмостка)):
  slope 1–10 % away from the building (СП 82.13330.2016).
- **Driveways** ([gh_18](Component-Reference#gh_18_driveway--drivewaypath-grades--compliance)):
  default max longitudinal grade 8 %; grades labelled in ‰.
- **Sheet sizes** ([gh_23](Component-Reference#gh_23_titleblock--spds-sheet-frame--title-block)):
  A4 210×297, A3 420×297, A2 594×420, A1 841×594, A0 1189×841 mm.
- **Title block rows:** Объект · Наименование листа · Стадия / Масштаб · Лист ·
  Разработал, дата (simplified ГОСТ Р 21.101).

### SPDS layer groups

Each baking component writes onto its own named parent layer with styled child
layers (colour + print weight): Картограмма земляных масс · Котлован · Разрез ·
Серия разрезов · Растительный слой · Рельеф · Водоотвод · Вертикальная
планировка · Проезды и дорожки · Дренаж · Оформление листа.

### Engineering checks never certify

The slope ([gh_07](Component-Reference#gh_07_slope_check--temporary-slope-assessment-aid))
and foundation ([gh_20](Component-Reference#gh_20_foundation_check--frost-depth-foundation-check))
checks are working aids and checklists. They are never "adequate/within allowable"
without `geotech_confirmed`, and groundwater, edge surcharge or excessive depth
force a review. Every report carries a mandatory non-certification note.

---

## INT — International (generic, metric)

A starter second standard that proves another country plugs in. It is metric and
English: English layer names, an English cut/fill report, table and warnings, and
English soil names, with **no GOST drawing-grid restriction** and volumes labelled
`m3`. It inherits RU's numeric rule tables (bulking, slope, frost) as generic
metric defaults. Its **edition stamp openly states "generic metric defaults — no
national code encoded"**, and its remaining report strings still inherit the
Russian text (a localisation to-do).

---

## US — United States (imperial)

**Encoded references (stamped on outputs):** OSHA 29 CFR 1926 Subpart P · IBC 2021
(frost line) · IRC R401/R403 · ADA / ICC A117.1 — *checked 2026-06*. Quantities
are in **cubic yards (CY)**, areas in **square feet (SF)**, lengths in **feet
(ft)**; the reports and the baked cartogram cell tags convert from the SI the core
computes (`Standard.volume_factor`). Layer names are English (inherited from INT).

**Inputs are imperial too.** Numeric length inputs — grid size, depths, widths,
elevations — are **entered in feet** and converted internally via
`Standard.input_length_factor`. (Volume inputs in `gh_15` and area inputs in
`gh_22` stay in SI, because they usually chain from other components' SI outputs;
their reports still display CY/SF.) Drop-downs are **standard-aware**: under US,
`soil_class` shows **OSHA Type A/B/C** and `sheet` shows **ANSI/ARCH** instead of
the RU defaults.

### Soil types (OSHA) and excavation slopes

`soil_class` maps to OSHA soil types. The max allowable slope is **H:V for
excavations up to 20 ft** (OSHA 1926 Subpart P, Appendix B); over 20 ft a
registered professional engineer must design the protective system.

| Class | OSHA type | Max slope (H : 1V) |
|---|---|---|
| 1 | Type A (cohesive, stable) | 0.75 : 1 |
| 2 | Type B (medium) | 1 : 1 |
| 3 | Type C (granular / unstable) | 1.5 : 1 |
| 4–6 | Type C (conservative) | 1.5 : 1 |

### Frost depth

The foundation check compares the footing depth to the **local frost line** —
enter `frost_depth_m` from the IBC / local code (a freezing-index formula is the
fallback). A footing below the frost line on frost-susceptible soil is adequate
(IBC 1809).

### Other rule values

- **Driveways / paths** ([gh_18](Component-Reference#gh_18_driveway--drivewaypath-grades--compliance)):
  default max grade 12 %; ADA accessible route ≤ 5 %, ramp ≤ 8.33 %. Grades in %.
- **Perimeter grading** ([gh_17](Component-Reference#gh_17_blind_area--blind-area-отмостка)):
  grade away from the building ≥ 5 % for the first 10 ft (IRC R401.3).
- **Foundation drain** ([gh_21](Component-Reference#gh_21_foundation_drain--foundation-ring-drain)):
  slope to outfall ≥ 0.5 % (IRC R405).
- **Sheet sizes** ([gh_23](Component-Reference#gh_23_titleblock--spds-sheet-frame--title-block)):
  ANSI A–E and ARCH A–E (default ARCH D, 36×24 in); ISO A-series also accepted.
- **Bulking**: swell / shrinkage per soil (indicative; confirm with the soils report).

Like RU, the slope and foundation checks are working aids that **never certify** —
they force a review on groundwater, surcharge, over-20-ft depth, or unconfirmed
geotech.

---

## Provenance

Every output is traceable. The neutral tool version lives in `version.py`
(`Earthwork Studio GH v0.9.0`); each standard declares the regulation editions it
encodes (`regulations`) and when they were last reviewed (`checked_on`).
`version.provenance(standard)` combines them, e.g.:

```
Earthwork Studio GH v0.9.0 - standard US: OSHA 29 CFR 1926 Subpart P,
IBC 2021 (frost line), IRC R401/R403, ADA / ICC A117.1; checked 2026-06
```

It is shown by [`gh_00_standard`](Component-Reference#gh_00_standard--select-the-country--standard)
and stamped onto the sheet by
[`gh_23_titleblock`](Component-Reference#gh_23_titleblock--spds-sheet-frame--title-block).
The stamp records the encoded editions; it does **not** replace engineer review.

---

## Adding a country

1. Subclass `Standard` (or `RussianStandard` to reuse its numeric tables) in
   `standards.py`. Set `code`, `name`, `locale`, `regulations`, `checked_on` and
   `volume_label`.
2. Override only the rules, report text and layer groups that differ.
3. Register it in the `STANDARDS` dict.

No changes to the core, the adapter, or the 24 components are needed — they read
the active standard through `standards.get_standard()`, which honours the
[`gh_00_standard`](Component-Reference#gh_00_standard--select-the-country--standard)
selection.
