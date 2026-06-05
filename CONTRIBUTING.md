# Contributing

## Branching model

- **`main`** - stable, released code. Every commit here is taggable. The remote
  loader's default `GITHUB_REF` tracks `main`; release tags (e.g. `v0.8.0`) pin a
  reproducible version.
- **`develop`** - integration branch. Day-to-day work merges here first.
- **feature branches** - branch off `develop`, named `feature/<short-name>`,
  `fix/<short-name>` or `chore/<short-name>`. Open a pull request back into
  `develop`.

Release flow: when `develop` is stable, open a PR `develop -> main`, merge, then
tag the release (`git tag -a vX.Y.Z -m "..." && git push --tags`) and bump
`__version__` in `version.py` and `version` in `manifest.json`.

```
feature/x ─▶ develop ─▶ main ─▶ tag vX.Y.Z
```

## Before you open a PR

1. Run the tests: `python -m pytest` (must be green; CI runs them on 3.9/3.11/3.12).
2. Keep the architecture boundaries intact:
   - `earthwork_core.py` stays language- and country-neutral (no regulation text,
     no localised strings, no layer names).
   - `rhino_adapter.py` stays universal Rhino plumbing (takes layer plans/labels
     as parameters).
   - All country-specific rules, text, citations and layer plans live in
     `standards.py` behind the `Standard` interface.
3. Importable modules must remain at the repository root (the Grasshopper loaders
   import them by bare name and the remote loader mirrors them into its cache
   root). Do not move them into a package folder.
4. If you add or rename a component or module, update `manifest.json`
   (`tests/test_remote.py` enforces that it matches the files on disk).
5. Components use item-access inputs only (the target Rhino build does not
   reliably set list access on script inputs).
6. Documentation lives in `wiki/` (not the GitHub wiki directly). It is
   auto-published to the wiki on push to `main`; a test keeps
   `wiki/Component-Reference.md` in sync with the components.

See [docs/STRUCTURE.md](docs/STRUCTURE.md) for the repository layout and
[docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) for the roadmap.
