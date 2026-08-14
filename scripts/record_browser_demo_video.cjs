#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..");
const DEMO_DIR = path.join(ROOT, "demo", "browser", "pska_webui_demo");
const SOURCE_DIR = path.join(DEMO_DIR, "source");
const NOTE_PATH = path.join(SOURCE_DIR, "pska-demo-note.md");
const DIST_DIR = path.join(DEMO_DIR, "dist");
const BUILD_DIR = path.join(DIST_DIR, "playwright-build");
const DEFAULT_PORT = 8773;
const QUESTION =
  "Show how PSKA proves this is a real browser demo with source recall, memory, trace, and next actions.";

function main() {
  const args = parseArgs(process.argv.slice(2));
  fs.mkdirSync(DIST_DIR, { recursive: true });
  fs.mkdirSync(BUILD_DIR, { recursive: true });

  const playwrightModule = args.playwrightModule || process.env.PSKA_PLAYWRIGHT_MODULE || "playwright";
  let chromium;
  try {
    ({ chromium } = require(playwrightModule));
  } catch (error) {
    console.error(`Cannot load Playwright module '${playwrightModule}'.`);
    console.error("Install it outside the repo, for example:");
    console.error("  mkdir -p /tmp/pska-playwright-recorder");
    console.error("  cd /tmp/pska-playwright-recorder && npm init -y && npm install playwright@1.62.1");
    console.error("  npx playwright install chromium");
    console.error("Then run:");
    console.error("  NODE_PATH=/tmp/pska-playwright-recorder/node_modules node scripts/record_browser_demo_video.cjs");
    throw error;
  }

  return record({ args, chromium }).catch((error) => {
    console.error(error && error.stack ? error.stack : error);
    process.exitCode = 1;
  });
}

async function record({ args, chromium }) {
  const port = Number(args.port || DEFAULT_PORT);
  const baseUrl = args.apiUrl || `http://127.0.0.1:${port}`;
  const startServer = !args.noServer;
  const runtimeDb = path.join(ROOT, ".pska-essential", "browser-recording-demo.sqlite3");
  const runtimeMemoryDb = path.join(ROOT, ".pska-essential", "browser-recording-memory.sqlite3");
  const runtimeSourceDb = path.join(ROOT, ".pska-essential", "browser-recording-sources.sqlite3");
  const logPath = path.join(BUILD_DIR, "product-api.log");
  let server = null;

  if (startServer) {
    removeSqlite(runtimeDb);
    removeSqlite(runtimeMemoryDb);
    removeSqlite(runtimeSourceDb);
    server = spawnProductApi({ port, dbPath: runtimeDb, memoryDbPath: runtimeMemoryDb, sourceDbPath: runtimeSourceDb, logPath });
  }

  try {
    await waitForHealth(baseUrl);
    const seed = await seedDemoData(baseUrl);
    const timeline = [];

    const browser = await chromium.launch({
      headless: !args.headed,
      slowMo: Number(args.slowMo || 0),
    });
    const context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
      recordVideo: {
        dir: BUILD_DIR,
        size: { width: 1280, height: 720 },
      },
    });
    const page = await context.newPage();

    const startedAt = Date.now();
    const scene = async (id, title, caption, fn) => {
      const startsAt = (Date.now() - startedAt) / 1000;
      timeline.push({ id, title, caption, narration: caption, startsAt, endsAt: startsAt });
      await setOverlay(page, title, caption).catch(() => {});
      await fn();
      timeline[timeline.length - 1].endsAt = (Date.now() - startedAt) / 1000;
    };

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await installOverlay(page);
    await page.waitForSelector("#agentic-context-brief", { timeout: 15_000 });
    await page.waitForTimeout(1500);

    await scene(
      "home",
      "打开 PSKA 诊断页",
      "真实浏览器连接本地 Product API，Home 显示知识库、Jarvis briefing、资料源和记忆信号。",
      async () => {
        await moveCursor(page, 1145, 278);
        await page.waitForTimeout(2500);
      },
    );

    await scene(
      "context_brief",
      "点击生成 Agentic Context Brief",
      "PSKA 在回答前组合 KB evidence、本地 source recall、Memory Card、trace 信号和 next actions。",
      async () => {
        await page.locator("#agentic-context-brief").scrollIntoViewIfNeeded();
        await page.waitForTimeout(600);
        const button = page.locator("#agentic-context-brief").getByRole("button", { name: "生成 Brief" }).last();
        await moveToLocator(page, button);
        await clickLocator(page, button);
        await page.waitForFunction(() => {
          const text = document.querySelector("#agentic-context-brief")?.innerText || "";
          return text.includes("Prepared") && text.includes("trace");
        }, { timeout: 20_000 });
        await page.waitForTimeout(2800);
      },
    );

    await scene(
      "ask_prefill",
      "从 Brief 的 next action 进入 Ask",
      "点击 Brief 中的提问动作，Ask 页面自动带入 ready knowledge scope。",
      async () => {
        const askButton = page.locator("#agentic-context-brief").getByRole("button", { name: "提问" }).last();
        await moveToLocator(page, askButton);
        await clickLocator(page, askButton);
        await page.waitForSelector("#ask-form textarea[name='question']", { timeout: 10_000 });
        await page.waitForTimeout(1600);
      },
    );

    await scene(
      "ask_run",
      "填写问题并运行 Ask",
      "问题要求系统在浏览器中证明 source recall、memory、trace 和 next actions 都真的被用上。",
      async () => {
        const questionBox = page.locator("#ask-form textarea[name='question']");
        await moveToLocator(page, questionBox);
        await questionBox.click();
        await page.keyboard.type(QUESTION, { delay: 8 });
        await page.waitForTimeout(500);
        const runButton = page.locator("#ask-form button[type='submit']");
        await moveToLocator(page, runButton);
        await clickLocator(page, runButton);
        await page.waitForFunction(() => {
          const text = document.querySelector("#ask-result")?.innerText || "";
          return text.includes("带来源 Brief") && text.includes("Source Manifest");
        }, { timeout: 25_000 });
        await page.waitForTimeout(1600);
      },
    );

    await scene(
      "sourced_brief",
      "查看带来源 Brief",
      "结果包含 run id、source count、inspected source count、used memory count、Source Manifest 和 Memory Attribution。",
      async () => {
        await page.getByRole("heading", { name: "带来源 Brief" }).scrollIntoViewIfNeeded();
        await moveCursor(page, 600, 650);
        await page.waitForTimeout(3600);
      },
    );

    await scene(
      "loop_trace",
      "查看 Agentic Loop Trace",
      "Loop 展示 scope.check、governance.policy、kb.readiness、retrieval.plan、memory.search 和 source.inspect。",
      async () => {
        await page.getByRole("heading", { name: "Loop" }).scrollIntoViewIfNeeded();
        await moveCursor(page, 1120, 640);
        await page.waitForTimeout(3300);
      },
    );

    await scene(
      "memory",
      "打开 Memory Card 页面",
      "Memory 页面展示最近使用的记忆卡片，并提供为什么用到、时间线、查看等治理入口。",
      async () => {
        await clickNav(page, "memory");
        await page.waitForSelector("#memory-card-summary", { timeout: 10_000 });
        await page.waitForTimeout(2500);
        await moveCursor(page, 1165, 346);
        await page.waitForTimeout(1000);
      },
    );

    await scene(
      "activity",
      "打开 Activity 审计记录",
      "Activity 页面展示刚才 Ask 产生的 agentic_loop.complete，以及 run、ready、context 等审计标签。",
      async () => {
        await clickNav(page, "activity");
        await page.waitForFunction(() => {
          const text = document.querySelector("#audit-list")?.innerText || "";
          return text.includes("agentic_loop.complete") || text.includes("agentic_context.brief.build");
        }, { timeout: 10_000 });
        await moveCursor(page, 985, 153);
        await page.waitForTimeout(2800);
      },
    );

    await scene(
      "sources",
      "打开 Sources 本地资料源",
      "Sources 页面展示 read only、scanned、objects 1 的本地文件夹，并保留扫描、抽取和审计入口。",
      async () => {
        await clickNav(page, "sources");
        await page.waitForSelector("#source-roots-list", { timeout: 10_000 });
        await moveCursor(page, 1084, 423);
        await page.waitForTimeout(2500);
      },
    );

    await scene(
      "source_search",
      "运行无 embedding 搜索",
      "在 Sources 中搜索 browser demo，命中本地 Markdown 文件 pska-demo-note.md，并显示行号和摘要。",
      async () => {
        const searchInput = page.locator("#source-search-form input[name='query']");
        await searchInput.fill("");
        await moveToLocator(page, searchInput);
        await searchInput.click();
        await page.keyboard.type("browser demo", { delay: 20 });
        const searchButton = page.locator("#source-search-form button[type='submit']");
        await moveToLocator(page, searchButton);
        await clickLocator(page, searchButton);
        await page.waitForFunction(() => {
          const text = document.querySelector("#source-search-results")?.innerText || "";
          return text.includes("pska-demo-note.md") || text.includes("PSKA Browser Demo Note");
        }, { timeout: 10_000 });
        await moveCursor(page, 329, 305);
        await page.waitForTimeout(3200);
      },
    );

    await page.waitForTimeout(800);
    const rawVideoPath = await page.video().path();
    await context.close();
    await browser.close();

    const rawOut = path.join(DIST_DIR, "pska_webui_browser_recording_raw.webm");
    const mp4Out = path.join(DIST_DIR, "pska_webui_browser_recording.mp4");
    fs.copyFileSync(rawVideoPath, rawOut);
    convertWebmToMp4(rawOut, mp4Out);

    const srtOut = path.join(DIST_DIR, "pska_webui_browser_recording.zh.srt");
    const storyboardOut = path.join(DIST_DIR, "playwright_storyboard.zh.md");
    const manifestOut = path.join(DIST_DIR, "playwright_recording_manifest.json");
    writeSrt(timeline, srtOut);
    writeStoryboard(timeline, storyboardOut);
    fs.writeFileSync(
      manifestOut,
      JSON.stringify(
        {
          schema: "pska.browser_playwright_recording.v1",
          base_url: baseUrl,
          seed,
          raw_video: path.relative(ROOT, rawOut),
          mp4: path.relative(ROOT, mp4Out),
          subtitles: path.relative(ROOT, srtOut),
          storyboard: path.relative(ROOT, storyboardOut),
          timeline,
        },
        null,
        2,
      ),
      "utf8",
    );

    console.log(`video: ${mp4Out}`);
    console.log(`raw: ${rawOut}`);
    console.log(`subtitles: ${srtOut}`);
    console.log(`storyboard: ${storyboardOut}`);
    console.log(`manifest: ${manifestOut}`);
  } finally {
    if (server) {
      server.kill("SIGINT");
      await new Promise((resolve) => setTimeout(resolve, 500));
      if (!server.killed) server.kill("SIGTERM");
    }
  }
}

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--no-server") args.noServer = true;
    else if (arg === "--headed") args.headed = true;
    else if (arg === "--port") args.port = argv[++index];
    else if (arg === "--api-url") args.apiUrl = argv[++index];
    else if (arg === "--slow-mo") args.slowMo = argv[++index];
    else if (arg === "--playwright-module") args.playwrightModule = argv[++index];
  }
  return args;
}

function removeSqlite(dbPath) {
  for (const candidate of [dbPath, `${dbPath}-wal`, `${dbPath}-shm`]) {
    fs.rmSync(candidate, { force: true });
  }
}

function spawnProductApi({ port, dbPath, memoryDbPath, sourceDbPath, logPath }) {
  const log = fs.createWriteStream(logPath, { flags: "w" });
  const env = {
    ...process.env,
    PYTHONPATH: "src",
    PSKA_DEV_FAKE: "1",
    PSKA_WORKSPACE_ID: "pska_webui_demo",
    PSKA_RETRIEVAL_PROVIDER: "fake",
    PSKA_KB_PROVIDER: "fake",
    PSKA_MEMORY_PROVIDER: "sqlite",
    PSKA_MEMORY_DB: memoryDbPath,
    PSKA_REVIEW_DB: dbPath,
    PSKA_SOURCE_DB: sourceDbPath,
    PSKA_API_PORT: String(port),
  };
  const child = spawn("python3", ["-m", "pska_essential.product_api"], {
    cwd: ROOT,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.pipe(log);
  child.stderr.pipe(log);
  child.on("exit", (code, signal) => {
    if (code && code !== 0) {
      console.error(`Product API exited with code ${code} signal ${signal || ""}. See ${logPath}`);
    }
  });
  return child;
}

async function waitForHealth(baseUrl) {
  const deadline = Date.now() + 30_000;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/api/health`);
      if (response.ok) return;
      lastError = new Error(`health ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(500);
  }
  throw lastError || new Error("Product API did not become healthy.");
}

async function seedDemoData(baseUrl) {
  const ingest = await api(baseUrl, "/api/kb/ingest", {
    file_paths: [NOTE_PATH],
    dataset_name: "PSKA Browser Recording Demo",
    description: "Playwright browser recording demo dataset.",
    wait: true,
  });
  const datasetId = findValue(ingest, "dataset_id") || "";
  const documentId = findValue(ingest, "document_id") || "";

  const rootPayload = await api(baseUrl, "/api/sources/roots", {
    path: SOURCE_DIR,
    kind: "local_folder",
    permission_mode: "read_only",
    label: "PSKA Browser Recording Source",
  });
  const rootId = rootPayload.root && rootPayload.root.root_id;
  if (rootId) {
    await api(baseUrl, `/api/sources/roots/${encodeURIComponent(rootId)}/scan`, { max_files: 1000 });
    await api(baseUrl, "/api/sources/audits/run", { scope: { root_ids: [rootId] }, limit: 20 }).catch(() => null);
  }

  const memory = await api(baseUrl, "/api/memory/conversation-change", {
    user_message:
      "For PSKA browser recordings, remember to show Agentic Context Brief before Ask so the demo has source recall, memory, trace, and next actions.",
    operation: "auto",
    text:
      "For PSKA browser recordings, show Agentic Context Brief before Ask so source recall, memory, trace, and next actions are visible.",
    session_id: "pska_browser_recording_demo",
    message_id: `msg_${Date.now()}`,
    reason: "Seed browser recording demo memory.",
    source_refs: [],
    scope: { workspace_id: "pska_webui_demo" },
    force_review: false,
    confidence: 0.99,
  });

  return {
    dataset_id: datasetId,
    document_id: documentId,
    root_id: rootId || "",
    memory_id: findValue(memory, "target_id") || findValue(memory, "memory_id") || findValue(memory, "fact_id") || "",
  };
}

async function api(baseUrl, apiPath, body) {
  const response = await fetch(`${baseUrl}${apiPath}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(`${apiPath} failed: ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

function findValue(value, key) {
  if (!value || typeof value !== "object") return "";
  if (Object.prototype.hasOwnProperty.call(value, key) && value[key]) return String(value[key]);
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findValue(item, key);
      if (found) return found;
    }
    return "";
  }
  for (const item of Object.values(value)) {
    const found = findValue(item, key);
    if (found) return found;
  }
  return "";
}

async function installOverlay(page) {
  await page.addStyleTag({
    content: `
      body { cursor: none !important; }
      #pska-demo-cursor, #pska-demo-overlay, .pska-demo-ripple {
        pointer-events: none !important;
      }
      #pska-demo-overlay {
        position: fixed;
        left: 248px;
        right: 0;
        top: 0;
        z-index: 999999;
        color: #f6faf8;
        font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      }
      #pska-demo-overlay .top {
        background: rgba(13, 30, 26, 0.92);
        border-bottom: 1px solid rgba(83, 177, 163, 0.45);
        padding: 14px 28px 12px;
      }
      #pska-demo-overlay .title {
        font-size: 25px;
        font-weight: 750;
        line-height: 1.15;
      }
      #pska-demo-overlay .caption {
        position: fixed;
        left: 278px;
        right: 28px;
        bottom: 22px;
        background: rgba(13, 30, 26, 0.92);
        border: 1px solid rgba(83, 177, 163, 0.65);
        border-radius: 12px;
        padding: 12px 16px;
        color: #f6faf8;
        font-size: 20px;
        line-height: 1.38;
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.18);
      }
      #pska-demo-cursor {
        position: fixed;
        left: 0;
        top: 0;
        z-index: 1000000;
        width: 34px;
        height: 46px;
        transform: translate3d(1040px, 300px, 0);
        filter: drop-shadow(0 2px 2px rgba(0, 0, 0, 0.45));
      }
      .pska-demo-ripple {
        position: fixed;
        z-index: 999998;
        width: 14px;
        height: 14px;
        margin-left: -7px;
        margin-top: -7px;
        border-radius: 999px;
        border: 4px solid rgba(35, 125, 116, 0.75);
        animation: pska-demo-ripple 620ms ease-out forwards;
      }
      @keyframes pska-demo-ripple {
        from { transform: scale(1); opacity: 0.9; }
        to { transform: scale(7); opacity: 0; }
      }
    `,
  });
  await page.evaluate(() => {
    const overlay = document.createElement("div");
    overlay.id = "pska-demo-overlay";
    overlay.innerHTML = '<div class="top"><div class="title"></div></div><div class="caption"></div>';
    document.body.appendChild(overlay);
    const cursor = document.createElement("div");
    cursor.id = "pska-demo-cursor";
    cursor.innerHTML = `
      <svg width="34" height="46" viewBox="0 0 34 46" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M3 3L3 34L13 25L20 43L28 39L20 22L32 22L3 3Z" fill="white" stroke="#10201c" stroke-width="2"/>
      </svg>`;
    document.body.appendChild(cursor);
    window.__pskaDemoSetOverlay = (title, caption) => {
      document.querySelector("#pska-demo-overlay .title").textContent = title || "";
      document.querySelector("#pska-demo-overlay .caption").textContent = caption || "";
    };
    window.__pskaDemoMoveCursor = (x, y) => {
      document.getElementById("pska-demo-cursor").style.transform = `translate3d(${x}px, ${y}px, 0)`;
    };
    window.__pskaDemoClickRipple = (x, y) => {
      const ripple = document.createElement("div");
      ripple.className = "pska-demo-ripple";
      ripple.style.left = `${x}px`;
      ripple.style.top = `${y}px`;
      document.body.appendChild(ripple);
      setTimeout(() => ripple.remove(), 700);
    };
  });
}

async function setOverlay(page, title, caption) {
  await page.evaluate(
    ({ title: nextTitle, caption: nextCaption }) => window.__pskaDemoSetOverlay?.(nextTitle, nextCaption),
    { title, caption },
  );
}

async function moveCursor(page, x, y) {
  await page.mouse.move(x, y, { steps: 18 });
  await page.evaluate(({ x: nextX, y: nextY }) => window.__pskaDemoMoveCursor?.(nextX, nextY), { x, y });
}

async function moveToLocator(page, locator) {
  const box = await locator.boundingBox();
  if (!box) return;
  await moveCursor(page, Math.round(box.x + box.width / 2), Math.round(box.y + box.height / 2));
}

async function clickLocator(page, locator) {
  const box = await locator.boundingBox();
  if (box) {
    const x = Math.round(box.x + box.width / 2);
    const y = Math.round(box.y + box.height / 2);
    await page.evaluate(({ x: nextX, y: nextY }) => window.__pskaDemoClickRipple?.(nextX, nextY), { x, y });
  }
  await locator.click();
}

async function clickNav(page, view) {
  const nav = page.locator(`.nav-item[data-view="${view}"]`);
  await moveToLocator(page, nav);
  await clickLocator(page, nav);
  await page.waitForFunction((nextView) => document.querySelector(`#${nextView}`)?.classList.contains("active"), view, {
    timeout: 10_000,
  });
  await page.waitForTimeout(500);
}

function convertWebmToMp4(input, output) {
  const result = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-hide_banner",
      "-loglevel",
      "error",
      "-i",
      input,
      "-vf",
      "format=yuv420p",
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "22",
      "-movflags",
      "+faststart",
      output,
    ],
    { stdio: "inherit" },
  );
  if (result.status !== 0) {
    throw new Error(`ffmpeg failed with status ${result.status}`);
  }
}

function writeSrt(timeline, output) {
  const blocks = timeline.map((item, index) => {
    const text = subtitleLines(item.caption, 42).join("\n");
    return `${index + 1}\n${srtTime(item.startsAt)} --> ${srtTime(item.endsAt)}\n${text}\n`;
  });
  fs.writeFileSync(output, blocks.join("\n"), "utf8");
}

function writeStoryboard(timeline, output) {
  const lines = ["# PSKA Diagnostic Page Playwright Recording Storyboard", ""];
  for (const [index, item] of timeline.entries()) {
    lines.push(`## ${String(index + 1).padStart(2, "0")}. ${item.title}`);
    lines.push("");
    lines.push(`Time: \`${srtTime(item.startsAt).replace(",", ".")}\` - \`${srtTime(item.endsAt).replace(",", ".")}\``);
    lines.push("");
    lines.push(item.caption);
    lines.push("");
  }
  fs.writeFileSync(output, lines.join("\n"), "utf8");
}

function subtitleLines(text, maxUnits) {
  const lines = [];
  let current = "";
  let width = 0;
  for (const token of subtitleTokens(text)) {
    if (/^\s+$/.test(token)) {
      if (current && !current.endsWith(" ")) {
        current += " ";
        width += 1;
      }
      continue;
    }
    const tokenWidth = displayWidth(token);
    if (current && width + tokenWidth > maxUnits) {
      lines.push(current.trimEnd());
      current = "";
      width = 0;
    }
    current += token;
    width += tokenWidth;
  }
  if (current) lines.push(current.trimEnd());
  return lines;
}

function subtitleTokens(text) {
  const tokens = [];
  let ascii = "";
  for (const char of text) {
    if (/\s/.test(char)) {
      if (ascii) {
        tokens.push(ascii);
        ascii = "";
      }
      tokens.push(" ");
    } else if (/^[A-Za-z0-9_.-]$/.test(char)) {
      ascii += char;
    } else {
      if (ascii) {
        tokens.push(ascii);
        ascii = "";
      }
      tokens.push(char);
    }
  }
  if (ascii) tokens.push(ascii);
  return tokens;
}

function displayWidth(text) {
  let width = 0;
  for (const char of text) width += char.charCodeAt(0) < 128 ? 1 : 2;
  return width;
}

function srtTime(seconds) {
  const millis = Math.max(0, Math.round(seconds * 1000));
  const hours = Math.floor(millis / 3_600_000);
  const minutes = Math.floor((millis % 3_600_000) / 60_000);
  const secs = Math.floor((millis % 60_000) / 1000);
  const ms = millis % 1000;
  return `${pad(hours)}:${pad(minutes)}:${pad(secs)},${String(ms).padStart(3, "0")}`;
}

function pad(value) {
  return String(value).padStart(2, "0");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main();
