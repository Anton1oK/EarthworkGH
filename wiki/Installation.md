# Installation

You need Rhino 8 with the Grasshopper **Python 3** script component. A component
runs straight from this repository — no local checkout needed.

## Run a component from GitHub

1. Open [`loaders/gh_remote_loader.py`](https://github.com/Anton1oK/EarthworkGH/blob/main/loaders/gh_remote_loader.py)
   and copy its contents into one Grasshopper **Python 3** script component.
   It already defaults to `GITHUB_REPO = "Anton1oK/EarthworkGH"` and
   `GITHUB_REF = "main"`. For a reproducible pin, set `GITHUB_REF` to a release
   tag such as `v0.8.0`.
2. Pick the component: **leave the first input empty and recompute** — the loader
   downloads the manifest and attaches a **drop-down of all components** to the
   first input. Select one (or, if you prefer, connect a text panel with the
   name, e.g. `gh_01_cut_fill_cartogram`).
3. Recompute again. The loader sets the input/output sockets and runs the
   component. Inputs that have a fixed set of values (e.g. `standard_code`,
   `soil_class`, `sheet`) also come up as drop-downs.

**Updates are automatic.** With `AUTO_UPDATE = True` (the default), the loader
compares the repo's `manifest.json` version to the cached one on each recompute
and re-downloads when a new release was published — so you rarely touch `REFRESH`
(which forces a full re-download regardless). The loader mirrors every listed
module and component into a cache, and falls back to it when offline.

> Use the **Python 3** script component, not the legacy IronPython GhPython one —
> the loader uses Python-3 networking and syntax.

## Requirements & troubleshooting

- **Internet access from Rhino.** The loader downloads from
  `raw.githubusercontent.com`; a proxy, VPN or firewall can block it. If the
  download fails the loader raises a message naming the reason and a checklist.
- **SSL.** Rhino's bundled Python sometimes cannot reach a usable certificate
  store on Windows; the loader automatically retries the download without
  certificate verification (the repo is public and read-only).
- **Public repo.** The files must be reachable anonymously over
  `raw.githubusercontent.com`.
- **Type hints.** On some builds the script component does not auto-assign type
  hints. If a **Curve** or **Mesh** input arrives as a `Guid`, set that input's
  type hint manually (right-click the input → *Type hint* → Curve / Mesh). All
  inputs are single-value (**item** access).

## Model units

Every component reads and checks the active document's unit itself before
calculating — there is no separate units node. The kit works in millimetres,
centimetres, metres, inches or feet; grid sizes are entered in metres and volumes
reported in cubic metres. If the document is unitless the volume components warn
rather than silently assuming metres, so set the Rhino document units before
relying on a quantity.

## Running the tests (developers)

```
python -m pytest
```

The pure-Python suite runs offline (no Rhino) on Python 3.9 / 3.11 / 3.12, the
same matrix CI uses. The Rhino smoke test (`tests/rhino_smoke_test.py`) must run
inside Rhino and is excluded from the offline run.
