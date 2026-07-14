const state = {
  datasets: [],
  reviews: [],
  health: null,
  lastRunId: null,
  reader: null,
  workflows: [],
  currentBrief: null,
  focusReviewId: null,
  activeDocumentDatasetId: null,
  activeDocuments: [],
  readinessByDataset: {},
  ingestionPoll: null,
  askDocumentsByDataset: {},
};

const titles = {
  home: "Home",
  kb: "Knowledge Bases",
  ask: "Ask",
  reader: "Reader",
  writing: "Writing",
  review: "Review",
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
      proposal_kind: form.get("proposal_kind"),
    };
    if (form.get("create_review")) {
      body.create_review = true;
    }
    const result = await api("/api/ask", { method: "POST", body });
    state.lastRunId = result.run && result.run.run_id;
    state.currentBrief = result.run
      ? {
          run: result.run,
          brief: result.brief || "",
          status: result.status,
          proposal: result.proposal,
          review: result.review,
        }
      : null;
    renderAskResult(result);
    renderWriting();
    await loadReviews();
    await loadWorkflows();
    renderHome();
  });

  const askForm = document.getElementById("ask-form");
  askForm.elements.dataset_ids.addEventListener("input", renderAskScope);
  askForm.elements.document_ids.addEventListener("input", renderAskScope);
}

function bindRefresh() {
  document.getElementById("refresh-all").addEventListener("click", refreshAll);
  document.getElementById("reload-datasets").addEventListener("click", loadDatasets);
  document.getElementById("parse-documents").addEventListener("click", parseActiveDocuments);
  document.getElementById("ask-add-dataset").addEventListener("click", () => addAskDataset());
  document.getElementById("ask-load-documents").addEventListener("click", loadAskDocuments);
  document.getElementById("reload-reviews").addEventListener("click", loadReviews);
  document.getElementById("reload-workflows").addEventListener("click", loadWorkflows);
  document.getElementById("export-markdown").addEventListener("click", () => exportCurrent("markdown"));
  document.getElementById("export-json").addEventListener("click", () => exportCurrent("json"));
}

async function refreshAll() {
  await Promise.allSettled([loadHealth(), loadDatasets(), loadReviews(), loadWorkflows()]);
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

async function loadDatasets() {
  try {
    const payload = await api("/api/kb/datasets");
    state.datasets = payload.datasets || [];
    renderDatasets();
    renderAskDatasetPicker();
    renderAskScope();
    renderHome();
  } catch (error) {
    renderList(document.getElementById("datasets-list"), [], "Datasets unavailable.");
    showToast(error.message);
  }
}

async function loadReviews() {
  try {
    const payload = await api("/api/reviews");
    state.reviews = payload.reviews || [];
    renderReviews();
    renderHome();
  } catch (error) {
    renderList(document.getElementById("reviews-list"), [], "Reviews unavailable.");
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
  document.getElementById("metric-datasets").textContent = String(state.datasets.length);
  document.getElementById("metric-reviews").textContent = String(
    state.reviews.filter((item) => item.status === "pending").length,
  );
  document.getElementById("metric-run").textContent = state.lastRunId ? shortId(state.lastRunId) : "None";
  renderList(document.getElementById("home-datasets"), state.datasets.slice(0, 4), "No datasets loaded.", datasetCard);
  renderList(
    document.getElementById("home-reviews"),
    state.reviews.filter((item) => item.status === "pending").slice(0, 4),
    "No pending reviews.",
    reviewCard,
  );
}

function renderSettings() {
  const settings = document.getElementById("runtime-settings");
  settings.replaceChildren();
  const providers = (state.health && state.health.providers) || {};
  const governance = (state.health && state.health.governance) || {};
  [
    ["Product API", state.health ? state.health.product_api : ""],
    ["Retrieval", providers.retrieval || "not configured"],
    ["Knowledge Base", providers.kb || "not configured"],
    ["Memory", providers.memory || "not configured"],
    ["Development Fake", providers.dev_fake ? "enabled" : "disabled"],
    ["Durable Memory Policy", governance.durable_memory || "manual_review"],
  ].forEach(([key, value]) => {
    settings.append(el("dt", {}, key), el("dd", {}, value));
  });
}

function renderDatasets() {
  renderList(document.getElementById("datasets-list"), state.datasets, "No datasets loaded.", datasetCard);
}

function renderDocuments(documents) {
  renderList(document.getElementById("documents-list"), documents, "No documents loaded.", documentCard);
  syncParseButton(documents);
}

function renderReviews() {
  renderList(document.getElementById("reviews-list"), state.reviews, "No reviews loaded.", reviewCard);
}

function renderWorkflowList() {
  renderList(document.getElementById("workflow-list"), state.workflows, "No runs loaded.", workflowCard);
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
  if (result.run && result.run.run_id) {
    actions.append(
      el("button", { className: "secondary-button", onclick: () => openWritingRun(result.run.run_id) }, "Open Writing"),
    );
  }
  if (result.review && result.review.review_id) {
    actions.append(
      el("button", { className: "secondary-button", onclick: () => openReview(result.review.review_id) }, "Open Review"),
    );
  }
  if (
    result.review &&
    result.review.review_id &&
    result.review.status === "accepted" &&
    result.proposal &&
    result.proposal.kind === "memory_patch"
  ) {
    actions.append(
      el("button", { className: "primary-button", onclick: () => applyMemory(result.review.review_id) }, "Apply Memory"),
    );
  }
  return el("div", { className: "panel compact-panel" }, [
    el("h2", {}, "Next Actions"),
    actions.children.length ? actions : el("p", {}, "No follow-up action is available for this result."),
  ]);
}

function loopPanel(result) {
  return el("div", { className: "panel" }, [
    el("h2", {}, "Loop"),
    el(
      "p",
      {},
      `Governance action: ${((result.loop || {}).governance || {}).action || "unknown"}`,
    ),
    el(
      "div",
      { className: "source-list" },
      ((result.loop && result.loop.steps) || []).map((step) => loopStepCard(step)),
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
  container.append(
    el("article", { className: "item-card" }, [
      el("header", {}, [
        el("div", {}, [
          el("h3", {}, run.intent || "Sourced brief"),
          el("p", {}, run.run_id || ""),
        ]),
        el("span", { className: "tag ready" }, state.currentBrief.status || "ready"),
      ]),
      el("pre", {}, state.currentBrief.brief || ""),
    ]),
  );
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
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, document.name || document.document_id), el("p", {}, document.progress_msg || "")]),
      el("span", { className: `tag ${stateName.className}` }, stateName.label),
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

function reviewCard(review) {
  const proposal = review.proposal || {};
  const actions = el("div", { className: "review-actions" }, []);
  const reason = el("input", { placeholder: "Reason", value: "" });
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
  return el("article", { className: review.review_id === state.focusReviewId ? "item-card highlighted" : "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, proposal.title || review.review_id), el("p", {}, proposal.body || "")]),
      el("span", { className: `tag ${review.status === "accepted" ? "ready" : "pending"}` }, review.status),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, proposal.kind || "proposal"),
      el("span", { className: "tag" }, shortId(review.review_id)),
    ]),
    actions,
  ]);
}

function workflowCard(workflow) {
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, workflow.intent || workflow.run_id),
        el("p", {}, `${workflow.context_packets ? workflow.context_packets.length : 0} context packets`),
      ]),
      el("button", { className: "secondary-button", onclick: () => loadBrief(workflow.run_id) }, "Open"),
    ]),
    el("div", { className: "meta-row" }, [
      el("span", { className: "tag" }, shortId(workflow.run_id || "")),
      el("span", { className: "tag" }, workflow.status || "active"),
    ]),
  ]);
}

async function loadBrief(runId) {
  const payload = await api(`/api/workflows/${encodeURIComponent(runId)}/export?format=markdown`);
  const workflow = state.workflows.find((item) => item.run_id === runId) || { run_id: runId };
  state.currentBrief = {
    run: workflow,
    brief: payload.export || "",
    status: workflow.status || "active",
  };
  renderWriting();
  document.querySelector('.nav-item[data-view="writing"]').click();
}

async function openWritingRun(runId) {
  await loadBrief(runId);
}

async function openReview(reviewId) {
  state.focusReviewId = reviewId;
  await loadReviews();
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
  renderWriting();
  showToast(`${format.toUpperCase()} export loaded.`);
}

async function readSource(sourceRef) {
  const payload = await api("/api/sources/read", { method: "POST", body: { source_ref: sourceRef } });
  state.reader = payload.source || null;
  renderReader();
  document.querySelector('.nav-item[data-view="reader"]').click();
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

async function decideReview(reviewId, decision, reason) {
  await api(`/api/reviews/${encodeURIComponent(reviewId)}/decision`, {
    method: "POST",
    body: { decision, reason },
  });
  showToast(`Review ${decision}.`);
  await loadReviews();
}

async function applyMemory(reviewId) {
  await api(`/api/reviews/${encodeURIComponent(reviewId)}/apply-memory`, { method: "POST", body: {} });
  showToast("Memory applied.");
  await loadReviews();
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
  if (["ready", "complete", "accepted"].includes(value)) return "ready";
  if (["failed", "fail", "missing", "blocked", "rejected", "empty"].includes(value)) return "failed";
  return "pending";
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 3600);
}
