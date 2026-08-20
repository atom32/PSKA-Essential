import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "integrations" / "hermes-webui-extension" / "pska-mini"


class HermesWebuiExtensionTests(unittest.TestCase):
    def test_manifest_describes_thin_pska_mini_package(self):
        manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["id"], "pska-mini")
        self.assertEqual(manifest["scripts"], ["pska-mini.js"])
        self.assertEqual(manifest["stylesheets"], ["pska-mini.css"])
        self.assertEqual(
            manifest["sidecar"],
            {
                "type": "loopback",
                "origin": "http://127.0.0.1:8765",
                "health_path": "/api/health",
            },
        )

    def test_extension_is_chip_only_and_uses_sidecar_bridge(self):
        script = (EXTENSION_DIR / "pska-mini.js").read_text(encoding="utf-8")

        self.assertIn("sidecarProxyBase(EXT_ID)", script)
        self.assertIn('const SKILL_NAME = "knowledge-retrieval"', script)
        self.assertIn("installApiBridge()", script)
        self.assertIn("installSendBridge()", script)
        self.assertIn("PSKA-Mini Runtime Scope", script)
        self.assertIn("pskaMiniDatasetList", script)
        self.assertIn("RAGFlow Probe", script)
        self.assertIn("Hermes 模块", script)
        self.assertIn("pskaMiniApplySuggestedScope", script)
        self.assertIn("pskaMiniSyncReviews", script)
        self.assertIn("pskaMiniCreateDigestTask", script)
        self.assertIn("pskaMiniJarvisBrief", script)
        self.assertIn("pskaMiniAgenticBrief", script)
        self.assertIn("Specialists:", script)
        self.assertIn("recommended_profiles", script)
        self.assertIn("pskaMiniSourceRecall", script)
        self.assertIn("buildForcedSkillMessage", script)
        self.assertIn("stripForcedSkillEnvelope", script)
        self.assertIn("[FORCED SKILL CONTEXT:", script)
        self.assertIn("GBrain", script)
        self.assertIn("gbrainComponent()", script)
        self.assertIn("dashboard.workspace?.components?.gbrain", script)
        self.assertIn('"/api/jarvis/briefing"', script)
        self.assertIn('"/api/agentic/context-brief"', script)
        self.assertIn("compact: true", script)
        self.assertIn('view: "webui"', script)
        self.assertIn("Refreshing PSKA workspace status", script)
        self.assertIn("isCompactComposer()", script)
        self.assertIn('"/api/sources/search"', script)
        self.assertIn("currentScopePayload()", script)
        self.assertIn("sourceRootIds", script)
        self.assertIn("pskaMiniSourceRootIds", script)
        self.assertIn("currentSourceScopePayload()", script)
        self.assertIn("source_root_ids: state.sourceRootIds", script)
        self.assertNotRegex(script, re.compile(r"source_scope:\s*\{\}"))
        self.assertIn("formatAgenticBrief", script)
        self.assertIn("候选内容", script)
        self.assertIn("PSKA 是权威来源", script)
        self.assertIn('const REVIEW_BOARD_SLUG = "pska-review"', script)
        self.assertIn('const DIGEST_TASK_NAME = "PSKA Digest Runner"', script)
        self.assertIn('"/api/profile/active"', script)
        self.assertIn('"/api/projects"', script)
        self.assertIn('"/api/workspaces"', script)
        self.assertIn('"/api/kanban/boards"', script)
        self.assertIn('"/api/kanban/tasks"', script)
        self.assertIn("/patch", script)
        self.assertIn('"/api/crons/create"', script)
        self.assertIn("idempotency_key", script)
        self.assertIn('"/api/chat/start"', script)
        self.assertIn('"/api/alpha/first-run-session"', script)
        self.assertIn('"/api/jobs/health?include_kb=false"', script)
        self.assertIn("jobHealthStatusLabel", script)
        self.assertIn("jobHealthCount", script)
        self.assertIn('"/api/wakeup/plan"', script)
        self.assertIn("wakeupStatusLabel", script)
        self.assertIn('"/api/observability/metrics?limit=300"', script)
        self.assertIn("observabilityMetricsStatusLabel", script)
        self.assertIn('"/api/sources/recall-eval?mode=fixture&limit=5"', script)
        self.assertIn("sourceRecallEvalStatusLabel", script)
        self.assertIn("First-run checklist", script)
        self.assertIn("pskaMiniFirstRun", script)
        self.assertIn("pskaMiniAnswerProofDetail", script)
        self.assertIn("Draft Memory Candidate", script)
        self.assertIn("hermes_answer_proof", script)
        self.assertIn("isUneditedAnswerProofDraft", script)
        self.assertIn("pskaMiniMemoryDraftSource", script)
        self.assertIn("pskaMiniChatgptMemorySummary", script)
        self.assertIn("importChatgptMemorySummary", script)
        self.assertIn('"/api/memory/chatgpt-summary/import"', script)
        self.assertIn("renderChatgptImportResult", script)
        self.assertIn("pskaMiniChatgptConversationPath", script)
        self.assertIn("importChatgptConversationArchive", script)
        self.assertIn('"/api/sources/chatgpt-conversations/import"', script)
        self.assertIn("renderChatgptConversationImportResult", script)
        self.assertNotIn("HermesChatStartHooks", script)
        self.assertNotIn("context_provider", script)
        self.assertNotRegex(script, re.compile(r'fetch\(["\']/api/pska/'))
        for forbidden in [
            "panelEidolia",
            "showing-eidolia",
            "main-view-header eidolia-header",
            "/api/pska/ask",
            "/api/pska/kb/ingest",
            "/api/pska/digest-jobs",
            "/api/pska/memory/search",
            "/api/pska/memory/conversation-change",
            "/api/pska/workflows/",
            "/api/pska/reviews/",
            "/api/pska/sources/read",
            "pska_agentic_question_start",
        ]:
            self.assertNotIn(forbidden, script)

    def test_extension_css_handles_compact_mobile_composer(self):
        css = (EXTENSION_DIR / "pska-mini.css").read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 520px)", css)
        self.assertIn(".composer-left .pska-mini-wrap", css)
        self.assertIn("order: -1", css)
        self.assertIn("flex: 0 0 72px", css)
        self.assertIn("#pskaMiniLabel", css)

    def test_sync_script_writes_webui_manifest_and_sidecar_consent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            extension_root = root / "extensions"
            state_dir = root / "webui-state"
            env = {
                **os.environ,
                "HERMES_HOME": str(root / "hermes"),
                "HERMES_WEBUI_EXTENSION_DIR": str(extension_root),
                "HERMES_WEBUI_EXTENSION_MANIFEST": "extensions.json",
                "HERMES_WEBUI_STATE_DIR": str(state_dir),
                "PSKA_API_BASE_URL": "http://127.0.0.1:9876",
            }

            result = subprocess.run(
                ["bash", "integrations/hermes-webui-extension/sync-to-hermes.sh"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((extension_root / "extensions.json").read_text(encoding="utf-8"))
            entries = {entry["id"]: entry for entry in manifest["extensions"]}
            self.assertIn("pska-mini", entries)
            pska_entry = entries["pska-mini"]
            self.assertEqual(pska_entry["scripts"], ["pska-mini/pska-mini.js"])
            self.assertEqual(pska_entry["stylesheets"], ["pska-mini/pska-mini.css"])
            self.assertEqual(pska_entry["sidecar"]["origin"], "http://127.0.0.1:9876")
            self.assertEqual(pska_entry["sidecar"]["health_path"], "/api/health")

            state = json.loads((state_dir / "extension-overrides.json").read_text(encoding="utf-8"))
            self.assertEqual(
                state["sidecar_proxy_consents"],
                {"pska-mini": "http://127.0.0.1:9876"},
            )


if __name__ == "__main__":
    unittest.main()
