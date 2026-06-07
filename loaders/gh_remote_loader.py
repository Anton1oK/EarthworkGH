"""
Earthwork Studio GH - remote loader (run components straight from GitHub).

Paste this into one Rhino 8 Grasshopper Python 3 component. It downloads the
plugin's modules and the requested component from a GitHub repo, caches them
locally, then runs the component - no local checkout needed. Editing the repo and
toggling ``refresh`` (or recomputing) pulls the latest code.

Setup (once):
  1. Set GITHUB_REPO below to your "owner/name" (and GITHUB_REF to a branch or,
     for stability, a release tag like "v0.8.0"). With AUTO_UPDATE on (default),
     a new release (manifest.json version bump) is pulled automatically on the
     next recompute; REFRESH = True forces a full re-download regardless.
  2. Connect a text panel with the component name (e.g. "gh_01_cut_fill_cartogram")
     to the FIRST input.
  3. Recompute. The first pass downloads + sets the input/output sockets (the only
     loader socket is the component name; the rest are the component's own); the
     second pass runs the component.

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
GITHUB_REPO = "Anton1oK/EarthworkGH"   # owner/name of the repo to load from
GITHUB_REF = "main"       # branch or tag; a tag (e.g. "v0.8.0") is reproducible
REFRESH = False           # set True once to force a full re-download, then back
AUTO_UPDATE = True        # auto re-download when the repo's manifest version changes
# ---------------------------------------------------------------------------


def _fetch(url, attempts=4):
    """Download a text file over verified HTTPS, with retries.

    Tries the system certificate store, then certifi's bundle if available (Rhino's
    bundled Python sometimes lacks a usable store on Windows). Transient failures -
    TLS handshake timeouts, dropped connections - are retried with a short backoff,
    because raw.githubusercontent.com can be flaky and a full sync opens many
    connections.
    """

    import socket
    import ssl
    import time
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "EarthworkStudioGH"})
    contexts = [ssl.create_default_context()]
    try:
        import certifi

        contexts.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass

    last_error = None
    for attempt in range(attempts):
        for context in contexts:
            try:
                with urllib.request.urlopen(request, timeout=45, context=context) as response:
                    return response.read().decode("utf-8")
            except (urllib.error.URLError, ssl.SSLError, socket.timeout) as error:
                last_error = error
        if attempt < attempts - 1:
            time.sleep(2.0 * (attempt + 1))  # backoff between rounds
    raise RuntimeError(
        "Download failed after {} tries for {}: {}. Usually a transient network / "
        "proxy / firewall issue (TLS handshake) - recompute to retry. For a TLS "
        "certificate error, run 'pip install certifi' in Rhino's Python.".format(
            attempts, url, last_error
        )
    )


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
refresh = bool(_value("refresh", REFRESH))
component_name = _value("component", None)
if component_name is None:
    # On a fresh component the first input is the default variable `x`; connected
    # inputs are exposed as globals by nickname, so read it directly.
    component_name = _value("x", None)
if component_name is None:
    component_name = _peek_first_input()
component_name = str(component_name or "").strip()

if not repo:
    raise ValueError(
        "Set GITHUB_REPO at the top of the remote loader to your 'owner/name'."
    )
# component_name may be empty here - after syncing we offer a drop-down of the
# available components on the first input instead of erroring.

# Cache folder (stable per repo + ref, so recomputes do not re-download).
_cache = os.path.join(
    tempfile.gettempdir(), "earthwork_studio_gh", _safe(repo), _safe(ref)
)
if not os.path.isdir(_cache):
    os.makedirs(_cache)

# Make the cache importable before anything is downloaded into it.
if _cache not in sys.path:
    sys.path.insert(0, _cache)
_components_dir = os.path.join(_cache, "gh_components")
if _components_dir not in sys.path:
    sys.path.insert(0, _components_dir)

# Bootstrap (fetch gh_remote.py, then sync everything) - the only network steps.
_boot_repo = repo
if _boot_repo.lower().startswith("github.com/"):
    _boot_repo = _boot_repo[len("github.com/"):]
_boot_repo = _boot_repo.strip("/")

import json as _json

_cached_manifest_path = os.path.join(_cache, "manifest.json")
_effective_refresh = bool(refresh)

# Read the repo's manifest.json (sync needs it anyway). When AUTO_UPDATE is on,
# a version different from the cached one triggers a full re-download - so pushing
# a new release auto-updates on the next recompute. Offline falls back to cache.
_manifest = None
try:
    _manifest = _json.loads(
        _fetch("https://raw.githubusercontent.com/{}/{}/manifest.json".format(_boot_repo, ref))
    )
except Exception:
    _manifest = None

if AUTO_UPDATE and not _effective_refresh and _manifest is not None:
    _remote_version = str(_manifest.get("version", ""))
    _cached_version = ""
    try:
        if os.path.exists(_cached_manifest_path):
            with open(_cached_manifest_path, encoding="utf-8") as _handle:
                _cached_version = str(_json.load(_handle).get("version", ""))
    except Exception:
        _cached_version = ""
    if _remote_version and _remote_version != _cached_version:
        _effective_refresh = True

if _manifest is None and os.path.exists(_cached_manifest_path):
    try:
        with open(_cached_manifest_path, encoding="utf-8") as _handle:
            _manifest = _json.load(_handle)  # offline: reuse the cached manifest
    except Exception:
        _manifest = None

_boot = os.path.join(_cache, "gh_remote.py")
try:
    if _effective_refresh or not os.path.exists(_boot):
        _boot_url = "https://raw.githubusercontent.com/{}/{}/gh_remote.py".format(_boot_repo, ref)
        with open(_boot, "w", encoding="utf-8") as _handle:
            _handle.write(_fetch(_boot_url))

    import gh_remote

    gh_remote = importlib.reload(gh_remote)

    # Pull the manifest + all modules and components into the cache.
    _sync = gh_remote.sync(repo, ref, _cache, _fetch, refresh=_effective_refresh, manifest=_manifest)
    # Record the manifest (version + component list) ONLY after a successful sync,
    # so a failed update never marks the cache as up to date.
    try:
        _record = _manifest if _manifest is not None else _sync.get("manifest")
        if _record is not None:
            with open(_cached_manifest_path, "w", encoding="utf-8") as _handle:
                _json.dump(_record, _handle)
    except Exception:
        pass
except Exception as _err:
    # A fetch failed (e.g. a transient TLS handshake timeout during an update).
    # If the cache can still run the component, use it and warn rather than break;
    # only hard-fail when there is nothing usable cached.
    _cached_ok = os.path.exists(_boot) and _manifest is not None
    if _cached_ok and component_name:
        try:
            _cached_ok = os.path.exists(os.path.join(
                _cache, *gh_remote.normalize_component(component_name).split("/")))
        except Exception:
            _cached_ok = os.path.exists(_boot)
    if _cached_ok:
        try:
            import gh_remote
            gh_remote = importlib.reload(gh_remote)
        except Exception:
            _cached_ok = False
    if _cached_ok:
        _sync = {"manifest": _manifest, "downloaded": 0, "files": []}
        print("WARNING: could not reach GitHub ({}). Using the cached copy; "
              "recompute when the connection is back to finish updating.".format(_err))
    else:
        raise RuntimeError(
            "Remote loader could not fetch '{}@{}'. Reason: {}. Checklist: "
            "(1) Rhino has internet access (a proxy / VPN / firewall can block it); "
            "(2) the repo is public and the owner/name is correct; "
            "(3) the ref '{}' (branch or tag) exists.".format(repo, ref, _err, ref)
        )

import gh_component_setup

gh_component_setup = importlib.reload(gh_component_setup)

# Self-heal a stale cache: if the cached helper predates a function this loader
# needs, re-fetch just that one file (so a full REFRESH is not required).
if not hasattr(gh_component_setup, "schedule_value_lists"):
    try:
        with open(os.path.join(_cache, "gh_component_setup.py"), "w", encoding="utf-8") as _handle:
            _handle.write(_fetch(
                "https://raw.githubusercontent.com/{}/{}/gh_component_setup.py".format(_boot_repo, ref)
            ))
        gh_component_setup = importlib.reload(gh_component_setup)
    except Exception:
        pass


def _set_component_label(label):
    if "ghenv" not in globals():
        return
    component = ghenv.Component
    component.Name = label
    component.NickName = label
    component.Message = "{}@{}".format(label, ref)


def _execute_component(path, source, output_specs, input_aliases=None, standard=None):
    env = dict(globals())
    # Aliases map the displayed socket name (e.g. grid_size_ft / cut_cy under US)
    # back to the canonical name the component reads; convert the value from the
    # standard's display unit to SI where needed (volumes/areas).
    if input_aliases:
        for display_name, canonical_name in input_aliases.items():
            value = env.get(display_name)
            if standard is not None:
                try:
                    value = standard.from_display(canonical_name, value)
                except Exception:
                    pass
            env[canonical_name] = value
    env["__file__"] = path
    env["__name__"] = "__grasshopper_remote_component__"
    exec(compile(source, path, "exec"), env)
    # Surface outputs under the standard's socket label, converting SI values to
    # the display unit (m3 -> CY, m2 -> SF, m -> ft under US).
    for name, _type_name, _access in output_specs:
        value = env.get(name, None)
        display = name
        if standard is not None:
            try:
                display = standard.socket_label(name) or name
                value = standard.to_display(name, value)
            except Exception:
                display = name
        globals()[display] = value


# Component names in this repo (for the component drop-down on the first input).
_component_names = sorted(
    os.path.splitext(os.path.basename(_path))[0]
    for _path in _sync["manifest"].get("components", [])
)

if not component_name:
    # Nothing picked yet: offer a drop-down of components on the first input.
    _offered = False
    if "ghenv" in globals() and hasattr(gh_component_setup, "schedule_value_lists"):
        _offered = gh_component_setup.schedule_value_lists(
            ghenv, [(0, gh_component_setup.value_list_items(_component_names, True))]
        )
    if not _offered:
        raise ValueError(
            "Connect a panel with a component name (e.g. 'gh_01_cut_fill_cartogram') "
            "to the first input."
        )
    print("Pick a component from the drop-down on the first input, then recompute.")
else:
    # Read the requested component's source + schema from the cache.
    _component_rel = gh_remote.normalize_component(component_name)
    _component_path = os.path.join(_cache, *_component_rel.split("/"))
    with open(_component_path, "r", encoding="utf-8") as _handle:
        _component_source = _handle.read()
    component_inputs, component_outputs = gh_remote.parse_schema(
        _component_source, _component_path
    )

    _set_component_label(os.path.splitext(os.path.basename(_component_path))[0])

    # Active standard - used to relabel sockets (e.g. *_m -> *_ft under US) and to
    # supply standard-specific drop-down options.
    try:
        import standards as _standards
        _active_std = _standards.get_standard()
    except Exception:
        _active_std = None

    # Standard-aware socket labels. The component still reads the canonical name;
    # _execute_component aliases the renamed value back to it.
    def _label_of(_name):
        if _active_std is not None:
            try:
                return _active_std.socket_label(_name) or _name
            except Exception:
                return _name
        return _name

    _input_aliases = {}
    _display_inputs = []
    for _spec in component_inputs:
        _canon = _spec[0]
        _label = _label_of(_canon)
        if _label != _canon:
            _input_aliases[_label] = _canon
        _display_inputs.append((_label,) + tuple(_spec[1:]))

    _display_outputs = [(_label_of(_ospec[0]),) + tuple(_ospec[1:]) for _ospec in component_outputs]

    # One loader socket (the component name) + the component's own inputs/outputs,
    # relabeled to the active standard's units (e.g. fill_m3 -> fill_cy under US).
    loader_inputs = (("component", "string", "item"),) + tuple(_display_inputs)
    loader_outputs = tuple(_display_outputs)

    changed = False
    if "ghenv" in globals() and not gh_component_setup.io_matches(
        ghenv, inputs=loader_inputs, outputs=loader_outputs
    ):
        changed = gh_component_setup.schedule_ensure_io(
            ghenv, inputs=loader_inputs, outputs=loader_outputs
        )

    if not changed:
        # Sockets are in place - run the component and surface its outputs.
        _execute_component(
            _component_path, _component_source, component_outputs, _input_aliases, _active_std
        )
        # Offer drop-downs: components on the first input, plus any input that
        # declares options (a 5th element in its COMPONENT_INPUTS spec). The
        # active standard may override the options (e.g. US soil types / sheets).
        if "ghenv" in globals() and hasattr(gh_component_setup, "schedule_value_lists"):
            _vl_specs = [(0, gh_component_setup.value_list_items(_component_names, True))]
            for _spec in component_inputs:
                if len(_spec) >= 5 and _spec[4]:
                    _opts = None
                    if _active_std is not None:
                        try:
                            _opts = _active_std.input_options(_spec[0])
                        except Exception:
                            _opts = None
                    if not _opts:
                        _as_string = _spec[1] in ("string", "text", "str")
                        _opts = gh_component_setup.value_list_items(_spec[4], _as_string)
                    # Target the displayed socket name (unchanged for option inputs).
                    _vl_specs.append((_label_of(_spec[0]), _opts))
            gh_component_setup.schedule_value_lists(ghenv, _vl_specs)
