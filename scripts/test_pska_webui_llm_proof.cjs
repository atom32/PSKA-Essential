#!/usr/bin/env node

const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");

const WEBUI = stripTrailingSlash(process.env.HERMES_WEBUI_URL || "http://127.0.0.1:8787");
const PSKA_API = stripTrailingSlash(process.env.PSKA_API_BASE_URL || "http://127.0.0.1:8765");
const PASSWORD = process.env.HERMES_WEBUI_PASSWORD || process.env.PSKA_WEBUI_TEST_PASSWORD || "";
const PLAYWRIGHT_MODULE = process.env.PSKA_PLAYWRIGHT_MODULE || process.env.PLAYWRIGHT_MODULE || "playwright";
const BROWSER_CHANNEL = process.env.PSKA_PLAYWRIGHT_CHANNEL || "";
const DATASET_ID = process.env.PSKA_TEST_DATASET_ID || "07f35e1a9b9411f197ff8391030412c0";
const SOURCE_ROOT_ID = process.env.PSKA_TEST_SOURCE_ROOT_ID || "root_ebdf0044b0442f494246012f";
const QUESTION = process.env.PSKA_LLM_PROOF_QUESTION || [
  "请用 PSKA 回答：Northstar Robotics Q2 演示资料里，收入增长、现金流、库存、未交付订单分别说明了什么风险？",
  "请先使用 PSKA 工具召回资料和记忆，只根据资料回答，列出来源编号或引用，不要写入长期记忆。"
].join("");
const OUT_DIR = process.env.PSKA_LLM_PROOF_OUT || path.join(os.tmpdir(), `pska-webui-llm-proof-${timestampSlug()}`);
const HEADLESS = !truthy(process.env.PSKA_PLAYWRIGHT_HEADED);
const KEEP_SESSION = truthy(process.env.PSKA_LLM_PROOF_KEEP_SESSION);
const TIMEOUT_MS = Number(process.env.PSKA_LLM_PROOF_TIMEOUT_MS || 240000);
const STORAGE_KEY = "pska-mini.hermes-webui.scope.v1";
const RECORD_ANSWER_PROOF = !falsy(process.env.PSKA_LLM_PROOF_RECORD_ANSWER_PROOF);

function usage() {
  console.log(`Usage: node scripts/test_pska_webui_llm_proof.cjs

Environment:
  HERMES_WEBUI_URL              default: http://127.0.0.1:8787
  HERMES_WEBUI_PASSWORD         required when WebUI auth is enabled
  PSKA_WEBUI_TEST_PASSWORD      alternate password env
  PSKA_PLAYWRIGHT_MODULE        playwright or playwright-core, default: playwright
  PSKA_PLAYWRIGHT_CHANNEL       optional browser channel, e.g. chrome
  PSKA_TEST_DATASET_ID          dataset selected in PSKA scope
  PSKA_TEST_SOURCE_ROOT_ID      source root selected in PSKA scope
  PSKA_LLM_PROOF_QUESTION       user-visible prompt to send
  PSKA_LLM_PROOF_OUT            output directory, default: /tmp/pska-webui-llm-proof-*
  PSKA_LLM_PROOF_TIMEOUT_MS     default: 240000
  PSKA_LLM_PROOF_KEEP_SESSION   set to 1 to keep the created WebUI session
  PSKA_LLM_PROOF_RECORD_ANSWER_PROOF
                                  set to 0/false/no/off to skip POSTing proof metadata to PSKA API
  PSKA_API_BASE_URL              default: http://127.0.0.1:8765
  PSKA_PLAYWRIGHT_HEADED        set to 1 for headed browser

This is an optional real-LLM proof. It lets Hermes WebUI run normally, records
chat stream events, and verifies that the answer-side turn used PSKA tools,
finished with a substantive answer, and kept the visible user message clean.`);
}

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  usage();
  process.exit(0);
}

function stripTrailingSlash(value) {
  return String(value || "").replace(/\/+$/u, "");
}

function truthy(value) {
  return /^(1|true|yes|on)$/iu.test(String(value || ""));
}

function falsy(value) {
  return /^(0|false|no|off)$/iu.test(String(value || ""));
}

function timestampSlug() {
  return new Date().toISOString().replace(/[:.]/gu, "-");
}

function sha256(value) {
  return crypto.createHash("sha256").update(String(value || ""), "utf8").digest("hex");
}

function loadPlaywright() {
  try {
    return require(PLAYWRIGHT_MODULE);
  } catch (error) {
    console.error(`Cannot load Playwright module '${PLAYWRIGHT_MODULE}'.`);
    console.error("Install it outside the PSKA repo, then expose it with NODE_PATH, for example:");
    console.error("  mkdir -p /tmp/pska-playwright && cd /tmp/pska-playwright");
    console.error("  npm init -y >/dev/null");
    console.error("  npm install playwright-core");
    console.error("  NODE_PATH=/tmp/pska-playwright/node_modules PSKA_PLAYWRIGHT_MODULE=playwright-core PSKA_PLAYWRIGHT_CHANNEL=chrome node scripts/test_pska_webui_llm_proof.cjs");
    console.error(`Original error: ${error.message}`);
    process.exit(2);
  }
}

function assertCheck(checks, name, ok, detail = {}) {
  checks.push({ name, ok: Boolean(ok), detail });
  if (!ok) {
    const rendered = JSON.stringify(detail, null, 2);
    throw new Error(`${name} failed${rendered ? `: ${rendered}` : ""}`);
  }
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch (_) {
    return null;
  }
}

async function authenticate(context, checks) {
  const statusResponse = await context.request.get("/api/auth/status");
  const status = await safeJson(statusResponse);
  const authEnabled = Boolean(status?.auth_enabled || status?.password_auth_enabled);
  assertCheck(checks, "WebUI auth status", statusResponse.ok(), {
    status: statusResponse.status(),
    auth_enabled: authEnabled,
  });
  if (!authEnabled) return;
  if (!PASSWORD) {
    throw new Error("WebUI auth is enabled. Set HERMES_WEBUI_PASSWORD or PSKA_WEBUI_TEST_PASSWORD.");
  }
  const loginResponse = await context.request.post("/api/auth/login", {
    data: { password: PASSWORD },
  });
  const loginJson = await safeJson(loginResponse);
  assertCheck(checks, "WebUI login", loginResponse.ok() && loginJson?.ok !== false, {
    status: loginResponse.status(),
  });
}

async function prepareContext(browser, viewport) {
  const context = await browser.newContext({
    baseURL: WEBUI,
    viewport,
  });
  await context.addInitScript(
    ({ storageKey, datasetId, sourceRootId }) => {
      const state = {
        enabled: true,
        mode: "project",
        datasetIds: datasetId ? [datasetId] : [],
        documentIds: [],
        sourceRootIds: sourceRootId ? [sourceRootId] : [],
        maxTokens: 3000,
      };
      localStorage.setItem(storageKey, JSON.stringify(state));
      localStorage.removeItem("hermes-webui-session");
    },
    { storageKey: STORAGE_KEY, datasetId: DATASET_ID, sourceRootId: SOURCE_ROOT_ID },
  );
  await context.addInitScript(() => {
    const NativeEventSource = window.EventSource;
    if (!NativeEventSource || NativeEventSource.__pskaLlmProofWrapped) return;
    window.__pskaLlmProofEvents = [];
    function record(type, event) {
      let data = event?.data || "";
      let json = null;
      try {
        json = data ? JSON.parse(data) : null;
      } catch (_) {
        json = null;
      }
      window.__pskaLlmProofEvents.push({
        type,
        at: new Date().toISOString(),
        data,
        json,
      });
    }
    function WrappedEventSource(url, config) {
      const source = new NativeEventSource(url, config);
      const href = String(url || "");
      if (href.includes("api/chat/stream")) {
        [
          "tool",
          "tool_complete",
          "token",
          "interim_assistant",
          "reasoning",
          "done",
          "stream_end",
          "warning",
          "error",
          "apperror",
          "cancel",
        ].forEach((eventName) => {
          source.addEventListener(eventName, (event) => record(eventName, event));
        });
      }
      return source;
    }
    WrappedEventSource.prototype = NativeEventSource.prototype;
    Object.setPrototypeOf(WrappedEventSource, NativeEventSource);
    WrappedEventSource.CONNECTING = NativeEventSource.CONNECTING;
    WrappedEventSource.OPEN = NativeEventSource.OPEN;
    WrappedEventSource.CLOSED = NativeEventSource.CLOSED;
    WrappedEventSource.__pskaLlmProofWrapped = true;
    window.EventSource = WrappedEventSource;
  });
  return context;
}

async function waitForExtension(page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#pskaMiniChip", { state: "visible", timeout: 20000 });
  await page.waitForFunction(() => {
    return Boolean(
      window.PSKAMini
        && typeof window.PSKAMini.getTurnInstructions === "function"
        && typeof window.send === "function"
        && typeof window.api === "function"
        && window.send.__pskaMiniWrapped
        && window.api.__pskaMiniWrapped,
    );
  }, { timeout: 20000 });
}

async function setComposerQuestion(page, question) {
  const input = page.locator("#msg");
  await input.waitFor({ state: "visible", timeout: 15000 });
  await input.fill("");
  await input.click();
  await page.keyboard.type(question, { delay: 2 });
  await input.evaluate((el) => el.dispatchEvent(new Event("input", { bubbles: true })));
}

function eventToolName(event) {
  const json = event?.json || {};
  return String(json.name || json.tool || json.function_name || "").trim();
}

function isPskaToolName(name) {
  return /pska/i.test(String(name || ""));
}

function isWriteLikeToolName(name) {
  return /(?:memory|review|source|file|kanban|task|digest).*?(?:apply|write|save|create|update|patch|delete|remove|decision|archive)|(?:apply|write|save|create|update|patch|delete|remove|decision|archive).*?(?:memory|review|source|file|kanban|task|digest)/iu.test(String(name || ""));
}

function toolArgsPreview(event) {
  try {
    return JSON.stringify(event?.json?.args || {}).slice(0, 800);
  } catch (_) {
    return "";
  }
}

function isWriteLikeToolEvent(event) {
  const name = eventToolName(event);
  if (isWriteLikeToolName(name)) return true;
  if (!/(?:terminal|shell|exec|command)/iu.test(name)) return false;
  const args = toolArgsPreview(event);
  return /(?:^|[\s;&|])(?:rm|mv|cp|chmod|chown|mkdir|touch|tee|apply_patch)\b|(?:^|[\s;&|])git\s+(?:commit|push|reset|checkout|clean|rm)\b|(?:^|[\s;&|])sed\s+-i\b|(?:^|[\s;&|])curl\b[\s\S]*\s-X\s+(?:POST|PUT|PATCH|DELETE)\b|(?:^|[^>])>{1,2}\s*[^&\s]/iu.test(args);
}

function isBenignSandboxPageError(message) {
  const text = String(message || "");
  return text.includes("Failed to read the 'localStorage' property from 'Window'")
    && text.includes("document is sandboxed")
    && text.includes("allow-same-origin");
}

function assistantAnswerFromMessages(messages) {
  for (const message of [...(messages || [])].reverse()) {
    if (message?.role === "assistant") {
      return String(message.content || message.text || "").trim();
    }
  }
  return "";
}

async function cleanupSession(context, sessionId, checks) {
  if (!sessionId || KEEP_SESSION) return;
  const response = await context.request.post("/api/session/delete", {
    data: { session_id: sessionId },
  });
  const json = await safeJson(response);
  checks.push({
    name: "Cleanup temporary WebUI session",
    ok: response.ok() && json?.ok !== false,
    detail: { status: response.status(), kept: false },
  });
}

async function recordAnswerProof(context, {
  sessionId,
  checks,
  proofSummary,
  artifacts,
  startedAt,
  answer,
  cleanupOk,
}) {
  if (!RECORD_ANSWER_PROOF) return null;
  const payload = {
    session_id: sessionId,
    caller: "webui-extension-llm-proof",
    webui: WEBUI,
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    question_preview: QUESTION.slice(0, 600),
    question_sha256: sha256(QUESTION),
    answer_preview: String(answer || "").slice(0, 600),
    answer_sha256: answer ? sha256(answer) : "",
    answer_length: String(answer || "").length,
    dataset_ids: DATASET_ID ? [DATASET_ID] : [],
    source_root_ids: SOURCE_ROOT_ID ? [SOURCE_ROOT_ID] : [],
    proof_summary: proofSummary,
    checks,
    artifacts,
    read_only: (proofSummary.write_like_tools || []).length === 0,
    metadata: {
      script: "scripts/test_pska_webui_llm_proof.cjs",
      kept_session: KEEP_SESSION,
      cleanup_ok: Boolean(cleanupOk),
      output_dir: OUT_DIR,
    },
  };
  const response = await context.request.post(`${PSKA_API}/api/hermes/answer-proofs`, { data: payload });
  const json = await safeJson(response);
  assertCheck(checks, "Persist Hermes answer proof in PSKA audit", response.ok() && json?.ok !== false, {
    pska_api: PSKA_API,
    status: response.status(),
    proof_id: json?.proof?.proof_id || "",
    audit_event_id: json?.audit_event_id || "",
    error: json?.error || null,
  });
  return json;
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const { chromium } = loadPlaywright();
  if (!chromium) throw new Error(`Playwright module '${PLAYWRIGHT_MODULE}' does not expose chromium.`);
  const browser = await chromium.launch({
    headless: HEADLESS,
    channel: BROWSER_CHANNEL || undefined,
  });

  const checks = [];
  const artifacts = {};
  const startedAt = new Date().toISOString();
  const requests = [];
  let sessionId = "";
  let context = null;
  let cleanupAttempted = false;
  let proofSummary = {};
  let finalAnswer = "";
  let answerProofRecord = null;

  try {
    context = await prepareContext(browser, { width: 1280, height: 720 });
    await authenticate(context, checks);
    const page = await context.newPage();
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
    page.on("request", (request) => {
      if (request.url().includes("/api/chat/start") && request.method() === "POST") {
        const postData = request.postData() || "";
        let body = null;
        try {
          body = postData ? JSON.parse(postData) : null;
        } catch (_) {
          body = null;
        }
        requests.push({
          url: request.url(),
          method: request.method(),
          body_keys: Object.keys(body || {}).sort(),
          session_id: String(body?.session_id || ""),
          message_length: String(body?.message || "").length,
          has_forced_context: String(body?.message || "").includes("[FORCED SKILL CONTEXT: knowledge-retrieval]"),
          has_runtime_scope: String(body?.message || "").includes("## PSKA-Mini Runtime Scope"),
        });
      }
    });

    await waitForExtension(page);
    const runtime = await page.evaluate(({ datasetId, sourceRootId }) => {
      const state = window.PSKAMini.getState();
      const instructions = window.PSKAMini.getTurnInstructions();
      return {
        sendWrapped: Boolean(window.send && window.send.__pskaMiniWrapped),
        apiWrapped: Boolean(window.api && window.api.__pskaMiniWrapped),
        state,
        hasDataset: instructions.includes(datasetId),
        hasSourceRoot: instructions.includes(sourceRootId),
      };
    }, { datasetId: DATASET_ID, sourceRootId: SOURCE_ROOT_ID });
    assertCheck(checks, "PSKA runtime bridge is installed", runtime.sendWrapped && runtime.apiWrapped, runtime);
    assertCheck(checks, "PSKA runtime scope contains selected dataset and source root", runtime.hasDataset && runtime.hasSourceRoot, {
      dataset_id: DATASET_ID,
      source_root_id: SOURCE_ROOT_ID,
      state: runtime.state,
    });

    await setComposerQuestion(page, QUESTION);
    const chatStartRequestPromise = page.waitForRequest((request) => (
      request.url().includes("/api/chat/start") && request.method() === "POST"
    ), { timeout: 30000 });
    await Promise.all([
      chatStartRequestPromise,
      page.evaluate(() => window.send()),
    ]);
    const chatStartRequest = await chatStartRequestPromise;
    try {
      const body = JSON.parse(chatStartRequest.postData() || "{}");
      sessionId = String(body.session_id || "");
    } catch (_) {
      sessionId = "";
    }
    await page.waitForFunction(() => {
      const events = window.__pskaLlmProofEvents || [];
      return events.some((event) => event.type === "done" || event.type === "stream_end" || event.type === "apperror" || event.type === "error");
    }, null, { timeout: TIMEOUT_MS });
    await page.waitForTimeout(1000);

    const state = await page.evaluate((question) => {
      const events = window.__pskaLlmProofEvents || [];
      const appState = typeof S !== "undefined" ? S : (window.S || {});
      const messages = Array.isArray(appState?.messages) ? appState.messages : [];
      const session = appState?.session || null;
      const pane = document.querySelector("#msgInner");
      const paneText = pane?.innerText || "";
      const userRows = Array.from(document.querySelectorAll('.msg-row[data-role="user"]')).map((row) => ({
        text: row.innerText || "",
        raw: row.dataset.rawText || "",
      }));
      return {
        events,
        messages,
        session_id: session?.session_id || "",
        busy: Boolean(appState?.busy || appState?.activeStreamId),
        paneText,
        userRows,
        visibleQuestion: paneText.includes(question) || userRows.some((row) => row.text.includes(question) || row.raw.includes(question)),
        visibleForcedEnvelope: /\[FORCED SKILL CONTEXT:|\[USER OVERRIDE\]/u.test(paneText)
          || userRows.some((row) => /\[FORCED SKILL CONTEXT:|\[USER OVERRIDE\]/u.test(`${row.text}\n${row.raw}`)),
      };
    }, QUESTION);
    if (state.session_id) sessionId = state.session_id;

    const terminalErrors = state.events.filter((event) => ["apperror", "error", "cancel"].includes(event.type));
    const toolEvents = state.events.filter((event) => ["tool", "tool_complete"].includes(event.type));
    const toolNames = Array.from(new Set(toolEvents.map(eventToolName).filter(Boolean)));
    const pskaToolNames = toolNames.filter(isPskaToolName);
    const completedPskaTools = state.events
      .filter((event) => event.type === "tool_complete" && isPskaToolName(eventToolName(event)) && !event?.json?.is_error)
      .map(eventToolName);
    const writeLikeEvents = toolEvents.filter(isWriteLikeToolEvent);
    const writeLikeTools = Array.from(new Set(writeLikeEvents.map(eventToolName).filter(Boolean)));
    const answer = assistantAnswerFromMessages(state.messages);
    finalAnswer = answer;
    proofSummary = {
      tool_names: toolNames,
      completed_pska_tools: Array.from(new Set(completedPskaTools)),
      write_like_tools: writeLikeTools,
      tool_events: toolEvents.map((event) => ({
        type: event.type,
        name: eventToolName(event),
        is_error: Boolean(event?.json?.is_error),
        args_preview: toolArgsPreview(event),
      })),
      answer_length: answer.length,
    };

    assertCheck(checks, "Hermes /api/chat/start received PSKA forced context", requests.some((request) => request.has_forced_context && request.has_runtime_scope), {
      requests,
    });
    assertCheck(checks, "LLM stream completed without terminal error", terminalErrors.length === 0 && !state.busy, {
      terminal_errors: terminalErrors.map((event) => ({ type: event.type, json: event.json, data: String(event.data || "").slice(0, 400) })),
      busy: state.busy,
    });
    assertCheck(checks, "Answer-side turn used PSKA tools", pskaToolNames.length > 0 && completedPskaTools.length > 0, {
      tool_names: toolNames,
      completed_pska_tools: completedPskaTools,
    });
    assertCheck(checks, "Answer-side turn stayed read-only", writeLikeTools.length === 0, {
      tool_names: toolNames,
      write_like_tools: writeLikeTools,
      write_like_events: writeLikeEvents.map((event) => ({
        type: event.type,
        name: eventToolName(event),
        args_preview: toolArgsPreview(event),
      })),
    });
    assertCheck(checks, "Final answer is substantive and source-oriented", (
      answer.length >= 120
        && /Northstar|收入|现金流|库存|未交付订单|backlog|inventory|cash flow|revenue/iu.test(answer)
        && /来源|引用|证据|source|citation|RAGFlow|dataset|文档|财报|Q2/iu.test(answer)
    ), {
      answer_length: answer.length,
      answer_preview: answer.slice(0, 1000),
    });
    assertCheck(checks, "Visible user turn remains clean", state.visibleQuestion && !state.visibleForcedEnvelope, {
      visible_question: state.visibleQuestion,
      visible_forced_envelope: state.visibleForcedEnvelope,
      user_rows: state.userRows.slice(0, 3),
    });

    artifacts.llmProofScreenshot = path.join(OUT_DIR, "llm-proof.png");
    await page.screenshot({ path: artifacts.llmProofScreenshot, fullPage: false });
    const relevantPageErrors = pageErrors.filter((message) => !isBenignSandboxPageError(message));
    assertCheck(checks, "Browser page has no relevant uncaught errors", relevantPageErrors.length === 0, {
      relevant_page_errors: relevantPageErrors,
      ignored_page_errors: pageErrors.length - relevantPageErrors.length,
    });

    await cleanupSession(context, sessionId, checks);
    cleanupAttempted = true;

    const failedCleanup = checks.find((check) => check.name === "Cleanup temporary WebUI session" && !check.ok);
    if (failedCleanup) {
      throw new Error(`Cleanup temporary WebUI session failed: ${JSON.stringify(failedCleanup.detail)}`);
    }
    answerProofRecord = await recordAnswerProof(context, {
      sessionId,
      checks,
      proofSummary,
      artifacts,
      startedAt,
      answer: finalAnswer,
      cleanupOk: !failedCleanup,
    });
    await page.close();
    await context.close();
  } finally {
    if (context && sessionId && !cleanupAttempted && !KEEP_SESSION) {
      try {
        await cleanupSession(context, sessionId, checks);
      } catch (_) {}
    }
    await browser.close();
  }

  const failed = checks.filter((check) => !check.ok);
  const output = {
    ok: failed.length === 0,
    webui: WEBUI,
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    output_dir: OUT_DIR,
    question: QUESTION,
    session_id: sessionId,
    kept_session: KEEP_SESSION,
    artifacts,
    proof_summary: proofSummary,
    answer_proof_record: answerProofRecord,
    checks,
  };
  const resultPath = path.join(OUT_DIR, "llm-proof-results.json");
  fs.writeFileSync(resultPath, JSON.stringify(output, null, 2));
  console.log(JSON.stringify(output, null, 2));
  process.exit(failed.length ? 1 : 0);
}

main().catch((error) => {
  const output = {
    ok: false,
    webui: WEBUI,
    output_dir: OUT_DIR,
    error: error?.stack || String(error),
  };
  try {
    fs.mkdirSync(OUT_DIR, { recursive: true });
    fs.writeFileSync(path.join(OUT_DIR, "llm-proof-results.json"), JSON.stringify(output, null, 2));
  } catch (_) {}
  console.error(output.error);
  process.exit(1);
});
