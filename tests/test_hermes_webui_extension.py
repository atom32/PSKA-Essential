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
        self.assertIn("installAnswerProofBridge()", script)
        self.assertIn("PSKAMiniAnswerProofEventSource", script)
        self.assertIn("finalizeAnswerProofTurn(turn).catch", script)
        self.assertIn("mergeAnswerProofTerminalPayload(turn, eventName, payload)", script)
        self.assertIn("answerTextFromTerminalPayload", script)
        self.assertIn("latestAssistantMessageText", script)
        self.assertIn("turn.answerCandidate", script)
        self.assertIn('answer_capture_source: hasTerminalAnswer ? "hermes_stream_terminal_payload" : "webui_state_or_dom"', script)
        self.assertIn('"/api/hermes/answer-proofs"', script)
        self.assertIn("automatic_after_answer_audit", script)
        self.assertIn("non_blocking: true", script)
        self.assertIn("caller: \"hermes-webui-extension\"", script)
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
        self.assertIn("DASHBOARD_REQUEST_TIMEOUT_MS = 30000", script)
        self.assertIn("pskaMiniSourceRecall", script)
        self.assertIn("buildForcedSkillMessage", script)
        self.assertIn("stripForcedSkillEnvelope", script)
        self.assertIn("[FORCED SKILL CONTEXT:", script)
        self.assertIn('"/api/conversation/context-pack"', script)
        self.assertIn("buildComposerContextPack", script)
        self.assertIn("formatContextPackForSkill", script)
        self.assertIn("prompt_context_block", script)
        self.assertIn("PSKA did not return a rendered prompt context block", script)
        self.assertNotIn("contextBlockLabel", script)
        self.assertIn("contextPackFlowLine", script)
        self.assertIn("contextPackWarningLines", script)
        self.assertIn("History boundary: query recall", script)
        self.assertIn("PSKA context pack", script)
        self.assertIn("hermesRecallComponent", script)
        self.assertIn("History recall", script)
        self.assertIn("max_conversation_blocks", script)
        self.assertIn("max_source_blocks", script)
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
        self.assertIn('wrap.querySelector("#pskaMiniSourceRootIds").addEventListener("input", syncFromControls)', script)
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
        self.assertIn("markSourcedAskDone", script)
        self.assertIn('data-pska-first-run-sourced-ask-done="1"', script)
        self.assertIn('"run_sourced_ask"', script)
        self.assertIn("markRuntimeConfirmedDone", script)
        self.assertIn('data-pska-first-run-runtime-done="1"', script)
        self.assertIn('"confirm_runtime"', script)
        self.assertIn("markRecoveryPlanDone", script)
        self.assertIn('data-pska-first-run-recovery-done="1"', script)
        self.assertIn('"confirm_recovery_plan"', script)
        self.assertIn("markWritebackLockedDone", script)
        self.assertIn('data-pska-first-run-writeback-locked="1"', script)
        self.assertIn('"keep_writeback_locked"', script)
        self.assertIn("markExitNotesDone", script)
        self.assertIn('data-pska-first-run-exit-notes="1"', script)
        self.assertIn('"record_exit_notes"', script)
        self.assertIn("markSelectedScopeDone", script)
        self.assertIn('data-pska-first-run-scope-done="1"', script)
        self.assertIn('"select_read_only_scope"', script)
        self.assertIn("markReviewQueueDone", script)
        self.assertIn('data-pska-first-run-review-done="1"', script)
        self.assertIn('"review_memory_queue"', script)
        self.assertIn("pskaMiniMemoryDraftSource", script)
        self.assertIn("pskaMiniChatgptMemorySummary", script)
        self.assertIn("importChatgptMemorySummary", script)
        self.assertIn('"/api/memory/chatgpt-summary/import"', script)
        self.assertIn("renderChatgptImportResult", script)
        self.assertIn("pskaMiniChatgptConversationPath", script)
        self.assertIn("pskaMiniChatgptConversationHistoryLimit", script)
        self.assertIn("importChatgptConversationHistory", script)
        self.assertIn('"/api/conversations/chatgpt/import-to-hermes"', script)
        self.assertIn('selection: "recent"', script)
        self.assertIn("importChatgptConversationArchive", script)
        self.assertIn('"/api/sources/chatgpt-conversations/import"', script)
        self.assertIn("renderChatgptConversationImportResult", script)
        self.assertIn("addSourceRootToScope(rootId)", script)
        self.assertIn("Report:", script)
        self.assertIn("pskaMiniSourceEvidenceQuery", script)
        self.assertIn("runSourceEvidenceSearch", script)
        self.assertIn("loadSourceEvidenceDetail", script)
        self.assertIn("draftMemoryCandidateFromSourceEvidence", script)
        self.assertIn("markSourceEvidenceRehearsalDone", script)
        self.assertIn('data-pska-first-run-rehearsal-done="1"', script)
        self.assertIn("SOURCE_EVIDENCE_DRAFT_PREFIX", script)
        self.assertIn("isUneditedSourceEvidenceDraft", script)
        self.assertIn('"/api/sources/search"', script)
        self.assertIn('"/api/sources/read"', script)
        self.assertIn("currentSourceScopePayload()", script)
        self.assertNotIn("HermesChatStartHooks", script)
        self.assertNotIn("context_provider", script)
        self.assertNotIn("/api/sessions/search", script)
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

    def test_live_contract_exercises_chatgpt_import_paths(self):
        script = (ROOT / "scripts" / "test_pska_webui_extension.mjs").read_text(encoding="utf-8")

        required = [
            "Button: Preview context-pack memory-only",
            "Button: Preview context-pack dataset scoped",
            "/api/extensions/pska-mini/sidecar/api/conversation/context-pack",
            "ChatGPT import: memory summary creates governed reviews",
            "ChatGPT import: reject temporary memory reviews",
            "ChatGPT import: conversation history creates Hermes history",
            "ChatGPT import: conversation archive creates source root",
            "ChatGPT import: conversation archive source search",
            "ChatGPT import: conversation archive leaves memory untouched",
            "/api/extensions/pska-mini/sidecar/api/memory/chatgpt-summary/import",
            "/api/extensions/pska-mini/sidecar/api/conversations/chatgpt/import-to-hermes",
            "/api/extensions/pska-mini/sidecar/api/sources/chatgpt-conversations/import",
            "/api/extensions/pska-mini/sidecar/api/reviews/batch-decision",
            "writeChatgptConversationFixture",
            "flow.writes_memory_directly === false",
            "flow.creates_review === false",
        ]
        for term in required:
            with self.subTest(term=term):
                self.assertIn(term, script)

    def test_llm_proof_verifies_extension_auto_answer_proof_by_default(self):
        script = (ROOT / "scripts" / "test_pska_webui_llm_proof.cjs").read_text(encoding="utf-8")

        required = [
            "PSKA_LLM_PROOF_ANSWER_PROOF_MODE",
            'return "auto"',
            'if (ANSWER_PROOF_MODE !== "auto") return null',
            "waitForAutomaticAnswerProof",
            "isAutomaticExtensionProof",
            "Extension automatic answer proof recorded in PSKA audit",
            'proof.caller === "hermes-webui-extension"',
            "metadata.automatic_after_answer_audit === true",
            "metadata.data_plane === \"pska\"",
        ]
        for term in required:
            with self.subTest(term=term):
                self.assertIn(term, script)
        self.assertNotIn("const RECORD_ANSWER_PROOF = !falsy", script)

    def test_visual_smoke_exercises_chatgpt_import_controls(self):
        script = (ROOT / "scripts" / "test_pska_webui_visual.cjs").read_text(encoding="utf-8")

        required = [
            "ChatGPT import controls visible on Memory page",
            "desktop-chatgpt-imports.png",
            "#pskaMiniChatgptImport",
            "#pskaMiniChatgptMemorySummary",
            "#pskaMiniChatgptIncludePrivate",
            "#pskaMiniImportChatgptMemory",
            "#pskaMiniChatgptConversationImport",
            "#pskaMiniChatgptConversationPath",
            "#pskaMiniChatgptConversationOutput",
            "#pskaMiniChatgptConversationLimit",
            "#pskaMiniImportChatgptConversations",
            "horizontallyOverflowing.length === 0",
        ]
        for term in required:
            with self.subTest(term=term):
                self.assertIn(term, script)

    def test_extension_css_handles_compact_mobile_composer(self):
        css = (EXTENSION_DIR / "pska-mini.css").read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 520px)", css)
        self.assertIn(".composer-left .pska-mini-wrap", css)
        self.assertIn("order: -1", css)
        self.assertIn("flex: 0 0 72px", css)
        self.assertIn("#pskaMiniLabel", css)
        self.assertIn(".pska-mini-source-evidence", css)
        self.assertIn(".pska-mini-source-evidence-list", css)
        self.assertIn(".pska-mini-source-evidence-detail pre", css)
        self.assertIn(".pska-mini-page-actions", css)
        self.assertIn(".pska-mini-page-action-buttons", css)
        self.assertIn(".pska-mini-first-run-exit-btn", css)
        self.assertIn(".pska-mini-inline-btn", css)

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
