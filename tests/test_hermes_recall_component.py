from __future__ import annotations

import io
import json
import unittest
from urllib.error import HTTPError

from pska_essential.hermes_recall_component import build_hermes_recall_component_status


class _Response:
    status = 200

    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class HermesRecallComponentTests(unittest.TestCase):
    def test_disabled_without_base_url_and_token(self):
        status = build_hermes_recall_component_status(environ={}, probe=True)

        self.assertEqual(status["schema"], "pska.hermes_recall_component_status.v1")
        self.assertEqual(status["status"], "disabled")
        self.assertEqual(status["mode"], "disabled")
        self.assertFalse(status["runtime"]["browser_extension_direct_history_allowed"])
        self.assertFalse(status["runtime"]["whole_recent_history_injected"])
        self.assertFalse(status["endpoints"]["probed"])

    def test_probe_uses_token_provider_without_exposing_secret(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["token"] = request.headers.get("X-pska-recall-token") or request.headers.get("X-PSKA-Recall-Token")
            captured["timeout"] = timeout
            return _Response({"schema": "hermes.pska_conversation_recall.v1", "items": []})

        status = build_hermes_recall_component_status(
            environ={
                "PSKA_HERMES_WEBUI_BASE_URL": "http://127.0.0.1:8787",
                "PSKA_HERMES_RECALL_TOKEN": "secret-token",
                "PSKA_DIAGNOSTICS_TIMEOUT": "2",
            },
            probe=True,
            urlopen_fn=fake_urlopen,
        )

        self.assertEqual(status["status"], "configured")
        self.assertEqual(status["mode"], "token_provider_verified")
        self.assertEqual(captured["url"], "http://127.0.0.1:8787/api/pska/conversations/search")
        self.assertEqual(captured["token"], "secret-token")
        self.assertEqual(status["endpoints"]["response_schema"], "hermes.pska_conversation_recall.v1")
        self.assertNotIn("secret-token", json.dumps(status))

    def test_probe_reports_missing_provider_route(self):
        def fake_urlopen(_request, timeout):
            raise HTTPError("http://127.0.0.1:8787/api/pska/conversations/search", 404, "missing", {}, io.BytesIO())

        status = build_hermes_recall_component_status(
            environ={
                "PSKA_HERMES_WEBUI_BASE_URL": "http://127.0.0.1:8787",
                "PSKA_HERMES_RECALL_TOKEN": "secret-token",
            },
            probe=True,
            urlopen_fn=fake_urlopen,
        )

        self.assertEqual(status["status"], "error")
        self.assertEqual(status["mode"], "token_provider_unreachable")
        self.assertEqual(status["endpoints"]["http_status"], 404)
        self.assertIn("install_or_restart_hermes_recall_provider", [item["action"] for item in status["next_actions"]])

    def test_legacy_password_fallback_is_warning(self):
        status = build_hermes_recall_component_status(
            environ={
                "PSKA_HERMES_WEBUI_BASE_URL": "http://127.0.0.1:8787",
                "PSKA_HERMES_LEGACY_RECALL_FALLBACK": "1",
                "PSKA_HERMES_WEBUI_PASSWORD": "password",
            }
        )

        self.assertEqual(status["status"], "warning")
        self.assertEqual(status["mode"], "legacy_password_fallback")
        self.assertTrue(status["configuration"]["legacy_fallback_enabled"])
        self.assertIn("disable_legacy_hermes_password_fallback", [item["action"] for item in status["next_actions"]])


if __name__ == "__main__":
    unittest.main()
