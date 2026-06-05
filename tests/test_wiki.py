from __future__ import annotations

import os
import re
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class WikiComponentCoverageTests(unittest.TestCase):
    """wiki/Component-Reference.md must document exactly the components that exist.

    The wiki source lives in wiki/ and is auto-published to the GitHub wiki on
    push to main; this test keeps it from drifting out of sync with the code.
    """

    def setUp(self):
        path = os.path.join(PROJECT_ROOT, "wiki", "Component-Reference.md")
        with open(path, encoding="utf-8") as handle:
            reference = handle.read()
        self.headings = set(re.findall(r"^### (gh_\S+)", reference, re.MULTILINE))
        self.components = {
            os.path.splitext(name)[0]
            for name in os.listdir(os.path.join(PROJECT_ROOT, "gh_components"))
            if name.endswith(".py")
        }

    def test_every_component_has_a_section(self):
        missing = self.components - self.headings
        self.assertEqual(missing, set(), "components not documented in the wiki: {}".format(missing))

    def test_no_section_for_a_missing_component(self):
        extra = self.headings - self.components
        self.assertEqual(extra, set(), "wiki documents components that do not exist: {}".format(extra))


if __name__ == "__main__":
    unittest.main()
