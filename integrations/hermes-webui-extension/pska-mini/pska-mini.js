(() => {
  const EXT_ID = "pska-mini";
  const PSKA_API_BASE = sidecarProxyBase(EXT_ID);
  const STORAGE_KEY = "pska-mini.hermes-webui.scope.v1";
  const SKILL_NAME = "knowledge-retrieval";
  const SKILL_CACHE_TTL_MS = 5 * 60 * 1000;
  const REVIEW_BOARD_SLUG = "pska-review";
  const DIGEST_TASK_NAME = "PSKA Digest Runner";
  const DIGEST_TASK_MARKER = "PSKA-Mini Digest Runner";
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
    reviewStatus: "pending",
    detail: null,
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
          <div class="pska-mini-page-sub">PSKA SQLite memory and review queue</div>
        </div>
        <div class="main-view-actions">
          <button class="pska-mini-page-btn" id="pskaMiniPageRefresh" type="button">Refresh</button>
        </div>
      </div>
      <div class="main-view-body">
        <div class="main-view-content pska-mini-page-content">
          <section class="pska-mini-page-status" id="pskaMiniPageStatus"></section>
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
              <details class="pska-mini-memory-create">
                <summary>Create review candidate</summary>
                <textarea id="pskaMiniMemoryDraft" rows="4" placeholder="A durable fact worth reviewing"></textarea>
                <div class="pska-mini-memory-create-actions">
                  <label><input id="pskaMiniMemoryForceReview" type="checkbox" checked> force review</label>
                  <button class="pska-mini-page-btn" id="pskaMiniCreateMemoryReview" type="button">Create</button>
                </div>
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
    panel.querySelector("#pskaMiniMemorySearch").addEventListener("click", runMemoryPageSearch);
    panel.querySelector("#pskaMiniMemoryQuery").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        runMemoryPageSearch();
      }
    });
    panel.querySelector("#pskaMiniReviewStatus").addEventListener("change", () => {
      memoryPage.reviewStatus = String(panel.querySelector("#pskaMiniReviewStatus")?.value || "pending");
      loadMemoryPageReviews();
    });
    panel.querySelector("#pskaMiniReviewList").addEventListener("click", onReviewListClick);
    panel.querySelector("#pskaMiniCreateMemoryReview").addEventListener("click", createMemoryReviewCandidate);
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
      sub.textContent = "SQLite memory / review queue";
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
      await Promise.all([refreshDashboard(), loadMemoryPageReviews(), runMemoryPageSearch({ silentEmpty: true })]);
      memoryPage = { ...memoryPage, loading: false, loadedAt: new Date().toLocaleTimeString(), message: "Loaded." };
    } catch (error) {
      memoryPage = { ...memoryPage, loading: false, error: errorText(error), message: "" };
    }
    renderMemoryPage();
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
          reason: "Created from Hermes WebUI PSKA Memory page",
          force_review: forceReview,
          source_refs: [{
            adapter: "hermes-webui",
            source_id: `pska-mini-memory-page:${Date.now()}`,
            title: "Hermes WebUI PSKA Memory page",
            metadata: { origin: "hermes-webui.pska-mini-extension" }
          }],
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
    container.innerHTML = `
      <div class="pska-mini-page-pills">
        <span class="pska-mini-pill ${dashboard.health?.ok ? "is-ok" : "is-bad"}"><b>API</b> ${dashboard.health?.ok ? "ready" : "missing"}</span>
        <span class="pska-mini-pill ${providers.memory ? "is-ok" : "is-warn"}"><b>Memory</b> ${escapeHtml(providers.memory || "unknown")}</span>
        <span class="pska-mini-pill ${kb.usable ? "is-ok" : "is-warn"}"><b>KB</b> ${escapeHtml(kb.usable ? `${kb.ready_dataset_count || 0}/${kb.dataset_count || 0}` : "not ready")}</span>
        <span class="pska-mini-pill is-${escapeAttr(embeddingTone(embedding))}" title="${escapeAttr(embeddingTitle(embedding))}"><b>Embedding</b> ${escapeHtml(embeddingStatusLabel(embedding))}</span>
        <span class="pska-mini-pill is-${escapeAttr(gbrainTone(gbrain))}"><b>GBrain</b> ${escapeHtml(gbrainStatusLabel(gbrain))}</span>
        ${memoryPage.loadedAt ? `<span class="pska-mini-pill"><b>Loaded</b> ${escapeHtml(memoryPage.loadedAt)}</span>` : ""}
      </div>
      ${memoryPage.message ? `<div class="pska-mini-page-note">${escapeHtml(memoryPage.message)}</div>` : ""}
      ${memoryPage.error ? `<div class="pska-mini-warning">${escapeHtml(memoryPage.error)}</div>` : ""}
    `;
    const statusSelect = document.getElementById("pskaMiniReviewStatus");
    if (statusSelect) statusSelect.value = memoryPage.reviewStatus;
    const queryInput = document.getElementById("pskaMiniMemoryQuery");
    if (queryInput && document.activeElement !== queryInput) queryInput.value = memoryPage.query || "";
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
      diagnostics: pskaMiniFetchJson("/api/runtime/diagnostics", { timeoutMs: 5000 })
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
    const statusItems = [
      ["API", apiOk ? "ready" : "missing", apiOk ? "ok" : "bad", ""],
      ["KB", kbOk ? `${kb.ready_dataset_count || 0}/${kb.dataset_count || 0}` : "not ready", kbOk ? "ok" : "warn", ""],
      ["Memory", memoryOk ? providers.memory : "down", memoryOk ? "ok" : "bad", ""],
      ["Embedding", embeddingStatusLabel(embedding), embeddingTone(embedding), embeddingTitle(embedding)],
      ["GBrain", gbrainStatusLabel(gbrain), gbrainTone(gbrain), ""]
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
      "If Graphiti is unavailable, keep RAGFlow evidence and SQLite memory/review paths working and report the degraded memory backend briefly.",
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
    const evidence = Array.isArray(recall.evidence_blocks) ? recall.evidence_blocks : [];
    const sources = Array.isArray(recall.source_recall) ? recall.source_recall : [];
    const memories = Array.isArray(memory.relevant_memories) ? memory.relevant_memories : [];
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

  function shortId(value) {
    return String(value || "").slice(0, 8);
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

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
