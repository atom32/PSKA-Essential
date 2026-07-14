from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pska_essential.governance import AUTO_APPLY, MANUAL_REVIEW, build_workspace_policy_from_env


class GovernancePolicyTests(unittest.TestCase):
    def test_default_policy_requires_manual_review(self):
        with patch.dict(os.environ, {}, clear=True):
            policy = build_workspace_policy_from_env()
        self.assertEqual(policy.durable_memory, MANUAL_REVIEW)
        self.assertEqual(policy.action_for("memory_patch"), MANUAL_REVIEW)
        self.assertEqual(policy.action_for("writing_brief"), "skip")

    def test_env_can_configure_auto_apply(self):
        with patch.dict(os.environ, {"PSKA_GOVERNANCE_DURABLE_MEMORY": AUTO_APPLY}, clear=True):
            policy = build_workspace_policy_from_env()
        self.assertEqual(policy.durable_memory, AUTO_APPLY)
        self.assertEqual(policy.action_for("memory_patch"), AUTO_APPLY)

    def test_invalid_policy_fails_explicitly(self):
        with patch.dict(os.environ, {"PSKA_GOVERNANCE_DURABLE_MEMORY": "silent_magic"}, clear=True):
            with self.assertRaisesRegex(ValueError, "PSKA_GOVERNANCE_DURABLE_MEMORY"):
                build_workspace_policy_from_env()


if __name__ == "__main__":
    unittest.main()
