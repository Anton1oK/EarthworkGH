"""
Earthwork Studio GH - remote loader (run components straight from GitHub).

Paste this into one Rhino 8 Grasshopper Python 3 component. It downloads the
plugin's modules and the requested component from a GitHub repo, caches them
locally, then runs the component - no local checkout needed. Editing the repo and
toggling ``refresh`` (or recomputing) pulls the latest code.

Setup (once):
  1. Set GITHUB_REPO below to your "owner/name" (and GITHUB_REF to a branch or,
     for stability, a release tag like "v0.8.0").
  2. Connect a text panel with the component name (e.g. "gh_01_cut_fill_cartogram")
     to the FIRST input.
  3. Recompute. The first pass downloads + sets the input/output sockets; the
     second pass runs the component. After that, the repo/ref/refresh sockets let
     you override per-instance.

Requires internet access from Rhino. The repo must be public (or the files
reachable via raw.githubusercontent.com).
"""

from __future__ import annotations

import importlib
import os
import re
import sys
import tempfile


# ---- configure once -------------------------------------------------------
GITHUB_REPO = ""          # e.g. "your-name/earthwork-studio-gh"
GITHUB_REF = "main"       # branch or tag; a tag (e.g. "v0.8.0") is reproducible
# ---------------------------------------------------------------------------


def _fetch(url):
    """Download a text file over HTTPS (verified). Raises on any failure."""

    import ssl
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "EarthworkStudioGH"})
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        return response.read().decode("utf-8")


def _peek_first_input():
    """Read the first GH input (component name) before sockets are configured."""

    if "ghenv" not in globals():
        return None
    try:
        component = ghenv.Component
        if component.Params.Input.Count < 1:
            return None
        volatile = component.Params.Input[0].VolatileData
        for branch_index in range(volatile.BranchCount):
            branch = volatile.get_Branch(branch_index)
            if branch is not None and branch.Count:
                item = branch[0]
                return getattr(item, "Value", item)
    except Exception:
        return None
    return None


def _value(name, default=None):
    raw = globals().get(name, None)
    if raw is None:
        return default
    raw = getattr(raw, "Value", raw)
    return raw if raw is not None else default


def _safe(part):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(part))


# Resolve configuration: explicit sockets win, else the constants above.
repo = str(_value("repo", "") or GITHUB_REPO).strip()
ref = str(_value("ref", "") or GITHUB_REF).strip() or "main"
refresh = bool(_value("refresh", False))
component_name = _value("component", None)
if component_name is None:
    component_name = _peek_first_input()
component_name = str(component_name or "").strip()

if not repo:
    raise ValueError(
        "Set GITHUB_REPO at the top of the remote loader to your 'owner/name' "
        "(or connect a 'repo' input)."
    )
if not component_name:
    raise ValueError(
        "Connect a panel with the component name (e.g. 'gh_01_cut_fill_cartogram') "
        "to the first input."
    )

# Cache folder (stable per repo + ref, so recomputes do not re-download).
_cache = os.path.join(
    tempfile.gettempdir(), "earthwork_studio_gh", _safe(repo), _safe(ref)
)
if not os.path.isdir(_cache):
    os.makedirs(_cache)

# Bootstrap: fetch gh_remote.py itself, then let it sync everything else.
_boot_repo = repo
if _boot_repo.lower().startswith("github.com/"):
    _boot_repo = _boot_repo[len("github.com/"):]
_boot_repo = _boot_repo.strip("/")
_boot = os.path.join(_cache, "gh_remote.py")
if refresh or not os.path.exists(_boot):
    _boot_url = "https://raw.githubusercontent.com/{}/{}/gh_remote.py".format(_boot_repo, ref)
    with open(_boot, "w", encoding="utf-8") as _handle:
        _handle.write(_fetch(_boot_url))

if _cache not in sys.path:
    sys.path.insert(0, _cache)
_components_dir = os.path.join(_cache, "gh_components")
if _components_dir not in sys.path:
    sys.path.insert(0, _components_dir)

import gh_remote

gh_remote = importlib.reload(gh_remote)

# Pull the manifest + all modules and components into the cache.
_sync = gh_remote.sync(repo, ref, _cache, _fetch, refresh=refresh)

import gh_component_setup

gh_component_setup = importlib.reload(gh_component_setup)

# Read the requested component's source + schema from the cache.
_component_rel = gh_remote.normalize_component(component_name)
_component_path = os.path.join(_cache, *_component_rel.split("/"))
with open(_component_path, "r", encoding="utf-8") as _handle:
    _component_source = _handle.read()
component_inputs, component_outputs = gh_remote.parse_schema(_component_source, _component_path)


def _set_component_label(label):
    if "ghenv" not in globals():
        return
    component = ghenv.Component
    component.Name = label
    component.NickName = label
    component.Message = "{}@{}".format(label, ref)


def _execute_component(path, source, output_specs):
    env = dict(globals())
    env["__file__"] = path
    env["__name__"] = "__grasshopper_remote_component__"
    exec(compile(source, path, "exec"), env)
    for name, _type_name, _access in output_specs:
        globals()[name] = env.get(name, None)


_label = os.path.splitext(os.path.basename(_component_path))[0]
_set_component_label(_label)

# Config sockets first, then the component's own declared inputs.
loader_inputs = (
    ("component", "string", "item"),
    ("repo", "string", "item", True),
    ("ref", "string", "item", True),
    ("refresh", "boolean", "item", True),
) + tuple(component_inputs)
loader_outputs = tuple(component_outputs) + (
    ("loader_status", "string", "item"),
    ("loader_schema", "string", "item"),
)
loader_schema = "{} -> {} ({} inputs / {} outputs)".format(
    _component_rel, "{}@{}".format(repo, ref), len(loader_inputs), len(loader_outputs)
)

changed = False
if "ghenv" in globals():
    if gh_component_setup.io_matches(ghenv, inputs=loader_inputs, outputs=loader_outputs):
        changed = False
    else:
        changed = gh_component_setup.schedule_ensure_io(
            ghenv, inputs=loader_inputs, outputs=loader_outputs
        )

if not changed:
    _execute_component(_component_path, _component_source, component_outputs)
    loader_status = "Loaded {} from {}@{} (downloaded {} file(s)).".format(
        _label, repo, ref, _sync["downloaded"]
    )
else:
    loader_status = "Updated IO for {} (recompute to run).".format(_label)
