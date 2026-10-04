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
  const values = isMeta
    ? [
        ["分类", "Meta · " + (result.meta_intent || "system")],
        ["识别来源", result.scope?.source || "rule"],
        ["处理方式", "直接响应 · 不进入 RAG"],
      ]
    : [
        ["分类", intent.content_type_label || intent.content_type || "-"],
        ["识别来源", intent.source || "-"],
        ["写作目标", intent.goal || "-"],
      ];
  values.forEach(([label, value]) => {
    const box = node("div", "metric-box");
    box.append(node("div", "metric-label", label), node("div", "metric-value", value));
    grid.append(box);
  });
  root.append(grid);
  const reason = isMeta ? (result.scope?.reason || result.message) : intent.reason;
  if (reason) root.append(node("div", "intent-reason", reason));
}

function renderQueryPlan(result) {
  const root = $("#query-plan");
  clear(root);
  const plan = result.query_plan || {};
  const list = node("div", "query-list");
  (plan.retrieval_queries || []).forEach((query, index) => {
    list.append(node("div", "query-chip" + (index === 0 ? " original" : ""), (index === 0 ? "Original · " : "Rewrite " + index + " · ") + query));
  });
  root.append(list);
  const note = node("div", "query-note", "Intent: " + (plan.intent || "-") + " · Rewrite: " + (plan.rewrite_needed ? "yes" : "no"));
  if (plan.reason) note.textContent += " · " + plan.reason;
  root.append(note);
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

  const priorities = [
    ["core", "CORE · 核心证据"],
    ["supporting", "SUPPORTING · 辅助证据"],
    ["low_priority", "LOW PRIORITY · 低优先级"],
    ["excluded", "EXCLUDED · 当前任务排除"],
    ["unclassified", "UNCLASSIFIED"],
  ];
  const grouped = Object.fromEntries(priorities.map(([key]) => [key, []]));
  hits.forEach(hit => {
    const key = grouped[hit.evidence_priority] ? hit.evidence_priority : "unclassified";
    grouped[key].push(hit);
  });

  function renderHit(hit, index) {
    const item = node("div", "evidence-item priority-" + (hit.evidence_priority || "unclassified"));
    item.id = "evidence-" + hit.id;

    const trigger = node("button", "evidence-trigger");
    trigger.type = "button";
    trigger.append(node("div", "evidence-rank", "#" + (hit.rank || index + 1)));

    const title = node("div", "evidence-title");
    title.append(node("strong", "", hit.heading || hit.id));
    title.append(node("span", "", "PDF p." + (hit.page ?? "?") + " · " + hit.id));
    trigger.append(title);

    const scoreBox = node("div", "evidence-score");
    if (hit.evidence_type) {
      scoreBox.append(node("span", "priority-badge badge-" + (hit.evidence_priority || "unclassified"), (hit.evidence_priority || "unclassified").toUpperCase()));
      scoreBox.append(node("span", "evidence-type-badge", hit.evidence_type.toUpperCase()));
    }
    const score = hit.reranker_score ?? hit.score ?? hit.rrf_score;
    if (score !== undefined && score !== null) {
      scoreBox.append(node("span", "score-line", "score " + Number(score).toFixed(4)));
    }
    trigger.append(scoreBox);

    const panel = node("div", "evidence-panel");
    if (hit.evidence_reason) {
      const policy = node("div", "evidence-policy-row");
      policy.append(node("strong", "", "Policy · "));
      policy.append(node("span", "", hit.evidence_reason));
      panel.append(policy);
    }
    if ((hit.matched_signals || []).length) {
      panel.append(node("div", "matched-signals", "Matched signals · " + hit.matched_signals.join(" / ")));
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

  priorities.forEach(([key, label]) => {
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

function renderDocument(result) {
  const root = $("#document-output");
  clear(root);
  const doc = result.document || result.article;
  if (!doc) {
    root.append(node("p", "query-note", result.message || "没有生成文档。"));
    return;
  }
  root.append(node("h1", "", doc.title || result.topic || "Generated Content"));
  const type = result.task_intent?.content_type;

  if (type === "faq") {
    appendClaims(root, doc.intro);
    (doc.faq || []).forEach(item => {
      root.append(node("h2", "", item.question));
      appendClaim(root, item.answer);
    });
    root.append(node("h2", "", "结语"));
    appendClaims(root, doc.conclusion);
  } else if (type === "brand_intro") {
    [["品牌定位", "positioning"], ["核心价值", "value_propositions"]].forEach(([heading, key]) => {
      root.append(node("h2", "", heading));
      appendClaims(root, doc[key]);
    });
    root.append(node("h2", "", "核心能力"));
    (doc.capabilities || []).forEach(section => {
      root.append(node("h3", "", section.heading));
      appendClaims(root, section.paragraphs);
    });
    [["服务对象", "audiences"], ["可信信息", "proof_points"]].forEach(([heading, key]) => {
      if ((doc[key] || []).length) {
        root.append(node("h2", "", heading));
        appendClaims(root, doc[key]);
      }
    });
  } else if (type === "product_intro") {
    [["产品定位", "summary"], ["用户问题", "pain_points"]].forEach(([heading, key]) => {
      root.append(node("h2", "", heading));
      appendClaims(root, doc[key]);
    });
    root.append(node("h2", "", "核心能力"));
    (doc.capabilities || []).forEach(section => {
      root.append(node("h3", "", section.heading));
      appendClaims(root, section.paragraphs);
    });
    [["使用场景", "use_cases"], ["适用边界", "boundaries"]].forEach(([heading, key]) => {
      root.append(node("h2", "", heading));
      appendClaims(root, doc[key]);
    });
  } else {
    appendClaims(root, doc.lead);
    (doc.sections || []).forEach(section => {
      root.append(node("h2", "", section.heading));
      appendClaims(root, section.paragraphs);
    });
    if ((doc.faq || []).length) {
      root.append(node("h2", "", "FAQ"));
      doc.faq.forEach(item => {
        root.append(node("h3", "", item.question));
        appendClaim(root, item.answer);
      });
    }
    root.append(node("h2", "", "结语"));
    appendClaims(root, doc.conclusion);
  }

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
