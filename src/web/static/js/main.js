// ===== Global State =====
let availablePersonas = [];
let selectedBloggers = new Set();
let isRunning = false;
let currentTaskId = null;

// ===== Init =====
document.addEventListener("DOMContentLoaded", () => {
    loadConfig();
    loadPersonas();
    bindNavigation();
    loadDashboardStatus();
});

// ===== Config & Personas =====

async function loadConfig() {
    try {
        const resp = await fetch("/api/config");
        const config = await resp.json();

        const llmSelect = document.getElementById("llmSelect");
        if (config.default_llm_provider) {
            llmSelect.value = config.default_llm_provider;
        }

        const badge = document.getElementById("llmBadge");
        const providerNames = {
            zhipu: "智谱", deepseek: "DeepSeek", openai: "OpenAI",
            qwen: "通义千问", minimax: "MiniMax", kimi: "Kimi"
        };
        const active = Object.entries(config.providers)
            .filter(([, v]) => v)
            .map(([k]) => providerNames[k] || k);
        badge.textContent = active.length ? active.join(" / ") : "未配置 LLM";

        if (config.default_llm_provider) {
            llmSelect.value = config.default_llm_provider;
        }
    } catch (e) {
        console.error("Failed to load config:", e);
    }
}

async function loadPersonas() {
    try {
        const resp = await fetch("/api/personas");
        const data = await resp.json();
        availablePersonas = data.personas;

        const container = document.getElementById("bloggerTags");
        container.innerHTML = "";

        // 默认选中的博主
        const defaultBloggers = new Set(["jl韭菜抄家", "只核大学生"]);

        availablePersonas.forEach(name => {
            const tag = document.createElement("span");
            const isSelected = defaultBloggers.has(name);
            tag.className = isSelected ? "blogger-tag selected" : "blogger-tag";
            tag.textContent = name;
            tag.dataset.name = name;
            
            if (isSelected) {
                selectedBloggers.add(name);
            }
            
            tag.onclick = () => {
                if (selectedBloggers.has(name)) {
                    selectedBloggers.delete(name);
                    tag.classList.remove("selected");
                } else {
                    selectedBloggers.add(name);
                    tag.classList.add("selected");
                }
            };
            container.appendChild(tag);
        });
    } catch (e) {
        console.error("Failed to load personas:", e);
    }
}

function bindNavigation() {
    document.querySelectorAll(".nav-item").forEach(btn => {
        btn.addEventListener("click", () => {
            switchTab(btn.dataset.tab);
        });
    });
}

function switchTab(tab) {
    document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
    const navBtn = document.querySelector(`.nav-item[data-tab="${tab}"]`);
    if (navBtn) navBtn.classList.add("active");

    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    document.getElementById(`tab-${tab}`).classList.add("active");

    if (tab === "analysis") { loadHistory(); loadNewsInputFiles(); loadNewsTxtList(); }
    if (tab === "posts") { initCrawlerUI(); loadPosts(); }
    if (tab === "radar") loadRadarStatus();
    if (tab === "hot") loadHotStocksPage();
    if (tab === "dashboard") loadDashboardStatus();
}

// ===== Dashboard (仪表盘) =====

async function loadDashboardStatus() {
    // LLM status
    const llmEl = document.getElementById("dashLlmStatus");
    try {
        const resp = await fetch("/api/config");
        const config = await resp.json();
        const activeCount = Object.values(config.providers || {}).filter(v => v).length;
        if (activeCount > 0) {
            llmEl.textContent = `${activeCount} 个已配置`;
            llmEl.className = "status-value status-ok";
        } else {
            llmEl.textContent = "未配置";
            llmEl.className = "status-value status-warn";
        }
    } catch {
        llmEl.textContent = "检测失败";
        llmEl.className = "status-value status-err";
    }

    // Radar status
    const radarEl = document.getElementById("dashRadarStatus");
    try {
        const resp = await fetch("/api/radar/status");
        const data = await resp.json();
        if (data.ready) {
            radarEl.textContent = `就绪 (${data.last_date})`;
            radarEl.className = "status-value status-ok";
        } else {
            radarEl.textContent = "未就绪";
            radarEl.className = "status-value status-warn";
        }
    } catch {
        radarEl.textContent = "检测失败";
        radarEl.className = "status-value status-err";
    }

    // History count
    const histEl = document.getElementById("dashHistoryCount");
    try {
        const resp = await fetch("/api/history");
        const data = await resp.json();
        const count = (data.reports || []).length;
        histEl.textContent = count > 0 ? `${count} 份报告` : "暂无报告";
        histEl.className = "status-value" + (count > 0 ? " status-ok" : "");
    } catch {
        histEl.textContent = "检测失败";
        histEl.className = "status-value status-err";
    }

    // Hot stocks overview
    loadDashHotStocks("dc");
}

// ===== Collapsible Cards =====

function toggleCard(cardId) {
    const card = document.getElementById(cardId);
    card.classList.toggle("collapsed");
}

function expandCard(cardId) {
    const card = document.getElementById(cardId);
    card.classList.remove("collapsed");
}

// ===== Analysis Flow =====

async function startAnalysis() {
    const query = document.getElementById("queryInput").value.trim();
    if (!query) {
        document.getElementById("queryInput").focus();
        return;
    }
    if (isRunning) return;

    const bloggers = [...selectedBloggers];
    if (bloggers.length === 0) {
        alert("请至少选择一个博主");
        return;
    }

    const rounds = document.getElementById("roundsSelect").value;
    const llmProvider = document.getElementById("llmSelect").value;

    isRunning = true;
    const runBtn = document.getElementById("runBtn");
    runBtn.disabled = true;
    runBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" style="animation: spin 1s linear infinite"><path fill="currentColor" d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg> 分析中...';

    document.getElementById("progressBar").style.display = "block";
    document.getElementById("resultArea").style.display = "block";
    document.getElementById("doneBanner").style.display = "none";

    resetProgress();
    hideAllCards();

    try {
        const resp = await fetch("/api/analysis/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, bloggers, rounds, llm_provider: llmProvider }),
        });
        const { task_id } = await resp.json();
        currentTaskId = task_id;

        listenSSE(task_id);
    } catch (e) {
        console.error("Failed to start analysis:", e);
        resetUI();
        alert("启动分析失败: " + e.message);
    }
}

function listenSSE(taskId) {
    const es = new EventSource(`/api/analysis/stream/${taskId}`);

    es.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleSSEMessage(msg, es);
    };

    es.onerror = () => {
        es.close();
        resetUI();
    };
}

function handleSSEMessage(msg, es) {
    switch (msg.type) {
        case "start":
            setStepActive(0);
            break;

        case "blogger_progress":
            // 博主讨论进度
            updateBloggerProgress(msg.current, msg.total, msg.blogger_name);
            break;

        case "step_done":
            setStepDone(msg.step_index);
            if (msg.step_index < 3) {
                setStepActive(msg.step_index + 1);
            }
            break;

        case "step_data":
            renderStepData(msg.step, msg.data);
            break;

        case "done":
            es.close();
            setStepDone(3);
            document.getElementById("doneBanner").style.display = "flex";
            document.getElementById("doneText").textContent = `分析完成，耗时 ${msg.total_time}s`;
            resetUI();
            break;

        case "error":
            es.close();
            const banner = document.getElementById("doneBanner");
            banner.style.display = "flex";
            banner.style.borderColor = "rgba(248, 113, 113, 0.2)";
            banner.style.background = "rgba(248, 113, 113, 0.08)";
            banner.style.color = "var(--red)";
            document.getElementById("doneText").textContent = `分析失败: ${msg.message}`;
            resetUI();
            break;
    }
}

// ===== Progress =====

function resetProgress() {
    document.querySelectorAll(".step").forEach(s => {
        s.classList.remove("active", "done");
    });
    document.querySelectorAll(".step-line").forEach(l => {
        l.classList.remove("done");
    });
}

function setStepActive(index) {
    const step = document.querySelector(`.step[data-step="${index}"]`);
    if (step) step.classList.add("active");
}

function setStepDone(index) {
    const step = document.querySelector(`.step[data-step="${index}"]`);
    if (step) {
        step.classList.remove("active");
        step.classList.add("done");
    }
    const lines = document.querySelectorAll(".step-line");
    if (index > 0 && lines[index - 1]) {
        lines[index - 1].classList.add("done");
    }
}

function updateBloggerProgress(current, total, bloggerName) {
    // 更新博主讨论步骤的文本，显示当前进度
    const step = document.querySelector(`.step[data-step="1"]`); // 步骤 1 是博主讨论
    if (!step) return;
    
    const span = step.querySelector("span");
    if (!span) return;
    
    const percent = Math.round((current / total) * 100);
    span.textContent = `博主讨论 (${current}/${total})`;
    
    // 可选：添加博主名称提示
    step.title = `当前发言: ${bloggerName}`;
    
    // 当完成时恢复文本
    if (current >= total) {
        setTimeout(() => {
            span.textContent = "博主讨论";
            step.title = "";
        }, 1000);
    }
}

// ===== Result Rendering =====

function hideAllCards() {
    ["newsCard", "bloggersCard", "riskCard", "decisionCard"].forEach(id => {
        const el = document.getElementById(id);
        el.style.display = "none";
        el.classList.remove("collapsed");
    });
}

function renderStepData(step, data) {
    switch (step) {
        case "news":
            document.getElementById("newsCard").style.display = "block";
            expandCard("newsCard");
            const sourceTag = document.getElementById("newsSourceTag");
            sourceTag.style.display = data.is_llm_generated ? "inline" : "none";
            document.getElementById("newsContent").innerHTML =
                simpleMarkdown(data.summary || "（无资讯内容）");
            break;

        case "bloggers":
            document.getElementById("bloggersCard").style.display = "block";
            expandCard("bloggersCard");
            renderDiscussions(data.discussions, data.consensus);
            break;

        case "risk":
            document.getElementById("riskCard").style.display = "block";
            expandCard("riskCard");
            renderRisk(data);
            break;

        case "decision":
            document.getElementById("decisionCard").style.display = "block";
            expandCard("decisionCard");
            document.getElementById("decisionContent").innerHTML =
                `<div class="decision-text">${simpleMarkdown(data.answer || "（无决策）")}</div>`;
            break;
    }
}

function renderDiscussions(discussions, consensus) {
    const container = document.getElementById("bloggersContent");
    if (!discussions || discussions.length === 0) {
        container.textContent = "（无讨论内容）";
        return;
    }

    let html = "";
    discussions.forEach(d => {
        html += `<div class="discussion-item">
            <div class="discussion-speaker">
                <span class="discussion-round">R${d.round}</span>${escapeHtml(d.speaker)}
            </div>
            <div class="discussion-content">${escapeHtml(d.content)}</div>
        </div>`;
    });

    if (consensus) {
        html += `<div class="discussion-consensus">
            <div class="discussion-consensus-label">讨论共识</div>
            <div class="discussion-consensus-text">${escapeHtml(consensus)}</div>
        </div>`;
    }

    container.innerHTML = html;
}

function renderRisk(data) {
    const badge = document.getElementById("riskBadge");
    badge.textContent = { low: "LOW 低风险", medium: "MEDIUM 中风险", high: "HIGH 高风险" }[data.level] || data.level.toUpperCase();
    badge.className = `risk-badge ${(data.level || "medium").toUpperCase()}`;

    let html = `<div>${simpleMarkdown(data.assessment || "（无评估）")}</div>`;

    if (data.warnings && data.warnings.length > 0) {
        html += `<div class="risk-warnings">`;
        data.warnings.forEach(w => {
            html += `<div class="risk-warning-item">${escapeHtml(w)}</div>`;
        });
        html += `</div>`;
    }

    document.getElementById("riskContent").innerHTML = html;
}

// ===== History =====

async function loadHistory() {
    const container = document.getElementById("historyList");
    container.innerHTML = '<div class="empty-state">加载中...</div>';

    try {
        const resp = await fetch("/api/history");
        const data = await resp.json();

        if (!data.reports || data.reports.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无报告</div>';
            return;
        }

        container.innerHTML = data.reports.map(r => `
            <div class="history-item" onclick="viewReport('${r.filename}')">
                <span class="history-item-name">${escapeHtml(r.filename)}</span>
                <div class="history-item-meta">
                    <span>${r.modified}</span>
                    <span>${r.size_kb} KB</span>
                </div>
            </div>
        `).join("");
    } catch (e) {
        container.innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

async function viewReport(filename) {
    document.getElementById("reportModal").style.display = "flex";
    document.getElementById("modalTitle").textContent = filename;

    try {
        const resp = await fetch(`/api/history/${encodeURIComponent(filename)}`);
        const data = await resp.json();
        document.getElementById("modalBody").innerHTML = simpleMarkdown(data.content);
    } catch (e) {
        document.getElementById("modalBody").textContent = "加载失败";
    }
}

function closeModal() {
    document.getElementById("reportModal").style.display = "none";
}

// ===== Radar (盘口雷达) =====

let radarDates = [];
let radarRunning = false;

async function loadRadarStatus() {
    const badge = document.getElementById("radarDataBadge");
    const info = document.getElementById("radarDataInfo");

    badge.textContent = "检查中...";
    info.textContent = "正在检查数据状态...";

    try {
        const resp = await fetch("/api/radar/status");
        const data = await resp.json();

        if (data.ready) {
            badge.textContent = "就绪";
            badge.className = "radar-status-badge radar-ready";
            info.innerHTML = `<span class="radar-info-item">最新日期: <strong>${data.last_date}</strong></span>`
                + `<span class="radar-info-item">股票数: <strong>${data.stock_count}</strong></span>`
                + `<span class="radar-info-item">记录数: <strong>${data.record_count.toLocaleString()}</strong></span>`;
            radarDates = data.dates || [];

            // 设置日期输入的最大值和默认值
            const dateInput = document.getElementById("radarDateInput");
            if (dateInput && radarDates.length > 0) {
                dateInput.max = radarDates[radarDates.length - 1];
                dateInput.min = radarDates[0];
                dateInput.value = radarDates[radarDates.length - 1];
            }
        } else {
            badge.textContent = "未就绪";
            badge.className = "radar-status-badge radar-not-ready";
            info.innerHTML = `<span class="radar-info-warn">${escapeHtml(data.message)}</span>`;
        }
    } catch (e) {
        badge.textContent = "错误";
        badge.className = "radar-status-badge radar-not-ready";
        info.textContent = "检查数据状态失败";
    }
}

async function startRadarDownload() {
    if (radarRunning) return;
    radarRunning = true;

    const btn = document.getElementById("radarDownloadBtn");
    btn.disabled = true;
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" style="animation: spin 1s linear infinite"><path fill="currentColor" d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg> 下载中...';

    const logEl = document.getElementById("radarDownloadLog");
    logEl.style.display = "block";
    logEl.innerHTML = "";

    try {
        const resp = await fetch("/api/radar/download", { method: "POST" });
        const { task_id } = await resp.json();

        const es = new EventSource(`/api/radar/stream/${task_id}`);
        es.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === "log") {
                appendRadarLog(logEl, msg.message);
            } else if (msg.type === "done") {
                es.close();
                appendRadarLog(logEl, msg.message);
                radarDates = msg.dates || [];

                // 更新状态
                const badge = document.getElementById("radarDataBadge");
                const info = document.getElementById("radarDataInfo");
                badge.textContent = "就绪";
                badge.className = "radar-status-badge radar-ready";
                info.innerHTML = `<span class="radar-info-item">最新日期: <strong>${msg.last_date}</strong></span>`
                    + `<span class="radar-info-item">股票数: <strong>${msg.stock_count}</strong></span>`
                    + `<span class="radar-info-item">记录数: <strong>${msg.record_count.toLocaleString()}</strong></span>`;

                // 更新日期输入
                const dateInput = document.getElementById("radarDateInput");
                if (dateInput && radarDates.length > 0) {
                    dateInput.max = radarDates[radarDates.length - 1];
                    dateInput.min = radarDates[0];
                    dateInput.value = radarDates[radarDates.length - 1];
                }

                resetRadarBtn(btn);
            } else if (msg.type === "error") {
                es.close();
                appendRadarLog(logEl, `错误: ${msg.message}`, true);
                resetRadarBtn(btn);
            }
        };
        es.onerror = () => {
            es.close();
            appendRadarLog(logEl, "连接中断", true);
            resetRadarBtn(btn);
        };
    } catch (e) {
        appendRadarLog(logEl, `启动失败: ${e.message}`, true);
        resetRadarBtn(btn);
    }
}

async function startRadarScreen() {
    if (radarRunning) return;

    const dateInput = document.getElementById("radarDateInput");
    const end_date = dateInput ? dateInput.value : "";
    if (!end_date) {
        alert("请选择基准日期");
        return;
    }

    radarRunning = true;
    const btn = document.getElementById("radarScreenBtn");
    btn.disabled = true;
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" style="animation: spin 1s linear infinite"><path fill="currentColor" d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg> 筛选中...';

    const logEl = document.getElementById("radarScreenLog");
    logEl.style.display = "block";
    logEl.innerHTML = "";

    const resultsEl = document.getElementById("radarResults");
    resultsEl.style.display = "none";
    resultsEl.innerHTML = "";

    try {
        const resp = await fetch("/api/radar/screen", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ end_date }),
        });
        const { task_id } = await resp.json();

        const es = new EventSource(`/api/radar/stream/${task_id}`);
        es.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === "log") {
                appendRadarLog(logEl, msg.message);
            } else if (msg.type === "rule_done") {
                appendRadarLog(logEl, `${msg.rule}: ${msg.count} 只股票`);
            } else if (msg.type === "done") {
                es.close();
                appendRadarLog(logEl, msg.message);
                renderRadarResults(msg.results, msg.base_date);
                resetRadarBtn(btn);
            } else if (msg.type === "error") {
                es.close();
                appendRadarLog(logEl, `错误: ${msg.message}`, true);
                resetRadarBtn(btn);
            }
        };
        es.onerror = () => {
            es.close();
            appendRadarLog(logEl, "连接中断", true);
            resetRadarBtn(btn);
        };
    } catch (e) {
        appendRadarLog(logEl, `启动失败: ${e.message}`, true);
        resetRadarBtn(btn);
    }
}

function appendRadarLog(logEl, message, isError) {
    const line = document.createElement("div");
    line.className = isError ? "radar-log-line radar-log-error" : "radar-log-line";
    line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
}

function resetRadarBtn(btn) {
    radarRunning = false;
    if (btn) {
        btn.disabled = false;
        // 根据按钮类型恢复不同文本
        if (btn.id === "radarDownloadBtn") {
            btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> 下载/更新数据';
        } else if (btn.id === "radarScreenBtn") {
            btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg> 开始筛选';
        }
    }
}

function renderRadarResults(results, baseDate) {
    const container = document.getElementById("radarResults");
    if (!results || results.length === 0) {
        container.style.display = "block";
        container.innerHTML = '<div class="empty-state">无筛选结果</div>';
        return;
    }

    let html = `<div class="radar-results-header">筛选结果（基准日: ${escapeHtml(baseDate)}）</div>`;

    results.forEach((rule, idx) => {
        const countTag = rule.type === "gain" ? `TOP ${rule.hits.length}` : `共 ${rule.hits.length} 只`;
        html += `<section class="result-card post-card collapsed" id="radarRule_${idx}">`;
        html += `<div class="card-header" onclick="toggleCard('radarRule_${idx}')">`;
        html += `<div class="card-header-left">`;
        html += `<svg class="icon" viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>`;
        html += `<h3>${escapeHtml(rule.label)} (${countTag})</h3>`;
        html += `</div>`;
        html += `<div class="card-meta"><svg class="collapse-chevron" viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/></svg></div>`;
        html += `</div>`;
        html += `<div class="card-body-wrapper"><div class="card-body"><div class="radar-table-wrap"><table class="radar-table">`;
        html += `<thead><tr><th>排名</th><th>代码</th><th>名称</th><th>区间涨幅</th><th>起始价</th><th>终止价</th><th>区间</th></tr></thead>`;
        html += `<tbody>`;
        rule.hits.forEach((h, rank) => {
            const gainClass = h.gain >= 0 ? "radar-gain-up" : "radar-gain-down";
            html += `<tr>`;
            html += `<td>${rank + 1}</td>`;
            html += `<td class="radar-code">${escapeHtml(h.code)}</td>`;
            html += `<td>${escapeHtml(h.name)}</td>`;
            html += `<td class="${gainClass}">${(h.gain * 100).toFixed(2)}%</td>`;
            html += `<td>${h.start_price.toFixed(2)}</td>`;
            html += `<td>${h.end_price.toFixed(2)}</td>`;
            html += `<td class="radar-date-cell">${h.start_date} ~ ${h.end_date}</td>`;
            html += `</tr>`;
        });
        html += `</tbody></table></div></div></div></section>`;
    });

    container.innerHTML = html;
    container.style.display = "block";
}

// ===== Posts (Blogger Posts) - Collapsible =====

async function loadPosts() {
    const container = document.getElementById("postsList");
    container.innerHTML = '<div class="empty-state">加载中...</div>';

    try {
        const resp = await fetch("/api/posts");
        const data = await resp.json();

        if (!data.posts || data.posts.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无帖子</div>';
            return;
        }

        container.innerHTML = data.posts.map((p, index) => {
            // 提取博主名和时间：博主名_YYYYMMDD_HHMMSS.md
            const match = p.filename.match(/^(.+?)_(\d{8})_(\d{6})\.md$/);
            let displayName = p.filename;
            let timeStr = "";
            
            if (match) {
                const bloggerName = match[1];
                const dateStr = match[2];
                const time = match[3];
                // 格式化为 YYYY-MM-DD HH:MM:SS
                timeStr = `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)} ${time.slice(0, 2)}:${time.slice(2, 4)}:${time.slice(4, 6)}`;
                displayName = bloggerName;
                console.log(`文件: ${p.filename} -> 博主: ${bloggerName}, 时间: ${timeStr}`);
            } else {
                console.log(`文件不匹配格式: ${p.filename}`);
            }
            
            return `
            <section class="result-card post-card collapsed" id="postCard_${index}" data-filename="${escapeHtml(p.filename)}">
                <div class="card-header" onclick="togglePostCard(${index})">
                    <div class="card-header-left">
                        <svg class="icon" viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
                        <h3>${escapeHtml(displayName)}</h3>
                    </div>
                    <div class="card-meta">
                        <span class="card-time">${timeStr || p.modified}</span>
                        <span class="card-time">${p.size_kb} KB</span>
                        <button class="post-delete-btn" onclick="event.stopPropagation(); deletePost(${index})" title="删除">
                            <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                        </button>
                        <svg class="collapse-chevron" viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/></svg>
                    </div>
                </div>
                <div class="card-body-wrapper">
                    <div class="card-body post-content-body" id="postBody_${index}"></div>
                </div>
            </section>`;
        }).join("");
    } catch (e) {
        container.innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

function togglePostCard(index) {
    const card = document.getElementById(`postCard_${index}`);
    const body = document.getElementById(`postBody_${index}`);
    const filename = card.dataset.filename;

    if (card.classList.contains("collapsed")) {
        // 展开：如果内容为空则先加载
        if (!body.dataset.loaded) {
            body.innerHTML = '<div class="post-loading">加载中...</div>';
            fetch(`/api/posts/${encodeURIComponent(filename)}`)
                .then(resp => resp.json())
                .then(data => {
                    body.innerHTML = simpleMarkdown(data.content);
                    body.dataset.loaded = "true";
                    card.classList.remove("collapsed");
                })
                .catch(() => {
                    body.innerHTML = '<span style="color: var(--red);">加载失败</span>';
                });
        } else {
            card.classList.remove("collapsed");
        }
    } else {
        card.classList.add("collapsed");
    }
}

async function deletePost(index) {
    const card = document.getElementById(`postCard_${index}`);
    const filename = card.dataset.filename;
    if (!confirm(`确认删除「${filename}」？`)) return;

    try {
        const resp = await fetch(`/api/posts/${encodeURIComponent(filename)}`, { method: "DELETE" });
        if (!resp.ok) {
            const err = await resp.json();
            alert(err.error || "删除失败");
            return;
        }
        card.style.transition = "opacity 0.3s, max-height 0.3s";
        card.style.opacity = "0";
        card.style.maxHeight = "0";
        card.style.marginBottom = "0";
        card.style.overflow = "hidden";
        setTimeout(() => card.remove(), 300);
    } catch (e) {
        alert("删除失败: " + e.message);
    }
}

const CRAWL_BLOGGERS = [
    { username: "jl韭菜抄家", user_id: "7737030" },
    { username: "延边刺客", user_id: "5894557" },
    { username: "主升龙头真经", user_id: "2776047" },
    { username: "小宝1105", user_id: "9239701" },
    { username: "短狙作手", user_id: "8423616" },
    { username: "小土堆爆金币", user_id: "9259508" },
    { username: "涅槃重生2018", user_id: "2888425" },
    { username: "米开朗基瑞", user_id: "11056656" },
];

let _crawlerUIInitialized = false;

function initCrawlerUI() {
    if (_crawlerUIInitialized) return;
    _crawlerUIInitialized = true;

    const container = document.getElementById("crawlerBloggers");
    container.innerHTML = CRAWL_BLOGGERS.map((b, i) => {
        return `<span class="crawler-blogger-tag" data-index="${i}" onclick="toggleBloggerTag(this)">${escapeHtml(b.username)}</span>`;
    }).join("");

    // Set default dates: last 3 days
    const today = new Date();
    const threeDaysAgo = new Date(today);
    threeDaysAgo.setDate(today.getDate() - 3);
    document.getElementById("crawlerEndDate").value = formatDateISO(today);
    document.getElementById("crawlerStartDate").value = formatDateISO(threeDaysAgo);
}

function formatDateISO(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
}

function toggleBloggerTag(el) {
    el.classList.toggle("selected");
}

function getSelectedBloggers() {
    const tags = document.querySelectorAll("#crawlerBloggers .crawler-blogger-tag.selected");
    return Array.from(tags).map(t => CRAWL_BLOGGERS[parseInt(t.dataset.index)]);
}

async function startCrawl() {
    const bloggers = getSelectedBloggers();
    if (bloggers.length === 0) {
        alert("请至少选择一个博主");
        return;
    }

    const startDate = document.getElementById("crawlerStartDate").value;
    const endDate = document.getElementById("crawlerEndDate").value;
    if (!startDate || !endDate) {
        alert("请选择日期范围");
        return;
    }
    if (startDate > endDate) {
        alert("开始日期不能晚于结束日期");
        return;
    }

    const maxPosts = parseInt(document.getElementById("crawlerMaxPosts").value) || 100;
    const maxComments = parseInt(document.getElementById("crawlerMaxComments").value) || 0;

    const btn = document.getElementById("crawlerBtn");
    const logEl = document.getElementById("crawlerLog");
    logEl.style.display = "block";
    logEl.innerHTML = "";
    btn.disabled = true;
    btn.style.opacity = "0.6";

    try {
        const resp = await fetch("/api/crawl/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                bloggers,
                start_date: startDate,
                end_date: endDate,
                max_posts: maxPosts,
                max_comments: maxComments,
            }),
        });
        const data = await resp.json();
        if (data.error) {
            appendCrawlerLog(logEl, data.error, true);
            resetCrawlerBtn(btn);
            return;
        }

        const es = new EventSource(`/api/crawl/stream/${data.task_id}`);
        es.onmessage = function(evt) {
            const msg = JSON.parse(evt.data);
            if (msg.type === "log") {
                appendCrawlerLog(logEl, msg.message, false);
            } else if (msg.type === "done") {
                es.close();
                appendCrawlerLog(logEl, msg.message, false);
                resetCrawlerBtn(btn);
                // Refresh posts list
                loadPosts();
            } else if (msg.type === "error") {
                es.close();
                appendCrawlerLog(logEl, msg.message, true);
                resetCrawlerBtn(btn);
            }
        };
        es.onerror = function() {
            es.close();
            appendCrawlerLog(logEl, "连接中断", true);
            resetCrawlerBtn(btn);
        };
    } catch (e) {
        appendCrawlerLog(logEl, "请求失败: " + e.message, true);
        resetCrawlerBtn(btn);
    }
}

function appendCrawlerLog(logEl, message, isError) {
    const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const line = document.createElement("div");
    line.className = isError ? "radar-log-line radar-log-error" : "radar-log-line";
    line.textContent = `[${time}] ${message}`;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
}

function resetCrawlerBtn(btn) {
    btn.disabled = false;
    btn.style.opacity = "1";
}

// ===== News Input Config (资讯配置) =====

async function loadNewsInputFiles() {
    const container = document.getElementById("newsManageList");
    const countEl = document.getElementById("newsInputCount");
    if (!container) return;

    try {
        const resp = await fetch("/api/news_input");
        const data = await resp.json();
        const files = data.files || [];
        countEl.textContent = `${files.length} 个文件`;

        if (files.length === 0) {
            container.innerHTML = '<div class="empty-state" style="padding:20px;">暂无资讯文件，请手动输入或从帖子导入</div>';
            return;
        }

        container.innerHTML = files.map(f => `
            <div class="news-manage-item">
                <div class="news-manage-info">
                    <span class="news-manage-name">${escapeHtml(f.filename)}</span>
                    <span class="news-manage-meta">${f.modified} | ${f.size_kb} KB</span>
                </div>
                <button class="news-manage-delete" onclick="deleteNewsInput('${escapeHtml(f.filename)}')" title="删除">
                    <svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                </button>
            </div>
        `).join("");
    } catch (e) {
        container.innerHTML = '<div class="empty-state" style="padding:20px;">加载失败</div>';
    }
}

async function deleteNewsInput(filename) {
    if (!confirm(`确认删除「${filename}」？`)) return;
    try {
        const resp = await fetch(`/api/news_input/${encodeURIComponent(filename)}`, { method: "DELETE" });
        if (!resp.ok) {
            const err = await resp.json();
            alert(err.error || "删除失败");
            return;
        }
        loadNewsInputFiles();
    } catch (e) {
        alert("删除失败: " + e.message);
    }
}

async function saveNewsInput() {
    const content = document.getElementById("newsInputTextarea").value.trim();
    const filename = document.getElementById("newsInputFilename").value.trim();
    if (!content) {
        alert("请输入资讯内容");
        return;
    }

    try {
        const resp = await fetch("/api/news_input/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content, filename }),
        });
        const data = await resp.json();
        if (data.error) {
            alert(data.error);
            return;
        }
        document.getElementById("newsInputTextarea").value = "";
        document.getElementById("newsInputFilename").value = "";
        alert(`已保存: ${data.saved}`);
        loadNewsInputFiles();
    } catch (e) {
        alert("保存失败: " + e.message);
    }
}

async function loadNewsTxtList() {
    const container = document.getElementById("newsImportList");
    if (!container) return;

    try {
        const resp = await fetch("/api/news/news_txt_list");
        const data = await resp.json();
        const files = data.files || [];

        if (files.length === 0) {
            container.innerHTML = '<div class="empty-state" style="padding:20px;">output/news/ 下无 txt 文件</div>';
            return;
        }

        container.innerHTML = files.map(f => `
            <label class="news-import-item">
                <input type="checkbox" value="${escapeHtml(f.filename)}" class="news-import-checkbox">
                <span class="news-import-name">${escapeHtml(f.filename)}</span>
                <span class="news-import-meta">${f.modified} | ${f.size_kb} KB</span>
            </label>
        `).join("");
    } catch (e) {
        container.innerHTML = '<div class="empty-state" style="padding:20px;">加载失败</div>';
    }
}

async function importSelectedNews() {
    const checkboxes = document.querySelectorAll("#newsImportList .news-import-checkbox:checked");
    if (checkboxes.length === 0) {
        alert("请至少选择一个文件");
        return;
    }
    const filenames = Array.from(checkboxes).map(cb => cb.value);

    const btn = document.getElementById("newsImportBtn");
    btn.disabled = true;
    btn.style.opacity = "0.6";

    try {
        const resp = await fetch("/api/news_input/import_from_news", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filenames }),
        });
        const data = await resp.json();

        if (data.errors && data.errors.length > 0) {
            alert("部分文件导入失败:\n" + data.errors.join("\n"));
        }
        if (data.imported && data.imported.length > 0) {
            alert(`成功导入 ${data.imported.length} 个文件`);
        }

        // Refresh both lists
        loadNewsInputFiles();
        loadNewsTxtList();
    } catch (e) {
        alert("导入失败: " + e.message);
    } finally {
        btn.disabled = false;
        btn.style.opacity = "1";
    }
}

function switchNewsConfigTab(tab, el) {
    document.querySelectorAll(".news-config-tab").forEach(t => t.classList.remove("active"));
    if (el) el.classList.add("active");

    document.querySelectorAll(".news-config-panel").forEach(p => p.classList.remove("active"));
    const panelMap = { input: "newsPanelInput", import: "newsPanelImport", manage: "newsPanelManage", generate: "newsPanelGenerate" };
    const panel = document.getElementById(panelMap[tab]);
    if (panel) panel.classList.add("active");
}

async function generateNews() {
    const topic = document.getElementById("newsGenTopic").value.trim();
    const btn = document.getElementById("newsGenBtn");
    const loading = document.getElementById("newsGenLoading");
    const result = document.getElementById("newsGenResult");
    const output = document.getElementById("newsGenOutput");

    btn.disabled = true;
    btn.style.opacity = "0.6";
    loading.style.display = "flex";
    result.style.display = "none";
    output.value = "";

    try {
        const resp = await fetch("/api/news/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ topic }),
        });
        const data = await resp.json();

        if (data.error) {
            alert("生成失败: " + data.error);
            return;
        }

        output.value = data.content || "";
        result.style.display = "block";
    } catch (e) {
        alert("生成失败: " + e.message);
    } finally {
        btn.disabled = false;
        btn.style.opacity = "1";
        loading.style.display = "none";
    }
}

function copyGenNews() {
    const output = document.getElementById("newsGenOutput");
    navigator.clipboard.writeText(output.value).then(() => {
        const btn = event.target.closest("button");
        const origText = btn.innerHTML;
        btn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/></svg> 已复制';
        setTimeout(() => { btn.innerHTML = origText; }, 1500);
    });
}

async function saveGenNews() {
    const content = document.getElementById("newsGenOutput").value.trim();
    if (!content) { alert("没有可保存的内容"); return; }

    try {
        const resp = await fetch("/api/news_input/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content, filename: "" }),
        });
        const data = await resp.json();
        if (data.error) { alert(data.error); return; }
        alert("已保存: " + data.saved);
        loadNewsInputFiles();
    } catch (e) {
        alert("保存失败: " + e.message);
    }
}

// ===== Hot Stocks (人气热股) =====

let hotStocksCache = null;
let dashHotCurrentSource = "dc";
let hotCurrentSource = "dc";

async function fetchHotStocksData() {
    if (hotStocksCache) return hotStocksCache;
    try {
        const resp = await fetch("/api/hot_stocks");
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || "获取失败");
        hotStocksCache = data;
        return data;
    } catch (e) {
        console.error("Failed to fetch hot stocks:", e);
        return null;
    }
}

// ---------- 仪表盘精简版 ----------

async function loadDashHotStocks(source) {
    dashHotCurrentSource = source;
    const container = document.getElementById("dashHotContent");
    if (!container) return;
    container.innerHTML = '<div class="empty-state" style="padding:20px;">加载中...</div>';

    const data = await fetchHotStocksData();
    if (!data) {
        container.innerHTML = '<div class="empty-state" style="padding:20px; color:var(--color-danger);">获取失败</div>';
        return;
    }

    const stocks = (data[source] || []).slice(0, 5);
    if (stocks.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding:20px;">暂无数据</div>';
        return;
    }

    let html = '<div class="dash-hot-list">';
    stocks.forEach((s, i) => {
        const change = s.pct_change != null ? parseFloat(s.pct_change) : null;
        const changeClass = change == null ? "" : (change >= 0 ? "color-up" : "color-down");
        const changeStr = change == null ? "--" : (change >= 0 ? "+" : "") + change.toFixed(2) + "%";

        html += `<div class="dash-hot-item" onclick="switchTab('hot')">
            <span class="dash-hot-rank ${i < 3 ? 'rank-top' : ''}">${i + 1}</span>
            <span class="dash-hot-name">${escapeHtml(s.ts_name || "--")}</span>
            <span class="dash-hot-code">${escapeHtml(s.ts_code || "")}</span>
            <span class="dash-hot-change ${changeClass}">${changeStr}</span>
        </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
}

function switchDashHotTab(source, el) {
    document.querySelectorAll(".hot-overview-tabs .hot-tab").forEach(b => b.classList.remove("active"));
    if (el) el.classList.add("active");
    loadDashHotStocks(source);
}

// ---------- 独立页面（丰富版） ----------

async function loadHotStocksPage() {
    const loadingEl = document.getElementById("hotLoadingState");
    const errorEl = document.getElementById("hotErrorState");
    const tableEl = document.getElementById("hotTableContent");

    // 如果已有缓存，直接渲染（仪表盘已加载过的场景）
    if (hotStocksCache) {
        loadingEl.style.display = "none";
        errorEl.style.display = "none";
        tableEl.style.display = "block";
        renderHotTable(hotCurrentSource);
        return;
    }

    // 无缓存时从后端获取（后端也有 5 分钟缓存）
    await _fetchHotStocksPage();
}

async function refreshHotStocks() {
    // 强制刷新：清除前端缓存，请求时带 force=1
    hotStocksCache = null;
    await _fetchHotStocksPage(true);
}

async function _fetchHotStocksPage(force = false) {
    const loadingEl = document.getElementById("hotLoadingState");
    const errorEl = document.getElementById("hotErrorState");
    const tableEl = document.getElementById("hotTableContent");

    loadingEl.style.display = "block";
    errorEl.style.display = "none";
    tableEl.style.display = "none";

    const btn = document.getElementById("hotRefreshBtn");
    if (btn) { btn.disabled = true; btn.style.opacity = "0.6"; }

    try {
        const resp = await fetch("/api/hot_stocks" + (force ? "?force=1" : ""));
        const data = await resp.json();

        if (!data.success) throw new Error(data.error || "获取失败");

        hotStocksCache = data;

        // 更新时间
        const timeEl = document.getElementById("hotUpdateTime");
        if (timeEl) {
            timeEl.textContent = "更新于 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
        }

        loadingEl.style.display = "none";
        tableEl.style.display = "block";

        renderHotTable(hotCurrentSource);
    } catch (e) {
        loadingEl.style.display = "none";
        errorEl.style.display = "block";
        const msgEl = document.getElementById("hotErrorMsg");
        if (msgEl) msgEl.textContent = "获取数据失败: " + e.message;
    } finally {
        if (btn) { btn.disabled = false; btn.style.opacity = "1"; }
    }
}

function switchHotTab(source, el) {
    hotCurrentSource = source;
    document.querySelectorAll("#tab-hot .hot-tabs .hot-tab").forEach(b => b.classList.remove("active"));
    if (el) el.classList.add("active");
    renderHotTable(source);
}

function renderHotTable(source) {
    if (!hotStocksCache) return;

    const data = hotStocksCache[source] || [];
    const thead = document.getElementById("hotTableHead");
    const tbody = document.getElementById("hotTableBody");

    // 根据数据源构建不同表头
    if (source === "dc") {
        thead.innerHTML = `<tr>
            <th>排名</th><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th>
        </tr>`;
    } else if (source === "ths") {
        thead.innerHTML = `<tr>
            <th>排名</th><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>热度值</th><th>排名变动</th><th>概念标签</th><th>热度标签</th>
        </tr>`;
    } else {
        thead.innerHTML = `<tr>
            <th>排名</th><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>东财排名</th><th>同花顺排名</th><th>热度值</th>
        </tr>`;
    }

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--el-text-color-placeholder); padding:40px;">暂无数据</td></tr>';
        return;
    }

    let html = "";
    data.forEach((s, i) => {
        const change = s.pct_change != null ? parseFloat(s.pct_change) : null;
        const changeClass = change == null ? "" : (change >= 0 ? "hot-change-up" : "hot-change-down");
        const changeStr = change == null ? "--" : (change >= 0 ? "+" : "") + change.toFixed(2) + "%";
        const price = s.price != null ? parseFloat(s.price).toFixed(2) : "--";

        html += `<tr>`;
        html += `<td>${i + 1}</td>`;
        html += `<td class="hot-code">${escapeHtml(s.ts_code || "--")}</td>`;
        html += `<td><strong>${escapeHtml(s.ts_name || "--")}</strong></td>`;
        html += `<td>${price}</td>`;
        html += `<td class="${changeClass}">${changeStr}</td>`;

        if (source === "dc") {
            html += `</tr>`;
        } else if (source === "ths") {
            html += `<td>${s.hot_value != null ? Number(s.hot_value).toLocaleString() : "--"}</td>`;
            // 排名变动
            const chg = s.rank_change;
            let chgStr = "--";
            if (chg != null) {
                if (chg > 0) { chgStr = `<span style="color:var(--color-danger);">&#9650; +${chg}</span>`; }
                else if (chg < 0) { chgStr = `<span style="color:var(--color-success);">&#9660; ${chg}</span>`; }
                else { chgStr = `<span style="color:var(--el-text-color-secondary);">--</span>`; }
            }
            html += `<td>${chgStr}</td>`;
            // 概念标签
            const concepts = s.concepts || [];
            html += `<td class="hot-tag-cell">${concepts.length > 0 ? concepts.map(c => escapeHtml(c)).join(", ") : ""}</td>`;
            // 热度标签
            html += `<td class="hot-tag-cell">${s.popularity_tag ? escapeHtml(s.popularity_tag) : ""}</td>`;
            html += `</tr>`;
        } else {
            html += `<td>${s.dc_rank != null ? s.dc_rank : "--"}</td>`;
            html += `<td>${s.ths_rank != null ? s.ths_rank : "--"}</td>`;
            html += `<td>${s.ths_hot_value != null ? Number(s.ths_hot_value).toLocaleString() : "--"}</td>`;
            html += `</tr>`;
        }
    });

    tbody.innerHTML = html;
}

// ===== Settings (设置) =====

let _settingsData = null;

function openSettingsModal() {
    document.getElementById("settingsModal").style.display = "flex";
    loadSettings();
}

function closeSettingsModal() {
    document.getElementById("settingsModal").style.display = "none";
}

async function loadSettings() {
    const container = document.getElementById("settingsContent");
    container.innerHTML = '<div class="empty-state" style="padding:20px;">加载中...</div>';

    try {
        const resp = await fetch("/api/settings");
        const data = await resp.json();

        if (data.error) {
            container.innerHTML = `<div class="empty-state" style="padding:20px; color:var(--color-danger);">${escapeHtml(data.error)}</div>`;
            return;
        }

        _settingsData = data;
        renderSettings(data);
    } catch (e) {
        container.innerHTML = '<div class="empty-state" style="padding:20px; color:var(--color-danger);">加载失败</div>';
    }
}

function renderSettings(data) {
    const container = document.getElementById("settingsContent");
    const providers = data.providers || [];

    // 分离默认 LLM 和各提供商
    const defaultItem = providers.find(p => p.type === "select");
    const providerItems = providers.filter(p => p.type === "provider");

    let html = "";

    // 默认 LLM 选择
    if (defaultItem) {
        const options = (defaultItem.options || []).map(opt =>
            `<option value="${opt}" ${opt === defaultItem.value ? 'selected' : ''}>${opt}</option>`
        ).join("");

        html += `<div class="settings-default-row">
            <label>${escapeHtml(defaultItem.label)}</label>
            <select data-settings-key="${escapeHtml(defaultItem.key)}" data-settings-type="select">${options}</select>
        </div>`;
    }

    // Provider 列表
    html += '<div class="settings-provider-list">';
    providerItems.forEach(p => {
        const statusClass = p.has_key ? "active" : "inactive";
        const statusText = p.has_key ? "已配置" : "未配置";

        html += `<div class="settings-provider-item">
            <span class="settings-provider-name">${escapeHtml(p.label)}</span>
            <span class="settings-provider-status ${statusClass}">${statusText}</span>
            <div class="settings-provider-inputs">
                <div class="settings-input-group">
                    <label>API Key</label>
                    <input type="password"
                        data-settings-key="${escapeHtml(p.key)}"
                        data-settings-type="api_key"
                        data-provider="${escapeHtml(p.provider_name || '')}"
                        placeholder="输入 API Key"
                        value="${escapeHtml(p.api_key || '')}">
                </div>
                <div class="settings-input-group">
                    <label>模型</label>
                    <input type="text"
                        data-settings-key="${escapeHtml(p.model_key)}"
                        data-settings-type="model"
                        data-provider="${escapeHtml(p.provider_name || '')}"
                        placeholder="模型名称"
                        value="${escapeHtml(p.model_value || '')}">
                </div>
            </div>
        </div>`;
    });
    html += '</div>';

    container.innerHTML = html;
}

async function saveSettings() {
    if (!_settingsData) return;

    const btn = document.getElementById("settingsSaveBtn");
    btn.disabled = true;
    btn.style.opacity = "0.6";
    btn.textContent = "保存中...";

    try {
        // 收集所有设置项
        const providers = [];

        // 收集默认 LLM
        const selectEl = document.querySelector("[data-settings-type='select']");
        if (selectEl) {
            providers.push({
                key: selectEl.dataset.settingsKey,
                type: "select",
                value: selectEl.value,
            });
        }

        // 收集各 provider
        document.querySelectorAll("[data-settings-type='api_key']").forEach(input => {
            const providerName = input.dataset.provider;
            const modelInput = document.querySelector(`[data-settings-type='model'][data-provider="${providerName}"]`);

            providers.push({
                key: input.dataset.settingsKey,
                type: "provider",
                provider_name: providerName,
                api_key: input.value,
                model_key: modelInput ? modelInput.dataset.settingsKey : "",
                model_value: modelInput ? modelInput.value : "",
            });
        });

        const resp = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ providers }),
        });
        const data = await resp.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        alert("配置已保存");

        // 刷新侧边栏 LLM 状态和仪表盘状态
        loadConfig();
        loadDashboardStatus();

        closeSettingsModal();
    } catch (e) {
        alert("保存失败: " + e.message);
    } finally {
        btn.disabled = false;
        btn.style.opacity = "1";
        btn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/></svg> 保存配置';
    }
}

// ===== Persona Management (博主人格管理) =====

let _personasList = null;
let _editingPersonaName = null;
let _generatedPersonaPrompt = null;

// ---------- 查看人格弹窗 ----------
function openPersonasModal() {
    document.getElementById("personasModal").style.display = "flex";
    loadPersonasDetail();
}

function closePersonasModal() {
    document.getElementById("personasModal").style.display = "none";
}

async function loadPersonasDetail() {
    const container = document.getElementById("personasModalBody");
    container.innerHTML = '<div class="empty-state" style="padding:20px;">加载中...</div>';

    try {
        const resp = await fetch("/api/personas/detail");
        const data = await resp.json();

        if (data.error) {
            container.innerHTML = `<div class="empty-state" style="padding:20px; color:var(--color-danger);">${escapeHtml(data.error)}</div>`;
            return;
        }

        _personasList = data.personas || [];

        if (_personasList.length === 0) {
            container.innerHTML = '<div class="empty-state" style="padding:20px;">暂无人格配置</div>';
            return;
        }

        let html = "";
        _personasList.forEach(p => {
            html += `<div class="persona-card">
                <div class="persona-card-header">
                    <span class="persona-card-name">
                        ${escapeHtml(p.name)}
                        <span class="persona-card-badge">${p.prompt.length} 字</span>
                    </span>
                </div>
                <div class="persona-card-summary">${escapeHtml(p.summary || "暂无简介")}</div>
                <div class="persona-card-prompt">${escapeHtml(p.prompt)}</div>
            </div>`;
        });

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="empty-state" style="padding:20px; color:var(--color-danger);">加载失败</div>';
    }
}

// ---------- 配置人格弹窗 ----------
function openPersonaEditor() {
    document.getElementById("personaEditorModal").style.display = "flex";
    document.getElementById("personaEditorForm").style.display = "none";
    document.getElementById("personaEditorList").style.display = "block";
    loadPersonaEditorList();
}

function closePersonaEditor() {
    document.getElementById("personaEditorModal").style.display = "none";
    _editingPersonaName = null;
}

async function loadPersonaEditorList() {
    const container = document.getElementById("personaEditorList");
    container.innerHTML = '<div class="empty-state" style="padding:20px;">加载中...</div>';

    try {
        const resp = await fetch("/api/personas/detail");
        const data = await resp.json();
        _personasList = data.personas || [];

        if (_personasList.length === 0) {
            container.innerHTML = '<div class="empty-state" style="padding:20px;">暂无人格，点击"新建人格"创建</div>';
            return;
        }

        let html = "";
        _personasList.forEach(p => {
            html += `<div class="persona-editor-item" onclick="editPersona('${escapeHtml(p.name)}')">
                <span class="persona-editor-item-name">${escapeHtml(p.name)}</span>
                <div class="persona-editor-item-actions" onclick="event.stopPropagation()">
                    <button onclick="editPersona('${escapeHtml(p.name)}')">编辑</button>
                    <button class="btn-delete" onclick="confirmDeletePersona('${escapeHtml(p.name)}')">删除</button>
                </div>
            </div>`;
        });

        // 添加新建按钮
        html += `<div class="persona-editor-item" style="justify-content:center; border:1px dashed var(--el-border-color); background:transparent;" onclick="createNewPersona()">
            <span style="color:var(--brand-primary);">+ 新建人格</span>
        </div>`;

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="empty-state" style="padding:20px; color:var(--color-danger);">加载失败</div>';
    }
}

function createNewPersona() {
    _editingPersonaName = null;
    document.getElementById("personaEditorTitle").textContent = "新建人格";
    document.getElementById("personaNameInput").value = "";
    document.getElementById("personaPromptInput").value = "";
    document.getElementById("personaNameInput").disabled = false;
    document.getElementById("personaDeleteBtn").style.display = "none";
    document.getElementById("personaEditorList").style.display = "none";
    document.getElementById("personaEditorForm").style.display = "block";
}

function editPersona(name) {
    const persona = _personasList.find(p => p.name === name);
    if (!persona) return;

    _editingPersonaName = name;
    document.getElementById("personaEditorTitle").textContent = "编辑人格: " + name;
    document.getElementById("personaNameInput").value = name;
    document.getElementById("personaPromptInput").value = persona.prompt;
    document.getElementById("personaNameInput").disabled = true;
    document.getElementById("personaDeleteBtn").style.display = "inline-block";
    document.getElementById("personaEditorList").style.display = "none";
    document.getElementById("personaEditorForm").style.display = "block";
}

function cancelPersonaEdit() {
    document.getElementById("personaEditorForm").style.display = "none";
    document.getElementById("personaEditorList").style.display = "block";
    _editingPersonaName = null;
}

async function savePersona() {
    const name = (document.getElementById("personaNameInput").value || "").trim();
    const prompt = (document.getElementById("personaPromptInput").value || "").trim();

    if (!name) {
        alert("请输入人格名称");
        return;
    }
    if (!prompt) {
        alert("请输入人格 Prompt");
        return;
    }

    try {
        const resp = await fetch(`/api/personas/${encodeURIComponent(name)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt }),
        });
        const data = await resp.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        alert(data.message || "保存成功");
        loadPersonas(); // 刷新博主标签列表
        cancelPersonaEdit();
        loadPersonaEditorList();
    } catch (e) {
        alert("保存失败: " + e.message);
    }
}

function confirmDeletePersona(name) {
    if (!confirm(`确定要删除人格 "${name}" 吗？此操作不可恢复。`)) return;
    deletePersonaByName(name);
}

async function deletePersonaByName(name) {
    try {
        const resp = await fetch(`/api/personas/${encodeURIComponent(name)}`, {
            method: "DELETE",
        });
        const data = await resp.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        alert(data.message || "删除成功");
        loadPersonas();
        loadPersonaEditorList();
    } catch (e) {
        alert("删除失败: " + e.message);
    }
}

async function deletePersona() {
    if (!_editingPersonaName) return;
    confirmDeletePersona(_editingPersonaName);
}

// ---------- LLM 生成人格弹窗 ----------
function openPersonaGenerator() {
    document.getElementById("personaGeneratorModal").style.display = "flex";
    document.getElementById("personaConceptInput").value = "";
    document.getElementById("generatedPromptPreview").style.display = "none";
    document.getElementById("regenerateBtn").style.display = "none";
    document.getElementById("saveGeneratedBtn").style.display = "none";
    document.getElementById("generatePersonaBtn").style.display = "inline-flex";
    document.getElementById("generatedPersonaName").value = "";
    _generatedPersonaPrompt = null;
}

function closePersonaGenerator() {
    document.getElementById("personaGeneratorModal").style.display = "none";
}

async function generatePersona() {
    const concept = (document.getElementById("personaConceptInput").value || "").trim();

    if (!concept) {
        alert("请输入人格概念描述");
        return;
    }

    const btn = document.getElementById("generatePersonaBtn");
    btn.disabled = true;
    btn.textContent = "生成中...";

    try {
        const resp = await fetch("/api/personas/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ concept }),
        });
        const data = await resp.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        _generatedPersonaPrompt = data.prompt;
        document.getElementById("generatedPromptOutput").value = data.prompt;
        document.getElementById("generatedPromptPreview").style.display = "block";
        document.getElementById("regenerateBtn").style.display = "inline-flex";
        document.getElementById("saveGeneratedBtn").style.display = "inline-flex";
        document.getElementById("generatePersonaBtn").style.display = "none";
    } catch (e) {
        alert("生成失败: " + e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> 生成';
    }
}

function regeneratePersona() {
    document.getElementById("generatePersonaBtn").style.display = "inline-flex";
    document.getElementById("regenerateBtn").style.display = "none";
    document.getElementById("saveGeneratedBtn").style.display = "none";
    document.getElementById("generatedPromptPreview").style.display = "none";
    generatePersona();
}

async function saveGeneratedPersona() {
    const name = (document.getElementById("generatedPersonaName").value || "").trim();
    const prompt = _generatedPersonaPrompt;

    if (!name) {
        alert("请输入人格名称");
        return;
    }
    if (!prompt) {
        alert("没有生成的内容");
        return;
    }

    try {
        const resp = await fetch(`/api/personas/${encodeURIComponent(name)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt }),
        });
        const data = await resp.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        alert(data.message || "保存成功");
        loadPersonas();
        closePersonaGenerator();
    } catch (e) {
        alert("保存失败: " + e.message);
    }
}

// ===== Simple Markdown Renderer =====

function simpleMarkdown(text) {
    return text
        .replace(/^### (.+)$/gm, "<h3>$1</h3>")
        .replace(/^## (.+)$/gm, "<h2>$1</h2>")
        .replace(/^# (.+)$/gm, "<h1>$1</h1>")
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/^---$/gm, "<hr>")
        .replace(/^- (.+)$/gm, "<li>$1</li>")
        .replace(/\n\n/g, "<br><br>")
        .replace(/\n/g, "<br>");
}

// ===== Utilities =====

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function resetUI() {
    isRunning = false;
    const runBtn = document.getElementById("runBtn");
    runBtn.disabled = false;
    runBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M8 5v14l11-7z"/></svg> 开始分析';
}

// Keyboard shortcut: Ctrl+Enter to submit
document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.ctrlKey) {
        startAnalysis();
    }
});
