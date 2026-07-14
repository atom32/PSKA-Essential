const state = {
  datasets: [],
  reviews: [],
  health: null,
  lastRunId: null,
  reader: null,
  workflows: [],
  currentBrief: null,
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
    state.currentBrief = {
      run: result.run,
      brief: result.brief || "",
      status: result.status,
      proposal: result.proposal,
      review: result.review,
    };
    renderAskResult(result);
    renderWriting();
    await loadReviews();
    await loadWorkflows();
    renderHome();
  });
}

function bindRefresh() {
  document.getElementById("refresh-all").addEventListener("click", refreshAll);
  document.getElementById("reload-datasets").addEventListener("click", loadDatasets);
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

async function loadDocuments(datasetId) {
  const payload = await api(`/api/kb/datasets/${encodeURIComponent(datasetId)}/documents`);
  renderDocuments(payload.documents || []);
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
}

function renderReviews() {
  renderList(document.getElementById("reviews-list"), state.reviews, "No reviews loaded.", reviewCard);
}

function renderWorkflowList() {
  renderList(document.getElementById("workflow-list"), state.workflows, "No runs loaded.", workflowCard);
}

function renderIngestResult(result) {
  const documents = result.documents || [];
  renderDocuments(documents);
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
  container.append(
    el("div", { className: "panel" }, [
      el("div", { className: "panel-header" }, [
        el("h2", {}, "Sourced Brief"),
        el("span", { className: "tag ready" }, result.review ? "Review created" : "Transient"),
      ]),
      el("pre", {}, result.brief || ""),
    ]),
  );
  container.append(
    el("div", { className: "panel" }, [
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
    ]),
  );
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
      el("span", { className: `tag ${step.status === "complete" ? "ready" : "pending"}` }, step.status || ""),
    ]),
  ]);
}

function datasetCard(dataset) {
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [
        el("h3", {}, dataset.name || dataset.dataset_id),
        el("p", {}, dataset.description || dataset.dataset_id || ""),
      ]),
      el("button", { className: "secondary-button", onclick: () => setAskDataset(dataset.dataset_id) }, "Use"),
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
  return el("article", { className: "item-card" }, [
    el("header", {}, [
      el("div", {}, [el("h3", {}, document.name || document.document_id), el("p", {}, document.progress_msg || "")]),
      el("span", { className: `tag ${stateName.className}` }, stateName.label),
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
  return el("article", { className: "item-card" }, [
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
  document.querySelector('#ask-form input[name="dataset_ids"]').value = datasetId || "";
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

function shortId(value) {
  const text = String(value || "");
  if (!text) return "none";
  if (text.length <= 12) return text;
  return `${text.slice(0, 6)}...${text.slice(-4)}`;
}

function documentState(document) {
  const run = String(document.run || "").toUpperCase();
  const progress = Number(document.progress || 0);
  if (run === "FAIL" || run === "CANCEL") return { label: run.toLowerCase(), className: "failed" };
  if (run === "DONE" || progress >= 1) return { label: "ready", className: "ready" };
  return { label: "processing", className: "pending" };
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 3600);
}
