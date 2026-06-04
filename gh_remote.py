"""Remote-loading helpers: fetch Earthwork Studio components from GitHub.

Pure and Rhino-free so URL building, cache paths, manifest handling and the
component-schema parse are unit-tested. The network fetch is passed in as a
callable, so this module imports no networking at load time and the whole sync
can be tested offline with a fake fetcher.

The Grasshopper-side bootstrap lives in ``gh_remote_loader.py``; it downloads
this file first, then delegates here.
"""

from __future__ import annotations

import ast
import json
import os
import re


RAW_HOST = "https://raw.githubusercontent.com"

# Used when the repo has no manifest.json yet; ``components`` is then left to the
# repo's manifest. Keep ``modules`` in sync with the importable root modules.
DEFAULT_MANIFEST = {
    "name": "Earthwork Studio GH",
    "modules": [
        "earthwork_core.py",
        "rhino_adapter.py",
        "standards.py",
        "version.py",
        "gh_component_setup.py",
        "gh_remote.py",
    ],
    "components": [],
}

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def validate_repo(repo):
    """Normalise and validate an ``owner/name`` repo slug (or a github URL)."""

    repo = (repo or "").strip().strip("/")
    if repo.lower().startswith("https://github.com/"):
        repo = repo[len("https://github.com/"):].strip("/")
    if repo.lower().startswith("github.com/"):
        repo = repo[len("github.com/"):].strip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not _REPO_RE.match(repo):
        raise ValueError(
            "Set the GitHub repo as 'owner/name' (got {!r}).".format(repo)
        )
    return repo


def raw_url(repo, ref, path):
    """Build a raw.githubusercontent.com URL for a repo-relative file path."""

    repo = validate_repo(repo)
    ref = (ref or "main").strip().strip("/")
    path = str(path).strip().lstrip("/")
    return "{}/{}/{}/{}".format(RAW_HOST, repo, ref, path)


def normalize_component(name):
    """Accept ``gh_01_x`` / ``gh_01_x.py`` / ``gh_components/gh_01_x.py``.

    Returns the repo-relative path ``gh_components/<name>.py``.
    """

    text = str(name or "").strip().strip("/").replace("\\", "/")
    if text.lower().startswith("https://") or text.lower().startswith("github.com/"):
        text = text.rsplit("/", 1)[-1]  # tolerate a pasted URL: keep the file name
    if not text:
        raise ValueError(
            "Connect the component name, e.g. 'gh_01_cut_fill_cartogram'."
        )
    if not text.endswith(".py"):
        text += ".py"
    if not text.startswith("gh_components/"):
        text = "gh_components/" + os.path.basename(text)
    return text


def _safe(part):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(part))


def cache_dir(tmp_root, repo, ref):
    """A stable per-repo, per-ref cache folder under ``tmp_root``."""

    return os.path.join(
        tmp_root,
        "earthwork_studio_gh",
        _safe(validate_repo(repo)),
        _safe((ref or "main").strip()),
    )


def manifest_paths(manifest):
    """All repo-relative file paths in a manifest (modules then components)."""

    ordered = list(manifest.get("modules", [])) + list(manifest.get("components", []))
    seen = set()
    paths = []
    for entry in ordered:
        rel = str(entry).strip().lstrip("/")
        if rel and rel not in seen:
            seen.add(rel)
            paths.append(rel)
    return paths


def parse_schema(source, filename="<remote component>"):
    """Read COMPONENT_INPUTS / COMPONENT_OUTPUTS from component source text."""

    inputs = None
    outputs = None
    tree = ast.parse(source, filename=filename)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "COMPONENT_INPUTS":
                inputs = ast.literal_eval(node.value)
            if isinstance(target, ast.Name) and target.id == "COMPONENT_OUTPUTS":
                outputs = ast.literal_eval(node.value)
    if inputs is None or outputs is None:
        raise ValueError(
            "Remote component must define COMPONENT_INPUTS and COMPONENT_OUTPUTS."
        )
    return tuple(inputs), tuple(outputs)


def fetch_manifest(repo, ref, fetch):
    """Fetch and parse manifest.json from the repo; fall back to a default."""

    try:
        data = json.loads(fetch(raw_url(repo, ref, "manifest.json")))
        if isinstance(data, dict) and data.get("modules"):
            return data
    except Exception:
        pass
    return dict(DEFAULT_MANIFEST)


def sync(repo, ref, dest, fetch, refresh=False, manifest=None):
    """Mirror the manifest's files from GitHub into ``dest``.

    ``fetch(url) -> text`` does the download (injected so this is testable).
    Files already present are skipped unless ``refresh`` is true. Returns a dict
    with ``dest``, ``manifest``, the ``files`` list and the ``downloaded`` count.
    """

    repo = validate_repo(repo)
    if manifest is None:
        manifest = fetch_manifest(repo, ref, fetch)
    paths = manifest_paths(manifest)
    downloaded = 0
    for rel in paths:
        target = os.path.join(dest, *rel.split("/"))
        if refresh or not os.path.exists(target):
            text = fetch(raw_url(repo, ref, rel))
            folder = os.path.dirname(target)
            if folder and not os.path.isdir(folder):
                os.makedirs(folder)
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(text)
            downloaded += 1
    return {
        "dest": dest,
        "manifest": manifest,
        "files": paths,
        "downloaded": downloaded,
    }
