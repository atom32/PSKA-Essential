const LOCALE = "zh-CN";
const MEMORY_CARD_TYPES = ["identity", "preference", "project_state", "working_habit", "source_route", "correction", "exclusion"];
const MEMORY_CARD_SCOPES = ["global", "workspace", "project", "folder"];

const messages = {
  "view.home": "首页",
  "view.kb": "知识库",
  "view.sources": "资料源",
  "view.ask": "提问",
  "view.reader": "来源",
  "view.writing": "写作",
  "view.memory": "记忆",
  "view.review": "异常审核",
  "view.activity": "活动",
  "view.settings": "设置",
  "status.none": "无",
  "status.apiOnline": "API 已连接",
  "status.apiError": "API 错误",
  "toast.kbCreatedSelected": "知识库已创建，并选为上传目标。",
  "toast.kbCreated": "知识库已创建。",
  "toast.selectFiles": "请选择文件。",
  "toast.uploadAcceptedSelected": "上传已接受，目标知识库已保留。",
  "toast.uploadAccepted": "上传已接受。",
  "toast.datasetRequired": "需要知识库 ID。",
  "toast.uploadTargetSelected": "已选择上传目标。",
  "toast.prepareLoop": "请选择来源文件、填写知识库名称，然后运行闭环。",
  "toast.selectKnowledgeBase": "请选择知识库。",
  "toast.selectDataset": "请选择数据集。",
  "toast.selectAtLeastOneDataset": "请至少选择一个知识库。",
  "toast.retrievalProbeRecorded": "检索探针已记录。",
  "toast.ingestLoopWaiting": "闭环正在等待知识库就绪。",
  "toast.ingestLoopCompleted": "闭环已完成。",
  "toast.ingestLoopIncomplete": "闭环尚未完成。",
  "toast.componentCheckRecorded": "组件检查已记录。",
  "toast.productEvalCompleted": "产品验收已完成。",
  "toast.memoryProbeRecorded": "记忆探针已记录。",
  "toast.memoryBriefingLoaded": "记忆简报已加载。",
  "toast.memoryReviewQueueLoaded": "记忆维护队列已加载。",
  "toast.reviewBatchDecided": "批量审核已处理。",
  "toast.reviewCandidatesMerged": "候选记忆已合并。",
  "toast.memoryCardsLoaded": "记忆卡片已加载。",
  "toast.memoryHealthLoaded": "记忆健康扫描已加载。",
  "toast.memoryAttributionLoaded": "记忆归因已加载。",
  "toast.memoryUseTraceLoaded": "记忆使用痕迹已加载。",
  "toast.memoryTimelineLoaded": "记忆时间线已加载。",
  "toast.closedLoopProbeRecorded": "实时闭环探针已记录。",
  "toast.askScopeReady": "提问范围已就绪。",
  "toast.askScopeNotReady": "提问范围尚未就绪。",
  "toast.loadDatasetBeforeParse": "请先加载知识库，再解析文档。",
  "toast.noUnreadyDocuments": "没有需要解析的文档。",
  "toast.parseStarted": "解析已开始。",
  "toast.kbReadyAskUpdated": "知识库已就绪，提问范围已更新。",
  "toast.sourceRootRegistered": "资料源已注册。",
  "toast.sourceScanCompleted": "资料源扫描完成。",
  "toast.sourceAuditCompleted": "资料源审计完成。",
  "toast.sourceAuditJobsActivated": "到期资料源审计已入队。",
  "toast.sourceAuditJobCompleted": "资料源审计队列已运行。",
  "toast.sourceExtractionJobQueued": "资料源抽取任务已入队。",
  "toast.sourceExtractionJobCompleted": "资料源抽取任务已运行。",
  "toast.sourceMemoryReviewCreated": "资料源记忆审核已创建。",
  "toast.sourceMemoryCandidatesCreated": "资料源记忆候选已创建。",
  "toast.sourceSavedSearchCreated": "资料源查询已保存。",
  "toast.sourceSelected": "资料源已选中。",
  "toast.sourceSelectRequired": "请先选择一个资料源。",
  "toast.sourceTagProposalCreated": "标签提议已创建。",
  "toast.sourceTagApplied": "标签已写入 sidecar。",
  "toast.sourceCommentProposalCreated": "Comment 提议已创建。",
  "toast.sourceCommentApplied": "Comment 已写入 sidecar。",
  "toast.obsidianMocProposalCreated": "Obsidian MOC 提议已创建。",
  "toast.sourceQueryRequired": "请输入资料源查询。",
  "empty.datasetsUnavailable": "知识库不可用。",
  "empty.datasets": "尚未加载知识库。",
  "empty.documents": "尚未加载文档。",
  "empty.reviewsUnavailable": "异常审核项不可用。",
  "empty.reviews": "尚未加载异常审核项。",
  "empty.runsUnavailable": "运行记录不可用。",
  "empty.runs": "尚未加载运行记录。",
  "empty.auditUnavailable": "审计记录不可用。",
  "empty.audit": "尚未加载审计记录。",
  "empty.noNextActions": "尚未加载下一步操作。",
  "empty.noReviews": "没有异常审核项。",
  "empty.noResumableAsks": "没有可恢复提问。",
  "empty.noScope": "尚未选择范围。",
  "empty.noAskScopeChecked": "尚未检查提问范围。",
  "empty.noDatasetsOption": "没有知识库",
  "empty.noDiagnostics": "尚未加载诊断。",
  "empty.noComponentCheck": "尚未运行组件检查。",
  "empty.noProductEval": "尚未运行产品验收。",
  "empty.noRetrievalProbe": "尚未运行检索探针。",
  "empty.noMemoryProbe": "尚未运行记忆探针。",
  "empty.noMemoryBriefing": "没有需要关注的记忆。",
  "empty.noMemoryReviewQueue": "没有需要处理的记忆维护项。",
  "empty.noMemoryCards": "没有匹配的记忆卡片。",
  "empty.noMemoryHealthIssues": "没有匹配的记忆健康问题。",
  "empty.noMemoryAttribution": "这个结果没有使用长期记忆。",
  "empty.noMemorySuggestions": "没有可治理的记忆建议。",
  "empty.noMemoryUseTrace": "没有匹配的记忆使用痕迹。",
  "empty.noMemoryTimeline": "没有匹配的记忆时间线。",
  "empty.noClosedLoopProbe": "尚未运行实时闭环探针。",
  "empty.noJarvisBriefing": "Jarvis briefing 尚未加载。",
  "empty.sourcesUnavailable": "资料源不可用。",
  "empty.sources": "尚未加载资料源。",
  "empty.noSourceAudit": "尚未运行资料源审计。",
  "empty.noSourceAuditActions": "没有资料源审计动作。",
  "empty.noSourceSearchResults": "没有匹配的资料源结果。",
  "empty.noSelectedSource": "从搜索结果或审计清单中选择一个 source。",
  "empty.noAskDocuments": "所选范围尚未加载文档。",
  "empty.selectDataset": "请选择知识库。",
  "empty.noContext": "所选范围没有检索到上下文。",
  "empty.noFollowup": "这个结果没有可用的后续操作。",
  "empty.writing": "运行提问后会生成带来源的 brief。",
  "empty.exportPrompt": "运行已加载。请使用 Markdown 或 JSON 创建导出。",
  "button.apply": "应用",
  "button.inspect": "查看",
  "button.parse": "解析",
  "button.parseScope": "解析范围",
  "button.parseListed": "解析列表",
  "button.resume": "恢复",
  "button.resumeLoop": "恢复闭环",
  "button.resumeAsk": "恢复提问",
  "button.review": "异常审核",
  "button.start": "开始",
  "button.ask": "提问",
  "button.askThisKb": "提问此知识库",
  "button.track": "跟踪",
  "button.trackStatus": "跟踪状态",
  "button.trackResume": "跟踪并恢复",
  "button.tracking": "跟踪中...",
  "button.openStatus": "打开状态",
  "button.reloadStatus": "刷新状态",
  "button.refreshJarvis": "刷新 Jarvis",
  "button.checkReadiness": "检查就绪",
  "button.upload": "上传",
  "button.open": "打开",
  "button.runAsk": "运行提问",
  "button.openWriting": "打开写作",
  "button.openAsk": "打开提问",
  "button.openReview": "打开异常审核",
  "button.register": "注册",
  "button.scan": "扫描",
  "button.audit": "审计",
  "button.search": "搜索",
  "button.annotate": "标注",
  "button.memoryReview": "创建异常审核",
  "button.applyMemory": "应用记忆",
  "button.applyMemoryUpdate": "应用记忆更新",
  "button.applyMemoryDelete": "应用记忆删除",
  "button.createUpdateReview": "创建异常更新审核",
  "button.createDeleteReview": "创建异常删除审核",
  "button.whyUsed": "为什么用到",
  "button.useTrace": "使用痕迹",
  "button.timeline": "时间线",
  "button.accept": "接受",
  "button.acceptGroup": "批量接受",
  "button.edit": "需修改",
  "button.reject": "拒绝",
  "button.rejectGroup": "批量拒绝",
  "button.revise": "提交修改",
  "button.history": "历史",
  "button.source": "来源",
  "button.delete": "删除",
  "button.unsupportedMemoryApply": "不支持应用记忆",
  "button.unsupportedUpdate": "不支持更新",
  "button.unsupportedDelete": "不支持删除",
  "label.productApi": "Product API",
  "label.capabilityContract": "能力契约",
  "label.runtimeStatus": "运行状态",
  "label.workspace": "工作区",
  "label.tenant": "租户",
  "label.memoryNamespace": "记忆命名空间",
  "label.retrieval": "检索",
  "label.knowledgeBase": "知识库",
  "label.memory": "记忆",
  "label.developmentFake": "开发 Fake",
  "label.durableMemoryPolicy": "长期记忆策略",
  "label.memoryApply": "记忆应用",
  "label.memoryUpdate": "记忆更新",
  "label.memoryDelete": "记忆删除",
  "label.memoryCard": "记忆卡片",
  "label.durableMemory": "长期记忆",
  "label.durableProposalKinds": "长期提案类型",
  "label.availableModes": "可用模式",
  "label.transientResults": "临时结果",
  "label.memoryPatchAction": "记忆补丁动作",
  "label.memoryUpdateAction": "记忆更新动作",
  "label.memoryDeleteAction": "记忆删除动作",
  "label.notChecked": "未检查",
  "label.notConfigured": "未配置",
  "label.default": "默认",
  "label.loaded": "已加载",
  "label.enabled": "启用",
  "label.disabled": "禁用",
  "label.notReported": "未报告",
  "label.supported": "支持",
  "label.unsupported": "不支持",
  "label.reason": "原因",
  "label.locked": "已锁定",
  "label.rejected": "已拒绝",
  "label.reviewReason": "原因",
  "label.sources": "来源",
  "heading.insufficientContext": "上下文不足",
  "heading.retrievedContext": "已检索上下文",
  "heading.scopeNotReady": "知识范围尚未就绪",
  "heading.sourcedBrief": "带来源 Brief",
  "heading.context": "上下文",
  "heading.nextActions": "下一步",
  "heading.appliedKnowledge": "已应用长期知识",
  "heading.durableMemory": "长期记忆",
  "heading.memoryAttribution": "记忆归因",
  "heading.memorySuggestions": "记忆建议",
  "heading.inspectedSources": "已检查来源",
  "heading.sourceManifest": "来源清单",
  "heading.componentCheck": "组件检查",
  "heading.productAcceptance": "产品验收",
  "heading.memoryProbe": "记忆探针",
  "heading.liveClosedLoop": "实时闭环",
  "heading.jarvisBar": "Jarvis Bar",
};

function t(key, fallback = "") {
  return messages[key] || fallback || key;
}

const state = {
  datasets: [],
  reviews: [],
  reviewView: [],
  pendingReviews: null,
  health: null,
  policy: null,
  capabilities: null,
  capabilitiesError: "",
  lastRunId: null,
  reader: null,
  workflows: [],
  resumableAsks: [],
  auditEvents: [],
  currentBrief: null,
  currentAskResult: null,
  diagnostics: null,
  workspaceStatus: null,
  jarvisBriefing: null,
  jarvisError: "",
  jarvisLoading: false,
  sourceRoots: [],
  sourceRootError: "",
  sourceAudit: null,
  sourceAuditScope: {},
  sourceExtractionJob: null,
  sourceSearchResults: [],
  sourceSearchError: "",
  sourceSearchCount: null,
  activeSourceRootId: "",
  sourceScanResults: {},
  selectedSourceRef: null,
  selectedSourceTitle: "",
  sourceSavedSearch: null,
  sourceTagProposal: null,
  sourceTagApply: null,
  sourceCommentProposal: null,
  sourceCommentApply: null,
  componentCheck: null,
  productEval: null,
  retrievalProbe: null,
  memoryProbe: null,
  memoryBriefing: null,
  memoryBriefingError: "",
  memoryReviewQueue: null,
  memoryReviewQueueError: "",
  memoryCards: [],
  memoryCardsError: "",
  memoryCardStatus: "active",
  memoryCardType: "",
  memoryCardQuery: "",
  memoryHealth: null,
  memoryHealthError: "",
  memoryHealthType: "",
  memoryUseTraces: [],
  memoryUseTraceError: "",
  memoryUseTraceMemoryId: "",
  memoryUseTraceQuery: "",
  memoryWhyUsed: null,
  memoryTimeline: null,
  memoryTimelineError: "",
  memoryTimelineMemoryId: "",
  closedLoopProbe: null,
  askReadiness: null,
  askReadinessScopeKey: "",
  focusReviewId: null,
  memoryApplyByReview: {},
  activeDocumentDatasetId: null,
  activeDocuments: [],
  readinessByDataset: {},
  ingestionPoll: null,
  blockedAskPoll: null,
  askDocumentsByDataset: {},
  auditAction: "",
  reviewStatus: "",
};

const titles = {
  home: t("view.home"),
  kb: t("view.kb"),
  sources: t("view.sources"),
  ask: t("view.ask"),
  reader: t("view.reader"),
  writing: t("view.writing"),
  memory: t("view.memory"),
  review: t("view.review"),
  activity: t("view.activity"),
  settings: t("view.settings"),
};

document.addEventListener("DOMContentLoaded", () => {
  bindNavigation();
  bindForms();
  bindRefresh();
  refreshAll();
});

function bindNavigation() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      const view = button.dataset.view;
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".view").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(view).classList.add("active");
      document.getElementById("view-title").textContent = titles[view] || "PSKA";
    });
  });
}

function bindForms() {
  document.getElementById("create-kb-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = await api("/api/kb/datasets", {
      method: "POST",
      body: {
        name: form.get("name"),
        description: form.get("description"),
        chunk_method: form.get("chunk_method"),
        embedding_model: form.get("embedding_model"),
      },
    });
    event.currentTarget.reset();
    if (payload.dataset && payload.dataset.dataset_id) {
      setUploadDataset(payload.dataset.dataset_id);
      showToast(t("toast.kbCreatedSelected"));
    } else {
      showToast(t("toast.kbCreated"));
    }
    await loadDatasets();
    await loadWorkspaceStatus();
    await loadAuditEvents("kb.dataset.create");
  });

  document.getElementById("upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = new FormData();
    const fileCount = appendUploadFiles(form, payload);
    if (!fileCount) {
      showToast(t("toast.selectFiles"));
      return;
    }
    payload.append("dataset_id", form.get("dataset_id") || "");
    payload.append("dataset_name", form.get("dataset_name") || "");
    payload.append("embedding_model", form.get("embedding_model") || "");
    payload.append("parse", form.get("parse") ? "true" : "false");
    payload.append("wait", form.get("wait") ? "true" : "false");
    const result = await api("/api/kb/ingest", { method: "POST", formData: payload });
    const datasetId = ingestDatasetId(result.ingest);
    event.currentTarget.reset();
    if (datasetId) {
      setUploadDataset(datasetId);
      showToast(t("toast.uploadAcceptedSelected"));
    } else {
      showToast(t("toast.uploadAccepted"));
    }
    renderIngestResult(result.ingest, result.readiness);
    await loadDatasets();
    await loadAuditEvents("kb.ingest");
    if (datasetId) {
      const documents = await loadDocuments(datasetId, { silent: true });
      const summary = summarizeDocuments(documents);
      if (result.ingest && result.ingest.parse && result.ingest.parse.parse_started && summary.status === "processing") {
        startIngestionPolling(datasetId);
      }
    }
    await loadWorkspaceStatus();
  });

  document.getElementById("document-status-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await loadDocuments(form.get("dataset_id"));
  });

  document.getElementById("ask-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      question: form.get("question"),
      dataset_ids: splitIds(form.get("dataset_ids")),
      document_ids: splitIds(form.get("document_ids")),
      limit: Number(form.get("limit") || 5),
      max_iterations: Number(form.get("max_iterations") || 2),
      min_context_packets: Number(form.get("min_context_packets") || 1),
      retrieval_queries: splitLines(form.get("retrieval_queries")),
      source_inspection_limit: Number(form.get("source_inspection_limit") || 3),
      proposal_kind: form.get("proposal_kind"),
      use_kg: Boolean(form.get("use_kg")),
    };
    if (form.get("create_review")) {
      body.create_review = true;
    }
    const result = await api("/api/ask", { method: "POST", body });
    await applyAskResult(result);
  });

  const askForm = document.getElementById("ask-form");
  askForm.elements.dataset_ids.addEventListener("input", handleAskScopeInput);
  askForm.elements.document_ids.addEventListener("input", handleAskScopeInput);
  document.getElementById("source-root-form").addEventListener("submit", registerSourceRoot);
  document.getElementById("source-search-form").addEventListener("submit", searchSources);
  document.getElementById("source-saved-search-form").addEventListener("submit", saveSourceSearch);
  document.getElementById("source-annotation-form").addEventListener("submit", handleSourceAnnotation);
  document.getElementById("memory-card-search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    state.memoryCardQuery = document.getElementById("memory-card-query").value || "";
    loadMemoryCards();
  });
  document.getElementById("memory-use-trace-form").addEventListener("submit", (event) => {
    event.preventDefault();
    state.memoryUseTraceMemoryId = document.getElementById("memory-use-trace-memory-id").value.trim();
    state.memoryUseTraceQuery = document.getElementById("memory-use-trace-query").value.trim();
    loadMemoryUseTraces({ toast: true });
  });
}

async function applyAskResult(result, options = {}) {
  state.lastRunId = result.run && result.run.run_id;
  state.currentAskResult = result.run ? result : null;
  state.currentBrief = result.run
    ? {
        run: result.run,
        artifact: result.artifact,
        brief: result.brief || "",
        status: result.status,
        proposal: result.proposal,
        review: result.review,
        review_decision: result.review_decision,
        memory_apply: result.memory_apply,
        memory_facts: result.memory_facts || [],
        memory_attribution: result.memory_attribution || (result.artifact && result.artifact.memory_attribution) || null,
        memory_suggestions: result.memory_suggestions || (result.artifact && result.artifact.memory_suggestions) || null,
      }
    : null;
  renderAskResult(result);
  renderWriting();
  await loadReviews();
  await loadPendingReviews();
  await loadWorkflows();
  await loadResumableAsks();
  await loadWorkspaceStatus();
  await loadAuditEvents(auditActionForAskResult(result));
  renderHome();
  if (options.toast) {
    showToast(options.toast);
  }
}

function bindRefresh() {
  document.getElementById("refresh-all").addEventListener("click", refreshAll);
  document.getElementById("reload-datasets").addEventListener("click", loadDatasets);
  document.getElementById("delete-all-datasets").addEventListener("click", deleteAllDatasets);
  document.getElementById("upload-use-dataset").addEventListener("click", setUploadDatasetFromPicker);
  document.getElementById("run-ingest-loop").addEventListener("click", runIngestLoopFromUploadForm);
  document.getElementById("parse-documents").addEventListener("click", parseActiveDocuments);
  document.getElementById("ask-add-dataset").addEventListener("click", () => addAskDataset());
  document.getElementById("ask-load-documents").addEventListener("click", loadAskDocuments);
  document.getElementById("ask-check-readiness").addEventListener("click", () => checkAskReadiness());
  document.getElementById("reload-sources").addEventListener("click", loadSourceRoots);
  document.getElementById("run-source-extraction-job").addEventListener("click", () => runSourceExtractionJob());
  document.getElementById("run-source-audit").addEventListener("click", () => runSourceAudit());
  document.getElementById("source-root-filter").addEventListener("change", (event) => {
    state.activeSourceRootId = event.currentTarget.value || "";
    renderSourceRootPickers();
    renderSources();
  });
  document.getElementById("reload-reviews").addEventListener("click", loadReviews);
  document.getElementById("reload-memory-review-queue").addEventListener("click", () => loadMemoryReviewQueue({ toast: true }));
  document.getElementById("review-status-filter").addEventListener("change", (event) => {
    state.reviewStatus = event.currentTarget.value || "";
    loadReviews();
  });
  document.getElementById("reload-workflows").addEventListener("click", loadWorkflows);
  document.getElementById("reload-audit").addEventListener("click", () => loadAuditEvents());
  document.getElementById("run-component-check").addEventListener("click", runComponentCheck);
  document.getElementById("run-product-eval").addEventListener("click", runProductEval);
  document.getElementById("run-retrieval-probe").addEventListener("click", runRetrievalProbe);
  document.getElementById("run-memory-probe").addEventListener("click", runMemoryProbe);
  document.getElementById("reload-memory-briefing").addEventListener("click", () => loadMemoryBriefing({ toast: true }));
  document.getElementById("reload-memory-cards").addEventListener("click", () => loadMemoryCards({ toast: true }));
  document.getElementById("reload-memory-health").addEventListener("click", () => loadMemoryHealth({ toast: true }));
  document.getElementById("memory-health-type-filter").addEventListener("change", (event) => {
    state.memoryHealthType = event.currentTarget.value || "";
    loadMemoryHealth();
  });
  document.getElementById("reload-memory-use-traces").addEventListener("click", () => loadMemoryUseTraces({ toast: true }));
  document.getElementById("load-memory-timeline").addEventListener("click", loadMemoryTimelineFromInput);
  document.getElementById("memory-card-status-filter").addEventListener("change", (event) => {
    state.memoryCardStatus = event.currentTarget.value || "active";
    loadMemoryCards();
  });
  document.getElementById("memory-card-type-filter").addEventListener("change", (event) => {
    state.memoryCardType = event.currentTarget.value || "";
    loadMemoryCards();
  });
  document.getElementById("run-closed-loop-probe").addEventListener("click", runClosedLoopProbe);
  document.getElementById("audit-action-filter").addEventListener("change", (event) => {
    state.auditAction = event.currentTarget.value || "";
    loadAuditEvents();
  });
  document.getElementById("export-markdown").addEventListener("click", () => exportCurrent("markdown"));
  document.getElementById("export-json").addEventListener("click", () => exportCurrent("json"));
  document.getElementById("create-memory-review").addEventListener("click", () => createMemoryReviewFromRun());
}

async function refreshAll() {
  await Promise.allSettled([
    loadHealth(),
    loadPolicy(),
    loadCapabilities(),
    loadDiagnostics(),
    loadWorkspaceStatus(),
    loadSourceRoots(),
    loadDatasets(),
    loadReviews(),
    loadMemoryReviewQueue(),
    loadMemoryBriefing(),
    loadMemoryCards(),
    loadMemoryHealth(),
    loadMemoryUseTraces(),
    loadPendingReviews(),
    loadWorkflows(),
    loadResumableAsks(),
    loadAuditEvents(),
  ]);
  renderHome();
}

async function loadHealth() {
  try {
    state.health = await api("/api/health");
    const status = document.getElementById("api-status");
    status.textContent = t("status.apiOnline");
    status.className = "status-pill ok";
    renderSettings();
  } catch (error) {
    const status = document.getElementById("api-status");
    status.textContent = t("status.apiError");
    status.className = "status-pill error";
    showToast(error.message);
  }
}

async function loadPolicy() {
  try {
    const payload = await api("/api/policy");
    state.policy = payload.governance || null;
    renderPolicy();
    renderSettings();
  } catch (error) {
    state.policy = null;
    renderPolicy();
    showToast(error.message);
  }
}

async function loadCapabilities() {
  try {
    const payload = await api("/api/capabilities");
    state.capabilities = payload.capabilities || null;
    state.capabilitiesError = "";
    renderSettings();
    renderReviews();
    renderCurrentResultSurfaces();
  } catch (error) {
    state.capabilities = null;
    state.capabilitiesError = error.message;
    renderSettings();
    renderReviews();
    renderCurrentResultSurfaces();
    showToast(error.message);
  }
}

async function loadDiagnostics() {
  try {
    const payload = await api("/api/runtime/diagnostics");
    state.diagnostics = payload.diagnostics || null;
    renderDiagnostics();
    renderSettings();
  } catch (error) {
    state.diagnostics = {
      status: "error",
      checks: [{ name: "runtime_diagnostics", status: "error", message: error.message, metadata: {} }],
    };
    renderDiagnostics();
    showToast(error.message);
  }
}

async function loadWorkspaceStatus() {
  try {
    const payload = await api("/api/workspace/status");
    state.workspaceStatus = payload.workspace_status || null;
    renderHome();
    await loadJarvisBriefing({ silent: true });
  } catch (error) {
    state.workspaceStatus = {
      status: "error",
      next_actions: [
        {
          action: "inspect_workspace_status_error",
          label: "Inspect workspace status",
          reason: error.message,
        },
      ],
    };
    renderHome();
    showToast(error.message);
  }
}

async function loadJarvisBriefing(options = {}) {
  state.jarvisLoading = true;
  renderJarvisBar();
  try {
    const payload = await api("/api/jarvis/briefing", { method: "POST", body: {} });
    state.jarvisBriefing = payload.briefing || null;
    state.jarvisError = "";
  } catch (error) {
    state.jarvisBriefing = null;
    state.jarvisError = error.message;
    if (!options.silent) showToast(error.message);
  } finally {
    state.jarvisLoading = false;
    renderJarvisBar();
  }
}

async function loadSourceRoots() {
  try {
    const payload = await api("/api/sources/roots");
    state.sourceRoots = payload.roots || [];
    state.sourceRootError = "";
    if (state.activeSourceRootId && !state.sourceRoots.some((root) => root.root_id === state.activeSourceRootId)) {
      state.activeSourceRootId = "";
    }
    renderSourceRootPickers();
    renderSources();
    renderHome();
  } catch (error) {
    state.sourceRoots = [];
    state.sourceRootError = error.message;
    renderSourceRootPickers();
    renderSources();
    showToast(error.message);
  }
}

async function registerSourceRoot(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = await api("/api/sources/roots", {
    method: "POST",
    body: {
      path: form.get("path"),
      kind: form.get("kind") || "auto",
      permission_mode: form.get("permission_mode") || "read_only",
      label: form.get("label") || "",
    },
  });
  event.currentTarget.reset();
  if (payload.root && payload.root.root_id) {
    state.activeSourceRootId = payload.root.root_id;
  }
  await loadSourceRoots();
  await runSourceAudit(sourceScopeFromRootId(state.activeSourceRootId));
  await loadJarvisBriefing({ silent: true });
  showToast(t("toast.sourceRootRegistered"));
}

async function scanSourceRoot(rootId) {
  const normalized = String(rootId || "").trim();
  if (!normalized) return;
  const payload = await api(`/api/sources/roots/${encodeURIComponent(normalized)}/scan`, {
    method: "POST",
    body: { max_files: 1000 },
  });
  state.sourceScanResults[normalized] = payload.scan || null;
  state.activeSourceRootId = normalized;
  await loadSourceRoots();
  await runSourceAudit(sourceScopeFromRootId(normalized));
  await loadAuditEvents("source.scan");
  await loadJarvisBriefing({ silent: true });
  showToast(t("toast.sourceScanCompleted"));
}

async function runSourceAudit(scopeOverride = undefined) {
  const scope = scopeOverride === undefined ? sourceScopeFromRootId(state.activeSourceRootId) : scopeOverride || {};
  const payload = await api("/api/sources/audits/run", {
    method: "POST",
    body: { scope, limit: 20 },
  });
  state.sourceAudit = payload.audit || null;
  state.sourceAuditScope = scope;
  if (scope && Array.isArray(scope.root_ids) && scope.root_ids.length === 1) {
    state.activeSourceRootId = scope.root_ids[0];
  }
  renderSourceRootPickers();
  renderSources();
  await loadJarvisBriefing({ silent: true });
  showToast(t("toast.sourceAuditCompleted"));
}

async function runSourceAuditJob(runId = "") {
  const path = runId
    ? `/api/sources/audit-jobs/${encodeURIComponent(runId)}/run`
    : "/api/sources/audit-jobs/run-next";
  const payload = await api(path, { method: "POST", body: {} });
  if (payload.source_audit) {
    state.sourceAudit = payload.source_audit;
    state.sourceAuditScope = payload.source_audit.scope || {};
  }
  renderSources();
  await loadWorkspaceStatus();
  await loadAuditEvents("source.audit_job.run");
  showToast(t("toast.sourceAuditJobCompleted"));
}

async function enqueueSourceExtractionJob(rootId) {
  const normalized = String(rootId || "").trim();
  if (!normalized) return;
  const payload = await api("/api/sources/extraction-jobs", {
    method: "POST",
    body: {
      root_id: normalized,
      max_files: 1000,
      extractor: "auto",
    },
  });
  state.sourceExtractionJob = payload.source_extraction_job || null;
  await loadWorkspaceStatus();
  await loadAuditEvents("source.extraction_job.enqueue");
  renderSources();
  showToast(t("toast.sourceExtractionJobQueued"));
}

async function runSourceExtractionJob(runId = "") {
  const path = runId
    ? `/api/sources/extraction-jobs/${encodeURIComponent(runId)}/run`
    : "/api/sources/extraction-jobs/run-next";
  const payload = await api(path, { method: "POST", body: {} });
  state.sourceExtractionJob = payload.source_extraction_job || null;
  if (payload.scan && payload.scan.root && payload.scan.root.root_id) {
    state.sourceScanResults[payload.scan.root.root_id] = payload.scan;
  }
  await loadSourceRoots();
  await loadWorkspaceStatus();
  await loadAuditEvents("source.extraction_job.run");
  showToast(t("toast.sourceExtractionJobCompleted"));
}

async function tickSourceAuditJobs() {
  const payload = await api("/api/sources/audit-jobs/tick", {
    method: "POST",
    body: {},
  });
  await loadWorkspaceStatus();
  await loadAuditEvents("source.audit_job.due");
  showToast(t("toast.sourceAuditJobsActivated"));
  return payload;
}

async function searchSources(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const query = String(form.get("query") || "").trim();
  if (!query) {
    showToast(t("toast.sourceQueryRequired"));
    return;
  }
  const rootId = String(form.get("root_id") || "").trim();
  const payload = await api("/api/sources/search", {
    method: "POST",
    body: {
      query,
      scope: sourceScopeFromRootId(rootId),
      limit: Number(form.get("limit") || 10),
    },
  });
  state.sourceSearchResults = payload.context_packets || [];
  state.sourceSearchCount = payload.count || 0;
  state.sourceSearchError = "";
  const saveQuery = document.getElementById("source-save-query");
  if (saveQuery) saveQuery.value = query;
  const saveRoot = document.getElementById("source-save-root");
  if (saveRoot) saveRoot.value = rootId;
  renderSources();
}

async function saveSourceSearch(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const query = String(form.get("query") || "").trim();
  if (!query) {
    showToast(t("toast.sourceQueryRequired"));
    return;
  }
  const rootId = String(form.get("root_id") || "").trim();
  const payload = await api("/api/sources/saved-searches", {
    method: "POST",
    body: {
      label: form.get("label"),
      query,
      scope: sourceScopeFromRootId(rootId),
      sort: form.get("sort") || "relevance",
    },
  });
  state.sourceSavedSearch = payload.saved_search || null;
  renderSourceTools();
  await loadAuditEvents("source.saved_search.create");
  showToast(t("toast.sourceSavedSearchCreated"));
}

async function handleSourceAnnotation(event) {
  event.preventDefault();
  const submitter = event.submitter;
  const action = submitter ? submitter.value : "";
  if (!state.selectedSourceRef) {
    showToast(t("toast.sourceSelectRequired"));
    return;
  }
  if (action === "tag_propose") {
    await proposeSourceTag(new FormData(event.currentTarget));
    return;
  }
  if (action === "tag_apply") {
    await applySourceTag();
    return;
  }
  if (action === "comment_propose") {
    await proposeSourceComment(new FormData(event.currentTarget));
    return;
  }
  if (action === "comment_apply") {
    await applySourceComment();
  }
}

async function proposeSourceTag(form) {
  const tag = String(form.get("tag") || "").trim();
  if (!tag) {
    showToast("请输入标签。");
    return;
  }
  const payload = await api("/api/sources/tags/proposals", {
    method: "POST",
    body: {
      target_ref: state.selectedSourceRef,
      tag,
      reason: form.get("tag_reason") || "",
      write_target: "sidecar",
    },
  });
  state.sourceTagProposal = payload.proposal || null;
  state.sourceTagApply = null;
  renderSourceTools();
  await loadAuditEvents("source.tag.propose");
  showToast(t("toast.sourceTagProposalCreated"));
}

async function applySourceTag() {
  const proposalId = state.sourceTagProposal && state.sourceTagProposal.proposal_id;
  if (!proposalId) {
    showToast("没有可应用的标签提议。");
    return;
  }
  const payload = await api(`/api/sources/tags/${encodeURIComponent(proposalId)}/apply`, { method: "POST", body: {} });
  state.sourceTagApply = payload.applied || null;
  if (state.sourceTagApply && state.sourceTagApply.proposal) {
    state.sourceTagProposal = state.sourceTagApply.proposal;
  }
  renderSourceTools();
  await loadAuditEvents("source.tag.apply");
  showToast(t("toast.sourceTagApplied"));
}

async function proposeSourceComment(form) {
  const body = String(form.get("comment") || "").trim();
  if (!body) {
    showToast("请输入 Comment。");
    return;
  }
  const payload = await api("/api/sources/comments/proposals", {
    method: "POST",
    body: {
      target_ref: state.selectedSourceRef,
      body,
      reason: form.get("comment_reason") || "",
      write_target: "sidecar",
    },
  });
  state.sourceCommentProposal = payload.proposal || null;
  state.sourceCommentApply = null;
  renderSourceTools();
  await loadAuditEvents("source.comment.propose");
  showToast(t("toast.sourceCommentProposalCreated"));
}

async function applySourceComment() {
  const proposalId = state.sourceCommentProposal && state.sourceCommentProposal.proposal_id;
  if (!proposalId) {
    showToast("没有可应用的 Comment 提议。");
    return;
  }
  const payload = await api(`/api/sources/comments/${encodeURIComponent(proposalId)}/apply`, { method: "POST", body: {} });
  state.sourceCommentApply = payload.applied || null;
  if (state.sourceCommentApply && state.sourceCommentApply.proposal) {
    state.sourceCommentProposal = state.sourceCommentApply.proposal;
  }
  renderSourceTools();
  await loadAuditEvents("source.comment.apply");
  showToast(t("toast.sourceCommentApplied"));
}

function selectSourceForAnnotation(sourceRef, title = "", options = {}) {
  if (!sourceRef) return;
  state.selectedSourceRef = sourceRef;
  state.selectedSourceTitle = title || sourceRef.title || sourceRef.path || "";
  state.sourceTagProposal = null;
  state.sourceTagApply = null;
  state.sourceCommentProposal = null;
  state.sourceCommentApply = null;
  renderSourceTools();
  if (!options.silent) showToast(t("toast.sourceSelected"));
}

function sourceScopeFromRootId(rootId) {
  const normalized = String(rootId || "").trim();
  return normalized ? { root_ids: [normalized] } : {};
}

async function loadDatasets() {
  try {
    const payload = await api("/api/kb/datasets");
    state.datasets = payload.datasets || [];
    renderDatasets();
    renderDatasetPickers();
    renderHome();
  } catch (error) {
    renderList(document.getElementById("datasets-list"), [], t("empty.datasetsUnavailable"));
    showToast(error.message);
  }
}

async function loadReviews() {
  try {
    const status = state.reviewStatus ? `&status=${encodeURIComponent(state.reviewStatus)}` : "";
    const payload = await api(`/api/reviews?limit=50${status}`);
    state.reviewView = payload.reviews || [];
    if (!state.reviewStatus) {
      state.reviews = [];
    }
    state.reviewView.forEach((review) => syncReviewRecord(review, { append: !state.reviewStatus }));
    renderReviews();
    renderHome();
  } catch (error) {
    renderList(document.getElementById("reviews-list"), [], t("empty.reviewsUnavailable"));
    showToast(error.message);
  }
}

async function loadMemoryReviewQueue(options = {}) {
  try {
    const payload = await api("/api/memory/review-queue?review_limit=50&health_limit=20&focus_limit=20");
    state.memoryReviewQueue = payload;
    state.memoryReviewQueueError = "";
    renderMemoryReviewQueue(payload);
    if (options.toast) showToast(t("toast.memoryReviewQueueLoaded"));
  } catch (error) {
    state.memoryReviewQueue = null;
    state.memoryReviewQueueError = error.message;
    renderMemoryReviewQueue();
    if (options.toast) showToast(error.message);
  }
}

async function loadMemoryBriefing(options = {}) {
  try {
    const payload = await api("/api/memory/briefing?card_limit=30&health_limit=20&trace_limit=30");
    state.memoryBriefing = payload;
    state.memoryBriefingError = "";
    renderMemoryBriefing(payload);
    if (options.toast) showToast(t("toast.memoryBriefingLoaded"));
  } catch (error) {
    state.memoryBriefing = null;
    state.memoryBriefingError = error.message;
    renderMemoryBriefing();
    if (options.toast) showToast(error.message);
  }
}

async function loadMemoryCards(options = {}) {
  const params = new URLSearchParams();
  params.set("limit", "50");
  params.set("status", state.memoryCardStatus || "active");
  if (state.memoryCardType) params.set("memory_type", state.memoryCardType);
  if (state.memoryCardQuery) params.set("query", state.memoryCardQuery);
  try {
    const payload = await api(`/api/memory/cards?${params.toString()}`);
    state.memoryCards = payload.cards || [];
    state.memoryCardsError = "";
    renderMemoryCards(payload);
    if (options.toast) showToast(t("toast.memoryCardsLoaded"));
  } catch (error) {
    state.memoryCards = [];
    state.memoryCardsError = error.message;
    renderMemoryCards();
    if (options.toast) showToast(error.message);
  }
}

async function loadMemoryHealth(options = {}) {
  const params = new URLSearchParams();
  params.set("limit", "100");
  if (state.memoryHealthType) params.set("issue_type", state.memoryHealthType);
  try {
    const payload = await api(`/api/memory/health?${params.toString()}`);
    state.memoryHealth = payload;
    state.memoryHealthError = "";
    renderMemoryHealth(payload);
    if (options.toast) showToast(t("toast.memoryHealthLoaded"));
  } catch (error) {
    state.memoryHealth = null;
    state.memoryHealthError = error.message;
    renderMemoryHealth();
    if (options.toast) showToast(error.message);
  }
}

async function loadMemoryUseTraces(options = {}) {
  const params = new URLSearchParams();
  params.set("limit", "50");
  if (state.memoryUseTraceMemoryId) params.set("memory_id", state.memoryUseTraceMemoryId);
  if (state.memoryUseTraceQuery) params.set("query", state.memoryUseTraceQuery);
  try {
    const payload = await api(`/api/memory/use-traces?${params.toString()}`);
    state.memoryUseTraces = payload.traces || [];
    state.memoryUseTraceError = "";
    state.memoryWhyUsed = null;
    state.memoryTimeline = null;
    state.memoryTimelineError = "";
    renderMemoryUseTraces(payload);
    if (options.toast) showToast(t("toast.memoryUseTraceLoaded"));
  } catch (error) {
    state.memoryUseTraces = [];
    state.memoryUseTraceError = error.message;
    state.memoryTimeline = null;
    renderMemoryUseTraces();
    if (options.toast) showToast(error.message);
  }
}

async function explainMemoryWhyUsed(memoryId) {
  const selected = String(memoryId || "").trim();
  if (!selected) return;
  try {
    const payload = await api(`/api/memory/${encodeURIComponent(selected)}/why-used?limit=20`);
    state.memoryWhyUsed = payload;
    state.memoryUseTraceMemoryId = selected;
    state.memoryUseTraceQuery = "";
    state.memoryUseTraces = payload.traces || [];
    state.memoryUseTraceError = "";
    state.memoryTimeline = null;
    state.memoryTimelineError = "";
    renderMemoryUseTraces(payload);
  } catch (error) {
    state.memoryUseTraceError = error.message;
    renderMemoryUseTraces();
    showToast(error.message);
  }
}

async function inspectMemoryUseTrace(memoryId) {
  state.memoryUseTraceMemoryId = String(memoryId || "").trim();
  state.memoryUseTraceQuery = "";
  state.memoryWhyUsed = null;
  state.memoryTimeline = null;
  state.memoryTimelineError = "";
  await loadMemoryUseTraces({ toast: true });
}

async function loadMemoryTimelineFromInput() {
  const input = document.getElementById("memory-use-trace-memory-id");
  await openMemoryTimeline(input ? input.value : "");
}

async function openMemoryTimeline(memoryId) {
  const selected = String(memoryId || "").trim();
  if (!selected) {
    showToast("需要记忆 ID。");
    return;
  }
  state.memoryTimelineMemoryId = selected;
  state.memoryUseTraceMemoryId = selected;
  state.memoryUseTraceQuery = "";
  try {
    const payload = await api(`/api/memory/${encodeURIComponent(selected)}/timeline?limit=50`);
    state.memoryTimeline = payload;
    state.memoryTimelineError = "";
    state.memoryWhyUsed = null;
    state.memoryUseTraces = [];
    state.memoryUseTraceError = "";
    renderMemoryUseTraces(payload);
    openView("memory");
    showToast(t("toast.memoryTimelineLoaded"));
  } catch (error) {
    state.memoryTimeline = null;
    state.memoryTimelineError = error.message;
    state.memoryUseTraceError = "";
    renderMemoryUseTraces();
    openView("memory");
    showToast(error.message);
  }
}

async function inspectMemoryCard(memoryId) {
  state.memoryCardQuery = String(memoryId || "").trim();
  state.memoryCardStatus = "all";
  await loadMemoryCards({ toast: true });
}

async function loadPendingReviews() {
  try {
    const payload = await api("/api/reviews?status=pending&limit=50");
    state.pendingReviews = payload.reviews || [];
    state.pendingReviews.forEach(syncReviewRecord);
    renderHome();
  } catch (error) {
    state.pendingReviews = [];
    renderHome();
    showToast(error.message);
  }
}

async function loadWorkflows() {
  try {
    const payload = await api("/api/workflows?limit=20");
    state.workflows = payload.workflows || [];
    renderWorkflowList();
  } catch (error) {
    renderList(document.getElementById("workflow-list"), [], t("empty.runsUnavailable"));
    showToast(error.message);
  }
}

async function loadResumableAsks() {
  try {
    const payload = await api("/api/workflows/resumable-asks?limit=20");
    state.resumableAsks = payload.resumable_asks || [];
    if (state.currentAskResult && state.currentAskResult.status === "not_ready") {
      renderAskResult(state.currentAskResult);
    }
    renderHome();
    renderWorkflowList();
  } catch (error) {
    state.resumableAsks = [];
    renderHome();
    showToast(error.message);
  }
}

async function loadAuditEvents(actionOverride = undefined) {
  try {
    if (typeof actionOverride === "string") {
      setAuditActionFilter(actionOverride);
    }
    const action = state.auditAction ? `&action=${encodeURIComponent(state.auditAction)}` : "";
    const payload = await api(`/api/audit?limit=50${action}`);
    state.auditEvents = payload.events || [];
    renderAuditEvents();
  } catch (error) {
    renderList(document.getElementById("audit-list"), [], t("empty.auditUnavailable"));
    showToast(error.message);
  }
}

async function loadDocuments(datasetId, options = {}) {
  const normalizedId = String(datasetId || "").trim();
  if (!normalizedId) {
    showToast(t("toast.datasetRequired"));
    return [];
  }
  state.activeDocumentDatasetId = normalizedId;
  try {
    const [documentsResult, readinessResult] = await Promise.allSettled([
      api(`/api/kb/datasets/${encodeURIComponent(normalizedId)}/documents`),
      api(`/api/kb/datasets/${encodeURIComponent(normalizedId)}/readiness`),
    ]);
    if (documentsResult.status === "rejected") {
      throw documentsResult.reason;
    }
    let documents = documentsResult.value.documents || [];
    let readiness = null;
    if (readinessResult.status === "fulfilled") {
      readiness = readinessResult.value.readiness || null;
      state.readinessByDataset[normalizedId] = readiness;
      documents = mergeReadinessDocuments(documents, readiness);
    }
    state.activeDocuments = documents;
    renderDocuments(documents);
    renderIngestionStatus(normalizedId, documents, readiness || state.readinessByDataset[normalizedId]);
    return documents;
  } catch (error) {
    if (!options.silent) showToast(error.message);
    throw error;
  }
}

function renderHome() {
  const pendingReviews = Array.isArray(state.pendingReviews)
    ? state.pendingReviews
    : state.reviews.filter((item) => item.status === "pending");
  document.getElementById("metric-datasets").textContent = String(state.datasets.length);
  document.getElementById("metric-reviews").textContent = String(pendingReviews.length);
  document.getElementById("metric-run").textContent = state.lastRunId ? shortId(state.lastRunId) : t("status.none");
  renderList(
    document.getElementById("home-next-actions"),
    ((state.workspaceStatus && state.workspaceStatus.next_actions) || []).slice(0, 5),
    t("empty.noNextActions"),
    workspaceActionCard,
  );
  renderList(document.getElementById("home-datasets"), state.datasets.slice(0, 4), t("empty.datasets"), datasetCard);
  renderList(
    document.getElementById("home-reviews"),
    pendingReviews.slice(0, 4),
    t("empty.noReviews"),
    reviewCard,
  );
  renderList(
    document.getElementById("home-resumable-asks"),
    state.resumableAsks.slice(0, 4),
    t("empty.noResumableAsks"),
    resumableAskCard,
  );
  renderJarvisBar();
}

function renderJarvisBar() {
  const container = document.getElementById("jarvis-bar");
  if (!container) return;
  container.classList.toggle("empty-list", !state.jarvisBriefing && !state.jarvisLoading && !state.jarvisError);
  container.replaceChildren();
  if (state.jarvisLoading && !state.jarvisBriefing) {
    container.textContent = "Jarvis briefing 正在加载。";
    return;
  }
  if (state.jarvisError) {
    container.append(
      el("div", { className: "jarvis-header" }, [
        el("div", {}, [
          el("h2", {}, t("heading.jarvisBar")),
          el("p", {}, state.jarvisError),
        ]),
        el("button", { className: "secondary-button", type: "button", onclick: () => loadJarvisBriefing() }, t("button.refreshJarvis")),
      ]),
    );
    return;
  }
  const briefing = state.jarvisBriefing;
  if (!briefing) {
    container.textContent = t("empty.noJarvisBriefing");
    return;
  }
  const summary = briefing.summary || {};
  const priorities = (briefing.priorities || []).slice(0, 4);
  const actions = (briefing.next_actions || []).slice(0, 3);
  container.append(
    el("div", { className: "jarvis-header" }, [
      el("div", {}, [
        el("p", { className: "eyebrow" }, "Hermes briefing"),
        el("h2", {}, t("heading.jarvisBar")),
      ]),
      el("div", { className: "meta-row" }, [
        el("span", { className: `tag ${statusClass(briefing.status)}` }, readableName(briefing.status || "unknown")),
        el("span", { className: "tag" }, `sources ${summary.source_root_count || 0}`),
        el("button", { className: "secondary-button", type: "button", onclick: () => loadJarvisBriefing() }, t("button.refreshJarvis")),
      ]),
    ]),
  );
  container.append(
    el("div", { className: "jarvis-stats" }, [
      jarvisStat("重复组", summary.duplicate_group_count || 0),
      jarvisStat("断链", summary.unresolved_link_count || 0),
      jarvisStat("孤立笔记", summary.unlinked_markdown_count || 0),
      jarvisStat("待审核", summary.pending_review_count || 0),
    ]),
  );
  if (priorities.length) {
    container.append(el("div", { className: "jarvis-priorities" }, priorities.map(jarvisPriorityRow)));
  }
  if (actions.length) {
    container.append(el("div", { className: "jarvis-actions" }, actions.map(jarvisActionRow)));
  }
}

function jarvisStat(label, value) {
  return el("div", { className: "jarvis-stat" }, [
    el("span", {}, label),
    el("strong", {}, String(value)),
  ]);
}

function jarvisPriorityRow(priority) {
  return el("div", { className: "jarvis-priority-row" }, [
    el("span", { className: `tag ${prioritySeverityClass(priority.severity)}` }, readableName(priority.severity || "info")),
    el("div", {}, [
      el("strong", {}, priority.title || readableName(priority.code || "priority")),
      el("p", {}, priority.reason || ""),
    ]),
  ]);
}

function jarvisActionRow(action) {
  return el("div", { className: "jarvis-action-row" }, [
    el("div", {}, [
      el("strong", {}, action.label || readableName(action.action || "action")),
      el("p", {}, action.reason || action.tool || action.api || ""),
    ]),
    el("button", { className: workspaceActionButtonClass(action), type: "button", onclick: () => openWorkspaceAction(action) }, workspaceActionButtonLabel(action)),
  ]);
}

function prioritySeverityClass(severity) {
  if (severity === "critical") return "failed";
  if (severity === "warning" || severity === "setup") return "pending";
  return "ready";
}

function workspaceActionCard(action) {
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("strong", {}, action.label || readableName(action.action || "action")),
      el("span", { className: `tag ${statusClass(action.action || "")}` }, readableName(action.action || "")),
    ]),
    el("div", { className: "meta-row" }, [
      action.tool ? el("span", { className: "tag" }, action.tool) : null,
      action.api ? el("span", { className: "tag" }, action.api) : null,
      action.view ? el("span", { className: "tag" }, action.view) : null,
    ]),
    el("p", {}, action.reason || ""),
    el("div", { className: "card-actions" }, [
      el(
        "button",
        { className: workspaceActionButtonClass(action), type: "button", onclick: () => openWorkspaceAction(action) },
        workspaceActionButtonLabel(action),
      ),
    ]),
  ]);
}

function workspaceActionButtonLabel(action) {
  const labels = {
    apply_accepted_memory: t("button.apply"),
    inspect_unsupported_memory_operation: t("button.inspect"),
    parse_documents: t("button.parse"),
    resume_blocked_ask: t("button.resume"),
    resume_ingest_loop: t("button.resumeLoop"),
    review_pending_durable_knowledge: t("button.review"),
    review_duplicates: t("button.inspect"),
    inspect_unresolved_links: t("button.inspect"),
    inspect_unlinked_notes: t("button.source"),
    create_source_route_memory: t("button.review"),
    create_source_memory_candidates_from_audit: t("button.review"),
    propose_obsidian_moc: t("button.review"),
    register_source_root: t("button.upload"),
    scan_source_root: t("button.track"),
    activate_due_source_audit_jobs: t("button.track"),
    run_source_audit_job: t("button.audit"),
    run_source_extraction_job: t("button.scan"),
    run_file_to_work_product_loop: t("button.start"),
    run_agentic_question: t("button.ask"),
    track_ingestion_status: t("button.track"),
    create_or_upload_knowledge_base: t("button.upload"),
    upload_documents: t("button.upload"),
    wait_for_ingestion: t("button.track"),
    wait_for_resumable_ask: t("button.track"),
  };
  return labels[action.action] || t("button.open");
}

function workspaceActionButtonClass(action) {
  return [
    "apply_accepted_memory",
    "parse_documents",
    "activate_due_source_audit_jobs",
    "run_source_audit_job",
    "run_source_extraction_job",
    "resume_blocked_ask",
    "resume_ingest_loop",
    "run_file_to_work_product_loop",
  ].includes(action.action)
    ? "primary-button"
    : "secondary-button";
}

async function openWorkspaceAction(action) {
  const params = action.params || {};
  if (action.action === "run_file_to_work_product_loop") {
    prepareIngestLoopForm(params);
    openView("kb");
    showToast(t("toast.prepareLoop"));
    return;
  }
  if (action.action === "run_agentic_question") {
    setAskDatasetIds(params.dataset_ids || []);
    setAskDocumentIds(params.document_ids || []);
    renderAskScope();
    openView("ask");
    await checkAskReadiness({ silent: true });
    return;
  }
  if (action.action === "resume_blocked_ask" && params.run_id) {
    await resumeBlockedRun(params.run_id);
    return;
  }
  if (action.action === "resume_ingest_loop" && params.run_id) {
    await resumeIngestLoopRun(params.run_id, params.export_format || "");
    return;
  }
  if (action.action === "wait_for_resumable_ask" && params.run_id) {
    await openBlockedAskRun(params.run_id, { track: true });
    return;
  }
  if (action.action === "apply_accepted_memory" && params.review_id) {
    await openReview(params.review_id);
    await applyMemory(params.review_id);
    return;
  }
  if (action.action === "inspect_unsupported_memory_operation" && params.review_id) {
    await openReview(params.review_id);
    return;
  }
  if (action.action === "review_pending_durable_knowledge" && params.review_id) {
    await openReview(params.review_id);
    return;
  }
  if (action.action === "register_source_root") {
    openView("sources");
    showToast(action.reason || "请注册一个本地文件夹或 Obsidian vault。");
    return;
  }
  if (action.action === "scan_source_root" && params.root_id) {
    openView("sources");
    await scanSourceRoot(params.root_id);
    return;
  }
  if (action.action === "review_duplicates" || action.action === "inspect_unresolved_links") {
    openView("sources");
    await runSourceAudit(params.scope || {});
    return;
  }
  if (action.action === "run_source_audit_job") {
    openView("sources");
    await runSourceAuditJob(params.run_id || "");
    return;
  }
  if (action.action === "run_source_extraction_job") {
    openView("sources");
    await runSourceExtractionJob(params.run_id || "");
    return;
  }
  if (action.action === "activate_due_source_audit_jobs") {
    openView("sources");
    await tickSourceAuditJobs();
    return;
  }
  if (action.action === "inspect_unlinked_notes") {
    openView("sources");
    if (params.source_ref) {
      state.sourceSearchResults = [
        {
          title: params.source_ref.title || params.source_ref.path || "source",
          text: action.reason || "",
          source_ref: params.source_ref,
          score: 1,
          metadata: params.source_ref.metadata || {},
        },
      ];
      state.sourceSearchCount = 1;
      renderSources();
    }
    return;
  }
  if (action.action === "create_source_route_memory") {
    await createSourceMemoryReview(params);
    return;
  }
  if (action.action === "create_source_memory_candidates_from_audit") {
    await createSourceMemoryCandidatesFromAudit(params);
    return;
  }
  if (action.action === "propose_obsidian_moc") {
    await proposeObsidianMoc(params);
    return;
  }
  if (action.action === "upload_documents" || action.action === "create_or_upload_knowledge_base") {
    setUploadDataset(params.dataset_ids || []);
    prepareIngestLoopForm(params);
    openView("kb");
    return;
  }
  if (action.action === "check_dataset_access" || action.action === "configure_embedding_provider") {
    openView("settings");
    return;
  }
  if (
    [
      "wait_for_ingestion",
      "track_ingestion_status",
      "parse_documents",
      "inspect_failure",
      "inspect_cancellation",
      "check_provider_status",
    ].includes(action.action)
  ) {
    const datasetId = params.dataset_id || (params.dataset_ids || [])[0] || state.activeDocumentDatasetId;
    if (datasetId) {
      openView("kb");
      await loadDocuments(datasetId, { silent: true });
      if (action.action === "parse_documents") {
        await parseDatasetDocuments(datasetId, params.document_ids || []);
        return;
      }
      if (action.action === "wait_for_ingestion" || action.action === "track_ingestion_status") startIngestionPolling(datasetId);
    }
    openView("kb");
    return;
  }
  openView(action.view || "home");
}

function prepareIngestLoopForm(params = {}) {
  const form = document.getElementById("upload-form");
  if (!form) return;
  const datasetId = form.querySelector('input[name="dataset_id"]');
  if (datasetId && !(params.dataset_ids || []).length) datasetId.value = "";
  const picker = document.getElementById("upload-dataset-picker");
  if (picker && !(params.dataset_ids || []).length) picker.value = "";
  const parse = form.querySelector('input[name="parse"]');
  if (parse && Object.prototype.hasOwnProperty.call(params, "parse")) parse.checked = Boolean(params.parse);
  const wait = form.querySelector('input[name="wait"]');
  if (wait && Object.prototype.hasOwnProperty.call(params, "wait_ready")) wait.checked = Boolean(params.wait_ready);
  const proposal = form.querySelector('[name="loop_proposal_kind"]');
  if (proposal && params.proposal_kind) proposal.value = params.proposal_kind;
  const format = form.querySelector('[name="loop_export_format"]');
  if (format && params.export_format) format.value = params.export_format;
  const question = form.querySelector('[name="loop_question"]');
  if (question && params.question) question.value = params.question;
  const fileInput = form.querySelector('input[name="file"]');
  if (fileInput) fileInput.focus();
}

function setUploadDataset(datasetIds) {
  const values = Array.isArray(datasetIds) ? datasetIds : [datasetIds];
  const datasetId = String((values || [])[0] || "").trim();
  if (!datasetId) return false;
  const field = document.querySelector('#upload-form input[name="dataset_id"]');
  if (field) field.value = datasetId;
  const picker = document.getElementById("upload-dataset-picker");
  if (picker && Array.from(picker.options).some((option) => option.value === datasetId)) {
    picker.value = datasetId;
  }
  const nameField = document.querySelector('#upload-form input[name="dataset_name"]');
  if (nameField) nameField.value = "";
  return true;
}

function openDatasetUpload(datasetId) {
  if (!setUploadDataset(datasetId)) {
    showToast(t("toast.datasetRequired"));
    return;
  }
  openView("kb");
  showToast(t("toast.uploadTargetSelected"));
}

async function openDatasetStatus(datasetId) {
  const normalized = String(datasetId || "").trim();
  if (!normalized) {
    showToast(t("toast.datasetRequired"));
    return;
  }
  const field = document.querySelector('#document-status-form input[name="dataset_id"]');
  if (field) field.value = normalized;
  openView("kb");
  await loadDocuments(normalized);
}

function openView(view) {
  const button = document.querySelector(`.nav-item[data-view="${view}"]`);
  if (button) button.click();
}

function renderSettings() {
  const settings = document.getElementById("runtime-settings");
  settings.replaceChildren();
  const providers = (state.health && state.health.providers) || {};
  const workspace = (state.health && state.health.workspace) || {};
  const governance = state.policy || (state.health && state.health.governance) || {};
  const diagnostics = state.diagnostics || {};
  const memoryCaps = memoryCapabilities();
  const capabilityStatus = state.capabilities
    ? t("label.loaded")
    : state.capabilitiesError
      ? `error: ${state.capabilitiesError}`
      : t("label.notChecked");
  [
    [t("label.productApi"), state.health ? state.health.product_api : ""],
    [t("label.capabilityContract"), capabilityStatus],
    [t("label.runtimeStatus"), diagnostics.status || t("label.notChecked")],
    [t("label.workspace"), workspace.workspace_id || t("label.default")],
    [t("label.tenant"), workspace.tenant_id || t("label.notConfigured")],
    [t("label.memoryNamespace"), workspace.memory_namespace || t("label.default")],
    [t("label.retrieval"), providers.retrieval || t("label.notConfigured")],
    [t("label.knowledgeBase"), providers.kb || t("label.notConfigured")],
    [t("label.memory"), providers.memory || t("label.notConfigured")],
    [t("label.developmentFake"), providers.dev_fake ? t("label.enabled") : t("label.disabled")],
    [t("label.durableMemoryPolicy"), governance.durable_memory || "manual_review"],
    [t("label.memoryApply"), capabilityLabel(memoryCaps, "apply")],
    [t("label.memoryUpdate"), capabilityLabel(memoryCaps, "update")],
    [t("label.memoryDelete"), capabilityLabel(memoryCaps, "delete")],
  ].forEach(([key, value]) => {
    settings.append(el("dt", {}, key), el("dd", {}, value));
  });
  renderPolicy();
  renderComponentCheck();
  renderProductEval();
  renderRetrievalProbe();
  renderMemoryProbe();
  renderClosedLoopProbe();
}

function memoryCapabilities() {
  if (state.capabilities && state.capabilities.memory && state.capabilities.memory.operations) return state.capabilities.memory;
  return { operations: {} };
}

function memoryCapability(operation) {
  return (memoryCapabilities().operations || {})[operation] || null;
}

function memoryOperationSupported(operation) {
  const capability = memoryCapability(operation);
  return Boolean(capability && capability.supported === true);
}

function memoryOperationForProposalKind(kind) {
  return {
    memory_patch: "apply",
    memory_update: "update",
    memory_delete: "delete",
  }[kind] || "";
}

function memoryCapabilityReason(operation) {
  const capability = memoryCapability(operation);
  if (capability && capability.reason) return capability.reason;
  if (!state.capabilities && state.capabilitiesError) return state.capabilitiesError;
  if (!state.capabilities) return "能力契约尚未加载。";
  return `${readableName(operation)} capability is not reported.`;
}

function capabilityLabel(capabilities, operation) {
  const capability = (capabilities.operations || {})[operation];
  if (!capability) return t("label.notReported");
  return capability.supported === false
    ? `${t("label.unsupported")}${capability.reason ? `: ${capability.reason}` : ""}`
    : t("label.supported");
}

function renderPolicy() {
  const settings = document.getElementById("policy-settings");
  if (!settings) return;
  settings.replaceChildren();
  const policy = state.policy || (state.health && state.health.governance) || {};
  const actions = policy.actions || {};
  [
    [t("label.durableMemory"), policy.durable_memory || "manual_review"],
    [t("label.durableProposalKinds"), (policy.durable_proposal_kinds || []).join(", ")],
    [t("label.availableModes"), (policy.durable_modes || []).join(", ")],
    [t("label.transientResults"), policy.transient_results || "skip"],
    [t("label.memoryPatchAction"), actions.memory_patch || policy.durable_memory || "manual_review"],
    [t("label.memoryUpdateAction"), actions.memory_update || policy.durable_memory || "manual_review"],
    [t("label.memoryDeleteAction"), actions.memory_delete || policy.durable_memory || "manual_review"],
  ].forEach(([key, value]) => {
    settings.append(el("dt", {}, key), el("dd", {}, value || t("label.notConfigured")));
  });
}

function renderDiagnostics() {
  const container = document.getElementById("runtime-diagnostics");
  const status = document.getElementById("diagnostics-status");
  if (!container || !status) return;
  const diagnostics = state.diagnostics || {};
  const checks = diagnostics.checks || [];
  status.textContent = diagnostics.status || t("label.notChecked");
  status.className = `tag ${statusClass(diagnostics.status || "pending")}`;
  renderList(container, checks, t("empty.noDiagnostics"), diagnosticCard);
}

function renderProbeDatasetPicker() {
  const picker = document.getElementById("probe-dataset-picker");
  if (!picker) return;
  const current = picker.value;
  picker.replaceChildren();
  if (!state.datasets.length) {
    picker.append(el("option", { value: "" }, t("empty.noDatasetsOption")));
    picker.disabled = true;
    return;
  }
  picker.disabled = false;
  state.datasets.forEach((dataset) => {
    picker.append(
      el(
        "option",
        { value: dataset.dataset_id || "" },
        `${dataset.name || dataset.dataset_id} (${shortId(dataset.dataset_id || "")})`,
      ),
    );
  });
  if (current && state.datasets.some((dataset) => dataset.dataset_id === current)) {
    picker.value = current;
  }
}

function renderUploadDatasetPicker() {
  const picker = document.getElementById("upload-dataset-picker");
  if (!picker) return;
  const field = document.querySelector('#upload-form input[name="dataset_id"]');
  const current = (field && field.value) || picker.value || "";
  picker.replaceChildren();
  if (!state.datasets.length) {
    picker.append(el("option", { value: "" }, t("empty.noDatasetsOption")));
    picker.disabled = true;
    return;
  }
  picker.disabled = false;
  state.datasets.forEach((dataset) => {
    picker.append(
      el(
        "option",
        { value: dataset.dataset_id || "" },
        `${dataset.name || dataset.dataset_id} (${shortId(dataset.dataset_id || "")})`,
      ),
    );
  });
  if (current && state.datasets.some((dataset) => dataset.dataset_id === current)) {
    picker.value = current;
  }
}

function renderDatasetPickers() {
  renderUploadDatasetPicker();
  renderAskDatasetPicker();
  renderProbeDatasetPicker();
  renderAskScope();
}

function setUploadDatasetFromPicker() {
  const picker = document.getElementById("upload-dataset-picker");
  const datasetId = String((picker && picker.value) || "").trim();
  if (!datasetId) {
    showToast(t("toast.selectKnowledgeBase"));
    return;
  }
  setUploadDataset(datasetId);
  showToast(t("toast.uploadTargetSelected"));
}

async function runRetrievalProbe() {
  const picker = document.getElementById("probe-dataset-picker");
  const question = document.getElementById("probe-question");
  const datasetId = String((picker && picker.value) || "").trim();
  if (!datasetId) {
    showToast(t("toast.selectDataset"));
    return;
  }
  const payload = await api("/api/runtime/retrieval-probe", {
    method: "POST",
    body: {
      question: question && question.value ? question.value : "PSKA retrieval probe",
      dataset_ids: [datasetId],
      limit: 1,
    },
  });
  state.retrievalProbe = payload.probe || null;
  renderRetrievalProbe();
  await loadAuditEvents("retrieval.probe");
  showToast(t("toast.retrievalProbeRecorded"));
}

async function runIngestLoopFromUploadForm() {
  const formEl = document.getElementById("upload-form");
  const form = new FormData(formEl);
  const payload = new FormData();
  const fileCount = appendUploadFiles(form, payload);
  if (!fileCount) {
    showToast(t("toast.selectFiles"));
    return;
  }
  payload.append("dataset_id", form.get("dataset_id") || "");
  payload.append("dataset_name", form.get("dataset_name") || "");
  payload.append("embedding_model", form.get("embedding_model") || "");
  payload.append("parse", form.get("parse") ? "true" : "false");
  payload.append("wait_ready", form.get("wait") ? "true" : "false");
  payload.append("question", form.get("loop_question") || "Summarize the uploaded documents with sources.");
  payload.append("export_format", form.get("loop_export_format") || "markdown");
  appendIngestLoopControls(form, payload);
  const payloadResult = await api("/api/ingest-loop", { method: "POST", formData: payload });
  const result = payloadResult.ingest_loop || {};
  const datasetId = ingestDatasetId(result.ingest || result);
  formEl.reset();
  if (datasetId) {
    setUploadDataset(datasetId);
    const documents = await loadDocuments(datasetId, { silent: true });
    renderIngestResult(result.ingest || { dataset: result.dataset, documents: result.documents || documents }, result.readiness);
  }
  await loadDatasets();
  if (result.status === "not_ready" && result.run && result.run.run_id) {
    if (datasetId && result.readiness && result.readiness.status === "processing") {
      startIngestionPolling(datasetId);
    }
    await applyAskResult(result, { toast: result.message || t("toast.ingestLoopWaiting") });
    document.querySelector('.nav-item[data-view="ask"]').click();
    return;
  }
  await loadWorkflows();
  if (result.review) {
    syncReviewRecord(result.review);
    await loadReviews();
    await loadPendingReviews();
  }
  if (result.review && result.memory_apply) {
    syncMemoryApply(result.review.review_id, result.memory_apply);
  }
  await loadWorkspaceStatus();
  await loadAuditEvents(auditActionForIngestLoop(result));
  if (result.status === "ok" && result.run_id) {
    openLoopWorkProduct(result);
    showToast(t("toast.ingestLoopCompleted"));
    return;
  }
  if (datasetId && result.readiness && result.readiness.status === "processing") {
    startIngestionPolling(datasetId);
  }
  showToast(result.message || t("toast.ingestLoopIncomplete"));
}

function appendUploadFiles(form, payload) {
  let count = 0;
  for (const file of form.getAll("file")) {
    if (file && file.name) {
      payload.append("file", file);
      count += 1;
    }
  }
  return count;
}

function appendIngestLoopControls(form, payload) {
  payload.append("limit", form.get("loop_limit") || "5");
  payload.append("max_iterations", form.get("loop_max_iterations") || "2");
  payload.append("min_context_packets", form.get("loop_min_context_packets") || "1");
  payload.append("source_inspection_limit", form.get("loop_source_inspection_limit") || "3");
  payload.append("proposal_kind", form.get("loop_proposal_kind") || "writing_brief");
  payload.append("retrieval_queries", form.get("loop_retrieval_queries") || "");
  payload.append("use_kg", form.get("loop_use_kg") ? "true" : "false");
  if (form.get("loop_create_review")) {
    payload.append("create_review", "true");
  }
}

function openLoopWorkProduct(result) {
  const exported = result.export;
  const artifact = exported && typeof exported === "object" ? exported : result.artifact || {};
  const run = result.run || artifact.run || (result.artifact && result.artifact.run) || { run_id: result.run_id };
  state.lastRunId = result.run_id || state.lastRunId;
  state.currentBrief = {
    run,
    artifact,
    proposal: result.proposal || artifact.latest_proposal || null,
    review: result.review || null,
    review_decision: result.review_decision || null,
    memory_apply: result.memory_apply || null,
    memory_facts: result.memory_facts || artifact.memory_facts || [],
    memory_attribution: result.memory_attribution || artifact.memory_attribution || null,
    memory_suggestions: result.memory_suggestions || artifact.memory_suggestions || null,
    brief: typeof exported === "string" ? exported : JSON.stringify(exported || artifact, null, 2),
    status: result.ask_status || result.status || "ready",
  };
  renderWriting();
  document.querySelector('.nav-item[data-view="writing"]').click();
}

function auditActionForIngestLoop(result) {
  if (!result || result.status !== "ok") return "kb.ingest";
  if (result.memory_apply) return memoryApplyAction(result.memory_apply);
  if (result.review) return "review.create";
  return "workflow.export";
}

async function runComponentCheck() {
  const picker = document.getElementById("probe-dataset-picker");
  const question = document.getElementById("probe-question");
  const datasetId = String((picker && picker.value) || "").trim();
  const payload = await api("/api/runtime/component-check", {
    method: "POST",
    body: {
      question: question && question.value ? question.value : "PSKA component check",
      dataset_ids: datasetId ? [datasetId] : [],
      limit: 3,
      retrieval_limit: 1,
      source_inspection_limit: 1,
      export_format: "json",
      require_memory: true,
      run_closed_loop: true,
    },
  });
  state.componentCheck = payload.component_check || null;
  if (state.componentCheck) {
    state.retrievalProbe = state.componentCheck.retrieval_probe || state.retrievalProbe;
    state.memoryProbe = state.componentCheck.memory_probe || state.memoryProbe;
    state.closedLoopProbe = state.componentCheck.closed_loop_probe || state.closedLoopProbe;
  }
  renderComponentCheck();
  renderRetrievalProbe();
  renderMemoryProbe();
  renderClosedLoopProbe();
  await loadAuditEvents(auditActionForComponentCheck(state.componentCheck));
  showToast(t("toast.componentCheckRecorded"));
}

async function runProductEval() {
  const payload = await api("/api/runtime/eval", {
    method: "POST",
    body: { suite: "product_acceptance" },
  });
  state.productEval = payload.eval || null;
  renderProductEval();
  await loadAuditEvents(auditActionForEval(state.productEval));
  showToast(t("toast.productEvalCompleted"));
}

async function runMemoryProbe() {
  const query = document.getElementById("memory-probe-query");
  const payload = await api("/api/runtime/memory-probe", {
    method: "POST",
    body: {
      query: query && query.value ? query.value : "PSKA memory probe",
      limit: 1,
      require_live: true,
    },
  });
  state.memoryProbe = payload.probe || null;
  renderMemoryProbe();
  await loadAuditEvents("memory.probe");
  showToast(t("toast.memoryProbeRecorded"));
}

async function runClosedLoopProbe() {
  const picker = document.getElementById("probe-dataset-picker");
  const question = document.getElementById("probe-question");
  const datasetId = String((picker && picker.value) || "").trim();
  if (!datasetId) {
    showToast(t("toast.selectDataset"));
    return;
  }
  const payload = await api("/api/runtime/closed-loop-probe", {
    method: "POST",
    body: {
      question: question && question.value ? question.value : "PSKA live closed-loop probe",
      dataset_ids: [datasetId],
      limit: 3,
      source_inspection_limit: 1,
      export_format: "json",
    },
  });
  state.closedLoopProbe = payload.probe || null;
  renderClosedLoopProbe();
  await loadAuditEvents("closed_loop.probe");
  showToast(t("toast.closedLoopProbeRecorded"));
}

function renderComponentCheck() {
  const container = document.getElementById("component-check-result");
  if (!container) return;
  container.replaceChildren();
  if (!state.componentCheck) {
    container.classList.add("empty-list");
    container.textContent = t("empty.noComponentCheck");
    return;
  }
  container.classList.remove("empty-list");
  container.append(componentCheckCard(state.componentCheck));
}

function renderProductEval() {
  const container = document.getElementById("product-eval-result");
  if (!container) return;
  container.replaceChildren();
  if (!state.productEval) {
    container.classList.add("empty-list");
    container.textContent = t("empty.noProductEval");
    return;
  }
  container.classList.remove("empty-list");
  container.append(evalResultCard(state.productEval));
}

function renderRetrievalProbe() {
  const container = document.getElementById("retrieval-probe-result");
  if (!container) return;
  container.replaceChildren();
  if (!state.retrievalProbe) {
    container.classList.add("empty-list");
    container.textContent = t("empty.noRetrievalProbe");
    return;
  }
  container.classList.remove("empty-list");
  container.append(retrievalProbeCard(state.retrievalProbe));
}

function renderMemoryProbe() {
  const container = document.getElementById("memory-probe-result");
  if (!container) return;
  container.replaceChildren();
  if (!state.memoryProbe) {
    container.classList.add("empty-list");
    container.textContent = t("empty.noMemoryProbe");
    return;
  }
  container.classList.remove("empty-list");
  container.append(memoryProbeCard(state.memoryProbe));
}

function renderClosedLoopProbe() {
  const container = document.getElementById("closed-loop-probe-result");
  if (!container) return;
  container.replaceChildren();
  if (!state.closedLoopProbe) {
    container.classList.add("empty-list");
    container.textContent = t("empty.noClosedLoopProbe");
    return;
  }
  container.classList.remove("empty-list");
  container.append(closedLoopProbeCard(state.closedLoopProbe));
}

function renderDatasets() {
  renderList(document.getElementById("datasets-list"), state.datasets, t("empty.datasets"), datasetCard);
}

function renderSources() {
  const rootsList = document.getElementById("source-roots-list");
  if (!rootsList) return;
  if (state.sourceRootError) {
    renderList(rootsList, [], t("empty.sourcesUnavailable"));
  } else {
    renderList(rootsList, state.sourceRoots, t("empty.sources"), sourceRootCard);
  }

  const searchStatus = document.getElementById("source-search-status");
  const searchText =
    state.sourceSearchCount === null
      ? "未搜索"
      : state.sourceSearchError
        ? "搜索失败"
        : `命中 ${state.sourceSearchCount}`;
  searchStatus.textContent = searchText;
  searchStatus.className = `tag ${state.sourceSearchError ? "failed" : state.sourceSearchCount === null ? "" : "ready"}`;
  renderList(
    document.getElementById("source-search-results"),
    state.sourceSearchResults,
    state.sourceSearchCount === null ? "尚未搜索资料源。" : t("empty.noSourceSearchResults"),
    sourceSearchResultCard,
  );

  renderSourceAudit();
  renderSourceTools();
}

function renderSourceRootPickers() {
  ["source-root-filter", "source-search-root", "source-save-root"].forEach((id) => {
    const picker = document.getElementById(id);
    if (!picker) return;
    const previous = id === "source-root-filter" ? state.activeSourceRootId : picker.value || "";
    picker.replaceChildren(el("option", { value: "" }, "全部资料源"));
    state.sourceRoots.forEach((root) => {
      picker.append(el("option", { value: root.root_id }, sourceRootLabel(root)));
    });
    picker.value = state.sourceRoots.some((root) => root.root_id === previous) ? previous : "";
  });
}

function renderSourceTools() {
  const selection = document.getElementById("source-selection-card");
  const selectionStatus = document.getElementById("source-selection-status");
  const savedStatus = document.getElementById("source-saved-search-status");
  const tagStatus = document.getElementById("source-tag-status");
  const commentStatus = document.getElementById("source-comment-status");
  if (!selection || !selectionStatus || !savedStatus || !tagStatus || !commentStatus) return;

  selection.replaceChildren();
  if (!state.selectedSourceRef) {
    selection.className = "empty-list";
    selection.textContent = t("empty.noSelectedSource");
    selectionStatus.textContent = "未选择";
    selectionStatus.className = "tag";
  } else {
    selection.className = "source-selection-card";
    selectionStatus.textContent = "已选择";
    selectionStatus.className = "tag ready";
    selection.append(
      el("strong", {}, state.selectedSourceTitle || state.selectedSourceRef.title || state.selectedSourceRef.path || "source"),
      el("p", {}, sourceRefPath(state.selectedSourceRef)),
      el("div", { className: "meta-row" }, [
        el("span", { className: "tag" }, state.selectedSourceRef.adapter || "source"),
        state.selectedSourceRef.chunk_id ? el("span", { className: "tag" }, shortId(state.selectedSourceRef.chunk_id)) : null,
      ]),
    );
  }

  renderSourceToolStatus(savedStatus, state.sourceSavedSearch, savedSearchSummary, "尚未保存查询。");
  renderSourceToolStatus(tagStatus, state.sourceTagApply || state.sourceTagProposal, sourceActionSummary, "没有标签提议。");
  renderSourceToolStatus(
    commentStatus,
    state.sourceCommentApply || state.sourceCommentProposal,
    sourceActionSummary,
    "没有 Comment 提议。",
  );
}

function renderSourceToolStatus(container, value, renderer, emptyText) {
  container.replaceChildren();
  if (!value) {
    container.className = "source-tool-status empty-list";
    container.textContent = emptyText;
    return;
  }
  container.className = "source-tool-status";
  container.append(renderer(value));
}

function savedSearchSummary(saved) {
  return el("div", {}, [
    el("strong", {}, saved.label || "saved search"),
    el("p", {}, saved.query || ""),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag ready" }, shortId(saved.search_id || "")),
      el("span", { className: "tag" }, saved.sort || "relevance"),
    ]),
  ]);
}

function sourceActionSummary(value) {
  const proposal = value.proposal || value;
  const record = value.record || null;
  const payload = proposal.payload || {};
  const text = record && (record.name || record.body) ? record.name || record.body : payload.tag || payload.body || "";
  return el("div", {}, [
    el("strong", {}, `${readableName(proposal.action || "source_action")} ${proposal.status || ""}`.trim()),
    el("p", {}, text),
    el("div", { className: "meta-row" }, [
      el("span", { className: `tag ${proposal.status === "applied" ? "ready" : "pending"}` }, proposal.status || "pending"),
      el("span", { className: "tag" }, proposal.write_target || "sidecar"),
      value.already_applied ? el("span", { className: "tag" }, "already applied") : null,
    ]),
  ]);
}

function renderSourceAudit() {
  const audit = state.sourceAudit;
  const summary = document.getElementById("source-audit-summary");
  const status = document.getElementById("source-audit-status");
  const actions = document.getElementById("source-audit-actions");
  const details = document.getElementById("source-audit-details");
  summary.replaceChildren();
  actions.replaceChildren();
  details.replaceChildren();
  if (!audit) {
    status.textContent = "未运行";
    status.className = "tag";
    summary.className = "source-audit-grid empty-list";
    summary.textContent = t("empty.noSourceAudit");
    renderList(actions, [], t("empty.noSourceAuditActions"));
    return;
  }

  const duplicate = audit.duplicate_preview || {};
  const unresolved = audit.unresolved_links || {};
  const unlinked = audit.unlinked_markdown || {};
  const routes = audit.route_candidates || [];
  status.textContent = `roots ${audit.root_count || 0}`;
  status.className = "tag ready";
  summary.className = "source-audit-grid";
  [
    ["资料源", audit.root_count || 0],
    ["重复组", duplicate.group_count || 0],
    ["断链", unresolved.count || 0],
    ["孤立笔记", unlinked.count || 0],
    ["路线候选", routes.length],
  ].forEach(([label, value]) => summary.append(sourceAuditStat(label, value)));

  renderList(actions, audit.next_actions || [], t("empty.noSourceAuditActions"), sourceAuditActionCard);
  details.append(
    sourceAuditSection("重复文件", duplicate.groups || [], duplicateGroupCard),
    sourceAuditSection("断链", unresolved.items || [], unresolvedLinkCard),
    sourceAuditSection("孤立 Markdown", unlinked.items || [], sourceCandidateCard),
    sourceAuditSection("路线候选", routes, sourceCandidateCard),
  );
}

function sourceRootCard(root) {
  const scan = state.sourceScanResults[root.root_id] || null;
  const counts = scan && scan.counts ? scan.counts : null;
  const tags = [
    el("span", { className: "tag" }, root.kind || "source"),
    el("span", { className: "tag" }, root.permission_mode || "read_only"),
    el("span", { className: `tag ${root.last_scan_at ? "ready" : "pending"}` }, root.last_scan_at ? "scanned" : "needs scan"),
    el("span", { className: "tag" }, `objects ${root.active_object_count || 0}`),
  ];
  if (counts) tags.push(el("span", { className: "tag ready" }, `indexed ${counts.indexed || 0}`));
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, sourceRootLabel(root)), el("p", {}, root.absolute_path || "")]),
      el("span", { className: "tag" }, shortId(root.root_id || "")),
    ]),
    el("div", { className: "meta-row" }, tags),
    el("div", { className: "card-actions" }, [
      el("button", { className: "secondary-button", type: "button", onclick: () => scanSourceRoot(root.root_id) }, t("button.scan")),
      el(
        "button",
        { className: "secondary-button", type: "button", onclick: () => enqueueSourceExtractionJob(root.root_id) },
        "队列抽取",
      ),
      el(
        "button",
        { className: "secondary-button", type: "button", onclick: () => runSourceAudit(sourceScopeFromRootId(root.root_id)) },
        t("button.audit"),
      ),
    ]),
  ]);
}

function sourceAuditStat(label, value) {
  return el("div", { className: "source-audit-stat" }, [el("span", {}, label), el("strong", {}, String(value))]);
}

function sourceAuditActionCard(action) {
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, action.label || readableName(action.action || "action")), el("p", {}, action.reason || "")]),
      el("span", { className: "tag" }, action.tool || action.api || readableName(action.action || "")),
    ]),
    el("div", { className: "card-actions" }, [
      el("button", { className: workspaceActionButtonClass(action), type: "button", onclick: () => openWorkspaceAction(action) }, workspaceActionButtonLabel(action)),
    ]),
  ]);
}

function sourceAuditSection(title, items, renderer) {
  const container = el("section", { className: "source-detail-section" }, [el("h3", {}, title)]);
  const list = el("div", { className: "list" });
  renderList(list, items, "没有项目。", renderer);
  container.append(list);
  return container;
}

function duplicateGroupCard(group) {
  const members = group.members || [];
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, `exact hash ${shortId(group.content_hash || "")}`),
        el("p", {}, `${members.length} 个文件，${formatBytes(group.size || 0)}`),
      ]),
      el("span", { className: "tag pending" }, "duplicate"),
    ]),
    el(
      "div",
      { className: "list" },
      members.map((member) =>
	        el("div", { className: "source-member-row" }, [
	          el("span", {}, `${member.root_label || member.root_kind || "root"} / ${member.path || ""}`),
	          member.source_ref
	            ? el("div", { className: "button-row compact-actions" }, [
	                el(
	                  "button",
	                  { className: "secondary-button", type: "button", onclick: () => selectSourceForAnnotation(member.source_ref, member.title || member.path) },
	                  t("button.annotate"),
	                ),
	                el("button", { className: "secondary-button", type: "button", onclick: () => readSource(member.source_ref) }, t("button.source")),
	              ])
	            : null,
	        ]),
      ),
    ),
  ]);
}

function unresolvedLinkCard(item) {
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, item.target_text || item.link_text || "unresolved link"),
        el("p", {}, `${item.root_label || item.root_kind || "root"} / ${item.source_path || ""}`),
      ]),
      el("span", { className: "tag pending" }, item.link_kind || "link"),
    ]),
    item.link_text ? el("p", {}, item.link_text) : null,
  ]);
}

function sourceCandidateCard(item) {
  const ref = item.source_ref || null;
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, item.title || item.path || "source"), el("p", {}, `${item.root_label || item.root_kind || "root"} / ${item.path || ""}`)]),
      el("span", { className: "tag" }, item.relation || item.object_kind || "source"),
    ]),
    item.reason ? el("p", {}, item.reason) : null,
	    ref
	      ? el("div", { className: "card-actions" }, [
	          el("button", { className: "secondary-button", type: "button", onclick: () => selectSourceForAnnotation(ref, item.title || item.path) }, t("button.annotate")),
	          el("button", { className: "secondary-button", type: "button", onclick: () => readSource(ref) }, t("button.source")),
	        ])
      : null,
  ]);
}

function sourceSearchResultCard(packet) {
  const ref = packet.source_ref || {};
  const metadata = packet.metadata || {};
  const lineRange = metadata.line_start ? `L${metadata.line_start}${metadata.line_end ? `-L${metadata.line_end}` : ""}` : "";
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, packet.title || ref.title || ref.path || "source"), el("p", {}, ref.path || metadata.path || "")]),
      el("span", { className: "tag ready" }, `${Math.round(Number(packet.score || 0) * 100)}%`),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, ref.adapter || metadata.root_kind || "source"),
      lineRange ? el("span", { className: "tag" }, lineRange) : null,
      metadata.extraction_status ? el("span", { className: "tag" }, metadata.extraction_status) : null,
    ]),
	    el("p", { className: "source-result-snippet" }, packet.text || ""),
	    el("div", { className: "card-actions" }, [
	      el("button", { className: "secondary-button", type: "button", onclick: () => selectSourceForAnnotation(ref, packet.title || ref.title || ref.path) }, t("button.annotate")),
	      el("button", { className: "secondary-button", type: "button", onclick: () => readSource(ref) }, t("button.source")),
	    ]),
  ]);
}

function sourceRootLabel(root) {
  return root.label || root.absolute_path || shortId(root.root_id || "");
}

function sourceRefPath(sourceRef) {
  const metadata = sourceRef.metadata || {};
  const root = metadata.root_label || metadata.root_kind || sourceRef.adapter || "source";
  const path = sourceRef.path || metadata.path || sourceRef.title || "";
  return `${root}${path ? ` / ${path}` : ""}`;
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderDocuments(documents) {
  renderList(document.getElementById("documents-list"), documents, t("empty.documents"), documentCard);
  syncParseButton(documents);
}

function renderReviews() {
  renderList(document.getElementById("reviews-list"), state.reviewView, t("empty.reviews"), reviewCard);
}

function renderMemoryReviewQueue(payload = null) {
  const list = document.getElementById("memory-review-queue-list");
  const summary = document.getElementById("memory-review-queue-summary");
  if (!list || !summary) return;
  if (state.memoryReviewQueueError) {
    summary.className = "job-status failed";
    summary.textContent = state.memoryReviewQueueError;
    renderList(list, [], t("empty.noMemoryReviewQueue"));
    return;
  }
  const queue = payload || state.memoryReviewQueue;
  if (!queue) {
    summary.className = "job-status pending";
    summary.textContent = "尚未加载记忆维护队列。";
    renderList(list, [], t("empty.noMemoryReviewQueue"));
    return;
  }
  const data = queue.summary || {};
  summary.className = queue.status === "ready" ? "job-status ready" : "job-status pending";
  summary.textContent = `${data.group_count || 0} 组 / ${data.item_count || 0} 项 / accepted ${data.accepted_unapplied_count || 0} / 对话候选 ${data.conversation_candidate_count || 0} / 相关候选 ${data.related_candidate_group_count || 0} / pending ${data.pending_review_count || 0}`;
  renderList(list, queue.groups || [], t("empty.noMemoryReviewQueue"), memoryReviewQueueGroupCard);
}

function renderMemoryCards(payload = null) {
  const list = document.getElementById("memory-cards-list");
  const summary = document.getElementById("memory-card-summary");
  if (!list || !summary) return;
  const filter = document.getElementById("memory-card-status-filter");
  if (filter) filter.value = state.memoryCardStatus || "active";
  const typeFilter = document.getElementById("memory-card-type-filter");
  if (typeFilter) typeFilter.value = state.memoryCardType || "";
  const query = document.getElementById("memory-card-query");
  if (query && query.value !== state.memoryCardQuery) query.value = state.memoryCardQuery || "";
  if (state.memoryCardsError) {
    summary.className = "job-status failed";
    summary.textContent = state.memoryCardsError;
    renderList(list, [], t("empty.noMemoryCards"));
    return;
  }
  const count = payload && Number.isFinite(Number(payload.count)) ? Number(payload.count) : state.memoryCards.length;
  summary.className = "job-status ready";
  summary.textContent = `${count} 张卡片 / ${state.memoryCardStatus || "active"}`;
  renderList(list, state.memoryCards, t("empty.noMemoryCards"), memoryCardCard);
}

function renderMemoryBriefing(payload = null) {
  const list = document.getElementById("memory-briefing-list");
  const summary = document.getElementById("memory-briefing-summary");
  if (!list || !summary) return;
  if (state.memoryBriefingError) {
    summary.className = "job-status failed";
    summary.textContent = state.memoryBriefingError;
    renderList(list, [], t("empty.noMemoryBriefing"));
    return;
  }
  const briefing = payload || state.memoryBriefing;
  if (!briefing) {
    summary.className = "job-status pending";
    summary.textContent = "尚未加载记忆简报。";
    renderList(list, [], t("empty.noMemoryBriefing"));
    return;
  }
  const data = briefing.summary || {};
  summary.className = briefing.status === "ready" ? "job-status ready" : "job-status pending";
  summary.textContent = `${data.focus_count || 0} 个关注项 / issues ${data.issue_count || 0} / recent ${data.recent_use_count || 0}`;
  renderList(list, briefing.focus_items || [], t("empty.noMemoryBriefing"), memoryBriefingItemCard);
}

function renderMemoryHealth(payload = null) {
  const list = document.getElementById("memory-health-list");
  const summary = document.getElementById("memory-health-summary");
  if (!list || !summary) return;
  const filter = document.getElementById("memory-health-type-filter");
  if (filter) filter.value = state.memoryHealthType || "";
  if (state.memoryHealthError) {
    summary.className = "job-status failed";
    summary.textContent = state.memoryHealthError;
    renderList(list, [], t("empty.noMemoryHealthIssues"));
    return;
  }
  const health = payload || state.memoryHealth;
  if (!health) {
    summary.className = "job-status pending";
    summary.textContent = "尚未扫描记忆健康。";
    renderList(list, [], t("empty.noMemoryHealthIssues"));
    return;
  }
  const summaryData = health.summary || {};
  summary.className = health.issue_count ? "job-status pending" : "job-status ready";
  summary.textContent = `${health.issue_count || 0} 个问题 / quality ${summaryData.quality || 0} / stale ${summaryData.stale || 0} / conflict ${summaryData.conflict || 0}`;
  renderList(list, health.issues || [], t("empty.noMemoryHealthIssues"), memoryHealthIssueCard);
}

function renderMemoryUseTraces(payload = null) {
  const list = document.getElementById("memory-use-trace-list");
  const summary = document.getElementById("memory-use-trace-summary");
  if (!list || !summary) return;
  const idInput = document.getElementById("memory-use-trace-memory-id");
  const queryInput = document.getElementById("memory-use-trace-query");
  if (idInput && idInput.value !== state.memoryUseTraceMemoryId) idInput.value = state.memoryUseTraceMemoryId || "";
  if (queryInput && queryInput.value !== state.memoryUseTraceQuery) queryInput.value = state.memoryUseTraceQuery || "";
  if (state.memoryUseTraceError || state.memoryTimelineError) {
    summary.className = "job-status failed";
    summary.textContent = state.memoryUseTraceError || state.memoryTimelineError;
    renderList(list, [], t("empty.noMemoryUseTrace"));
    return;
  }
  const timeline = payload && payload.schema === "pska.memory_timeline.v1" ? payload : state.memoryTimeline;
  const whyUsed = payload && payload.schema === "pska.memory_why_used.v1" ? payload : state.memoryWhyUsed;
  const count = payload && Number.isFinite(Number(payload.count))
    ? Number(payload.count)
    : state.memoryUseTraces.length;
  summary.className = "job-status ready";
  summary.textContent = timeline
    ? `${timeline.entry_count || 0} 条时间线 / usage ${(timeline.summary && timeline.summary.usage_trace_count) || 0} / sources ${(timeline.summary && timeline.summary.source_anchor_count) || 0}`
    : whyUsed
    ? `${whyUsed.confidence || "trace"} / ${whyUsed.trace_count || 0} 条痕迹`
    : `${count} 条痕迹`;
  const items = [];
  if (timeline) items.push(memoryTimelineCard(timeline));
  if (whyUsed) items.push(memoryWhyUsedCard(whyUsed));
  items.push(...state.memoryUseTraces.map((trace) => memoryUseTraceCard(trace)));
  renderList(list, items, t("empty.noMemoryUseTrace"), (item) => item);
}

function setReviewStatusFilter(status) {
  state.reviewStatus = status || "";
  const filter = document.getElementById("review-status-filter");
  if (filter) filter.value = state.reviewStatus;
}

function renderWorkflowList() {
  renderList(document.getElementById("workflow-list"), state.workflows, t("empty.runs"), workflowCard);
}

function renderAuditEvents() {
  renderList(document.getElementById("audit-list"), state.auditEvents, t("empty.audit"), auditEventCard);
}

function auditActionForAskResult(result) {
  if (result.status === "not_ready") return "kb.readiness.blocked";
  if (result.status === "insufficient_context") return "agentic_loop.insufficient_context";
  if (result.status === "ready") return "agentic_loop.complete";
  return "";
}

function auditActionForComponentCheck(result) {
  if (!result) return "";
  if (result.closed_loop_probe) return "closed_loop.probe";
  if (result.retrieval_probe) return "retrieval.probe";
  if (result.memory_probe) return "memory.probe";
  return "";
}

function auditActionForEval(result) {
  if (!result || !result.ok) return "";
  return "eval.run";
}

function setAuditActionFilter(action) {
  state.auditAction = action || "";
  const filter = document.getElementById("audit-action-filter");
  if (filter) filter.value = state.auditAction;
}

function renderAskDatasetPicker() {
  const picker = document.getElementById("ask-dataset-picker");
  if (!picker) return;
  picker.replaceChildren();
  if (!state.datasets.length) {
    picker.append(el("option", { value: "" }, t("empty.noDatasetsOption")));
    picker.disabled = true;
    return;
  }
  picker.disabled = false;
  state.datasets.forEach((dataset) => {
    picker.append(
      el(
        "option",
        { value: dataset.dataset_id || "" },
        `${dataset.name || dataset.dataset_id} (${shortId(dataset.dataset_id || "")})`,
      ),
    );
  });
}

function renderAskScope() {
  const datasetIds = askDatasetIds();
  const documentIds = askDocumentIds();
  const summary = document.getElementById("ask-scope-summary");
  if (summary) {
    summary.classList.toggle("empty-list", !datasetIds.length && !documentIds.length);
    summary.replaceChildren();
    if (!datasetIds.length && !documentIds.length) {
      summary.textContent = t("empty.noScope");
    } else {
      datasetIds.forEach((datasetId) => {
        summary.append(el("span", { className: "tag ready" }, `dataset ${shortId(datasetId)}`));
      });
      documentIds.forEach((documentId) => {
        summary.append(el("span", { className: "tag" }, `doc ${shortId(documentId)}`));
      });
    }
  }
  renderAskReadinessStatus();
  renderAskDocumentPicker();
}

function handleAskScopeInput() {
  invalidateAskReadiness();
  renderAskScope();
}

function invalidateAskReadiness() {
  state.askReadiness = null;
  state.askReadinessScopeKey = "";
}

async function checkAskReadiness(options = {}) {
  const datasetIds = askDatasetIds();
  const documentIds = askDocumentIds();
  if (!datasetIds.length) {
    state.askReadiness = null;
    state.askReadinessScopeKey = "";
    renderAskReadinessStatus();
    if (!options.silent) showToast(t("toast.selectAtLeastOneDataset"));
    return null;
  }
  try {
    const payload = await api("/api/kb/readiness", {
      method: "POST",
      body: {
        dataset_ids: datasetIds,
        document_ids: documentIds,
      },
    });
    state.askReadiness = payload.readiness || null;
    state.askReadinessScopeKey = askScopeKey(datasetIds, documentIds);
    renderAskReadinessStatus();
    if (!options.silent) {
      showToast(state.askReadiness && state.askReadiness.ready ? t("toast.askScopeReady") : t("toast.askScopeNotReady"));
    }
    return state.askReadiness;
  } catch (error) {
    state.askReadiness = {
      status: "failed",
      ready: false,
      message: error.message,
      ingestion_status: {},
    };
    state.askReadinessScopeKey = askScopeKey(datasetIds, documentIds);
    renderAskReadinessStatus();
    if (!options.silent) showToast(error.message);
    return null;
  }
}

function renderAskReadinessStatus() {
  const node = document.getElementById("ask-readiness-status");
  const actionsNode = document.getElementById("ask-readiness-actions");
  if (actionsNode) actionsNode.replaceChildren();
  if (!node) return;
  const datasetIds = askDatasetIds();
  const documentIds = askDocumentIds();
  const currentKey = askScopeKey(datasetIds, documentIds);
  if (!datasetIds.length) {
    node.className = "job-status pending";
    node.textContent = t("empty.noScope");
    return;
  }
  if (!state.askReadiness || state.askReadinessScopeKey !== currentKey) {
    node.className = "job-status pending";
    node.textContent = t("empty.noAskScopeChecked");
    return;
  }
  const readiness = state.askReadiness;
  const job = readiness.ingestion_status || {};
  const actions = (job.next_actions || []).map(readableName).join(", ");
  const suffix = actions ? ` 下一步：${actions}。` : "";
  const progress = job.kind ? ` ${formatPercent(job.progress)}.` : "";
  node.className = `job-status ${statusClass(readiness.status)}`;
  node.textContent = `${readiness.message || "提问范围就绪状态已检查。"}${progress}${suffix}`;
  renderAskReadinessActions(actionsNode, readiness);
}

function renderAskReadinessActions(container, readiness, options = {}) {
  if (!container || !readiness) return;
  const job = readiness.ingestion_status || {};
  const actions = new Set(job.next_actions || []);
  const datasetIds = options.datasetIds || readiness.dataset_ids || askDatasetIds();
  const documentIds = options.documentIds || readiness.document_ids || askDocumentIds();
  const datasetId = readinessDatasetForAction(readiness, "", datasetIds) || datasetIds[0] || "";
  if (options.includeRunAsk !== false && (readiness.ready || actions.has("run_ask"))) {
    container.append(el("button", { className: "primary-button", onclick: submitAskForm }, t("button.runAsk")));
  }
  if (actions.has("start_parse")) {
    container.append(
      el(
        "button",
        {
          className: "primary-button",
          onclick: () => handleAskReadinessAction("start_parse", { readiness, datasetIds, documentIds }),
        },
        t("button.parseScope"),
      ),
    );
  }
  if (actions.has("wait_for_ingestion")) {
    container.append(
      el(
        "button",
        {
          className: "secondary-button",
          onclick: () => handleAskReadinessAction("wait_for_ingestion", { readiness, datasetIds, documentIds }),
        },
        t("button.trackStatus"),
      ),
    );
  }
  if (datasetId) {
    container.append(
      el(
        "button",
        {
          className: "secondary-button",
          onclick: () => handleAskReadinessAction("open_status", { readiness, datasetIds, documentIds }),
        },
        t("button.openStatus"),
      ),
    );
  }
}

async function handleAskReadinessAction(action, options = {}) {
  const readiness = options.readiness || state.askReadiness || {};
  const datasetIds = options.datasetIds || askDatasetIds();
  const documentIds = options.documentIds || askDocumentIds();
  const datasetId = readinessDatasetForAction(readiness, action, datasetIds) || datasetIds[0] || "";
  if (!datasetId) {
    showToast(t("toast.selectAtLeastOneDataset"));
    return;
  }
  await openDatasetStatus(datasetId);
  if (action === "start_parse") {
    await parseDatasetDocuments(datasetId, documentIds);
    return;
  }
  if (action === "wait_for_ingestion") {
    startIngestionPolling(datasetId);
  }
}

function readinessDatasetForAction(readiness, action, fallbackDatasetIds = []) {
  const productAction = productReadinessAction(action);
  const datasets = readiness.datasets || [];
  const match = datasets.find((dataset) => productReadinessAction((dataset.ingestion || {}).next_action) === productAction);
  return String((match && match.dataset_id) || (readiness.dataset_ids || fallbackDatasetIds || [])[0] || "");
}

function productReadinessAction(action) {
  const mapping = {
    configure_embedding_provider: "configure_embedding_provider",
    inspect_cancelled_documents: "inspect_cancellation",
    inspect_failed_documents: "inspect_failure",
    open_status: "open_status",
    run_ask: "run_agentic_question",
    start_parse: "parse_documents",
  };
  return mapping[action] || action || "";
}

function submitAskForm() {
  const form = document.getElementById("ask-form");
  if (form) form.requestSubmit();
}

function renderAskDocumentPicker() {
  const container = document.getElementById("ask-document-picker");
  if (!container) return;
  const datasetIds = askDatasetIds();
  const documentIds = new Set(askDocumentIds());
  const loaded = datasetIds.flatMap((datasetId) =>
    (state.askDocumentsByDataset[datasetId] || []).map((document) => ({ datasetId, document })),
  );
  container.replaceChildren();
  if (!loaded.length) {
    container.classList.add("empty-list");
    container.textContent = datasetIds.length ? t("empty.noAskDocuments") : t("empty.selectDataset");
    return;
  }
  container.classList.remove("empty-list");
  loaded.forEach(({ datasetId, document }) => {
    container.append(askDocumentCard(datasetId, document, documentIds.has(document.document_id)));
  });
}

function askDocumentCard(datasetId, document, checked) {
  const stateName = documentState(document);
  const input = el("input", { type: "checkbox", value: document.document_id || "" });
  input.checked = checked;
  input.addEventListener("change", () => toggleAskDocument(document.document_id, input.checked));
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("label", { className: "check-row" }, [
        input,
        el("span", {}, document.name || document.document_id || "document"),
      ]),
      el("span", { className: `tag ${stateName.className}` }, stateName.label),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, `dataset ${shortId(datasetId)}`),
      el("span", { className: "tag" }, shortId(document.document_id || "")),
      el("span", { className: "tag" }, `chunks ${document.chunk_count || 0}`),
    ]),
  ]);
}

function renderIngestResult(result, readiness = null) {
  const documents = result.documents || [];
  const datasetId = ingestDatasetId(result);
  state.activeDocumentDatasetId = datasetId || state.activeDocumentDatasetId;
  const displayDocuments = mergeReadinessDocuments(documents, readiness);
  state.activeDocuments = displayDocuments;
  renderDocuments(displayDocuments);
  if (datasetId) {
    if (readiness) state.readinessByDataset[datasetId] = readiness;
    renderIngestionStatus(datasetId, displayDocuments, readiness);
    if (readiness && readiness.ready) {
      prepareAskScope(datasetId, displayDocuments);
    }
    const statusForm = document.querySelector('#document-status-form input[name="dataset_id"]');
    if (statusForm) statusForm.value = datasetId;
  }
}

async function parseActiveDocuments() {
  const field = document.querySelector('#document-status-form input[name="dataset_id"]');
  const requestedDatasetId = field ? field.value.trim() : "";
  const datasetId = requestedDatasetId || state.activeDocumentDatasetId || "";
  await parseDatasetDocuments(datasetId);
}

async function parseDatasetDocuments(datasetId, requestedDocumentIds = []) {
  if (!datasetId) {
    showToast(t("toast.loadDatasetBeforeParse"));
    return;
  }
  let documents = state.activeDocumentDatasetId === datasetId ? state.activeDocuments || [] : [];
  if (!documents.length) {
    documents = await loadDocuments(datasetId);
  }
  const requested = new Set(uniqueIds(requestedDocumentIds));
  const documentIds = documents
    .filter((document) => !requested.size || requested.has(document.document_id))
    .filter((document) => documentState(document).label !== "ready")
    .map((document) => document.document_id)
    .filter(Boolean);
  if (!documentIds.length) {
    showToast(t("toast.noUnreadyDocuments"));
    return;
  }
  const parsed = await api(`/api/kb/datasets/${encodeURIComponent(datasetId)}/parse`, {
    method: "POST",
    body: {
      document_ids: documentIds,
      wait: false,
    },
  });
  showToast(t("toast.parseStarted"));
  const displayDocuments = parsed.readiness ? mergeReadinessDocuments(documents, parsed.readiness) : documents;
  if (parsed.readiness) {
    state.readinessByDataset[datasetId] = parsed.readiness;
    renderIngestionStatus(datasetId, displayDocuments, parsed.readiness);
    if (parsed.readiness.ready) {
      prepareAskScope(datasetId, displayDocuments);
    }
  } else {
    setIngestionStatus(`正在跟踪 ${shortId(datasetId)} 解析...`, "pending");
  }
  if (!parsed.readiness || !parsed.readiness.ready) {
    startIngestionPolling(datasetId);
  }
  await loadDocuments(datasetId, { silent: true });
  await loadWorkspaceStatus();
  await loadAuditEvents("kb.parse");
}

function addAskDataset(datasetId = "") {
  const picker = document.getElementById("ask-dataset-picker");
  const selected = String(datasetId || (picker ? picker.value : "") || "").trim();
  if (!selected) {
    showToast(t("toast.selectDataset"));
    return;
  }
  prepareAskScope(selected);
}

async function loadAskDocuments() {
  const picker = document.getElementById("ask-dataset-picker");
  const datasetId = String((picker && picker.value) || askDatasetIds()[0] || "").trim();
  if (!datasetId) {
    showToast(t("toast.selectDataset"));
    return;
  }
  addAskDataset(datasetId);
  const payload = await api(`/api/kb/datasets/${encodeURIComponent(datasetId)}/documents`);
  state.askDocumentsByDataset[datasetId] = payload.documents || [];
  renderAskScope();
}

function toggleAskDocument(documentId, checked) {
  const normalized = String(documentId || "").trim();
  if (!normalized) return;
  const documentIds = askDocumentIds().filter((item) => item !== normalized);
  if (checked) {
    documentIds.push(normalized);
  }
  setAskDocumentIds(documentIds);
  renderAskScope();
}

function startIngestionPolling(datasetId) {
  stopIngestionPolling();
  state.ingestionPoll = {
    datasetId,
    attempts: 0,
    maxAttempts: 120,
    timer: null,
  };
  setIngestionStatus(`正在跟踪 ${shortId(datasetId)} 入库...`, "pending");
  state.ingestionPoll.timer = window.setInterval(async () => {
    if (!state.ingestionPoll || state.ingestionPoll.datasetId !== datasetId) return;
    state.ingestionPoll.attempts += 1;
    try {
      const documents = await loadDocuments(datasetId, { silent: true });
      await loadDatasets();
      await loadWorkspaceStatus();
      const summary = summarizeDocuments(documents);
      if (summary.status === "ready") {
        stopIngestionPolling();
        prepareAskScope(datasetId, documents);
        showToast(t("toast.kbReadyAskUpdated"));
      } else if (["failed", "empty"].includes(summary.status)) {
        stopIngestionPolling();
      } else if (state.ingestionPoll && state.ingestionPoll.attempts >= state.ingestionPoll.maxAttempts) {
        stopIngestionPolling();
        setIngestionStatus(`${shortId(datasetId)} 的跟踪已暂停。`, "pending");
      }
    } catch (error) {
      stopIngestionPolling();
      setIngestionStatus(error.message, "failed");
    }
  }, 2500);
}

function stopIngestionPolling() {
  if (state.ingestionPoll && state.ingestionPoll.timer) {
    window.clearInterval(state.ingestionPoll.timer);
  }
  state.ingestionPoll = null;
}

function renderIngestionStatus(datasetId, documents, readiness) {
  const summary = summarizeDocuments(documents);
  const job = readiness && readiness.ingestion_status;
  if (job && job.kind === "kb_ingestion_status") {
    const actions = (job.next_actions || []).map(readableName).join(", ");
    const suffix = actions ? ` 下一步：${actions}。` : "";
    setIngestionStatus(`${shortId(datasetId)}: ${job.message || readiness.message} ${formatPercent(job.progress)}.${suffix}`, job.status);
    renderIngestionActions(datasetId, job, summary);
    return;
  }
  const readinessStatus = readiness && readiness.status ? readiness.status : summary.status;
  const label = readiness && readiness.message ? readiness.message : `${summary.ready}/${summary.total} 个文档已就绪。`;
  setIngestionStatus(`${shortId(datasetId)}: ${label}`, readinessStatus);
  renderIngestionActions(datasetId, null, summary);
}

function setIngestionStatus(message, status) {
  const node = document.getElementById("ingestion-status");
  if (!node) return;
  node.className = `job-status ${statusClass(status)}`;
  node.textContent = message;
  const actions = document.getElementById("ingestion-actions");
  if (actions) actions.replaceChildren();
}

function renderIngestionActions(datasetId, job, summary) {
  const container = document.getElementById("ingestion-actions");
  if (!container) return;
  container.replaceChildren();
  const actions = new Set((job && job.next_actions) || []);
  if ((job && job.ready) || actions.has("run_ask") || summary.status === "ready") {
    container.append(el("button", { className: "primary-button", onclick: () => setAskDataset(datasetId) }, t("button.askThisKb")));
  }
  if (actions.has("start_parse")) {
    container.append(el("button", { className: "primary-button", onclick: parseActiveDocuments }, t("button.parseListed")));
  }
  if (actions.has("wait_for_ingestion") || summary.status === "processing") {
    container.append(el("button", { className: "secondary-button", onclick: () => startIngestionPolling(datasetId) }, t("button.trackStatus")));
  }
  if (
    actions.has("inspect_failure") ||
    actions.has("inspect_failed_documents") ||
    actions.has("inspect_cancellation") ||
    actions.has("inspect_cancelled_documents") ||
    summary.status === "failed"
  ) {
    container.append(el("button", { className: "secondary-button", onclick: () => loadDocuments(datasetId) }, t("button.reloadStatus")));
  }
}

function syncParseButton(documents = state.activeDocuments || []) {
  const button = document.getElementById("parse-documents");
  if (!button) return;
  const unreadyCount = documents.filter((document) => documentState(document).label !== "ready").length;
  button.disabled = !state.activeDocumentDatasetId || unreadyCount === 0;
  button.textContent = unreadyCount ? `${t("button.parseListed")} (${unreadyCount})` : t("button.parseListed");
}

function ingestDatasetId(result) {
  if (!result) return "";
  if (result.dataset && result.dataset.dataset_id) return result.dataset.dataset_id;
  const documents = result.documents || [];
  return documents.length ? documents[0].dataset_id || "" : "";
}

function mergeReadinessDocuments(documents, readiness) {
  const readinessDocuments = ((readiness && readiness.datasets) || []).flatMap((dataset) => dataset.documents || []);
  if (!readinessDocuments.length) return documents;
  const byId = new Map(readinessDocuments.map((document) => [document.document_id, document]));
  return documents.map((document) => {
    const statusDocument = byId.get(document.document_id);
    return statusDocument ? { ...document, ...statusDocument } : document;
  });
}

function renderAskResult(result) {
  const container = document.getElementById("ask-result");
  container.replaceChildren();
  if (result.status === "insufficient_context") {
    container.append(
      el("div", { className: "item-card" }, [
        el("h3", {}, t("heading.insufficientContext")),
        el("p", {}, result.message || t("empty.noContext")),
      ]),
    );
    container.append(loopPanel(result));
    if ((result.context_packets || []).length) {
      container.append(
        el("div", { className: "panel" }, [
          el("h2", {}, t("heading.retrievedContext")),
          el(
            "div",
            { className: "source-list" },
            (result.context_packets || []).map((packet) => contextCard(packet)),
          ),
        ]),
      );
    }
    container.append(askResultActions(result));
    return;
  }
  if (result.status === "not_ready") {
    const fresh = result.run ? resumableAskFor(result.run.run_id) : null;
    const readiness = (fresh && fresh.readiness) || result.readiness || {};
    container.append(
      el("div", { className: "item-card" }, [
        el("h3", {}, t("heading.scopeNotReady")),
        el("p", {}, (fresh && fresh.message) || result.message || readiness.message || "所选知识范围尚未就绪，不能检索。"),
      ]),
    );
    container.append(readinessPanel(readiness));
    container.append(loopPanel(result));
    container.append(askResultActions(result));
    return;
  }
  container.append(
    el("div", { className: "panel" }, [
      el("div", { className: "panel-header" }, [
        el("h2", {}, t("heading.sourcedBrief")),
        el("span", { className: "tag ready" }, result.review ? "已创建异常审核" : "临时结果"),
      ]),
      el("pre", {}, result.brief || ""),
    ]),
  );
  container.append(askResultActions(result));
  container.append(memoryAttributionPanel(result.memory_attribution || (result.artifact && result.artifact.memory_attribution)));
  container.append(memorySuggestionsPanel(result.memory_suggestions || (result.artifact && result.artifact.memory_suggestions)));
  container.append(loopPanel(result));
  container.append(
      el("div", { className: "panel" }, [
      el("h2", {}, t("heading.context")),
      el(
        "div",
        { className: "source-list" },
        (result.context_packets || []).map((packet) => contextCard(packet)),
      ),
    ]),
  );
}

function askResultActions(result) {
  const actions = el("div", { className: "result-actions" }, []);
  const reviewId = result.review && result.review.review_id;
  const memoryApply = result.memory_apply || (reviewId && state.memoryApplyByReview[reviewId]);
  if (result.run && result.run.run_id) {
    actions.append(
      el("button", { className: "secondary-button", onclick: () => openWritingRun(result.run.run_id) }, t("button.openWriting")),
    );
    if (result.status === "ready") {
      actions.append(
        el(
          "button",
          { className: "secondary-button", onclick: () => exportWorkflow(result.run.run_id, "markdown", { openWriting: true }) },
          "Markdown",
        ),
        el(
          "button",
          { className: "secondary-button", onclick: () => exportWorkflow(result.run.run_id, "json", { openWriting: true }) },
          "JSON",
        ),
      );
    }
    if (result.status === "ready" && !reviewId) {
      actions.append(
        el(
          "button",
          { className: "primary-button", onclick: () => createMemoryReviewFromRun(result.run.run_id) },
          t("button.memoryReview"),
        ),
      );
    }
    if (result.status === "not_ready") {
      const fresh = resumableAskFor(result.run.run_id);
      const runForResume = (fresh && fresh.run) || result.run;
      const askRequest = (fresh && fresh.ask_request) || (result.run.metadata && result.run.metadata.ask_request) || {};
      const readiness = (fresh && fresh.readiness) || result.readiness || {};
      const resume = resumeContractForResult(result) || (fresh && fresh.resume) || null;
      const canResume = fresh ? Boolean(fresh.can_resume) : resume ? Boolean(resume.can_resume) : Boolean(result.readiness && result.readiness.ready);
      const tracking = state.blockedAskPoll && state.blockedAskPoll.runId === result.run.run_id;
      const contractActions = resultNextActions(result, fresh);
      appendResultContractActions(actions, contractActions);
      renderAskReadinessActions(actions, readiness, {
        datasetIds: askRequest.dataset_ids || readiness.dataset_ids || [],
        documentIds: askRequest.document_ids || readiness.document_ids || [],
        includeRunAsk: false,
      });
      actions.append(
        el(
          "button",
          { className: "secondary-button", onclick: () => refreshBlockedAskReadiness(result.run.run_id) },
          t("button.checkReadiness"),
        ),
      );
      actions.append(
        el(
          "button",
          {
            className: "secondary-button",
            onclick: () => startBlockedAskTracking(result.run.run_id),
            ...(tracking ? { disabled: true } : {}),
          },
          tracking ? t("button.tracking") : t("button.trackResume"),
        ),
      );
      if (!contractActions.some((action) => ["resume_blocked_ask", "resume_ingest_loop"].includes(action.action))) {
        actions.append(
          el(
            "button",
            {
              className: "primary-button",
              onclick: () => resumeBlockedRun(result.run.run_id),
              ...(canResume ? {} : { disabled: true }),
            },
            isIngestLoopResume(resume) || hasIngestLoopResume(runForResume) ? t("button.resumeLoop") : t("button.resumeAsk"),
          ),
        );
      }
    }
  }
  if (reviewId) {
    actions.append(
      el("button", { className: "secondary-button", onclick: () => openReview(reviewId) }, t("button.openReview")),
    );
  }
  if (
    result.review &&
    reviewId &&
    result.review.status === "accepted" &&
    result.proposal &&
    result.proposal.kind === "memory_patch" &&
    !memoryApply
  ) {
    actions.append(
      el("button", { className: "primary-button", onclick: () => applyMemory(reviewId) }, t("button.applyMemory")),
    );
  }
  if (memoryApply) {
    actions.append(el("span", { className: "tag ready" }, memoryApplyLabel(memoryApply)));
  }
  return el("div", { className: "panel compact-panel" }, [
    el("h2", {}, t("heading.nextActions")),
    actions.children.length ? actions : el("p", {}, t("empty.noFollowup")),
  ]);
}

function resultNextActions(result, fresh) {
  const actions = (fresh && fresh.next_actions && fresh.next_actions.length ? fresh.next_actions : result.next_actions) || [];
  return actions.filter((action) => action && action.action);
}

function appendResultContractActions(container, actions) {
  const supported = actions.filter((action) =>
    ["track_ingestion_status", "resume_ingest_loop", "resume_blocked_ask"].includes(action.action),
  );
  for (const action of supported) {
    container.append(
      el(
        "button",
        {
          className: workspaceActionButtonClass(action),
          onclick: () => openWorkspaceAction(action),
          ...(action.requires_ready && !action.can_resume ? { disabled: true } : {}),
        },
        workspaceActionButtonLabel(action),
      ),
    );
  }
}

function loopPanel(result) {
  const loop = result.loop || {};
  const governanceAction = (loop.governance || {}).action;
  const tags = [];
  if (loop.status) tags.push(el("span", { className: `tag ${statusClass(loop.status)}` }, loop.status));
  if (governanceAction) tags.push(el("span", { className: "tag" }, governanceAction));
  if (loop.durable_proposal !== undefined) {
    tags.push(el("span", { className: `tag ${loop.durable_proposal ? "pending" : "ready"}` }, loop.durable_proposal ? "durable" : "transient"));
  }
  if (loop.review_required !== undefined) {
    tags.push(el("span", { className: `tag ${loop.review_required ? "pending" : "ready"}` }, loop.review_required ? "review required" : "no review"));
  }
  return el("div", { className: "panel" }, [
    el("div", { className: "panel-header" }, [
      el("h2", {}, "Loop"),
      tags.length ? el("div", { className: "meta-row" }, tags) : null,
    ]),
    loop.context_count !== undefined
      ? el("p", {}, `Context packets: ${loop.context_count}${loop.required_context_count ? ` / required ${loop.required_context_count}` : ""}`)
      : null,
    el(
      "div",
      { className: "source-list" },
      (loop.steps || []).map((step) => loopStepCard(step)),
    ),
  ]);
}

function readinessPanel(readiness) {
  const blocking = readiness.blocking || [];
  const datasets = readiness.datasets || [];
  const job = readiness.ingestion_status || {};
  return el("div", { className: "panel" }, [
    el("div", { className: "panel-header" }, [
      el("h2", {}, "Readiness"),
      el("span", { className: `tag ${statusClass(readiness.status)}` }, readiness.status || "unknown"),
    ]),
    job.kind
      ? el("div", { className: "meta-row" }, [
          el("span", { className: "tag" }, job.phase || "phase"),
          el("span", { className: "tag" }, formatPercent(job.progress)),
          el("span", { className: "tag" }, `${job.ready_count || 0}/${job.document_count || 0} ready`),
          ...(job.next_actions || []).map((action) => el("span", { className: "tag" }, readableName(action))),
        ])
      : null,
    blocking.length
      ? el("div", { className: "source-list" }, blocking.map((item) => el("p", {}, item)))
      : el("p", {}, readiness.message || "Selected knowledge scope is ready for retrieval."),
    el("div", { className: "source-list" }, datasets.map((dataset) => readinessDatasetCard(dataset))),
  ]);
}

function readinessDatasetCard(dataset) {
  const documents = dataset.documents || [];
  const job = dataset.ingestion || {};
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, dataset.name || dataset.dataset_id || "dataset"),
        el("p", {}, dataset.dataset_id || ""),
      ]),
      el("span", { className: `tag ${statusClass(dataset.status)}` }, dataset.status || "unknown"),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, `docs ${dataset.document_count || 0}`),
      el("span", { className: "tag" }, `chunks ${dataset.chunk_count || 0}`),
      el("span", { className: "tag" }, dataset.exists ? "visible" : "missing"),
      job.phase ? el("span", { className: "tag" }, job.phase) : null,
      job.next_action ? el("span", { className: "tag" }, readableName(job.next_action)) : null,
    ]),
    documents.length
      ? el(
          "div",
          { className: "meta-row" },
          documents.map((document) =>
            el(
              "span",
              { className: `tag ${statusClass(document.status)}` },
              `${document.name || shortId(document.document_id)}: ${document.status}`,
            ),
          ),
        )
      : null,
  ]);
}

function renderWriting() {
  const container = document.getElementById("writing-current");
  container.classList.toggle("empty-list", !state.currentBrief);
  container.replaceChildren();
  if (!state.currentBrief) {
    container.textContent = t("empty.writing");
    return;
  }
  const run = state.currentBrief.run || {};
  const artifact = state.currentBrief.artifact || {};
  const latestProposal = state.currentBrief.proposal || artifact.latest_proposal || null;
  const sourceManifest = artifact.source_manifest || [];
  const sourceInspections = artifact.source_inspections || [];
  const contextPackets = artifact.context_packets || run.context_packets || [];
  const memoryFacts = artifact.memory_facts || state.currentBrief.memory_facts || [];
  const review = state.currentBrief.review || {};
  const memoryApply = state.currentBrief.memory_apply || (review.review_id && state.memoryApplyByReview[review.review_id]);
  container.append(
    el("article", { className: "item-card" }, [
      el("header", {}, [
        el("div", {}, [
          el("h3", {}, run.intent || t("heading.sourcedBrief")),
          el("p", {}, run.run_id || ""),
        ]),
        el("span", { className: `tag ${statusClass(review.status || state.currentBrief.status)}` }, review.status || state.currentBrief.status || "ready"),
      ]),
      review.review_id
        ? el("div", { className: "meta-row" }, [
            el("span", { className: "tag" }, shortId(review.review_id)),
            memoryApply ? el("span", { className: "tag ready" }, memoryApplyLabel(memoryApply)) : null,
          ])
        : null,
      state.currentBrief.brief
        ? el("pre", {}, state.currentBrief.brief)
        : latestProposal
          ? workProductBlock(latestProposal)
          : el("p", { className: "empty-list" }, t("empty.exportPrompt")),
    ]),
  );
  const loop = run.metadata && run.metadata.agentic_loop;
  if (loop && loop.steps) {
    container.append(loopPanel({ loop }));
  }
  if (memoryApply) {
    container.append(
      el("div", { className: "panel" }, [
        el("h2", {}, t("heading.appliedKnowledge")),
        memoryApplyCard(memoryApply),
      ]),
    );
  }
  container.append(memoryAttributionPanel(state.currentBrief.memory_attribution || artifact.memory_attribution));
  container.append(memorySuggestionsPanel(state.currentBrief.memory_suggestions || artifact.memory_suggestions));
  if (!state.currentBrief.brief && memoryFacts.length) {
    container.append(
      el("div", { className: "panel" }, [
        el("h2", {}, t("heading.durableMemory")),
        el("div", { className: "source-list" }, memoryFacts.map((fact) => memoryFactCard(fact))),
      ]),
    );
  }
  if (!state.currentBrief.brief && sourceInspections.length) {
    container.append(
      el("div", { className: "panel" }, [
        el("h2", {}, t("heading.inspectedSources")),
        el("div", { className: "source-list" }, sourceInspections.map((source) => sourceInspectionCard(source))),
      ]),
    );
  }
  if (!state.currentBrief.brief && sourceManifest.length) {
    container.append(
      el("div", { className: "panel" }, [
        el("h2", {}, t("heading.sourceManifest")),
        el("div", { className: "source-list" }, sourceManifest.map((source) => sourceManifestCard(source))),
      ]),
    );
  }
  if (!state.currentBrief.brief && contextPackets.length) {
    container.append(
      el("div", { className: "panel" }, [
        el("h2", {}, t("heading.context")),
        el("div", { className: "source-list" }, contextPackets.map((packet) => contextCard(packet))),
      ]),
    );
  }
}

function memoryAttributionPanel(attribution) {
  const used = (attribution && attribution.used_memories) || [];
  return el("div", { className: "panel" }, [
    el("div", { className: "panel-header" }, [
      el("h2", {}, t("heading.memoryAttribution")),
      el("span", { className: `tag ${used.length ? "ready" : "pending"}` }, `${used.length} memories`),
    ]),
    used.length
      ? el("div", { className: "source-list" }, used.map(memoryAttributionCard))
      : el("p", { className: "empty-list" }, t("empty.noMemoryAttribution")),
  ]);
}

function memoryAttributionCard(memory) {
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, memory.display_text || memory.memory_id || "memory"),
        el("p", {}, memory.evidence_status || memory.used_as || ""),
      ]),
      el("button", { className: "secondary-button", onclick: () => inspectMemoryCard(memory.memory_id) }, t("button.inspect")),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, shortId(memory.memory_id || "")),
      memory.memory_type ? el("span", { className: "tag" }, memory.memory_type) : null,
      memory.memory_scope ? el("span", { className: "tag" }, memory.memory_scope) : null,
      el("span", { className: "tag" }, `${memory.source_count || 0} sources`),
    ]),
  ]);
}

function memorySuggestionsPanel(payload) {
  const suggestions = (payload && payload.suggestions) || [];
  return el("div", { className: "panel" }, [
    el("div", { className: "panel-header" }, [
      el("h2", {}, t("heading.memorySuggestions")),
      el("span", { className: `tag ${suggestions.length ? "pending" : "ready"}` }, `${suggestions.length} suggestions`),
    ]),
    suggestions.length
      ? el("div", { className: "source-list" }, suggestions.map(memorySuggestionCard))
      : el("p", { className: "empty-list" }, t("empty.noMemorySuggestions")),
  ]);
}

function memorySuggestionCard(suggestion) {
  const runId = suggestion.run_id || (suggestion.evidence && suggestion.evidence.run_id) || "";
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, suggestion.title || suggestion.type || "memory suggestion"),
        el("p", {}, suggestion.reason || ""),
      ]),
      runId
        ? el("button", { className: "primary-button", onclick: () => createMemoryReviewFromRun(runId) }, t("button.memoryReview"))
        : null,
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, suggestion.type || "suggestion"),
      el("span", { className: "tag" }, `confidence ${Number(suggestion.confidence || 0).toFixed(2)}`),
      el("span", { className: "tag" }, `${suggestion.source_count || 0} sources`),
    ]),
  ]);
}

function workProductBlock(proposal) {
  return el("section", { className: "work-product" }, [
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, proposal.kind || "proposal"),
      el("span", { className: "tag" }, shortId(proposal.proposal_id || "")),
    ]),
    el("h3", {}, proposal.title || "Work product"),
    el("pre", {}, proposal.body || ""),
  ]);
}

function loopStepCard(step) {
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, step.name || "step"), el("p", {}, step.message || "")]),
      el("span", { className: `tag ${statusClass(step.status)}` }, step.status || ""),
    ]),
  ]);
}

function datasetCard(dataset) {
  const stateName = datasetState(dataset);
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, dataset.name || dataset.dataset_id),
        el("p", {}, dataset.description || dataset.dataset_id || ""),
      ]),
      el("div", { className: "card-actions" }, [
        el("span", { className: `tag ${stateName.className}` }, stateName.label),
        el("button", { className: "secondary-button", onclick: () => setAskDataset(dataset.dataset_id) }, t("button.ask")),
        el("button", { className: "secondary-button", onclick: () => openDatasetUpload(dataset.dataset_id) }, t("button.upload")),
        el("button", { className: "secondary-button", onclick: () => openDatasetStatus(dataset.dataset_id) }, t("button.openStatus")),
        el("button", { className: "secondary-button danger-button", onclick: () => deleteDataset(dataset.dataset_id) }, t("button.delete")),
      ]),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, `docs ${dataset.document_count || 0}`),
      el("span", { className: "tag" }, `chunks ${dataset.chunk_count || 0}`),
      el("span", { className: "tag" }, dataset.chunk_method || "method"),
      el("span", { className: "tag" }, shortId(dataset.dataset_id || "")),
    ]),
  ]);
}

function documentCard(document) {
  const stateName = documentState(document);
  const progress = Math.max(0, Math.min(1, Number(document.progress || 0)));
  const datasetId = document.dataset_id || state.activeDocumentDatasetId || "";
  const documentId = document.document_id || "";
  const detail = document.failure_reason || document.progress_msg || "";
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, document.name || document.document_id), el("p", {}, detail)]),
      el("div", { className: "card-actions" }, [
        el("span", { className: `tag ${stateName.className}` }, stateName.label),
        datasetId && documentId && stateName.label === "ready"
          ? el("button", { className: "secondary-button", onclick: () => askDocument(datasetId, document) }, "Ask")
          : null,
        datasetId && documentId
          ? el("button", { className: "secondary-button", onclick: () => readDocumentGraph(datasetId, documentId) }, "Graph")
          : null,
      ]),
    ]),
    el("div", { className: "progress-row" }, [
      el("progress", { value: String(progress), max: "1" }, ""),
      el("span", {}, `${Math.round(progress * 100)}%`),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, `chunks ${document.chunk_count || 0}`),
      el("span", { className: "tag" }, `tokens ${document.token_count || 0}`),
      document.phase ? el("span", { className: "tag" }, document.phase) : null,
      document.next_action ? el("span", { className: "tag" }, readableName(document.next_action)) : null,
      el("span", { className: "tag" }, shortId(document.document_id || "")),
    ]),
  ]);
}

function contextCard(packet) {
  const sourceRef = packet.source_ref || {};
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, packet.title || sourceRef.title || packet.context_id), el("p", {}, packet.text || "")]),
      el("button", { className: "secondary-button", onclick: () => readSource(sourceRef) }, t("button.source")),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, sourceRef.adapter || "adapter"),
      el("span", { className: "tag" }, shortId(sourceRef.document_id || sourceRef.source_id || "")),
      el("span", { className: "tag" }, `score ${Number(packet.score || 0).toFixed(2)}`),
    ]),
  ]);
}

function memoryFactCard(fact) {
  const sourceRefs = fact.source_refs || [];
  const reason = el("input", { placeholder: t("label.reviewReason"), value: "" });
  const updatedText = el("textarea", { placeholder: "Updated memory text", value: fact.text || "" });
  const updateSupported = memoryOperationSupported("update");
  const deleteSupported = memoryOperationSupported("delete");
  const updateReason = memoryCapabilityReason("update");
  const deleteReason = memoryCapabilityReason("delete");
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, fact.fact_id || "Memory"), el("p", {}, fact.text || "")]),
      el("div", { className: "card-actions" }, [
        fact.fact_id
          ? el("button", { className: "secondary-button", onclick: () => openMemoryLifecycle(fact.fact_id) }, t("button.history"))
          : null,
        el("span", { className: "tag" }, `sources ${sourceRefs.length}`),
      ]),
    ]),
    sourceRefs.length
      ? el("div", { className: "review-source-list" }, sourceRefs.map((sourceRef, index) => reviewSourceRow(sourceRef, index)))
      : null,
    el("div", { className: "review-actions" }, [
      updatedText,
      reason,
      el(
        "button",
        {
          className: "primary-button",
          onclick: () => createMemoryUpdateReview(fact, updatedText.value, reason.value),
          ...(sourceRefs.length && updateSupported ? {} : { disabled: true }),
          title: updateSupported ? "" : updateReason,
        },
        updateSupported ? t("button.createUpdateReview") : t("button.unsupportedUpdate"),
      ),
      el(
        "button",
        {
          className: "secondary-button",
          onclick: () => createMemoryDeleteReview(fact, reason.value),
          ...(sourceRefs.length && deleteSupported ? {} : { disabled: true }),
          title: deleteSupported ? "" : deleteReason,
        },
        deleteSupported ? t("button.createDeleteReview") : t("button.unsupportedDelete"),
      ),
    ]),
  ]);
}

function memoryCardCard(card) {
  const sourceRefs = card.source_refs || [];
  const quality = card.quality || {};
  const agentView = card.agent_view || {};
  const reason = el("input", { placeholder: t("label.reviewReason"), value: "" });
  const updatedText = el("textarea", { placeholder: "Updated memory text", value: card.display_text || card.text || "" });
  const fact = {
    fact_id: card.memory_id || card.fact_id,
    text: card.text || card.display_text || "",
    source_refs: sourceRefs,
    metadata: card.metadata || {},
  };
  const updateSupported = memoryOperationSupported("update");
  const deleteSupported = memoryOperationSupported("delete");
  const updateReason = memoryCapabilityReason("update");
  const deleteReason = memoryCapabilityReason("delete");
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, card.display_text || card.memory_id || t("label.memoryCard")),
        el("p", {}, agentView.why_use || card.behavior_delta || card.text || ""),
      ]),
      el("div", { className: "card-actions" }, [
        el("span", { className: `tag ${statusClass(card.status || "pending")}` }, card.status || "active"),
        card.memory_id
          ? el("button", { className: "secondary-button", onclick: () => openMemoryLifecycle(card.memory_id) }, t("button.history"))
          : null,
        card.memory_id
          ? el("button", { className: "secondary-button", onclick: () => openMemoryTimeline(card.memory_id) }, t("button.timeline"))
          : null,
        card.memory_id
          ? el("button", { className: "secondary-button", onclick: () => explainMemoryWhyUsed(card.memory_id) }, t("button.whyUsed"))
          : null,
        card.memory_id
          ? el("button", { className: "secondary-button", onclick: () => inspectMemoryUseTrace(card.memory_id) }, t("button.useTrace"))
          : null,
      ]),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, card.memory_type || "unspecified"),
      el("span", { className: "tag" }, card.memory_scope || "scope"),
      el("span", { className: quality.needs_review ? "tag pending" : "tag ready" }, quality.needs_review ? "needs envelope" : "complete"),
      el("span", { className: "tag" }, `${t("label.sources")} ${sourceRefs.length}`),
      card.memory_id ? el("span", { className: "tag" }, shortId(card.memory_id)) : null,
    ]),
    quality.missing_fields && quality.missing_fields.length
      ? el("p", { className: "empty-list" }, `缺少字段：${quality.missing_fields.join(", ")}`)
      : null,
    sourceRefs.length
      ? el("div", { className: "review-source-list" }, sourceRefs.map((sourceRef, index) => reviewSourceRow(sourceRef, index)))
      : null,
    card.status === "active"
      ? el("div", { className: "review-actions" }, [
          updatedText,
          reason,
          el(
            "button",
            {
              className: "primary-button",
              onclick: () => createMemoryUpdateReview(fact, updatedText.value, reason.value),
              ...(sourceRefs.length && updateSupported ? {} : { disabled: true }),
              title: updateSupported ? "" : updateReason,
            },
            updateSupported ? t("button.createUpdateReview") : t("button.unsupportedUpdate"),
          ),
          el(
            "button",
            {
              className: "secondary-button",
              onclick: () => createMemoryDeleteReview(fact, reason.value),
              ...(sourceRefs.length && deleteSupported ? {} : { disabled: true }),
              title: deleteSupported ? "" : deleteReason,
            },
            deleteSupported ? t("button.createDeleteReview") : t("button.unsupportedDelete"),
          ),
        ])
      : null,
  ]);
}

function memoryBriefingItemCard(item) {
  const reasons = item.reason_codes || [];
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, item.display_text || item.memory_id || "memory"),
        el("p", {}, item.behavior_delta || reasons.join(", ") || item.memory_id || ""),
      ]),
      el("div", { className: "card-actions" }, [
        el("span", { className: `tag ${statusClass(item.severity || item.status || "ready")}` }, `score ${item.attention_score || 0}`),
        item.memory_id ? el("button", { className: "secondary-button", onclick: () => openMemoryTimeline(item.memory_id) }, t("button.timeline")) : null,
        item.memory_id ? el("button", { className: "secondary-button", onclick: () => explainMemoryWhyUsed(item.memory_id) }, t("button.whyUsed")) : null,
        item.memory_id ? el("button", { className: "secondary-button", onclick: () => inspectMemoryCard(item.memory_id) }, t("button.inspect")) : null,
      ]),
    ]),
    el("div", { className: "meta-row" }, [
      item.memory_id ? el("span", { className: "tag" }, shortId(item.memory_id)) : null,
      item.memory_type ? el("span", { className: "tag" }, item.memory_type) : null,
      item.memory_scope ? el("span", { className: "tag" }, item.memory_scope) : null,
      el("span", { className: "tag" }, `${item.trace_count || 0} traces`),
      el("span", { className: "tag" }, `${item.source_count || 0} sources`),
      ...(item.issue_types || []).slice(0, 4).map((issue) => el("span", { className: "tag pending" }, issue)),
    ]),
    reasons.length ? el("p", { className: "empty-list" }, `关注原因：${reasons.join(", ")}`) : null,
  ]);
}

function memoryWhyUsedCard(payload) {
  const card = payload.card || {};
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, card.display_text || payload.memory_id || t("button.whyUsed")),
        el("p", {}, payload.explanation || ""),
      ]),
      el("div", { className: "card-actions" }, [
        el("span", { className: `tag ${statusClass(payload.confidence || "ready")}` }, payload.confidence || "trace"),
        payload.memory_id
          ? el("button", { className: "secondary-button", onclick: () => openMemoryTimeline(payload.memory_id) }, t("button.timeline"))
          : null,
      ]),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, shortId(payload.memory_id || "")),
      el("span", { className: "tag" }, `${payload.trace_count || 0} traces`),
      card.memory_type ? el("span", { className: "tag" }, card.memory_type) : null,
      card.memory_scope ? el("span", { className: "tag" }, card.memory_scope) : null,
    ]),
    payload.why_use ? el("p", {}, payload.why_use) : null,
  ]);
}

function memoryTimelineCard(payload) {
  const summary = payload.summary || {};
  const card = payload.card || {};
  const entries = payload.entries || [];
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, card.display_text || payload.memory_id || t("button.timeline")),
        el("p", {}, card.behavior_delta || "Memory Card / lifecycle / use trace / SourceRef"),
      ]),
      el("div", { className: "card-actions" }, [
        el("span", { className: `tag ${statusClass(payload.status || "ready")}` }, payload.status || "ok"),
        payload.memory_id
          ? el("button", { className: "secondary-button", onclick: () => explainMemoryWhyUsed(payload.memory_id) }, t("button.whyUsed"))
          : null,
        payload.memory_id
          ? el("button", { className: "secondary-button", onclick: () => openMemoryLifecycle(payload.memory_id) }, t("button.history"))
          : null,
      ]),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, shortId(payload.memory_id || "")),
      summary.memory_type ? el("span", { className: "tag" }, summary.memory_type) : null,
      summary.memory_scope ? el("span", { className: "tag" }, summary.memory_scope) : null,
      el("span", { className: "tag" }, `${summary.lifecycle_change_count || 0} lifecycle`),
      el("span", { className: "tag" }, `${summary.usage_trace_count || 0} usage`),
      el("span", { className: "tag" }, `${summary.source_anchor_count || 0} sources`),
    ]),
    entries.length ? el("div", { className: "source-list" }, entries.map(memoryTimelineEntryRow)) : null,
    payload.limitations && payload.limitations.length ? el("p", { className: "empty-list" }, payload.limitations[0]) : null,
  ]);
}

function memoryTimelineEntryRow(entry) {
  const evidence = entry.evidence || {};
  const detail =
    evidence.query ||
    evidence.action ||
    evidence.audit_event_id ||
    (evidence.source_ref && (evidence.source_ref.source_id || evidence.source_ref.path || evidence.source_ref.uri)) ||
    entry.confidence ||
    "";
  return el("p", {}, [
    el("strong", {}, entry.title || entry.type || "timeline"),
    ` · ${entry.occurred_at || ""}`,
    el("br"),
    entry.summary || "",
    detail ? " " : null,
    detail ? el("span", { className: "tag" }, detail) : null,
  ]);
}

function memoryUseTraceCard(trace) {
  const ids = trace.memory_ids || [];
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, trace.action || "memory trace"),
        el("p", {}, trace.interpretation || trace.query || trace.trace_id || ""),
      ]),
      el("span", { className: "tag" }, trace.created_at || ""),
    ]),
    el("div", { className: "meta-row" }, [
      trace.query ? el("span", { className: "tag" }, trace.query) : null,
      trace.caller ? el("span", { className: "tag" }, trace.caller) : null,
      trace.purpose ? el("span", { className: "tag" }, trace.purpose) : null,
      trace.run_id ? el("span", { className: "tag" }, shortId(trace.run_id)) : null,
      el("span", { className: "tag" }, `${ids.length} memories`),
    ]),
    ids.length
      ? el("div", { className: "meta-row" }, ids.slice(0, 8).map((memoryId) => el("span", { className: "tag" }, shortId(memoryId))))
      : null,
  ]);
}

function memoryHealthIssueCard(issue) {
  const cards = issue.cards || [];
  const memoryIds = issue.memory_ids || [];
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, issue.title || issue.type || "memory health"),
        el("p", {}, issue.reason || ""),
      ]),
      el("span", { className: `tag ${statusClass(issue.severity || "pending")}` }, `${issue.type || "issue"} / ${issue.severity || "medium"}`),
    ]),
    el("div", { className: "meta-row" }, [
      ...(memoryIds || []).slice(0, 6).map((memoryId) => el("span", { className: "tag" }, shortId(memoryId))),
      el("span", { className: "tag" }, issue.issue_id || ""),
    ]),
    cards.length
      ? el("div", { className: "source-list" }, cards.map((card) => el("p", {}, card.display_text || card.memory_id || "")))
      : null,
    issue.next_actions && issue.next_actions.length
      ? el("div", { className: "card-actions" }, issue.next_actions.slice(0, 3).map(memoryHealthActionButton))
      : null,
  ]);
}

function memoryHealthActionButton(action) {
  const memoryId = action.params && action.params.memory_id;
  if (action.tool === "pska_memory_card_get" && memoryId) {
    return el("button", { className: "secondary-button", onclick: () => inspectMemoryCard(memoryId) }, action.label || t("button.inspect"));
  }
  if (action.tool === "pska_memory_update_review" && memoryId) {
    return el("button", { className: "secondary-button", onclick: () => inspectMemoryCard(memoryId) }, action.label || t("button.inspect"));
  }
  return el("button", { className: "secondary-button", disabled: true }, action.label || action.action || t("button.inspect"));
}

function memoryApplyCard(memoryApply) {
  const action = memoryApplyAction(memoryApply);
  const operation = memoryApply && memoryApply.metadata && memoryApply.metadata.operation;
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, memoryApplyLabel(memoryApply)),
        el("p", {}, memoryApply.message || "Durable memory state updated."),
      ]),
      el("div", { className: "card-actions" }, [
        el("span", { className: `tag ${memoryApply.applied ? "ready" : "pending"}` }, memoryApply.applied ? "applied" : "pending"),
        memoryApply.target_id
          ? el("button", { className: "secondary-button", onclick: () => openMemoryLifecycle(memoryApply.target_id) }, t("button.history"))
          : null,
      ]),
    ]),
    el("div", { className: "meta-row" }, [
      memoryApply.backend ? el("span", { className: "tag" }, memoryApply.backend) : null,
      operation ? el("span", { className: "tag" }, operation) : null,
      el("span", { className: "tag" }, action),
      memoryApply.target_id ? el("span", { className: "tag" }, shortId(memoryApply.target_id)) : null,
    ]),
  ]);
}

function sourceManifestCard(source) {
  const sourceRef = source.source_ref || {};
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, source.title || source.context_id || t("button.source")), el("p", {}, source.source_id || "")]),
      sourceRef.adapter ? el("button", { className: "secondary-button", onclick: () => readSource(sourceRef) }, t("button.source")) : null,
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, `#${source.index || ""}`),
      el("span", { className: "tag" }, source.adapter || "adapter"),
      source.dataset_id ? el("span", { className: "tag" }, shortId(source.dataset_id)) : null,
      source.document_id ? el("span", { className: "tag" }, shortId(source.document_id)) : null,
      el("span", { className: "tag" }, `score ${Number(source.score || 0).toFixed(2)}`),
    ]),
  ]);
}

function sourceInspectionCard(source) {
  const sourceRef = source.source_ref || {};
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, sourceRef.title || sourceRef.document_id || t("button.source")), el("p", {}, source.text || "")]),
      sourceRef.adapter ? el("button", { className: "secondary-button", onclick: () => readSource(sourceRef) }, t("button.source")) : null,
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, sourceRef.adapter || "adapter"),
      sourceRef.dataset_id ? el("span", { className: "tag" }, shortId(sourceRef.dataset_id)) : null,
      sourceRef.document_id ? el("span", { className: "tag" }, shortId(sourceRef.document_id)) : null,
      sourceRef.chunk_id ? el("span", { className: "tag" }, shortId(sourceRef.chunk_id)) : null,
    ]),
  ]);
}

function syncReviewRecord(review, options = {}) {
  if (!review || !review.review_id) return false;
  const index = state.reviews.findIndex((item) => item.review_id === review.review_id);
  if (index >= 0) {
    state.reviews[index] = review;
  } else if (options.append) {
    state.reviews.push(review);
  } else {
    state.reviews.unshift(review);
  }
  if (review.memory_apply) {
    state.memoryApplyByReview[review.review_id] = review.memory_apply;
  }
  return true;
}

function memoryReviewQueueGroupCard(group) {
  const items = group.items || [];
  const batchActions = group.batch_actions || [];
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, group.title || group.code || "memory queue"),
        el("p", {}, group.reason || ""),
      ]),
      el("span", { className: `tag ${statusClass(group.severity || "pending")}` }, `${group.count || 0} items`),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, group.code || "group"),
      el("span", { className: "tag" }, group.severity || "review"),
    ]),
    batchActions.length
      ? el("div", { className: "review-actions compact-actions" }, batchActions.map((action) => memoryReviewQueueBatchActionButton(action)))
      : null,
    items.length ? el("div", { className: "source-list" }, items.slice(0, 5).map(memoryReviewQueueItemRow)) : null,
  ]);
}

function memoryReviewQueueItemRow(item) {
  const actions = (item.next_actions || []).slice(0, 3);
  const memoryId = item.memory_id || (item.memory_ids && item.memory_ids[0]) || "";
  return el("p", {}, [
    el("strong", {}, item.title || item.review_id || item.issue_id || memoryId || item.item_type || "item"),
    item.reason ? ` · ${item.reason}` : "",
    el("br"),
    item.review_id ? el("span", { className: "tag" }, shortId(item.review_id)) : null,
    memoryId ? el("span", { className: "tag" }, shortId(memoryId)) : null,
    item.status ? el("span", { className: "tag" }, item.status) : null,
    item.issue_type ? el("span", { className: "tag pending" }, item.issue_type) : null,
    actions.length
      ? el("span", { className: "card-actions" }, actions.map((action) => memoryReviewQueueActionButton(action, item)))
      : null,
  ]);
}

function memoryReviewQueueActionButton(action, item) {
  return el(
    "button",
    {
      className: "secondary-button",
      type: "button",
      onclick: () => runMemoryReviewQueueAction(action, item),
    },
    action.label || action.action || t("button.inspect"),
  );
}

function memoryReviewQueueBatchActionButton(action) {
  const decision = (action.params && action.params.decision) || "";
  const label = decision === "accept" ? t("button.acceptGroup") : decision === "reject" ? t("button.rejectGroup") : action.label;
  return el(
    "button",
    {
      className: decision === "reject" ? "danger-button" : "secondary-button",
      type: "button",
      onclick: () => decideReviewBatch(action),
    },
    label || action.action || t("button.inspect"),
  );
}

function reviewCard(review) {
  const proposal = review.proposal || {};
  const sourceRefs = review.source_refs || proposal.source_refs || [];
  const revision = review.revision || {};
  const runId = proposal.run_id || (proposal.metadata && proposal.metadata.run_id) || "";
  const candidate = memoryCandidateForProposal(proposal);
  const candidateEditor =
    review.status === "needs_edit" && proposal.kind === "memory_patch" && candidate ? memoryCandidateEditor(candidate) : null;
  const memoryOperation = memoryOperationForProposalKind(proposal.kind);
  const memoryApplySupported = memoryOperation ? memoryOperationSupported(memoryOperation) : true;
  const memoryApplyReason = memoryOperation ? memoryCapabilityReason(memoryOperation) : "";
  const actions = el("div", { className: "review-actions" }, []);
  const reason = el("input", { placeholder: t("label.reviewReason"), value: "" });
  const memoryApply = review.memory_apply || state.memoryApplyByReview[review.review_id];
  const locked = Boolean(memoryApply);
  if (runId) {
    actions.append(el("button", { className: "secondary-button", onclick: () => openWritingRun(runId) }, t("button.openWriting")));
  }
  if (locked) {
    actions.append(el("span", { className: "tag ready" }, memoryApplyLabel(memoryApply)));
    actions.append(el("span", { className: "tag" }, t("label.locked")));
    if (memoryApply.target_id) {
      actions.append(
        el("button", { className: "secondary-button", onclick: () => openMemoryLifecycle(memoryApply.target_id) }, t("button.history")),
      );
    }
  } else if (review.status === "pending") {
    actions.append(
      reason,
      el("button", { className: "primary-button", onclick: () => decideReview(review.review_id, "accept", reason.value) }, t("button.accept")),
      el("button", { className: "secondary-button", onclick: () => decideReview(review.review_id, "edit", reason.value) }, t("button.edit")),
      el("button", { className: "danger-button", onclick: () => decideReview(review.review_id, "reject", reason.value) }, t("button.reject")),
    );
  } else if (review.status === "accepted") {
    if (proposal.kind === "memory_patch") {
      actions.append(
        el(
          "button",
          {
            className: "primary-button",
            onclick: () => applyMemory(review.review_id),
            ...(memoryApplySupported ? {} : { disabled: true }),
            title: memoryApplySupported ? "" : memoryApplyReason,
          },
          memoryApplySupported ? t("button.applyMemory") : t("button.unsupportedMemoryApply"),
        ),
      );
    }
    if (proposal.kind === "memory_update") {
      actions.append(
        el(
          "button",
          {
            className: "primary-button",
            onclick: () => applyMemory(review.review_id),
            ...(memoryApplySupported ? {} : { disabled: true }),
            title: memoryApplySupported ? "" : memoryApplyReason,
          },
          memoryApplySupported ? t("button.applyMemoryUpdate") : t("button.unsupportedUpdate"),
        ),
      );
    }
    if (proposal.kind === "memory_delete") {
      actions.append(
        el(
          "button",
          {
            className: "danger-button",
            onclick: () => applyMemory(review.review_id),
            ...(memoryApplySupported ? {} : { disabled: true }),
            title: memoryApplySupported ? "" : memoryApplyReason,
          },
          memoryApplySupported ? t("button.applyMemoryDelete") : t("button.unsupportedDelete"),
        ),
      );
    }
  } else if (review.status === "needs_edit") {
    actions.append(
      reason,
      el(
        "button",
        {
          className: "primary-button",
          onclick: () => reviseReview(review.review_id, reason.value, memoryCandidateEditorPayload(candidateEditor)),
        },
        t("button.revise"),
      ),
    );
  } else if (review.status === "rejected") {
    actions.append(el("span", { className: "tag failed" }, t("label.rejected")));
  }
  return el("article", { className: review.review_id === state.focusReviewId ? "item-card highlighted" : "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, proposal.title || review.review_id), el("p", {}, proposal.body || "")]),
      el("span", { className: `tag ${review.status === "accepted" ? "ready" : "pending"}` }, review.status),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, proposal.kind || "proposal"),
      el("span", { className: "tag" }, shortId(review.review_id)),
      el("span", { className: "tag" }, `${t("label.sources")} ${review.source_count ?? sourceRefs.length}`),
      revision.previous_review_id ? el("span", { className: "tag" }, `from ${shortId(revision.previous_review_id)}`) : null,
      revision.next_review_id ? el("span", { className: "tag" }, `to ${shortId(revision.next_review_id)}`) : null,
    ]),
    candidate ? memoryCandidatePanel(candidate, candidateEditor) : null,
    sourceRefs.length
      ? el("div", { className: "review-source-list" }, sourceRefs.map((sourceRef, index) => reviewSourceRow(sourceRef, index)))
      : el("p", { className: "empty-list" }, "此审核没有关联来源追踪。"),
    actions,
  ]);
}

function memoryCandidateForProposal(proposal) {
  if (!proposal || !["memory_patch", "memory_update", "memory_delete"].includes(proposal.kind)) return null;
  const payload = proposal.memory_patch || proposal.memory_update || proposal.memory_delete || {};
  const metadata = payload.metadata || proposal.metadata || {};
  const sourceRefs = payload.source_refs || proposal.source_refs || [];
  return {
    operation: proposal.kind || metadata.semantic_operation || metadata.operation || "",
    text: payload.text || metadata.display_text || proposal.body || "",
    previous_text: payload.previous_text || metadata.previous_text || "",
    behavior_delta: metadata.behavior_delta || payload.reason || metadata.reason || "",
    memory_type: metadata.memory_type || "",
    memory_scope: metadata.memory_scope || "",
    origin: metadata.candidate_origin || metadata.origin || "",
    confidence: payload.confidence,
    target_id: payload.target_id || metadata.target_fact_id || metadata.memory_target_id || "",
    message_ids: metadata.message_ids || [],
    evidence_quotes: metadata.evidence_quotes || [],
    source_refs: sourceRefs,
  };
}

function memoryCandidatePanel(candidate, editor = null) {
  const tags = [
    candidate.memory_type ? el("span", { className: "tag" }, candidate.memory_type) : null,
    candidate.memory_scope ? el("span", { className: "tag" }, candidate.memory_scope) : null,
    candidate.origin ? el("span", { className: "tag" }, candidate.origin) : null,
    candidate.operation ? el("span", { className: "tag" }, candidate.operation) : null,
    candidate.confidence !== undefined ? el("span", { className: "tag" }, `confidence ${Number(candidate.confidence || 0).toFixed(2)}`) : null,
    candidate.target_id ? el("span", { className: "tag" }, `target ${shortId(candidate.target_id)}`) : null,
  ].filter(Boolean);
  const evidence = memoryCandidateEvidence(candidate);
  return el("section", { className: "memory-candidate-panel" }, [
    el("div", { className: "memory-candidate-header" }, [
      el("strong", {}, "记忆候选"),
      tags.length ? el("div", { className: "meta-row" }, tags) : null,
    ]),
    editor || candidate.text ? editor || el("p", { className: "memory-candidate-text" }, candidate.text) : null,
    candidate.previous_text ? memoryCandidateField("原记忆", candidate.previous_text) : null,
    !editor && candidate.behavior_delta ? memoryCandidateField("行为变化", candidate.behavior_delta) : null,
    evidence.length ? el("div", { className: "source-list" }, evidence.map(memoryCandidateEvidenceRow)) : null,
  ]);
}

function memoryCandidateEditor(candidate) {
  const text = memoryCandidateTextarea(candidate.text, 4, "候选文本");
  const behaviorDelta = memoryCandidateTextarea(candidate.behavior_delta, 3, "行为变化");
  const memoryType = memoryCandidateSelect(MEMORY_CARD_TYPES, candidate.memory_type || "project_state");
  const memoryScope = memoryCandidateSelect(MEMORY_CARD_SCOPES, candidate.memory_scope || "workspace");
  const editor = el("div", { className: "memory-candidate-editor" }, [
    el("label", {}, ["候选文本", text]),
    el("label", {}, ["行为变化", behaviorDelta]),
    el("div", { className: "form-row" }, [
      el("label", {}, ["类型", memoryType]),
      el("label", {}, ["范围", memoryScope]),
    ]),
  ]);
  editor.memoryCandidateInputs = { text, behaviorDelta, memoryType, memoryScope };
  return editor;
}

function memoryCandidateEditorPayload(editor) {
  const inputs = editor && editor.memoryCandidateInputs;
  if (!inputs) return null;
  return {
    text: inputs.text.value.trim(),
    behavior_delta: inputs.behaviorDelta.value.trim(),
    memory_type: inputs.memoryType.value,
    memory_scope: inputs.memoryScope.value,
  };
}

function memoryCandidateTextarea(value, rows, ariaLabel) {
  const node = el("textarea", { rows: String(rows), "aria-label": ariaLabel });
  node.value = value || "";
  return node;
}

function memoryCandidateSelect(options, selected) {
  const node = el(
    "select",
    {},
    options.map((option) => el("option", { value: option }, option)),
  );
  node.value = options.includes(selected) ? selected : options[0];
  return node;
}

function memoryCandidateField(label, value) {
  return el("p", { className: "memory-candidate-field" }, [el("strong", {}, `${label}: `), value]);
}

function memoryCandidateEvidence(candidate) {
  const rows = [];
  (candidate.message_ids || []).forEach((messageId) => rows.push({ label: "消息", value: shortId(messageId) }));
  (candidate.evidence_quotes || []).forEach((quote) => rows.push({ label: "证据", value: quote }));
  (candidate.source_refs || []).forEach((sourceRef) => {
    const metadata = sourceRef.metadata || {};
    if (metadata.message_excerpt) rows.push({ label: "消息摘录", value: metadata.message_excerpt });
    else if (sourceRef.title || sourceRef.path || sourceRef.source_id || sourceRef.external_id) {
      rows.push({
        label: sourceRef.adapter || "来源",
        value: sourceRef.title || sourceRef.path || sourceRef.source_id || sourceRef.external_id,
      });
    }
  });
  return rows.slice(0, 6);
}

function memoryCandidateEvidenceRow(item) {
  return el("p", { className: "memory-candidate-evidence" }, [el("span", { className: "tag" }, item.label), item.value || ""]);
}

function reviewSourceRow(sourceRef, index) {
  return el("div", { className: "review-source-row" }, [
    el("div", {}, [
      el("strong", {}, sourceRef.title || sourceRef.document_id || sourceRef.source_id || `${t("button.source")} ${index + 1}`),
      el(
        "span",
        {},
        `${sourceRef.adapter || "adapter"} / ${shortId(sourceRef.document_id || sourceRef.source_id || sourceRef.external_id || "")}`,
      ),
    ]),
    el("button", { className: "secondary-button", onclick: () => readSource(sourceRef) }, t("button.source")),
  ]);
}

function workflowCard(workflow) {
  const blockedByKb = workflow.metadata && workflow.metadata.blocked_reason === "kb_not_ready";
  const resumable = resumableAskFor(workflow.run_id);
  const canResume = !resumable || Boolean(resumable.can_resume);
  const resumeLabel =
    isIngestLoopResume(resumable && resumable.resume) || hasIngestLoopResume((resumable && resumable.run) || workflow)
      ? t("button.resumeLoop")
      : t("button.resumeAsk");
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, workflow.intent || workflow.run_id),
        el("p", {}, `${workflow.context_packets ? workflow.context_packets.length : 0} context packets`),
      ]),
      el("div", { className: "result-actions" }, [
        blockedByKb
          ? el(
              "button",
              {
                className: "primary-button",
                onclick: () =>
                  canResume
                    ? resumeBlockedRun(workflow.run_id)
                    : openBlockedAskRun(workflow.run_id, { track: true }),
              },
              canResume ? resumeLabel : t("button.track"),
            )
          : null,
        el("button", { className: "secondary-button", onclick: () => openWorkflowRun(workflow.run_id) }, "Open"),
      ]),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, shortId(workflow.run_id || "")),
      el("span", { className: "tag" }, workflow.status || "active"),
      resumable
        ? el(
            "span",
            { className: `tag ${statusClass(resumable.readiness && resumable.readiness.status)}` },
            resumable.can_resume ? "ready to resume" : resumable.readiness.status || "not ready",
          )
        : null,
    ]),
  ]);
}

function resumableAskCard(record) {
  const run = record.run || {};
  const askRequest = record.ask_request || {};
  const readiness = record.readiness || {};
  const resumeLabel = isIngestLoopResume(record.resume) || hasIngestLoopResume(run) ? t("button.resumeLoop") : t("button.resumeAsk");
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, askRequest.question || run.intent || "Blocked Ask"),
        el("p", {}, record.message || readiness.message || ""),
      ]),
      el("span", { className: `tag ${statusClass(readiness.status)}` }, readiness.status || "unknown"),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, shortId(run.run_id || "")),
      el("span", { className: `tag ${record.can_resume ? "ready" : "pending"}` }, record.can_resume ? "can resume" : "waiting"),
    ]),
    el("div", { className: "result-actions" }, [
      el(
        "button",
        {
          className: "primary-button",
          onclick: () =>
            record.can_resume
              ? resumeBlockedRun(run.run_id)
              : openBlockedAskRun(run.run_id, { track: true }),
        },
        record.can_resume ? resumeLabel : t("button.track"),
      ),
      el("button", { className: "secondary-button", onclick: () => openBlockedAskRun(run.run_id) }, t("button.openAsk")),
    ]),
  ]);
}

function resumableAskFor(runId) {
  return state.resumableAsks.find((record) => record.run && record.run.run_id === runId) || null;
}

function resumeContractForResult(result) {
  return result && result.resume && typeof result.resume === "object" ? result.resume : null;
}

function resumeContractForRun(runId) {
  const current =
    state.currentAskResult &&
    state.currentAskResult.run &&
    state.currentAskResult.run.run_id === runId
      ? resumeContractForResult(state.currentAskResult)
      : null;
  if (current) return current;
  const record = resumableAskFor(runId);
  if (record && record.resume) return record.resume;
  const run =
    (record && record.run) ||
    state.workflows.find((workflow) => workflow.run_id === runId) ||
    {};
  const metadata = ingestLoopResumeMetadata(run);
  if (!metadata) return null;
  const exportFormat = metadata.export_format || "";
  return {
    tool: "pska_ingest_loop_resume",
    params: { run_id: runId, export_format: exportFormat },
  };
}

function isIngestLoopResume(resume) {
  return Boolean(resume && resume.tool === "pska_ingest_loop_resume");
}

function ingestLoopResumeMetadata(run) {
  const metadata = run && run.metadata && run.metadata.ingest_loop;
  return metadata && typeof metadata === "object" ? metadata : null;
}

function hasIngestLoopResume(run) {
  return Boolean(ingestLoopResumeMetadata(run));
}

function askResultFromResumableRecord(record) {
  const run = record.run || {};
  return {
    status: "not_ready",
    message: record.message || "Selected knowledge scope is still not ready.",
    run,
    readiness: record.readiness || (run.metadata && run.metadata.readiness) || {},
    resume: record.resume || null,
    next_actions: record.next_actions || [],
    loop: (run.metadata && run.metadata.agentic_loop) || {},
    artifact: { run },
    context_packets: [],
    proposal: null,
    review: null,
    review_decision: null,
    memory_apply: null,
    memory_facts: [],
    brief: "",
  };
}

function diagnosticCard(check) {
  const metadata = check.metadata || {};
  const tags = [];
  if (metadata.provider) {
    tags.push(el("span", { className: "tag" }, metadata.provider));
  }
  if (metadata.health_checked) {
    tags.push(el("span", { className: "tag ready" }, "health checked"));
  }
  if (metadata.dataset_sample_count !== undefined) {
    tags.push(el("span", { className: "tag" }, `datasets sampled: ${metadata.dataset_sample_count}`));
  }
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, readableName(check.name)),
        el("p", {}, check.message || ""),
      ]),
      el("span", { className: `tag ${statusClass(check.status)}` }, check.status || "unknown"),
    ]),
    tags.length ? el("div", { className: "meta-row" }, tags) : null,
  ]);
}

function retrievalProbeCard(probe) {
  const error = probe.error || {};
  const readiness = probe.readiness || {};
  const sourceRefs = probe.source_refs || [];
  const tags = [
    el("span", { className: "tag" }, probe.provider || "provider"),
    el("span", { className: `tag ${statusClass(readiness.status)}` }, readiness.status || "readiness"),
    el("span", { className: "tag" }, `context ${probe.context_count || 0}`),
  ];
  if (error.type) tags.push(el("span", { className: "tag error" }, error.type));
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, "Retrieval Probe"), el("p", {}, probe.message || "")]),
      el("span", { className: `tag ${statusClass(probe.status)}` }, probe.status || "unknown"),
    ]),
    el("div", { className: "meta-row" }, tags),
    sourceRefs.length
      ? el("div", { className: "review-source-list" }, sourceRefs.map((sourceRef, index) => reviewSourceRow(sourceRef, index)))
      : null,
  ]);
}

function componentCheckCard(result) {
  const providers = result.providers || {};
  const scope = result.scope || {};
  const tags = [
    el("span", { className: "tag" }, `kb ${providers.kb || "unknown"}`),
    el("span", { className: "tag" }, `retrieval ${providers.retrieval || "unknown"}`),
    el("span", { className: "tag" }, `memory ${providers.memory || "unknown"}`),
  ];
  const datasetIds = scope.dataset_ids || [];
  if (datasetIds.length) tags.push(el("span", { className: "tag" }, `datasets ${datasetIds.length}`));
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, t("heading.componentCheck")), el("p", {}, result.message || "")]),
      el("span", { className: `tag ${statusClass(result.status)}` }, result.status || "unknown"),
    ]),
    el("div", { className: "meta-row" }, tags),
    result.steps && result.steps.length
      ? el(
          "ol",
          { className: "compact-list" },
          result.steps.map((step) =>
            el("li", {}, [
              el("span", { className: `tag ${statusClass(step.status)}` }, step.status || "unknown"),
              ` ${readableName(step.name)}${step.required === false ? " (optional)" : ""}: ${step.message || ""}`,
            ]),
          ),
        )
      : null,
  ]);
}

function evalResultCard(result) {
  const providers = result.providers || {};
  const artifacts = result.artifacts || {};
  const tags = [
    el("span", { className: "tag" }, result.suite || "eval"),
    el("span", { className: "tag" }, `kb ${providers.kb || "unknown"}`),
    el("span", { className: "tag" }, `retrieval ${providers.retrieval || "unknown"}`),
    el("span", { className: "tag" }, `memory ${providers.memory || "unknown"}`),
  ];
  if (artifacts.ready_run_id) tags.push(el("span", { className: "tag" }, `ready ${shortId(artifacts.ready_run_id)}`));
  if (artifacts.resumed_run_id) tags.push(el("span", { className: "tag" }, `resumed ${shortId(artifacts.resumed_run_id)}`));
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, t("heading.productAcceptance")), el("p", {}, result.message || "")]),
      el("span", { className: `tag ${statusClass(result.status)}` }, result.status || "unknown"),
    ]),
    el("div", { className: "meta-row" }, tags),
    result.steps && result.steps.length
      ? el(
          "ol",
          { className: "compact-list" },
          result.steps.map((step) =>
            el("li", {}, [
              el("span", { className: `tag ${statusClass(step.status)}` }, step.status || "unknown"),
              ` ${readableName(step.name)}: ${step.message || ""}`,
            ]),
          ),
        )
      : null,
  ]);
}

function memoryProbeCard(probe) {
  const error = probe.error || {};
  const tags = [
    el("span", { className: "tag" }, probe.provider || "provider"),
    el("span", { className: "tag" }, `facts ${probe.memory_count || 0}`),
  ];
  if (error.type) tags.push(el("span", { className: "tag error" }, error.type));
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, t("heading.memoryProbe")), el("p", {}, probe.message || "")]),
      el("span", { className: `tag ${statusClass(probe.status)}` }, probe.status || "unknown"),
    ]),
    el("div", { className: "meta-row" }, tags),
  ]);
}

function closedLoopProbeCard(probe) {
  const providers = probe.providers || {};
  const ask = probe.ask || {};
  const exported = probe.export || {};
  const tags = [
    el("span", { className: "tag" }, `kb ${providers.kb || "unknown"}`),
    el("span", { className: "tag" }, `retrieval ${providers.retrieval || "unknown"}`),
    el("span", { className: "tag" }, `context ${probe.context_count || 0}`),
  ];
  if (probe.run_id) tags.push(el("span", { className: "tag" }, shortId(probe.run_id)));
  if (ask.proposal_kind) tags.push(el("span", { className: "tag" }, ask.proposal_kind));
  if (exported.exported) tags.push(el("span", { className: "tag ready" }, "exported"));
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, t("heading.liveClosedLoop")), el("p", {}, probe.message || "")]),
      el("span", { className: `tag ${statusClass(probe.status)}` }, probe.status || "unknown"),
    ]),
    el("div", { className: "meta-row" }, tags),
    probe.steps && probe.steps.length
      ? el(
          "ol",
          { className: "compact-list" },
          probe.steps.map((step) =>
            el("li", {}, [
              el("span", { className: `tag ${statusClass(step.status)}` }, step.status || "unknown"),
              ` ${readableName(step.name)}: ${step.message || ""}`,
            ]),
          ),
        )
      : null,
  ]);
}

function auditEventCard(event) {
  const metadata = event.metadata || {};
  const tags = [
    el("span", { className: "tag" }, event.target_type || "target"),
    el("span", { className: "tag" }, shortId(event.target_id || "")),
  ];
  if (metadata.format) tags.push(el("span", { className: "tag" }, metadata.format));
  if (metadata.status) tags.push(el("span", { className: `tag ${statusClass(metadata.status)}` }, metadata.status));
  if (metadata.backend) tags.push(el("span", { className: "tag" }, metadata.backend));
  if (metadata.context_count !== undefined) tags.push(el("span", { className: "tag" }, `context: ${metadata.context_count}`));
  if (metadata.source_count !== undefined) tags.push(el("span", { className: "tag" }, `sources: ${metadata.source_count}`));
  if (metadata.proposal_kind) tags.push(el("span", { className: "tag" }, metadata.proposal_kind));
  if (metadata.memory_target_id) tags.push(el("span", { className: "tag" }, shortId(metadata.memory_target_id)));
  if (metadata.document_count !== undefined) tags.push(el("span", { className: "tag" }, `documents: ${metadata.document_count}`));
  if (metadata.document_id) tags.push(el("span", { className: "tag" }, `doc ${shortId(metadata.document_id)}`));
  if (metadata.chunk_id) tags.push(el("span", { className: "tag" }, `chunk ${shortId(metadata.chunk_id)}`));
  if (metadata.dataset_name) tags.push(el("span", { className: "tag" }, metadata.dataset_name));
  if (metadata.parse_started !== undefined) {
    tags.push(el("span", { className: `tag ${metadata.parse_started ? "ready" : "pending"}` }, metadata.parse_started ? "parse started" : "parse skipped"));
  }
  if (metadata.provider) tags.push(el("span", { className: "tag" }, metadata.provider));
  if (metadata.error_type) tags.push(el("span", { className: "tag error" }, metadata.error_type));
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, event.action || "audit.event"),
        el("p", {}, auditSummary(event)),
      ]),
      el("span", { className: "tag ready" }, "recorded"),
    ]),
    el("div", { className: "meta-row" }, tags),
  ]);
}

function auditSummary(event) {
  const metadata = event.metadata || {};
  if (event.action === "kb.ingest") {
    const names = (metadata.document_names || []).join(", ");
    return names ? `Ingested ${names}` : `${metadata.document_count || 0} document(s) ingested.`;
  }
  if (event.action === "kb.parse") {
    return `${(metadata.document_ids || []).length} document(s) sent to parsing.`;
  }
  if (event.action === "kb.dataset.create") {
    return `Dataset ${metadata.dataset_name || event.target_id || ""} created.`;
  }
  if (event.action === "kb.graph.read") {
    return `Graph read for document ${shortId(metadata.document_id || event.target_id || "")}.`;
  }
  if (event.action === "source.read") {
    return `Source opened from ${metadata.adapter || "adapter"} ${shortId(metadata.document_id || metadata.source_id || event.target_id || "")}.`;
  }
  if (event.action === "source.scan") {
    return `Scanned source root ${metadata.root_label || shortId(event.target_id || "")} with ${metadata.indexed || metadata.indexed_count || metadata.object_count || 0} indexed item(s).`;
  }
  if (event.action === "source.audit.run") {
    return `Source audit found ${metadata.duplicate_group_count || 0} duplicate group(s), ${metadata.unresolved_link_count || 0} unresolved link(s), and ${metadata.unlinked_markdown_count || 0} unlinked note(s).`;
  }
  if (event.action === "source.audit_job.enqueue") {
    return `Queued source audit job ${shortId(event.target_id || "")}.`;
  }
  if (event.action === "source.audit_job.due") {
    return `Activated due source audit job ${shortId(event.target_id || "")}.`;
  }
  if (event.action === "source.audit_job.run") {
    return `Source audit job ${metadata.status || "recorded"} for ${shortId(event.target_id || "")}.`;
  }
  if (event.action === "source.extraction_job.enqueue") {
    return `Queued source extraction job ${shortId(event.target_id || "")}.`;
  }
  if (event.action === "source.extraction_job.run") {
    return `Source extraction job ${metadata.status || "recorded"} for ${shortId(event.target_id || "")}.`;
  }
  if (event.action === "source.obsidian_moc.propose") {
    return `Obsidian MOC proposal created for ${metadata.moc_path || "MOC"} with ${metadata.link_count || 0} link(s).`;
  }
  if (event.action === "source.obsidian_moc.apply") {
    return `Obsidian MOC ${metadata.changed ? "updated" : "checked"} at ${metadata.moc_path || "MOC"}.`;
  }
  if (event.action === "source.memory_review.create") {
    return `Source memory review created for ${metadata.memory_type || "source_route"} with ${metadata.source_count || 0} source(s).`;
  }
  if (event.action === "source.saved_search.create") {
    return `Saved source search ${metadata.label || event.target_id || ""}.`;
  }
  if (event.action === "source.tag.propose") {
    return `Proposed source tag ${metadata.tag || ""}.`;
  }
  if (event.action === "source.tag.apply") {
    return `Applied source tag ${metadata.tag || ""}.`;
  }
  if (event.action === "source.comment.propose") {
    return "Proposed source comment.";
  }
  if (event.action === "source.comment.apply") {
    return "Applied source comment.";
  }
  if (event.action === "retrieval.probe") {
    return `Retrieval probe ${metadata.status || "recorded"} with ${metadata.context_count || 0} context packet(s).`;
  }
  if (event.action === "memory.probe") {
    return `Memory probe ${metadata.status || "recorded"} with ${metadata.memory_count || 0} fact(s).`;
  }
  if (event.action === "eval.run") {
    return `Eval ${metadata.suite || event.target_id || "suite"} ${metadata.status || "recorded"} with ${metadata.step_count || 0} step(s).`;
  }
  if (event.action === "workflow.export") {
    return `Exported ${metadata.format || "work product"} with ${metadata.source_count || 0} source(s).`;
  }
  if (event.action === "memory.apply") {
    return `Applied durable memory through ${metadata.backend || "memory backend"}.`;
  }
  if (event.action === "memory.update") {
    return `Updated durable memory through ${metadata.backend || "memory backend"}.`;
  }
  if (event.action === "memory.delete") {
    return `Deleted durable memory through ${metadata.backend || "memory backend"}.`;
  }
  if (event.action === "memory.search") {
    return `Searched durable memory and found ${metadata.count || 0} fact(s).`;
  }
  if (event.action === "review.decide") {
    return `Review ${metadata.decision || metadata.status || "decided"}.`;
  }
  if (event.action === "review.create") {
    return `Review created for ${metadata.proposal_kind || "proposal"}.`;
  }
  if (event.action === "review.revise") {
    return `Review revision created for ${metadata.proposal_kind || "proposal"}.`;
  }
  return event.created_at || "";
}

async function openWorkflowRun(runId) {
  const payload = await api(`/api/workflows/${encodeURIComponent(runId)}`);
  const artifact = payload.artifact || {};
  const workflow = artifact.run || payload.workflow || state.workflows.find((item) => item.run_id === runId) || { run_id: runId };
  const loopStatus = workflow.metadata && workflow.metadata.agentic_loop && workflow.metadata.agentic_loop.status;
  state.currentBrief = {
    run: workflow,
    artifact,
    brief: "",
    status: loopStatus || workflow.status || "active",
    memory_facts: artifact.memory_facts || [],
    memory_attribution: artifact.memory_attribution || null,
    memory_suggestions: artifact.memory_suggestions || null,
  };
  renderWriting();
  document.querySelector('.nav-item[data-view="writing"]').click();
}

async function openBlockedAskRun(runId, options = {}) {
  await loadResumableAsks();
  const record = resumableAskFor(runId);
  if (!record) {
    showToast("没有找到被阻塞的提问。");
    openView("activity");
    return;
  }
  if (record.can_resume && options.track) {
    await resumeBlockedRun(runId);
    return;
  }
  const result = askResultFromResumableRecord(record);
  state.currentAskResult = result;
  state.currentBrief = null;
  state.lastRunId = runId;
  renderAskResult(result);
  renderWriting();
  openView("ask");
  if (options.track) {
    startBlockedAskTracking(runId);
  }
}

async function resumeBlockedRun(runId) {
  const resume = resumeContractForRun(runId);
  if (isIngestLoopResume(resume)) {
    const params = resume.params || {};
    await resumeIngestLoopRun(runId, params.export_format || "");
    return;
  }
  await resumeAskRun(runId);
}

async function resumeIngestLoopRun(runId, exportFormat = "") {
  stopBlockedAskTracking(runId);
  const payload = await api(`/api/workflows/${encodeURIComponent(runId)}/resume-ingest-loop`, {
    method: "POST",
    body: { export_format: exportFormat || "" },
  });
  const result = payload.ingest_loop || {};
  await loadWorkflows();
  if (result.review) {
    syncReviewRecord(result.review);
    await loadReviews();
    await loadPendingReviews();
  }
  if (result.review && result.memory_apply) {
    syncMemoryApply(result.review.review_id, result.memory_apply);
  }
  await loadResumableAsks();
  await loadWorkspaceStatus();
  await loadAuditEvents(auditActionForIngestLoop(result));
  if (result.status === "ok" && result.run_id) {
    openLoopWorkProduct(result);
    showToast("闭环已恢复并导出。");
    return;
  }
  await applyAskResult(result, {
    toast: result.status === "ready" ? "闭环已恢复。" : "知识范围仍在处理中。",
  });
  document.querySelector('.nav-item[data-view="ask"]').click();
}

async function resumeAskRun(runId) {
  stopBlockedAskTracking(runId);
  const result = await api(`/api/workflows/${encodeURIComponent(runId)}/resume-ask`, { method: "POST", body: {} });
  await applyAskResult(result, {
    toast: result.status === "ready" ? "提问已恢复。" : "知识范围仍在处理中。",
  });
  document.querySelector('.nav-item[data-view="ask"]').click();
}

async function refreshBlockedAskReadiness(runId) {
  await loadResumableAsks();
  await loadWorkspaceStatus();
  const record = resumableAskFor(runId);
  if (record && state.currentAskResult && state.currentAskResult.run && state.currentAskResult.run.run_id === runId) {
    state.currentAskResult.readiness = record.readiness || state.currentAskResult.readiness;
    state.currentAskResult.message = record.message || state.currentAskResult.message;
    renderAskResult(state.currentAskResult);
  }
  showToast(record && record.can_resume ? "知识范围已可恢复。" : "知识范围仍在处理中。");
  return record || null;
}

function startBlockedAskTracking(runId) {
  stopBlockedAskTracking();
  state.blockedAskPoll = {
    runId,
    attempts: 0,
    maxAttempts: 120,
    timer: null,
  };
  renderAskResult(state.currentAskResult || {});
  showToast("正在跟踪本次提问的就绪状态。");
  state.blockedAskPoll.timer = window.setInterval(async () => {
    if (!state.blockedAskPoll || state.blockedAskPoll.runId !== runId) return;
    state.blockedAskPoll.attempts += 1;
    try {
      const record = await refreshBlockedAskReadiness(runId);
      if (record && record.can_resume) {
        stopBlockedAskTracking(runId);
        showToast("知识范围已就绪，正在恢复流程。");
        await resumeBlockedRun(runId);
      } else if (state.blockedAskPoll && state.blockedAskPoll.attempts >= state.blockedAskPoll.maxAttempts) {
        stopBlockedAskTracking(runId);
        showToast("就绪跟踪已暂停。");
      }
    } catch (error) {
      stopBlockedAskTracking(runId);
      showToast(error.message);
    }
  }, 2500);
}

function stopBlockedAskTracking(runId = "") {
  if (runId && state.blockedAskPoll && state.blockedAskPoll.runId !== runId) return;
  const stoppedRunId = state.blockedAskPoll && state.blockedAskPoll.runId;
  if (state.blockedAskPoll && state.blockedAskPoll.timer) {
    window.clearInterval(state.blockedAskPoll.timer);
  }
  state.blockedAskPoll = null;
  if (
    stoppedRunId &&
    state.currentAskResult &&
    state.currentAskResult.status === "not_ready" &&
    state.currentAskResult.run &&
    state.currentAskResult.run.run_id === stoppedRunId
  ) {
    renderAskResult(state.currentAskResult);
  }
}

async function openWritingRun(runId) {
  if (state.currentAskResult && state.currentAskResult.run && state.currentAskResult.run.run_id === runId) {
    state.currentBrief = {
      run: state.currentAskResult.run,
      artifact: state.currentAskResult.artifact || {
        run: state.currentAskResult.run,
        latest_proposal: state.currentAskResult.proposal,
        proposals: state.currentAskResult.proposal ? [state.currentAskResult.proposal] : [],
        context_packets: state.currentAskResult.context_packets || [],
        memory_facts: state.currentAskResult.memory_facts || [],
        source_manifest: [],
      },
      brief: state.currentAskResult.brief || "",
      status: state.currentAskResult.status,
      proposal: state.currentAskResult.proposal,
      review: state.currentAskResult.review,
      review_decision: state.currentAskResult.review_decision,
      memory_apply: state.currentAskResult.memory_apply,
      memory_facts: state.currentAskResult.memory_facts || [],
      memory_attribution:
        state.currentAskResult.memory_attribution ||
        (state.currentAskResult.artifact && state.currentAskResult.artifact.memory_attribution) ||
        null,
      memory_suggestions:
        state.currentAskResult.memory_suggestions ||
        (state.currentAskResult.artifact && state.currentAskResult.artifact.memory_suggestions) ||
        null,
    };
    renderWriting();
    document.querySelector('.nav-item[data-view="writing"]').click();
    return;
  }
  await openWorkflowRun(runId);
}

async function openReview(reviewId) {
  setReviewStatusFilter("");
  state.focusReviewId = reviewId;
  const payload = await api(`/api/reviews/${encodeURIComponent(reviewId)}`);
  if (!syncReviewRecord(payload.review)) {
    throw new Error("未找到异常审核项。");
  }
  state.reviewView = [payload.review, ...state.reviewView.filter((review) => review.review_id !== reviewId)];
  renderReviews();
  renderHome();
  document.querySelector('.nav-item[data-view="review"]').click();
  showToast("异常审核已打开。");
}

async function runMemoryReviewQueueAction(action, item = {}) {
  const params = action.params || {};
  const reviewId = params.review_id || item.review_id || "";
  const memoryId = params.memory_id || item.memory_id || (item.memory_ids && item.memory_ids[0]) || "";
  if (action.action === "apply_accepted_memory" && reviewId) {
    await openReview(reviewId);
    await applyMemory(reviewId);
    await loadMemoryReviewQueue();
    return;
  }
  if ((action.tool === "pska_review_get" || action.action === "open_review" || action.action === "review_pending_durable_knowledge") && reviewId) {
    await openReview(reviewId);
    return;
  }
  if (action.tool === "pska_memory_candidate_dedup" || action.action === "inspect_duplicate_memory_candidates") {
    await api("/api/memory/candidate-dedup?review_limit=100&similarity_threshold=0.82");
    await loadMemoryReviewQueue({ toast: true });
    openView("review");
    return;
  }
  if (action.tool === "pska_review_merge_candidates" || action.action === "merge_candidate_group") {
    await mergeMemoryCandidateGroup(action);
    return;
  }
  if (action.tool === "pska_memory_health_scan" || action.action === "inspect_memory_health") {
    openView("memory");
    await loadMemoryHealth({ toast: true });
    return;
  }
  if (action.tool === "pska_memory_timeline" && memoryId) {
    await openMemoryTimeline(memoryId);
    return;
  }
  if (action.tool === "pska_memory_why_used" && memoryId) {
    await explainMemoryWhyUsed(memoryId);
    openView("memory");
    return;
  }
  if (memoryId) {
    await inspectMemoryCard(memoryId);
    return;
  }
  showToast(action.label || action.action || "无法执行该操作。");
}

async function mergeMemoryCandidateGroup(action) {
  const params = action.params || {};
  const reviewIds = params.review_ids || [];
  if (reviewIds.length < 2) return;
  const text = window.prompt("合并后的候选记忆文本");
  if (!text || !text.trim()) return;
  const behaviorDelta = window.prompt("这条记忆应如何改变未来行为？");
  if (!behaviorDelta || !behaviorDelta.trim()) return;
  const payload = await api("/api/reviews/merge-candidates", {
    method: "POST",
    body: {
      review_ids: reviewIds,
      reason: action.label || "merge candidate group",
      memory_candidate: {
        text: text.trim(),
        behavior_delta: behaviorDelta.trim(),
        memory_type: params.memory_type || "project_state",
        memory_scope: params.memory_scope || "workspace",
      },
    },
  });
  syncReviewRecord(payload.review);
  state.focusReviewId = payload.review && payload.review.review_id;
  setReviewStatusFilter("");
  await loadReviews();
  await loadPendingReviews();
  await loadMemoryReviewQueue();
  await loadWorkspaceStatus();
  await loadAuditEvents("review.merge_candidates");
  renderCurrentResultSurfaces();
  showToast(t("toast.reviewCandidatesMerged"));
}

async function exportCurrent(format) {
  if (!state.currentBrief || !state.currentBrief.run || !state.currentBrief.run.run_id) {
    showToast("尚未选择运行。");
    return;
  }
  await exportWorkflow(state.currentBrief.run.run_id, format);
}

async function exportWorkflow(runId, format, options = {}) {
  const selectedRunId = String(runId || "").trim();
  if (!selectedRunId) {
    showToast("尚未选择运行。");
    return;
  }
  try {
    const payload = await api(`/api/workflows/${encodeURIComponent(selectedRunId)}/export?format=${encodeURIComponent(format)}`);
    const content = typeof payload.export === "string" ? payload.export : JSON.stringify(payload.export, null, 2);
    const current =
      state.currentBrief && state.currentBrief.run && state.currentBrief.run.run_id === selectedRunId
        ? state.currentBrief
        : {
            run: state.workflows.find((workflow) => workflow.run_id === selectedRunId) || { run_id: selectedRunId },
            artifact: {},
            status: "ready",
          };
    state.currentBrief = current;
    state.currentBrief.brief = content;
    if (payload.export && typeof payload.export === "object") {
      state.currentBrief.artifact = payload.export;
      state.currentBrief.memory_attribution = payload.export.memory_attribution || null;
      state.currentBrief.memory_suggestions = payload.export.memory_suggestions || null;
      state.currentBrief.memory_facts = payload.export.memory_facts || state.currentBrief.memory_facts || [];
    }
    renderWriting();
    await loadAuditEvents("workflow.export");
    if (options.openWriting) {
      document.querySelector('.nav-item[data-view="writing"]').click();
    }
    showToast(`${format.toUpperCase()} 导出已加载。`);
  } catch (error) {
    showToast(error.message);
  }
}

async function createMemoryReviewFromRun(runId = "") {
  const selectedRunId = String(
    runId || (state.currentBrief && state.currentBrief.run && state.currentBrief.run.run_id) || "",
  ).trim();
  if (!selectedRunId) {
    showToast("尚未选择工作流。");
    return;
  }
  const intent =
    (state.currentBrief && state.currentBrief.run && state.currentBrief.run.intent) ||
    (state.currentAskResult && state.currentAskResult.run && state.currentAskResult.run.intent) ||
    "";
  const payload = await api(`/api/workflows/${encodeURIComponent(selectedRunId)}/memory-review`, {
    method: "POST",
    body: { intent },
  });
  setReviewStatusFilter("");
  syncReviewRecord(payload.review);
  state.focusReviewId = payload.review && payload.review.review_id;
  syncWorkflowMemoryReview(selectedRunId, payload);
  await loadReviews();
  await loadPendingReviews();
  await loadWorkflows();
  await loadWorkspaceStatus();
  await loadAuditEvents(payload.memory_apply ? memoryApplyAction(payload.memory_apply) : "review.create");
  renderCurrentResultSurfaces();
  document.querySelector('.nav-item[data-view="review"]').click();
  showToast(payload.memory_apply ? memoryApplyToast(payload.memory_apply) : "异常审核已创建。");
}

async function createSourceMemoryReview(params = {}) {
  const sourceRefs = params.source_refs || (params.source_ref ? [params.source_ref] : []);
  if (!sourceRefs.length) {
    openView("sources");
    showToast("没有可提升为记忆的资料源。");
    return;
  }
  const payload = await api("/api/sources/memory-reviews", {
    method: "POST",
    body: {
      source_refs: sourceRefs,
      text: params.text || "Route related questions to this source before broad search.",
      memory_type: params.memory_type || "source_route",
      behavior_delta: params.behavior_delta || "Inspect this source before broad search for related questions.",
      memory_scope: params.memory_scope || "workspace",
      reason: params.reason || "source route candidate",
      confidence: params.confidence || 0.82,
      scope: params.scope || {},
    },
  });
  setReviewStatusFilter("");
  if (payload.review) {
    syncReviewRecord(payload.review);
    state.focusReviewId = payload.review.review_id;
  }
  if (payload.review && payload.memory_apply) {
    syncMemoryApply(payload.review.review_id, payload.memory_apply);
  }
  await loadReviews();
  await loadPendingReviews();
  await loadWorkflows();
  await loadWorkspaceStatus();
  await loadAuditEvents(payload.memory_apply ? memoryApplyAction(payload.memory_apply) : "source.memory_review.create");
  openView("review");
  showToast(payload.memory_apply ? memoryApplyToast(payload.memory_apply) : t("toast.sourceMemoryReviewCreated"));
}

async function createSourceMemoryCandidatesFromAudit(params = {}) {
  const payload = await api("/api/sources/memory-candidates/from-audit", {
    method: "POST",
    body: {
      scope: params.scope || {},
      audit_limit: params.audit_limit || 20,
      candidate_limit: params.candidate_limit || 5,
      memory_scope: params.memory_scope || "project",
      dedupe_existing: params.dedupe_existing !== false,
    },
  });
  (payload.created || []).forEach((item) => {
    if (item.review_id) state.focusReviewId = item.review_id;
  });
  await loadReviews();
  await loadPendingReviews();
  await loadWorkspaceStatus();
  await loadAuditEvents("source.memory_candidates.from_audit");
  openView(payload.created_count ? "review" : "sources");
  showToast(
    payload.created_count
      ? `${t("toast.sourceMemoryCandidatesCreated")} ${payload.created_count} 个；跳过 ${payload.skipped_count || 0} 个。`
      : "没有新的资料源记忆候选。",
  );
}

async function proposeObsidianMoc(params = {}) {
  const sourceRefs = params.source_refs || (params.source_ref ? [params.source_ref] : []);
  if (!params.root_id || !sourceRefs.length) {
    openView("sources");
    showToast("没有可生成 MOC 的 Obsidian 资料源。");
    return;
  }
  await api("/api/sources/obsidian/moc/proposals", {
    method: "POST",
    body: {
      root_id: params.root_id,
      source_refs: sourceRefs,
      moc_path: params.moc_path || "PSKA MOC.md",
      title: params.title || "PSKA MOC",
      reason: params.reason || "Obsidian MOC candidate",
    },
  });
  await loadWorkspaceStatus();
  await loadAuditEvents("source.obsidian_moc.propose");
  openView("activity");
  showToast(t("toast.obsidianMocProposalCreated"));
}

async function readSource(sourceRef) {
  selectSourceForAnnotation(sourceRef, sourceRef.title || sourceRef.path || "", { silent: true });
  const payload = await api("/api/sources/read", { method: "POST", body: { source_ref: sourceRef } });
  state.reader = payload.source || null;
  renderReader();
  await loadAuditEvents("source.read");
  document.querySelector('.nav-item[data-view="reader"]').click();
}

async function readDocumentGraph(datasetId, documentId) {
  const payload = await api(
    `/api/kb/datasets/${encodeURIComponent(datasetId)}/documents/${encodeURIComponent(documentId)}/graph`,
  );
  state.reader = { kind: "graph", graph: payload.graph || null };
  renderReader();
  await loadAuditEvents("kb.graph.read");
  document.querySelector('.nav-item[data-view="reader"]').click();
  showToast("图谱已加载。");
}

async function deleteDataset(datasetId) {
  if (!datasetId) return;
  if (!window.confirm(`Delete knowledge base ${shortId(datasetId)}?`)) return;
  await api(`/api/kb/datasets/${encodeURIComponent(datasetId)}`, { method: "DELETE", body: {} });
  if (state.activeDocumentDatasetId === datasetId) {
    state.activeDocumentDatasetId = null;
    state.activeDocuments = [];
    renderDocuments([]);
  }
  state.datasets = state.datasets.filter((dataset) => dataset.dataset_id !== datasetId);
  renderDatasets();
  renderDatasetPickers();
  showToast("知识库已删除。");
  await loadDatasets();
  await loadWorkspaceStatus();
  await loadAuditEvents("kb.dataset.delete");
}

async function deleteAllDatasets() {
  const count = state.datasets.length;
  if (!count) {
    showToast("没有可删除的知识库。");
    return;
  }
  if (!window.confirm(`Delete all knowledge bases in the configured KB provider? ${count} currently listed.`)) return;
  await api("/api/kb/datasets", { method: "DELETE", body: { delete_all: true } });
  state.activeDocumentDatasetId = null;
  state.activeDocuments = [];
  state.datasets = [];
  setAskDatasetIds([]);
  setAskDocumentIds([]);
  const uploadDataset = document.querySelector('#upload-form input[name="dataset_id"]');
  if (uploadDataset) uploadDataset.value = "";
  const documentDataset = document.querySelector('#document-status-form input[name="dataset_id"]');
  if (documentDataset) documentDataset.value = "";
  invalidateAskReadiness();
  renderDatasets();
  renderDocuments([]);
  renderDatasetPickers();
  showToast("知识库已删除。");
  await loadDatasets();
  await loadWorkspaceStatus();
  await loadAuditEvents("kb.dataset.delete");
}

function renderReader() {
  const source = state.reader;
  const sourceBox = document.getElementById("reader-source");
  const metadata = document.getElementById("reader-metadata");
  const status = document.getElementById("reader-status");
  sourceBox.replaceChildren();
  metadata.replaceChildren();
  if (!source) {
    status.textContent = "尚未选择来源";
    status.className = "tag";
    sourceBox.className = "reader-source empty-list";
    sourceBox.textContent = "请从提问结果中选择来源。";
    return;
  }
  if (source.kind === "graph") {
    renderGraphReader(source.graph || {}, sourceBox, metadata, status);
    return;
  }
  status.textContent = "已加载";
  status.className = "tag ready";
  sourceBox.className = "reader-source";
  sourceBox.append(el("pre", {}, source.text || "来源为空。"));
  const ref = source.source_ref || {};
  [
    ["Adapter", ref.adapter || ""],
    ["Dataset", ref.dataset_id || ""],
    ["Document", ref.document_id || ""],
    ["Chunk", ref.chunk_id || ""],
    [t("button.source"), ref.source_id || ""],
    ["External ID", ref.external_id || ""],
    ["Title", ref.title || ""],
    ["Path", ref.path || ""],
    ["URL", ref.url || ""],
  ]
    .filter(([, value]) => value)
    .forEach(([key, value]) => {
      metadata.append(el("dt", {}, key), el("dd", {}, value));
    });
  if (!metadata.children.length) {
    metadata.append(el("dt", {}, "Metadata"), el("dd", {}, "没有可用的来源坐标。"));
  }
}

function renderGraphReader(graph, sourceBox, metadata, status) {
  const templates = graph.templates || [];
  status.textContent = "图谱已加载";
  status.className = "tag ready";
  sourceBox.className = "reader-source";
  sourceBox.append(el("pre", {}, JSON.stringify(graph, null, 2)));
  [
    ["Backend", graph.backend || ""],
    ["Dataset", graph.dataset_id || ""],
    ["Document", graph.document_id || ""],
    ["Templates", String(templates.length)],
    ["Note", graph.note || ""],
  ]
    .filter(([, value]) => value)
    .forEach(([key, value]) => {
      metadata.append(el("dt", {}, key), el("dd", {}, value));
    });
}

async function decideReview(reviewId, decision, reason) {
  const payload = await api(`/api/reviews/${encodeURIComponent(reviewId)}/decision`, {
    method: "POST",
    body: { decision, reason },
  });
  state.focusReviewId = reviewId;
  if (payload.decision && payload.decision.status) {
    setReviewStatusFilter("");
  }
  syncReviewDecision(payload.decision);
  showToast(`异常审核已${reviewDecisionLabel(decision)}。`);
  await loadReviews();
  await loadPendingReviews();
  await loadWorkspaceStatus();
  await loadAuditEvents("review.decide");
  renderCurrentResultSurfaces();
}

async function decideReviewBatch(action) {
  const params = action.params || {};
  const reviewIds = params.review_ids || [];
  if (!reviewIds.length || !params.decision) return;
  const payload = await api("/api/reviews/batch-decision", {
    method: "POST",
    body: {
      review_ids: reviewIds,
      decision: params.decision,
      reason: action.label || action.action || "",
    },
  });
  (payload.decisions || []).forEach(syncReviewDecision);
  setReviewStatusFilter("");
  await loadReviews();
  await loadPendingReviews();
  await loadMemoryReviewQueue();
  await loadWorkspaceStatus();
  await loadAuditEvents("review.decide_batch");
  renderCurrentResultSurfaces();
  showToast(`${t("toast.reviewBatchDecided")} ${payload.decided_count || 0}/${payload.requested_count || 0}`);
}

async function reviseReview(reviewId, intent, memoryCandidate = null) {
  const body = { intent };
  if (memoryCandidate) body.memory_candidate = memoryCandidate;
  const payload = await api(`/api/reviews/${encodeURIComponent(reviewId)}/revision`, {
    method: "POST",
    body,
  });
  syncReviewRecord(payload.previous_review);
  syncReviewRecord(payload.review);
  state.focusReviewId = payload.review && payload.review.review_id;
  setReviewStatusFilter("");
  state.reviewView = [payload.review, ...state.reviewView.filter((review) => review.review_id !== payload.review.review_id)];
  await loadReviews();
  await loadPendingReviews();
  await loadMemoryReviewQueue();
  await loadWorkspaceStatus();
  await loadAuditEvents("review.revise");
  renderCurrentResultSurfaces();
  showToast("异常审核修改已创建。");
}

async function applyMemory(reviewId) {
  const payload = await api(`/api/reviews/${encodeURIComponent(reviewId)}/apply-memory`, { method: "POST", body: {} });
  syncMemoryApply(reviewId, payload.applied);
  const action = memoryApplyAction(payload.applied);
  showToast(memoryApplyToast(payload.applied));
  await loadReviews();
  await loadMemoryCards();
  await loadPendingReviews();
  await loadWorkspaceStatus();
  await loadAuditEvents(action);
  renderCurrentResultSurfaces();
}

async function createMemoryUpdateReview(fact, text, reason) {
  const payload = await api("/api/memory/update-review", {
    method: "POST",
    body: { memory_fact: fact, text, reason },
  });
  syncReviewRecord(payload.review);
  state.focusReviewId = payload.review && payload.review.review_id;
  setReviewStatusFilter("");
  await loadReviews();
  await loadMemoryCards();
  await loadPendingReviews();
  await loadWorkspaceStatus();
  await loadAuditEvents("review.create");
  document.querySelector('.nav-item[data-view="review"]').click();
  showToast("异常记忆更新审核已创建。");
}

async function createMemoryDeleteReview(fact, reason) {
  const payload = await api("/api/memory/delete-review", {
    method: "POST",
    body: { memory_fact: fact, reason },
  });
  syncReviewRecord(payload.review);
  state.focusReviewId = payload.review && payload.review.review_id;
  setReviewStatusFilter("");
  await loadReviews();
  await loadMemoryCards();
  await loadPendingReviews();
  await loadWorkspaceStatus();
  await loadAuditEvents("review.create");
  document.querySelector('.nav-item[data-view="review"]').click();
  showToast("异常记忆删除审核已创建。");
}

async function openMemoryLifecycle(memoryTargetId) {
  const payload = await api(`/api/memory/${encodeURIComponent(memoryTargetId)}/lifecycle`);
  setAuditActionFilter("");
  state.auditEvents = (payload.lifecycle && payload.lifecycle.events) || [];
  renderAuditEvents();
  document.querySelector('.nav-item[data-view="activity"]').click();
  showToast("记忆生命周期已加载。");
}

function memoryApplyLabel(memoryApply) {
  const action = memoryApplyAction(memoryApply);
  if (action === "memory.delete") return "记忆已删除";
  if (action === "memory.update") return "记忆已更新";
  return "记忆已应用";
}

function memoryApplyAction(memoryApply) {
  const operation = memoryApply && memoryApply.metadata && memoryApply.metadata.operation;
  if (operation === "delete") return "memory.delete";
  if (operation === "update") return "memory.update";
  return "memory.apply";
}

function memoryApplyToast(memoryApply) {
  const action = memoryApplyAction(memoryApply);
  if (action === "memory.delete") return "记忆删除已应用。";
  if (action === "memory.update") return "记忆更新已应用。";
  return "记忆已应用。";
}

function reviewDecisionLabel(decision) {
  return {
    accept: "接受",
    edit: "标记为需修改",
    reject: "拒绝",
  }[decision] || decision;
}

function syncReviewDecision(decision) {
  if (!decision || !decision.review_id) return;
  const update = (target) => {
    if (!target || !target.review || target.review.review_id !== decision.review_id) return;
    target.review = {
      ...target.review,
      decision: decision.decision,
      reason: decision.reason,
      status: decision.status,
      decided_at: decision.decided_at,
    };
    target.review_decision = decision;
  };
  update(state.currentAskResult);
  update(state.currentBrief);
}

function syncWorkflowMemoryReview(runId, payload) {
  const update = (target) => {
    if (!target || !target.run || target.run.run_id !== runId) return;
    target.proposal = payload.proposal || target.proposal;
    target.review = payload.review || target.review;
    target.review_decision = payload.review_decision || target.review_decision;
    target.memory_apply = payload.memory_apply || target.memory_apply;
    target.artifact = payload.artifact || target.artifact;
    target.status = payload.review ? payload.review.status : target.status;
  };
  update(state.currentAskResult);
  update(state.currentBrief);
}

function syncMemoryApply(reviewId, applied) {
  if (!reviewId || !applied) return;
  state.memoryApplyByReview[reviewId] = applied;
  const update = (target) => {
    if (!target || !target.review || target.review.review_id !== reviewId) return;
    target.memory_apply = applied;
  };
  update(state.currentAskResult);
  update(state.currentBrief);
}

function renderCurrentResultSurfaces() {
  if (state.currentAskResult) {
    renderAskResult(state.currentAskResult);
  }
  renderWriting();
  renderHome();
}

function setAskDataset(datasetId) {
  document.querySelector('.nav-item[data-view="ask"]').click();
  prepareAskScope(datasetId || "");
}

function askDocument(datasetId, document) {
  const normalizedDatasetId = String(datasetId || "").trim();
  const documentId = String((document && document.document_id) || "").trim();
  if (!normalizedDatasetId || !documentId) {
    showToast("需要知识库 ID 和文档 ID。");
    return;
  }
  setAskDatasetIds([normalizedDatasetId]);
  setAskDocumentIds([documentId]);
  state.askDocumentsByDataset[normalizedDatasetId] = state.activeDocuments.length ? state.activeDocuments : [document];
  renderAskScope();
  document.querySelector('.nav-item[data-view="ask"]').click();
  void checkAskReadiness({ silent: true });
  showToast("文档已加入提问范围。");
}

function prepareAskScope(datasetId, documents = []) {
  const normalized = String(datasetId || "").trim();
  if (!normalized) return false;
  const datasetIds = askDatasetIds();
  if (!datasetIds.includes(normalized)) {
    datasetIds.push(normalized);
    setAskDatasetIds(datasetIds);
  }
  if (documents.length) {
    state.askDocumentsByDataset[normalized] = documents;
  }
  renderAskScope();
  void checkAskReadiness({ silent: true });
  return true;
}

async function api(path, options = {}) {
  const request = {
    method: options.method || "GET",
    headers: {},
  };
  if (options.formData) {
    request.body = options.formData;
  } else if (options.body !== undefined) {
    request.headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, request);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    const message = payload.error && payload.error.message ? payload.error.message : `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

function renderList(container, items, emptyText, renderer = null) {
  container.classList.toggle("empty-list", !items.length);
  container.replaceChildren();
  if (!items.length) {
    container.textContent = emptyText;
    return;
  }
  items.forEach((item) => container.append(renderer ? renderer(item) : el("div", {}, String(item))));
}

function el(tagName, props = {}, children = []) {
  const node = document.createElement(tagName);
  Object.entries(props).forEach(([key, value]) => {
    if (key === "className") node.className = value;
    else if (key === "onclick") node.addEventListener("click", value);
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  });
  const list = Array.isArray(children) ? children : [children];
  list.forEach((child) => {
    if (child === null || child === undefined) return;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  });
  return node;
}

function splitIds(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitLines(value) {
  return String(value || "")
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function askDatasetIds() {
  const input = document.querySelector('#ask-form input[name="dataset_ids"]');
  return splitIds(input ? input.value : "");
}

function askDocumentIds() {
  const input = document.querySelector('#ask-form input[name="document_ids"]');
  return splitIds(input ? input.value : "");
}

function setAskDatasetIds(datasetIds) {
  const input = document.querySelector('#ask-form input[name="dataset_ids"]');
  if (input) input.value = uniqueIds(datasetIds).join(", ");
  invalidateAskReadiness();
}

function setAskDocumentIds(documentIds) {
  const input = document.querySelector('#ask-form input[name="document_ids"]');
  if (input) input.value = uniqueIds(documentIds).join(", ");
  invalidateAskReadiness();
}

function askScopeKey(datasetIds = askDatasetIds(), documentIds = askDocumentIds()) {
  return `${uniqueIds(datasetIds).join("|")}::${uniqueIds(documentIds).join("|")}`;
}

function uniqueIds(values) {
  const result = [];
  values.forEach((value) => {
    const normalized = String(value || "").trim();
    if (normalized && !result.includes(normalized)) result.push(normalized);
  });
  return result;
}

function shortId(value) {
  const text = String(value || "");
  if (!text) return "none";
  if (text.length <= 12) return text;
  return `${text.slice(0, 6)}...${text.slice(-4)}`;
}

function readableName(value) {
  return String(value || "unknown")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatPercent(value) {
  const numeric = Math.max(0, Math.min(1, Number(value || 0)));
  return `${Math.round(numeric * 100)}%`;
}

function datasetState(dataset) {
  const documents = Number(dataset.document_count || 0);
  const chunks = Number(dataset.chunk_count || 0);
  if (chunks > 0) return { label: "ready", className: "ready" };
  if (documents <= 0) return { label: "empty", className: "failed" };
  return { label: "processing", className: "pending" };
}

function documentState(document) {
  const run = String(document.run || "").toUpperCase();
  const status = String(document.status || "").toLowerCase();
  const progressMsg = String(document.progress_msg || "").toLowerCase();
  const progress = Number(document.progress || 0);
  const chunks = Number(document.chunk_count || 0);
  if (
    ["CANCEL", "CANCELED", "CANCELLED"].includes(run) ||
    ["cancel", "canceled", "cancelled"].includes(status) ||
    progressMsg.includes("cancel")
  ) {
    return { label: "cancelled", className: "failed" };
  }
  if (
    ["FAIL", "FAILED", "ERROR"].includes(run) ||
    ["fail", "failed", "error"].includes(status) ||
    progressMsg.includes("fail") ||
    progressMsg.includes("error")
  ) {
    return { label: "failed", className: "failed" };
  }
  if (run === "DONE" || progress >= 1 || chunks > 0 || ["ready", "done", "success"].includes(status)) {
    return { label: "ready", className: "ready" };
  }
  return { label: "processing", className: "pending" };
}

function summarizeDocuments(documents) {
  const total = documents.length;
  let ready = 0;
  let failed = 0;
  documents.forEach((document) => {
    const stateName = documentState(document);
    if (stateName.label === "ready") ready += 1;
    if (stateName.label === "failed") failed += 1;
  });
  if (!total) return { status: "empty", total, ready, failed };
  if (failed) return { status: "failed", total, ready, failed };
  if (ready === total) return { status: "ready", total, ready, failed };
  return { status: "processing", total, ready, failed };
}

function statusClass(status) {
  const value = String(status || "").toLowerCase();
  if (["ready", "complete", "accepted", "ok"].includes(value)) return "ready";
  if (
    [
      "failed",
      "fail",
      "missing",
      "blocked",
      "rejected",
      "empty",
      "error",
      "invalid_configuration",
      "cancel",
      "canceled",
      "cancelled",
    ].includes(value)
  ) {
    return "failed";
  }
  return "pending";
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 3600);
}
