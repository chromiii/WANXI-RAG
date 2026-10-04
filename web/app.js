const $ = (selector) => document.querySelector(selector);

const state = { result: null, info: null };

function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined && text !== null) item.textContent = String(text);
  return item;
}

function clear(target) {
  while (target.firstChild) target.removeChild(target.firstChild);
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2400);
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, options);
  let value;
  try {
    value = await response.json();
  } catch (_) {
    throw new Error("服务器返回了非 JSON 响应");
  }
  if (!response.ok) throw new Error(value.error || "请求失败");
  return value;
}

async function loadInfo() {
  try {
    state.info = await jsonFetch("/api/info");
    const api = $("#api-status");
    api.textContent = state.info.api_configured ? "API · Live ready" : "API · Offline only";
    api.classList.toggle("good", !!state.info.api_configured);
    $("#model-status").textContent = "Model · " + (state.info.model || "-");
    if (!state.info.api_configured && $("#mode").value === "live") $("#mode").value = "offline";
  } catch (error) {
    $("#api-status").textContent = "API · unavailable";
    showToast(error.message);
  }
}

function pill(text, good = false) {
  const p = node("span", "pill" + (good ? " validation-good" : ""), text);
  return p;
}

function renderIntent(result) {
  const root = $("#intent-card");
  clear(root);
  const intent = result.task_intent || {};
  const isMeta = result.status === "meta" || result.meta_intent;
  const grid = node("div", "intent-grid");
  const confidence = typeof intent.confidence === "number"
    ? Math.round(intent.confidence * 100) + "%"
    : "-";
  const values = isMeta
    ? [
        ["分类", "Meta · " + (result.meta_intent || "system")],
        ["识别来源", result.scope?.source || "rule"],
        ["处理方式", "直接响应 · 不进入 RAG"],
      ]
    : [
        ["呈现类型", intent.content_type_label || intent.content_type || "-"],
        ["Intent 来源", intent.source || "-"],
        ["语义焦点", intent.semantic_focus || "-"],
        ["置信度", confidence],
      ];
  values.forEach(([label, value]) => {
    const box = node("div", "metric-box");
    box.append(node("div", "metric-label", label), node("div", "metric-value", value));
    grid.append(box);
  });
  root.append(grid);
  const reason = isMeta ? (result.scope?.reason || result.message) : intent.reason;
  if (reason) root.append(node("div", "intent-reason", reason));
  if (!isMeta) {
    const objective = node("div", "intent-needs");
    objective.append(node("div", "small-title", "User goal"));
    objective.append(node("div", "intent-reason", intent.user_goal || intent.goal || result.topic || "-"));
    objective.append(node(
      "div",
      "query-note",
      "Original topic · " + (intent.primary_question || result.topic || "-")
    ));
    root.append(objective);
  }
}

function renderQueryPlan(result) {
  const root = $("#query-plan");
  clear(root);
  const plan = result.query_plan || {};
  const list = node("div", "query-list");
  (plan.retrieval_queries || []).forEach((query, index) => {
    const label = index === 0 ? "Original · " : ((plan.strategy || "rewrite").toUpperCase() + " " + index + " · ");
    list.append(node("div", "query-chip" + (index === 0 ? " original" : ""), label + query));
  });
  root.append(list);
  const note = node("div", "query-note", "Strategy: " + (plan.strategy || "-") + " · Intent: " + (plan.intent || "-") + " · Extra queries: " + Math.max(0, (plan.retrieval_queries || []).length - 1));
  if (plan.reason) note.textContent += " · " + plan.reason;
  root.append(note);
  if (plan.rerank_query) {
    const details = node("details", "query-details");
    details.append(node("summary", "", "查看 Rerank Query"));
    details.append(node("pre", "", plan.rerank_query));
    root.append(details);
  }
}

function renderWorkflow(result) {
  const root = $("#workflow-trace");
  clear(root);
  (result.workflow_trace || []).forEach(step => {
    const item = node("div", "workflow-step");
    item.append(node("div", "workflow-name", step.step || "-"));
    item.append(node("div", "workflow-status", step.status || "-"));
    const extras = Object.entries(step)
      .filter(([key]) => !["step", "status", "evidence_ids"].includes(key))
      .map(([key, value]) => key + ": " + (typeof value === "object" ? JSON.stringify(value) : value));
    if (extras.length) item.append(node("div", "workflow-extra", extras.join("\n")));
    root.append(item);
  });
}

function assetUrl(hit) {
  if (!hit.asset_path) return null;
  const name = hit.asset_path.split(/[\\/]/).pop();
  return /^p\d{3}\.png$/.test(name) ? "/assets/pages/" + name : null;
}

function renderEvidence(result) {
  const root = $("#evidence-list");
  clear(root);
  const hits = result.retrieval_hits || result.hits || [];
  if (!hits.length) {
    root.append(node("p", "query-note", "没有返回证据。"));
    return;
  }

  const groups = [
    ["selected", "SELECTED · 送入 Writer"],
    ["filtered", "FILTERED · Hard Safety"],
    ["deduplicated", "DEDUPED · 近重复"],
    ["budget_dropped", "BUDGET · 超出上下文预算"],
    ["not_selected", "NOT SELECTED · Final Top-N 之外"],
    ["unprocessed", "UNPROCESSED"],
  ];
  const grouped = Object.fromEntries(groups.map(([key]) => [key, []]));
  hits.forEach(hit => {
    const key = grouped[hit.postprocess_status] ? hit.postprocess_status : "unprocessed";
    grouped[key].push(hit);
  });

  function renderHit(hit, index) {
    const status = hit.postprocess_status || "unprocessed";
    const item = node("div", "evidence-item status-" + status);
    item.id = "evidence-" + hit.id;

    const trigger = node("button", "evidence-trigger");
    trigger.type = "button";
    trigger.append(node("div", "evidence-rank", "#" + (hit.rank || index + 1)));

    const title = node("div", "evidence-title");
    title.append(node("strong", "", hit.heading || hit.id));
    title.append(node("span", "", "PDF p." + (hit.page ?? "?") + " · " + hit.id));
    trigger.append(title);

    const scoreBox = node("div", "evidence-score");
    scoreBox.append(node("span", "priority-badge badge-" + status, status.replaceAll("_", " ").toUpperCase()));
    if (hit.evidence_type) scoreBox.append(node("span", "evidence-type-badge", hit.evidence_type.toUpperCase()));
    const score = hit.reranker_score ?? hit.score ?? hit.rrf_score;
    if (score !== undefined && score !== null) {
      scoreBox.append(node("span", "score-line", "rerank " + Number(score).toFixed(4)));
    }
    trigger.append(scoreBox);

    const panel = node("div", "evidence-panel");
    if (hit.postprocess_reason) {
      const policy = node("div", "evidence-policy-row");
      policy.append(node("strong", "", "Post-process · "));
      policy.append(node("span", "", hit.postprocess_reason));
      panel.append(policy);
    }
    if ((hit.risk_flags || []).length) {
      panel.append(node("div", "matched-signals", "Risk flags · " + hit.risk_flags.join(" / ")));
    }
    panel.append(node("p", "evidence-text", hit.text || hit.quote || ""));

    const channels = node("div", "channel-grid");
    if (hit.rrf_score !== undefined) channels.append(node("span", "channel-chip", "RRF " + Number(hit.rrf_score).toFixed(5)));
    if (hit.pre_rerank_rank !== undefined) channels.append(node("span", "channel-chip", "pre-rerank #" + hit.pre_rerank_rank));
    Object.entries(hit.retrieval_channels || {}).forEach(([name, data]) => {
      channels.append(node("span", "channel-chip", name + " #" + data.rank + " · " + Number(data.score || 0).toFixed(4)));
    });
    panel.append(channels);

    const url = assetUrl(hit);
    if (url) {
      const link = node("a", "page-link", "查看整页证据 · PDF p." + hit.page);
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener";
      panel.append(link);
    }

    trigger.addEventListener("click", () => item.classList.toggle("open"));
    item.append(trigger, panel);
    return item;
  }

  groups.forEach(([key, label]) => {
    const group = grouped[key];
    if (!group.length) return;
    const section = node("div", "evidence-group");
    const header = node("div", "evidence-group-header");
    header.append(node("strong", "", label));
    header.append(node("span", "", group.length + " 条"));
    section.append(header);
    group.forEach((hit, index) => section.append(renderHit(hit, index)));
    root.append(section);
  });
}

function citationButton(id) {
  const btn = node("button", "citation-btn", id);
  btn.type = "button";
  btn.addEventListener("click", () => {
    const evidence = document.getElementById("evidence-" + id);
    if (!evidence) return;
    evidence.classList.add("open", "flash");
    evidence.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => evidence.classList.remove("flash"), 1400);
  });
  return btn;
}

function appendClaim(root, claim) {
  const p = node("p", "claim", claim.text || "");
  const citations = node("span", "citation-row");
  (claim.citations || []).forEach(id => citations.append(citationButton(id)));
  p.append(citations);
  root.append(p);
}

function appendClaims(root, claims) {
  (claims || []).forEach(claim => appendClaim(root, claim));
}

function appendExtensionFaq(root, doc) {
  const items = doc.faq || [];
  if (!items.length) return;
  root.append(node("h2", "", "延展 FAQ"));
  const list = node("div", "faq-output-list");
  items.forEach((item, index) => {
    const card = node("section", "faq-output-card compact-faq");
    const q = node("div", "faq-question");
    q.append(node("span", "faq-index", "Q" + (index + 1)));
    q.append(node("h3", "", item.question));
    card.append(q);
    const answer = node("div", "faq-answer");
    appendClaim(answer, item.answer);
    card.append(answer);
    list.append(card);
  });
  root.append(list);
}

function appendSourceVisuals(root, result) {
  const visuals = result.source_visuals || [];
  if (!visuals.length) return;
  root.append(node("h2", "", "引用页图"));
  const grid = node("div", "source-visual-grid");
  visuals.forEach(item => {
    const url = assetUrl(item);
    if (!url) return;
    const card = node("a", "source-visual-card");
    card.href = url;
    card.target = "_blank";
    card.rel = "noopener";
    const img = document.createElement("img");
    img.src = url;
    img.alt = (item.heading || "PDF evidence") + " · PDF p." + (item.page ?? "?");
    img.loading = "lazy";
    const caption = node("div", "source-visual-caption");
    caption.append(node("strong", "", item.heading || "PDF 页图"));
    caption.append(node("span", "", "PDF p." + (item.page ?? "?") + " · " + (item.id || "")));
    card.append(img, caption);
    grid.append(card);
  });
  if (grid.children.length) root.append(grid);
}

function renderDocument(result) {
  const root = $("#document-output");
  clear(root);
  const doc = result.document || result.article;
  if (!doc) {
    root.append(node("p", "query-note", result.message || "没有生成文档。"));
    return;
  }
  const type = result.task_intent?.content_type;
  root.className = "document-output output-" + (type || "blog");
  root.append(node("h1", "", doc.title || result.topic || "Generated Content"));

  if (type === "faq") {
    const intro = node("div", "output-intro");
    appendClaims(intro, doc.intro);
    root.append(intro);
    const list = node("div", "faq-output-list");
    (doc.faq || []).forEach((item, index) => {
      const card = node("section", "faq-output-card");
      const q = node("div", "faq-question");
      q.append(node("span", "faq-index", "Q" + (index + 1)));
      q.append(node("h2", "", item.question));
      card.append(q);
      const answer = node("div", "faq-answer");
      appendClaim(answer, item.answer);
      card.append(answer);
      list.append(card);
    });
    root.append(list);
    if ((doc.conclusion || []).length) {
      const footer = node("div", "output-conclusion");
      footer.append(node("strong", "", "总结"));
      appendClaims(footer, doc.conclusion);
      root.append(footer);
    }
  } else if (type === "brand_intro") {
    const grid = node("div", "structured-output-grid");
    [["品牌定位", "positioning"], ["核心价值", "value_propositions"], ["服务对象", "audiences"], ["可信信息", "proof_points"]].forEach(([heading, key]) => {
      if (!(doc[key] || []).length) return;
      const card = node("section", "structured-output-card");
      card.append(node("div", "structured-label", heading));
      appendClaims(card, doc[key]);
      grid.append(card);
    });
    root.append(grid);
    root.append(node("h2", "", "核心能力"));
    const capabilities = node("div", "capability-grid");
    (doc.capabilities || []).forEach(section => {
      const card = node("section", "capability-card");
      card.append(node("h3", "", section.heading));
      appendClaims(card, section.paragraphs);
      capabilities.append(card);
    });
    root.append(capabilities);
    appendExtensionFaq(root, doc);
  } else if (type === "product_intro") {
    const hero = node("section", "product-hero");
    hero.append(node("div", "structured-label", "产品定位"));
    appendClaims(hero, doc.summary);
    root.append(hero);

    if ((doc.pain_points || []).length) {
      root.append(node("h2", "", "解决什么问题"));
      const pains = node("div", "structured-output-grid");
      doc.pain_points.forEach(item => {
        const card = node("section", "structured-output-card");
        appendClaim(card, item);
        pains.append(card);
      });
      root.append(pains);
    }

    root.append(node("h2", "", "核心能力"));
    const capabilities = node("div", "capability-grid");
    (doc.capabilities || []).forEach(section => {
      const card = node("section", "capability-card");
      card.append(node("h3", "", section.heading));
      appendClaims(card, section.paragraphs);
      capabilities.append(card);
    });
    root.append(capabilities);

    [["使用场景", "use_cases"], ["适用边界", "boundaries"]].forEach(([heading, key]) => {
      if (!(doc[key] || []).length) return;
      root.append(node("h2", "", heading));
      const block = node("div", "output-intro");
      appendClaims(block, doc[key]);
      root.append(block);
    });
    appendExtensionFaq(root, doc);
  } else {
    const lead = node("div", "blog-lead");
    appendClaims(lead, doc.lead);
    root.append(lead);
    (doc.sections || []).forEach(section => {
      root.append(node("h2", "", section.heading));
      appendClaims(root, section.paragraphs);
    });
    root.append(node("h2", "", "结语"));
    appendClaims(root, doc.conclusion);
    appendExtensionFaq(root, doc);
  }

  appendSourceVisuals(root, result);

  if ((doc.limitations || []).length) {
    root.append(node("h2", "", "资料与限制"));
    const box = node("div", "limitations");
    doc.limitations.forEach(item => box.append(node("div", "", "• " + item)));
    root.append(box);
  }
}

function renderDiagnostics(result) {
  const validation = $("#validation");
  clear(validation);
  const v = result.validation || {};
  const grid = node("div", "validation-grid");
  if (Object.keys(v).length) {
    grid.append(pill("Claims " + (v.claim_count ?? "-"), true));
    grid.append(pill("Citation IDs " + (v.citation_ids_valid ? "PASS" : "FAIL"), !!v.citation_ids_valid));
    grid.append(pill("Numeric Guard " + (v.numeric_guard_passed ? "PASS" : "FAIL"), !!v.numeric_guard_passed));
    if (v.semantic_entailment) grid.append(pill("Entailment · " + v.semantic_entailment));
  } else {
    grid.append(pill("No validation result"));
  }
  validation.append(grid);

  const callsRoot = $("#model-calls");
  clear(callsRoot);
  const calls = node("div", "call-grid");
  (result.model_calls || []).forEach(call => {
    const card = node("div", "call-card");
    card.append(node("strong", "", call.purpose || "model call"));
    card.append(node("span", "", call.model || "-"));
    card.append(node("span", "", "tokens " + (call.usage?.total_tokens ?? "-")));
    card.append(node("span", "", "latency " + (call.duration_ms ?? "-") + " ms"));
    calls.append(card);
  });
  if (!(result.model_calls || []).length) calls.append(node("div", "query-note", "本次没有外部模型调用。"));
  callsRoot.append(calls);
}

function renderRunMeta(result) {
  const root = $("#run-meta");
  clear(root);
  root.append(pill("Run · " + (result.run_id || "CLI/no id")));
  root.append(pill("Status · " + (result.status || "-"), result.status === "ok"));
  root.append(pill("Mode · " + (result.mode || "-")));
  if (result.duration_ms !== undefined) root.append(pill("Workflow · " + result.duration_ms + " ms"));
}

function renderResult(result) {
  state.result = result;
  $("#empty-state").classList.add("hidden");
  $("#result-root").classList.remove("hidden");
  renderRunMeta(result);
  renderIntent(result);
  renderQueryPlan(result);
  renderWorkflow(result);
  renderEvidence(result);
  renderDocument(result);
  renderDiagnostics(result);
  $("#raw-json").textContent = JSON.stringify(result, null, 2);
}

async function runWorkflow(event) {
  event.preventDefault();
  const button = $("#run-button");
  button.disabled = true;
  button.classList.add("loading");
  button.querySelector(".button-label").textContent = "RAG 运行中…";
  try {
    const result = await jsonFetch("/api/write", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: $("#topic").value,
        audience: $("#audience").value,
        content_type: $("#content-type").value,
        mode: $("#mode").value,
        top_k: Number($("#top-k").value),
      }),
    });
    renderResult(result);
    showToast("完成 · " + (result.run_id || ""));
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.classList.remove("loading");
    button.querySelector(".button-label").textContent = "运行完整 RAG Workflow";
  }
}

function openLogs() {
  $("#log-drawer").classList.add("open");
  $("#drawer-backdrop").classList.add("open");
  $("#log-drawer").setAttribute("aria-hidden", "false");
  loadLogs();
}

function closeLogs() {
  $("#log-drawer").classList.remove("open");
  $("#drawer-backdrop").classList.remove("open");
  $("#log-drawer").setAttribute("aria-hidden", "true");
}

async function loadLogs() {
  const list = $("#log-list");
  clear(list);
  list.append(node("p", "query-note", "读取中…"));
  try {
    const data = await jsonFetch("/api/logs?limit=20");
    clear(list);
    if (!data.runs.length) {
      list.append(node("p", "query-note", "还没有日志。先运行一次 RAG。"));
      return;
    }
    data.runs.forEach(record => {
      const btn = node("button", "log-run");
      btn.type = "button";
      btn.append(node("strong", "", record.run_id || "-"));
      const topic = record.request?.topic || record.request?.query || record.endpoint || "";
      btn.append(node("span", "", (record.logged_at_utc || "") + " · " + topic));
      btn.addEventListener("click", () => {
        const detail = $("#log-detail");
        clear(detail);
        const pre = node("pre", "", JSON.stringify(record, null, 2));
        detail.append(pre);
      });
      list.append(btn);
    });
  } catch (error) {
    clear(list);
    list.append(node("p", "query-note", error.message));
  }
}

$("#rag-form").addEventListener("submit", runWorkflow);
$("#top-k").addEventListener("input", event => $("#top-k-value").textContent = event.target.value);
document.querySelectorAll(".case-button").forEach(button => {
  button.addEventListener("click", () => {
    $("#topic").value = button.dataset.topic;
    $("#content-type").value = button.dataset.type;
  });
});
$("#refresh-logs").addEventListener("click", openLogs);
$("#close-logs").addEventListener("click", closeLogs);
$("#drawer-backdrop").addEventListener("click", closeLogs);

loadInfo();
