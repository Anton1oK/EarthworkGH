from __future__ import annotations

import json
import os
import tempfile
import unittest

import gh_remote


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RepoAndUrlTests(unittest.TestCase):
    def test_validate_repo_accepts_owner_name(self):
        self.assertEqual(gh_remote.validate_repo("anton/earthwork"), "anton/earthwork")

    def test_validate_repo_strips_url_and_git_suffix(self):
        self.assertEqual(
            gh_remote.validate_repo("https://github.com/anton/earthwork.git"),
            "anton/earthwork",
        )

    def test_validate_repo_rejects_garbage(self):
        for bad in ("", "no-slash", "a/b/c", "a b/c"):
            with self.assertRaises(ValueError):
                gh_remote.validate_repo(bad)

    def test_raw_url_is_well_formed(self):
        self.assertEqual(
            gh_remote.raw_url("anton/earthwork", "main", "gh_components/gh_01.py"),
            "https://raw.githubusercontent.com/anton/earthwork/main/gh_components/gh_01.py",
        )

    def test_raw_url_defaults_ref_to_main(self):
        self.assertIn("/main/", gh_remote.raw_url("a/b", "", "version.py"))


class ComponentNameTests(unittest.TestCase):
    def test_bare_name(self):
        self.assertEqual(
            gh_remote.normalize_component("gh_01_cut_fill_cartogram"),
            "gh_components/gh_01_cut_fill_cartogram.py",
        )

    def test_with_extension(self):
        self.assertEqual(
            gh_remote.normalize_component("gh_01_cut_fill_cartogram.py"),
            "gh_components/gh_01_cut_fill_cartogram.py",
        )

    def test_with_folder(self):
        self.assertEqual(
            gh_remote.normalize_component("gh_components/gh_06_topsoil.py"),
            "gh_components/gh_06_topsoil.py",
        )

    def test_empty_is_rejected(self):
        with self.assertRaises(ValueError):
            gh_remote.normalize_component("   ")


class CacheAndManifestTests(unittest.TestCase):
    def test_cache_dir_is_namespaced_and_safe(self):
        path = gh_remote.cache_dir("/tmp", "anton/earthwork", "v0.8.0")
        self.assertIn("earthwork_studio_gh", path)
        self.assertIn("anton_earthwork", path)
        self.assertTrue(path.endswith("v0.8.0"))

    def test_manifest_paths_dedup_and_order(self):
        manifest = {
            "modules": ["a.py", "b.py", "a.py"],
            "components": ["gh_components/c.py"],
        }
        self.assertEqual(
            gh_remote.manifest_paths(manifest),
            ["a.py", "b.py", "gh_components/c.py"],
        )

    def test_parse_schema_reads_io(self):
        source = (
            "COMPONENT_INPUTS = (('boundary', 'curve', 'item'),)\n"
            "COMPONENT_OUTPUTS = (('fill_m3', 'number', 'item'),)\n"
            "x = 1\n"
        )
        inputs, outputs = gh_remote.parse_schema(source)
        self.assertEqual(inputs[0][0], "boundary")
        self.assertEqual(outputs[0][0], "fill_m3")

    def test_parse_schema_requires_both(self):
        with self.assertRaises(ValueError):
            gh_remote.parse_schema("COMPONENT_INPUTS = ()\n")


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "modules": ["earthwork_core.py", "gh_remote.py"],
            "components": ["gh_components/gh_01_cut_fill_cartogram.py"],
        }
        self.calls = []

    def _fetch(self, url):
        self.calls.append(url)
        return "# fetched from {}\n".format(url)

    def test_sync_writes_all_files_then_caches(self):
        with tempfile.TemporaryDirectory() as dest:
            result = gh_remote.sync(
                "anton/earthwork", "main", dest, self._fetch, manifest=self.manifest
            )
            self.assertEqual(result["downloaded"], 3)
            self.assertTrue(os.path.exists(os.path.join(dest, "earthwork_core.py")))
            self.assertTrue(
                os.path.exists(os.path.join(dest, "gh_components", "gh_01_cut_fill_cartogram.py"))
            )
            # second sync without refresh downloads nothing (cache hit)
            again = gh_remote.sync(
                "anton/earthwork", "main", dest, self._fetch, manifest=self.manifest
            )
            self.assertEqual(again["downloaded"], 0)
            # refresh re-downloads every file
            forced = gh_remote.sync(
                "anton/earthwork", "main", dest, self._fetch,
                refresh=True, manifest=self.manifest,
            )
            self.assertEqual(forced["downloaded"], 3)

    def test_fetch_manifest_falls_back_when_missing(self):
        def boom(_url):
            raise RuntimeError("404")

        manifest = gh_remote.fetch_manifest("anton/earthwork", "main", boom)
        self.assertEqual(manifest, gh_remote.DEFAULT_MANIFEST)


class ManifestIntegrityTests(unittest.TestCase):
    """The shipped manifest.json must match the files actually in the repo."""

    def setUp(self):
        with open(os.path.join(PROJECT_ROOT, "manifest.json"), encoding="utf-8") as handle:
            self.manifest = json.load(handle)

    def test_every_listed_file_exists(self):
        for rel in gh_remote.manifest_paths(self.manifest):
            self.assertTrue(
                os.path.exists(os.path.join(PROJECT_ROOT, *rel.split("/"))),
                "manifest lists a missing file: {}".format(rel),
            )

    def test_every_component_is_listed(self):
        on_disk = {
            "gh_components/" + name
            for name in os.listdir(os.path.join(PROJECT_ROOT, "gh_components"))
            if name.endswith(".py")
        }
        listed = set(self.manifest["components"])
        self.assertEqual(
            on_disk,
            listed,
            "manifest components out of sync with gh_components/ "
            "(missing: {}; extra: {})".format(on_disk - listed, listed - on_disk),
        )

    def test_manifest_version_matches_tool(self):
        import version

        self.assertEqual(self.manifest["version"], version.__version__)


if __name__ == "__main__":
    unittest.main()
