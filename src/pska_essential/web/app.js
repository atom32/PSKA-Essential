const state = {
  datasets: [],
  reviews: [],
  reviewView: [],
  pendingReviews: null,
  health: null,
  lastRunId: null,
  reader: null,
  workflows: [],
  resumableAsks: [],
  auditEvents: [],
  currentBrief: null,
  currentAskResult: null,
  diagnostics: null,
  retrievalProbe: null,
  focusReviewId: null,
  memoryApplyByReview: {},
  activeDocumentDatasetId: null,
  activeDocuments: [],
  readinessByDataset: {},
  ingestionPoll: null,
  askDocumentsByDataset: {},
  auditAction: "",
  reviewStatus: "",
};

const titles = {
  home: "Home",
  kb: "Knowledge Bases",
  ask: "Ask",
  reader: "Reader",
  writing: "Writing",
  review: "Review",
  activity: "Activity",
  settings: "Settings",
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
    await api("/api/kb/datasets", {
      method: "POST",
      body: {
        name: form.get("name"),
        description: form.get("description"),
        chunk_method: form.get("chunk_method"),
      },
    });
    event.currentTarget.reset();
    showToast("Knowledge base created.");
    await loadDatasets();
    await loadAuditEvents("kb.dataset.create");
  });

  document.getElementById("upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = new FormData();
    for (const file of form.getAll("file")) {
      if (file && file.name) payload.append("file", file);
    }
    payload.append("dataset_id", form.get("dataset_id") || "");
    payload.append("dataset_name", form.get("dataset_name") || "");
    payload.append("parse", form.get("parse") ? "true" : "false");
    payload.append("wait", form.get("wait") ? "true" : "false");
    const result = await api("/api/kb/ingest", { method: "POST", formData: payload });
    event.currentTarget.reset();
    showToast("Upload accepted.");
    renderIngestResult(result.ingest);
    await loadDatasets();
    await loadAuditEvents("kb.ingest");
    const datasetId = ingestDatasetId(result.ingest);
    if (datasetId) {
      const documents = await loadDocuments(datasetId, { silent: true });
      const summary = summarizeDocuments(documents);
      if (result.ingest && result.ingest.parse && result.ingest.parse.parse_started && summary.status === "processing") {
        startIngestionPolling(datasetId);
      }
    }
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
  askForm.elements.dataset_ids.addEventListener("input", renderAskScope);
  askForm.elements.document_ids.addEventListener("input", renderAskScope);
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
      }
    : null;
  renderAskResult(result);
  renderWriting();
  await loadReviews();
  await loadPendingReviews();
  await loadWorkflows();
  await loadResumableAsks();
  await loadAuditEvents(auditActionForAskResult(result));
  renderHome();
  if (options.toast) {
    showToast(options.toast);
  }
}

function bindRefresh() {
  document.getElementById("refresh-all").addEventListener("click", refreshAll);
  document.getElementById("reload-datasets").addEventListener("click", loadDatasets);
  document.getElementById("parse-documents").addEventListener("click", parseActiveDocuments);
  document.getElementById("ask-add-dataset").addEventListener("click", () => addAskDataset());
  document.getElementById("ask-load-documents").addEventListener("click", loadAskDocuments);
  document.getElementById("reload-reviews").addEventListener("click", loadReviews);
  document.getElementById("review-status-filter").addEventListener("change", (event) => {
    state.reviewStatus = event.currentTarget.value || "";
    loadReviews();
  });
  document.getElementById("reload-workflows").addEventListener("click", loadWorkflows);
  document.getElementById("reload-audit").addEventListener("click", () => loadAuditEvents());
  document.getElementById("run-retrieval-probe").addEventListener("click", runRetrievalProbe);
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
    loadDiagnostics(),
    loadDatasets(),
    loadReviews(),
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
    status.textContent = "API online";
    status.className = "status-pill ok";
    renderSettings();
  } catch (error) {
    const status = document.getElementById("api-status");
    status.textContent = "API error";
    status.className = "status-pill error";
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

async function loadDatasets() {
  try {
    const payload = await api("/api/kb/datasets");
    state.datasets = payload.datasets || [];
    renderDatasets();
    renderAskDatasetPicker();
    renderProbeDatasetPicker();
    renderAskScope();
    renderHome();
  } catch (error) {
    renderList(document.getElementById("datasets-list"), [], "Datasets unavailable.");
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
    renderList(document.getElementById("reviews-list"), [], "Reviews unavailable.");
    showToast(error.message);
  }
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
    renderList(document.getElementById("workflow-list"), [], "Runs unavailable.");
    showToast(error.message);
  }
}

async function loadResumableAsks() {
  try {
    const payload = await api("/api/workflows/resumable-asks?limit=20");
    state.resumableAsks = payload.resumable_asks || [];
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
    renderList(document.getElementById("audit-list"), [], "Audit events unavailable.");
    showToast(error.message);
  }
}

async function loadDocuments(datasetId, options = {}) {
  const normalizedId = String(datasetId || "").trim();
  if (!normalizedId) {
    showToast("Dataset ID is required.");
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
    const documents = documentsResult.value.documents || [];
    state.activeDocuments = documents;
    renderDocuments(documents);
    if (readinessResult.status === "fulfilled") {
      state.readinessByDataset[normalizedId] = readinessResult.value.readiness;
    }
    renderIngestionStatus(normalizedId, documents, state.readinessByDataset[normalizedId]);
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
  document.getElementById("metric-run").textContent = state.lastRunId ? shortId(state.lastRunId) : "None";
  renderList(document.getElementById("home-datasets"), state.datasets.slice(0, 4), "No datasets loaded.", datasetCard);
  renderList(
    document.getElementById("home-reviews"),
    pendingReviews.slice(0, 4),
    "No pending reviews.",
    reviewCard,
  );
  renderList(
    document.getElementById("home-resumable-asks"),
    state.resumableAsks.slice(0, 4),
    "No resumable asks.",
    resumableAskCard,
  );
}

function renderSettings() {
  const settings = document.getElementById("runtime-settings");
  settings.replaceChildren();
  const providers = (state.health && state.health.providers) || {};
  const workspace = (state.health && state.health.workspace) || {};
  const governance = (state.health && state.health.governance) || {};
  const diagnostics = state.diagnostics || {};
  [
    ["Product API", state.health ? state.health.product_api : ""],
    ["Runtime Status", diagnostics.status || "not checked"],
    ["Workspace", workspace.workspace_id || "default"],
    ["Tenant", workspace.tenant_id || "not configured"],
    ["Retrieval", providers.retrieval || "not configured"],
    ["Knowledge Base", providers.kb || "not configured"],
    ["Memory", providers.memory || "not configured"],
    ["Development Fake", providers.dev_fake ? "enabled" : "disabled"],
    ["Durable Memory Policy", governance.durable_memory || "manual_review"],
  ].forEach(([key, value]) => {
    settings.append(el("dt", {}, key), el("dd", {}, value));
  });
}

function renderDiagnostics() {
  const container = document.getElementById("runtime-diagnostics");
  const status = document.getElementById("diagnostics-status");
  if (!container || !status) return;
  const diagnostics = state.diagnostics || {};
  const checks = diagnostics.checks || [];
  status.textContent = diagnostics.status || "not checked";
  status.className = `tag ${statusClass(diagnostics.status || "pending")}`;
  renderList(container, checks, "No diagnostics loaded.", diagnosticCard);
}

function renderProbeDatasetPicker() {
  const picker = document.getElementById("probe-dataset-picker");
  if (!picker) return;
  const current = picker.value;
  picker.replaceChildren();
  if (!state.datasets.length) {
    picker.append(el("option", { value: "" }, "No datasets"));
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

async function runRetrievalProbe() {
  const picker = document.getElementById("probe-dataset-picker");
  const question = document.getElementById("probe-question");
  const datasetId = String((picker && picker.value) || "").trim();
  if (!datasetId) {
    showToast("Select a dataset.");
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
  showToast("Retrieval probe recorded.");
}

function renderRetrievalProbe() {
  const container = document.getElementById("retrieval-probe-result");
  if (!container) return;
  container.replaceChildren();
  if (!state.retrievalProbe) {
    container.classList.add("empty-list");
    container.textContent = "No retrieval probe run.";
    return;
  }
  container.classList.remove("empty-list");
  container.append(retrievalProbeCard(state.retrievalProbe));
}

function renderDatasets() {
  renderList(document.getElementById("datasets-list"), state.datasets, "No datasets loaded.", datasetCard);
}

function renderDocuments(documents) {
  renderList(document.getElementById("documents-list"), documents, "No documents loaded.", documentCard);
  syncParseButton(documents);
}

function renderReviews() {
  renderList(document.getElementById("reviews-list"), state.reviewView, "No reviews loaded.", reviewCard);
}

function setReviewStatusFilter(status) {
  state.reviewStatus = status || "";
  const filter = document.getElementById("review-status-filter");
  if (filter) filter.value = state.reviewStatus;
}

function renderWorkflowList() {
  renderList(document.getElementById("workflow-list"), state.workflows, "No runs loaded.", workflowCard);
}

function renderAuditEvents() {
  renderList(document.getElementById("audit-list"), state.auditEvents, "No audit events loaded.", auditEventCard);
}

function auditActionForAskResult(result) {
  if (result.status === "not_ready") return "kb.readiness.blocked";
  if (result.status === "insufficient_context") return "agentic_loop.insufficient_context";
  if (result.status === "ready") return "agentic_loop.complete";
  return "";
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
    picker.append(el("option", { value: "" }, "No datasets"));
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
      summary.textContent = "No scope selected.";
    } else {
      datasetIds.forEach((datasetId) => {
        summary.append(el("span", { className: "tag ready" }, `dataset ${shortId(datasetId)}`));
      });
      documentIds.forEach((documentId) => {
        summary.append(el("span", { className: "tag" }, `doc ${shortId(documentId)}`));
      });
    }
  }
  renderAskDocumentPicker();
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
    container.textContent = datasetIds.length ? "No documents loaded for selected scope." : "Select a dataset.";
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

function renderIngestResult(result) {
  const documents = result.documents || [];
  const datasetId = ingestDatasetId(result);
  state.activeDocumentDatasetId = datasetId || state.activeDocumentDatasetId;
  state.activeDocuments = documents;
  renderDocuments(documents);
  if (datasetId) {
    renderIngestionStatus(datasetId, documents, null);
    const statusForm = document.querySelector('#document-status-form input[name="dataset_id"]');
    if (statusForm) statusForm.value = datasetId;
  }
}

async function parseActiveDocuments() {
  const field = document.querySelector('#document-status-form input[name="dataset_id"]');
  const requestedDatasetId = field ? field.value.trim() : "";
  const datasetId = requestedDatasetId || state.activeDocumentDatasetId || "";
  if (!datasetId) {
    showToast("Load a dataset before parsing documents.");
    return;
  }
  let documents = state.activeDocumentDatasetId === datasetId ? state.activeDocuments || [] : [];
  if (!documents.length) {
    documents = await loadDocuments(datasetId);
  }
  const documentIds = documents
    .filter((document) => documentState(document).label !== "ready")
    .map((document) => document.document_id)
    .filter(Boolean);
  if (!documentIds.length) {
    showToast("No unready documents to parse.");
    return;
  }
  await api(`/api/kb/datasets/${encodeURIComponent(datasetId)}/parse`, {
    method: "POST",
    body: {
      document_ids: documentIds,
      wait: false,
    },
  });
  showToast("Parse started.");
  setIngestionStatus(`Tracking ${shortId(datasetId)} parsing...`, "pending");
  startIngestionPolling(datasetId);
  await loadDocuments(datasetId, { silent: true });
  await loadAuditEvents("kb.parse");
}

function addAskDataset(datasetId = "") {
  const picker = document.getElementById("ask-dataset-picker");
  const selected = String(datasetId || (picker ? picker.value : "") || "").trim();
  if (!selected) {
    showToast("Select a dataset.");
    return;
  }
  const datasetIds = askDatasetIds();
  if (!datasetIds.includes(selected)) {
    datasetIds.push(selected);
  }
  setAskDatasetIds(datasetIds);
  renderAskScope();
}

async function loadAskDocuments() {
  const picker = document.getElementById("ask-dataset-picker");
  const datasetId = String((picker && picker.value) || askDatasetIds()[0] || "").trim();
  if (!datasetId) {
    showToast("Select a dataset.");
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
  setIngestionStatus(`Tracking ${shortId(datasetId)} ingestion...`, "pending");
  state.ingestionPoll.timer = window.setInterval(async () => {
    if (!state.ingestionPoll || state.ingestionPoll.datasetId !== datasetId) return;
    state.ingestionPoll.attempts += 1;
    try {
      const documents = await loadDocuments(datasetId, { silent: true });
      await loadDatasets();
      const summary = summarizeDocuments(documents);
      if (["ready", "failed", "empty"].includes(summary.status)) {
        stopIngestionPolling();
      } else if (state.ingestionPoll && state.ingestionPoll.attempts >= state.ingestionPoll.maxAttempts) {
        stopIngestionPolling();
        setIngestionStatus(`Tracking paused for ${shortId(datasetId)}.`, "pending");
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
  const readinessStatus = readiness && readiness.status ? readiness.status : summary.status;
  const label = readiness && readiness.message ? readiness.message : `${summary.ready}/${summary.total} documents ready.`;
  setIngestionStatus(`${shortId(datasetId)}: ${label}`, readinessStatus);
}

function setIngestionStatus(message, status) {
  const node = document.getElementById("ingestion-status");
  if (!node) return;
  node.className = `job-status ${statusClass(status)}`;
  node.textContent = message;
}

function syncParseButton(documents = state.activeDocuments || []) {
  const button = document.getElementById("parse-documents");
  if (!button) return;
  const unreadyCount = documents.filter((document) => documentState(document).label !== "ready").length;
  button.disabled = !state.activeDocumentDatasetId || unreadyCount === 0;
  button.textContent = unreadyCount ? `Parse Listed (${unreadyCount})` : "Parse Listed";
}

function ingestDatasetId(result) {
  if (!result) return "";
  if (result.dataset && result.dataset.dataset_id) return result.dataset.dataset_id;
  const documents = result.documents || [];
  return documents.length ? documents[0].dataset_id || "" : "";
}

function renderAskResult(result) {
  const container = document.getElementById("ask-result");
  container.replaceChildren();
  if (result.status === "insufficient_context") {
    container.append(
      el("div", { className: "item-card" }, [
        el("h3", {}, "Insufficient Context"),
        el("p", {}, result.message || "No context was retrieved from the selected scope."),
      ]),
    );
    container.append(loopPanel(result));
    if ((result.context_packets || []).length) {
      container.append(
        el("div", { className: "panel" }, [
          el("h2", {}, "Retrieved Context"),
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
    const readiness = result.readiness || {};
    container.append(
      el("div", { className: "item-card" }, [
        el("h3", {}, "Knowledge Scope Not Ready"),
        el("p", {}, result.message || readiness.message || "Selected knowledge scope is not ready for retrieval."),
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
        el("h2", {}, "Sourced Brief"),
        el("span", { className: "tag ready" }, result.review ? "Review created" : "Transient"),
      ]),
      el("pre", {}, result.brief || ""),
    ]),
  );
  container.append(askResultActions(result));
  container.append(loopPanel(result));
  container.append(
    el("div", { className: "panel" }, [
      el("h2", {}, "Context"),
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
      el("button", { className: "secondary-button", onclick: () => openWritingRun(result.run.run_id) }, "Open Writing"),
    );
    if (result.status === "ready" && !reviewId) {
      actions.append(
        el(
          "button",
          { className: "primary-button", onclick: () => createMemoryReviewFromRun(result.run.run_id) },
          "Create Memory Review",
        ),
      );
    }
    if (result.status === "not_ready") {
      const canResume = Boolean(result.readiness && result.readiness.ready);
      actions.append(
        el(
          "button",
          {
            className: "primary-button",
            onclick: () => resumeAskRun(result.run.run_id),
            ...(canResume ? {} : { disabled: true }),
          },
          "Resume Ask",
        ),
      );
    }
  }
  if (reviewId) {
    actions.append(
      el("button", { className: "secondary-button", onclick: () => openReview(reviewId) }, "Open Review"),
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
      el("button", { className: "primary-button", onclick: () => applyMemory(reviewId) }, "Apply Memory"),
    );
  }
  if (memoryApply) {
    actions.append(el("span", { className: "tag ready" }, memoryApplyLabel(memoryApply)));
  }
  return el("div", { className: "panel compact-panel" }, [
    el("h2", {}, "Next Actions"),
    actions.children.length ? actions : el("p", {}, "No follow-up action is available for this result."),
  ]);
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
  return el("div", { className: "panel" }, [
    el("div", { className: "panel-header" }, [
      el("h2", {}, "Readiness"),
      el("span", { className: `tag ${statusClass(readiness.status)}` }, readiness.status || "unknown"),
    ]),
    blocking.length
      ? el("div", { className: "source-list" }, blocking.map((item) => el("p", {}, item)))
      : el("p", {}, readiness.message || "Selected knowledge scope is ready for retrieval."),
    el("div", { className: "source-list" }, datasets.map((dataset) => readinessDatasetCard(dataset))),
  ]);
}

function readinessDatasetCard(dataset) {
  const documents = dataset.documents || [];
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
    container.textContent = "Run Ask to create a sourced brief.";
    return;
  }
  const run = state.currentBrief.run || {};
  const artifact = state.currentBrief.artifact || {};
  const latestProposal = state.currentBrief.proposal || artifact.latest_proposal || null;
  const sourceManifest = artifact.source_manifest || [];
  const contextPackets = artifact.context_packets || run.context_packets || [];
  const memoryFacts = artifact.memory_facts || state.currentBrief.memory_facts || [];
  const review = state.currentBrief.review || {};
  const memoryApply = state.currentBrief.memory_apply || (review.review_id && state.memoryApplyByReview[review.review_id]);
  container.append(
    el("article", { className: "item-card" }, [
      el("header", {}, [
        el("div", {}, [
          el("h3", {}, run.intent || "Sourced brief"),
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
          : el("p", { className: "empty-list" }, "Run loaded. Use Markdown or JSON to create an export."),
    ]),
  );
  const loop = run.metadata && run.metadata.agentic_loop;
  if (loop && loop.steps) {
    container.append(loopPanel({ loop }));
  }
  if (!state.currentBrief.brief && memoryFacts.length) {
    container.append(
      el("div", { className: "panel" }, [
        el("h2", {}, "Durable Memory"),
        el("div", { className: "source-list" }, memoryFacts.map((fact) => memoryFactCard(fact))),
      ]),
    );
  }
  if (!state.currentBrief.brief && sourceManifest.length) {
    container.append(
      el("div", { className: "panel" }, [
        el("h2", {}, "Source Manifest"),
        el("div", { className: "source-list" }, sourceManifest.map((source) => sourceManifestCard(source))),
      ]),
    );
  }
  if (!state.currentBrief.brief && contextPackets.length) {
    container.append(
      el("div", { className: "panel" }, [
        el("h2", {}, "Context"),
        el("div", { className: "source-list" }, contextPackets.map((packet) => contextCard(packet))),
      ]),
    );
  }
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
        el("button", { className: "secondary-button", onclick: () => setAskDataset(dataset.dataset_id) }, "Use"),
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
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, document.name || document.document_id), el("p", {}, document.progress_msg || "")]),
      el("div", { className: "card-actions" }, [
        el("span", { className: `tag ${stateName.className}` }, stateName.label),
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
      el("span", { className: "tag" }, shortId(document.document_id || "")),
    ]),
  ]);
}

function contextCard(packet) {
  const sourceRef = packet.source_ref || {};
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, packet.title || sourceRef.title || packet.context_id), el("p", {}, packet.text || "")]),
      el("button", { className: "secondary-button", onclick: () => readSource(sourceRef) }, "Source"),
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
  const reason = el("input", { placeholder: "Reason", value: "" });
  const updatedText = el("textarea", { placeholder: "Updated memory text", value: fact.text || "" });
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, fact.fact_id || "Memory"), el("p", {}, fact.text || "")]),
      el("span", { className: "tag" }, `sources ${sourceRefs.length}`),
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
          ...(sourceRefs.length ? {} : { disabled: true }),
        },
        "Create Update Review",
      ),
      el(
        "button",
        {
          className: "secondary-button",
          onclick: () => createMemoryDeleteReview(fact, reason.value),
          ...(sourceRefs.length ? {} : { disabled: true }),
        },
        "Create Delete Review",
      ),
    ]),
  ]);
}

function sourceManifestCard(source) {
  const sourceRef = source.source_ref || {};
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, source.title || source.context_id || "Source"), el("p", {}, source.source_id || "")]),
      sourceRef.adapter ? el("button", { className: "secondary-button", onclick: () => readSource(sourceRef) }, "Source") : null,
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

function reviewCard(review) {
  const proposal = review.proposal || {};
  const sourceRefs = review.source_refs || proposal.source_refs || [];
  const revision = review.revision || {};
  const actions = el("div", { className: "review-actions" }, []);
  const reason = el("input", { placeholder: "Reason", value: "" });
  const memoryApply = review.memory_apply || state.memoryApplyByReview[review.review_id];
  const locked = Boolean(memoryApply);
  if (locked) {
    actions.append(el("span", { className: "tag ready" }, memoryApplyLabel(memoryApply)));
    actions.append(el("span", { className: "tag" }, "Locked"));
  } else {
    actions.append(
      reason,
      el("button", { className: "primary-button", onclick: () => decideReview(review.review_id, "accept", reason.value) }, "Accept"),
      el("button", { className: "secondary-button", onclick: () => decideReview(review.review_id, "edit", reason.value) }, "Edit"),
      el("button", { className: "danger-button", onclick: () => decideReview(review.review_id, "reject", reason.value) }, "Reject"),
    );
    if (review.status === "accepted" && proposal.kind === "memory_patch") {
      actions.append(
        el("button", { className: "primary-button", onclick: () => applyMemory(review.review_id) }, "Apply Memory"),
      );
    }
    if (review.status === "accepted" && proposal.kind === "memory_update") {
      actions.append(
        el("button", { className: "primary-button", onclick: () => applyMemory(review.review_id) }, "Apply Memory Update"),
      );
    }
    if (review.status === "accepted" && proposal.kind === "memory_delete") {
      actions.append(
        el("button", { className: "danger-button", onclick: () => applyMemory(review.review_id) }, "Apply Memory Delete"),
      );
    }
    if (review.status === "needs_edit") {
      actions.append(
        el("button", { className: "primary-button", onclick: () => reviseReview(review.review_id, reason.value) }, "Revise"),
      );
    }
  }
  return el("article", { className: review.review_id === state.focusReviewId ? "item-card highlighted" : "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, proposal.title || review.review_id), el("p", {}, proposal.body || "")]),
      el("span", { className: `tag ${review.status === "accepted" ? "ready" : "pending"}` }, review.status),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, proposal.kind || "proposal"),
      el("span", { className: "tag" }, shortId(review.review_id)),
      el("span", { className: "tag" }, `sources ${review.source_count ?? sourceRefs.length}`),
      revision.previous_review_id ? el("span", { className: "tag" }, `from ${shortId(revision.previous_review_id)}`) : null,
      revision.next_review_id ? el("span", { className: "tag" }, `to ${shortId(revision.next_review_id)}`) : null,
    ]),
    sourceRefs.length
      ? el("div", { className: "review-source-list" }, sourceRefs.map((sourceRef, index) => reviewSourceRow(sourceRef, index)))
      : el("p", { className: "empty-list" }, "No source trace is attached to this review."),
    actions,
  ]);
}

function reviewSourceRow(sourceRef, index) {
  return el("div", { className: "review-source-row" }, [
    el("div", {}, [
      el("strong", {}, sourceRef.title || sourceRef.document_id || sourceRef.source_id || `Source ${index + 1}`),
      el(
        "span",
        {},
        `${sourceRef.adapter || "adapter"} / ${shortId(sourceRef.document_id || sourceRef.source_id || sourceRef.external_id || "")}`,
      ),
    ]),
    el("button", { className: "secondary-button", onclick: () => readSource(sourceRef) }, "Source"),
  ]);
}

function workflowCard(workflow) {
  const blockedByKb = workflow.metadata && workflow.metadata.blocked_reason === "kb_not_ready";
  const resumable = resumableAskFor(workflow.run_id);
  const canResume = !resumable || Boolean(resumable.can_resume);
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
                onclick: () => resumeAskRun(workflow.run_id),
                ...(canResume ? {} : { disabled: true }),
              },
              "Resume Ask",
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
          onclick: () => resumeAskRun(run.run_id),
          ...(record.can_resume ? {} : { disabled: true }),
        },
        "Resume Ask",
      ),
      el("button", { className: "secondary-button", onclick: () => openWorkflowRun(run.run_id) }, "Open"),
    ]),
  ]);
}

function resumableAskFor(runId) {
  return state.resumableAsks.find((record) => record.run && record.run.run_id === runId) || null;
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
  if (event.action === "retrieval.probe") {
    return `Retrieval probe ${metadata.status || "recorded"} with ${metadata.context_count || 0} context packet(s).`;
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
  };
  renderWriting();
  document.querySelector('.nav-item[data-view="writing"]').click();
}

async function resumeAskRun(runId) {
  const result = await api(`/api/workflows/${encodeURIComponent(runId)}/resume-ask`, { method: "POST", body: {} });
  await applyAskResult(result, {
    toast: result.status === "ready" ? "Ask resumed." : "Knowledge scope is still not ready.",
  });
  document.querySelector('.nav-item[data-view="ask"]').click();
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
    throw new Error("Review not found.");
  }
  state.reviewView = [payload.review, ...state.reviewView.filter((review) => review.review_id !== reviewId)];
  renderReviews();
  renderHome();
  document.querySelector('.nav-item[data-view="review"]').click();
  showToast("Review opened.");
}

async function exportCurrent(format) {
  if (!state.currentBrief || !state.currentBrief.run || !state.currentBrief.run.run_id) {
    showToast("No run selected.");
    return;
  }
  const runId = state.currentBrief.run.run_id;
  const payload = await api(`/api/workflows/${encodeURIComponent(runId)}/export?format=${encodeURIComponent(format)}`);
  const content = typeof payload.export === "string" ? payload.export : JSON.stringify(payload.export, null, 2);
  state.currentBrief.brief = content;
  if (payload.export && typeof payload.export === "object") {
    state.currentBrief.artifact = payload.export;
  }
  renderWriting();
  await loadAuditEvents("workflow.export");
  showToast(`${format.toUpperCase()} export loaded.`);
}

async function createMemoryReviewFromRun(runId = "") {
  const selectedRunId = String(
    runId || (state.currentBrief && state.currentBrief.run && state.currentBrief.run.run_id) || "",
  ).trim();
  if (!selectedRunId) {
    showToast("No workflow selected.");
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
  syncReviewRecord(payload.review);
  state.focusReviewId = payload.review && payload.review.review_id;
  syncWorkflowMemoryReview(selectedRunId, payload);
  await loadReviews();
  await loadPendingReviews();
  await loadWorkflows();
  await loadAuditEvents("review.create");
  renderCurrentResultSurfaces();
  showToast("Memory review created.");
}

async function readSource(sourceRef) {
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
  showToast("Graph loaded.");
}

function renderReader() {
  const source = state.reader;
  const sourceBox = document.getElementById("reader-source");
  const metadata = document.getElementById("reader-metadata");
  const status = document.getElementById("reader-status");
  sourceBox.replaceChildren();
  metadata.replaceChildren();
  if (!source) {
    status.textContent = "No source selected";
    status.className = "tag";
    sourceBox.className = "reader-source empty-list";
    sourceBox.textContent = "Select a source from Ask.";
    return;
  }
  if (source.kind === "graph") {
    renderGraphReader(source.graph || {}, sourceBox, metadata, status);
    return;
  }
  status.textContent = "Loaded";
  status.className = "tag ready";
  sourceBox.className = "reader-source";
  sourceBox.append(el("pre", {}, source.text || "Source is empty."));
  const ref = source.source_ref || {};
  [
    ["Adapter", ref.adapter || ""],
    ["Dataset", ref.dataset_id || ""],
    ["Document", ref.document_id || ""],
    ["Chunk", ref.chunk_id || ""],
    ["Source", ref.source_id || ""],
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
    metadata.append(el("dt", {}, "Metadata"), el("dd", {}, "No source coordinates available."));
  }
}

function renderGraphReader(graph, sourceBox, metadata, status) {
  const templates = graph.templates || [];
  status.textContent = "Graph loaded";
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
  syncReviewDecision(payload.decision);
  showToast(`Review ${decision}.`);
  await loadReviews();
  await loadPendingReviews();
  await loadAuditEvents("review.decide");
  renderCurrentResultSurfaces();
}

async function reviseReview(reviewId, intent) {
  const payload = await api(`/api/reviews/${encodeURIComponent(reviewId)}/revision`, {
    method: "POST",
    body: { intent },
  });
  syncReviewRecord(payload.previous_review);
  syncReviewRecord(payload.review);
  state.focusReviewId = payload.review && payload.review.review_id;
  setReviewStatusFilter("");
  state.reviewView = [payload.review, ...state.reviewView.filter((review) => review.review_id !== payload.review.review_id)];
  await loadReviews();
  await loadPendingReviews();
  await loadAuditEvents("review.revise");
  renderCurrentResultSurfaces();
  showToast("Review revision created.");
}

async function applyMemory(reviewId) {
  const payload = await api(`/api/reviews/${encodeURIComponent(reviewId)}/apply-memory`, { method: "POST", body: {} });
  syncMemoryApply(reviewId, payload.applied);
  const action = memoryApplyAction(payload.applied);
  showToast(memoryApplyToast(payload.applied));
  await loadReviews();
  await loadPendingReviews();
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
  await loadPendingReviews();
  await loadAuditEvents("review.create");
  document.querySelector('.nav-item[data-view="review"]').click();
  showToast("Memory update review created.");
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
  await loadPendingReviews();
  await loadAuditEvents("review.create");
  document.querySelector('.nav-item[data-view="review"]').click();
  showToast("Memory delete review created.");
}

function memoryApplyLabel(memoryApply) {
  const action = memoryApplyAction(memoryApply);
  if (action === "memory.delete") return "memory deleted";
  if (action === "memory.update") return "memory updated";
  return "memory applied";
}

function memoryApplyAction(memoryApply) {
  const operation = memoryApply && memoryApply.metadata && memoryApply.metadata.operation;
  if (operation === "delete") return "memory.delete";
  if (operation === "update") return "memory.update";
  return "memory.apply";
}

function memoryApplyToast(memoryApply) {
  const action = memoryApplyAction(memoryApply);
  if (action === "memory.delete") return "Memory deletion applied.";
  if (action === "memory.update") return "Memory update applied.";
  return "Memory applied.";
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
  addAskDataset(datasetId || "");
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
}

function setAskDocumentIds(documentIds) {
  const input = document.querySelector('#ask-form input[name="document_ids"]');
  if (input) input.value = uniqueIds(documentIds).join(", ");
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
    ["FAIL", "FAILED", "CANCEL", "CANCELED", "ERROR"].includes(run) ||
    ["fail", "failed", "cancel", "canceled", "error"].includes(status) ||
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
  if (["failed", "fail", "missing", "blocked", "rejected", "empty", "error"].includes(value)) return "failed";
  return "pending";
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 3600);
}
