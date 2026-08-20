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
const OUT_DIR = process.env.PSKA_VISUAL_OUT || path.join(os.tmpdir(), `pska-webui-visual-${timestampSlug()}`);
const HEADLESS = !truthy(process.env.PSKA_PLAYWRIGHT_HEADED);
const STORAGE_KEY = "pska-mini.hermes-webui.scope.v1";

function usage() {
  console.log(`Usage: node scripts/test_pska_webui_visual.cjs

Environment:
  HERMES_WEBUI_URL            default: http://127.0.0.1:8787
  HERMES_WEBUI_PASSWORD       required when WebUI auth is enabled
  PSKA_WEBUI_TEST_PASSWORD    alternate password env
  PSKA_PLAYWRIGHT_MODULE      playwright or playwright-core, default: playwright
  PSKA_PLAYWRIGHT_CHANNEL     optional browser channel, e.g. chrome
  PSKA_TEST_DATASET_ID        dataset selected in PSKA scope
  PSKA_TEST_SOURCE_ROOT_ID    source root selected in PSKA scope
  PSKA_VISUAL_OUT             output directory, default: /tmp/pska-webui-visual-*
  PSKA_PLAYWRIGHT_HEADED      set to 1 for headed browser

This is a live browser smoke for the Hermes WebUI PSKA extension. It writes
screenshots and visual-results.json to PSKA_VISUAL_OUT.`);
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
    console.error("  NODE_PATH=/tmp/pska-playwright/node_modules PSKA_PLAYWRIGHT_MODULE=playwright-core PSKA_PLAYWRIGHT_CHANNEL=chrome node scripts/test_pska_webui_visual.cjs");
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
    },
    { storageKey: STORAGE_KEY, datasetId: DATASET_ID, sourceRootId: SOURCE_ROOT_ID },
  );
  return context;
}

async function waitForExtension(page, options = {}) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#pskaMiniChip", { state: "visible", timeout: 20000 });
  if (options.requireRail !== false) {
    await page.waitForSelector("#pskaMiniRailButton", { state: "visible", timeout: 20000 });
  }
}

async function openMenuAndWait(page) {
  await page.click("#pskaMiniChip");
  await page.waitForSelector("#pskaMiniMenu", { state: "visible", timeout: 10000 });
  await page.evaluate(() => window.PSKAMini?.refresh?.()).catch(() => {});
  try {
    await page.waitForFunction(() => {
      const text = document.querySelector("#pskaMiniStatus")?.innerText || "";
      return /API\s+ready/iu.test(text)
        && /KB\s+(\d+\/\d+|ready)/iu.test(text)
        && /Embedding\s+(local|TEI|external)/iu.test(text)
        && /Alpha\s+(alpha_ready|not visible)/iu.test(text);
    }, undefined, { timeout: 45000 });
  } catch (error) {
    const statusText = await page.locator("#pskaMiniStatus").innerText().catch(() => "");
    throw new Error(`${error.message}\nPSKA menu status at timeout:\n${statusText}`);
  }
}

async function pageText(page, selector) {
  return page.locator(selector).evaluate((el) => el.innerText || el.textContent || "");
}

async function runDesktop(context, checks, artifacts) {
  const page = await context.newPage();
  const consoleWarningsAndErrors = [];
  page.on("console", (msg) => {
    if (["warning", "error"].includes(msg.type())) {
      consoleWarningsAndErrors.push({ type: msg.type(), text: msg.text() });
    }
  });
  await waitForExtension(page);
  await openMenuAndWait(page);

  const menuCheck = await page.evaluate(() => {
    const menu = document.querySelector("#pskaMiniMenu");
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const rect = menu ? {
      top: Math.round(menu.getBoundingClientRect().top),
      right: Math.round(menu.getBoundingClientRect().right),
      bottom: Math.round(menu.getBoundingClientRect().bottom),
      left: Math.round(menu.getBoundingClientRect().left),
      width: Math.round(menu.getBoundingClientRect().width),
      height: Math.round(menu.getBoundingClientRect().height),
    } : null;
    return {
      visible: Boolean(menu && !menu.hidden),
      rect,
      overflows: {
        top: !rect || rect.top < 0,
        right: !rect || rect.right > viewport.width,
        bottom: !rect || rect.bottom > viewport.height,
        left: !rect || rect.left < 0,
      },
      statusText: document.querySelector("#pskaMiniStatus")?.innerText || "",
    };
  });
  assertCheck(
    checks,
    "Desktop menu visible and in viewport",
    menuCheck.visible
      && !Object.values(menuCheck.overflows).some(Boolean)
      && /Embedding\s+(local|TEI|external)/iu.test(menuCheck.statusText)
      && /Alpha\s+(alpha_ready|not visible)/iu.test(menuCheck.statusText),
    menuCheck,
  );
  artifacts.desktopMenu = path.join(OUT_DIR, "desktop-menu.png");
  await page.screenshot({ path: artifacts.desktopMenu, fullPage: false });

  await page.click("#pskaMiniSourceRecall");
  await page.waitForFunction(() => {
    const box = document.querySelector("#pskaMiniPreviewBox");
    const text = box?.innerText || "";
    return !box?.hidden && /Source Recall/iu.test(text) && /result/iu.test(text);
  }, { timeout: 30000 });
  const sourceRecallText = await pageText(page, "#pskaMiniPreviewBox");
  assertCheck(checks, "Desktop Source Recall returns visible results", /Source Recall/iu.test(sourceRecallText) && /\d+\s+result/iu.test(sourceRecallText), {
    text: sourceRecallText.slice(0, 600),
  });
  artifacts.desktopSourceRecall = path.join(OUT_DIR, "desktop-source-recall.png");
  await page.screenshot({ path: artifacts.desktopSourceRecall, fullPage: false });

  await page.click("#pskaMiniAgenticBrief");
  await page.waitForFunction(() => {
    const text = document.querySelector("#pskaMiniPreviewBox")?.innerText || "";
    return /Agentic Brief/iu.test(text) && /Specialists:/iu.test(text);
  }, { timeout: 30000 });
  const agenticBriefText = await pageText(page, "#pskaMiniPreviewBox");
  assertCheck(checks, "Desktop Agentic Brief shows specialist profiles", (
    /Agentic Brief/iu.test(agenticBriefText)
      && /Specialists:/iu.test(agenticBriefText)
      && /Specialist/iu.test(agenticBriefText)
      && /read tool/iu.test(agenticBriefText)
  ), {
    text: agenticBriefText.slice(0, 900),
  });

  await page.click("#pskaMiniClose");
  await page.waitForSelector("#pskaMiniMenu", { state: "hidden", timeout: 10000 });
  await page.click("#pskaMiniRailButton");
  await page.waitForSelector("#mainPskaMini", { state: "visible", timeout: 10000 });
  await page.waitForFunction(() => {
    const status = document.querySelector("#pskaMiniPageStatus")?.innerText || "";
    const count = document.querySelector("#pskaMiniMemoryCount")?.innerText || "";
    const memoryText = document.querySelector("#pskaMiniMemoryResults")?.innerText || "";
    const reviewText = document.querySelector("#pskaMiniReviewList")?.innerText || "";
    const firstRunText = document.querySelector("#pskaMiniFirstRun")?.innerText || "";
    const answerProofText = document.querySelector("#pskaMiniAnswerProofs")?.innerText || "";
    const countMatch = count.match(/(\d+)\s+shown/iu);
    const alphaReadyVisible = /Alpha\s+alpha_ready/iu.test(status) || /readiness\s+alpha_ready/iu.test(firstRunText);
    return /API\s+ready/iu.test(status)
      && /Embedding\s+(local|TEI|external)/iu.test(status)
      && alphaReadyVisible
      && /First-run checklist/iu.test(firstRunText)
      && /Confirm runtime and providers/iu.test(firstRunText)
      && /Rehearse source evidence to memory/iu.test(firstRunText)
      && !/Loading answer proofs/iu.test(answerProofText)
      && countMatch
      && Number(countMatch[1]) > 0
      && !/Loading memory/iu.test(memoryText)
      && !/Loading reviews/iu.test(reviewText);
  }, undefined, { timeout: 60000 });
  const memoryCheck = await page.evaluate(() => ({
    visible: Boolean(document.querySelector("#mainPskaMini")),
    title: document.querySelector("#mainPskaMini .main-view-title")?.innerText || "",
    subtitle: document.querySelector("#mainPskaMini .pska-mini-page-sub")?.innerText || "",
    status: document.querySelector("#pskaMiniPageStatus")?.innerText || "",
    firstRun: document.querySelector("#pskaMiniFirstRun")?.innerText?.slice(0, 1200) || "",
    answerProofs: document.querySelector("#pskaMiniAnswerProofs")?.innerText?.slice(0, 1200) || "",
    hasAnswerProofButton: Boolean(document.querySelector("[data-pska-answer-proof-id]")),
    hasReviewViewButton: Boolean(document.querySelector('[data-pska-review-action="view"]')),
    count: document.querySelector("#pskaMiniMemoryCount")?.innerText || "",
    fullText: document.querySelector("#mainPskaMini")?.innerText?.slice(0, 2000) || "",
    firstMemory: document.querySelector("#pskaMiniMemoryResults")?.innerText?.slice(0, 400) || "",
    firstReview: document.querySelector("#pskaMiniReviewList")?.innerText?.slice(0, 400) || "",
  }));
  const countMatch = memoryCheck.count.match(/(\d+)\s+shown/iu);
  assertCheck(
    checks,
    "Memory page visible with memory and review data",
    memoryCheck.visible
      && /PSKA Memory/iu.test(memoryCheck.title)
      && /governed memory and review queue/iu.test(memoryCheck.subtitle)
      && /Embedding\s+(local|TEI|external)/iu.test(memoryCheck.status)
      && (/Alpha\s+alpha_ready/iu.test(memoryCheck.status) || /readiness\s+alpha_ready/iu.test(memoryCheck.firstRun))
      && /First-run checklist/iu.test(memoryCheck.firstRun)
      && /Confirm runtime and providers/iu.test(memoryCheck.firstRun)
      && /Rehearse source evidence to memory/iu.test(memoryCheck.firstRun)
      && /readiness\s+alpha_ready/iu.test(memoryCheck.firstRun)
      && /recovery/iu.test(memoryCheck.firstRun)
      && memoryCheck.answerProofs
      && !/Loading answer proofs/iu.test(memoryCheck.answerProofs)
      && countMatch
      && Number(countMatch[1]) > 0
      && !/SQLite memory/iu.test(memoryCheck.fullText)
      && !/Loading memory/iu.test(memoryCheck.firstMemory)
      && !/Loading reviews/iu.test(memoryCheck.firstReview),
    memoryCheck,
  );

  if (memoryCheck.hasReviewViewButton) {
    await page.click('[data-pska-review-action="view"]');
    await page.waitForFunction(() => {
      const detail = document.querySelector("#pskaMiniReviewDetail")?.innerText || "";
      return /Review Detail/iu.test(detail) && /Mark review inspected/iu.test(detail);
    }, { timeout: 20000 });
    const reviewDetailText = await pageText(page, "#pskaMiniReviewDetail");
    assertCheck(checks, "Review detail exposes first-run inspection action", (
      /Review Detail/iu.test(reviewDetailText)
        && /First-run evidence/iu.test(reviewDetailText)
        && /Mark review inspected/iu.test(reviewDetailText)
    ), {
      text: reviewDetailText.slice(0, 900),
    });
    await page.click("[data-pska-first-run-review-done]");
    await page.waitForFunction(() => {
      const items = Array.from(document.querySelectorAll(".pska-mini-first-run-item"));
      const item = items.find((node) => /Inspect Memory Review queue/iu.test(node.innerText || ""));
      const text = item?.innerText || "";
      const note = item?.querySelector("textarea")?.value || "";
      return /done\s+·\s+required/iu.test(text) && /review/iu.test(note);
    }, { timeout: 15000 });
    const reviewQueueCheck = await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".pska-mini-first-run-item"));
      const item = items.find((node) => /Inspect Memory Review queue/iu.test(node.innerText || ""));
      return {
        text: item?.innerText?.slice(0, 900) || "",
        note: item?.querySelector("textarea")?.value || "",
      };
    });
    assertCheck(checks, "Review detail marks first-run review queue done with review note", (
      /done\s+·\s+required/iu.test(reviewQueueCheck.text)
        && /review/iu.test(reviewQueueCheck.note)
        && /source refs|pending|accepted|rejected|applied/iu.test(reviewQueueCheck.note)
    ), reviewQueueCheck);
  } else {
    checks.push({
      name: "Review detail exposes first-run inspection action",
      ok: true,
      detail: { skipped: "No review candidate available in current queue" },
    });
    checks.push({
      name: "Review detail marks first-run review queue done with review note",
      ok: true,
      detail: { skipped: "No review candidate available in current queue" },
    });
  }

  await page.fill("#pskaMiniSourceEvidenceQuery", "Northstar Robotics");
  await page.click("#pskaMiniSourceEvidenceSearch");
  await page.waitForFunction(() => {
    const count = document.querySelector("#pskaMiniSourceEvidenceCount")?.innerText || "";
    const results = document.querySelector("#pskaMiniSourceEvidenceResults")?.innerText || "";
    const countMatch = count.match(/(\d+)\s+shown/iu);
    return countMatch && Number(countMatch[1]) > 0 && /Northstar|Robotics|Finance/iu.test(results);
  }, { timeout: 30000 });
  const sourceEvidenceSearch = await page.evaluate(() => ({
    count: document.querySelector("#pskaMiniSourceEvidenceCount")?.innerText || "",
    scope: document.querySelector("#pskaMiniSourceEvidenceScope")?.innerText || "",
    results: document.querySelector("#pskaMiniSourceEvidenceResults")?.innerText?.slice(0, 1200) || "",
    hasRead: Boolean(document.querySelector('[data-pska-source-evidence-action="read"]')),
    hasDraft: Boolean(document.querySelector('[data-pska-source-evidence-action="draft"]')),
  }));
  assertCheck(checks, "Source Evidence search returns selected source results", (
    /\d+\s+shown/iu.test(sourceEvidenceSearch.count)
      && /Scope:/iu.test(sourceEvidenceSearch.scope)
      && /Northstar|Robotics|Finance/iu.test(sourceEvidenceSearch.results)
      && sourceEvidenceSearch.hasRead
      && sourceEvidenceSearch.hasDraft
  ), sourceEvidenceSearch);

  await page.click('[data-pska-source-evidence-action="read"]');
  await page.waitForFunction(() => {
    const detail = document.querySelector("#pskaMiniSourceEvidenceDetail")?.innerText || "";
    return /Source Evidence Detail/iu.test(detail) && /Northstar|Robotics|Finance/iu.test(detail);
  }, { timeout: 20000 });
  const sourceEvidenceDetail = await pageText(page, "#pskaMiniSourceEvidenceDetail");
  assertCheck(checks, "Source Evidence detail reads full source through PSKA", (
    /Source Evidence Detail/iu.test(sourceEvidenceDetail)
      && /Adapter/iu.test(sourceEvidenceDetail)
      && /Path/iu.test(sourceEvidenceDetail)
      && /Northstar|Robotics|Finance/iu.test(sourceEvidenceDetail)
  ), {
    text: sourceEvidenceDetail.slice(0, 1200),
  });

  await page.click('[data-pska-source-evidence-action="draft-detail"]');
  await page.waitForFunction(() => {
    const draft = document.querySelector("#pskaMiniMemoryDraft")?.value || "";
    const source = document.querySelector("#pskaMiniMemoryDraftSource")?.innerText || "";
    return /请先把这条资料证据改写成一条稳定记忆/iu.test(draft) && /source evidence/iu.test(source);
  }, { timeout: 10000 });
  const sourceEvidenceDraft = await page.evaluate(() => ({
    draft: document.querySelector("#pskaMiniMemoryDraft")?.value?.slice(0, 1000) || "",
    source: document.querySelector("#pskaMiniMemoryDraftSource")?.innerText || "",
  }));
  assertCheck(checks, "Source Evidence can draft a sourced memory candidate", (
    /请先把这条资料证据改写成一条稳定记忆/iu.test(sourceEvidenceDraft.draft)
      && /资料标题/iu.test(sourceEvidenceDraft.draft)
      && /证据摘录/iu.test(sourceEvidenceDraft.draft)
      && /source evidence/iu.test(sourceEvidenceDraft.source)
  ), sourceEvidenceDraft);

  await page.click("[data-pska-first-run-rehearsal-done]");
  await page.waitForFunction(() => {
    const items = Array.from(document.querySelectorAll(".pska-mini-first-run-item"));
    const item = items.find((node) => /Rehearse source evidence to memory/iu.test(node.innerText || ""));
    const text = item?.innerText || "";
    return /done\s+·\s+required/iu.test(text) && /source evidence/iu.test(text);
  }, { timeout: 15000 });
  const rehearsalCheck = await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll(".pska-mini-first-run-item"));
    const item = items.find((node) => /Rehearse source evidence to memory/iu.test(node.innerText || ""));
    return {
      text: item?.innerText?.slice(0, 900) || "",
      note: item?.querySelector("textarea")?.value || "",
    };
  });
  assertCheck(checks, "Source Evidence marks first-run rehearsal done with source note", (
    /done\s+·\s+required/iu.test(rehearsalCheck.text)
      && /source evidence/iu.test(rehearsalCheck.note)
      && /Northstar Robotics/iu.test(rehearsalCheck.note)
  ), rehearsalCheck);
  artifacts.desktopSourceEvidence = path.join(OUT_DIR, "desktop-source-evidence.png");
  await page.screenshot({ path: artifacts.desktopSourceEvidence, fullPage: false });

  if (memoryCheck.hasAnswerProofButton) {
    await page.click("[data-pska-answer-proof-id]");
    await page.waitForFunction(() => {
      const detail = document.querySelector("#pskaMiniAnswerProofDetail")?.innerText || "";
      return /Answer Proof Detail/iu.test(detail) && /Completed PSKA tools/iu.test(detail) && /Trace entries/iu.test(detail);
    }, { timeout: 20000 });
    const proofDetail = await pageText(page, "#pskaMiniAnswerProofDetail");
    assertCheck(checks, "Answer proof detail shows trace and tools", (
      /Answer Proof Detail/iu.test(proofDetail)
        && /Completed PSKA tools/iu.test(proofDetail)
        && /Draft Memory Candidate/iu.test(proofDetail)
        && /Mark sourced Ask done/iu.test(proofDetail)
        && /Trace entries/iu.test(proofDetail)
        && /hermes\.answer_proof|answer proof|trace/iu.test(proofDetail)
    ), {
      text: proofDetail.slice(0, 1200),
    });
    await page.click("[data-pska-first-run-sourced-ask-done]");
    await page.waitForFunction(() => {
      const items = Array.from(document.querySelectorAll(".pska-mini-first-run-item"));
      const item = items.find((node) => /Run one sourced Ask/iu.test(node.innerText || ""));
      const text = item?.innerText || "";
      const note = item?.querySelector("textarea")?.value || "";
      return /done\s+·\s+required/iu.test(text) && /answer proof/iu.test(note);
    }, { timeout: 15000 });
    const sourcedAskCheck = await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll(".pska-mini-first-run-item"));
      const item = items.find((node) => /Run one sourced Ask/iu.test(node.innerText || ""));
      return {
        text: item?.innerText?.slice(0, 900) || "",
        note: item?.querySelector("textarea")?.value || "",
      };
    });
    assertCheck(checks, "Answer proof marks first-run sourced Ask done with proof note", (
      /done\s+·\s+required/iu.test(sourcedAskCheck.text)
        && /answer proof/iu.test(sourcedAskCheck.note)
        && /source root|KB|pska_/iu.test(sourcedAskCheck.note)
    ), sourcedAskCheck);
    await page.click("[data-pska-answer-proof-draft]");
    await page.waitForFunction(() => {
      const draft = document.querySelector("#pskaMiniMemoryDraft")?.value || "";
      const source = document.querySelector("#pskaMiniMemoryDraftSource")?.innerText || "";
      return /请先改写这份 Answer Proof 草稿/iu.test(draft) && /answer proof/iu.test(source);
    }, { timeout: 10000 });
    const proofDraft = await page.evaluate(() => ({
      draft: document.querySelector("#pskaMiniMemoryDraft")?.value?.slice(0, 1000) || "",
      source: document.querySelector("#pskaMiniMemoryDraftSource")?.innerText || "",
    }));
    assertCheck(checks, "Answer proof can draft a sourced memory candidate", (
      /请先改写这份 Answer Proof 草稿/iu.test(proofDraft.draft)
        && /来源问题/iu.test(proofDraft.draft)
        && /建议记忆/iu.test(proofDraft.draft)
        && /answer proof/iu.test(proofDraft.source)
    ), proofDraft);
  } else {
    checks.push({
      name: "Answer proof detail shows trace and tools",
      ok: true,
      detail: { skipped: "No answer proof recorded yet" },
    });
    checks.push({
      name: "Answer proof can draft a sourced memory candidate",
      ok: true,
      detail: { skipped: "No answer proof recorded yet" },
    });
  }
  artifacts.desktopMemoryPage = path.join(OUT_DIR, "desktop-memory-page.png");
  await page.screenshot({ path: artifacts.desktopMemoryPage, fullPage: false });

  await page.close();
  return consoleWarningsAndErrors;
}

async function runMobile(context, checks, artifacts) {
  const page = await context.newPage();
  await page.setViewportSize({ width: 390, height: 844 });
  await waitForExtension(page, { requireRail: false });
  const chipCheck = await page.evaluate(() => {
    const visibleRect = (el) => {
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      return {
        top: Math.round(rect.top),
        right: Math.round(rect.right),
        bottom: Math.round(rect.bottom),
        left: Math.round(rect.left),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      };
    };
    const overflows = (rect, viewport) => ({
      top: !rect || rect.top < 0,
      right: !rect || rect.right > viewport.width,
      bottom: !rect || rect.bottom > viewport.height,
      left: !rect || rect.left < 0,
    });
    const intersects = (a, b) => {
      if (!a || !b) return false;
      return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
    };
    const chip = document.querySelector("#pskaMiniChip");
    const send = Array.from(document.querySelectorAll("button")).find((button) => {
      const text = [
        button.id,
        button.getAttribute("aria-label"),
        button.getAttribute("title"),
        button.textContent,
      ].join(" ");
      return /send|发送/iu.test(text) && button.offsetParent !== null;
    }) || null;
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const chipRect = visibleRect(chip);
    const sendRect = visibleRect(send);
    return {
      labelText: document.querySelector("#pskaMiniLabel")?.innerText || "",
      chip: chipRect,
      send: sendRect,
      withinViewport: chipRect && !Object.values(overflows(chipRect, viewport)).some(Boolean),
      overlapsSend: intersects(chipRect, sendRect),
    };
  });
  assertCheck(checks, "Mobile PSKA chip visible and not overlapping send", chipCheck.labelText === "PSKA" && chipCheck.withinViewport && !chipCheck.overlapsSend, chipCheck);
  artifacts.mobileChip = path.join(OUT_DIR, "mobile-chip.png");
  await page.screenshot({ path: artifacts.mobileChip, fullPage: false });

  await openMenuAndWait(page);
  const menuCheck = await page.evaluate(() => {
    const menu = document.querySelector("#pskaMiniMenu");
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const rect = menu ? {
      top: Math.round(menu.getBoundingClientRect().top),
      right: Math.round(menu.getBoundingClientRect().right),
      bottom: Math.round(menu.getBoundingClientRect().bottom),
      left: Math.round(menu.getBoundingClientRect().left),
      width: Math.round(menu.getBoundingClientRect().width),
      height: Math.round(menu.getBoundingClientRect().height),
    } : null;
    return {
      visible: Boolean(menu && !menu.hidden),
      rect,
      overflows: {
        top: !rect || rect.top < 0,
        right: !rect || rect.right > viewport.width,
        bottom: !rect || rect.bottom > viewport.height,
        left: !rect || rect.left < 0,
      },
      statusText: document.querySelector("#pskaMiniStatus")?.innerText || "",
    };
  });
  assertCheck(
    checks,
    "Mobile menu visible and in viewport",
    menuCheck.visible
      && !Object.values(menuCheck.overflows).some(Boolean)
      && /Embedding\s+(local|TEI|external)/iu.test(menuCheck.statusText)
      && /Alpha\s+(alpha_ready|not visible)/iu.test(menuCheck.statusText),
    menuCheck,
  );
  artifacts.mobileMenu = path.join(OUT_DIR, "mobile-menu.png");
  await page.screenshot({ path: artifacts.mobileMenu, fullPage: false });
  await page.close();
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
  let consoleWarningsAndErrors = [];
  try {
    const context = await prepareContext(browser, { width: 1280, height: 720 });
    await authenticate(context, checks);
    consoleWarningsAndErrors = await runDesktop(context, checks, artifacts);
    await runMobile(context, checks, artifacts);
    await context.close();
  } finally {
    await browser.close();
  }
  assertCheck(checks, "Console has no warnings or errors", consoleWarningsAndErrors.length === 0, { consoleWarningsAndErrors });
  const failed = checks.filter((check) => !check.ok);
  const output = {
    ok: failed.length === 0,
    webui: WEBUI,
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    output_dir: OUT_DIR,
    artifacts,
    checks,
    consoleWarningsAndErrors,
  };
  const resultPath = path.join(OUT_DIR, "visual-results.json");
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
    fs.writeFileSync(path.join(OUT_DIR, "visual-results.json"), JSON.stringify(output, null, 2));
  } catch (_) {}
  console.error(output.error);
  process.exit(1);
});
