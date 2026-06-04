from __future__ import annotations

import unittest
from unittest import mock

import gh_component_setup


class _Document:
    def ScheduleSolution(self, _delay, callback):
        callback(self)


class _Component:
    def __init__(self):
        self.expire_calls = []
        self.document = _Document()

    def OnPingDocument(self):
        return self.document

    def ExpireSolution(self, recompute):
        self.expire_calls.append(recompute)


class _GhEnv:
    def __init__(self):
        self.Component = _Component()


class ScheduledIoUpdateTests(unittest.TestCase):
    def test_recompute_is_requested_after_successful_schema_update(self):
        ghenv = _GhEnv()
        with mock.patch.object(gh_component_setup, "ensure_io", return_value=True):
            with mock.patch.object(gh_component_setup, "io_matches", return_value=True):
                scheduled = gh_component_setup.schedule_ensure_io(ghenv, (), ())

        self.assertTrue(scheduled)
        self.assertEqual(ghenv.Component.expire_calls, [False])

    def test_no_recompute_loop_when_schema_update_does_not_converge(self):
        ghenv = _GhEnv()
        with mock.patch.object(gh_component_setup, "ensure_io", return_value=True):
            with mock.patch.object(gh_component_setup, "io_matches", return_value=False):
                scheduled = gh_component_setup.schedule_ensure_io(ghenv, (), ())

        self.assertTrue(scheduled)
        self.assertEqual(ghenv.Component.expire_calls, [])

    def test_no_recompute_when_schema_did_not_change(self):
        ghenv = _GhEnv()
        with mock.patch.object(gh_component_setup, "ensure_io", return_value=False):
            with mock.patch.object(gh_component_setup, "io_matches", return_value=True):
                scheduled = gh_component_setup.schedule_ensure_io(ghenv, (), ())

        self.assertTrue(scheduled)
        self.assertEqual(ghenv.Component.expire_calls, [])


if __name__ == "__main__":
    unittest.main()
