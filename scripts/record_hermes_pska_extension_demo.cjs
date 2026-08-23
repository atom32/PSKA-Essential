#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..");
const DEMO_DIR = path.join(ROOT, "demo", "browser", "hermes_pska_extension_demo");
const DIST_DIR = path.join(DEMO_DIR, "dist");
const BUILD_DIR = path.join(DIST_DIR, "playwright-build");
const DEFAULT_BASE_URL = "http://127.0.0.1:8787";
const DEFAULT_PSKA_API_BASE_URL = "http://127.0.0.1:8765";
const DEFAULT_EIDOLIA_BASE_URL = "http://127.0.0.1:8797";
const DEMO_SOURCE_DIR = path.join(DEMO_DIR, "source_root");
const QUESTION =
  "请使用当前资料范围回答：为什么个人知识助手不单独做一个新页面，而是放在对话工作台里？请引用资料找回、记忆、记录和下一步动作。";
const SOURCE_RECALL_QUERY =
  "对话工作台 个人知识助手 胶水层 资料找回 记忆 记录 创作画布 系统架构";
const DEFAULT_CASE_ID = "core";
const DEMO_CASES = {
  core: {
    id: "core",
    title: "个人知识助手核心架构",
    outputBasename: "hermes_pska_extension_demo",
    sourceDir: DEMO_SOURCE_DIR,
    sourceLabel: "个人知识助手演示资料",
    question: QUESTION,
    sourceRecallQuery: SOURCE_RECALL_QUERY,
    captions: {},
  },
  finance_report_research: {
    id: "finance_report_research",
    title: "财报调研与经营管理",
    outputBasename: "hermes_pska_finance_case_demo",
    sourceDir: path.join(DEMO_DIR, "cases", "finance_report_research", "source_root"),
    sourceLabel: "财报调研演示资料",
    question:
      "请使用当前资料范围回答：北星机器人二〇二六年第二季度财报调研中，业绩变化的核心原因、经营风险和管理层下一步动作是什么？请区分事实、推断和建议，并指出哪些内容应进入待确认记忆。",
    sourceRecallQuery:
      "北星机器人 二〇二六年 第二季度 收入 毛利率 经营现金流 库存 回款天数 未交付订单 服务毛利 财务负责人 营运资金",
    eidolia: {
      projectName: "知识助手与创作画布：财报报告演示",
      projectDescription: "基于资料找回，把北星机器人第二季度财报材料沉淀为想法、来源和报告草稿。",
      draftNodeId: "draft-finance-report",
      focusNodeIds: [
        "thought-finance-report",
        "artifact-finance-evidence",
        "draft-finance-report",
        "artifact-finance-memory-review",
      ],
    },
    captions: {
      webui_entry: "从对话工作台进入，演示对象是金融分析师和经营管理者的财报调研流程。",
      extension_status:
        "知识助手只读取你允许的资料；财报文件夹先登记，再按本轮需要查找。",
      scope_selection: "本轮只查看北星机器人第二季度材料，不扫全盘文件夹。",
      jarvis_brief: "开始前总览会列出可用资料、待确认记忆和下一步调研动作。",
      agentic_brief: "回答前整理会把财报事实、风险问题、经营动作和待确认记忆放在一起。",
      source_recall:
        "资料找回命中收入、毛利、回款天数、库存、未交付订单和管理层问题。",
      chat_injection: "对话助手根据本轮资料范围，输出事实、推断、建议和待确认记忆。",
      memory_review:
        "记忆页只展示候选内容，必须由用户确认后才会成为长期记忆。",
      projection_tasks: "审核结果和整理任务可以同步到任务列表，方便后续跟进。",
      eidolia_bridge:
        "创作画布接住财报证据：先整理问题，再保存来源，最后形成经营报告草稿。",
    },
  },
  webnovel_author: {
    id: "webnovel_author",
    title: "网文作者创作流程",
    outputBasename: "hermes_pska_webnovel_case_demo",
    sourceDir: path.join(DEMO_DIR, "cases", "webnovel_author", "source_root"),
    sourceLabel: "网文续写演示资料",
    question:
      "请使用当前资料范围回答：《云涯纪》第十八章续写有哪些设定冲突、读者反馈影响和记忆候选？请引用设定资料、章节问题、读者反馈或创作画布记录。",
    sourceRecallQuery:
      "云涯纪 第18章 星图 铜针 岑青砚 不能直接说谎 陆怀砂 读者反馈 具体问题",
    eidolia: {
      projectName: "知识助手与创作画布：网文续写演示",
      projectDescription: "基于资料找回，把《云涯纪》设定资料、读者反馈和章节问题沉淀为续写草稿。",
      draftNodeId: "draft-webnovel-continuation",
      focusNodeIds: [
        "thought-webnovel-continuation",
        "artifact-webnovel-story-bible",
        "artifact-webnovel-reader-feedback",
        "draft-webnovel-continuation",
      ],
    },
    captions: {
      webui_entry: "从对话工作台进入，演示对象是网文作者、写手和编辑的长篇创作流程。",
      extension_status:
        "知识助手不另开复杂页面，创作材料来自设定资料、章节草稿、读者反馈和画布记录。",
      scope_selection: "本轮只查看《云涯纪》的资料文件夹，帮助续写前恢复设定和风格约束。",
      jarvis_brief: "开始前总览会汇总创作材料、待确认记忆和下一章动作。",
      agentic_brief: "回答前整理会把设定资料、章节冲突、读者反馈和画布记录放在一起。",
      source_recall: "资料找回命中星图、铜针、岑青砚约束、陆怀砂功能和章末问题。",
      chat_injection: "对话助手给出设定冲突、续写方向和待确认记忆。",
      memory_review: "记忆页展示作者风格和世界观约束，防止模型悄悄改设定。",
      projection_tasks: "审核结果和整理任务同步到任务列表，支持后续章节复盘。",
      eidolia_bridge:
        "创作画布只分想法和产物两类：设定与反馈进画布，续写草稿成为可审阅产物。",
    },
  },
};

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
    console.error("Install Playwright outside the repo, then set NODE_PATH or --playwright-module.");
    console.error("Example:");
    console.error("  mkdir -p /tmp/pska-playwright-recorder");
    console.error("  cd /tmp/pska-playwright-recorder && npm init -y && npm install playwright");
    console.error("  npx playwright install chromium");
    throw error;
  }

  return record({ args, chromium }).catch((error) => {
    console.error(error && error.stack ? error.stack : error);
    process.exitCode = 1;
  });
}

async function record({ args, chromium }) {
  const demoCase = resolveDemoCase(args);
  const baseUrl = String(args.baseUrl || process.env.HERMES_WEBUI_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/g, "");
  const outBase = args.outputBasename || demoCase.outputBasename || "hermes_pska_extension_demo";
  const storageState = args.storageState || process.env.HERMES_WEBUI_STORAGE_STATE || "";
  const password = args.password || process.env.HERMES_WEBUI_PASSWORD || "";
  const detailed = Boolean(args.detailed || process.env.HERMES_DEMO_PROFILE === "detailed");
  const dwellScale = Number(args.dwellScale || process.env.HERMES_DEMO_DWELL_SCALE || (detailed ? 4 : 1));
  const waitForLlmMs = Number(args.waitForLlmMs || process.env.HERMES_DEMO_WAIT_FOR_LLM_MS || (detailed ? 75_000 : 45_000));
  const tailPadMs = Number(args.tailPadMs || process.env.HERMES_DEMO_TAIL_PAD_MS || 0);
  const pskaApiBaseUrl = String(
    args.pskaApiBaseUrl || process.env.PSKA_PRODUCT_API_BASE_URL || DEFAULT_PSKA_API_BASE_URL,
  ).replace(/\/+$/g, "");
  const eidoliaBaseUrl = String(
    args.eidoliaBaseUrl || process.env.EIDOLIA_BASE_URL || DEFAULT_EIDOLIA_BASE_URL,
  ).replace(/\/+$/g, "");
  const shouldSeedDemoData = !args.noSeedDemoData && process.env.HERMES_DEMO_SEED_DATA !== "0";
  const shouldSeedEidoliaData =
    Boolean(demoCase.eidolia) && !args.noSeedEidoliaData && process.env.HERMES_DEMO_SEED_EIDOLIA !== "0";
  const sceneCaption = (id, fallback) => (demoCase.captions && demoCase.captions[id]) || fallback;

  await checkWebuiReachable(baseUrl);
  const demoSeed = shouldSeedDemoData ? await seedHermesDemoData({ pskaApiBaseUrl, demoCase }) : null;
  const eidoliaSeed = shouldSeedEidoliaData
    ? await seedEidoliaDemoProject({ eidoliaBaseUrl, pskaApiBaseUrl, demoCase, demoSeed })
    : null;

  const browser = await chromium.launch({
    headless: !args.headed,
    slowMo: Number(args.slowMo || 0),
  });
  const contextOptions = {
    viewport: { width: 1280, height: 720 },
    recordVideo: {
      dir: BUILD_DIR,
      size: { width: 1280, height: 720 },
    },
  };
  if (storageState) contextOptions.storageState = path.resolve(storageState);

  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();
  const timeline = [];
  const startedAt = Date.now();

  const scene = async (id, title, caption, fn) => {
    const startsAt = (Date.now() - startedAt) / 1000;
    timeline.push({ id, title, caption, narration: caption, startsAt, endsAt: startsAt });
    await setOverlay(page, title, caption).catch(() => {});
    await fn();
    timeline[timeline.length - 1].endsAt = (Date.now() - startedAt) / 1000;
  };
  const pause = (ms) => page.waitForTimeout(Math.max(0, Math.round(ms * dwellScale)));

  try {
    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await loginIfNeeded(page, { password, baseUrl });
    await waitForHermesShell(page);
    await installOverlay(page);
    await applyDemoSourceScope(page, demoSeed);

    await scene(
      "webui_entry",
      "对话工作台是主入口",
      sceneCaption(
        "webui_entry",
        "演示从对话工作台开始：聊天、工具、设置和知识助手都在同一个地方。",
      ),
      async () => {
        await page.waitForSelector("#msg", { timeout: 20_000 });
        await page.waitForSelector("#pskaMiniChip", { timeout: 20_000 });
        await moveCursor(page, 994, 618);
        await pause(1800);
      },
    );

    await scene(
      "extension_status",
      "知识助手已连接",
      sceneCaption(
        "extension_status",
        "旁边的小按钮只是入口，真正的资料读取和记忆管理都由知识助手统一处理。",
      ),
      async () => {
        await openPskaMenu(page);
        await clickById(page, "pskaMiniRefresh");
        await waitForPskaStatusReady(page, 45_000);
        await moveCursor(page, 189, 423);
        await pause(2200);
      },
    );

    await scene(
      "scope_selection",
      "选择本轮资料范围",
      sceneCaption(
        "scope_selection",
        "用户先选择这一次要看的资料范围，下一次回答就只围绕这些资料展开。",
      ),
      async () => {
        await prepareScope(page);
        await pause(1800);
      },
    );

    await scene(
      "jarvis_brief",
      "开始前总览",
      sceneCaption(
        "jarvis_brief",
        "开始前总览会把可用资料、待确认记忆和下一步动作整理到一起。",
      ),
      async () => {
        await clickById(page, "pskaMiniJarvisBrief");
        await waitForPreviewAny(page, ["开始前总览", "工作区", "待确认", "下一步", "Jarvis Brief", "失败"], 30_000);
        await revealPreview(page);
        await moveCursor(page, 359, 530);
        await pause(2600);
      },
    );

    await scene(
      "agentic_brief",
      "回答前整理",
      sceneCaption(
        "agentic_brief",
        "回答前整理会把相关资料、已有记忆、操作记录和下一步建议放到同一处。",
      ),
      async () => {
        await setComposerQuestion(page, demoCase.question);
        await openPskaMenu(page);
        await clickById(page, "pskaMiniAgenticBrief");
        await waitForPreviewAny(page, ["回答前整理", "资料", "记忆", "记录", "Agentic Brief", "失败"], 35_000);
        await revealPreview(page);
        await moveCursor(page, 363, 530);
        await pause(3200);
      },
    );

    await scene(
      "source_recall",
      "按文件信息找资料",
      sceneCaption(
        "source_recall",
        "资料找回会查文件名、标题、路径和摘要，适合管理个人文件夹里的材料。",
      ),
      async () => {
        await setComposerQuestion(page, demoCase.sourceRecallQuery);
        await openPskaMenu(page);
        await clickById(page, "pskaMiniSourceRecall");
        await waitForPreviewAny(page, ["资料找回", "命中", "结果", "Source Recall", "失败"], 25_000);
        await revealPreview(page);
        await moveCursor(page, 383, 530);
        await pause(2600);
      },
    );

    await scene(
      "chat_injection",
      "发起一次正式回答",
      sceneCaption(
        "chat_injection",
        "这一步仍然在对话里完成，不跳到另一个产品页面；助手会带着本轮资料范围回答。",
      ),
      async () => {
        await setComposerQuestion(page, demoCase.question);
        await ensurePskaEnabled(page);
        await closePskaMenu(page);
        const sendButton = page.locator("#btnSend");
        await moveToLocator(page, sendButton);
        await clickLocator(page, sendButton);
        await page.waitForFunction(
          (needle) => document.body.innerText.includes(needle.slice(0, 24)),
          demoCase.question,
          { timeout: 15_000 },
        );
        if (waitForLlmMs > 0) {
          await waitForHermesTurnCompletion({ page, baseUrl, timeoutMs: waitForLlmMs });
        } else {
          await pause(3000);
        }
      },
    );

    await scene(
      "memory_review",
      "待确认记忆",
      sceneCaption(
        "memory_review",
        "记忆页展示可搜索的记忆和候选内容，长期记忆需要用户确认后才会写入。",
      ),
      async () => {
        await openPskaMenu(page);
        await clickById(page, "pskaMiniOpenMemoryPage");
        await page.waitForSelector("#mainPskaMini", { timeout: 15_000 });
        await pause(2800);
      },
    );

    await scene(
      "projection_tasks",
      "同步到任务列表",
      sceneCaption(
        "projection_tasks",
        "审核结果和整理任务可以同步到任务列表，方便之后继续处理。",
      ),
      async () => {
        await returnToChatShell(page);
        await openPskaMenu(page);
        await clickById(page, "pskaMiniSyncReviews");
        await waitForPreviewAny(page, ["PSKA Review", "审核", "同步", "失败"], 25_000);
        await revealPreview(page);
        await pause(1800);
        await clickById(page, "pskaMiniCreateDigestTask");
        await waitForPreviewAny(page, ["摘要任务", "Hermes 任务", "Tasks", "失败"], 25_000);
        await revealPreview(page);
        await pause(2400);
      },
    );

    await scene(
      "eidolia_bridge",
      "创作画布生成草稿",
      sceneCaption(
        "eidolia_bridge",
        "创作画布把资料、想法和草稿连在一起；知识助手继续负责来源和记忆确认。",
      ),
      async () => {
        await closePskaMenu(page);
        const eidolia = page.locator("#eidoliaRailButton");
        if (await eidolia.count()) {
          await moveToLocator(page, eidolia);
          await clickLocator(page, eidolia);
          await page.waitForSelector("#eidoliaFrame", { timeout: 15_000 });
          await moveCursor(page, 1150, 120);
          if (eidoliaSeed) {
            const frame = await getEidoliaContentFrame(page);
            await waitForEidoliaCanvas(frame, eidoliaSeed);
            await fitEidoliaNodes(frame, eidoliaSeed.focus_node_ids, 180, 1100);
            await highlightEidoliaNode(frame, eidoliaSeed.draft_node_id);
            await pause(2600);
            await openEidoliaNode(frame, eidoliaSeed.draft_node_id);
            await pause(3200);
            await scrollEidoliaOverlay(frame, 620);
            await pause(2200);
          } else {
            await pause(3600);
          }
        } else {
          await setOverlay(
            page,
            "创作画布未加载",
            "当前没有找到创作画布入口；录制仍保留知识助手主线。",
          );
          await pause(2600);
        }
      },
    );

    if (tailPadMs > 0) {
      await page.waitForTimeout(tailPadMs);
      if (timeline.length) {
        timeline[timeline.length - 1].endsAt += tailPadMs / 1000;
      }
    }

    const rawVideoPath = await page.video().path();
    await context.close();
    await browser.close();

    const rawOut = path.join(DIST_DIR, `${outBase}_raw.webm`);
    const mp4Out = path.join(DIST_DIR, `${outBase}.mp4`);
    const srtOut = path.join(DIST_DIR, `${outBase}.zh.srt`);
    const storyboardOut = path.join(DIST_DIR, `${outBase}_storyboard.zh.md`);
    const manifestOut = path.join(DIST_DIR, `${outBase}_manifest.json`);

    convertWebmToMp4(rawVideoPath, mp4Out);
    if (args.keepRaw) {
      fs.copyFileSync(rawVideoPath, rawOut);
    } else {
      fs.unlinkSync(rawVideoPath);
    }
    writeSrt(timeline, srtOut);
    writeStoryboard(timeline, storyboardOut);
    fs.writeFileSync(
      manifestOut,
      JSON.stringify(
        {
          schema: "pska.hermes_extension_playwright_recording.v1",
          demo_case: {
            id: demoCase.id,
            title: demoCase.title,
            source_root: demoCase.sourceDir,
          },
          base_url: baseUrl,
          mp4: path.relative(ROOT, mp4Out),
          subtitles: path.relative(ROOT, srtOut),
          storyboard: path.relative(ROOT, storyboardOut),
          timeline,
          llm_wait_ms: waitForLlmMs,
          tail_pad_ms: tailPadMs,
          demo_profile: detailed ? "detailed" : "standard",
          dwell_scale: dwellScale,
          no_tts: true,
          keep_raw: Boolean(args.keepRaw),
          entrypoint: "Hermes WebUI extension",
          seeded_source_root: demoSeed,
          seeded_eidolia_project: eidoliaSeed,
        },
        null,
        2,
      ) + "\n",
      "utf8",
    );

    console.log(`video: ${mp4Out}`);
    console.log(`subtitles: ${srtOut}`);
    console.log(`storyboard: ${storyboardOut}`);
    console.log(`manifest: ${manifestOut}`);
  } catch (error) {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
    throw error;
  }
}

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--base-url") args.baseUrl = argv[++index];
    else if (arg === "--headed") args.headed = true;
    else if (arg === "--slow-mo") args.slowMo = argv[++index];
    else if (arg === "--playwright-module") args.playwrightModule = argv[++index];
    else if (arg === "--storage-state") args.storageState = argv[++index];
    else if (arg === "--password") args.password = argv[++index];
    else if (arg === "--case") args.caseId = argv[++index];
    else if (arg === "--wait-for-llm-ms") args.waitForLlmMs = argv[++index];
    else if (arg === "--tail-pad-ms") args.tailPadMs = argv[++index];
    else if (arg === "--output-basename") args.outputBasename = argv[++index];
    else if (arg === "--pska-api-base-url") args.pskaApiBaseUrl = argv[++index];
    else if (arg === "--eidolia-base-url") args.eidoliaBaseUrl = argv[++index];
    else if (arg === "--detailed") args.detailed = true;
    else if (arg === "--dwell-scale") args.dwellScale = argv[++index];
    else if (arg === "--keep-raw") args.keepRaw = true;
    else if (arg === "--no-seed-demo-data") args.noSeedDemoData = true;
    else if (arg === "--no-seed-eidolia-data") args.noSeedEidoliaData = true;
  }
  return args;
}

function resolveDemoCase(args) {
  const caseId = String(args.caseId || process.env.HERMES_DEMO_CASE || DEFAULT_CASE_ID).trim();
  const demoCase = DEMO_CASES[caseId];
  if (!demoCase) {
    throw new Error(`Unknown demo case '${caseId}'. Available cases: ${Object.keys(DEMO_CASES).join(", ")}`);
  }
  return demoCase;
}

async function seedHermesDemoData({ pskaApiBaseUrl, demoCase }) {
  if (!fs.existsSync(demoCase.sourceDir)) {
    throw new Error(`Demo source fixture does not exist: ${demoCase.sourceDir}`);
  }
  await fetchJson(`${pskaApiBaseUrl}/api/health`).catch((error) => {
    throw new Error(`PSKA Product API health check failed at ${pskaApiBaseUrl}/api/health: ${error.message || error}`);
  });
  const registered = await postJson(`${pskaApiBaseUrl}/api/sources/roots`, {
    path: demoCase.sourceDir,
    kind: "local_folder",
    permission_mode: "read_only",
    label: demoCase.sourceLabel,
  });
  const rootId = registered.root && registered.root.root_id;
  if (!rootId) throw new Error("PSKA Product API did not return a source root id for demo fixture.");
  const scanned = await postJson(`${pskaApiBaseUrl}/api/sources/roots/${encodeURIComponent(rootId)}/scan`, {
    max_files: 30,
    max_bytes: 300_000,
    extractor: "auto",
  });
  const recalled = await postJson(`${pskaApiBaseUrl}/api/sources/search`, {
    query: demoCase.sourceRecallQuery,
    scope: { root_ids: [rootId] },
    limit: 5,
  });
  const count = Number(recalled.count || 0);
  if (count < 1) {
    throw new Error("Demo fixture was scanned, but Source Recall returned no hits.");
  }
  console.log(
    `seeded demo source root: ${rootId}; case=${demoCase.id}; indexed=${scanned.scan?.counts?.indexed || 0}; recall_hits=${count}`,
  );
  return {
    root_id: rootId,
    label: registered.root.label,
    path: demoCase.sourceDir,
    case_id: demoCase.id,
    recall_hits: count,
  };
}

async function seedEidoliaDemoProject({ eidoliaBaseUrl, pskaApiBaseUrl, demoCase, demoSeed }) {
  await fetchJson(`${eidoliaBaseUrl}/api/agent/health`).catch((error) => {
    throw new Error(`Eidolia health check failed at ${eidoliaBaseUrl}/api/agent/health: ${error.message || error}`);
  });
  const sourcePackets = demoSeed?.root_id
    ? normalizeRecallPackets(
        await postJson(`${pskaApiBaseUrl}/api/sources/search`, {
          query: demoCase.sourceRecallQuery,
          scope: { root_ids: [demoSeed.root_id] },
          limit: 6,
        }).catch(() => ({})),
      )
    : [];
  const projectId = `pska-${demoCase.id.replace(/_/g, "-")}-eidolia-${Date.now().toString(36)}`;
  const created = await postJson(`${eidoliaBaseUrl}/api/projects`, {
    id: projectId,
    name: demoCase.eidolia.projectName,
    description: demoCase.eidolia.projectDescription,
    templateId: "blank",
    smartStarter: false,
    main: `# ${demoCase.eidolia.projectName}\n\n本项目用于展示：资料先由知识助手找回，再交给创作画布沉淀为想法、来源和草稿。\n`,
    background: `# 来源\n\n资料文件夹编号：${demoSeed?.root_id || "未指定"}\n\n${demoCase.sourceLabel}\n`,
    notes: "# 约束\n\n创作画布不替代记忆管理；长期记忆仍需要用户确认。\n",
  });
  const actualProjectId = String(created.project?.id || projectId);
  const workspace = buildEidoliaDemoWorkspace({
    demoCase,
    projectId: actualProjectId,
    demoSeed,
    sourcePackets,
  });
  await putJson(`${eidoliaBaseUrl}/api/workspace?project=${encodeURIComponent(actualProjectId)}`, workspace);
  console.log(
    `seeded Eidolia project: ${actualProjectId}; case=${demoCase.id}; source_packets=${sourcePackets.length}; draft=${demoCase.eidolia.draftNodeId}`,
  );
  return {
    project_id: actualProjectId,
    name: demoCase.eidolia.projectName,
    url: `${eidoliaBaseUrl}/?project=${encodeURIComponent(actualProjectId)}`,
    draft_node_id: demoCase.eidolia.draftNodeId,
    focus_node_ids: demoCase.eidolia.focusNodeIds,
    source_packets: sourcePackets.length,
  };
}

function buildEidoliaDemoWorkspace({ demoCase, projectId, demoSeed, sourcePackets }) {
  if (demoCase.id === "finance_report_research") {
    return buildFinanceEidoliaWorkspace({ projectId, demoSeed, sourcePackets });
  }
  if (demoCase.id === "webnovel_author") {
    return buildWebnovelEidoliaWorkspace({ projectId, demoSeed, sourcePackets });
  }
  throw new Error(`Demo case '${demoCase.id}' has no Eidolia workspace builder.`);
}

function buildFinanceEidoliaWorkspace({ projectId, demoSeed, sourcePackets }) {
  const recallList = sourcePacketsAsMarkdown(sourcePackets);
  const nodes = [
    noteNode("artifact-finance-overview", -520, -330, {
      subtype: "demo_overview",
      title: "Workflow: 财报材料到经营报告",
      category: "工作流说明",
      source: "pska_demo_recorder",
      content: [
        "# 知识助手到创作画布：财报报告链",
        "",
        "目标：基于授权资料文件夹里的财报材料，把北星机器人二〇二六年第二季度材料组织成一份管理层经营简报草稿。",
        "",
        "链路：",
        "",
        "想法：明确问题和报告口径",
        "产物：保存找回的资料和来源",
        "草稿：输出可审阅的经营报告草稿",
        "",
        `资料文件夹编号：${demoSeed?.root_id || "未指定"}`,
      ].join("\n"),
    }),
    thoughtNode("thought-finance-report", -140, -240, {
      subtype: "question",
      title: "把第二季度财报调研转成管理层经营简报",
      content: [
        "我要把北星机器人二〇二六年第二季度的材料转成一份给管理层看的简报。",
        "",
        "关键问题：收入增长是否健康？毛利和服务收入为什么下滑？现金流压力来自哪里？哪些判断需要进入待确认记忆，而不是直接变成长记忆？",
      ].join("\n"),
    }),
    noteNode("artifact-finance-evidence", 330, -270, {
      subtype: "evidence",
      title: "资料找回：第二季度财报证据包",
      category: "资料证据",
      source: "pska_source_recall",
      sourceRefs: sourcePackets,
      content: [
        "# 资料找回命中",
        "",
        recallList || "- 本次没有拿到资料找回结果；下方仍展示演示资料中的关键事实。",
        "",
        "# 抽取事实",
        "",
        "- 收入十八点四亿美元，同比增长百分之十八。",
        "- 毛利率百分之四十一点二，低于去年同期百分之四十四点七。",
        "- 经营现金流一亿四千六百万美元，低于去年同期二亿一千一百万美元。",
        "- 未交付订单六十三亿美元，同比增长百分之二十二。",
        "- 库存七亿八千万美元，同比增长百分之二十五。",
        "- 回款天数七十一天，高于去年同期五十八天。",
        "",
        "# 需要区分",
        "",
        "事实来自资料找回；推断和建议必须在报告里标出，并进入用户确认环节。",
      ].join("\n"),
    }),
    draftNode("draft-finance-report", 850, -270, {
      title: "北星机器人第二季度经营简报草稿",
      source: "eidolia_with_pska_evidence",
      runId: "pska-eidolia-finance-demo",
      flowRecipe: { id: "pska_evidence_to_report", name: "资料证据生成报告草稿" },
      contextEntries: [
        { id: "artifact-finance-evidence", enabled: true, label: "资料证据" },
        { id: "thought-finance-report", enabled: true, label: "报告目标" },
      ],
      content: [
        "# 北星机器人二〇二六年第二季度管理层经营简报草稿",
        "",
        "## 一句话结论",
        "",
        "第二季度是“收入继续增长，但毛利、回款和库存周转同时承压”的季度。增长本身还在，但经营质量需要被单独跟踪。",
        "",
        "## 已确认事实",
        "",
        "- 收入十八点四亿美元，同比增长百分之十八。",
        "- 毛利率 41.2%，低于上年同期 44.7%。",
        "- 经营现金流一亿四千六百万美元，低于上年同期二亿一千一百万美元。",
        "- 未交付订单六十三亿美元，同比增长百分之二十二，说明需求并未消失。",
        "- 库存七亿八千万美元，同比增长百分之二十五；回款天数七十一天，高于五十八天。",
        "",
        "## 推断",
        "",
        "收入增长和未交付订单增长说明订单侧仍有支撑；毛利率下滑更可能来自服务收入占比、交付成本或价格折让，而不是单纯需求恶化。现金流下滑主要应从回款天数和库存扩张两条线排查。",
        "",
        "## 建议动作",
        "",
        "1. 让财务负责人给出回款变慢的客户和区域拆分，并解释是否与大型项目验收节奏有关。",
        "2. 将库存增长拆成安全库存、滞销库存和项目预备库存，避免把真实需求和执行问题混在一起。",
        "3. 把服务毛利率、回款天数和未交付订单兑现率设为后续季度跟踪指标。",
        "",
        "## 待确认记忆",
        "",
        "- 用户在财报分析里偏好先区分事实、推断、建议。",
        "- 对增长型公司，用户会同时看收入增长和经营质量，而不是只看 revenue。",
        "- 回款天数、库存和服务毛利率应作为北星机器人后续跟踪字段。",
      ].join("\n"),
    }),
    noteNode("artifact-finance-memory-review", 330, 120, {
      subtype: "memory_review",
      title: "待确认记忆：财报分析偏好候选",
      category: "记忆确认",
      source: "pska_memory_review",
      content: [
        "# 不能自动写入长期记忆",
        "",
        "这些只是候选，智能助手不能直接写入长期记忆：",
        "",
        "- 事实/推断/建议必须分层。",
        "- 经营质量指标需要跟 revenue 一起看。",
        "- 针对北星机器人的后续跟踪字段：回款天数、库存、服务毛利、未交付订单兑现。",
        "",
        "知识助手负责确认和应用；对话工作台和创作画布只负责把候选呈现出来。",
      ].join("\n"),
    }),
  ];
  return workspace({ projectId, nodes, edges: [
    canvasEdge("edge-finance-thought-evidence", "thought-finance-report", "artifact-finance-evidence", "uses"),
    canvasEdge("edge-finance-evidence-draft", "artifact-finance-evidence", "draft-finance-report", "supports"),
    canvasEdge("edge-finance-thought-draft", "thought-finance-report", "draft-finance-report", "produces"),
    canvasEdge("edge-finance-draft-memory", "draft-finance-report", "artifact-finance-memory-review", "review"),
  ] });
}

function buildWebnovelEidoliaWorkspace({ projectId, demoSeed, sourcePackets }) {
  const recallList = sourcePacketsAsMarkdown(sourcePackets);
  const nodes = [
    noteNode("artifact-webnovel-overview", -520, -330, {
      subtype: "demo_overview",
      title: "Workflow: 设定恢复到章节续写",
      category: "工作流说明",
      source: "pska_demo_recorder",
      content: [
        "# 知识助手到创作画布：网文续写链",
        "",
        "目标：基于《云涯纪》的设定资料、章节问题和读者反馈，恢复设定约束，再在创作画布上生成第十八章续写草稿。",
        "",
        "链路：",
        "",
        "想法：明确下一章写作问题",
        "产物：保存设定资料和读者反馈",
        "草稿：输出可审阅续写段落",
        "",
        `资料文件夹编号：${demoSeed?.root_id || "未指定"}`,
      ].join("\n"),
    }),
    thoughtNode("thought-webnovel-continuation", -140, -240, {
      subtype: "question",
      title: "第18章续写：用具体动作替代命运独白",
      content: [
        "第18章需要续写，但必须保留既有设定：星图是记忆/导航工具，不是武器；岑青砚不能直接说谎；陆怀砂要承担读者视角。",
        "",
        "目标不是讲大道理，而是用铜针、星图背面、矿灯和人物动作推进情节。",
      ].join("\n"),
    }),
    noteNode("artifact-webnovel-story-bible", 330, -300, {
      subtype: "material",
      title: "设定资料与资料找回",
      category: "设定产物",
      source: "pska_source_recall",
      sourceRefs: sourcePackets,
      content: [
        "# 资料找回命中",
        "",
        recallList || "- 本次没有拿到资料找回结果；下方仍展示演示资料中的关键规则。",
        "",
        "# 稳定设定",
        "",
        "- 星图不是毁灭性武器；它更像记忆索引和导航界面。",
        "- 铜针是触发星图局部记忆的具体物件。",
        "- 岑青砚不能直接说谎，但可以回避、拆字、换顺序。",
        "- 陆怀砂需要保持读者代理人的功能：追问、误解、替读者确认规则。",
      ].join("\n"),
    }),
    noteNode("artifact-webnovel-reader-feedback", 330, 80, {
      subtype: "evidence",
      title: "读者反馈：读者更喜欢具体物件",
      category: "读者反馈",
      source: "pska_source_recall",
      content: [
        "# 读者反馈",
        "",
        "- 完读率在“铜针/星图/矿灯”等具体物件出现时更高。",
        "- “命运”“天命”“无法逃脱”类抽象独白容易降低节奏。",
        "- 读者希望第18章给出一个小答案，而不是继续扩大谜团。",
        "",
        "# 写作约束",
        "",
        "续写段落应让角色用动作发现线索，并把设定冲突转成场景张力。",
      ].join("\n"),
    }),
    draftNode("draft-webnovel-continuation", 850, -260, {
      title: "《云涯纪》第18章续写候选",
      source: "eidolia_with_pska_evidence",
      runId: "pska-eidolia-webnovel-demo",
      flowRecipe: { id: "pska_evidence_to_continuation", name: "资料证据生成续写草稿" },
      contextEntries: [
        { id: "artifact-webnovel-story-bible", enabled: true, label: "设定资料" },
        { id: "artifact-webnovel-reader-feedback", enabled: true, label: "读者反馈" },
      ],
      content: [
        "# 《云涯纪》第18章续写候选",
        "",
        "沈照夜把铜针按在星图背面时，矿灯忽然矮了一寸。",
        "",
        "不是灯火暗了，是他们脚下那块青石沉了下去。石缝里浮出一线银色的光，像有人在很久以前用指甲刻过一条路，又怕后来者看不见，便把星光藏在了缝里。",
        "",
        "陆怀砂先蹲下去，伸手要摸，被沈照夜一把扣住手腕。",
        "",
        "“别碰。”",
        "",
        "“你刚才不是说它只认针吗？”陆怀砂看着他，“那它为什么认得我的影子？”",
        "",
        "星图上，陆怀砂的影子被拉得很长，正好压住了第三颗暗星。暗星一亮，背面的细纹便从铜针周围散开，拼出半行残字：",
        "",
        "归路不在北，在记得北的人身上。",
        "",
        "岑青砚站在更远处，眼神微微动了一下。",
        "",
        "“这句话是什么意思？”陆怀砂问。",
        "",
        "岑青砚没有立刻回答。她把袖口往下拉，遮住掌心那道旧伤，像是在把某个答案重新折好。",
        "",
        "“意思是，”她说，“你们找错了门。”",
        "",
        "沈照夜抬头看她：“只是找错门？”",
        "",
        "岑青砚望向星图，声音很轻：“我没有骗你们。”",
        "",
        "她确实没有直接说谎。可沈照夜忽然明白，她也没有把话说完。",
        "",
        "## 写作说明",
        "",
        "- 用铜针、星图背面、矿灯和影子推进情节。",
        "- 保持岑青砚不能直接说谎的约束。",
        "- 给出小答案：归路与“记得北的人”有关，但保留下一章悬念。",
      ].join("\n"),
    }),
    noteNode("artifact-webnovel-memory-review", 850, 170, {
      subtype: "memory_review",
      title: "待确认记忆：创作规则候选",
      category: "记忆确认",
      source: "pska_memory_review",
      content: [
        "# 候选记忆",
        "",
        "- 用户偏好“具体物件推动剧情”，少用抽象命运独白。",
        "- 《云涯纪》星图是记忆/导航工具，不是武器。",
        "- 岑青砚不能直接说谎。",
        "",
        "这些规则需要用户确认后再进入长期 memory。",
      ].join("\n"),
    }),
  ];
  return workspace({ projectId, nodes, edges: [
    canvasEdge("edge-webnovel-thought-bible", "thought-webnovel-continuation", "artifact-webnovel-story-bible", "uses"),
    canvasEdge("edge-webnovel-bible-draft", "artifact-webnovel-story-bible", "draft-webnovel-continuation", "supports"),
    canvasEdge("edge-webnovel-feedback-draft", "artifact-webnovel-reader-feedback", "draft-webnovel-continuation", "supports"),
    canvasEdge("edge-webnovel-draft-memory", "draft-webnovel-continuation", "artifact-webnovel-memory-review", "review"),
  ] });
}

function workspace({ projectId, nodes, edges }) {
  return {
    version: 1,
    layoutVersion: 2,
    projectId,
    updatedAt: new Date().toISOString(),
    settings: {
      systemPrompt:
        "你是 Eidolia 创作画布助手。只基于显式连接的 thought/artifact 和 PSKA evidence 工作；事实、推断、建议和长期记忆候选必须分层。",
    },
    nodes,
    edges,
    viewport: { x: 80, y: 80, zoom: 0.85 },
  };
}

function noteNode(id, x, y, data) {
  return canvasNode("note", id, x, y, {
    kind: "artifact",
    capabilities: ["editable", "context_source"],
    expanded: false,
    ...data,
  });
}

function thoughtNode(id, x, y, data) {
  return canvasNode("thought", id, x, y, {
    kind: "thought",
    capabilities: ["editable", "runnable", "context_source"],
    confidence: "medium",
    expanded: false,
    ...data,
  });
}

function draftNode(id, x, y, data) {
  return canvasNode("draft", id, x, y, {
    kind: "artifact",
    subtype: "candidate",
    status: "completed",
    expanded: false,
    ...data,
  });
}

function canvasNode(type, id, x, y, data) {
  const now = new Date().toISOString();
  const content = String(data.content || "");
  return {
    id,
    type,
    position: { x, y },
    data: {
      summary: summarizeForNode(content, 220),
      charCount: content.replace(/\s+/g, "").length,
      stats: basicTextStats(content),
      createdAt: now,
      updatedAt: now,
      ...data,
    },
  };
}

function canvasEdge(id, source, target, relation) {
  return {
    id,
    source,
    target,
    sourceHandle: "output",
    targetHandle: "input",
    type: "smoothstep",
    label: relation,
    data: { relation },
  };
}

function normalizeRecallPackets(recalled) {
  const packets = [
    recalled?.context_packets,
    recalled?.packets,
    recalled?.items,
    recalled?.results,
    recalled?.hits,
  ].find(Array.isArray) || [];
  return packets.slice(0, 6).map((packet, index) => {
    const metadata = packet.metadata || packet.meta || {};
    const sourceRef = packet.source_ref || packet.sourceRef || packet.source || {};
    return {
      index: index + 1,
      title:
        packet.title
        || packet.document_title
        || sourceRef.title
        || metadata.title
        || packet.source_id
        || `source ${index + 1}`,
      path: packet.path || sourceRef.path || metadata.path || metadata.file_path || packet.source_path || "",
      excerpt:
        packet.excerpt
        || packet.snippet
        || packet.summary
        || metadata.content_excerpt
        || metadata.excerpt
        || sourceRef.excerpt
        || "",
      score: packet.score ?? packet.rank ?? null,
      source_id: packet.source_id || sourceRef.source_id || sourceRef.id || "",
    };
  });
}

function sourcePacketsAsMarkdown(sourcePackets) {
  return sourcePackets
    .map((packet) => {
      const pathText = packet.path ? ` (${packet.path})` : "";
      const excerpt = packet.excerpt ? `: ${String(packet.excerpt).replace(/\s+/g, " ").slice(0, 220)}` : "";
      return `- ${packet.title}${pathText}${excerpt}`;
    })
    .join("\n");
}

function summarizeForNode(text, maxLength) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  return clean.length > maxLength ? `${clean.slice(0, maxLength - 1)}...` : clean;
}

function basicTextStats(text) {
  const value = String(text || "");
  const nonWhitespace = value.replace(/\s+/g, "");
  return {
    chars: value.length,
    non_whitespace_chars: nonWhitespace.length,
    lines: value ? value.split(/\r?\n/u).length : 0,
    estimated_tokens: Math.ceil(value.length / 1.35),
  };
}

async function checkWebuiReachable(baseUrl) {
  const health = await fetchJson(`${baseUrl}/health`).catch((error) => {
    throw new Error(`Hermes WebUI health check failed at ${baseUrl}/health: ${error.message || error}`);
  });
  const status = await fetchJson(`${baseUrl}/api/auth/status`).catch(() => null);
  if (status && status.auth_enabled && !status.logged_in) {
    console.log("Hermes WebUI auth is enabled. Recorder will use storage state or password login if provided.");
  }
  return health;
}

async function waitForHermesTurnCompletion({ page, baseUrl, timeoutMs }) {
  const deadline = Date.now() + Math.max(0, timeoutMs);
  let sawActive = false;
  let polls = 0;
  while (Date.now() < deadline) {
    polls += 1;
    const health = await fetchJson(`${baseUrl}/health`).catch(() => null);
    const activeRuns = Number(health?.active_runs || 0);
    const activeStreams = Number(health?.active_streams || 0);
    const active = activeRuns + activeStreams;
    if (active > 0) sawActive = true;
    if (sawActive && active === 0) {
      await page.waitForTimeout(2500);
      return { completed: true, polls };
    }
    await page.waitForTimeout(1000);
  }
  if (!sawActive && timeoutMs > 0) {
    await page.waitForTimeout(Math.min(timeoutMs, 30_000));
  }
  return { completed: false, polls };
}

async function postJson(url, payload) {
  return fetchJson(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

async function putJson(url, payload) {
  return fetchJson(url, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  if (!response.ok) throw new Error(payload.error || `${response.status} ${response.statusText}`);
  return payload;
}

async function loginIfNeeded(page, { password, baseUrl }) {
  await page.waitForLoadState("domcontentloaded");
  if (!(await page.locator("#login-form").count())) return;
  if (!password) {
    throw new Error(
      [
        "Hermes WebUI requires authentication.",
        "Provide one of:",
        "  HERMES_WEBUI_PASSWORD=... node scripts/record_hermes_pska_extension_demo.cjs",
        "  HERMES_WEBUI_STORAGE_STATE=/absolute/path/state.json node scripts/record_hermes_pska_extension_demo.cjs",
        "To export a storage state, log in with Playwright or ask Codex to generate one after you provide the password.",
      ].join("\n"),
    );
  }
  await page.locator("#pw").fill(password);
  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 20_000 }).catch(() => null),
    page.locator("#login-form button[type='submit']").click(),
  ]);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
}

async function waitForHermesShell(page) {
  await page.waitForSelector("#msg", { timeout: 30_000 });
  await page.waitForSelector("#btnSend", { timeout: 30_000 });
  await page.waitForSelector("#pskaMiniChip", { timeout: 30_000 });
}

async function openPskaMenu(page) {
  const chip = page.locator("#pskaMiniChip");
  if (!(await chip.isVisible().catch(() => false))) {
    await returnToChatShell(page);
  }
  await chip.waitFor({ state: "visible", timeout: 15_000 });
  const menuHidden = await page.locator("#pskaMiniMenu").evaluate((el) => el.hidden).catch(() => true);
  if (menuHidden) {
    await moveToLocator(page, chip);
    await clickLocator(page, chip);
  }
  await page.locator("#pskaMiniMenu").waitFor({ state: "visible", timeout: 10_000 });
}

async function returnToChatShell(page) {
  await page.evaluate(async () => {
    const isVisible = (element) => {
      if (!element) return false;
      const style = window.getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
    };
    if (typeof window.switchPanel === "function") {
      for (const panelName of ["chat", "sessions", "home"]) {
        try {
          const result = window.switchPanel(panelName);
          if (result && typeof result.then === "function") await result;
          if (isVisible(document.querySelector("#msg")) && isVisible(document.querySelector("#pskaMiniChip"))) break;
        } catch {
          // Hermes panel names have changed across local builds; fall through to DOM cleanup.
        }
      }
    }
    const main = document.querySelector("main.main") || document.querySelector("main");
    if (main) main.classList.remove("showing-pska-mini");
    document.querySelectorAll('[data-panel="pska-mini"]').forEach((item) => item.classList.remove("active"));
  });

  const navCandidates = [
    '[data-panel="chat"]',
    '[data-panel="sessions"]',
    '[data-panel="home"]',
    '[data-dashboard-link]',
    'button[aria-label="Chat"]',
    'button[aria-label="Sessions"]',
  ];
  for (const selector of navCandidates) {
    if ((await page.locator("#msg").isVisible().catch(() => false))
      && (await page.locator("#pskaMiniChip").isVisible().catch(() => false))) {
      break;
    }
    const candidate = page.locator(selector).first();
    if (await candidate.isVisible().catch(() => false)) {
      await moveToLocator(page, candidate);
      await clickLocator(page, candidate);
      await page.waitForTimeout(500);
    }
  }

  await page.locator("#msg").waitFor({ state: "visible", timeout: 15_000 });
  await page.locator("#pskaMiniChip").waitFor({ state: "visible", timeout: 15_000 });
}

async function closePskaMenu(page) {
  await page.keyboard.press("Escape").catch(() => {});
  await page.evaluate(() => {
    const menu = document.getElementById("pskaMiniMenu");
    const chip = document.getElementById("pskaMiniChip");
    if (menu) menu.hidden = true;
    if (chip) chip.setAttribute("aria-expanded", "false");
  }).catch(() => {});
  await page.waitForTimeout(300);
}

async function getEidoliaContentFrame(page) {
  const iframe = page.locator("#eidoliaFrame");
  await iframe.waitFor({ state: "attached", timeout: 15_000 });
  const handle = await iframe.elementHandle();
  for (let attempt = 0; attempt < 80; attempt += 1) {
    const frame = await handle.contentFrame();
    if (frame) return frame;
    await page.waitForTimeout(250);
  }
  throw new Error("Eidolia iframe was attached, but Playwright could not access its content frame.");
}

async function waitForEidoliaCanvas(frame, eidoliaSeed) {
  await frame.waitForSelector(".react-flow__viewport", { timeout: 30_000 });
  const draftSelector = `[data-id="${eidoliaSeed.draft_node_id}"]`;
  try {
    await frame.waitForSelector(draftSelector, { timeout: 18_000 });
  } catch (error) {
    const projectSelect = frame.locator("select").first();
    if (await projectSelect.count().catch(() => 0)) {
      await projectSelect.selectOption(eidoliaSeed.project_id).catch(() => {});
      await frame.waitForTimeout(1800);
    }
    await frame.waitForSelector(draftSelector, { timeout: 18_000 });
  }
  for (const nodeId of eidoliaSeed.focus_node_ids || []) {
    await frame.waitForSelector(`[data-id="${nodeId}"]`, { timeout: 10_000 });
  }
}

async function fitEidoliaNodes(frame, nodeIds, padding = 160, duration = 900) {
  await frame.evaluate(
    ({ nodeIds: ids, padding: framePadding, duration: transitionDuration }) => {
      const parseTranslate = (value = "") => {
        const match = String(value).match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/u);
        return match ? { x: Number(match[1]), y: Number(match[2]) } : { x: 0, y: 0 };
      };
      const selected = ids
        .map((nodeId) => document.querySelector(`[data-id="${CSS.escape(nodeId)}"]`))
        .filter(Boolean)
        .map((node) => {
          const position = parseTranslate(node.getAttribute("style") || "");
          return {
            x: position.x,
            y: position.y,
            width: node.offsetWidth || 340,
            height: node.offsetHeight || 200,
          };
        });
      if (!selected.length) return;
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const node of selected) {
        minX = Math.min(minX, node.x);
        minY = Math.min(minY, node.y);
        maxX = Math.max(maxX, node.x + node.width);
        maxY = Math.max(maxY, node.y + node.height);
      }
      const flowBox = document.querySelector(".react-flow")?.getBoundingClientRect();
      const visibleWidth = Math.max(1, flowBox?.width || window.innerWidth || 1280);
      const visibleHeight = Math.max(1, flowBox?.height || window.innerHeight || 720);
      const boundsWidth = Math.max(1, maxX - minX + framePadding * 2);
      const boundsHeight = Math.max(1, maxY - minY + framePadding * 2);
      const zoom = Math.max(0.28, Math.min(0.95, visibleWidth / boundsWidth, visibleHeight / boundsHeight));
      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      const viewport = {
        x: visibleWidth / 2 - centerX * zoom,
        y: visibleHeight / 2 - centerY * zoom,
        zoom,
      };
      const transform = document.querySelector(".react-flow__viewport");
      if (transform) {
        transform.style.transition = `transform ${transitionDuration}ms cubic-bezier(0.22, 1, 0.36, 1)`;
        transform.style.transform = `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`;
      }
    },
    { nodeIds, padding, duration },
  );
  await frame.waitForTimeout(duration + 300);
}

async function highlightEidoliaNode(frame, nodeId) {
  await frame.evaluate((targetNodeId) => {
    document.querySelectorAll(".pska-demo-eidolia-highlight").forEach((node) => {
      node.classList.remove("pska-demo-eidolia-highlight");
      node.style.boxShadow = "";
      node.style.outline = "";
    });
    const node = document.querySelector(`[data-id="${CSS.escape(targetNodeId)}"]`);
    if (!node) return;
    node.classList.add("pska-demo-eidolia-highlight");
    node.style.outline = "3px solid rgba(51, 129, 255, 0.95)";
    node.style.boxShadow = "0 0 0 8px rgba(51, 129, 255, 0.18), 0 22px 50px rgba(15, 23, 42, 0.18)";
  }, nodeId);
  await frame.waitForTimeout(500);
}

async function openEidoliaNode(frame, nodeId) {
  await frame.waitForSelector(`[data-id="${nodeId}"]`, { timeout: 10_000 });
  await frame.evaluate((targetNodeId) => {
    const node = document.querySelector(`[data-id="${CSS.escape(targetNodeId)}"]`);
    if (!node) return;
    const maximize = node.querySelector('button[title="充满窗口"]');
    if (maximize) {
      maximize.click();
      return;
    }
    const article = node.querySelector("article") || node;
    article.dispatchEvent(new MouseEvent("dblclick", {
      bubbles: true,
      cancelable: true,
      view: window,
    }));
  }, nodeId);
  await frame.waitForSelector(".node-focus-overlay", { timeout: 10_000 });
}

async function scrollEidoliaOverlay(frame, amount = 600) {
  await frame.evaluate((nextAmount) => {
    const box = document.querySelector(".node-focus-content");
    if (box) box.scrollTop += nextAmount;
  }, amount);
  await frame.waitForTimeout(650);
}

async function applyDemoSourceScope(page, demoSeed) {
  if (!demoSeed || !demoSeed.root_id) return;
  await page.waitForFunction(
    () => window.PSKAMini && typeof window.PSKAMini.setSourceRootIds === "function",
    null,
    { timeout: 15_000 },
  );
  await page.evaluate((rootId) => {
    window.PSKAMini.setSourceRootIds([rootId]);
  }, demoSeed.root_id);
}

async function prepareScope(page) {
  await ensurePskaEnabled(page);
  const datasets = await page.locator("#pskaMiniDatasetList [data-pska-dataset-id]").count().catch(() => 0);
  if (datasets > 0) {
    await clickById(page, "pskaMiniSelectReady");
  } else {
    await page.locator("#pskaMiniMode").selectOption("memory-only");
  }
  await page.waitForTimeout(500);
}

async function ensurePskaEnabled(page) {
  await openPskaMenu(page);
  const enabled = page.locator("#pskaMiniEnabled");
  if (!(await enabled.isChecked().catch(() => false))) {
    await enabled.check({ force: true });
  }
}

async function clickById(page, id) {
  const locator = page.locator(`#${id}`);
  await locator.waitFor({ state: "attached", timeout: 15_000 });
  await locator.scrollIntoViewIfNeeded({ timeout: 10_000 }).catch(() => {});
  await locator.waitFor({ state: "visible", timeout: 15_000 });
  await moveToLocator(page, locator);
  await clickLocator(page, locator);
}

async function waitForPreviewText(page, needle, timeout) {
  await page.waitForFunction(
    (text) => {
      const box = document.querySelector("#pskaMiniPreviewBox");
      return Boolean(box && !box.hidden && box.innerText.includes(text));
    },
    needle,
    { timeout },
  );
}

async function waitForPreviewOrMenuText(page, needle, timeout) {
  await page.waitForFunction(
    (text) => {
      const menu = document.querySelector("#pskaMiniMenu");
      const preview = document.querySelector("#pskaMiniPreviewBox");
      return Boolean(
        (menu && menu.innerText.includes(text)) || (preview && !preview.hidden && preview.innerText.includes(text)),
      );
    },
    needle,
    { timeout },
  );
}

async function waitForPskaStatusReady(page, timeout) {
  await page.waitForFunction(
    () => {
      const text = document.querySelector("#pskaMiniStatus")?.innerText || "";
      return /API\s+ready/iu.test(text)
        && /KB\s+(\d+\/\d+|ready)/iu.test(text)
        && /Memory\s+\S+/iu.test(text)
        && !/checking/iu.test(text);
    },
    undefined,
    { timeout },
  );
}

async function waitForPreviewAny(page, needles, timeout) {
  await page.waitForFunction(
    (items) => {
      const box = document.querySelector("#pskaMiniPreviewBox");
      if (!box || box.hidden) return false;
      const text = box.innerText || "";
      return items.some((item) => text.includes(item));
    },
    needles,
    { timeout },
  );
}

async function revealPreview(page) {
  await page.evaluate(() => {
    const menu = document.getElementById("pskaMiniMenu");
    const preview = document.getElementById("pskaMiniPreviewBox");
    if (!menu || !preview || preview.hidden) return;
    preview.scrollIntoView({ block: "end", inline: "nearest" });
    menu.scrollTop = menu.scrollHeight;
    preview.scrollTop = 0;
  });
  await page.waitForTimeout(250);
}

async function setComposerQuestion(page, question) {
  const input = page.locator("#msg");
  await input.waitFor({ state: "visible", timeout: 15_000 });
  await input.fill("");
  await input.click();
  await page.keyboard.type(question, { delay: 4 });
  await input.evaluate((el) => el.dispatchEvent(new Event("input", { bubbles: true })));
}

async function installOverlay(page) {
  await page.addStyleTag({
    content: `
      body { cursor: none !important; }
      #pska-demo-cursor, #pska-demo-overlay, .pska-demo-ripple { pointer-events: none !important; }
      #pska-demo-overlay {
        position: fixed;
        left: 72px;
        right: 0;
        top: 0;
        z-index: 999999;
        color: #f7faf8;
        font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      }
      #pska-demo-overlay .top {
        background: rgba(14, 20, 24, 0.92);
        border-bottom: 1px solid rgba(92, 157, 244, 0.45);
        padding: 12px 24px 10px;
      }
      #pska-demo-overlay .title {
        font-size: 24px;
        font-weight: 760;
        line-height: 1.15;
      }
      #pska-demo-overlay .caption {
        position: fixed;
        left: 96px;
        right: 24px;
        bottom: 20px;
        background: rgba(14, 20, 24, 0.92);
        border: 1px solid rgba(92, 157, 244, 0.55);
        border-radius: 10px;
        padding: 11px 15px;
        color: #f7faf8;
        font-size: 20px;
        line-height: 1.36;
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.2);
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
        border: 4px solid rgba(74, 139, 245, 0.75);
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
        <path d="M3 3L3 34L13 25L20 43L28 39L20 22L32 22L3 3Z" fill="white" stroke="#101820" stroke-width="2"/>
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
  if (result.status !== 0) throw new Error(`ffmpeg failed with status ${result.status}`);
}

function writeSrt(timeline, output) {
  const blocks = timeline.map((item, index) => {
    const text = subtitleLines(item.caption, 42).join("\n");
    return `${index + 1}\n${srtTime(item.startsAt)} --> ${srtTime(item.endsAt)}\n${text}\n`;
  });
  fs.writeFileSync(output, blocks.join("\n"), "utf8");
}

function writeStoryboard(timeline, output) {
  const lines = ["# Hermes WebUI PSKA Extension Demo Storyboard", ""];
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

main();
