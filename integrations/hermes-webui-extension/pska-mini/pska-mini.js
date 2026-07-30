(() => {
  const EXT_ID = "pska-mini";
  const PSKA_API_BASE = sidecarProxyBase(EXT_ID);
  const STORAGE_KEY = "pska-mini.hermes-webui.scope.v1";
  const SKILL_NAME = "knowledge-retrieval";
  const SKILL_CACHE_TTL_MS = 5 * 60 * 1000;
  const REVIEW_BOARD_SLUG = "pska-review";
  const DIGEST_TASK_NAME = "PSKA Digest Runner";
  const DIGEST_TASK_MARKER = "PSKA-Mini Digest Runner";

  if (window.__pskaMiniExtensionLoaded) return;
  window.__pskaMiniExtensionLoaded = true;

  const state = loadState();
  let skillCache = null;
  let sendBridgeInstalling = false;
  let sendBridgeInjecting = false;
  let apiBridgeInstalling = false;
  let pendingChatStartInjection = null;
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

        <details class="pska-mini-advanced">
          <summary>Advanced scope</summary>
          <label>Dataset IDs
            <textarea id="pskaMiniDatasetIds" rows="2" placeholder="optional manual fallback"></textarea>
          </label>
          <label>Document IDs
            <textarea id="pskaMiniDocumentIds" rows="2" placeholder="optional"></textarea>
          </label>
        </details>

        <div class="pska-mini-actions">
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
    wrap.querySelector("#pskaMiniProbe").addEventListener("click", runRetrievalProbe);
    wrap.querySelector("#pskaMiniPreview").addEventListener("click", previewTurnContext);
    wrap.querySelector("#pskaMiniApplySuggestedScope").addEventListener("click", applySuggestedScope);
    wrap.querySelector("#pskaMiniSyncReviews").addEventListener("click", syncReviewBoard);
    wrap.querySelector("#pskaMiniCreateDigestTask").addEventListener("click", createDigestTask);
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

  async function refreshDashboard() {
    dashboard = { ...dashboard, loading: true, errors: {} };
    renderDashboard();
    const results = await settleObject({
      health: pskaMiniFetchJson("/api/health"),
      workspace: pskaMiniFetchJson("/api/workspace/status"),
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
    const workspace = dashboard.workspace || {};
    const kb = workspace.kb || {};
    const providers = workspace.providers || dashboard.health?.providers || {};
    const apiOk = Boolean(dashboard.health?.ok);
    const kbOk = Boolean(kb.usable);
    const memoryOk = Boolean(providers.memory) && !dashboard.diagnosticsError;
    const statusItems = [
      ["API", apiOk ? "ready" : "missing", apiOk ? "ok" : "bad"],
      ["KB", kbOk ? `${kb.ready_dataset_count || 0}/${kb.dataset_count || 0}` : "not ready", kbOk ? "ok" : "warn"],
      ["Memory", memoryOk ? providers.memory : "down", memoryOk ? "ok" : "bad"]
    ];
    container.innerHTML = `
      <div class="pska-mini-status-pills">
        ${statusItems.map(([label, value, tone]) => `
          <span class="pska-mini-pill is-${escapeAttr(tone)}">
            <b>${escapeHtml(label)}</b> ${escapeHtml(value)}
          </span>
        `).join("")}
      </div>
      ${dashboard.diagnosticsError ? `<div class="pska-mini-warning">Graphiti diagnostics: ${escapeHtml(dashboard.diagnosticsError)}</div>` : ""}
      ${Object.keys(dashboard.errors).length ? `
        <div class="pska-mini-warning">${Object.entries(dashboard.errors).map(([key, value]) => `${escapeHtml(key)}: ${escapeHtml(value)}`).join("<br>")}</div>
      ` : ""}
      ${dashboard.loadedAt ? `<div class="pska-mini-muted">Last refresh: ${escapeHtml(dashboard.loadedAt)}</div>` : ""}
    `;
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
    const maxTokens = document.getElementById("pskaMiniMaxTokens");
    if (chip) chip.classList.toggle("is-active", state.enabled);
    if (label) {
      const selected = state.datasetIds.length ? ` · ${state.datasetIds.length} KB` : "";
      label.textContent = state.enabled ? `PSKA ${state.mode}${selected}` : `PSKA off${selected}`;
    }
    if (enabled) enabled.checked = state.enabled;
    if (mode) mode.value = state.mode;
    if (datasetIds) datasetIds.value = state.datasetIds.join("\n");
    if (documentIds) documentIds.value = state.documentIds.join("\n");
    if (maxTokens) maxTokens.value = String(state.maxTokens);
    renderBridgeStatus();
  }

  function syncFromControls() {
    state.enabled = Boolean(document.getElementById("pskaMiniEnabled")?.checked);
    state.mode = String(document.getElementById("pskaMiniMode")?.value || "auto");
    state.datasetIds = normalizeList(document.getElementById("pskaMiniDatasetIds")?.value || "");
    state.documentIds = normalizeList(document.getElementById("pskaMiniDocumentIds")?.value || "");
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
    const scope = state.datasetIds.length
      ? `${state.datasetIds.length} selected knowledge base${state.datasetIds.length === 1 ? "" : "s"}`
      : "auto dataset discovery";
    container.innerHTML = state.enabled
      ? `Enabled sends will load <code>${escapeHtml(SKILL_NAME)}</code> with ${escapeHtml(scope)}.`
      : `Turn PSKA on to force <code>${escapeHtml(SKILL_NAME)}</code> for the next send.`;
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
      "Operational rule: when PSKA is enabled from the chip, use PSKA-Essential MCP retrieval tools for knowledge-base evidence before answering. Treat Graphiti memory as optional; if memory diagnostics fail, keep retrieval working and say memory is unavailable only when it matters."
    ];
    return lines.join("\n");
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
      setEnabled(value) {
        state.enabled = Boolean(value);
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
    const message = String(document.getElementById("msg")?.value || "").trim() || "PSKA-mini preview";
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
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    addCsrfHeader(target, options, headers);
    const fetchOptions = { ...options };
    delete fetchOptions.timeoutMs;
    try {
      const response = await fetch(target, {
        ...fetchOptions,
        credentials: "same-origin",
        headers,
        signal: controller.signal
      });
      const text = await response.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        throw new Error(text || `${response.status} ${response.statusText}`);
      }
      if (!response.ok || data.ok === false) throw new Error(errorMessage(data, response.statusText));
      return data;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function pskaMiniFetch(path, options = {}) {
    const target = `${PSKA_API_BASE}${String(path || "").startsWith("/") ? "" : "/"}${path || ""}`;
    const headers = { ...(options.headers || {}) };
    const timeoutMs = Number(options.timeoutMs || 15000);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    addCsrfHeader(target, options, headers);
    const fetchOptions = { ...options };
    delete fetchOptions.timeoutMs;
    return fetch(target, {
      ...fetchOptions,
      credentials: "same-origin",
      headers,
      signal: controller.signal
    }).finally(() => window.clearTimeout(timer));
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
