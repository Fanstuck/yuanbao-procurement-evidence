const $ = (id) => document.getElementById(id);
let config = {},
  current = null,
  filter = "all",
  polling = null,
  token = sessionStorage.getItem("app_token") || "";
const statusNames = {
  queued: "等待执行",
  running: "正在执行",
  completed: "任务完成",
  partial: "记录不足",
  failed: "任务失败",
  interrupted: "已中断",
};
const recordNames = {
  verified: "金额核对通过",
  pending: "待复核",
  excluded: "不纳入",
  duplicate: "重复记录",
};
const money = (value) =>
  value === null || value === undefined
    ? "—"
    : Number(value).toLocaleString("zh-CN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
const time = (value) =>
  value ? value.replace("T", " ").replace(/\+08:00$/, "") : "—";
function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function notify(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => ($("toast").hidden = true), 4500);
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-App-Token": token,
      ...options.headers,
    },
  });
  if (!response.ok) {
    let error;
    try {
      error = await response.json();
    } catch {
      error = { detail: "服务暂时不可用" };
    }
    if (response.status === 401 && !$("auth-dialog").open)
      $("auth-dialog").showModal();
    throw new Error(
      typeof error.detail === "string" ? error.detail : "查询条件格式不正确",
    );
  }
  return response;
}
function view(name) {
  $("query-view").hidden = name !== "query";
  $("history-view").hidden = name !== "history";
  $("nav-query").classList.toggle("active", name === "query");
  $("nav-history").classList.toggle("active", name === "history");
  $("page-name").textContent = name === "query" ? "成交信息查询" : "查询历史";
  if (name === "history") loadHistory();
}
function setMode() {
  const demo =
    document.querySelector("input[name=mode]:checked").value === "demo";
  for (const id of ["keyword", "region", "freshness", "site"])
    $(id).disabled = demo;
  if (demo) {
    $("keyword").value = "智慧黑板";
    $("region").value = "江西";
    $("freshness").value = "y2";
    $("site").value = "";
  }
  $("mode-notice").hidden = !demo;
  $("mode-notice").textContent =
    "示例回放使用 2026-10-30 保存的公开公告样本，不会发起新的搜索或原站请求。";
}
function render(task) {
  current = task;
  $("task-panel").hidden = false;
  $("initial-empty").hidden = true;
  const busy = ["queued", "running"].includes(task.status);
  $("submit-btn").disabled = busy;
  $("submit-btn").textContent = busy ? "查询进行中…" : "开始查询 →";
  $("task-status").textContent = statusNames[task.status] || task.status;
  $("task-status").className =
    "badge" +
    (["partial", "failed", "interrupted"].includes(task.status)
      ? " pending"
      : "");
  $("replay-badge").hidden = task.input.mode !== "demo";
  $("task-meta").textContent =
    `任务 ${task.id} · ${task.input.keyword} / ${task.input.region || "不限地区"} · ${time(task.created_at)}`;
  $("progress-fill").style.width = task.progress + "%";
  $("stage-text").textContent = task.stage;
  $("elapsed-text").textContent = task.elapsed_seconds
    ? `任务耗时 ${task.elapsed_seconds} 秒`
    : busy
      ? "正在处理…"
      : "";
  $("task-error").hidden = !task.error;
  $("task-error").textContent = task.error || "";
  $("task-notice").hidden = !["completed", "partial"].includes(task.status);
  $("task-notice").textContent =
    task.status === "partial"
      ? `核对通过 ${task.stats.verified} 条，未达到 ${task.input.target} 条目标。可查看待复核原因，调整名称或范围后重新查询。`
      : "目标数量已达到。以下为项目成交总额，金额核对通过不代表设备规格可比。";
  const counts = {
    candidates: task.records.length,
    verified: 0,
    pending: 0,
    excluded: 0,
    duplicate: 0,
  };
  for (const r of task.records) counts[r.status] = (counts[r.status] || 0) + 1;
  $("metric-candidates").textContent = counts.candidates;
  $("metric-verified").textContent = counts.verified;
  $("metric-pending").textContent = counts.pending;
  $("metric-other").textContent = counts.excluded + counts.duplicate;
  $("export-btn").disabled = busy;
  $("preview-report").disabled = busy;
  renderRows();
  renderLogs();
}
function renderRows() {
  if (!current) return;
  const rows = current.records.filter(
    (r) =>
      filter === "all" ||
      (filter === "other"
        ? ["excluded", "duplicate"].includes(r.status)
        : r.status === filter),
  );
  $("results-body").replaceChildren();
  $("empty-results").hidden = rows.length > 0;
  $("result-count").textContent = `${rows.length} 条记录`;
  if (!rows.length && !["queued", "running"].includes(current.status)) {
    $("empty-results").querySelector("b").textContent = "当前筛选下暂无记录";
    $("empty-results").querySelector("p").textContent =
      "可切换其他状态，或调整查询条件。";
  }
  for (const r of rows) {
    const tr = document.createElement("tr");
    const project = el("td");
    project.append(
      el("div", r.title, "record-title"),
      el(
        "div",
        [r.project_id || "编号待确认", r.published_date || "日期待确认"].join(
          " · ",
        ),
        "record-sub",
      ),
    );
    const amount = el("td");
    const number = el("div", money(r.amount_yuan), "amount");
    number.append(el("small", r.amount_yuan ? " 元" : ""));
    amount.append(number, el("div", "项目总额 · 规格另行复核", "amount-label"));
    const state = el("td");
    state.append(
      el("span", recordNames[r.status], "state-chip " + r.status),
      el("div", r.reason, "state-reason"),
    );
    const source = el("td");
    let host = "来源待核实";
    try {
      host = new URL(r.url).hostname;
    } catch {}
    source.append(el("div", host, "source-host"));
    const actions = el("div", undefined, "source-actions");
    const inspect = el("button", "查看依据", "text-button");
    inspect.type = "button";
    inspect.dataset.recordId = r.id;
    inspect.onclick = () => showEvidence(r.id);
    const link = el("a", "打开公告 ↗");
    link.href = r.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    actions.append(inspect, link);
    source.append(actions);
    tr.append(project, amount, state, source);
    $("results-body").append(tr);
  }
}
function renderLogs() {
  $("run-logs").replaceChildren();
  for (const log of current.logs) {
    $("run-logs").append(el("li", `${time(log.time)}　${log.message}`));
  }
  $("request-trace").replaceChildren();
  for (const r of current.requests) {
    const block = el("div", undefined, "trace-item");
    block.append(
      el(
        "div",
        r.replayed
          ? `历史回放 · 样本日期 ${r.snapshot_date}`
          : `实时请求 · ${r.version || "版本未返回"}`,
      ),
      el(
        "div",
        `请求标识：${r.request_id || "未返回"} · 接口耗时 ${r.elapsed_seconds} 秒`,
      ),
      el("div", `查询条件：${JSON.stringify(r.payload)}`),
    );
    $("request-trace").append(block);
  }
}
function showEvidence(id) {
  const r = current.records.find((x) => x.id === id);
  if (!r) return;
  $("evidence-title").textContent = r.title;
  const body = $("evidence-content");
  body.replaceChildren();
  body.append(
    el("span", recordNames[r.status], "state-chip " + r.status),
    el("p", r.reason, "evidence-value"),
  );
  const amounts = el("div", undefined, "evidence-amounts");
  for (const [label, value] of [
    ["正文总额（元）", r.amount_yuan],
    ["概要换算（元）", r.summary_yuan],
  ]) {
    const cell = el("div");
    cell.append(el("small", label), el("b", money(value)));
    amounts.append(cell);
  }
  body.append(amounts, el("div", "金额证据片段", "evidence-label"));
  if (r.evidence.length) {
    for (const text of r.evidence)
      body.append(el("pre", text, "evidence-block"));
  } else
    body.append(
      el(
        "p",
        "尚未取得足够的原文金额证据，请打开原公告检查。",
        "evidence-value",
      ),
    );
  for (const [label, value] of [
    ["项目编号", r.project_id || "待确认"],
    ["原公告日期", r.published_date || "待确认"],
    ["正文读取时间", time(r.fetched_at)],
    ["来源网址", r.final_url || r.url],
    ["原文 SHA-256", r.snapshot_sha256 || "未取得原文"],
  ]) {
    body.append(
      el("div", label, "evidence-label"),
      el("div", value, "evidence-value"),
    );
  }
  body.append(
    el("div", "使用说明", "evidence-label"),
    el(
      "p",
      "金额一致只是一项规则检查。请继续核对规格、数量、包件、更正公告与服务范围，不直接用项目总额推算设备单价。",
      "evidence-value",
    ),
  );
  $("drawer-backdrop").hidden = false;
  $("evidence-drawer").hidden = false;
  $("drawer-close").focus();
}
function closeEvidence() {
  $("drawer-backdrop").hidden = true;
  $("evidence-drawer").hidden = true;
}
async function poll(id) {
  clearTimeout(polling);
  try {
    const task = await (await api("/api/tasks/" + id)).json();
    render(task);
    if (["queued", "running"].includes(task.status))
      polling = setTimeout(() => poll(id), 900);
    else loadHistory(false);
  } catch (error) {
    notify(error.message);
    $("submit-btn").disabled = false;
  }
}
async function loadHistory(show = true) {
  try {
    const items = await (await api("/api/tasks")).json();
    $("history-count").textContent = items.length;
    if (!show) return;
    $("history-list").replaceChildren();
    if (!items.length) {
      $("history-list").append(
        el("p", "还没有历史任务，先发起一次查询吧。", "empty-state"),
      );
      return;
    }
    for (const t of items) {
      const row = el("div", undefined, "history-item");
      const left = el("div");
      left.append(
        el("h3", `${t.input.keyword} · ${t.input.region || "不限地区"}`),
        el(
          "p",
          `${time(t.created_at)} · ${t.id} · ${t.input.mode === "live" ? "实时检索" : "历史示例回放"}`,
        ),
      );
      const right = el("div", undefined, "history-right");
      right.append(
        el(
          "span",
          statusNames[t.status],
          "badge" + (t.status === "partial" ? " pending" : ""),
        ),
        el("span", `核对通过 ${t.stats.verified} 条`, "subtle"),
      );
      const open = el("button", "查看任务 →", "secondary");
      open.onclick = () => {
        view("query");
        poll(t.id);
        $("task-panel").scrollIntoView({ behavior: "smooth" });
      };
      right.append(open);
      row.append(left, right);
      $("history-list").append(row);
    }
  } catch (error) {
    notify(error.message);
  }
}
async function exportTask(preview = false) {
  if (!current) return;
  const format = preview ? "html" : $("export-format").value;
  try {
    const response = await api(
      `/api/tasks/${current.id}/export?format=${format}`,
    );
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    if (preview) {
      const tab = window.open(url, "_blank");
      if (!tab) notify("浏览器阻止了新窗口，可使用导出按钮。");
      setTimeout(() => URL.revokeObjectURL(url), 120000);
    } else {
      const link = el("a");
      link.href = url;
      link.download = `采购成交信息报告-${current.input.keyword}-${current.id}.${format}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      notify("报告已导出，包含来源与核验依据。");
    }
  } catch (error) {
    notify(error.message);
  }
}
$("query-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("submit-btn").disabled = true;
  clearTimeout(polling);
  try {
    const payload = {
      keyword: $("keyword").value.trim(),
      region: $("region").value.trim(),
      freshness: $("freshness").value,
      site: $("site").value,
      target: Number($("target").value),
      mode: document.querySelector("input[name=mode]:checked").value,
      expand_search: $("expand-search").checked,
    };
    const task = await (
      await api("/api/tasks", { method: "POST", body: JSON.stringify(payload) })
    ).json();
    filter = "all";
    document
      .querySelectorAll(".tab")
      .forEach((n) => n.classList.toggle("active", n.dataset.filter === "all"));
    render(task);
    poll(task.id);
  } catch (error) {
    $("submit-btn").disabled = false;
    notify(error.message);
  }
});
document
  .querySelectorAll("input[name=mode]")
  .forEach((n) => n.addEventListener("change", setMode));
document.querySelectorAll(".tab").forEach((n) =>
  n.addEventListener("click", () => {
    filter = n.dataset.filter;
    document
      .querySelectorAll(".tab")
      .forEach((x) => x.classList.toggle("active", x === n));
    renderRows();
  }),
);
$("nav-query").onclick = () => view("query");
$("nav-history").onclick = () => view("history");
$("refresh-history").onclick = () => loadHistory();
$("export-btn").onclick = () => exportTask();
$("preview-report").onclick = () => exportTask(true);
$("drawer-close").onclick = closeEvidence;
$("drawer-backdrop").onclick = closeEvidence;
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeEvidence();
});
$("auth-form").onsubmit = () => {
  token = $("app-token").value;
  sessionStorage.setItem("app_token", token);
  setTimeout(() => loadHistory(false), 50);
};
(async () => {
  try {
    config = await (await api("/api/config")).json();
    $("connection").lastChild.textContent = config.live_available
      ? " 元宝搜索已就绪"
      : " 示例可用 · 实时密钥未配置";
    if (!config.live_available) {
      document.querySelector("input[value=demo]").checked = true;
      setMode();
    }
    if (config.auth_required && !token) $("auth-dialog").showModal();
    else loadHistory(false);
  } catch (error) {
    $("connection").textContent = "服务连接失败";
    notify(error.message);
  }
})();
