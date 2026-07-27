(() => {
  const EXT_ID = "pska-mini";
  const STORAGE_KEY = "pska-mini.hermes-webui.scope.v1";

  if (window.__pskaMiniExtensionLoaded) return;
  window.__pskaMiniExtensionLoaded = true;

  const state = loadState();

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
      mode: String(data.mode || "project"),
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
    registerChatStartHook();
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
        <div class="pska-mini-row">
          <strong>PSKA-mini</strong>
          <label><input id="pskaMiniEnabled" type="checkbox"> enabled</label>
        </div>
        <label>Mode
          <select id="pskaMiniMode">
            <option value="project">project</option>
            <option value="auto">auto</option>
            <option value="evidence-only">evidence-only</option>
            <option value="memory-only">memory-only</option>
          </select>
        </label>
        <label>Dataset IDs
          <input id="pskaMiniDatasetIds" type="text" placeholder="dataset-a, dataset-b">
        </label>
        <label>Document IDs
          <input id="pskaMiniDocumentIds" type="text" placeholder="optional">
        </label>
        <label>Max context tokens
          <input id="pskaMiniMaxTokens" type="number" min="500" max="12000" step="500">
        </label>
        <div class="pska-mini-actions">
          <button id="pskaMiniPreview" type="button">Preview</button>
          <button id="pskaMiniClose" type="button">Close</button>
        </div>
        <div class="pska-mini-preview" id="pskaMiniPreviewBox" hidden></div>
      </div>
    `;
    anchor.parentElement.insertBefore(wrap, anchor.nextSibling);

    wrap.querySelector("#pskaMiniChip").addEventListener("click", toggleMenu);
    wrap.querySelector("#pskaMiniClose").addEventListener("click", closeMenu);
    wrap.querySelector("#pskaMiniPreview").addEventListener("click", previewTurnContext);
    wrap.querySelector("#pskaMiniEnabled").addEventListener("change", syncFromControls);
    wrap.querySelector("#pskaMiniMode").addEventListener("change", syncFromControls);
    wrap.querySelector("#pskaMiniDatasetIds").addEventListener("input", syncFromControls);
    wrap.querySelector("#pskaMiniDocumentIds").addEventListener("input", syncFromControls);
    wrap.querySelector("#pskaMiniMaxTokens").addEventListener("input", syncFromControls);
    document.addEventListener("click", (event) => {
      if (!wrap.contains(event.target)) closeMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMenu();
    });
    renderControls();
  }

  function registerChatStartHook() {
    const hooks = window.HermesChatStartHooks;
    if (!hooks || typeof hooks.register !== "function") return;
    hooks.register({
      id: EXT_ID,
      beforeSend() {
        if (!state.enabled) return true;
        if (state.mode !== "auto" && state.mode !== "memory-only" && !state.datasetIds.length) {
          toast("Select a PSKA-mini dataset, switch to auto, or turn PSKA-mini off.", "error");
          openMenu();
          return false;
        }
        return true;
      },
      extendBody(ctx) {
        if (!state.enabled) return {};
        return {
          context_provider: {
            id: EXT_ID,
            mode: state.mode,
            scope: {
              workspace: "hermes-webui",
              dataset_ids: state.datasetIds,
              document_ids: state.documentIds
            },
            budget: {
              max_tokens: state.maxTokens
            },
            preview_text: String(ctx && ctx.text || "").slice(0, 500)
          }
        };
      }
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
    if (label) label.textContent = state.enabled ? `PSKA ${state.mode}` : "PSKA off";
    if (enabled) enabled.checked = state.enabled;
    if (mode) mode.value = state.mode;
    if (datasetIds) datasetIds.value = state.datasetIds.join(", ");
    if (documentIds) documentIds.value = state.documentIds.join(", ");
    if (maxTokens) maxTokens.value = String(state.maxTokens);
  }

  function syncFromControls() {
    state.enabled = Boolean(document.getElementById("pskaMiniEnabled")?.checked);
    state.mode = String(document.getElementById("pskaMiniMode")?.value || "project");
    state.datasetIds = normalizeList(document.getElementById("pskaMiniDatasetIds")?.value || "");
    state.documentIds = normalizeList(document.getElementById("pskaMiniDocumentIds")?.value || "");
    state.maxTokens = boundedInt(document.getElementById("pskaMiniMaxTokens")?.value, 3000, 500, 12000);
    saveState();
    renderControls();
  }

  async function previewTurnContext() {
    syncFromControls();
    const box = document.getElementById("pskaMiniPreviewBox");
    if (!box) return;
    const message = String(document.getElementById("msg")?.value || "").trim() || "PSKA-mini preview";
    box.hidden = false;
    box.textContent = "Loading turn context...";
    try {
      const response = await fetch("/api/pska/turn-context", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        credentials: "same-origin",
        body: JSON.stringify({
          caller: "hermes-webui-extension",
          user_message: message,
          mode: state.mode,
          scope: {
            dataset_ids: state.datasetIds,
            document_ids: state.documentIds
          },
          budget: {
            max_evidence_blocks: 3,
            max_memory_notes: 3,
            max_tokens: state.maxTokens
          },
          requirements: {
            need_citations: true
          }
        })
      });
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(errorMessage(data, response.statusText));
      const context = data.turn_context || {};
      box.textContent = [
        context.summary || "No summary.",
        `evidence: ${(context.evidence_blocks || []).length}`,
        `memory: ${(context.memory_notes || []).length}`,
        `citations: ${(context.citations || []).length}`
      ].join("\n");
    } catch (error) {
      box.textContent = `PSKA-mini unavailable: ${error.message || error}`;
    }
  }

  function toggleMenu(event) {
    event?.stopPropagation();
    const menu = document.getElementById("pskaMiniMenu");
    if (!menu) return;
    if (menu.hidden) openMenu();
    else closeMenu();
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

  function toast(message, type) {
    if (typeof window.showToast === "function") window.showToast(message, 3000, type);
  }

  function errorMessage(data, fallback) {
    if (data && typeof data.error === "string") return data.error;
    if (data && data.error && typeof data.error.message === "string") return data.error.message;
    if (data && typeof data.message === "string") return data.message;
    return fallback || "request failed";
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
