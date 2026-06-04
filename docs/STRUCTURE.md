# Repository structure

```
EarthworkGH/
├── README.md                 # overview, components, install, workflow
├── LICENSE                   # proprietary, all rights reserved
├── CHANGELOG.md              # release notes
├── CONTRIBUTING.md           # branching model + contribution rules
├── manifest.json             # modules + components the remote loader mirrors
├── pytest.ini                # test config (offline / CI)
├── example_component.py      # generic demo target for the local loader (root)
│
├── earthwork_core.py         # ── importable modules (MUST stay at repo root) ──
├── rhino_adapter.py          #    universal RhinoCommon plumbing
├── standards.py              #    all country/code-specific rules + layers
├── version.py                #    tool name/version + provenance
├── gh_component_setup.py     #    Grasshopper IO setup used by the loaders
├── gh_remote.py              #    remote-fetch helpers (pure, unit-tested)
│
├── gh_components/            # the 25 components (gh_00_* .. gh_23_*)
├── loaders/                  # entry points pasted into a GH Python component
│   ├── gh_dynamic_loader.py        # load a component from a local checkout
│   ├── gh_remote_loader.py         # load a component straight from GitHub
│   └── gh_dynamic_loader_template.py
├── docs/                     # planning + reference docs (this file, plan, regs)
├── tests/                    # pure-Python unit tests + the Rhino smoke test
└── .github/                  # CI workflow, PR template
```

## Why the modules live at the repository root

The Grasshopper components import their dependencies by **bare name**
(`import earthwork_core`, `import standards`, ...). Two mechanisms rely on that:

1. **Local loader** - each component derives its project folder from its own
   location (`dirname(dirname(__file__))`) and adds it to `sys.path`, so the root
   modules import directly.
2. **Remote loader** - `gh_remote.sync` mirrors every `manifest.json` module into
   the cache **root** and every component into `cache/gh_components/`, reproducing
   this same flat layout so the bare-name imports resolve offline.

Moving the modules into a `src/` package would break both. Grouping that does not
touch importability - `docs/`, `loaders/`, `.github/`, `tests/` - is fine; the
importable modules and `gh_components/` stay where the loaders expect them.

## Three-layer architecture

- `earthwork_core.py` - geometry/math, language- and country-neutral.
- `rhino_adapter.py` - universal Rhino plumbing (takes layer plans as parameters).
- `standards.py` - every country/code-specific rule, string, citation and layer
  plan, behind the `Standard` interface (`RU` default, `INT` generic).

See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for the roadmap and
[REGULATORY_BASIS.md](REGULATORY_BASIS.md) for standards boundaries.
