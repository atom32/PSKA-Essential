from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pska_essential.audit import audit_event
from pska_essential.governance import AUTO_APPLY, MANUAL_REVIEW, build_workspace_policy_from_env
from pska_essential.runtime_context import build_runtime_workspace_context


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

    def test_runtime_workspace_context_is_explicit_when_unconfigured(self):
        with patch.dict(os.environ, {}, clear=True):
            context = build_runtime_workspace_context()
        self.assertEqual(context.workspace_id, "default")
        self.assertFalse(context.workspace_configured)
        self.assertEqual(context.tenant_id, "")
        self.assertFalse(context.tenant_configured)

    def test_audit_event_includes_workspace_context(self):
        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-a", "PSKA_TENANT_ID": "tenant-a"},
            clear=True,
        ):
            event = audit_event("workflow.start", "workflow", "run-1")
        self.assertEqual(event.metadata["workspace_id"], "workspace-a")
        self.assertEqual(event.metadata["tenant_id"], "tenant-a")
        self.assertTrue(event.metadata["workspace_configured"])
        self.assertTrue(event.metadata["tenant_configured"])


if __name__ == "__main__":
    unittest.main()
