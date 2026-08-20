#!/usr/bin/env node

const fs = require("fs");
const os = require("os");
const path = require("path");

const WEBUI = stripTrailingSlash(process.env.HERMES_WEBUI_URL || "http://127.0.0.1:8787");
const PASSWORD = process.env.HERMES_WEBUI_PASSWORD || process.env.PSKA_WEBUI_TEST_PASSWORD || "";
const PLAYWRIGHT_MODULE = process.env.PSKA_PLAYWRIGHT_MODULE || process.env.PLAYWRIGHT_MODULE || "playwright";
const BROWSER_CHANNEL = process.env.PSKA_PLAYWRIGHT_CHANNEL || "";
const DATASET_ID = process.env.PSKA_TEST_DATASET_ID || "07f35e1a9b9411f197ff8391030412c0";
const SOURCE_ROOT_ID = process.env.PSKA_TEST_SOURCE_ROOT_ID || "root_ebdf0044b0442f494246012f";
const QUESTION = process.env.PSKA_TURN_BRIDGE_QUESTION || `PSKA turn bridge smoke ${Date.now()} Northstar Robotics revenue risk`;
const OUT_DIR = process.env.PSKA_TURN_BRIDGE_OUT || path.join(os.tmpdir(), `pska-webui-turn-bridge-${timestampSlug()}`);
const HEADLESS = !truthy(process.env.PSKA_PLAYWRIGHT_HEADED);
const STORAGE_KEY = "pska-mini.hermes-webui.scope.v1";

function usage() {
  console.log(`Usage: node scripts/test_pska_webui_turn_bridge.cjs

Environment:
  HERMES_WEBUI_URL            default: http://127.0.0.1:8787
  HERMES_WEBUI_PASSWORD       required when WebUI auth is enabled
  PSKA_WEBUI_TEST_PASSWORD    alternate password env
  PSKA_PLAYWRIGHT_MODULE      playwright or playwright-core, default: playwright
  PSKA_PLAYWRIGHT_CHANNEL     optional browser channel, e.g. chrome
  PSKA_TEST_DATASET_ID        dataset selected in PSKA scope
  PSKA_TEST_SOURCE_ROOT_ID    source root selected in PSKA scope
  PSKA_TURN_BRIDGE_QUESTION   user-visible prompt to send
  PSKA_TURN_BRIDGE_OUT        output directory, default: /tmp/pska-webui-turn-bridge-*
  PSKA_PLAYWRIGHT_HEADED      set to 1 for headed browser

This live browser smoke intercepts Hermes WebUI /api/chat/start. It verifies
that the PSKA mini extension injects the forced skill context into the actual
chat-start payload while leaving the visible user turn clean.`);
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

function timestampSlug() {
  return new Date().toISOString().replace(/[:.]/gu, "-");
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
    console.error("  NODE_PATH=/tmp/pska-playwright/node_modules PSKA_PLAYWRIGHT_MODULE=playwright-core PSKA_PLAYWRIGHT_CHANNEL=chrome node scripts/test_pska_webui_turn_bridge.cjs");
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

async function safeJson(response) {
  try {
    return await response.json();
  } catch (_) {
    return null;
  }
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

function timeoutPromise(ms, label) {
  return new Promise((_, reject) => {
    setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
  });
}

function forcedContextCount(text) {
  return (String(text || "").match(/\[FORCED SKILL CONTEXT:/gu) || []).length;
}

function isBenignSandboxPageError(message) {
  const text = String(message || "");
  return text.includes("Failed to read the 'localStorage' property from 'Window'")
    && text.includes("document is sandboxed")
    && text.includes("allow-same-origin");
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
  let capturedChatStart = null;
  let capturedResolver = null;
  const capturedPromise = new Promise((resolve) => {
    capturedResolver = resolve;
  });

  try {
    const context = await prepareContext(browser, { width: 1280, height: 720 });
    await authenticate(context, checks);
    const page = await context.newPage();
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));

    await page.route("**/api/chat/start", async (route) => {
      const request = route.request();
      const postData = request.postData() || "";
      let body = null;
      try {
        body = postData ? JSON.parse(postData) : null;
      } catch (_) {
        body = null;
      }
      capturedChatStart = {
        url: request.url(),
        method: request.method(),
        postData,
        body,
      };
      if (capturedResolver) capturedResolver(capturedChatStart);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          stream_id: "pska_turn_bridge_stream",
          title: "PSKA bridge smoke",
          pending_started_at: Date.now() / 1000,
          effective_model: body?.model || "",
          effective_model_provider: body?.model_provider || "",
        }),
      });
    });

    await page.route("**/api/chat/stream?**", async (route) => {
      const sessionId = capturedChatStart?.body?.session_id || "pska-turn-bridge-session";
      const done = {
        status: "completed",
        stream_id: "pska_turn_bridge_stream",
        session: {
          session_id: sessionId,
          title: "PSKA bridge smoke",
          messages: [
            { role: "user", content: QUESTION, _ts: Date.now() / 1000 },
            { role: "assistant", content: "PSKA turn bridge smoke complete.", _ts: Date.now() / 1000 },
          ],
          message_count: 2,
        },
      };
      await route.fulfill({
        status: 200,
        headers: {
          "content-type": "text/event-stream; charset=utf-8",
          "cache-control": "no-cache",
          connection: "close",
        },
        body: `event: done\ndata: ${JSON.stringify(done)}\n\n`,
      });
    });

    await page.route("**/api/chat/stream/status?**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, active: false, stream_id: "pska_turn_bridge_stream" }),
      });
    });

    await waitForExtension(page);
    const runtime = await page.evaluate(({ datasetId, sourceRootId }) => {
      const state = window.PSKAMini.getState();
      const instructions = window.PSKAMini.getTurnInstructions();
      return {
        sendWrapped: Boolean(window.send && window.send.__pskaMiniWrapped),
        apiWrapped: Boolean(window.api && window.api.__pskaMiniWrapped),
        state,
        instructions,
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
    await Promise.all([
      capturedPromise,
      page.evaluate(() => window.send()),
    ]);
    const captured = await Promise.race([capturedPromise, timeoutPromise(20000, "chat-start capture")]);
    const body = captured.body || {};
    const message = String(body.message || "");
    assertCheck(checks, "Hermes /api/chat/start was intercepted", captured.method === "POST" && Boolean(body.session_id), {
      method: captured.method,
      has_session_id: Boolean(body.session_id),
      keys: Object.keys(body).sort(),
    });
    assertCheck(checks, "Chat-start payload contains forced PSKA skill context", (
      message.includes("[USER OVERRIDE]")
        && message.includes("[FORCED SKILL CONTEXT: knowledge-retrieval]")
        && message.includes("## PSKA-Mini Runtime Scope")
        && message.includes(DATASET_ID)
        && message.includes(SOURCE_ROOT_ID)
        && message.includes(QUESTION)
        && forcedContextCount(message) === 1
    ), {
      has_user_override: message.includes("[USER OVERRIDE]"),
      has_forced_context: message.includes("[FORCED SKILL CONTEXT: knowledge-retrieval]"),
      has_runtime_scope: message.includes("## PSKA-Mini Runtime Scope"),
      has_dataset: message.includes(DATASET_ID),
      has_source_root: message.includes(SOURCE_ROOT_ID),
      has_question: message.includes(QUESTION),
      forced_context_count: forcedContextCount(message),
      message_preview: message.slice(0, 500),
    });

    await page.waitForTimeout(800);
    const visible = await page.evaluate((question) => {
      const pane = document.querySelector("#msgInner");
      const paneText = pane?.innerText || "";
      const userRows = Array.from(document.querySelectorAll('.msg-row[data-role="user"]')).map((row) => ({
        text: row.innerText || "",
        raw: row.dataset.rawText || "",
      }));
      return {
        paneText,
        userRows,
        composer: document.getElementById("msg")?.value || "",
        visibleQuestion: paneText.includes(question) || userRows.some((row) => row.text.includes(question) || row.raw.includes(question)),
        visibleForcedEnvelope: /\[FORCED SKILL CONTEXT:|\[USER OVERRIDE\]/u.test(paneText)
          || userRows.some((row) => /\[FORCED SKILL CONTEXT:|\[USER OVERRIDE\]/u.test(`${row.text}\n${row.raw}`)),
      };
    }, QUESTION);
    assertCheck(checks, "Visible user turn remains clean", visible.visibleQuestion && !visible.visibleForcedEnvelope, {
      visible_question: visible.visibleQuestion,
      visible_forced_envelope: visible.visibleForcedEnvelope,
      composer_empty: visible.composer === "",
      user_rows: visible.userRows.slice(0, 3),
    });

    artifacts.turnBridgeScreenshot = path.join(OUT_DIR, "turn-bridge.png");
    await page.screenshot({ path: artifacts.turnBridgeScreenshot, fullPage: false });
    const relevantPageErrors = pageErrors.filter((message) => !isBenignSandboxPageError(message));
    assertCheck(checks, "Browser page has no relevant uncaught errors", relevantPageErrors.length === 0, {
      relevant_page_errors: relevantPageErrors,
      ignored_page_errors: pageErrors.length - relevantPageErrors.length,
    });

    await page.close();
    await context.close();
  } finally {
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
    artifacts,
    checks,
    captured_chat_start: capturedChatStart ? {
      url: capturedChatStart.url,
      method: capturedChatStart.method,
      body_keys: Object.keys(capturedChatStart.body || {}).sort(),
      message_length: String(capturedChatStart.body?.message || "").length,
      forced_context_count: forcedContextCount(capturedChatStart.body?.message),
    } : null,
  };
  const resultPath = path.join(OUT_DIR, "turn-bridge-results.json");
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
    fs.writeFileSync(path.join(OUT_DIR, "turn-bridge-results.json"), JSON.stringify(output, null, 2));
  } catch (_) {}
  console.error(output.error);
  process.exit(1);
});
