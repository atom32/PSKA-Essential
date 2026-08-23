#!/usr/bin/env node

import fs from "node:fs";
import os from "node:os";
import pathModule from "node:path";

const WEBUI = process.env.HERMES_WEBUI_URL || "http://127.0.0.1:8787";
const PASSWORD = process.env.HERMES_WEBUI_PASSWORD || process.env.PSKA_WEBUI_TEST_PASSWORD || "";
const DATASET_ID = process.env.PSKA_TEST_DATASET_ID || "07f35e1a9b9411f197ff8391030412c0";
const SOURCE_ROOT_ID = process.env.PSKA_TEST_SOURCE_ROOT_ID || "root_ebdf0044b0442f494246012f";

const tests = [];
let cookie = "";
let csrf = "";

function record(name, ok, detail = {}) {
  tests.push({ name, ok: Boolean(ok), detail });
}

function cookieHeaderFrom(setCookieValues) {
  const values = Array.isArray(setCookieValues) ? setCookieValues : [setCookieValues].filter(Boolean);
  return values.map((value) => String(value).split(";")[0]).filter(Boolean).join("; ");
}

async function request(path, options = {}) {
  const url = path.startsWith("http") ? path : `${WEBUI}${path}`;
  const method = String(options.method || "GET").toUpperCase();
  const headers = {
    ...(options.headers || {}),
    Origin: WEBUI,
    Referer: `${WEBUI}/`,
  };
  if (cookie) headers.Cookie = cookie;
  if (/^(POST|PUT|PATCH|DELETE)$/u.test(method) && csrf) headers["X-Hermes-CSRF-Token"] = csrf;
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const response = await fetch(url, {
    method,
    headers,
    body: typeof options.body === "string" ? options.body : options.body ? JSON.stringify(options.body) : undefined,
    redirect: options.redirect || "manual",
  });
  const text = await response.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = null;
  }
  return { response, text, json };
}

async function testJson(name, path, options = {}, predicate = (json, response) => response.ok && json?.ok !== false) {
  try {
    const { response, json, text } = await request(path, options);
    const ok = predicate(json, response, text);
    record(name, ok, {
      status: response.status,
      ok_field: json?.ok,
      summary: summarize(json, text),
    });
    return { ok, response, json, text };
  } catch (error) {
    record(name, false, { error: String(error?.message || error) });
    return { ok: false, error };
  }
}

function summarize(json, text) {
  if (!json || typeof json !== "object") return String(text || "").slice(0, 180);
  if (json.error) return json.error;
  if (json.service) return `${json.service} ${json.product_api || ""}`.trim();
  if (json.chatgpt_memory_summary_import) {
    const summary = json.chatgpt_memory_summary_import.summary || {};
    return `chatgpt_memory_reviews=${summary.created_count || 0} private_skipped=${summary.skipped_private_count || 0}`;
  }
  if (json.chatgpt_conversations_import) {
    const summary = json.chatgpt_conversations_import.summary || {};
    return `chatgpt_archive_conversations=${summary.imported_conversation_count || 0}`;
  }
  if (json.chatgpt_conversation_history_import) {
    const summary = json.chatgpt_conversation_history_import.summary || {};
    return `chatgpt_history_conversations=${summary.imported_conversation_count || 0}`;
  }
  if (json.datasets) return `datasets=${json.datasets.length}`;
  if (json.workspace_status) return `workspace_status keys=${Object.keys(json.workspace_status).length}`;
  if (json.alpha_readiness) return `alpha=${json.alpha_readiness.status || "unknown"}`;
  if (json.alpha_first_run_session) {
    const progress = json.alpha_first_run_session.progress || {};
    return `first_run=${json.alpha_first_run_session.status || "unknown"} done=${progress.done_count || 0}/${progress.total_count || 0}`;
  }
  if (json.proofs) return `answer_proofs=${json.proofs.length}`;
  if (json.diagnostics) return `diagnostics=${json.diagnostics.status || "ok"}`;
  if (json.probe) return `probe=${json.probe.status || "ok"} contexts=${json.probe.context_count || 0}`;
  if (json.context_pack) {
    const counts = json.context_pack.source_counts || {};
    return `context_pack memory=${counts.memory || 0} conversation=${counts.conversation || 0} evidence=${counts.evidence || 0} source=${counts.source || 0}`;
  }
  if (json.turn_context) return `turn_context evidence=${(json.turn_context.evidence_blocks || []).length} memory=${(json.turn_context.memory_notes || []).length}`;
  if (json.briefing) return `briefing=${json.briefing.status || "ok"}`;
  if (json.agentic_context_brief) {
    const brief = json.agentic_context_brief;
    return `brief=${brief.status || "ok"} sources=${(brief.recall?.source_recall || []).length} memories=${(brief.memory?.relevant_memories || []).length}`;
  }
  if (json.context_packets) return `context_packets=${json.context_packets.length}`;
  if (json.memory_facts) return `memory_facts=${json.memory_facts.length}`;
  if (json.reviews || json.items || json.review_candidates) return `reviews=${(json.reviews || json.items || json.review_candidates || []).length}`;
  if (json.jobs) return `jobs=${json.jobs.length}`;
  if (json.boards) return `boards=${json.boards.length}`;
  if (json.board || json.task || json.job) return "created_or_found";
  return Object.keys(json).slice(0, 8).join(",");
}

function chatgptMemoryReviewIds(payload) {
  const created = payload?.chatgpt_memory_summary_import?.candidate_result?.created || [];
  return created.map((item) => String(item?.review_id || "").trim()).filter(Boolean);
}

function writeChatgptConversationFixture(marker) {
  const root = pathModule.join(os.tmpdir(), "pska-webui-extension-chatgpt-import-contract");
  const outputDir = pathModule.join(root, "archive");
  const exportPath = pathModule.join(root, "conversations.json");
  fs.mkdirSync(root, { recursive: true });
  const payload = [
    {
      id: "conv-pska-webui-contract",
      title: "PSKA WebUI ChatGPT archive contract",
      messages: [
        {
          id: "msg-user-1",
          role: "user",
          content: `This ChatGPT archive fixture contains ${marker} and should become PSKA source archive material.`,
        },
        {
          id: "msg-assistant-1",
          role: "assistant",
          content: "Only reviewed claims from this archive should become durable Memory Cards.",
        },
      ],
    },
  ];
  fs.writeFileSync(exportPath, JSON.stringify(payload, null, 2), "utf8");
  return { exportPath, outputDir };
}

function extractCsrf(html) {
  const match = String(html || "").match(/csrfToken:"([^"]+)"/);
  return match ? match[1] : "";
}

async function main() {
  if (!PASSWORD) {
    console.error("Set HERMES_WEBUI_PASSWORD or PSKA_WEBUI_TEST_PASSWORD.");
    process.exit(2);
  }

  const login = await fetch(`${WEBUI}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: PASSWORD }),
    redirect: "manual",
  });
  const loginText = await login.text();
  let loginJson = {};
  try {
    loginJson = loginText ? JSON.parse(loginText) : {};
  } catch {}
  const setCookie = login.headers.getSetCookie ? login.headers.getSetCookie() : login.headers.get("set-cookie");
  cookie = cookieHeaderFrom(setCookie);
  record("WebUI login", login.ok && loginJson.ok && cookie, { status: login.status, has_cookie: Boolean(cookie) });

  const root = await request("/");
  csrf = extractCsrf(root.text);
  record("WebUI root page loads", root.response.ok && root.text.includes("/extensions/pska-mini/pska-mini.css"), {
    status: root.response.status,
    bytes: root.text.length,
    has_pska_css: root.text.includes("/extensions/pska-mini/pska-mini.css"),
    has_csrf: Boolean(csrf),
  });

  const manifest = await testJson(
    "Extension manifest loads",
    "/extensions/pska-mini/manifest.json",
    {},
    (json, response) => response.ok && json?.id === "pska-mini" && json?.sidecar?.origin === "http://127.0.0.1:8765",
  );
  const jsAsset = await request("/extensions/pska-mini/pska-mini.js");
  record("Extension JS loads and contains handlers", jsAsset.response.ok
    && jsAsset.text.includes("runJarvisBrief")
    && jsAsset.text.includes("createDigestTask")
    && jsAsset.text.includes("/api/alpha/readiness")
    && jsAsset.text.includes("/api/alpha/first-run-session")
    && jsAsset.text.includes("/api/hermes/answer-proofs")
    && jsAsset.text.includes("/api/memory/chatgpt-summary/import")
    && jsAsset.text.includes("/api/conversations/chatgpt/import-to-hermes")
    && jsAsset.text.includes("pskaMiniChatgptConversationHistoryLimit")
    && jsAsset.text.includes('selection: "recent"')
    && jsAsset.text.includes("/api/sources/chatgpt-conversations/import")
    && jsAsset.text.includes("/api/jobs/health?include_kb=false")
    && jsAsset.text.includes("/api/wakeup/plan")
    && jsAsset.text.includes("/api/observability/metrics?limit=300")
    && jsAsset.text.includes("/api/sources/recall-eval?mode=fixture&limit=5")
    && jsAsset.text.includes("jobHealthStatusLabel")
    && jsAsset.text.includes("jobHealthCount")
    && jsAsset.text.includes("wakeupStatusLabel")
    && jsAsset.text.includes("observabilityMetricsStatusLabel")
    && jsAsset.text.includes("sourceRecallEvalStatusLabel")
    && jsAsset.text.includes("importChatgptMemorySummary")
    && jsAsset.text.includes("renderChatgptImportResult")
    && jsAsset.text.includes("importChatgptConversationHistory")
    && jsAsset.text.includes("importChatgptConversationArchive")
    && jsAsset.text.includes("renderChatgptConversationImportResult")
    && jsAsset.text.includes("addSourceRootToScope(rootId)")
    && jsAsset.text.includes("renderAnswerProofs")
    && jsAsset.text.includes("alphaStatusLabel"), {
    status: jsAsset.response.status,
    bytes: jsAsset.text.length,
  });
  record("Extension JS uses provider-neutral memory labels", jsAsset.response.ok
    && jsAsset.text.includes("PSKA governed memory and review queue")
    && jsAsset.text.includes("Governed memory / review queue")
    && !/SQLite memory/iu.test(jsAsset.text), {
    status: jsAsset.response.status,
    bytes: jsAsset.text.length,
  });
  record("Extension JS keeps chat bridge injection and display sanitizer", jsAsset.response.ok
    && jsAsset.text.includes("installSendBridge()")
    && jsAsset.text.includes("installApiBridge()")
    && jsAsset.text.includes("buildForcedSkillMessage")
    && jsAsset.text.includes("stripForcedSkillEnvelope")
    && jsAsset.text.includes("[FORCED SKILL CONTEXT:")
    && jsAsset.text.includes("PSKA-Mini Runtime Scope")
    && jsAsset.text.includes('"/api/chat/start"'), {
    status: jsAsset.response.status,
    bytes: jsAsset.text.length,
  });
  const cssAsset = await request("/extensions/pska-mini/pska-mini.css");
  record("Extension CSS loads", cssAsset.response.ok && cssAsset.text.includes(".pska-mini-chip") && cssAsset.text.includes(".pska-mini-first-run"), {
    status: cssAsset.response.status,
    bytes: cssAsset.text.length,
  });

  await testJson("Sidecar health through WebUI", "/api/extensions/pska-mini/sidecar/api/health");
  await testJson("Dashboard: workspace status", "/api/extensions/pska-mini/sidecar/api/workspace/status?compact=1&view=webui", {}, (json, response) =>
    response.ok && json?.workspace_status?.kind === "workspace_status_compact"
      && json.workspace_status?.components?.embedding?.schema === "pska.embedding_component_status.v1",
  );
  await testJson("Dashboard: embedding component", "/api/extensions/pska-mini/sidecar/api/components/embedding", {}, (json, response) =>
    response.ok && json?.component?.schema === "pska.embedding_component_status.v1"
      && json.component?.governance?.allowed_flow === "Hermes/WebUI -> PSKA -> RAGFlow -> embedding",
  );
  await testJson("Dashboard: KB datasets", "/api/extensions/pska-mini/sidecar/api/kb/datasets", {}, (json, response) =>
    response.ok && Array.isArray(json?.datasets) && json.datasets.some((dataset) => (dataset.dataset_id || dataset.id) === DATASET_ID),
  );
  await testJson("Dashboard: runtime diagnostics", "/api/extensions/pska-mini/sidecar/api/runtime/diagnostics", {}, (json, response) =>
    response.ok && json?.diagnostics?.status !== "error",
  );
  await testJson("Dashboard: job health", "/api/extensions/pska-mini/sidecar/api/jobs/health?include_kb=false", {}, (json, response) =>
    response.ok
      && json?.job_health?.schema === "pska.job_health.v1"
      && json.job_health?.data_flow?.read_only === true
      && json.job_health?.data_flow?.runs_jobs === false
      && json.job_health?.data_flow?.activates_due_jobs === false,
  );
  await testJson("Dashboard: wakeup plan", "/api/extensions/pska-mini/sidecar/api/wakeup/plan", {}, (json, response) =>
    response.ok
      && json?.wakeup_plan?.schema === "pska.wakeup_plan.v1"
      && json.wakeup_plan?.data_flow?.read_only === true
      && json.wakeup_plan?.data_flow?.calls_tick_endpoint === false
      && json.wakeup_plan?.data_flow?.activates_due_jobs === false
      && json.wakeup_plan?.data_flow?.runs_jobs === false,
  );
  await testJson("Dashboard: observability metrics", "/api/extensions/pska-mini/sidecar/api/observability/metrics?limit=300", {}, (json, response) =>
    response.ok
      && json?.observability_metrics?.schema === "pska.observability_metrics.v1"
      && json.observability_metrics?.data_flow?.read_only === true
      && json.observability_metrics?.data_flow?.writes_source_files === false
      && json.observability_metrics?.data_flow?.writes_memory_directly === false
      && json.observability_metrics?.data_flow?.runs_jobs === false
      && json.observability_metrics?.data_flow?.exports_external_trace === false,
  );
  await testJson("Dashboard: source recall eval", "/api/extensions/pska-mini/sidecar/api/sources/recall-eval?mode=fixture&limit=5", {}, (json, response) =>
    response.ok
      && json?.source_recall_eval?.schema === "pska.source_recall_eval.v1"
      && json.source_recall_eval?.status === "ok"
      && json.source_recall_eval?.data_flow?.read_only === true
      && json.source_recall_eval?.data_flow?.writes_source_files === false
      && json.source_recall_eval?.data_flow?.writes_memory_directly === false
      && json.source_recall_eval?.data_flow?.embedding_required === false,
  );
  await testJson("Dashboard: alpha readiness", "/api/extensions/pska-mini/sidecar/api/alpha/readiness", {}, (json, response) =>
    response.ok
      && json?.alpha_readiness?.status === "alpha_ready"
      && json.alpha_readiness?.summary?.warn_count === 0
      && json.alpha_readiness?.summary?.fail_count === 0,
  );
  const firstRunSessionId = `pska-webui-extension-test-${Date.now()}`;
  await testJson("Alpha: first-run session", `/api/extensions/pska-mini/sidecar/api/alpha/first-run-session?session_id=${encodeURIComponent(firstRunSessionId)}`, {}, (json, response) =>
    response.ok
      && json?.alpha_first_run_session?.schema === "pska.alpha_first_run_session.v1"
      && Array.isArray(json.alpha_first_run_session?.checklist)
      && json.alpha_first_run_session.checklist.length >= 6
      && json.alpha_first_run_session?.data_flow?.executes_trial_step === false,
  );
  await testJson("Alpha: first-run item update", "/api/extensions/pska-mini/sidecar/api/alpha/first-run-session/items/confirm_runtime", {
    method: "POST",
    body: {
      session_id: firstRunSessionId,
      status: "done",
      note: "temporary WebUI extension contract test",
    },
  }, (json, response) =>
    response.ok
      && json?.alpha_first_run_session?.progress?.done_count === 1
      && json.alpha_first_run_session?.data_flow?.writes_source_files === false
      && json.alpha_first_run_session?.data_flow?.writes_memory_directly === false
      && json.alpha_first_run_session?.data_flow?.executes_trial_step === false,
  );
  await testJson("Hermes context: active profile", "/api/profile/active", {}, (json, response) => response.ok && (json?.profile || json?.name));
  await testJson("Hermes context: projects", "/api/projects", {}, (json, response) => response.ok && (Array.isArray(json?.projects) || Array.isArray(json)));
  await testJson("Hermes context: workspaces", "/api/workspaces", {}, (json, response) => response.ok && (Array.isArray(json?.workspaces) || Array.isArray(json)));

  await testJson("Button: RAGFlow Probe", "/api/extensions/pska-mini/sidecar/api/runtime/retrieval-probe", {
    method: "POST",
    body: {
      question: "收入增长 现金流 库存 未交付订单",
      dataset_ids: [DATASET_ID],
      document_ids: [],
      limit: 3,
      use_kg: false,
    },
  }, (json, response) => response.ok && json?.probe && json.probe.context_count >= 0);

  await testJson("Button: Preview context-pack memory-only", "/api/extensions/pska-mini/sidecar/api/conversation/context-pack", {
    method: "POST",
    body: {
      caller: "hermes-webui-extension-test",
      user_message: "PSKA 第一用户 dogfooding 怎么做？",
      mode: "memory-only",
      scope: { dataset_ids: [], document_ids: [] },
      budget: { max_evidence_blocks: 0, max_memory_notes: 3, max_conversation_blocks: 3, max_source_blocks: 0, max_tokens: 3000 },
      requirements: { need_citations: true },
    },
  }, (json, response) => response.ok && json?.context_pack);

  await testJson("Button: Preview context-pack dataset scoped", "/api/extensions/pska-mini/sidecar/api/conversation/context-pack", {
    method: "POST",
    body: {
      caller: "hermes-webui-extension-test",
      user_message: "财报研究时要看哪些指标？",
      mode: "project",
      scope: { dataset_ids: [DATASET_ID], document_ids: [] },
      budget: { max_evidence_blocks: 3, max_memory_notes: 3, max_conversation_blocks: 3, max_source_blocks: 0, max_tokens: 3000 },
      requirements: { need_citations: true },
    },
  }, (json, response) => response.ok && json?.context_pack);

  await testJson("Button: Jarvis Brief", "/api/extensions/pska-mini/sidecar/api/jarvis/briefing", {
    method: "POST",
    body: {
      scope: { dataset_ids: [DATASET_ID], document_ids: [], hermes: {} },
      source_scope: { root_ids: [SOURCE_ROOT_ID] },
      compact: true,
      view: "webui",
      audit_limit: 12,
      dataset_page_size: 20,
      review_limit: 30,
      workflow_limit: 30,
    },
  }, (json, response) => response.ok && json?.briefing);

  await testJson("Button: Agentic Brief", "/api/extensions/pska-mini/sidecar/api/agentic/context-brief", {
    method: "POST",
    body: {
      objective: "Prepare Hermes pre-answer context for the current WebUI turn.",
      question: "财报研究时应该先召回哪些资料和记忆？",
      project_hint: "",
      scope: { dataset_ids: [DATASET_ID], document_ids: [], hermes: {} },
      source_scope: { root_ids: [SOURCE_ROOT_ID] },
      compact: true,
      view: "webui",
      evidence_limit: 4,
      source_limit: 4,
      memory_limit: 4,
      trace_limit: 8,
    },
  }, (json, response) => response.ok
    && json?.agentic_context_brief?.status === "ready"
    && Array.isArray(json?.agentic_context_brief?.specialists?.recommended_profiles)
    && json.agentic_context_brief.specialists.recommended_profiles.length > 0
    && json.agentic_context_brief.specialists.data_flow?.starts_agents === false);

  await testJson("Button: Source Recall", "/api/extensions/pska-mini/sidecar/api/sources/search", {
    method: "POST",
    body: {
      query: "收入增长 现金流 库存 未交付订单",
      scope: { root_ids: [SOURCE_ROOT_ID] },
      limit: 5,
    },
  }, (json, response) => response.ok && Array.isArray(json?.context_packets) && json.context_packets.length > 0);

  await testJson("Memory Page: search", "/api/extensions/pska-mini/sidecar/api/memory/search", {
    method: "POST",
    body: { query: "PSKA", scope: {}, limit: 20 },
  }, (json, response) => response.ok && Array.isArray(json?.memory_facts));

  const memoryMarker = `PSKA WebUI ChatGPT memory contract marker ${Date.now()}`;
  const privateDetail = `private live contract detail ${Date.now()}`;
  const chatgptMemoryImport = await testJson(
    "ChatGPT import: memory summary creates governed reviews",
    "/api/extensions/pska-mini/sidecar/api/memory/chatgpt-summary/import",
    {
      method: "POST",
      body: {
        source_label: "PSKA WebUI contract ChatGPT memory summary",
        candidate_limit: 6,
        include_private: false,
        text: [
          `用户长期项目 PSKA 的目标之一是构建有来源、有审核的外挂智能。${memoryMarker}。`,
          `用户有一段与家庭和亲密经历有关的私密资料：${privateDetail}。默认不应进入长期记忆。`,
          "你叫徐大为，长期研究认知智能、自然语言处理、知识图谱和个人知识管理。",
        ].join("\n\n"),
      },
    },
    (json, response) => {
      const result = json?.chatgpt_memory_summary_import || {};
      const summary = result.summary || {};
      const flow = result.data_flow || {};
      const serialized = JSON.stringify(result);
      return response.ok
        && result.schema === "pska.chatgpt_memory_summary_import.v1"
        && summary.created_count >= 1
        && summary.skipped_private_count >= 1
        && summary.privacy_boundary_created === true
        && flow.creates_review === true
        && flow.writes_memory_directly === false
        && flow.writes_source_files === false
        && flow.stores_full_import_text === false
        && !serialized.includes(privateDetail);
    },
  );
  const chatgptReviewIds = chatgptMemoryReviewIds(chatgptMemoryImport.json);
  if (chatgptReviewIds.length) {
    await testJson("ChatGPT import: reject temporary memory reviews", "/api/extensions/pska-mini/sidecar/api/reviews/batch-decision", {
      method: "POST",
      body: {
        review_ids: chatgptReviewIds,
        decision: "reject",
        reason: "Reject temporary ChatGPT memory import contract test reviews",
      },
    }, (json, response) =>
      response.ok
        && json?.schema === "pska.review_decide_batch.v1"
        && json?.decision === "reject"
        && json?.decided_count === chatgptReviewIds.length
        && json?.data_flow?.writes_memory_directly === false,
    );
  } else {
    record("ChatGPT import: reject temporary memory reviews", false, { reason: "No review ids returned from import" });
  }

  const historyMarker = `PSKA WebUI ChatGPT history marker ${Date.now()}`;
  const historyFixture = writeChatgptConversationFixture(historyMarker);
  await testJson(
    "ChatGPT import: conversation history creates Hermes history",
    "/api/extensions/pska-mini/sidecar/api/conversations/chatgpt/import-to-hermes",
    {
      method: "POST",
      body: {
        export_path: historyFixture.exportPath,
        source_label: "PSKA WebUI contract ChatGPT conversation history",
        conversation_limit: 1,
        selection: "recent",
        read_only: true,
      },
    },
    (json, response) => {
      const result = json?.chatgpt_conversation_history_import || {};
      const flow = result.data_flow || {};
      return response.ok
        && result.schema === "pska.chatgpt_conversation_history_import.v1"
        && result.status === "imported"
        && result.summary?.selection === "recent"
        && result.summary?.imported_conversation_count >= 1
        && flow.writes_hermes_history === true
        && flow.writes_source_registry === false
        && flow.writes_memory_directly === false
        && flow.runtime_special_chatgpt_channel === false
        && flow.query_based_recall_after_import === true;
    },
  );

  const archiveMarker = `PSKA WebUI ChatGPT archive marker ${Date.now()}`;
  const archiveFixture = writeChatgptConversationFixture(archiveMarker);
  const chatgptArchiveImport = await testJson(
    "ChatGPT import: conversation archive creates source root",
    "/api/extensions/pska-mini/sidecar/api/sources/chatgpt-conversations/import",
    {
      method: "POST",
      body: {
        export_path: archiveFixture.exportPath,
        output_dir: archiveFixture.outputDir,
        source_label: "PSKA WebUI contract ChatGPT conversation archive",
        conversation_limit: 0,
        scan: true,
        scan_max_bytes: 1000000,
      },
    },
    (json, response) => {
      const result = json?.chatgpt_conversations_import || {};
      const flow = result.data_flow || {};
      return response.ok
        && result.schema === "pska.chatgpt_conversations_import.v1"
        && result.status === "imported"
        && result.summary?.imported_conversation_count === 1
        && result.root?.root_id
        && result.archive?.manifest_path
        && result.archive?.report_path
        && flow.writes_original_export_files === false
        && flow.writes_normalized_archive_files === true
        && flow.writes_import_report_files === true
        && flow.writes_source_registry === true
        && flow.writes_memory_directly === false
        && flow.creates_review === false
        && flow.embedding_required === false;
    },
  );
  const chatgptArchiveRootId = String(chatgptArchiveImport.json?.chatgpt_conversations_import?.root?.root_id || "").trim();
  if (chatgptArchiveRootId) {
    await testJson("ChatGPT import: conversation archive source search", "/api/extensions/pska-mini/sidecar/api/sources/search", {
      method: "POST",
      body: {
        query: archiveMarker,
        scope: { root_ids: [chatgptArchiveRootId] },
        limit: 5,
      },
    }, (json, response) =>
      response.ok
        && Array.isArray(json?.context_packets)
        && JSON.stringify(json.context_packets).includes(archiveMarker),
    );
    await testJson("ChatGPT import: conversation archive leaves memory untouched", "/api/extensions/pska-mini/sidecar/api/memory/search", {
      method: "POST",
      body: { query: archiveMarker, scope: {}, limit: 10 },
    }, (json, response) =>
      response.ok
        && Array.isArray(json?.memory_facts)
        && !JSON.stringify(json.memory_facts).includes(archiveMarker),
    );
  } else {
    record("ChatGPT import: conversation archive source search", false, { reason: "No source root id returned from archive import" });
    record("ChatGPT import: conversation archive leaves memory untouched", false, { reason: "No source root id returned from archive import" });
  }

  await testJson("Memory Page: review list pending", "/api/extensions/pska-mini/sidecar/api/reviews?status=pending&limit=50", {}, (json, response) =>
    response.ok && Array.isArray(json?.reviews || json?.items || json?.review_candidates || []),
  );
  const recentProofs = await testJson("Memory Page: recent answer proofs", "/api/extensions/pska-mini/sidecar/api/hermes/answer-proofs?limit=5", {}, (json, response) =>
    response.ok
      && json?.schema === "pska.hermes_answer_proof_list.v1"
      && Array.isArray(json?.proofs)
      && json?.data_flow?.writes_memory_directly === false
      && json?.data_flow?.writes_source_files === false,
  );
  const firstProofId = recentProofs.json?.proofs?.[0]?.proof_id || "";
  if (firstProofId) {
    await testJson("Memory Page: answer proof trace query", `/api/extensions/pska-mini/sidecar/api/trace/query?target_type=hermes_turn&target_id=${encodeURIComponent(firstProofId)}&limit=10`, {}, (json, response) =>
      response.ok
        && json?.schema === "pska.trace_query.v1"
        && json?.status === "found"
        && Array.isArray(json?.entries)
        && json.entries.some((entry) => entry?.evidence?.action === "hermes.answer_proof"),
    );
  } else {
    record("Memory Page: answer proof trace query", true, { skipped: "No answer proof recorded yet" });
  }

  const created = await testJson("Memory Page: create review candidate", "/api/extensions/pska-mini/sidecar/api/memory/conversation-change", {
    method: "POST",
    body: {
      operation: "memory_patch",
      user_message: `PSKA 页面测试临时候选 ${new Date().toISOString()}，应在测试结束后被拒绝。`,
      text: `PSKA 页面测试临时候选 ${new Date().toISOString()}，应在测试结束后被拒绝。`,
      reason: "Created from automated PSKA WebUI extension test",
      force_review: true,
      source_refs: [{
        adapter: "hermes-webui",
        source_type: "hermes_webui",
        source_id: `pska-mini-webui-test:${Date.now()}`,
        title: "Hermes WebUI PSKA extension automated test",
        metadata: { origin: "hermes-webui.pska-mini-extension-test" },
      }],
      scope: {},
    },
  }, (json, response) => response.ok && (json?.review?.review_id || json?.review_id));

  const reviewId = created.json?.review?.review_id || created.json?.review_id || "";
  if (reviewId) {
    await testJson("Memory Page: review detail", `/api/extensions/pska-mini/sidecar/api/reviews/${encodeURIComponent(reviewId)}`);
    await testJson("Memory Page: reject temporary candidate", `/api/extensions/pska-mini/sidecar/api/reviews/${encodeURIComponent(reviewId)}/decision`, {
      method: "POST",
      body: { decision: "reject", reason: "Reject temporary automated PSKA WebUI extension test candidate" },
    });
  } else {
    record("Memory Page: review detail", false, { reason: "No review id from create candidate" });
    record("Memory Page: reject temporary candidate", false, { reason: "No review id from create candidate" });
  }

  await testJson("Kanban: list/create PSKA board", "/api/kanban/boards", {
    method: "POST",
    body: {
      slug: "pska-review",
      name: "PSKA Review",
      description: "Projection of the PSKA review queue",
      icon: "check-square",
      color: "#4b7bec",
    },
  }, (json, response) => response.ok && (json?.board || json?.ok !== false));

  const reviews = await request("/api/extensions/pska-mini/sidecar/api/reviews?limit=1");
  const reviewPayload = reviews.json;
  const firstReview = (reviewPayload?.reviews || reviewPayload?.items || reviewPayload?.review_candidates || [])[0];
  if (firstReview) {
    const projection = await testJson("Kanban: create one projected task", "/api/kanban/tasks", {
      method: "POST",
      body: {
        title: `PSKA test projection ${firstReview.review_id || firstReview.id || "review"}`,
        body: "Temporary projection created by PSKA extension contract test.",
        board: "pska-review",
        status: "todo",
        priority: 1,
        idempotency_key: `pska-webui-extension-test:${firstReview.review_id || firstReview.id || "unknown"}`,
      },
    }, (json, response) => response.ok && (json?.task || json?.ok !== false));
    const taskId = projection.json?.task?.id || projection.json?.task?.task_id || "";
    if (taskId) {
      await testJson("Kanban: archive temporary projected task", `/api/kanban/tasks/${encodeURIComponent(taskId)}/patch`, {
        method: "POST",
        body: {
          board: "pska-review",
          status: "archived",
          reason: "Archive temporary PSKA WebUI extension contract test projection",
        },
      }, (json, response) => response.ok && (json?.task || json?.ok !== false));
    } else {
      record("Kanban: archive temporary projected task", false, { reason: "No task id from projection response" });
    }
  } else {
    record("Kanban: create one projected task", true, { skipped: "No review returned for projection test" });
    record("Kanban: archive temporary projected task", true, { skipped: "No review returned for projection test" });
  }

  const crons = await testJson("Digest Task: list Hermes tasks", "/api/crons", {}, (json, response) => response.ok && Array.isArray(json?.jobs));
  const hasDigest = (crons.json?.jobs || []).some((job) => job?.name === "PSKA Digest Runner" || String(job?.prompt || "").includes("PSKA-Mini Digest Runner"));
  if (hasDigest) {
    record("Digest Task: create or find", true, { status: "already_exists" });
  } else {
    await testJson("Digest Task: create or find", "/api/crons/create", {
      method: "POST",
      body: {
        name: "PSKA Digest Runner",
        schedule: "every 1h",
        deliver: "local",
        skills: ["knowledge-retrieval"],
        prompt: "PSKA-Mini Digest Runner\nUse PSKA-Essential MCP tools to inspect provider jobs and digest jobs. Do not write durable memory directly.",
      },
    }, (json, response) => response.ok && (json?.job || json?.ok !== false));
  }

  await testJson("Chat bridge dependency: skill content", "/api/skills/content?name=knowledge-retrieval", {}, (json, response) =>
    response.ok && typeof json?.content === "string" && json.content.length > 0,
  );

  const failed = tests.filter((test) => !test.ok);
  const output = {
    ok: failed.length === 0,
    total: tests.length,
    passed: tests.length - failed.length,
    failed: failed.length,
    failed_names: failed.map((test) => test.name),
    tests,
  };
  console.log(JSON.stringify(output, null, 2));
  process.exit(failed.length ? 1 : 0);
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exit(1);
});
