(() => {
  const EXT_ID = "pska-mini";
  const PSKA_API_BASE = sidecarProxyBase(EXT_ID);
  const STORAGE_KEY = "pska-mini.hermes-webui.scope.v1";
  const SKILL_NAME = "knowledge-retrieval";
  const SKILL_CACHE_TTL_MS = 5 * 60 * 1000;
  const REVIEW_BOARD_SLUG = "pska-review";
  const DIGEST_TASK_NAME = "PSKA Digest Runner";
  const DIGEST_TASK_MARKER = "PSKA-Mini Digest Runner";
  const ANSWER_PROOF_DRAFT_PREFIX = "请先改写这份 Answer Proof 草稿";
  const SOURCE_EVIDENCE_DRAFT_PREFIX = "请先把这条资料证据改写成一条稳定记忆";
  const PANEL_NAME = "pska-mini";
  const MAIN_PANEL_ID = "mainPskaMini";
  const BUILTIN_MAIN_CLASSES = [
    "showing-settings",
    "showing-skills",
    "showing-memory",
    "showing-tasks",
    "showing-kanban",
    "showing-workspaces",
    "showing-profiles",
    "showing-insights",
    "showing-logs",
    "showing-plugin"
  ];

  if (window.__pskaMiniExtensionLoaded) return;
  window.__pskaMiniExtensionLoaded = true;

  const state = loadState();
  let skillCache = null;
  let sendBridgeInstalling = false;
  let sendBridgeInjecting = false;
  let apiBridgeInstalling = false;
  let pendingChatStartInjection = null;
  let memoryPage = {
    loading: false,
    loadedAt: "",
    query: "PSKA",
    facts: [],
    reviews: [],
    answerProofs: [],
    answerProofDetail: null,
    answerProofTrace: null,
    answerProofLoadingId: "",
    sourceSearchQuery: "PSKA",
    sourceSearchResults: [],
    sourceSearchDetail: null,
    sourceSearchLoadingKey: "",
    memoryDraftSourceRefs: [],
    memoryDraftSourceLabel: "",
    chatgptImportResult: null,
    chatgptConversationImportResult: null,
    reviewStatus: "pending",
    detail: null,
    firstRunSession: null,
    firstRunSavingItem: "",
    message: "",
    error: ""
  };
  let dashboard = {
    loading: false,
    loadedAt: "",
    health: null,
    workspace: null,
    datasets: [],
    hermesProfile: null,
    hermesProjects: null,
    hermesWorkspaces: null,
    alphaReadiness: null,
    jobHealth: null,
    wakeupPlan: null,
    observabilityMetrics: null,
    sourceRecallEval: null,
    scopeSuggestions: [],
    diagnosticsError: "",
    errors: {}
  };

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return normalizeState(JSON.parse(raw));
    } catch (_) {}
    return normalizeState({});
  }

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (_) {}
  }

  function normalizeState(value) {
    const data = value && typeof value === "object" ? value : {};
    return {
      enabled: Boolean(data.enabled),
      mode: String(data.mode || "auto"),
      datasetIds: normalizeList(data.datasetIds || data.dataset_ids),
      documentIds: normalizeList(data.documentIds || data.document_ids),
      sourceRootIds: normalizeList(data.sourceRootIds || data.source_root_ids || data.root_ids),
      maxTokens: boundedInt(data.maxTokens || data.max_tokens, 3000, 500, 12000)
    };
  }

  function normalizeList(value) {
    const raw = Array.isArray(value) ? value : String(value || "").split(/[,\n]/);
    return Array.from(new Set(raw.map((item) => String(item || "").trim()).filter(Boolean)));
  }

  function boundedInt(value, fallback, min, max) {
    const parsed = Number.parseInt(String(value || ""), 10);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(min, Math.min(max, parsed));
  }

  function init() {
    installPanelCleanup();
    installNavButtons();
    installMemoryPage();
    installComposerChip();
    installApiBridge();
    installDisplaySanitizer();
    installVisibleEnvelopeCleaner();
    installSendBridge();
    exposeRuntimeApi();
  }

  function installComposerChip() {
    if (document.getElementById("pskaMiniWrap")) return;
    const anchor = document.getElementById("composerToolsetsWrap")
      || document.getElementById("profileChipWrap")
      || document.querySelector(".composer-left");
    if (!anchor || !anchor.parentElement) return;

    const wrap = document.createElement("div");
    wrap.id = "pskaMiniWrap";
    wrap.className = "pska-mini-wrap";
    wrap.innerHTML = `
      <button class="pska-mini-chip" id="pskaMiniChip" type="button" aria-haspopup="true" aria-expanded="false">
        <span class="pska-mini-dot" aria-hidden="true"></span>
        <span id="pskaMiniLabel"></span>
      </button>
      <div class="pska-mini-menu" id="pskaMiniMenu" hidden>
        <div class="pska-mini-row pska-mini-head">
          <strong>PSKA-mini</strong>
          <label><input id="pskaMiniEnabled" type="checkbox"> enabled</label>
        </div>

        <div class="pska-mini-status" id="pskaMiniStatus"></div>
        <div class="pska-mini-bridge" id="pskaMiniBridgeStatus"></div>

        <div class="pska-mini-controls">
          <label>Mode
            <select id="pskaMiniMode">
              <option value="auto">auto</option>
              <option value="project">project</option>
              <option value="evidence-only">evidence-only</option>
              <option value="memory-only">memory-only</option>
            </select>
          </label>
          <label>Max context tokens
            <input id="pskaMiniMaxTokens" type="number" min="500" max="12000" step="500">
          </label>
        </div>

        <div class="pska-mini-section-head">
          <strong>Knowledge bases</strong>
          <button id="pskaMiniRefresh" type="button">Refresh</button>
        </div>
        <div class="pska-mini-dataset-list" id="pskaMiniDatasetList"></div>
        <div class="pska-mini-dataset-actions">
          <button id="pskaMiniSelectReady" type="button">Select ready</button>
          <button id="pskaMiniClearDatasets" type="button">Clear</button>
        </div>

        <div class="pska-mini-section-head">
          <strong>Hermes 模块</strong>
        </div>
        <div class="pska-mini-hermes" id="pskaMiniHermesModules"></div>
        <div class="pska-mini-actions pska-mini-hermes-actions">
          <button id="pskaMiniApplySuggestedScope" type="button">应用建议范围</button>
          <button id="pskaMiniSyncReviews" type="button">同步审核看板</button>
          <button id="pskaMiniCreateDigestTask" type="button">创建摘要任务</button>
        </div>

        <div class="pska-mini-section-head">
          <strong>Agentic context</strong>
        </div>
        <div class="pska-mini-actions pska-mini-agentic-actions">
          <button id="pskaMiniJarvisBrief" type="button">Jarvis Brief</button>
          <button id="pskaMiniAgenticBrief" type="button">Agentic Brief</button>
          <button id="pskaMiniSourceRecall" type="button">Source Recall</button>
        </div>

        <details class="pska-mini-advanced">
          <summary>Advanced scope</summary>
          <label>Dataset IDs
            <textarea id="pskaMiniDatasetIds" rows="2" placeholder="optional manual fallback"></textarea>
          </label>
          <label>Document IDs
            <textarea id="pskaMiniDocumentIds" rows="2" placeholder="optional"></textarea>
          </label>
          <label>Source Root IDs
            <textarea id="pskaMiniSourceRootIds" rows="2" placeholder="optional local source roots"></textarea>
          </label>
        </details>

        <div class="pska-mini-actions">
          <button id="pskaMiniOpenMemoryPage" type="button">Memory Page</button>
          <button id="pskaMiniProbe" type="button">RAGFlow Probe</button>
          <button id="pskaMiniPreview" type="button">Preview</button>
          <button id="pskaMiniClose" type="button">Close</button>
        </div>
        <div class="pska-mini-preview" id="pskaMiniPreviewBox" hidden></div>
      </div>
    `;
    anchor.parentElement.insertBefore(wrap, anchor.nextSibling);

    wrap.querySelector("#pskaMiniChip").addEventListener("click", toggleMenu);
    wrap.querySelector("#pskaMiniClose").addEventListener("click", closeMenu);
    wrap.querySelector("#pskaMiniRefresh").addEventListener("click", refreshDashboard);
    wrap.querySelector("#pskaMiniSelectReady").addEventListener("click", selectReadyDatasets);
    wrap.querySelector("#pskaMiniClearDatasets").addEventListener("click", clearDatasets);
    wrap.querySelector("#pskaMiniOpenMemoryPage").addEventListener("click", activateMainPage);
    wrap.querySelector("#pskaMiniProbe").addEventListener("click", runRetrievalProbe);
    wrap.querySelector("#pskaMiniPreview").addEventListener("click", previewTurnContext);
    wrap.querySelector("#pskaMiniApplySuggestedScope").addEventListener("click", applySuggestedScope);
    wrap.querySelector("#pskaMiniSyncReviews").addEventListener("click", syncReviewBoard);
    wrap.querySelector("#pskaMiniCreateDigestTask").addEventListener("click", createDigestTask);
    wrap.querySelector("#pskaMiniJarvisBrief").addEventListener("click", runJarvisBrief);
    wrap.querySelector("#pskaMiniAgenticBrief").addEventListener("click", runAgenticBrief);
    wrap.querySelector("#pskaMiniSourceRecall").addEventListener("click", runSourceRecall);
    wrap.querySelector("#pskaMiniEnabled").addEventListener("change", syncFromControls);
    wrap.querySelector("#pskaMiniMode").addEventListener("change", syncFromControls);
    wrap.querySelector("#pskaMiniMaxTokens").addEventListener("input", syncFromControls);
    wrap.querySelector("#pskaMiniDatasetIds").addEventListener("input", syncFromControls);
    wrap.querySelector("#pskaMiniDocumentIds").addEventListener("input", syncFromControls);
    wrap.querySelector("#pskaMiniSourceRootIds").addEventListener("input", syncFromControls);
    wrap.querySelector("#pskaMiniDatasetList").addEventListener("change", onDatasetToggle);
    document.addEventListener("click", (event) => {
      if (!wrap.contains(event.target)) closeMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMenu();
    });
    renderControls();
    renderDashboard();
  }

  function installNavButtons() {
    if (!document.getElementById("pskaMiniRailButton")) {
      const rail = document.querySelector(".rail");
      if (rail) rail.insertBefore(createNavButton("rail"), navInsertAnchor(rail));
    }
    if (!document.getElementById("pskaMiniMobileButton")) {
      const mobile = document.querySelector(".sidebar-nav");
      if (mobile) mobile.insertBefore(createNavButton("mobile"), navInsertAnchor(mobile));
    }
  }

  function navInsertAnchor(container) {
    return container?.querySelector(".dashboard-link, [data-dashboard-link]")
      || container?.querySelector(".rail-spacer")
      || container?.querySelector('[data-panel="settings"]')
      || null;
  }

  function createNavButton(kind) {
    const button = document.createElement("button");
    button.type = "button";
    button.id = kind === "rail" ? "pskaMiniRailButton" : "pskaMiniMobileButton";
    button.className = kind === "rail"
      ? "rail-btn nav-tab has-tooltip pska-mini-nav-button"
      : "nav-tab has-tooltip has-tooltip--bottom pska-mini-nav-button";
    button.dataset.panel = PANEL_NAME;
    button.dataset.tooltip = "PSKA";
    button.setAttribute("aria-label", "PSKA Memory");
    if (kind !== "rail") button.dataset.label = "PSKA";
    button.innerHTML = `
      <svg width="${kind === "rail" ? 20 : 18}" height="${kind === "rail" ? 20 : 18}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Z"/>
        <path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/>
        <path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>
      </svg>
    `;
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      await activateMainPage({ fromRailClick: true });
    });
    return button;
  }

  async function activateMainPage(opts = {}) {
    closeMenu();
    installMemoryPage();
    if (typeof window.switchPanel === "function") {
      const switched = await window.switchPanel(PANEL_NAME, { fromRailClick: Boolean(opts.fromRailClick) });
      if (switched === false) return;
    }
    showMainPage();
    if (!memoryPage.loadedAt && !memoryPage.loading) refreshMemoryPage();
  }

  function installMemoryPage() {
    if (document.getElementById(MAIN_PANEL_ID)) return;
    const main = document.querySelector("main.main") || document.querySelector("main");
    if (!main) return;
    const panel = document.createElement("section");
    panel.id = MAIN_PANEL_ID;
    panel.className = "main-view pska-mini-page";
    panel.innerHTML = `
      <div class="main-view-header pska-mini-page-header">
        <div>
          <div class="main-view-title">PSKA Memory</div>
          <div class="pska-mini-page-sub">PSKA governed memory and review queue</div>
        </div>
        <div class="main-view-actions">
          <button class="pska-mini-page-btn" id="pskaMiniPageRefresh" type="button">Refresh</button>
        </div>
      </div>
      <div class="main-view-body">
        <div class="main-view-content pska-mini-page-content">
          <section class="pska-mini-page-status" id="pskaMiniPageStatus"></section>
          <section class="pska-mini-first-run" id="pskaMiniFirstRun"></section>
          <section class="pska-mini-answer-proofs">
            <div class="pska-mini-page-section-head">
              <h2>Recent Answer Proofs</h2>
              <span id="pskaMiniAnswerProofCount"></span>
            </div>
            <div class="pska-mini-answer-proof-list" id="pskaMiniAnswerProofs"></div>
            <div class="pska-mini-answer-proof-detail" id="pskaMiniAnswerProofDetail"></div>
          </section>
          <section class="pska-mini-source-evidence">
            <div class="pska-mini-page-section-head">
              <h2>Source Evidence</h2>
              <span id="pskaMiniSourceEvidenceCount"></span>
            </div>
            <div class="pska-mini-page-search">
              <input id="pskaMiniSourceEvidenceQuery" type="search" value="PSKA" placeholder="Search selected source archives">
              <button class="pska-mini-page-btn" id="pskaMiniSourceEvidenceSearch" type="button">Search</button>
            </div>
            <div class="pska-mini-source-scope" id="pskaMiniSourceEvidenceScope"></div>
            <div class="pska-mini-source-evidence-list" id="pskaMiniSourceEvidenceResults"></div>
            <div class="pska-mini-source-evidence-detail" id="pskaMiniSourceEvidenceDetail"></div>
          </section>
          <div class="pska-mini-page-grid">
            <section class="pska-mini-page-section">
              <div class="pska-mini-page-section-head">
                <h2>Memory</h2>
                <span id="pskaMiniMemoryCount"></span>
              </div>
              <div class="pska-mini-page-search">
                <input id="pskaMiniMemoryQuery" type="search" value="PSKA" placeholder="Search PSKA memory">
                <button class="pska-mini-page-btn" id="pskaMiniMemorySearch" type="button">Search</button>
              </div>
              <div class="pska-mini-memory-results" id="pskaMiniMemoryResults"></div>
              <details class="pska-mini-memory-create" id="pskaMiniMemoryCreate">
                <summary>Create review candidate</summary>
                <textarea id="pskaMiniMemoryDraft" rows="4" placeholder="A durable fact worth reviewing"></textarea>
                <div class="pska-mini-memory-draft-source" id="pskaMiniMemoryDraftSource"></div>
                <div class="pska-mini-memory-create-actions">
                  <label><input id="pskaMiniMemoryForceReview" type="checkbox" checked> force review</label>
                  <button class="pska-mini-page-btn" id="pskaMiniClearMemoryDraftSource" type="button">Clear source</button>
                  <button class="pska-mini-page-btn" id="pskaMiniCreateMemoryReview" type="button">Create</button>
                </div>
              </details>
              <details class="pska-mini-memory-create" id="pskaMiniChatgptImport">
                <summary>Import ChatGPT memory summary</summary>
                <textarea id="pskaMiniChatgptMemorySummary" rows="5" placeholder="Paste ChatGPT memory summary"></textarea>
                <div class="pska-mini-memory-create-actions">
                  <label><input id="pskaMiniChatgptIncludePrivate" type="checkbox"> include private chunks</label>
                  <button class="pska-mini-page-btn" id="pskaMiniImportChatgptMemory" type="button">Import</button>
                </div>
                <div class="pska-mini-memory-import-result" id="pskaMiniChatgptImportResult"></div>
              </details>
              <details class="pska-mini-memory-create" id="pskaMiniChatgptConversationImport">
                <summary>Import ChatGPT conversation archive</summary>
                <input id="pskaMiniChatgptConversationPath" type="text" placeholder="Path to conversations.json or export zip">
                <input id="pskaMiniChatgptConversationOutput" type="text" placeholder="Optional PSKA archive output folder">
                <div class="pska-mini-memory-create-actions">
                  <label>limit <input id="pskaMiniChatgptConversationLimit" type="number" min="0" max="5000" step="50" value="100"></label>
                  <button class="pska-mini-page-btn" id="pskaMiniImportChatgptConversations" type="button">Import archive</button>
                </div>
                <div class="pska-mini-memory-import-result" id="pskaMiniChatgptConversationImportResult"></div>
              </details>
            </section>
            <section class="pska-mini-page-section">
              <div class="pska-mini-page-section-head">
                <h2>Review Queue</h2>
                <select id="pskaMiniReviewStatus">
                  <option value="pending">pending</option>
                  <option value="accepted">accepted</option>
                  <option value="all">all</option>
                </select>
              </div>
              <div class="pska-mini-review-list" id="pskaMiniReviewList"></div>
            </section>
          </div>
          <section class="pska-mini-review-detail" id="pskaMiniReviewDetail"></section>
        </div>
      </div>
    `;
    main.appendChild(panel);
    panel.querySelector("#pskaMiniPageRefresh").addEventListener("click", refreshMemoryPage);
    panel.querySelector("#pskaMiniPageStatus").addEventListener("click", onMemoryPageStatusClick);
    panel.querySelector("#pskaMiniMemorySearch").addEventListener("click", runMemoryPageSearch);
    panel.querySelector("#pskaMiniSourceEvidenceSearch").addEventListener("click", runSourceEvidenceSearch);
    panel.querySelector("#pskaMiniMemoryQuery").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        runMemoryPageSearch();
      }
    });
    panel.querySelector("#pskaMiniSourceEvidenceQuery").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        runSourceEvidenceSearch();
      }
    });
    panel.querySelector("#pskaMiniReviewStatus").addEventListener("change", () => {
      memoryPage.reviewStatus = String(panel.querySelector("#pskaMiniReviewStatus")?.value || "pending");
      loadMemoryPageReviews();
    });
    panel.querySelector("#pskaMiniFirstRun").addEventListener("click", onFirstRunClick);
    panel.querySelector("#pskaMiniAnswerProofs").addEventListener("click", onAnswerProofClick);
    panel.querySelector("#pskaMiniAnswerProofDetail").addEventListener("click", onAnswerProofDetailClick);
    panel.querySelector("#pskaMiniSourceEvidenceResults").addEventListener("click", onSourceEvidenceClick);
    panel.querySelector("#pskaMiniSourceEvidenceDetail").addEventListener("click", onSourceEvidenceClick);
    panel.querySelector("#pskaMiniMemoryDraftSource").addEventListener("click", onMemoryDraftSourceClick);
    panel.querySelector("#pskaMiniReviewList").addEventListener("click", onReviewListClick);
    panel.querySelector("#pskaMiniReviewDetail").addEventListener("click", onReviewDetailClick);
    panel.querySelector("#pskaMiniClearMemoryDraftSource").addEventListener("click", clearMemoryDraftSource);
    panel.querySelector("#pskaMiniCreateMemoryReview").addEventListener("click", createMemoryReviewCandidate);
    panel.querySelector("#pskaMiniImportChatgptMemory").addEventListener("click", importChatgptMemorySummary);
    panel.querySelector("#pskaMiniImportChatgptConversations").addEventListener("click", importChatgptConversationArchive);
    renderMemoryPage();
  }

  function showMainPage() {
    installMemoryPage();
    const main = document.querySelector("main.main") || document.querySelector("main");
    if (main) {
      BUILTIN_MAIN_CLASSES.forEach((className) => main.classList.remove(className));
      main.classList.add("showing-pska-mini");
    }
    document.querySelectorAll("[data-panel]").forEach((item) => {
      item.classList.toggle("active", item.dataset.panel === PANEL_NAME);
    });
    const title = document.getElementById("appTitlebarTitle");
    const sub = document.getElementById("appTitlebarSub");
    if (title) title.textContent = "PSKA Memory";
    if (sub) {
      sub.textContent = "Governed memory / review queue";
      sub.hidden = false;
    }
  }

  function installPanelCleanup() {
    document.addEventListener("click", (event) => {
      const tab = event.target?.closest?.("[data-panel], [data-dashboard-link]");
      if (!tab) return;
      if (tab.dataset.panel === PANEL_NAME) return;
      hideMainPageClass();
    }, true);
    patchSwitchPanel();
    window.setTimeout(patchSwitchPanel, 250);
    window.setTimeout(patchSwitchPanel, 1000);
  }

  function patchSwitchPanel() {
    if (typeof window.switchPanel !== "function") return;
    if (window.switchPanel.__pskaMiniPanelWrapped) return;
    const original = window.switchPanel;
    const wrapped = function pskaMiniPanelSwitch(name) {
      if (String(name || "") !== PANEL_NAME) hideMainPageClass();
      return original.apply(this, arguments);
    };
    wrapped.__pskaMiniPanelWrapped = true;
    window.switchPanel = wrapped;
  }

  function hideMainPageClass() {
    const main = document.querySelector("main.main") || document.querySelector("main");
    if (main) main.classList.remove("showing-pska-mini");
    document.querySelectorAll(`[data-panel="${PANEL_NAME}"]`).forEach((item) => item.classList.remove("active"));
  }

  async function refreshMemoryPage() {
    memoryPage = { ...memoryPage, loading: true, error: "", message: "Loading PSKA memory..." };
    renderMemoryPage();
    try {
      await Promise.all([
        refreshDashboard(),
        loadFirstRunSession(),
        loadAnswerProofs(),
        loadMemoryPageReviews(),
        runSourceEvidenceSearch({ silentEmpty: true, skipIfNoScope: true }),
        runMemoryPageSearch({ silentEmpty: true })
      ]);
      memoryPage = { ...memoryPage, loading: false, loadedAt: new Date().toLocaleTimeString(), message: "Loaded." };
    } catch (error) {
      memoryPage = { ...memoryPage, loading: false, error: errorText(error), message: "" };
    }
    renderMemoryPage();
  }

  async function loadFirstRunSession() {
    const data = await pskaMiniFetchJson("/api/alpha/first-run-session", { timeoutMs: 15000 });
    memoryPage = {
      ...memoryPage,
      firstRunSession: data.alpha_first_run_session || null,
      loadedAt: new Date().toLocaleTimeString()
    };
    renderMemoryPage();
  }

  async function loadAnswerProofs() {
    const data = await pskaMiniFetchJson("/api/hermes/answer-proofs?limit=5", { timeoutMs: 15000 });
    memoryPage = {
      ...memoryPage,
      answerProofs: Array.isArray(data.proofs) ? data.proofs : [],
      loadedAt: new Date().toLocaleTimeString()
    };
    renderMemoryPage();
  }

  async function onAnswerProofClick(event) {
    const button = event.target?.closest?.("[data-pska-answer-proof-id]");
    if (!button) return;
    const proofId = button.getAttribute("data-pska-answer-proof-id") || "";
    if (!proofId) return;
    await loadAnswerProofDetail(proofId);
  }

  async function loadAnswerProofDetail(proofId) {
    memoryPage = { ...memoryPage, answerProofLoadingId: proofId, message: `Loading answer proof ${shortId(proofId, 12)}...`, error: "" };
    renderMemoryPage();
    try {
      const [proofData, traceData] = await Promise.all([
        pskaMiniFetchJson(`/api/hermes/answer-proofs?proof_id=${encodeURIComponent(proofId)}&limit=1`, { timeoutMs: 15000 }),
        pskaMiniFetchJson(`/api/trace/query?target_type=hermes_turn&target_id=${encodeURIComponent(proofId)}&limit=10`, { timeoutMs: 15000 })
      ]);
      const proof = Array.isArray(proofData.proofs) ? proofData.proofs[0] : null;
      memoryPage = {
        ...memoryPage,
        answerProofLoadingId: "",
        answerProofDetail: proof || null,
        answerProofTrace: traceData || null,
        message: proof ? `Answer proof ${shortId(proofId, 12)} loaded.` : `Answer proof ${shortId(proofId, 12)} not found.`,
        error: ""
      };
    } catch (error) {
      memoryPage = { ...memoryPage, answerProofLoadingId: "", error: errorText(error), message: "" };
    }
    renderMemoryPage();
  }

  async function onAnswerProofDetailClick(event) {
    const sourcedAskButton = event.target?.closest?.("[data-pska-first-run-sourced-ask-done]");
    if (sourcedAskButton) {
      event.preventDefault();
      await markSourcedAskDone();
      return;
    }
    const button = event.target?.closest?.("[data-pska-answer-proof-draft]");
    if (!button) return;
    event.preventDefault();
    draftMemoryCandidateFromAnswerProof();
  }

  async function onFirstRunClick(event) {
    const button = event.target?.closest?.("[data-pska-first-run-status]");
    if (!button) return;
    const itemId = button.getAttribute("data-pska-first-run-id") || "";
    const status = button.getAttribute("data-pska-first-run-status") || "";
    if (!itemId || !status) return;
    const note = String(document.querySelector(`[data-pska-first-run-note="${cssEscape(itemId)}"]`)?.value || "").trim();
    await updateFirstRunItem(itemId, status, note);
  }

  async function updateFirstRunItem(itemId, status, note) {
    memoryPage = { ...memoryPage, firstRunSavingItem: itemId, message: `Updating first-run item ${itemId}...`, error: "" };
    renderMemoryPage();
    try {
      const data = await pskaMiniFetchJson(`/api/alpha/first-run-session/items/${encodeURIComponent(itemId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, note }),
        timeoutMs: 15000
      });
      memoryPage = {
        ...memoryPage,
        firstRunSavingItem: "",
        firstRunSession: data.alpha_first_run_session || memoryPage.firstRunSession,
        message: `First-run item ${itemId} marked ${status}.`,
        error: ""
      };
      toast("PSKA first-run checklist updated.", "success");
    } catch (error) {
      memoryPage = { ...memoryPage, firstRunSavingItem: "", error: errorText(error), message: "" };
      toast(`PSKA first-run update failed: ${errorText(error)}`, "error");
    }
    renderMemoryPage();
  }

  async function onMemoryPageStatusClick(event) {
    const button = event.target?.closest?.("[data-pska-first-run-scope-done]");
    if (!button) return;
    event.preventDefault();
    await markSelectedScopeDone();
  }

  async function runMemoryPageSearch(options = {}) {
    const input = document.getElementById("pskaMiniMemoryQuery");
    const query = String(input?.value || memoryPage.query || "").trim();
    memoryPage.query = query;
    if (!query) {
      memoryPage = { ...memoryPage, facts: [], message: options.silentEmpty ? memoryPage.message : "Enter a memory search query.", error: "" };
      renderMemoryPage();
      return;
    }
    memoryPage = { ...memoryPage, loading: true, message: "Searching memory...", error: "" };
    renderMemoryPage();
    try {
      const data = await pskaMiniFetchJson("/api/memory/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, scope: {}, limit: 20 }),
        timeoutMs: 15000
      });
      memoryPage = {
        ...memoryPage,
        loading: false,
        facts: Array.isArray(data.memory_facts) ? data.memory_facts : [],
        loadedAt: new Date().toLocaleTimeString(),
        message: `Found ${data.count || 0} memory fact(s).`,
        error: ""
      };
    } catch (error) {
      memoryPage = { ...memoryPage, loading: false, facts: [], error: errorText(error), message: "" };
    }
    renderMemoryPage();
  }

  async function runSourceEvidenceSearch(options = {}) {
    const input = document.getElementById("pskaMiniSourceEvidenceQuery");
    const query = String(input?.value || memoryPage.sourceSearchQuery || "").trim();
    memoryPage.sourceSearchQuery = query;
    if (!query) {
      memoryPage = {
        ...memoryPage,
        sourceSearchResults: [],
        sourceSearchDetail: null,
        message: options.silentEmpty ? memoryPage.message : "Enter a source evidence search query.",
        error: ""
      };
      renderMemoryPage();
      return;
    }
    if (options.skipIfNoScope && !state.sourceRootIds.length) {
      renderMemoryPage();
      return;
    }
    const scope = state.sourceRootIds.length ? currentSourceScopePayload() : {};
    memoryPage = { ...memoryPage, loading: true, message: "Searching source evidence...", error: "" };
    renderMemoryPage();
    try {
      const data = await pskaMiniFetchJson("/api/sources/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, scope, limit: 8 }),
        timeoutMs: 20000
      });
      memoryPage = {
        ...memoryPage,
        loading: false,
        sourceSearchResults: Array.isArray(data.context_packets) ? data.context_packets : [],
        sourceSearchDetail: null,
        loadedAt: new Date().toLocaleTimeString(),
        message: `Found ${data.count || 0} source evidence packet(s).`,
        error: ""
      };
    } catch (error) {
      memoryPage = {
        ...memoryPage,
        loading: false,
        sourceSearchResults: [],
        sourceSearchDetail: null,
        error: errorText(error),
        message: ""
      };
    }
    renderMemoryPage();
  }

  async function onSourceEvidenceClick(event) {
    const button = event.target?.closest?.("[data-pska-source-evidence-action]");
    if (!button) return;
    const action = button.getAttribute("data-pska-source-evidence-action") || "";
    const index = boundedInt(button.getAttribute("data-pska-source-evidence-index"), -1, -1, 10000);
    if (action === "read") {
      await loadSourceEvidenceDetail(index);
    } else if (action === "draft") {
      draftMemoryCandidateFromSourceEvidence(index);
    } else if (action === "draft-detail") {
      draftMemoryCandidateFromSourceEvidenceDetail();
    }
  }

  async function onMemoryDraftSourceClick(event) {
    const button = event.target?.closest?.("[data-pska-first-run-rehearsal-done]");
    if (!button) return;
    event.preventDefault();
    await markSourceEvidenceRehearsalDone();
  }

  async function loadSourceEvidenceDetail(index) {
    const packet = memoryPage.sourceSearchResults[index] || null;
    if (!packet?.source_ref) return;
    const loadingKey = sourceEvidenceKey(packet, index);
    memoryPage = { ...memoryPage, sourceSearchLoadingKey: loadingKey, message: "Reading source evidence...", error: "" };
    renderMemoryPage();
    try {
      const data = await pskaMiniFetchJson("/api/sources/read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_ref: packet.source_ref }),
        timeoutMs: 20000
      });
      memoryPage = {
        ...memoryPage,
        sourceSearchLoadingKey: "",
        sourceSearchDetail: {
          packet,
          source: data.source || null
        },
        message: `Loaded source evidence ${sourceEvidenceTitle(packet)}.`,
        error: ""
      };
    } catch (error) {
      memoryPage = { ...memoryPage, sourceSearchLoadingKey: "", error: errorText(error), message: "" };
    }
    renderMemoryPage();
  }

  async function loadMemoryPageReviews() {
    const status = memoryPage.reviewStatus === "all" ? "" : `status=${encodeURIComponent(memoryPage.reviewStatus)}&`;
    const data = await pskaMiniFetchJson(`/api/reviews?${status}limit=50`, { timeoutMs: 15000 });
    memoryPage = {
      ...memoryPage,
      reviews: normalizeReviews(data),
      loadedAt: new Date().toLocaleTimeString()
    };
    renderMemoryPage();
  }

  async function createMemoryReviewCandidate() {
    const draft = String(document.getElementById("pskaMiniMemoryDraft")?.value || "").trim();
    const forceReview = Boolean(document.getElementById("pskaMiniMemoryForceReview")?.checked);
    if (!draft) {
      memoryPage = { ...memoryPage, error: "Memory candidate text is required.", message: "" };
      renderMemoryPage();
      return;
    }
    if (isUneditedAnswerProofDraft(draft)) {
      memoryPage = { ...memoryPage, error: "Edit the proof draft into a durable memory before creating a review candidate.", message: "" };
      renderMemoryPage();
      return;
    }
    if (isUneditedSourceEvidenceDraft(draft)) {
      memoryPage = { ...memoryPage, error: "Edit the source evidence into a durable memory before creating a review candidate.", message: "" };
      renderMemoryPage();
      return;
    }
    const sourceRefs = memoryPage.memoryDraftSourceRefs.length
      ? memoryPage.memoryDraftSourceRefs
      : [{
        adapter: "hermes-webui",
        source_id: `pska-mini-memory-page:${Date.now()}`,
        title: "Hermes WebUI PSKA Memory page",
        metadata: { origin: "hermes-webui.pska-mini-extension" }
      }];
    memoryPage = { ...memoryPage, loading: true, message: "Creating memory review candidate...", error: "" };
    renderMemoryPage();
    try {
      const data = await pskaMiniFetchJson("/api/memory/conversation-change", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_message: draft,
          operation: "memory_patch",
          text: draft,
          reason: memoryPage.memoryDraftSourceLabel
            ? `Created from Hermes WebUI PSKA Memory page with ${memoryPage.memoryDraftSourceLabel}`
            : "Created from Hermes WebUI PSKA Memory page",
          force_review: forceReview,
          source_refs: sourceRefs,
          scope: {}
        }),
        timeoutMs: 20000
      });
      const reviewId = data.review?.review_id || "";
      const status = data.status || "created";
      const draftBox = document.getElementById("pskaMiniMemoryDraft");
      if (draftBox) draftBox.value = "";
      memoryPage = {
        ...memoryPage,
        loading: false,
        memoryDraftSourceRefs: [],
        memoryDraftSourceLabel: "",
        message: reviewId ? `Memory candidate ${reviewId} ${status}.` : `Memory candidate ${status}.`,
        error: ""
      };
      await loadMemoryPageReviews();
      await runMemoryPageSearch({ silentEmpty: true });
      toast("PSKA memory candidate created.", "success");
    } catch (error) {
      memoryPage = { ...memoryPage, loading: false, error: errorText(error), message: "" };
      renderMemoryPage();
      toast(`PSKA memory candidate failed: ${errorText(error)}`, "error");
    }
  }

  async function importChatgptMemorySummary() {
    const textBox = document.getElementById("pskaMiniChatgptMemorySummary");
    const text = String(textBox?.value || "").trim();
    const includePrivate = Boolean(document.getElementById("pskaMiniChatgptIncludePrivate")?.checked);
    if (!text) {
      memoryPage = { ...memoryPage, error: "ChatGPT memory summary text is required.", message: "" };
      renderMemoryPage();
      return;
    }
    memoryPage = { ...memoryPage, loading: true, message: "Importing ChatGPT memory summary...", error: "" };
    renderMemoryPage();
    try {
      const data = await pskaMiniFetchJson("/api/memory/chatgpt-summary/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_label: "ChatGPT memory summary",
          candidate_limit: 12,
          text,
          include_private: includePrivate
        }),
        timeoutMs: 25000
      });
      const result = data.chatgpt_memory_summary_import || null;
      if (textBox) textBox.value = "";
      memoryPage = {
        ...memoryPage,
        loading: false,
        chatgptImportResult: result,
        message: result
          ? `ChatGPT memory import created ${result.summary?.created_count || 0} review candidate(s).`
          : "ChatGPT memory import completed.",
        error: ""
      };
      await loadMemoryPageReviews();
      toast("PSKA ChatGPT memory import completed.", "success");
    } catch (error) {
      memoryPage = { ...memoryPage, loading: false, error: errorText(error), message: "" };
      renderMemoryPage();
      toast(`PSKA ChatGPT memory import failed: ${errorText(error)}`, "error");
    }
  }

  async function importChatgptConversationArchive() {
    const pathBox = document.getElementById("pskaMiniChatgptConversationPath");
    const outputBox = document.getElementById("pskaMiniChatgptConversationOutput");
    const limitBox = document.getElementById("pskaMiniChatgptConversationLimit");
    const exportPath = String(pathBox?.value || "").trim();
    const outputDir = String(outputBox?.value || "").trim();
    const limit = boundedInt(limitBox?.value, 100, 0, 5000);
    if (!exportPath) {
      memoryPage = { ...memoryPage, error: "ChatGPT conversation export path is required.", message: "" };
      renderMemoryPage();
      return;
    }
    memoryPage = { ...memoryPage, loading: true, message: "Importing ChatGPT conversation archive...", error: "" };
    renderMemoryPage();
    try {
      const data = await pskaMiniFetchJson("/api/sources/chatgpt-conversations/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          export_path: exportPath,
          output_dir: outputDir,
          source_label: "ChatGPT conversation archive",
          conversation_limit: limit,
          scan: true
        }),
        timeoutMs: 60000
      });
      const result = data.chatgpt_conversations_import || null;
      const rootId = String(result?.root?.root_id || "").trim();
      if (rootId) addSourceRootToScope(rootId);
      memoryPage = {
        ...memoryPage,
        loading: false,
        chatgptConversationImportResult: result,
        message: result
          ? `ChatGPT archive imported ${result.summary?.imported_conversation_count || 0} conversation(s)${rootId ? " and selected its source root." : "."}`
          : "ChatGPT archive import completed.",
        error: ""
      };
      await refreshDashboard();
      toast("PSKA ChatGPT conversation archive imported.", "success");
    } catch (error) {
      memoryPage = { ...memoryPage, loading: false, error: errorText(error), message: "" };
      renderMemoryPage();
      toast(`PSKA ChatGPT archive import failed: ${errorText(error)}`, "error");
    }
  }

  function draftMemoryCandidateFromAnswerProof() {
    const proof = memoryPage.answerProofDetail || null;
    if (!proof) return;
    const draftBox = document.getElementById("pskaMiniMemoryDraft");
    const createBox = document.getElementById("pskaMiniMemoryCreate");
    if (!draftBox) return;
    const proofId = String(proof.proof_id || "");
    const trace = memoryPage.answerProofTrace || {};
    draftBox.value = buildAnswerProofMemoryDraft(proof, trace);
    if (createBox) createBox.open = true;
    memoryPage = {
      ...memoryPage,
      memoryDraftSourceRefs: [answerProofSourceRef(proof, trace)],
      memoryDraftSourceLabel: `answer proof ${shortId(proofId, 12)}`,
      message: `Drafted memory candidate from answer proof ${shortId(proofId, 12)}. Edit it before creating review.`,
      error: ""
    };
    renderMemoryPage();
    draftBox.focus();
  }

  function draftMemoryCandidateFromSourceEvidence(index) {
    const packet = memoryPage.sourceSearchResults[index] || null;
    if (!packet?.source_ref) return;
    applySourceEvidenceMemoryDraft(packet, null);
  }

  function draftMemoryCandidateFromSourceEvidenceDetail() {
    const detail = memoryPage.sourceSearchDetail || null;
    const packet = detail?.packet || null;
    if (!packet?.source_ref) return;
    applySourceEvidenceMemoryDraft(packet, detail.source || null);
  }

  function applySourceEvidenceMemoryDraft(packet, source) {
    const draftBox = document.getElementById("pskaMiniMemoryDraft");
    const createBox = document.getElementById("pskaMiniMemoryCreate");
    if (!draftBox) return;
    draftBox.value = buildSourceEvidenceMemoryDraft(packet, source);
    if (createBox) createBox.open = true;
    memoryPage = {
      ...memoryPage,
      memoryDraftSourceRefs: [source?.source_ref || packet.source_ref],
      memoryDraftSourceLabel: `source evidence ${sourceEvidenceTitle(packet, source)}`,
      message: "Drafted memory candidate from source evidence. Edit it before creating review.",
      error: ""
    };
    renderMemoryPage();
    draftBox.focus();
  }

  function clearMemoryDraftSource() {
    memoryPage = { ...memoryPage, memoryDraftSourceRefs: [], memoryDraftSourceLabel: "", message: "Memory draft source cleared.", error: "" };
    renderMemoryPage();
  }

  function addSourceRootToScope(rootId) {
    const normalized = String(rootId || "").trim();
    if (!normalized) return;
    state.sourceRootIds = Array.from(new Set([...state.sourceRootIds, normalized]));
    state.enabled = true;
    saveState();
    renderControls();
    renderHermesModules();
  }

  async function onReviewListClick(event) {
    const button = event.target?.closest?.("[data-pska-review-action]");
    if (!button) return;
    const reviewId = button.getAttribute("data-pska-review-id") || "";
    const action = button.getAttribute("data-pska-review-action") || "";
    if (!reviewId) return;
    if (action === "view") {
      await loadReviewDetail(reviewId);
    } else if (action === "accept") {
      await decideReview(reviewId, "accept");
    } else if (action === "reject") {
      await decideReview(reviewId, "reject");
    } else if (action === "apply") {
      await applyReviewMemory(reviewId);
    }
  }

  async function onReviewDetailClick(event) {
    const button = event.target?.closest?.("[data-pska-first-run-review-done]");
    if (!button) return;
    event.preventDefault();
    await markReviewQueueDone();
  }

  async function loadReviewDetail(reviewId) {
    memoryPage = { ...memoryPage, loading: true, message: "Loading review detail...", error: "" };
    renderMemoryPage();
    try {
      const data = await pskaMiniFetchJson(`/api/reviews/${encodeURIComponent(reviewId)}`, { timeoutMs: 15000 });
      memoryPage = { ...memoryPage, loading: false, detail: data.review || null, message: "", error: "" };
    } catch (error) {
      memoryPage = { ...memoryPage, loading: false, error: errorText(error), message: "" };
    }
    renderMemoryPage();
  }

  async function decideReview(reviewId, decision) {
    memoryPage = { ...memoryPage, loading: true, message: `${decision} review ${reviewId}...`, error: "" };
    renderMemoryPage();
    try {
      await pskaMiniFetchJson(`/api/reviews/${encodeURIComponent(reviewId)}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reason: `${decision} from Hermes WebUI PSKA Memory page` }),
        timeoutMs: 15000
      });
      memoryPage = { ...memoryPage, loading: false, message: `Review ${reviewId} ${decision}ed.`, error: "" };
      await loadMemoryPageReviews();
      await loadReviewDetail(reviewId);
      toast(`PSKA review ${decision}ed.`, "success");
    } catch (error) {
      memoryPage = { ...memoryPage, loading: false, error: errorText(error), message: "" };
      renderMemoryPage();
      toast(`PSKA review decision failed: ${errorText(error)}`, "error");
    }
  }

  async function applyReviewMemory(reviewId) {
    memoryPage = { ...memoryPage, loading: true, message: `Applying review ${reviewId}...`, error: "" };
    renderMemoryPage();
    try {
      await pskaMiniFetchJson(`/api/reviews/${encodeURIComponent(reviewId)}/apply-memory`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
        timeoutMs: 20000
      });
      memoryPage = { ...memoryPage, loading: false, message: `Review ${reviewId} applied to memory.`, error: "" };
      await loadMemoryPageReviews();
      await runMemoryPageSearch({ silentEmpty: true });
      await loadReviewDetail(reviewId);
      toast("PSKA memory applied.", "success");
    } catch (error) {
      memoryPage = { ...memoryPage, loading: false, error: errorText(error), message: "" };
      renderMemoryPage();
      toast(`PSKA memory apply failed: ${errorText(error)}`, "error");
    }
  }

  function renderMemoryPage() {
    renderMemoryPageStatus();
    renderFirstRunSession();
    renderAnswerProofs();
    renderAnswerProofDetail();
    renderSourceEvidenceSearch();
    renderSourceEvidenceDetail();
    renderMemoryDraftSource();
    renderChatgptImportResult();
    renderChatgptConversationImportResult();
    renderMemoryResults();
    renderReviewList();
    renderReviewDetail();
  }

  function renderMemoryPageStatus() {
    const container = document.getElementById("pskaMiniPageStatus");
    if (!container) return;
    const workspace = dashboard.workspace || {};
    const providers = workspace.providers || dashboard.health?.providers || {};
    const kb = workspace.kb || {};
    const embedding = embeddingComponent();
    const gbrain = gbrainComponent();
    const jobs = jobHealth();
    const wakeup = wakeupPlan();
    const metrics = observabilityMetrics();
    const recallEval = sourceRecallEval();
    const alpha = alphaReadiness();
    container.innerHTML = `
      <div class="pska-mini-page-pills">
        <span class="pska-mini-pill ${dashboard.health?.ok ? "is-ok" : "is-bad"}"><b>API</b> ${dashboard.health?.ok ? "ready" : "missing"}</span>
        <span class="pska-mini-pill ${providers.memory ? "is-ok" : "is-warn"}"><b>Memory</b> ${escapeHtml(providers.memory || "unknown")}</span>
        <span class="pska-mini-pill ${kb.usable ? "is-ok" : "is-warn"}"><b>KB</b> ${escapeHtml(kb.usable ? `${kb.ready_dataset_count || 0}/${kb.dataset_count || 0}` : "not ready")}</span>
        <span class="pska-mini-pill is-${escapeAttr(embeddingTone(embedding))}" title="${escapeAttr(embeddingTitle(embedding))}"><b>Embedding</b> ${escapeHtml(embeddingStatusLabel(embedding))}</span>
        <span class="pska-mini-pill is-${escapeAttr(gbrainTone(gbrain))}"><b>GBrain</b> ${escapeHtml(gbrainStatusLabel(gbrain))}</span>
        <span class="pska-mini-pill is-${escapeAttr(jobHealthTone(jobs))}" title="${escapeAttr(jobHealthTitle(jobs))}"><b>Jobs</b> ${escapeHtml(jobHealthStatusLabel(jobs))}</span>
        <span class="pska-mini-pill is-${escapeAttr(wakeupTone(wakeup))}" title="${escapeAttr(wakeupTitle(wakeup))}"><b>Wakeup</b> ${escapeHtml(wakeupStatusLabel(wakeup))}</span>
        <span class="pska-mini-pill is-${escapeAttr(observabilityMetricsTone(metrics))}" title="${escapeAttr(observabilityMetricsTitle(metrics))}"><b>Metrics</b> ${escapeHtml(observabilityMetricsStatusLabel(metrics))}</span>
        <span class="pska-mini-pill is-${escapeAttr(sourceRecallEvalTone(recallEval))}" title="${escapeAttr(sourceRecallEvalTitle(recallEval))}"><b>Recall</b> ${escapeHtml(sourceRecallEvalStatusLabel(recallEval))}</span>
        <span class="pska-mini-pill is-${escapeAttr(alphaTone(alpha))}" title="${escapeAttr(alphaTitle(alpha))}"><b>Alpha</b> ${escapeHtml(alphaStatusLabel(alpha))}</span>
        ${memoryPage.loadedAt ? `<span class="pska-mini-pill"><b>Loaded</b> ${escapeHtml(memoryPage.loadedAt)}</span>` : ""}
      </div>
      ${selectedScopeActionHtml()}
      ${memoryPage.message ? `<div class="pska-mini-page-note">${escapeHtml(memoryPage.message)}</div>` : ""}
      ${jobHealthWarning(jobs)}
      ${wakeupWarning(wakeup)}
      ${observabilityMetricsWarning(metrics)}
      ${sourceRecallEvalWarning(recallEval)}
      ${memoryPage.error ? `<div class="pska-mini-warning">${escapeHtml(memoryPage.error)}</div>` : ""}
    `;
    const statusSelect = document.getElementById("pskaMiniReviewStatus");
    if (statusSelect) statusSelect.value = memoryPage.reviewStatus;
    const queryInput = document.getElementById("pskaMiniMemoryQuery");
    if (queryInput && document.activeElement !== queryInput) queryInput.value = memoryPage.query || "";
  }

  function renderFirstRunSession() {
    const container = document.getElementById("pskaMiniFirstRun");
    if (!container) return;
    const session = memoryPage.firstRunSession;
    if (!session) {
      container.innerHTML = `<div class="pska-mini-empty">First-run checklist is loading.</div>`;
      return;
    }
    const progress = session.progress || {};
    const checklist = Array.isArray(session.checklist) ? session.checklist : [];
    container.innerHTML = `
      <div class="pska-mini-first-run-head">
        <div>
          <h2>First-run checklist</h2>
          <p>${escapeHtml(firstRunSummary(session))}</p>
        </div>
        <div class="pska-mini-first-run-meter" title="${escapeAttr(firstRunDataFlowTitle(session))}">
          <strong>${escapeHtml(String(progress.done_count || 0))}/${escapeHtml(String(progress.total_count || 0))}</strong>
          <span>${escapeHtml(firstRunStatusLabel(session.status))}</span>
        </div>
      </div>
      <div class="pska-mini-first-run-list">
        ${checklist.map((item) => renderFirstRunItem(item)).join("")}
      </div>
    `;
  }

  function renderFirstRunItem(item) {
    const id = String(item.item_id || "");
    const status = String(item.status || "pending");
    const saving = memoryPage.firstRunSavingItem === id;
    return `
      <article class="pska-mini-first-run-item is-${escapeAttr(firstRunTone(status))}">
        <div class="pska-mini-first-run-item-main">
          <div class="pska-mini-first-run-item-title">
            <strong>${escapeHtml(item.label || id)}</strong>
            <span>${escapeHtml(firstRunStatusLabel(status))}${item.required ? " · required" : ""}</span>
          </div>
          <p>${escapeHtml(item.description || "")}</p>
          <code>${escapeHtml(item.tool || "")}${item.api ? ` · ${escapeHtml(item.api)}` : ""}</code>
          <textarea data-pska-first-run-note="${escapeAttr(id)}" rows="1" placeholder="Operator note">${escapeHtml(item.note || "")}</textarea>
        </div>
        <div class="pska-mini-first-run-actions">
          <button class="pska-mini-page-btn" data-pska-first-run-status="done" data-pska-first-run-id="${escapeAttr(id)}" type="button" ${saving ? "disabled" : ""}>Done</button>
          <button class="pska-mini-page-btn" data-pska-first-run-status="needs_attention" data-pska-first-run-id="${escapeAttr(id)}" type="button" ${saving ? "disabled" : ""}>Attention</button>
          <button class="pska-mini-page-btn" data-pska-first-run-status="blocked" data-pska-first-run-id="${escapeAttr(id)}" type="button" ${saving ? "disabled" : ""}>Block</button>
          <button class="pska-mini-page-btn" data-pska-first-run-status="skipped" data-pska-first-run-id="${escapeAttr(id)}" type="button" ${saving ? "disabled" : ""}>Skip</button>
          <button class="pska-mini-page-btn" data-pska-first-run-status="pending" data-pska-first-run-id="${escapeAttr(id)}" type="button" ${saving ? "disabled" : ""}>Reset</button>
        </div>
      </article>
    `;
  }

  function firstRunSummary(session) {
    const progress = session.progress || {};
    const bits = [
      `readiness ${session.readiness_status || "unknown"}`,
      `recovery ${session.recovery_status || "unknown"}`,
      `${progress.required_done_count || 0}/${progress.required_count || 0} required`
    ];
    return bits.join(" · ");
  }

  function firstRunDataFlowTitle(session) {
    const flow = session.data_flow || {};
    return [
      "Checklist update only",
      flow.writes_source_files ? "writes source files" : "does not write source files",
      flow.writes_memory_directly ? "writes memory directly" : "does not write memory directly",
      flow.executes_trial_step ? "executes trial steps" : "does not execute trial steps"
    ].join(" · ");
  }

  function firstRunStatusLabel(status) {
    return String(status || "pending").replace(/_/g, " ");
  }

  function firstRunTone(status) {
    const normalized = String(status || "");
    if (normalized === "done") return "ok";
    if (normalized === "needs_attention" || normalized === "blocked") return "warn";
    if (normalized === "skipped") return "bad";
    return "pending";
  }

  function renderMemoryResults() {
    const count = document.getElementById("pskaMiniMemoryCount");
    if (count) count.textContent = `${memoryPage.facts.length} shown`;
    const container = document.getElementById("pskaMiniMemoryResults");
    if (!container) return;
    if (memoryPage.loading && !memoryPage.facts.length) {
      container.innerHTML = `<div class="pska-mini-empty">Loading memory...</div>`;
      return;
    }
    if (!memoryPage.facts.length) {
      container.innerHTML = `<div class="pska-mini-empty">No memory facts matched this query.</div>`;
      return;
    }
    container.innerHTML = memoryPage.facts.map((fact) => {
      const id = String(fact.fact_id || fact.id || "");
      return `
        <article class="pska-mini-memory-card">
          <div class="pska-mini-memory-card-head">
            <strong>${escapeHtml(id || "memory fact")}</strong>
            <code>${escapeHtml(memoryMetadataLine(fact))}</code>
          </div>
          <p>${escapeHtml(fact.text || fact.display_text || "")}</p>
          <small>${escapeHtml(memorySourceLabel(fact))}</small>
        </article>
      `;
    }).join("");
  }

  function renderAnswerProofs() {
    const count = document.getElementById("pskaMiniAnswerProofCount");
    if (count) count.textContent = `${memoryPage.answerProofs.length} shown`;
    const container = document.getElementById("pskaMiniAnswerProofs");
    if (!container) return;
    if (memoryPage.loading && !memoryPage.answerProofs.length) {
      container.innerHTML = `<div class="pska-mini-empty">Loading answer proofs...</div>`;
      return;
    }
    if (!memoryPage.answerProofs.length) {
      container.innerHTML = `<div class="pska-mini-empty">No Hermes answer proofs recorded yet.</div>`;
      return;
    }
    container.innerHTML = memoryPage.answerProofs.map((proof) => {
      const proofId = String(proof.proof_id || "");
      const summary = proof.tool_summary || {};
      const scope = proof.scope || {};
      const tools = Array.isArray(summary.completed_pska_tools) ? summary.completed_pska_tools : [];
      const datasetCount = Array.isArray(scope.dataset_ids) ? scope.dataset_ids.length : 0;
      const sourceRootCount = Array.isArray(scope.source_root_ids) ? scope.source_root_ids.length : 0;
      const failedCount = Number(proof.check_summary?.failed_check_count || 0);
      const answerLength = Number(proof.answer?.length || 0);
      const loading = memoryPage.answerProofLoadingId === proofId;
      return `
        <article class="pska-mini-answer-proof-card ${proof.read_only ? "is-read-only" : "is-write-like"}">
          <div class="pska-mini-answer-proof-card-head">
            <strong>${escapeHtml(shortId(proofId, 12) || "answer proof")}</strong>
            <span>${escapeHtml(proof.read_only ? "read-only" : "write-like")} · ${escapeHtml(String(tools.length))} PSKA tools</span>
          </div>
          <p>${escapeHtml(truncate(proof.answer?.preview || proof.question?.preview || "No preview", 220))}</p>
          <div class="pska-mini-answer-proof-meta">
            <span>${escapeHtml(datasetCount)} KB</span>
            <span>${escapeHtml(sourceRootCount)} source root</span>
            <span>${escapeHtml(String(answerLength))} chars</span>
            <span>${escapeHtml(String(failedCount))} failed check</span>
          </div>
          <code>${escapeHtml(tools.map((tool) => lastNameSegment(tool)).join(" · ") || "no completed PSKA tools")}</code>
          <div class="pska-mini-answer-proof-actions">
            <button class="pska-mini-page-btn" data-pska-answer-proof-id="${escapeAttr(proofId)}" type="button" ${loading ? "disabled" : ""}>${loading ? "Loading" : "View Trace"}</button>
          </div>
        </article>
      `;
    }).join("");
  }

  function renderAnswerProofDetail() {
    const container = document.getElementById("pskaMiniAnswerProofDetail");
    if (!container) return;
    const proof = memoryPage.answerProofDetail;
    const trace = memoryPage.answerProofTrace || {};
    if (!proof) {
      container.innerHTML = `<div class="pska-mini-empty">Select an answer proof to inspect its observed tools, checks, and trace entries.</div>`;
      return;
    }
    const summary = proof.tool_summary || {};
    const checks = Array.isArray(proof.checks) ? proof.checks : [];
    const entries = Array.isArray(trace.entries) ? trace.entries : [];
    const tools = Array.isArray(summary.completed_pska_tools) ? summary.completed_pska_tools : [];
    const failedCount = Number(proof.check_summary?.failed_check_count || 0);
    const canMarkSourcedAsk = Boolean(proof.read_only) && tools.length > 0 && failedCount === 0;
    container.innerHTML = `
      <div class="pska-mini-page-section-head">
        <h2>Answer Proof Detail</h2>
        <code>${escapeHtml(proof.proof_id || "")}</code>
      </div>
      <div class="pska-mini-answer-proof-detail-grid">
        <span>Read only</span><strong>${escapeHtml(String(Boolean(proof.read_only)))}</strong>
        <span>Stored text</span><strong>${escapeHtml(proof.data_flow?.stores_full_answer ? "full answer" : "preview + hash")}</strong>
        <span>Answer</span><strong>${escapeHtml(String(proof.answer?.length || 0))} chars</strong>
        <span>Trace</span><strong>${escapeHtml(trace.status || "unknown")} · ${escapeHtml(String(trace.entry_count || 0))} entries</strong>
      </div>
      <div class="pska-mini-answer-proof-detail-block">
        <strong>Completed PSKA tools</strong>
        <p>${escapeHtml(tools.map((tool) => lastNameSegment(tool)).join(" · ") || "none")}</p>
      </div>
      <div class="pska-mini-answer-proof-detail-block">
        <strong>Memory candidate</strong>
        <p>Draft from this proof, then edit before creating a Review candidate.</p>
        <button class="pska-mini-page-btn" data-pska-answer-proof-draft="${escapeAttr(proof.proof_id || "")}" type="button">Draft Memory Candidate</button>
        ${canMarkSourcedAsk ? `<button class="pska-mini-inline-btn" data-pska-first-run-sourced-ask-done="1" type="button" ${memoryPage.firstRunSavingItem ? "disabled" : ""}>Mark sourced Ask done</button>` : ""}
      </div>
      <div class="pska-mini-answer-proof-detail-block">
        <strong>Checks</strong>
        <ul>${checks.slice(0, 8).map((check) => `<li>${escapeHtml(check.ok ? "OK" : "FAIL")} · ${escapeHtml(check.name || "")}</li>`).join("") || "<li>No checks recorded.</li>"}</ul>
      </div>
      <div class="pska-mini-answer-proof-detail-block">
        <strong>Trace entries</strong>
        <ul>${entries.slice(0, 6).map((entry) => `<li>${escapeHtml(entry.title || entry.entry_type || "trace")} · ${escapeHtml(entry.occurred_at || "")}</li>`).join("") || "<li>No trace entries.</li>"}</ul>
      </div>
    `;
  }

  function renderSourceEvidenceSearch() {
    const count = document.getElementById("pskaMiniSourceEvidenceCount");
    const roots = state.sourceRootIds || [];
    if (count) count.textContent = `${memoryPage.sourceSearchResults.length} shown · ${roots.length || "all"} root${roots.length === 1 ? "" : "s"}`;
    const scope = document.getElementById("pskaMiniSourceEvidenceScope");
    if (scope) {
      scope.innerHTML = roots.length
        ? `Scope: ${roots.slice(0, 4).map((rootId) => `<code>${escapeHtml(shortId(rootId, 16))}</code>`).join(" ")}${roots.length > 4 ? ` <span>+${escapeHtml(String(roots.length - 4))}</span>` : ""}`
        : "Scope: all registered source archives";
    }
    const queryInput = document.getElementById("pskaMiniSourceEvidenceQuery");
    if (queryInput && document.activeElement !== queryInput) queryInput.value = memoryPage.sourceSearchQuery || "";
    const container = document.getElementById("pskaMiniSourceEvidenceResults");
    if (!container) return;
    if (memoryPage.loading && !memoryPage.sourceSearchResults.length) {
      container.innerHTML = `<div class="pska-mini-empty">Searching source evidence...</div>`;
      return;
    }
    if (!memoryPage.sourceSearchResults.length) {
      container.innerHTML = `<div class="pska-mini-empty">Search imported archives or selected source roots for evidence before creating memory.</div>`;
      return;
    }
    container.innerHTML = memoryPage.sourceSearchResults.map((packet, index) => {
      const loadingKey = sourceEvidenceKey(packet, index);
      const loading = memoryPage.sourceSearchLoadingKey === loadingKey;
      const ref = packet.source_ref || {};
      return `
        <article class="pska-mini-source-evidence-card">
          <div class="pska-mini-source-evidence-card-head">
            <strong>${escapeHtml(sourceEvidenceTitle(packet))}</strong>
            <span>${escapeHtml(sourceEvidenceMeta(packet))}</span>
          </div>
          <p>${escapeHtml(truncate(packet.text || "", 280))}</p>
          <code>${escapeHtml([ref.adapter, ref.path || ref.document_id || ref.source_id].filter(Boolean).join(" · ") || "source")}</code>
          <div class="pska-mini-source-evidence-actions">
            <button class="pska-mini-page-btn" data-pska-source-evidence-action="read" data-pska-source-evidence-index="${escapeAttr(String(index))}" type="button" ${loading ? "disabled" : ""}>${loading ? "Reading" : "Read"}</button>
            <button class="pska-mini-page-btn" data-pska-source-evidence-action="draft" data-pska-source-evidence-index="${escapeAttr(String(index))}" type="button">Draft Memory Candidate</button>
          </div>
        </article>
      `;
    }).join("");
  }

  function renderSourceEvidenceDetail() {
    const container = document.getElementById("pskaMiniSourceEvidenceDetail");
    if (!container) return;
    const detail = memoryPage.sourceSearchDetail;
    if (!detail) {
      container.innerHTML = `<div class="pska-mini-empty">Read a source evidence packet to inspect the full source text and attach it to a memory candidate.</div>`;
      return;
    }
    const packet = detail.packet || {};
    const source = detail.source || {};
    const ref = source.source_ref || packet.source_ref || {};
    const text = source.text || packet.text || "";
    container.innerHTML = `
      <div class="pska-mini-page-section-head">
        <h2>Source Evidence Detail</h2>
        <code>${escapeHtml(shortId(ref.source_id || ref.document_id || packet.context_id || "", 18))}</code>
      </div>
      <div class="pska-mini-source-evidence-detail-grid">
        <span>Title</span><strong>${escapeHtml(sourceEvidenceTitle(packet, source))}</strong>
        <span>Adapter</span><strong>${escapeHtml(ref.adapter || "")}</strong>
        <span>Path</span><strong>${escapeHtml(ref.path || ref.document_id || ref.source_id || "")}</strong>
        <span>Score</span><strong>${escapeHtml(sourceEvidenceScore(packet))}</strong>
      </div>
      <pre>${escapeHtml(truncate(text, 2600))}</pre>
      <div class="pska-mini-source-evidence-actions">
        <button class="pska-mini-page-btn" data-pska-source-evidence-action="draft-detail" type="button">Draft Memory Candidate</button>
      </div>
    `;
  }

  function renderMemoryDraftSource() {
    const container = document.getElementById("pskaMiniMemoryDraftSource");
    if (!container) return;
    const label = String(memoryPage.memoryDraftSourceLabel || "").trim();
    const canMarkSourceEvidence = label.toLowerCase().startsWith("source evidence ");
    container.innerHTML = label
      ? `Source attached: <strong>${escapeHtml(label)}</strong>${canMarkSourceEvidence ? ` <button class="pska-mini-inline-btn" data-pska-first-run-rehearsal-done="1" type="button" ${memoryPage.firstRunSavingItem ? "disabled" : ""}>Mark rehearsal done</button>` : ""}`
      : "Source attached: manual memory page";
  }

  function renderChatgptImportResult() {
    const container = document.getElementById("pskaMiniChatgptImportResult");
    if (!container) return;
    const result = memoryPage.chatgptImportResult;
    if (!result) {
      container.innerHTML = "";
      return;
    }
    const summary = result.summary || {};
    container.innerHTML = `
      <div class="pska-mini-memory-draft-source">
        Import <strong>${escapeHtml(shortId(result.import_id || "", 12) || "done")}</strong> ·
        created ${escapeHtml(String(summary.created_count || 0))} ·
        private skipped ${escapeHtml(String(summary.skipped_private_count || 0))} ·
        boundary ${escapeHtml(summary.privacy_boundary_created ? "yes" : "no")}
      </div>
    `;
  }

  function renderChatgptConversationImportResult() {
    const container = document.getElementById("pskaMiniChatgptConversationImportResult");
    if (!container) return;
    const result = memoryPage.chatgptConversationImportResult;
    if (!result) {
      container.innerHTML = "";
      return;
    }
    const summary = result.summary || {};
    const archive = result.archive || {};
    const rootId = result.root?.root_id || "";
    container.innerHTML = `
      <div class="pska-mini-memory-draft-source">
        Archive <strong>${escapeHtml(shortId(result.import_id || "", 12) || "done")}</strong> ·
        conversations ${escapeHtml(String(summary.imported_conversation_count || 0))}/${escapeHtml(String(summary.selected_conversation_count || 0))} ·
        files ${escapeHtml(String(archive.file_count || 0))} ·
        root ${escapeHtml(shortId(rootId, 12) || "not scanned")}
        <br>
        ${escapeHtml(archive.output_dir || "")}
        ${archive.report_path ? `<br>Report: ${escapeHtml(archive.report_path)}` : ""}
      </div>
    `;
  }

  function buildAnswerProofMemoryDraft(proof, trace) {
    const summary = proof.tool_summary || {};
    const checks = proof.check_summary || {};
    const tools = Array.isArray(summary.completed_pska_tools) ? summary.completed_pska_tools : [];
    const questionPreview = String(proof.question?.preview || "").trim();
    const answerPreview = String(proof.answer?.preview || "").trim();
    const lines = [
      `${ANSWER_PROOF_DRAFT_PREFIX}，再创建审核候选。`,
      "",
      `来源问题：${truncate(questionPreview || "未记录问题预览", 260)}`,
      `回答依据：${tools.map((tool) => lastNameSegment(tool)).join("、") || "未记录 PSKA 工具"}；trace ${trace.status || "unknown"}；失败检查 ${checks.failed_check_count || 0}。`,
      "",
      "建议记忆：",
      "- ",
      "",
      "适用范围：",
      "- ",
      "",
      "未来影响：",
      "- ",
      "",
      `回答预览：${truncate(answerPreview || "未记录回答预览", 360)}`
    ];
    return lines.join("\n");
  }

  function buildSourceEvidenceMemoryDraft(packet, source) {
    const ref = source?.source_ref || packet?.source_ref || {};
    const text = String(source?.text || packet?.text || "").trim();
    const lines = [
      `${SOURCE_EVIDENCE_DRAFT_PREFIX}，再创建审核候选。`,
      "",
      `资料标题：${sourceEvidenceTitle(packet, source)}`,
      `资料位置：${[ref.adapter, ref.path || ref.document_id || ref.source_id].filter(Boolean).join(" / ") || "未记录"}`,
      "",
      "建议记忆：",
      "- ",
      "",
      "适用范围：",
      "- ",
      "",
      "未来影响：",
      "- ",
      "",
      `证据摘录：${truncate(text || "未记录文本", 520)}`
    ];
    return lines.join("\n");
  }

  async function markSourceEvidenceRehearsalDone() {
    const note = sourceEvidenceRehearsalNote();
    await updateFirstRunItem("rehearse_source_evidence_memory", "done", note);
  }

  async function markSourcedAskDone() {
    const note = sourcedAskNote();
    await updateFirstRunItem("run_sourced_ask", "done", note);
  }

  async function markSelectedScopeDone() {
    const note = selectedScopeNote();
    await updateFirstRunItem("select_read_only_scope", "done", note);
  }

  async function markReviewQueueDone() {
    const note = reviewQueueInspectionNote();
    await updateFirstRunItem("review_memory_queue", "done", note);
  }

  function selectedScopeActionHtml() {
    if (!hasExplicitScope()) return "";
    return `
      <div class="pska-mini-page-actions">
        <span>${escapeHtml(selectedScopeSummary())}</span>
        <button class="pska-mini-inline-btn" data-pska-first-run-scope-done="1" type="button" ${memoryPage.firstRunSavingItem ? "disabled" : ""}>Mark scope selected</button>
      </div>
    `;
  }

  function hasExplicitScope() {
    return Boolean(state.datasetIds.length || state.documentIds.length || state.sourceRootIds.length);
  }

  function selectedScopeSummary() {
    return [
      "Selected read-only scope",
      state.datasetIds.length ? countLabel(state.datasetIds.length, "KB") : "",
      state.documentIds.length ? countLabel(state.documentIds.length, "document") : "",
      state.sourceRootIds.length ? countLabel(state.sourceRootIds.length, "source root") : ""
    ].filter(Boolean).join(" · ");
  }

  function countLabel(count, label) {
    return `${count} ${label}${count === 1 || label === "KB" ? "" : "s"}`;
  }

  function selectedScopeNote() {
    return [
      "selected read-only scope",
      state.datasetIds.length ? scopeListNote("KB", state.datasetIds) : "",
      state.documentIds.length ? scopeListNote("document", state.documentIds) : "",
      state.sourceRootIds.length ? scopeListNote("source root", state.sourceRootIds) : ""
    ].filter(Boolean).join(" · ");
  }

  function scopeListNote(label, values) {
    const list = (values || []).slice(0, 3).map((value) => shortId(value, 12)).filter(Boolean).join(" / ");
    const extra = values.length > 3 ? ` +${values.length - 3}` : "";
    return `${countLabel(values.length, label)}${list ? ` ${list}${extra}` : extra}`;
  }

  function sourcedAskNote() {
    const proof = memoryPage.answerProofDetail || {};
    const summary = proof.tool_summary || {};
    const tools = Array.isArray(summary.completed_pska_tools) ? summary.completed_pska_tools : [];
    const scope = proof.scope || {};
    const sourceRootCount = Array.isArray(scope.source_root_ids) ? scope.source_root_ids.length : 0;
    const datasetCount = Array.isArray(scope.dataset_ids) ? scope.dataset_ids.length : 0;
    const toolLabel = tools.slice(0, 4).map((tool) => lastNameSegment(tool)).join(" / ");
    const extraTools = tools.length > 4 ? ` +${tools.length - 4}` : "";
    return [
      `answer proof ${shortId(proof.proof_id || "", 12) || "unknown"}`,
      toolLabel ? `${toolLabel}${extraTools}` : "",
      `${datasetCount} KB`,
      `${sourceRootCount} source root`
    ].filter(Boolean).join(" · ");
  }

  function reviewQueueInspectionNote() {
    const detail = memoryPage.detail || {};
    const proposal = detail.proposal || {};
    const kind = String(proposal.kind || detail.kind || "candidate");
    const status = normalizeReviewStatus(detail);
    const sourceCount = Array.isArray(proposal.source_refs) ? proposal.source_refs.length : 0;
    return [
      `review ${shortId(detail.review_id || detail.id || "", 12) || "unknown"}`,
      reviewKindLabel(kind),
      reviewStatusLabel(status),
      `${sourceCount} source refs`
    ].filter(Boolean).join(" · ");
  }

  function sourceEvidenceRehearsalNote() {
    const ref = memoryPage.memoryDraftSourceRefs[0] || {};
    const label = String(memoryPage.memoryDraftSourceLabel || "source evidence").trim();
    const location = [ref.adapter, ref.path || ref.document_id || ref.source_id].filter(Boolean).join(" / ");
    return [label, location].filter(Boolean).join(" · ");
  }

  function answerProofSourceRef(proof, trace) {
    const proofId = String(proof.proof_id || "");
    const summary = proof.tool_summary || {};
    const checks = proof.check_summary || {};
    return {
      adapter: "hermes_answer_proof",
      source_id: proofId,
      external_id: String(proof.session_id || proof.response_id || proofId),
      title: `Hermes answer proof ${shortId(proofId, 12) || "unknown"}`,
      metadata: {
        origin: "hermes-webui.pska-mini-answer-proof",
        proof_id: proofId,
        audit_event_id: String(proof.audit_event_id || ""),
        session_id: String(proof.session_id || ""),
        message_id: String(proof.message_id || ""),
        response_id: String(proof.response_id || ""),
        read_only: Boolean(proof.read_only),
        question_sha256: String(proof.question?.sha256 || ""),
        answer_sha256: String(proof.answer?.sha256 || ""),
        answer_length: Number(proof.answer?.length || 0),
        completed_pska_tools: Array.isArray(summary.completed_pska_tools) ? summary.completed_pska_tools : [],
        write_like_tools: Array.isArray(summary.write_like_tools) ? summary.write_like_tools : [],
        failed_check_count: Number(checks.failed_check_count || 0),
        trace_status: String(trace?.status || ""),
        trace_entry_count: Number(trace?.entry_count || 0)
      }
    };
  }

  function isUneditedAnswerProofDraft(value) {
    return String(value || "").trim().startsWith(ANSWER_PROOF_DRAFT_PREFIX);
  }

  function isUneditedSourceEvidenceDraft(value) {
    return String(value || "").trim().startsWith(SOURCE_EVIDENCE_DRAFT_PREFIX);
  }

  function sourceEvidenceTitle(packet, source) {
    const ref = source?.source_ref || packet?.source_ref || {};
    return String(source?.metadata?.title || packet?.title || ref.title || ref.path || ref.document_id || ref.source_id || packet?.context_id || "source evidence");
  }

  function sourceEvidenceMeta(packet) {
    const ref = packet?.source_ref || {};
    return [sourceEvidenceScore(packet), ref.adapter || "", ref.metadata?.root_label || ""].filter(Boolean).join(" · ");
  }

  function sourceEvidenceScore(packet) {
    const score = Number(packet?.score || 0);
    if (!Number.isFinite(score) || score <= 0) return "score n/a";
    return `score ${score.toFixed(2)}`;
  }

  function sourceEvidenceKey(packet, index) {
    const ref = packet?.source_ref || {};
    return [index, packet?.context_id, ref.adapter, ref.document_id, ref.chunk_id, ref.source_id, ref.path].filter((item) => item !== undefined && item !== null).join(":");
  }

  function renderReviewList() {
    const container = document.getElementById("pskaMiniReviewList");
    if (!container) return;
    if (memoryPage.loading && !memoryPage.reviews.length) {
      container.innerHTML = `<div class="pska-mini-empty">Loading reviews...</div>`;
      return;
    }
    if (!memoryPage.reviews.length) {
      container.innerHTML = `<div class="pska-mini-empty">No ${escapeHtml(memoryPage.reviewStatus)} review candidates.</div>`;
      return;
    }
    container.innerHTML = memoryPage.reviews.map((review) => {
      const id = String(review.review_id || review.id || "");
      const status = normalizeReviewStatus(review);
      const proposal = review.proposal || {};
      const kind = String(proposal.kind || review.kind || "candidate");
      const applied = Boolean(review.memory_apply);
      return `
        <article class="pska-mini-review-card">
          <div class="pska-mini-review-card-head">
            <strong>${escapeHtml(reviewKindLabel(kind))}</strong>
            <span>${escapeHtml(reviewStatusLabel(status))}${applied ? " · applied" : ""}</span>
          </div>
          <p>${escapeHtml(proposalPreview(proposal))}</p>
          <code>${escapeHtml(id)}</code>
          <div class="pska-mini-review-actions">
            <button class="pska-mini-page-btn" data-pska-review-action="view" data-pska-review-id="${escapeAttr(id)}" type="button">View</button>
            ${status === "pending" ? `<button class="pska-mini-page-btn" data-pska-review-action="accept" data-pska-review-id="${escapeAttr(id)}" type="button">Accept</button>` : ""}
            ${status === "pending" ? `<button class="pska-mini-page-btn" data-pska-review-action="reject" data-pska-review-id="${escapeAttr(id)}" type="button">Reject</button>` : ""}
            ${status === "accepted" && !applied ? `<button class="pska-mini-page-btn" data-pska-review-action="apply" data-pska-review-id="${escapeAttr(id)}" type="button">Apply</button>` : ""}
          </div>
        </article>
      `;
    }).join("");
  }

  function renderReviewDetail() {
    const container = document.getElementById("pskaMiniReviewDetail");
    if (!container) return;
    const detail = memoryPage.detail;
    if (!detail) {
      container.innerHTML = `<div class="pska-mini-empty">Select a review candidate to inspect its proposal, evidence, and memory apply state.</div>`;
      return;
    }
    container.innerHTML = `
      <div class="pska-mini-page-section-head">
        <h2>Review Detail</h2>
        <code>${escapeHtml(detail.review_id || "")}</code>
      </div>
      <div class="pska-mini-answer-proof-detail-block">
        <strong>First-run evidence</strong>
        <p>Record that you inspected this Review Queue candidate before accepting, rejecting, or applying memory.</p>
        <button class="pska-mini-inline-btn" data-pska-first-run-review-done="1" type="button" ${memoryPage.firstRunSavingItem ? "disabled" : ""}>Mark review inspected</button>
      </div>
      <pre>${escapeHtml(stableJson(detail))}</pre>
    `;
  }

  function memoryMetadataLine(fact) {
    const metadata = fact?.metadata || {};
    const version = metadata.version ? `v${metadata.version}` : "";
    const layer = metadata.layer || "";
    const namespace = metadata.memory_namespace || "";
    return [version, layer, namespace].filter(Boolean).join(" · ") || "default";
  }

  function memorySourceLabel(fact) {
    const refs = Array.isArray(fact?.source_refs) ? fact.source_refs : [];
    if (!refs.length) return "No source refs";
    return refs.slice(0, 3).map((ref) => ref.title || ref.source_id || ref.adapter || "source").join(" · ");
  }

  function proposalPreview(proposal) {
    const patch = proposal?.memory_patch?.text || proposal?.memory_update?.text || proposal?.memory_delete?.text;
    return truncate(patch || proposal?.body || proposal?.intent || "No preview", 260);
  }

  async function refreshDashboard() {
    dashboard = { ...dashboard, loading: true, errors: {} };
    renderDashboard();
    const results = await settleObject({
      health: pskaMiniFetchJson("/api/health"),
      workspace: pskaMiniFetchJson("/api/workspace/status?compact=1&view=webui&next_action_limit=8"),
      datasets: pskaMiniFetchJson("/api/kb/datasets"),
      hermesProfile: fetchWebuiJson("/api/profile/active", { timeoutMs: 5000 }),
      hermesProjects: fetchWebuiJson("/api/projects", { timeoutMs: 5000 }),
      hermesWorkspaces: fetchWebuiJson("/api/workspaces", { timeoutMs: 5000 }),
      jobHealth: pskaMiniFetchJson("/api/jobs/health?include_kb=false", { timeoutMs: 10000 }),
      wakeupPlan: pskaMiniFetchJson("/api/wakeup/plan", { timeoutMs: 10000 }),
      observabilityMetrics: pskaMiniFetchJson("/api/observability/metrics?limit=300", { timeoutMs: 10000 }),
      sourceRecallEval: pskaMiniFetchJson("/api/sources/recall-eval?mode=fixture&limit=5", { timeoutMs: 10000 }),
      alphaReadiness: pskaMiniFetchJson("/api/alpha/readiness", { timeoutMs: 10000 }),
      diagnostics: pskaMiniFetchJson("/api/runtime/diagnostics", { timeoutMs: 10000 })
    });
    const diagnosticsValue = valueOrNull(results.diagnostics);
    const nextDashboard = {
      loading: false,
      loadedAt: new Date().toLocaleTimeString(),
      health: valueOrNull(results.health),
      workspace: valueOrNull(results.workspace)?.workspace_status || null,
      datasets: valueOrNull(results.datasets)?.datasets || [],
      hermesProfile: valueOrNull(results.hermesProfile),
      hermesProjects: valueOrNull(results.hermesProjects),
      hermesWorkspaces: valueOrNull(results.hermesWorkspaces),
      jobHealth: valueOrNull(results.jobHealth)?.job_health || null,
      wakeupPlan: valueOrNull(results.wakeupPlan)?.wakeup_plan || null,
      observabilityMetrics: valueOrNull(results.observabilityMetrics)?.observability_metrics || null,
      sourceRecallEval: valueOrNull(results.sourceRecallEval)?.source_recall_eval || null,
      alphaReadiness: valueOrNull(results.alphaReadiness)?.alpha_readiness || null,
      scopeSuggestions: [],
      diagnosticsError: results.diagnostics.status === "rejected"
        ? errorText(results.diagnostics.reason)
        : diagnosticsValue?.ok === false
          ? errorMessage(diagnosticsValue, "diagnostics failed")
          : diagnosticsValue?.diagnostics?.status === "error"
            ? "diagnostics status: error"
            : "",
      errors: Object.fromEntries(
        Object.entries(results)
          .filter(([key, result]) => key !== "diagnostics" && result.status === "rejected")
          .map(([key, result]) => [key, errorText(result.reason)])
      )
    };
    nextDashboard.scopeSuggestions = buildScopeSuggestions(nextDashboard);
    dashboard = nextDashboard;
    renderDashboard();
  }

  function renderDashboard() {
    renderStatus();
    renderDatasets();
    renderHermesModules();
  }

  function renderStatus() {
    const container = document.getElementById("pskaMiniStatus");
    if (!container) return;
    if (dashboard.loading && !dashboard.loadedAt && !dashboard.health && !dashboard.workspace) {
      container.innerHTML = `
        <div class="pska-mini-status-pills">
          <span class="pska-mini-pill is-warn"><b>API</b> checking</span>
          <span class="pska-mini-pill is-warn"><b>KB</b> checking</span>
          <span class="pska-mini-pill is-warn"><b>Memory</b> checking</span>
          <span class="pska-mini-pill is-warn"><b>Embedding</b> checking</span>
          <span class="pska-mini-pill is-warn"><b>GBrain</b> checking</span>
          <span class="pska-mini-pill is-warn"><b>Jobs</b> checking</span>
          <span class="pska-mini-pill is-warn"><b>Wakeup</b> checking</span>
          <span class="pska-mini-pill is-warn"><b>Metrics</b> checking</span>
          <span class="pska-mini-pill is-warn"><b>Recall</b> checking</span>
          <span class="pska-mini-pill is-warn"><b>Alpha</b> checking</span>
        </div>
        <div class="pska-mini-muted">Refreshing PSKA workspace status...</div>
      `;
      return;
    }
    const workspace = dashboard.workspace || {};
    const kb = workspace.kb || {};
    const providers = workspace.providers || dashboard.health?.providers || {};
    const apiOk = Boolean(dashboard.health?.ok);
    const kbOk = Boolean(kb.usable);
    const memoryOk = Boolean(providers.memory) && !dashboard.diagnosticsError;
    const embedding = embeddingComponent();
    const gbrain = gbrainComponent();
    const jobs = jobHealth();
    const wakeup = wakeupPlan();
    const metrics = observabilityMetrics();
    const recallEval = sourceRecallEval();
    const alpha = alphaReadiness();
    const statusItems = [
      ["API", apiOk ? "ready" : "missing", apiOk ? "ok" : "bad", ""],
      ["KB", kbOk ? `${kb.ready_dataset_count || 0}/${kb.dataset_count || 0}` : "not ready", kbOk ? "ok" : "warn", ""],
      ["Memory", memoryOk ? providers.memory : "down", memoryOk ? "ok" : "bad", ""],
      ["Embedding", embeddingStatusLabel(embedding), embeddingTone(embedding), embeddingTitle(embedding)],
      ["GBrain", gbrainStatusLabel(gbrain), gbrainTone(gbrain), ""],
      ["Jobs", jobHealthStatusLabel(jobs), jobHealthTone(jobs), jobHealthTitle(jobs)],
      ["Wakeup", wakeupStatusLabel(wakeup), wakeupTone(wakeup), wakeupTitle(wakeup)],
      ["Metrics", observabilityMetricsStatusLabel(metrics), observabilityMetricsTone(metrics), observabilityMetricsTitle(metrics)],
      ["Recall", sourceRecallEvalStatusLabel(recallEval), sourceRecallEvalTone(recallEval), sourceRecallEvalTitle(recallEval)],
      ["Alpha", alphaStatusLabel(alpha), alphaTone(alpha), alphaTitle(alpha)]
    ];
    container.innerHTML = `
      <div class="pska-mini-status-pills">
        ${statusItems.map(([label, value, tone, title]) => `
          <span class="pska-mini-pill is-${escapeAttr(tone)}" ${title ? `title="${escapeAttr(title)}"` : ""}>
            <b>${escapeHtml(label)}</b> ${escapeHtml(value)}
          </span>
        `).join("")}
      </div>
      ${dashboard.diagnosticsError ? `<div class="pska-mini-warning">Runtime diagnostics: ${escapeHtml(dashboard.diagnosticsError)}</div>` : ""}
      ${jobHealthWarning(jobs)}
      ${wakeupWarning(wakeup)}
      ${observabilityMetricsWarning(metrics)}
      ${sourceRecallEvalWarning(recallEval)}
      ${Object.keys(dashboard.errors).length ? `
        <div class="pska-mini-warning">${Object.entries(dashboard.errors).map(([key, value]) => `${escapeHtml(key)}: ${escapeHtml(value)}`).join("<br>")}</div>
      ` : ""}
      ${dashboard.loadedAt ? `<div class="pska-mini-muted">Last refresh: ${escapeHtml(dashboard.loadedAt)}</div>` : ""}
    `;
  }

  function embeddingComponent() {
    return dashboard.workspace?.components?.embedding || null;
  }

  function embeddingStatusLabel(component) {
    if (!component) return "not visible";
    const model = String(component.model?.configured || "").trim();
    const mode = String(component.mode || component.status || "").trim();
    if (mode === "local_infinity_dev") return model ? `local ${model}` : "local";
    if (mode === "tei_container_delivery") return model ? `TEI ${model}` : "TEI";
    if (mode === "external_http_embedding") return "external";
    if (mode === "disabled") return "disabled";
    return mode || "unknown";
  }

  function embeddingTone(component) {
    if (!component) return "bad";
    if (component.status === "configured") return "ok";
    if (component.status === "disabled") return "warn";
    return "bad";
  }

  function embeddingTitle(component) {
    if (!component) return "Embedding component is not visible in PSKA workspace status.";
    const endpoint = component.endpoints?.ragflow_expected_url || component.endpoints?.host_health_url || "";
    const flow = "Hermes/WebUI -> PSKA -> RAGFlow -> embedding";
    return [component.runtime?.product_flow_status, endpoint, flow].filter(Boolean).join(" · ");
  }

  function gbrainComponent() {
    return dashboard.workspace?.components?.gbrain || null;
  }

  function gbrainStatusLabel(component) {
    if (!component) return "not visible";
    if (component.runtime?.participates_in_memory_search) return "active";
    return String(component.mode || component.status || "candidate");
  }

  function gbrainTone(component) {
    if (!component) return "bad";
    if (component.runtime?.participates_in_memory_search) return "ok";
    return "warn";
  }

  function jobHealth() {
    return dashboard.jobHealth || null;
  }

  function jobHealthStatusLabel(health) {
    if (!health) return "not visible";
    const summary = health.summary || {};
    const total = jobHealthCount(summary, "job");
    if (health.status === "empty") return "empty";
    if (health.status === "needs_attention") {
      const failed = jobHealthCount(summary, "failed");
      const stale = jobHealthCount(summary, "stale");
      if (failed) return `${failed} failed`;
      if (stale) return `${stale} stale`;
      return "attention";
    }
    if (health.status === "action_required") {
      const due = jobHealthCount(summary, "due");
      const active = jobHealthCount(summary, "running") + jobHealthCount(summary, "processing");
      if (due) return `${due} due`;
      if (active) return `${active} active`;
      return `${total} queued`;
    }
    return total ? `${total} tracked` : String(health.status || "ok");
  }

  function jobHealthTone(health) {
    if (!health) return "bad";
    if (health.status === "needs_attention") return "bad";
    if (health.status === "action_required") return "warn";
    return "ok";
  }

  function jobHealthTitle(health) {
    if (!health) return "PSKA job health is not visible in Product API.";
    const summary = health.summary || {};
    return [
      String(health.status || "unknown"),
      `${jobHealthCount(summary, "job")} jobs`,
      `${jobHealthCount(summary, "due")} due`,
      `${jobHealthCount(summary, "failed")} failed`
    ].join(" · ");
  }

  function jobHealthCount(summary, key) {
    return Number(summary?.[`${key}_count`] || summary?.[key] || 0);
  }

  function jobHealthWarning(health) {
    if (!health) return "";
    if (!["needs_attention", "action_required"].includes(String(health.status || ""))) return "";
    const rawGroups = Array.isArray(health.groups) ? health.groups : Object.values(health.groups || {});
    const groups = rawGroups
      .filter((group) => group?.status && group.status !== "ok" && group.status !== "empty")
      .slice(0, 3)
      .map((group) => `${group.id || group.label || "jobs"}: ${group.status}`);
    if (!groups.length) return "";
    return `<div class="pska-mini-warning">Job health: ${escapeHtml(groups.join(" · "))}</div>`;
  }

  function wakeupPlan() {
    return dashboard.wakeupPlan || null;
  }

  function wakeupStatusLabel(plan) {
    if (!plan) return "not visible";
    const status = String(plan.status || "");
    if (status === "active") return "active";
    if (status === "configured") return "configured";
    if (status === "configured_not_loaded") return "not loaded";
    if (status === "install_required") return "setup";
    if (status === "idle") return "idle";
    if (status === "drift") return "drift";
    if (status === "cron_or_external_required") return "external";
    return status || "unknown";
  }

  function wakeupTone(plan) {
    const status = String(plan?.status || "");
    if (!plan) return "bad";
    if (status === "active" || status === "configured" || status === "idle") return "ok";
    if (status === "install_required" || status === "configured_not_loaded" || status === "cron_or_external_required") return "warn";
    return "bad";
  }

  function wakeupTitle(plan) {
    if (!plan) return "PSKA wakeup plan is not visible in Product API.";
    const summary = plan.summary || {};
    return [
      String(plan.status || "unknown"),
      `${summary.scheduled_source_audit_count || 0} scheduled`,
      `${summary.due_source_audit_count || 0} due`,
      summary.next_due_at ? `next ${summary.next_due_at}` : "",
      plan.launchd?.label || ""
    ].filter(Boolean).join(" · ");
  }

  function wakeupWarning(plan) {
    if (!plan) return "";
    const status = String(plan.status || "");
    if (!["install_required", "configured_not_loaded", "drift", "cron_or_external_required"].includes(status)) return "";
    const action = Array.isArray(plan.next_actions) ? plan.next_actions[0] : null;
    const label = action?.label || wakeupStatusLabel(plan);
    return `<div class="pska-mini-warning">Wakeup: ${escapeHtml(label)}. ${escapeHtml(plan.launchd?.install_command || "")}</div>`;
  }

  function observabilityMetrics() {
    return dashboard.observabilityMetrics || null;
  }

  function observabilityMetricsStatusLabel(metrics) {
    if (!metrics) return "not visible";
    const summary = metrics.summary || {};
    const status = String(metrics.status || "");
    if (status === "needs_attention") {
      const failed = Number(summary.failed_event_count || 0);
      if (failed) return `${failed} failed`;
      const proof = Number(summary.answer_failed_check_count || 0);
      if (proof) return `${proof} proof`;
      return "attention";
    }
    if (status === "action_required") {
      const zero = Number(summary.zero_result_event_count || 0);
      if (zero) return `${zero} zero`;
      return "review";
    }
    if (status === "no_recent_signal") return "no signals";
    return `${Number(summary.observed_group_count || 0)} groups`;
  }

  function observabilityMetricsTone(metrics) {
    const status = String(metrics?.status || "");
    if (!metrics) return "bad";
    if (status === "needs_attention") return "bad";
    if (status === "action_required" || status === "no_recent_signal") return "warn";
    return "ok";
  }

  function observabilityMetricsTitle(metrics) {
    if (!metrics) return "PSKA observability metrics are not visible in Product API.";
    const summary = metrics.summary || {};
    return [
      String(metrics.status || "unknown"),
      `${summary.event_count || 0} events`,
      `${summary.failed_event_count || 0} failed`,
      `${summary.zero_result_event_count || 0} zero`,
      `${summary.answer_failed_check_count || 0} proof checks`
    ].join(" · ");
  }

  function observabilityMetricsWarning(metrics) {
    if (!metrics) return "";
    const status = String(metrics.status || "");
    if (!["needs_attention", "action_required"].includes(status)) return "";
    const groups = (Array.isArray(metrics.groups) ? metrics.groups : [])
      .filter((group) => ["needs_attention", "action_required"].includes(String(group?.status || "")))
      .slice(0, 3)
      .map((group) => `${group.id || group.label || "metrics"}: ${group.status}`);
    if (!groups.length) return "";
    return `<div class="pska-mini-warning">Metrics: ${escapeHtml(groups.join(" · "))}</div>`;
  }

  function sourceRecallEval() {
    return dashboard.sourceRecallEval || null;
  }

  function sourceRecallEvalStatusLabel(evalReport) {
    if (!evalReport) return "not visible";
    const summary = evalReport.summary || {};
    if (evalReport.status === "ok") {
      return `${Number(summary.passed_case_count || 0)}/${Number(summary.case_count || 0)}`;
    }
    if (evalReport.status === "needs_attention") {
      return `${Number(summary.failed_case_count || 0)} failed`;
    }
    if (evalReport.status === "no_cases") return "no cases";
    return String(evalReport.status || "unknown");
  }

  function sourceRecallEvalTone(evalReport) {
    const status = String(evalReport?.status || "");
    if (!evalReport) return "bad";
    if (status === "ok") return "ok";
    if (status === "no_cases") return "warn";
    return "bad";
  }

  function sourceRecallEvalTitle(evalReport) {
    if (!evalReport) return "PSKA source recall eval is not visible in Product API.";
    const summary = evalReport.summary || {};
    return [
      String(evalReport.status || "unknown"),
      `${summary.passed_case_count || 0}/${summary.case_count || 0} passed`,
      `${summary.expected_hit_count || 0} expected hits`,
      `${summary.forbidden_hit_count || 0} wrong hits`
    ].join(" · ");
  }

  function sourceRecallEvalWarning(evalReport) {
    if (!evalReport || evalReport.status !== "needs_attention") return "";
    const failedIds = (Array.isArray(evalReport.cases) ? evalReport.cases : [])
      .filter((item) => item?.status !== "ok")
      .slice(0, 3)
      .map((item) => item.case_id || "case");
    return `<div class="pska-mini-warning">Recall: ${escapeHtml(failedIds.join(" · ") || "check failed cases")}</div>`;
  }

  function alphaReadiness() {
    return dashboard.alphaReadiness || null;
  }

  function alphaStatusLabel(readiness) {
    if (!readiness) return "not visible";
    return String(readiness.status || "unknown");
  }

  function alphaTone(readiness) {
    const status = String(readiness?.status || "");
    if (status === "alpha_ready") return "ok";
    if (status === "technical_alpha" || status === "technical_alpha_only") return "warn";
    return "bad";
  }

  function alphaTitle(readiness) {
    if (!readiness) return "Alpha readiness is not visible in PSKA Product API.";
    const summary = readiness.summary || {};
    const parts = [
      readiness.audience || "",
      `pass ${summary.pass_count || 0}/${summary.check_count || 0}`,
      `warn ${summary.warn_count || 0}`,
      `fail ${summary.fail_count || 0}`
    ];
    return parts.filter(Boolean).join(" · ");
  }

  function renderDatasets() {
    const container = document.getElementById("pskaMiniDatasetList");
    if (!container) return;
    if (dashboard.loading && !dashboard.datasets.length) {
      container.innerHTML = `<div class="pska-mini-empty">Loading RAGFlow datasets...</div>`;
      return;
    }
    if (!dashboard.datasets.length) {
      container.innerHTML = `<div class="pska-mini-empty">No datasets loaded. Click Refresh.</div>`;
      return;
    }
    container.innerHTML = dashboard.datasets.map((dataset) => {
      const id = String(dataset.dataset_id || "");
      const checked = state.datasetIds.includes(id);
      return `
        <label class="pska-mini-dataset ${checked ? "is-selected" : ""}">
          <input type="checkbox" data-pska-dataset-id="${escapeAttr(id)}" ${checked ? "checked" : ""}>
          <span>
            <strong>${escapeHtml(dataset.name || id)}</strong>
            <small>${escapeHtml(dataset.document_count || 0)} docs · ${escapeHtml(dataset.chunk_count || 0)} chunks</small>
            <code>${escapeHtml(id)}</code>
          </span>
        </label>
      `;
    }).join("");
  }

  function renderHermesModules() {
    const container = document.getElementById("pskaMiniHermesModules");
    if (!container) return;
    const profileName = String(dashboard.hermesProfile?.name || dashboard.hermesProjects?.active_profile || "default");
    const workspacePath = String(dashboard.hermesWorkspaces?.last || dashboard.hermesProfile?.default_workspace || "");
    const projects = Array.isArray(dashboard.hermesProjects?.projects) ? dashboard.hermesProjects.projects : [];
    const projectNames = projects
      .map((project) => String(project?.name || project?.label || project?.path || "").trim())
      .filter(Boolean)
      .slice(0, 3);
    const suggestions = dashboard.scopeSuggestions || [];
    const scopeButton = document.getElementById("pskaMiniApplySuggestedScope");
    if (scopeButton) scopeButton.disabled = !suggestions.length;
    container.innerHTML = `
      <div class="pska-mini-hermes-grid">
        <span>Profile</span>
        <strong>${escapeHtml(profileName)}</strong>
        <span>Workspace</span>
        <strong title="${escapeAttr(workspacePath)}">${escapeHtml(basename(workspacePath) || "none")}</strong>
        <span>Projects</span>
        <strong>${escapeHtml(projectNames.join(", ") || "none")}</strong>
      </div>
      <div class="pska-mini-suggestions">
        ${suggestions.length ? suggestions.map((item) => `
          <button type="button" data-pska-suggested-dataset="${escapeAttr(item.id)}" title="${escapeAttr(item.reason)}">
            ${escapeHtml(item.name)}
          </button>
        `).join("") : `<span>暂无数据集建议</span>`}
      </div>
    `;
    container.querySelectorAll("[data-pska-suggested-dataset]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.getAttribute("data-pska-suggested-dataset");
        if (!id) return;
        state.datasetIds = Array.from(new Set([...state.datasetIds, id]));
        state.enabled = true;
        saveState();
        renderControls();
        renderDatasets();
        renderHermesModules();
      });
    });
  }

  function renderControls() {
    const chip = document.getElementById("pskaMiniChip");
    const label = document.getElementById("pskaMiniLabel");
    const enabled = document.getElementById("pskaMiniEnabled");
    const mode = document.getElementById("pskaMiniMode");
    const datasetIds = document.getElementById("pskaMiniDatasetIds");
    const documentIds = document.getElementById("pskaMiniDocumentIds");
    const sourceRootIds = document.getElementById("pskaMiniSourceRootIds");
    const maxTokens = document.getElementById("pskaMiniMaxTokens");
    if (chip) chip.classList.toggle("is-active", state.enabled);
    if (label) {
      const selectedParts = [];
      if (state.datasetIds.length) selectedParts.push(`${state.datasetIds.length} KB`);
      if (state.sourceRootIds.length) selectedParts.push(`${state.sourceRootIds.length} source`);
      const selected = selectedParts.length ? ` · ${selectedParts.join(" · ")}` : "";
      if (isCompactComposer()) {
        label.textContent = "PSKA";
      } else {
        label.textContent = state.enabled ? `PSKA ${state.mode}${selected}` : `PSKA off${selected}`;
      }
    }
    if (enabled) enabled.checked = state.enabled;
    if (mode) mode.value = state.mode;
    if (datasetIds) datasetIds.value = state.datasetIds.join("\n");
    if (documentIds) documentIds.value = state.documentIds.join("\n");
    if (sourceRootIds) sourceRootIds.value = state.sourceRootIds.join("\n");
    if (maxTokens) maxTokens.value = String(state.maxTokens);
    renderBridgeStatus();
  }

  function syncFromControls() {
    state.enabled = Boolean(document.getElementById("pskaMiniEnabled")?.checked);
    state.mode = String(document.getElementById("pskaMiniMode")?.value || "auto");
    state.datasetIds = normalizeList(document.getElementById("pskaMiniDatasetIds")?.value || "");
    state.documentIds = normalizeList(document.getElementById("pskaMiniDocumentIds")?.value || "");
    state.sourceRootIds = normalizeList(document.getElementById("pskaMiniSourceRootIds")?.value || "");
    state.maxTokens = boundedInt(document.getElementById("pskaMiniMaxTokens")?.value, 3000, 500, 12000);
    saveState();
    renderControls();
    renderDatasets();
    renderHermesModules();
  }

  function onDatasetToggle(event) {
    const checkbox = event.target?.closest?.("[data-pska-dataset-id]");
    if (!checkbox) return;
    const id = checkbox.dataset.pskaDatasetId || "";
    if (!id) return;
    if (checkbox.checked) {
      state.datasetIds = Array.from(new Set([...state.datasetIds, id]));
    } else {
      state.datasetIds = state.datasetIds.filter((item) => item !== id);
    }
    state.enabled = state.datasetIds.length > 0 || state.enabled;
    saveState();
    renderControls();
    renderDatasets();
    renderHermesModules();
  }

  function renderBridgeStatus() {
    const container = document.getElementById("pskaMiniBridgeStatus");
    if (!container) return;
    const scopeParts = [];
    if (state.datasetIds.length) {
      scopeParts.push(`${state.datasetIds.length} selected knowledge base${state.datasetIds.length === 1 ? "" : "s"}`);
    }
    if (state.sourceRootIds.length) {
      scopeParts.push(`${state.sourceRootIds.length} source root${state.sourceRootIds.length === 1 ? "" : "s"}`);
    }
    const scope = scopeParts.length ? scopeParts.join(" and ") : "auto dataset/source discovery";
    container.innerHTML = state.enabled
      ? `Enabled sends will load <code>${escapeHtml(SKILL_NAME)}</code> with ${escapeHtml(scope)}.`
      : `Turn PSKA on to force <code>${escapeHtml(SKILL_NAME)}</code> for the next send.`;
  }

  function isCompactComposer() {
    return Boolean(window.matchMedia?.("(max-width: 520px)")?.matches);
  }

  function installSendBridge() {
    if (sendBridgeInstalling) return;
    sendBridgeInstalling = true;
    const tryInstall = () => {
      const currentSend = window.send;
      if (typeof currentSend !== "function") {
        window.setTimeout(tryInstall, 250);
        return;
      }
      if (currentSend.__pskaMiniWrapped) return;
      const originalSend = currentSend;
      const wrappedSend = async function pskaMiniWrappedSend(...args) {
        if (!sendBridgeInjecting && shouldApplyToNextSend()) {
          sendBridgeInjecting = true;
          try {
            await prepareChatStartInjection();
            toast("PSKA scope attached to this turn.", "success");
          } catch (error) {
            toast(`PSKA skill bridge failed: ${errorText(error)}`, "error");
          } finally {
            sendBridgeInjecting = false;
          }
        }
        return originalSend.apply(this, args);
      };
      wrappedSend.__pskaMiniWrapped = true;
      wrappedSend.__pskaMiniOriginal = originalSend;
      window.send = wrappedSend;
    };
    tryInstall();
  }

  function installApiBridge() {
    if (apiBridgeInstalling) return;
    apiBridgeInstalling = true;
    const tryInstall = () => {
      const currentApi = window.api;
      if (typeof currentApi !== "function") {
        window.setTimeout(tryInstall, 250);
        return;
      }
      if (currentApi.__pskaMiniWrapped) return;
      const originalApi = currentApi;
      const wrappedApi = async function pskaMiniWrappedApi(path, opts = {}) {
        if (shouldInjectChatStart(path, opts)) {
          opts = injectChatStartMessage(opts);
        }
        return originalApi.call(this, path, opts);
      };
      wrappedApi.__pskaMiniWrapped = true;
      wrappedApi.__pskaMiniOriginal = originalApi;
      window.api = wrappedApi;
    };
    tryInstall();
  }

  function shouldApplyToNextSend() {
    if (!state.enabled) return false;
    const input = document.getElementById("msg");
    const text = String(input?.value || "").trim();
    if (!text) return false;
    if (text.startsWith("/")) return false;
    return true;
  }

  async function prepareChatStartInjection() {
    const skillContent = await loadSkillContent();
    const scopeBlock = buildRuntimeScopeBlock();
    const payload = {
      name: SKILL_NAME,
      directive: `[USER OVERRIDE] You MUST follow the skill '${SKILL_NAME}' and the PSKA-mini runtime scope below before responding to the next message.`,
      content: `${skillContent}\n\n${scopeBlock}`
    };
    pendingChatStartInjection = {
      payload,
      expiresAt: Date.now() + 30000
    };
  }

  async function loadSkillContent() {
    const now = Date.now();
    if (skillCache && now - skillCache.loadedAt < SKILL_CACHE_TTL_MS) return skillCache.content;
    const data = await fetchWebuiJson(`/api/skills/content?name=${encodeURIComponent(SKILL_NAME)}`, {
      timeoutMs: 10000
    });
    const content = String(data?.content || "").trim();
    if (!content) throw new Error(`Skill ${SKILL_NAME} has no readable content`);
    skillCache = { loadedAt: now, content };
    return content;
  }

  function buildRuntimeScopeBlock() {
    const payload = {
      enabled: state.enabled,
      mode: state.mode,
      dataset_ids: state.datasetIds,
      document_ids: state.documentIds,
      source_root_ids: state.sourceRootIds,
      max_tokens: state.maxTokens,
      source: "hermes-webui.pska-mini-chip",
      hermes: currentHermesContext()
    };
    const lines = [
      "## PSKA-Mini Runtime Scope",
      "",
      "Use this browser-selected scope for this turn. Do not invent dataset IDs.",
      "",
      "```json",
      JSON.stringify(payload, null, 2),
      "```",
      "",
      "Operational rule: when PSKA is enabled from the chip, use PSKA-Essential MCP retrieval tools for knowledge-base evidence before answering. Treat memory and embedding as governed PSKA components; keep retrieval working when an optional component is unavailable, and mention the unavailable component only when it matters."
    ];
    return lines.join("\n");
  }

  function currentScopePayload() {
    return {
      dataset_ids: state.datasetIds,
      document_ids: state.documentIds,
      hermes: currentHermesContext()
    };
  }

  function currentSourceScopePayload() {
    return {
      root_ids: state.sourceRootIds
    };
  }

  function shouldInjectChatStart(path, opts) {
    if (!pendingChatStartInjection) return false;
    if (Date.now() > pendingChatStartInjection.expiresAt) {
      pendingChatStartInjection = null;
      return false;
    }
    if (String(path || "") !== "/api/chat/start") return false;
    return Boolean(opts && typeof opts.body === "string");
  }

  function injectChatStartMessage(opts) {
    const injection = pendingChatStartInjection;
    pendingChatStartInjection = null;
    if (!injection) return opts;
    try {
      const body = JSON.parse(opts.body);
      const originalMessage = String(body.message || "").trim();
      if (!originalMessage) return opts;
      body.message = buildForcedSkillMessage(injection.payload, originalMessage);
      return { ...opts, body: JSON.stringify(body) };
    } catch (error) {
      toast(`PSKA payload injection failed: ${errorText(error)}`, "error");
      return opts;
    }
  }

  function buildForcedSkillMessage(payload, originalMessage) {
    const name = String(payload?.name || "").trim();
    const directive = String(payload?.directive || "").trim();
    const content = String(payload?.content || "").trim();
    const block = name && content
      ? `[FORCED SKILL CONTEXT: ${name}]\n${content}\n[/FORCED SKILL CONTEXT]`
      : "";
    return `${directive}${block ? `\n\n${block}` : ""}\n\n${originalMessage}`.trim();
  }

  function installDisplaySanitizer() {
    const tryInstall = () => {
      const currentMsgContent = window.msgContent;
      if (typeof currentMsgContent !== "function") {
        window.setTimeout(tryInstall, 250);
        return;
      }
      if (currentMsgContent.__pskaMiniWrapped) return;
      const wrappedMsgContent = function pskaMiniMsgContent(message) {
        const text = currentMsgContent.call(this, message);
        if (message?.role !== "user") return text;
        return stripForcedSkillEnvelope(text);
      };
      wrappedMsgContent.__pskaMiniWrapped = true;
      wrappedMsgContent.__pskaMiniOriginal = currentMsgContent;
      window.msgContent = wrappedMsgContent;
      try {
        msgContent = wrappedMsgContent;
      } catch (_) {}
      try {
        if (typeof window.renderMessages === "function") {
          window.renderMessages({ preserveScroll: true });
        }
      } catch (_) {}
    };
    tryInstall();
  }

  function installVisibleEnvelopeCleaner() {
    const clean = () => cleanVisibleForcedSkillRows();
    window.setTimeout(clean, 500);
    window.setInterval(clean, 1500);
    const attachObserver = () => {
      const target = document.getElementById("msgInner") || document.body;
      if (!target || target.__pskaMiniEnvelopeObserver) return;
      const observer = new MutationObserver(() => clean());
      observer.observe(target, { childList: true, subtree: true, characterData: true });
      target.__pskaMiniEnvelopeObserver = observer;
      clean();
    };
    attachObserver();
    window.setTimeout(attachObserver, 1000);
    window.setTimeout(attachObserver, 3000);
  }

  function cleanVisibleForcedSkillRows() {
    document.querySelectorAll('.msg-row[data-role="user"]').forEach((row) => {
      const body = row.querySelector(".msg-body");
      if (!body) return;
      const raw = row.dataset.rawText || body.innerText || "";
      if (!raw.includes("[FORCED SKILL CONTEXT") && !raw.includes("[USER OVERRIDE]")) return;
      const clean = stripForcedSkillEnvelope(raw);
      if (!clean || clean === raw) return;
      row.dataset.rawText = clean;
      row.dataset.pskaMiniCleaned = "1";
      body.innerHTML = escapeHtml(clean).replace(/\n/g, "<br>");
    });
  }

  function stripForcedSkillEnvelope(text) {
    let value = String(text || "").trim();
    value = value.replace(/^\[USER OVERRIDE\][^\n]*\n*/i, "").trim();
    value = value.replace(/\[FORCED SKILL CONTEXT:[^\]]+\][\s\S]*?\[\/FORCED SKILL CONTEXT\]\s*/gi, "").trim();
    return value;
  }

  function exposeRuntimeApi() {
    window.PSKAMini = {
      getState: () => JSON.parse(JSON.stringify(state)),
      getTurnInstructions: buildRuntimeScopeBlock,
      refresh: refreshDashboard,
      jarvisBrief: runJarvisBrief,
      agenticBrief: runAgenticBrief,
      sourceRecall: runSourceRecall,
      setEnabled(value) {
        state.enabled = Boolean(value);
        saveState();
        renderControls();
      },
      setSourceRootIds(value) {
        state.sourceRootIds = normalizeList(value);
        state.enabled = state.sourceRootIds.length > 0 || state.enabled;
        saveState();
        renderControls();
      }
    };
  }

  function selectReadyDatasets() {
    const readyIds = (dashboard.workspace?.kb?.ready_dataset_ids || dashboard.datasets.map((dataset) => dataset.dataset_id))
      .map((id) => String(id || ""))
      .filter(Boolean);
    state.datasetIds = Array.from(new Set(readyIds));
    state.enabled = state.datasetIds.length > 0 || state.enabled;
    saveState();
    renderControls();
    renderDatasets();
    renderHermesModules();
  }

  function clearDatasets() {
    state.datasetIds = [];
    saveState();
    renderControls();
    renderDatasets();
    renderHermesModules();
  }

  function applySuggestedScope() {
    const suggestions = dashboard.scopeSuggestions || [];
    if (!suggestions.length) {
      showPreviewText("当前 Hermes profile/project 没有匹配到数据集建议。");
      return;
    }
    state.datasetIds = Array.from(new Set(suggestions.slice(0, 3).map((item) => item.id).filter(Boolean)));
    state.enabled = state.datasetIds.length > 0;
    saveState();
    renderControls();
    renderDatasets();
    renderHermesModules();
    showPreviewText(`已应用 ${state.datasetIds.length} 个建议数据集。`);
  }

  async function runRetrievalProbe() {
    syncFromControls();
    const box = document.getElementById("pskaMiniPreviewBox");
    if (!box) return;
    const message = String(document.getElementById("msg")?.value || "").trim() || "PSKA retrieval probe";
    box.hidden = false;
    if (!state.datasetIds.length) {
      box.textContent = "Select at least one RAGFlow dataset first.";
      return;
    }
    box.textContent = "Running RAGFlow retrieval probe...";
    try {
      const data = await pskaMiniFetchJson("/api/runtime/retrieval-probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: message,
          dataset_ids: state.datasetIds,
          document_ids: state.documentIds,
          limit: 3,
          use_kg: false
        }),
        timeoutMs: 20000
      });
      const probe = data.probe || {};
      const refs = probe.source_refs || [];
      box.textContent = [
        probe.message || probe.status || "Retrieval completed.",
        `contexts: ${probe.context_count || refs.length || 0}`,
        ...refs.slice(0, 3).map((ref, index) => {
          const excerpt = ref.metadata?.content_excerpt || "";
          return `\n[${index + 1}] ${ref.title || ref.document_id || "source"}\n${excerpt.slice(0, 420)}`;
        })
      ].join("\n");
    } catch (error) {
      box.textContent = `RAGFlow probe failed: ${errorText(error)}`;
    }
  }

  async function previewTurnContext() {
    syncFromControls();
    const box = document.getElementById("pskaMiniPreviewBox");
    if (!box) return;
    const message = currentComposerMessage("PSKA-mini preview");
    box.hidden = false;
    box.textContent = "Loading turn context...";
    if ((state.mode === "project" || state.mode === "evidence-only") && !state.datasetIds.length) {
      box.textContent = "Select a dataset, or switch mode to auto/memory-only.";
      return;
    }
    const previewMode = state.mode === "auto" && !state.datasetIds.length ? "memory-only" : state.mode;
    const maxEvidenceBlocks = previewMode === "memory-only" ? 0 : 3;
    try {
      const data = await pskaMiniFetchJson("/api/turn-context", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          caller: "hermes-webui-extension",
          user_message: message,
          mode: previewMode,
          scope: {
            dataset_ids: state.datasetIds,
            document_ids: state.documentIds
          },
          budget: {
            max_evidence_blocks: maxEvidenceBlocks,
            max_memory_notes: 3,
            max_tokens: state.maxTokens
          },
          requirements: {
            need_citations: true
          }
        }),
        timeoutMs: 20000
      });
      const context = data.turn_context || {};
      box.textContent = [
        context.summary || "No summary.",
        `evidence: ${(context.evidence_blocks || []).length}`,
        `memory: ${(context.memory_notes || []).length}`,
        `citations: ${(context.citations || []).length}`
      ].join("\n");
    } catch (error) {
      box.textContent = `PSKA preview failed: ${errorText(error)}`;
    }
  }

  async function runJarvisBrief() {
    syncFromControls();
    showPreviewText("Building Jarvis briefing...");
    try {
      const data = await pskaMiniFetchJson("/api/jarvis/briefing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          compact: true,
          view: "webui",
          scope: currentScopePayload(),
          source_scope: currentSourceScopePayload(),
          audit_limit: 12,
          dataset_page_size: 20,
          review_limit: 30,
          workflow_limit: 30
        }),
        timeoutMs: 30000
      });
      showPreviewText(formatJarvisBrief(data.briefing || {}));
    } catch (error) {
      showPreviewText(`Jarvis briefing failed: ${errorText(error)}`);
    }
  }

  async function runAgenticBrief() {
    syncFromControls();
    const question = currentComposerMessage("What should Hermes recall before answering about this PSKA workspace?");
    showPreviewText("Building agentic context brief...");
    try {
      const data = await pskaMiniFetchJson("/api/agentic/context-brief", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          compact: true,
          view: "webui",
          objective: "Prepare Hermes pre-answer context for the current WebUI turn.",
          question,
          project_hint: currentHermesContext().workspace || "",
          scope: currentScopePayload(),
          source_scope: currentSourceScopePayload(),
          evidence_limit: 4,
          source_limit: 4,
          memory_limit: 4,
          trace_limit: 8
        }),
        timeoutMs: 30000
      });
      showPreviewText(formatAgenticBrief(data.agentic_context_brief || {}));
    } catch (error) {
      showPreviewText(`Agentic brief failed: ${errorText(error)}`);
    }
  }

  async function runSourceRecall() {
    syncFromControls();
    const query = currentComposerMessage("PSKA source recall");
    showPreviewText("Running metadata-first source recall...");
    try {
      const data = await pskaMiniFetchJson("/api/sources/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          scope: currentSourceScopePayload(),
          limit: 5
        }),
        timeoutMs: 20000
      });
      showPreviewText(formatSourceRecall(data.context_packets || [], data.count || 0));
    } catch (error) {
      showPreviewText(`Source recall failed: ${errorText(error)}`);
    }
  }

  async function syncReviewBoard() {
    const box = document.getElementById("pskaMiniPreviewBox");
    if (!box) return;
    box.hidden = false;
    box.textContent = "正在同步 PSKA 审核项到 Hermes Kanban...";
    try {
      const reviewsPayload = await pskaMiniFetchJson("/api/reviews?limit=50", { timeoutMs: 10000 });
      const reviews = normalizeReviews(reviewsPayload)
        .filter((review) => shouldProjectReview(review))
        .slice(0, 25);
      await fetchWebuiJson("/api/kanban/boards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slug: REVIEW_BOARD_SLUG,
          name: "PSKA Review",
          description: "Projection of the PSKA review queue",
          icon: "check-square",
          color: "#4b7bec"
        }),
        timeoutMs: 10000
      });
      let synced = 0;
      for (const review of reviews) {
        const taskPayload = reviewTaskPayload(review);
        const created = await fetchWebuiJson("/api/kanban/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(taskPayload),
          timeoutMs: 10000
        });
        const taskId = created?.task?.id || created?.task?.task_id;
        if (taskId) {
          await fetchWebuiJson(`/api/kanban/tasks/${encodeURIComponent(taskId)}/patch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              board: REVIEW_BOARD_SLUG,
              title: taskPayload.title,
              body: taskPayload.body,
              priority: taskPayload.priority,
              status: taskPayload.status
            }),
            timeoutMs: 10000
          });
        }
        synced += 1;
      }
      box.textContent = reviews.length
        ? `已同步 ${synced} 张 PSKA 审核卡片到 Hermes Kanban 看板 "${REVIEW_BOARD_SLUG}"。`
        : `PSKA Review 看板已就绪；没有待处理审核候选。`;
      toast("PSKA review board synced.", "success");
    } catch (error) {
      box.textContent = `同步审核看板失败：${errorText(error)}`;
      toast(`PSKA review sync failed: ${errorText(error)}`, "error");
    }
  }

  async function createDigestTask() {
    const box = document.getElementById("pskaMiniPreviewBox");
    if (!box) return;
    box.hidden = false;
    box.textContent = "正在检查 Hermes Tasks...";
    try {
      const jobsPayload = await fetchWebuiJson("/api/crons", { timeoutMs: 10000 });
      const jobs = Array.isArray(jobsPayload?.jobs) ? jobsPayload.jobs : [];
      const existing = jobs.find((job) => {
        const name = String(job?.name || "");
        const prompt = String(job?.prompt || "");
        return name === DIGEST_TASK_NAME || prompt.includes(DIGEST_TASK_MARKER);
      });
      if (existing) {
        box.textContent = `摘要任务已存在：${existing.name || existing.id || DIGEST_TASK_NAME}`;
        toast("PSKA digest task already exists.", "success");
        return;
      }
      const data = await fetchWebuiJson("/api/crons/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: DIGEST_TASK_NAME,
          schedule: "every 1h",
          deliver: "local",
          skills: [SKILL_NAME],
          prompt: buildDigestTaskPrompt()
        }),
        timeoutMs: 10000
      });
      const job = data.job || {};
      box.textContent = `已创建 Hermes 任务：${job.name || DIGEST_TASK_NAME}。自动定时运行仍需要 Hermes gateway daemon。`;
      toast("PSKA digest task created.", "success");
    } catch (error) {
      box.textContent = `创建摘要任务失败：${errorText(error)}`;
      toast(`PSKA digest task failed: ${errorText(error)}`, "error");
    }
  }

  function buildScopeSuggestions(view) {
    const datasets = Array.isArray(view.datasets) ? view.datasets : [];
    const context = currentHermesContext(view);
    const searchValues = [
      context.profile,
      context.workspace,
      basename(context.workspace),
      ...context.projects
    ].filter(Boolean);
    const tokens = scopeTokens(searchValues);
    if (!datasets.length || !tokens.length) return [];
    return datasets
      .map((dataset) => {
        const id = String(dataset.dataset_id || dataset.id || "");
        const name = String(dataset.name || id || "");
        const haystack = normalizeSearchText(`${name} ${id}`);
        let score = 0;
        const matched = [];
        tokens.forEach((token) => {
          if (!token || token.length < 2) return;
          if (haystack.includes(token)) {
            score += Math.min(6, token.length);
            matched.push(token);
          }
        });
        return { id, name, score, reason: matched.length ? `matched ${matched.slice(0, 4).join(", ")}` : "" };
      })
      .filter((item) => item.id && item.score > 0)
      .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
      .slice(0, 3);
  }

  function currentHermesContext(view = dashboard) {
    const profile = String(view.hermesProfile?.name || view.hermesProjects?.active_profile || "").trim();
    const workspace = String(view.hermesWorkspaces?.last || view.hermesProfile?.default_workspace || "").trim();
    const projects = Array.isArray(view.hermesProjects?.projects) ? view.hermesProjects.projects : [];
    return {
      profile: profile || "default",
      workspace,
      projects: projects
        .map((project) => String(project?.name || project?.label || project?.path || "").trim())
        .filter(Boolean)
        .slice(0, 8)
    };
  }

  function scopeTokens(values) {
    const tokens = [];
    values.forEach((value) => {
      const normalized = normalizeSearchText(value);
      const parts = normalized.match(/[a-z0-9\u4e00-\u9fff]+/g) || [];
      parts.forEach((part) => {
        if (part.length >= 2) tokens.push(part);
      });
    });
    return Array.from(new Set(tokens));
  }

  function normalizeSearchText(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[_\-.\\/]+/g, " ")
      .trim();
  }

  function normalizeReviews(payload) {
    const direct = payload?.reviews || payload?.items || payload?.candidates || [];
    if (Array.isArray(direct)) return direct;
    if (Array.isArray(payload?.review_candidates)) return payload.review_candidates;
    return [];
  }

  function shouldProjectReview(review) {
    const status = normalizeReviewStatus(review);
    return ["pending", "accepted", "needs_revision", "needs_edit"].includes(status);
  }

  function normalizeReviewStatus(review) {
    return String(review?.status || review?.decision_status || review?.state || "pending")
      .toLowerCase()
      .replace(/[\s-]+/g, "_");
  }

  function reviewTaskPayload(review) {
    const reviewId = String(review?.review_id || review?.id || review?.candidate_id || "");
    const status = normalizeReviewStatus(review);
    const proposal = review?.proposal || review?.candidate || review?.payload || {};
    const kind = String(review?.kind || proposal?.kind || proposal?.type || "candidate");
    return {
      board: REVIEW_BOARD_SLUG,
      title: reviewTaskTitle(proposal, status, kind, reviewId),
      body: reviewTaskBody(review, proposal, reviewId, status, kind),
      created_by: "pska-mini",
      priority: reviewPriority(status),
      status: reviewKanbanStatus(status),
      idempotency_key: reviewId ? `pska-review:${reviewId}` : `pska-review:${kind}:${fingerprint(proposal)}`,
      skills: [SKILL_NAME]
    };
  }

  function reviewTaskTitle(proposal, status, kind, reviewId) {
    const readable = cleanReviewTitle(
      proposal?.title
      || proposal?.intent
      || firstLine(proposal?.body)
      || reviewId
      || "审核候选"
    );
    return truncate(`PSKA ${reviewStatusLabel(status)} · ${reviewKindLabel(kind)} · ${readable}`, 120);
  }

  function reviewTaskBody(review, proposal, reviewId, status, kind) {
    const evidence = proposal?.evidence || proposal?.evidence_refs || proposal?.source_refs || review?.evidence || [];
    const rationale = String(proposal?.rationale || review?.rationale || proposal?.reason || "").trim();
    const candidateBody = String(proposal?.body || proposal?.memory_patch?.text || proposal?.memory_update?.text || "").trim();
    const body = [
      "PSKA 是权威来源；这张 Kanban 卡只是工作视图。",
      "",
      `审核 ID：${reviewId || "unknown"}`,
      `类型：${reviewKindLabel(kind)}`,
      `状态：${reviewStatusLabel(status)}`,
      reviewId ? `PSKA API：GET /api/reviews/${reviewId}` : "",
      "",
      candidateBody ? `候选内容：\n${truncate(candidateBody, 1400)}` : "",
      rationale ? `\n理由：\n${truncate(rationale, 500)}` : "",
      Array.isArray(evidence) && evidence.length ? `\n证据：\n${evidence.slice(0, 5).map((ref, index) => evidenceLine(ref, index)).join("\n")}` : "",
      "",
      "原始详情请回到 PSKA Review 或调用上面的 PSKA API 查看。"
    ].filter(Boolean);
    return body.join("\n");
  }

  function evidenceLine(ref, index) {
    const title = String(ref?.title || ref?.document_id || ref?.source_id || "source");
    const chunk = String(ref?.chunk_id || ref?.external_id || "").trim();
    const suffix = chunk ? ` · ${shortId(chunk)}` : "";
    return `${index + 1}. ${title}${suffix}`;
  }

  function reviewKindLabel(kind) {
    const value = String(kind || "").toLowerCase();
    if (value === "memory_patch") return "新增记忆候选";
    if (value === "memory_update") return "更新记忆候选";
    if (value === "memory_delete") return "删除记忆候选";
    if (value === "digest") return "摘要候选";
    if (value === "writing_brief") return "写作简报";
    return value || "审核候选";
  }

  function reviewStatusLabel(status) {
    const value = String(status || "").toLowerCase();
    if (value === "pending") return "待审核";
    if (value === "accepted") return "已接受待应用";
    if (value === "needs_revision" || value === "needs_edit") return "需修订";
    if (value === "rejected") return "已拒绝";
    if (value === "applied") return "已应用";
    return value || "未知状态";
  }

  function cleanReviewTitle(value) {
    return String(value || "")
      .replace(/^Memory Patch:\s*/i, "")
      .replace(/^Memory Update:\s*/i, "")
      .replace(/^Memory Delete:\s*/i, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function reviewKanbanStatus(status) {
    if (status === "accepted") return "ready";
    if (status === "needs_revision" || status === "needs_edit") return "blocked";
    return "triage";
  }

  function reviewPriority(status) {
    if (status === "accepted") return 2;
    if (status === "needs_revision" || status === "needs_edit") return 1;
    return 3;
  }

  function buildDigestTaskPrompt() {
    const context = currentHermesContext();
    const scope = {
      dataset_ids: state.datasetIds,
      document_ids: state.documentIds,
      source_root_ids: state.sourceRootIds,
      hermes: context
    };
    return [
      DIGEST_TASK_MARKER,
      "",
      "Use PSKA-Essential MCP tools to inspect provider jobs and digest jobs.",
      "Run only queued or ready digest work. Do not write durable memory directly; leave candidates in PSKA Review unless the user has explicitly approved applying them.",
      "If a memory backend is unavailable, keep RAGFlow evidence and PSKA review paths working and report the degraded memory backend briefly.",
      "",
      "Runtime scope:",
      "```json",
      JSON.stringify(scope, null, 2),
      "```"
    ].join("\n");
  }

  function formatJarvisBrief(briefing) {
    const summary = briefing.summary || {};
    const priorities = Array.isArray(briefing.priorities) ? briefing.priorities : [];
    const actions = Array.isArray(briefing.next_actions) ? briefing.next_actions : [];
    const lines = [
      `Jarvis Brief · ${briefing.status || "unknown"}`,
      `datasets: ${summary.workspace_status || "unknown"} · pending reviews: ${summary.pending_review_count || 0} · memory focus: ${summary.memory_focus_count || 0}`,
      `source roots: ${summary.source_root_count || 0} · duplicates: ${summary.duplicate_group_count || 0} · broken links: ${summary.unresolved_link_count || 0}`,
      "",
      "Priorities:",
      ...(priorities.length ? priorities.slice(0, 4).map((item, index) => `${index + 1}. ${item.title || item.code || item.action || "priority"} - ${item.message || item.detail || ""}`) : ["none"]),
      "",
      "Next actions:",
      ...(actions.length ? actions.slice(0, 4).map((item, index) => `${index + 1}. ${item.label || item.action || "action"} (${item.tool || item.api || "PSKA"})`) : ["none"])
    ];
    return lines.join("\n");
  }

  function formatAgenticBrief(brief) {
    const summary = brief.summary || {};
    const recall = brief.recall || {};
    const memory = brief.memory || {};
    const trace = brief.trace || {};
    const specialists = brief.specialists || {};
    const evidence = Array.isArray(recall.evidence_blocks) ? recall.evidence_blocks : (Array.isArray(recall.kb_evidence) ? recall.kb_evidence : []);
    const sources = Array.isArray(recall.source_recall) ? recall.source_recall : [];
    const memories = Array.isArray(memory.relevant_memories) ? memory.relevant_memories : [];
    const profiles = Array.isArray(specialists.recommended_profiles) ? specialists.recommended_profiles : [];
    const actions = Array.isArray(brief.next_actions) ? brief.next_actions : [];
    const lines = [
      `Agentic Brief · ${brief.status || summary.status || "unknown"}`,
      summary.lead || `Prepared ${evidence.length} evidence, ${sources.length} source, ${memories.length} memory, ${trace.signal_count || 0} trace signal(s).`,
      "",
      "Evidence:",
      ...(evidence.length ? evidence.slice(0, 3).map((item, index) => `${index + 1}. ${item.title || item.context_id || "evidence"} - ${truncate(item.text || "", 220)}`) : ["none"]),
      "",
      "Source recall:",
      ...(sources.length ? sources.slice(0, 3).map((item, index) => `${index + 1}. ${item.title || item.context_id || "source"} - ${truncate(item.text || "", 220)}`) : ["none"]),
      "",
      "Memory:",
      ...(memories.length ? memories.slice(0, 3).map((item, index) => `${index + 1}. ${item.fact_id || "memory"} - ${truncate(item.text || "", 220)}`) : ["none"]),
      "",
      "Specialists:",
      ...(profiles.length ? profiles.slice(0, 4).map((item, index) => {
        const tools = item.tool_profile?.read_tools || [];
        return `${index + 1}. ${item.label || item.profile_id || "specialist"} - ${truncate(item.purpose || "", 160)} (${tools.length} read tool${tools.length === 1 ? "" : "s"})`;
      }) : ["none"]),
      "",
      "Next actions:",
      ...(actions.length ? actions.slice(0, 4).map((item, index) => `${index + 1}. ${item.label || item.action || "action"} (${item.tool || item.api || "PSKA"})`) : ["none"])
    ];
    return lines.join("\n");
  }

  function formatSourceRecall(packets, count) {
    const items = Array.isArray(packets) ? packets : [];
    if (!items.length) return `Source Recall · ${count || 0} result(s)\nNo registered source matched this query.`;
    const lines = [
      `Source Recall · ${count || items.length} result(s)`,
      ...items.slice(0, 5).map((packet, index) => {
        const ref = packet.source_ref || {};
        const location = ref.path || ref.source_id || packet.context_id || "";
        return `\n${index + 1}. ${packet.title || ref.title || location || "source"}\n${location}\n${truncate(packet.text || "", 360)}`;
      })
    ];
    return lines.join("\n");
  }

  function currentComposerMessage(fallback) {
    return String(document.getElementById("msg")?.value || "").trim() || fallback;
  }

  function showPreviewText(text) {
    const box = document.getElementById("pskaMiniPreviewBox");
    if (!box) return;
    box.hidden = false;
    box.textContent = text;
  }

  function stableJson(value) {
    try {
      return JSON.stringify(sortJson(value), null, 2);
    } catch (_) {
      return String(value || "");
    }
  }

  function sortJson(value) {
    if (Array.isArray(value)) return value.map(sortJson);
    if (!value || typeof value !== "object") return value;
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortJson(value[key])]));
  }

  function truncate(value, maxLength) {
    const text = String(value || "");
    return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
  }

  function firstLine(value) {
    return String(value || "").split(/\r?\n/)[0] || "";
  }

  function shortId(value, maxLength = 8) {
    return String(value || "").slice(0, maxLength);
  }

  function fingerprint(value) {
    const text = stableJson(value).replace(/[^a-zA-Z0-9]+/g, "").slice(0, 80);
    return text || "unknown";
  }

  function basename(path) {
    const text = String(path || "").replace(/\/+$/g, "");
    if (!text) return "";
    const parts = text.split(/[\\/]/);
    return parts[parts.length - 1] || text;
  }

  function lastNameSegment(value) {
    const text = String(value || "");
    const parts = text.split("__");
    return parts[parts.length - 1] || text;
  }

  async function pskaMiniFetchJson(path, options = {}) {
    const response = await pskaMiniFetch(path, options);
    const text = await response.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(text || `${response.status} ${response.statusText}`);
    }
    if (!response.ok || data.ok === false) throw new Error(errorMessage(data, response.statusText));
    return data;
  }

  async function fetchWebuiJson(path, options = {}) {
    const target = String(path || "").startsWith("/") ? path : `/${path || ""}`;
    const headers = { ...(options.headers || {}) };
    const timeoutMs = Number(options.timeoutMs || 15000);
    addCsrfHeader(target, options, headers);
    const fetchOptions = { ...options };
    delete fetchOptions.timeoutMs;
    try {
      const response = await requestWithTimeout(target, {
        ...fetchOptions,
        credentials: "same-origin",
        headers
      }, timeoutMs);
      const text = await response.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        throw new Error(text || `${response.status} ${response.statusText}`);
      }
      if (!response.ok || data.ok === false) throw new Error(errorMessage(data, response.statusText));
      return data;
    } catch (error) {
      throw error;
    }
  }

  function pskaMiniFetch(path, options = {}) {
    const target = `${PSKA_API_BASE}${String(path || "").startsWith("/") ? "" : "/"}${path || ""}`;
    const headers = { ...(options.headers || {}) };
    const timeoutMs = Number(options.timeoutMs || 15000);
    addCsrfHeader(target, options, headers);
    const fetchOptions = { ...options };
    delete fetchOptions.timeoutMs;
    return requestWithTimeout(target, {
      ...fetchOptions,
      credentials: "same-origin",
      headers
    }, timeoutMs);
  }

  function requestWithTimeout(target, options = {}, timeoutMs = 15000) {
    if (typeof window.fetch === "function") {
      const controller = typeof AbortController === "function" ? new AbortController() : null;
      const timer = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
      const fetchOptions = { ...options };
      if (controller) fetchOptions.signal = controller.signal;
      return window.fetch(target, fetchOptions).finally(() => {
        if (timer) window.clearTimeout(timer);
      });
    }
    return xhrRequest(target, options, timeoutMs);
  }

  function xhrRequest(target, options = {}, timeoutMs = 15000) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const method = String(options.method || "GET").toUpperCase();
      xhr.open(method, target, true);
      xhr.withCredentials = true;
      xhr.timeout = timeoutMs;
      const headers = options.headers || {};
      Object.entries(headers).forEach(([key, value]) => {
        if (value === undefined || value === null) return;
        xhr.setRequestHeader(key, String(value));
      });
      xhr.onload = () => {
        resolve({
          ok: xhr.status >= 200 && xhr.status < 300,
          status: xhr.status,
          statusText: xhr.statusText || String(xhr.status),
          text: () => Promise.resolve(xhr.responseText || "")
        });
      };
      xhr.onerror = () => reject(new Error("request failed"));
      xhr.ontimeout = () => {
        const error = new Error("request timed out");
        error.name = "AbortError";
        reject(error);
      };
      xhr.send(options.body === undefined ? null : options.body);
    });
  }

  function addCsrfHeader(target, options = {}, headers = {}) {
    const method = String(options.method || "GET").toUpperCase();
    if (!/^(POST|PUT|PATCH|DELETE)$/u.test(method)) return;
    if (headers["X-Hermes-CSRF-Token"] || headers["x-hermes-csrf-token"]) return;
    let url;
    try {
      url = new URL(target, window.location.href);
    } catch {
      return;
    }
    if (url.origin !== window.location.origin) return;
    const token = window.__HERMES_CONFIG__?.csrfToken;
    if (token) headers["X-Hermes-CSRF-Token"] = String(token);
  }

  function toggleMenu(event) {
    event?.stopPropagation();
    const menu = document.getElementById("pskaMiniMenu");
    if (!menu) return;
    if (menu.hidden) {
      openMenu();
      if (!dashboard.loadedAt && !dashboard.loading) refreshDashboard();
    } else {
      closeMenu();
    }
  }

  function openMenu() {
    const menu = document.getElementById("pskaMiniMenu");
    const chip = document.getElementById("pskaMiniChip");
    if (menu) menu.hidden = false;
    if (chip) chip.setAttribute("aria-expanded", "true");
  }

  function closeMenu() {
    const menu = document.getElementById("pskaMiniMenu");
    const chip = document.getElementById("pskaMiniChip");
    if (menu) menu.hidden = true;
    if (chip) chip.setAttribute("aria-expanded", "false");
  }

  async function settleObject(requests) {
    const entries = await Promise.all(
      Object.entries(requests).map(async ([key, promise]) => [key, await Promise.resolve(promise).then(
        (value) => ({ status: "fulfilled", value }),
        (reason) => ({ status: "rejected", reason })
      )])
    );
    return Object.fromEntries(entries);
  }

  function valueOrNull(result) {
    return result?.status === "fulfilled" ? result.value : null;
  }

  function sidecarProxyBase(id) {
    return `/api/extensions/${encodeURIComponent(id)}/sidecar`;
  }

  function toast(message, type) {
    if (typeof window.showToast === "function") window.showToast(message, 3000, type);
  }

  function errorText(error) {
    if (error?.name === "AbortError") return "request timed out";
    return error?.message || String(error || "request failed");
  }

  function errorMessage(data, fallback) {
    if (data && typeof data.error === "string") return data.error;
    if (data && data.error && typeof data.error.message === "string") return data.error.message;
    if (data && typeof data.message === "string") return data.message;
    return fallback || "request failed";
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/"/g, "&quot;");
  }

  function cssEscape(value) {
    if (window.CSS?.escape) return window.CSS.escape(String(value || ""));
    return String(value || "").replace(/["\\\]]/g, "\\$&");
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
