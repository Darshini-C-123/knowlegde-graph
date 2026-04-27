/**
 * Knowledge Graph Swarm — dashboard + graph + logs + all panels
 *
 * Features:
 *  - Agent Panel: highlight active agent, show status (idle/running/done)
 *  - State Panel: current state + transition history with timestamps
 *  - Interaction Panel: structured agent messages with timestamps + agent badges
 *  - Metrics Dashboard: nodes, edges, accuracy, duplicates, density, avg degree
 *  - Run Controls: Start / Stop / Reset / Seed
 *  - Run ID badge
 *  - Graph Growth Metrics: cumulative chart across runs
 *  - Run History & Replay
 */
(function () {
  const STORAGE_KEY = "kg_swarm_use_agents";
  const AGENT_NAMES = ["Extractor", "Validator", "Deduplicator", "Curator", "Evaluator"];

  const STATE_ORDER = [
    "INIT",
    "EXTRACTING",
    "VALIDATING",
    "DEDUPLICATING",
    "CURATING",
    "EVALUATING",
    "COMPLETED",
  ];

  
  function typeColor(type) {
    const t = (type || "").toLowerCase();
    if (t === "person") return "#3b82f6";
    if (t === "organization") return "#a855f7";
    if (t === "location") return "#22c55e";
    if (t === "event") return "#eab308";
    return "#64748b";
  }

  function graphToVisData(graph) {
    if (!graph || !graph.nodes) {
      return { nodes: [], edges: [] };
    }
    const degree = {};
    (graph.edges || []).forEach((e) => {
      degree[e.source] = (degree[e.source] || 0) + 1;
      degree[e.target] = (degree[e.target] || 0) + 1;
    });
    const nodes = graph.nodes.map((n) => {
      const d = degree[n.id] || 0;
      const size = Math.max(14, Math.min(32, 18 + d * 2));
      return {
        id: n.id,
        label: n.name,
        title: `${n.name}\n${n.type}`,
        color: { background: typeColor(n.type), border: "#1e293b" },
        font: { color: "#f8fafc" },
        value: d,
        size,
        type: n.type,
      };
    });
    const edges = (graph.edges || []).map((e, i) => ({
      id: "e" + i,
      from: e.source,
      to: e.target,
      label: e.relation || "",
      arrows: "to",
      font: { align: "middle", color: "#cbd5e1", size: 11 },
      color: { color: "rgba(148,163,184,0.6)" },
    }));
    return { nodes, edges };
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function shortTs(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return isoStr.slice(11, 19);
    }
  }

  // ── Metrics ──────────────────────────────────────────────────────────────

  function updateMetrics(elPrefix, metrics) {
    if (!metrics) return;
    const set = (id, val) => {
      const el = document.getElementById(elPrefix + id);
      if (el) el.textContent = val != null ? String(val) : "—";
    };
    set("Nodes", metrics.node_count);
    set("Edges", metrics.edge_count);
    const acc = metrics.accuracy ?? metrics.validation_accuracy;
    set("Accuracy", acc != null ? acc : "—");
    set("Duplicates", metrics.duplicates_removed != null ? metrics.duplicates_removed : "—");
    set("Density", metrics.graph_density != null ? metrics.graph_density : "—");
    set("AvgDegree", metrics.average_degree != null ? metrics.average_degree : "—");
  }

  // ── State Machine ────────────────────────────────────────────────────────

  function renderStateMachine(activeIndex, doneThrough) {
    const pills = document.querySelectorAll(".state-pill");
    pills.forEach((p, i) => {
      p.classList.remove("active", "done");
      if (i < doneThrough) p.classList.add("done");
    });
    if (activeIndex >= 0 && pills[activeIndex]) {
      pills[activeIndex].classList.add("active");
    }
  }

  let stateAnimTimer = null;
  let stateAnimIdx = 0;

  function animateStatesDuringProcessing() {
    stateAnimIdx = 0;
    renderStateMachine(0, 0);
    stateAnimTimer = setInterval(() => {
      stateAnimIdx = Math.min(stateAnimIdx + 1, STATE_ORDER.length - 2);
      renderStateMachine(stateAnimIdx, stateAnimIdx);
      // Also animate agent panel
      animateAgentByStateIndex(stateAnimIdx);
      if (stateAnimIdx >= STATE_ORDER.length - 2) stateAnimIdx = 1;
    }, 700);
  }

  function stopStateAnim() {
    if (stateAnimTimer) {
      clearInterval(stateAnimTimer);
      stateAnimTimer = null;
    }
  }

  function finalizeStates() {
    stopStateAnim();
    const last = STATE_ORDER.length - 1;
    renderStateMachine(last, last);
  }

  // ── Agent Panel ──────────────────────────────────────────────────────────

  function setAgentStatus(agentName, status) {
    const card = document.getElementById("agent-" + agentName);
    if (!card) return;
    card.classList.remove("active", "done");
    const indicator = card.querySelector(".agent-indicator");
    const statusText = card.querySelector(".agent-status-text");
    if (indicator) {
      indicator.classList.remove("idle", "running", "done");
      indicator.classList.add(status);
    }
    if (statusText) {
      statusText.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    }
    if (status === "running") card.classList.add("active");
    if (status === "done") card.classList.add("done");
  }

  function resetAllAgents() {
    AGENT_NAMES.forEach((n) => setAgentStatus(n, "idle"));
  }

  function animateAgentByStateIndex(idx) {
    // STATE_ORDER: INIT(0) EXTRACTING(1) VALIDATING(2) DEDUPLICATING(3) CURATING(4) EVALUATING(5) COMPLETED(6)
    // AGENT_NAMES: Extractor(0) Validator(1) Deduplicator(2) Curator(3) Evaluator(4)
    const mapping = { 1: 0, 2: 1, 3: 2, 4: 3, 5: 4 };
    const agentIdx = mapping[idx];
    if (agentIdx === undefined) return;
    // Set all prior agents to done
    for (let i = 0; i < agentIdx; i++) setAgentStatus(AGENT_NAMES[i], "done");
    // Current agent running
    setAgentStatus(AGENT_NAMES[agentIdx], "running");
    // Future agents idle
    for (let i = agentIdx + 1; i < AGENT_NAMES.length; i++) setAgentStatus(AGENT_NAMES[i], "idle");
  }

  function applyAgentTimeline(timeline) {
    if (!timeline || !timeline.length) return;
    resetAllAgents();
    timeline.forEach((entry) => {
      setAgentStatus(entry.agent, entry.status || "done");
    });
  }

  // ── Transition History ───────────────────────────────────────────────────

  function renderTransitions(transitions) {
    const list = document.getElementById("transition-list");
    if (!list) return;
    if (!transitions || !transitions.length) {
      list.innerHTML = '<div class="empty-hint">No transitions yet</div>';
      return;
    }
    list.innerHTML = transitions
      .map(
        (t) =>
          `<div class="transition-entry"><span class="ts">${shortTs(t.timestamp)}</span>${escapeHtml(t.from)} → ${escapeHtml(t.to)}</div>`
      )
      .join("");
    list.scrollTop = list.scrollHeight;
  }

  // ── Interaction Panel (Agent Messages) ──────────────────────────────────

  function renderMessages(messages) {
    const list = document.getElementById("message-list");
    if (!list) return;
    if (!messages || !messages.length) {
      list.innerHTML = '<div class="empty-hint">Messages will appear here after a run</div>';
      return;
    }
    list.innerHTML = messages
      .map((m) => {
        const agentClass = (m.agent || "").toLowerCase();
        return `<div class="msg-envelope">
          <div class="msg-top">
            <span class="msg-agent-badge ${agentClass}">${escapeHtml(m.agent)}</span>
            <span class="msg-ts">${shortTs(m.timestamp)}</span>
          </div>
          <div class="msg-body">
            <span class="msg-label">In:</span><span class="msg-val">${escapeHtml(m.input_summary || "—")}</span>
            <span class="msg-label">Out:</span><span class="msg-val">${escapeHtml(m.output_summary || "—")}</span>
          </div>
        </div>`;
      })
      .join("");
    list.scrollTop = list.scrollHeight;
  }

  // ── Run ID Badge ────────────────────────────────────────────────────────

  function setRunId(runId) {
    const badge = document.getElementById("run-id-badge");
    if (badge) badge.textContent = runId ? `Run: ${runId}` : "No run yet";
    const logsBadge = document.getElementById("logs-run-badge");
    if (logsBadge) logsBadge.textContent = runId ? `Run: ${runId}` : "—";
  }

  // ── Graph Growth Chart (canvas) ─────────────────────────────────────────

  function drawGrowthChart(growthData) {
    const canvas = document.getElementById("growth-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    if (!growthData || growthData.length === 0) {
      ctx.fillStyle = "#94a3b8";
      ctx.font = "13px Poppins, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("No data — run the pipeline to see growth", W / 2, H / 2);
      return;
    }

    const padding = { top: 20, right: 30, bottom: 40, left: 50 };
    const chartW = W - padding.left - padding.right;
    const chartH = H - padding.top - padding.bottom;

    const maxN = Math.max(...growthData.map((d) => d.cumulative_nodes), 1);
    const maxE = Math.max(...growthData.map((d) => d.cumulative_edges), 1);
    const maxVal = Math.max(maxN, maxE);

    function xPos(i) {
      return padding.left + (chartW / Math.max(growthData.length - 1, 1)) * i;
    }
    function yPos(val) {
      return padding.top + chartH - (val / maxVal) * chartH;
    }

    // Grid lines
    ctx.strokeStyle = "rgba(148, 163, 184, 0.15)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(W - padding.right, y);
      ctx.stroke();
    }

    // Axis labels
    ctx.fillStyle = "#94a3b8";
    ctx.font = "11px Poppins, sans-serif";
    ctx.textAlign = "right";
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      const val = Math.round(maxVal - (maxVal / 4) * i);
      ctx.fillText(val, padding.left - 8, y + 4);
    }

    // X labels (run IDs)
    ctx.textAlign = "center";
    growthData.forEach((d, i) => {
      ctx.fillText(d.run_id || `#${i + 1}`, xPos(i), H - 8);
    });

    // Draw cumulative nodes line
    ctx.strokeStyle = "#6366f1";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    growthData.forEach((d, i) => {
      const x = xPos(i);
      const y = yPos(d.cumulative_nodes);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Node dots
    growthData.forEach((d, i) => {
      ctx.fillStyle = "#6366f1";
      ctx.beginPath();
      ctx.arc(xPos(i), yPos(d.cumulative_nodes), 4, 0, Math.PI * 2);
      ctx.fill();
    });

    // Draw cumulative edges line
    ctx.strokeStyle = "#a855f7";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    growthData.forEach((d, i) => {
      const x = xPos(i);
      const y = yPos(d.cumulative_edges);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Edge dots
    growthData.forEach((d, i) => {
      ctx.fillStyle = "#a855f7";
      ctx.beginPath();
      ctx.arc(xPos(i), yPos(d.cumulative_edges), 4, 0, Math.PI * 2);
      ctx.fill();
    });

    // Legend
    ctx.fillStyle = "#6366f1";
    ctx.fillRect(padding.left + 10, padding.top + 4, 12, 3);
    ctx.fillStyle = "#e2e8f0";
    ctx.font = "10px Poppins, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("Nodes", padding.left + 26, padding.top + 8);

    ctx.fillStyle = "#a855f7";
    ctx.fillRect(padding.left + 80, padding.top + 4, 12, 3);
    ctx.fillStyle = "#e2e8f0";
    ctx.fillText("Edges", padding.left + 96, padding.top + 8);
  }

  function loadGrowthData() {
    fetch("/api/growth")
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok) return;
        const g = data.growth || [];
        drawGrowthChart(g);

        const totalRuns = document.getElementById("growth-total-runs");
        const cumNodes = document.getElementById("growth-cum-nodes");
        const cumEdges = document.getElementById("growth-cum-edges");
        if (g.length > 0) {
          const last = g[g.length - 1];
          if (totalRuns) totalRuns.textContent = g.length;
          if (cumNodes) cumNodes.textContent = last.cumulative_nodes;
          if (cumEdges) cumEdges.textContent = last.cumulative_edges;
        }
      })
      .catch(() => {});
  }

  // ── Run History / Replay ────────────────────────────────────────────────

  function loadRunHistory(listId) {
    const list = document.getElementById(listId);
    if (!list) return;
    fetch("/api/runs")
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok || !data.runs || !data.runs.length) {
          list.innerHTML = '<div class="empty-hint">No previous runs</div>';
          return;
        }
        list.innerHTML = data.runs
          .map(
            (r) =>
              `<div class="replay-entry" data-run-id="${escapeHtml(r.run_id)}" onclick="window.__replayRun('${escapeHtml(r.run_id)}')">
                <span class="replay-id">${escapeHtml(r.run_id)}</span>
                <span class="replay-meta">${r.node_count} nodes, ${r.edge_count} edges</span>
                <span class="replay-meta">${shortTs(r.timestamp)}</span>
              </div>`
          )
          .join("");
      })
      .catch(() => {});
  }

  window.__replayRun = function (runId) {
    fetch(`/api/run/${encodeURIComponent(runId)}`)
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok) return;
        // Apply data as if it were a new run result
        window.__kgLastPayload = data;
        setRunId(data.run_id);
        if (data.transitions) renderTransitions(data.transitions);
        if (data.messages) renderMessages(data.messages);
        if (data.agent_timeline) applyAgentTimeline(data.agent_timeline);
        finalizeStates();
        refreshDisplayFromStore();

        // Also update logs page elements if present
        renderLogsMessages(data.messages);
        renderLogsTerminal(data.logs);
      })
      .catch(() => {});
  };

  // ── Dashboard Initialization ────────────────────────────────────────────

  let _refreshDisplayFromStore = null;

  function refreshDisplayFromStore() {
    if (_refreshDisplayFromStore) _refreshDisplayFromStore();
  }

  function initDashboard() {
    const preview = document.getElementById("graph-network");
    if (preview && typeof vis !== "undefined" && !window.__kgNetwork) {
      window.__kgNetwork = new vis.Network(
        preview,
        { nodes: [], edges: [] },
        {
          nodes: { shape: "dot", size: 20 },
          edges: { smooth: { type: "continuous" } },
          physics: { stabilization: { iterations: 100 } },
          interaction: { hover: true, navigationButtons: true },
        }
      );
    }

    const chat = document.getElementById("chat-messages");
    const input = document.getElementById("chat-input");
    const sendBtn = document.getElementById("btn-send");
    const fileInput = document.getElementById("file-input");
    const toggle = document.getElementById("toggle-agents");
    const qaInput = document.getElementById("qa-input");
    const qaAskBtn = document.getElementById("qa-ask-btn");
    const qaAnswer = document.getElementById("qa-answer");

    // Run controls
    const startBtn = document.getElementById("btn-start");
    const stopBtn = document.getElementById("btn-stop");
    const resetBtn = document.getElementById("btn-reset");
    const seedBtn = document.getElementById("btn-seed");
    const seedMenu = document.getElementById("seed-menu");

    
    window.__kgLastPayload = null;

    function appendBubble(text, role) {
      const div = document.createElement("div");
      div.className = "bubble " + (role === "user" ? "user" : "system");
      div.textContent = text;
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
      return div;
    }

    function appendProcessing() {
      const div = document.createElement("div");
      div.className = "bubble system processing";
      div.innerHTML = '<span class="spinner"></span> Processing…';
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
      return div;
    }

    
    _refreshDisplayFromStore = function () {
      const p = window.__kgLastPayload;
      if (!p) return;
      updateMetrics("m-", p.metrics || {});
      if (window.__kgNetwork && p.graph) {
        window.__kgNetwork.setData(graphToVisData(p.graph));
      }
    };

    // ── Seed Menu ──
    fetch("/api/seed")
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok || !data.seeds) return;
        if (!seedMenu) return;
        seedMenu.innerHTML = Object.keys(data.seeds)
          .map(
            (key) =>
              `<div class="seed-menu-item" data-seed="${escapeHtml(key)}">${escapeHtml(key.replace(/_/g, " "))}</div>`
          )
          .join("");
        seedMenu.querySelectorAll(".seed-menu-item").forEach((item) => {
          item.addEventListener("click", () => {
            const seedKey = item.dataset.seed;
            const text = data.seeds[seedKey];
            if (input && text) input.value = text;
            seedMenu.classList.remove("open");
          });
        });
      })
      .catch(() => {});

    if (seedBtn && seedMenu) {
      seedBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        seedMenu.classList.toggle("open");
      });
      document.addEventListener("click", () => seedMenu.classList.remove("open"));
    }

    // ── Start button (same as Send) ──
    if (startBtn) {
      startBtn.addEventListener("click", () => {
        const t = (input && input.value) || "";
        if (t.trim()) {
          input.value = "";
          processText(t);
        }
      });
    }

    // ── Stop button (cancels animation) ──
    if (stopBtn) {
      stopBtn.addEventListener("click", () => {
        stopStateAnim();
        resetAllAgents();
        if (stopBtn) stopBtn.disabled = true;
      });
    }

    // ── Reset button ──
    if (resetBtn) {
      resetBtn.addEventListener("click", async () => {
        try {
          await fetch("/api/reset", { method: "POST" });
        } catch {}
        window.__kgLastPayload = null;
        if (chat) chat.innerHTML = "";
        resetAllAgents();
        renderStateMachine(-1, 0);
        renderTransitions([]);
        renderMessages([]);
        setRunId(null);
        updateMetrics("m-", {});
        if (window.__kgNetwork) window.__kgNetwork.setData({ nodes: [], edges: [] });
        if (qaAnswer) {
          qaAnswer.textContent = "Answer will appear here.";
          qaAnswer.classList.add("muted");
        }
        drawGrowthChart([]);
      });
    }

    // ── QA ──
    async function askQuestion(q) {
      const question = (q || "").trim();
      if (!question) return;
      if (qaAnswer) {
        qaAnswer.textContent = "Thinking…";
        qaAnswer.classList.remove("muted");
      }
      try {
        const res = await fetch("/api/qa", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        });
        const data = await res.json();
        if (!data.ok) {
          if (qaAnswer) qaAnswer.textContent = data.error || "Failed to answer.";
          return;
        }
        if (qaAnswer) qaAnswer.textContent = data.answer || "Answer not found in knowledge graph";
      } catch (e) {
        if (qaAnswer) qaAnswer.textContent = "Failed to answer (network error).";
      }
    }

    if (qaAskBtn) {
      qaAskBtn.addEventListener("click", () => askQuestion(qaInput ? qaInput.value : ""));
    }
    if (qaInput) {
      qaInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          askQuestion(qaInput.value);
        }
      });
    }

    // ── Process text ──
    async function processText(text) {
      if (!text.trim()) return;
      appendBubble(text, "user");
      const procEl = appendProcessing();
      animateStatesDuringProcessing();
      if (sendBtn) sendBtn.disabled = true;
      if (startBtn) startBtn.disabled = true;
      if (stopBtn) stopBtn.disabled = false;
      if (fileInput) fileInput.disabled = true;

      try {
        const res = await fetch("/api/process", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        const data = await res.json();
        procEl.remove();
        stopStateAnim();
        finalizeStates();
        if (sendBtn) sendBtn.disabled = false;
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
        if (fileInput) fileInput.disabled = false;

        if (!data.ok) {
          appendBubble("Error: " + (data.error || "Unknown"), "system");
          return;
        }

        window.__kgLastPayload = data;
        appendBubble(data.summary || "Done.", "system");
        refreshDisplayFromStore();

        // Update panels
        setRunId(data.run_id);
        if (data.transitions) renderTransitions(data.transitions);
        if (data.messages) renderMessages(data.messages);
        if (data.agent_timeline) applyAgentTimeline(data.agent_timeline);

        if (window.__kgNetwork && data.graph) {
          const g = graphToVisData(data.graph);
          window.__kgNetwork.setData(g);
        }

        // Refresh growth chart + replay list
        loadGrowthData();
        loadRunHistory("replay-list");
      } catch (e) {
        procEl.remove();
        stopStateAnim();
        if (sendBtn) sendBtn.disabled = false;
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
        if (fileInput) fileInput.disabled = false;
        appendBubble("Network error: " + e, "system");
      }
    }

    sendBtn &&
      sendBtn.addEventListener("click", () => {
        const t = input.value;
        input.value = "";
        processText(t);
      });

    input &&
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          const t = input.value;
          input.value = "";
          processText(t);
        }
      });

    fileInput &&
      fileInput.addEventListener("change", async () => {
        const f = fileInput.files && fileInput.files[0];
        if (!f) return;
        const procEl = appendProcessing();
        animateStatesDuringProcessing();
        if (sendBtn) sendBtn.disabled = true;
        if (startBtn) startBtn.disabled = true;
        if (stopBtn) stopBtn.disabled = false;
        fileInput.disabled = true;
        const fd = new FormData();
        fd.append("file", f);
        try {
          const res = await fetch("/api/upload", { method: "POST", body: fd });
          const data = await res.json();
          procEl.remove();
          stopStateAnim();
          finalizeStates();
          if (sendBtn) sendBtn.disabled = false;
          if (startBtn) startBtn.disabled = false;
          if (stopBtn) stopBtn.disabled = true;
          fileInput.disabled = false;
          if (!data.ok) {
            appendBubble("Upload error: " + (data.error || ""), "system");
            return;
          }
          if (data.text) appendBubble("[Uploaded file content loaded]", "user");
          window.__kgLastPayload = data;
          appendBubble(data.summary || "Done.", "system");
          refreshDisplayFromStore();

          setRunId(data.run_id);
          if (data.transitions) renderTransitions(data.transitions);
          if (data.messages) renderMessages(data.messages);
          if (data.agent_timeline) applyAgentTimeline(data.agent_timeline);

          if (window.__kgNetwork) {
            window.__kgNetwork.setData(graphToVisData(data.graph));
          }
          loadGrowthData();
          loadRunHistory("replay-list");
        } catch (e) {
          procEl.remove();
          stopStateAnim();
          if (sendBtn) sendBtn.disabled = false;
          if (startBtn) startBtn.disabled = false;
          if (stopBtn) stopBtn.disabled = true;
          fileInput.disabled = false;
          appendBubble("Upload failed: " + e, "system");
        }
        fileInput.value = "";
      });

    // Restore last run from server
    fetch("/api/last")
      .then((r) => r.json())
      .then((data) => {
        if (data.ok && data.graph) {
          window.__kgLastPayload = data;
          refreshDisplayFromStore();
          setRunId(data.run_id);
          if (data.transitions) renderTransitions(data.transitions);
          if (data.messages) renderMessages(data.messages);
          if (data.agent_timeline) applyAgentTimeline(data.agent_timeline);
          else resetAllAgents();
          finalizeStates();
          if (window.__kgNetwork) {
            window.__kgNetwork.setData(graphToVisData(data.graph));
          }
          if (qaAnswer) {
            qaAnswer.textContent = "Answer will appear here.";
            qaAnswer.classList.add("muted");
          }
        }
      })
      .catch(() => {});

    // Load growth + replay on page load
    loadGrowthData();
    loadRunHistory("replay-list");

    window.refreshMetrics = refreshDisplayFromStore;
  }

  // ── Graph page ──────────────────────────────────────────────────────────

  function initGraphPage() {
    const container = document.getElementById("graph-network");
    const toggle = document.getElementById("toggle-agents");
    const searchInput = document.getElementById("graph-search");
    const searchBtn = document.getElementById("btn-graph-search");
    const exportBtn = document.getElementById("btn-export-graph");
    const filterPerson = document.getElementById("filter-person");
    const filterOrg = document.getElementById("filter-org");
    const filterLoc = document.getElementById("filter-loc");
    const filterEvent = document.getElementById("filter-event");
    const nodeInfo = document.getElementById("graph-node-info");
    if (!container || typeof vis === "undefined") return;

    const options = {
      nodes: { shape: "dot", size: 22, borderWidth: 2 },
      edges: { smooth: { type: "continuous" } },
      physics: {
        enabled: true,
        stabilization: { iterations: 120 },
      },
      interaction: { hover: true, navigationButtons: true, keyboard: true },
    };

    const net = new vis.Network(container, { nodes: [], edges: [] }, options);
    window.__kgNetwork = net;

    let fullGraph = null;

    
    function applyFiltersAndRender() {
      if (!fullGraph) return;
      const allowedTypes = new Set();
      if (!filterPerson || filterPerson.checked) allowedTypes.add("Person");
      if (!filterOrg || filterOrg.checked) allowedTypes.add("Organization");
      if (!filterLoc || filterLoc.checked) allowedTypes.add("Location");
      if (!filterEvent || filterEvent.checked) allowedTypes.add("Event");

      const nodes = fullGraph.nodes.filter((n) => {
        if (!n.type || allowedTypes.size === 0) return true;
        return allowedTypes.has(n.type);
      });
      const nodeIds = new Set(nodes.map((n) => n.id));
      const edges = fullGraph.edges.filter(
        (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
      );
      net.setData(graphToVisData({ nodes, edges }));
    }

    function loadGraphForToggle() {
      fetch("/api/last")
        .then((r) => r.json())
        .then((data) => {
          if (!data.ok || !data.graph) return;
          fullGraph = data.graph;
          applyFiltersAndRender();
        })
        .catch(() => {});
    }

    loadGraphForToggle();

    if (filterPerson)
      filterPerson.addEventListener("change", applyFiltersAndRender);
    if (filterOrg) filterOrg.addEventListener("change", applyFiltersAndRender);
    if (filterLoc) filterLoc.addEventListener("change", applyFiltersAndRender);
    if (filterEvent)
      filterEvent.addEventListener("change", applyFiltersAndRender);

    function highlightBySearch() {
      if (!fullGraph || !searchInput) return;
      const q = searchInput.value.trim().toLowerCase();
      if (!q) return;
      const match = (fullGraph.nodes || []).find(
        (n) => n.name && n.name.toLowerCase().includes(q)
      );
      if (!match) return;
      net.selectNodes([match.id]);
      net.focus(match.id, {
        scale: 1.4,
        animation: { duration: 500, easingFunction: "easeInOutQuad" },
      });
    }

    if (searchBtn) searchBtn.addEventListener("click", highlightBySearch);
    if (searchInput)
      searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          highlightBySearch();
        }
      });

    if (exportBtn) {
      exportBtn.addEventListener("click", () => {
        if (!fullGraph) return;
        fetch("/api/last")
          .then((r) => r.json())
          .then((data) => {
            if (!data.ok) return;
            if (!data.graph) return;
            const payload = {
              nodes: data.graph.nodes,
              edges: data.graph.edges,
              metrics: data.metrics,
            };
            const blob = new Blob([JSON.stringify(payload, null, 2)], {
              type: "application/json",
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "knowledge-graph.json";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          })
          .catch(() => {});
      });
    }

    net.on("click", (params) => {
      if (!params.nodes || !params.nodes.length) return;
      const nodeId = params.nodes[0];
      if (!fullGraph || !nodeInfo) return;
      const node = (fullGraph.nodes || []).find((n) => n.id === nodeId);
      if (!node) return;
      const degree =
        (fullGraph.edges || []).filter(
          (e) => e.source === nodeId || e.target === nodeId
        ).length || 0;
      const body = nodeInfo.querySelector(".body");
      const title = nodeInfo.querySelector(".title");
      if (title) title.textContent = "Node details";
      if (body) {
        body.innerHTML = `
          <div><strong>Name:</strong> ${escapeHtml(node.name || "")}</div>
          <div><strong>Type:</strong> ${escapeHtml(node.type || "Other")}</div>
          <div><strong>Connections:</strong> ${degree}</div>
        `;
      }
      net.selectNodes([nodeId]);
      net.selectEdges(net.getConnectedEdges(nodeId));
      net.focus(nodeId, {
        scale: 1.3,
        animation: { duration: 400, easingFunction: "easeInOutQuad" },
      });
    });
  }

  // ── Logs page ───────────────────────────────────────────────────────────

  function renderLogsMessages(messages) {
    const list = document.getElementById("logs-messages-list");
    if (!list) return;
    if (!messages || !messages.length) {
      list.innerHTML = '<div class="empty-hint">No messages yet</div>';
      return;
    }
    list.innerHTML = messages
      .map((m) => {
        const agentClass = (m.agent || "").toLowerCase();
        return `<div class="msg-envelope">
          <div class="msg-top">
            <span class="msg-agent-badge ${agentClass}">${escapeHtml(m.agent)}</span>
            <span class="msg-ts">${shortTs(m.timestamp)}</span>
            <span class="msg-ts" style="margin-left:auto;">run: ${escapeHtml(m.run_id || "—")}</span>
          </div>
          <div class="msg-body">
            <span class="msg-label">Action:</span><span class="msg-val">${escapeHtml(m.action || "—")}</span>
            <span class="msg-label">In:</span><span class="msg-val">${escapeHtml(m.input_summary || "—")}</span>
            <span class="msg-label">Out:</span><span class="msg-val">${escapeHtml(m.output_summary || "—")}</span>
          </div>
        </div>`;
      })
      .join("");
  }

  function renderLogsTerminal(logs) {
    const term = document.getElementById("logs-terminal");
    if (!term) return;
    if (!logs || !logs.length) {
      term.textContent = "No logs yet. Run a job from the dashboard.";
      return;
    }
    term.innerHTML = logs
      .map((line) => `<div class="line">${escapeHtml(line)}</div>`)
      .join("");
    term.scrollTop = term.scrollHeight;
  }

  function initLogsPage() {
    fetch("/api/last")
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok) {
          renderLogsTerminal([]);
          return;
        }
        setRunId(data.run_id);
        renderLogsMessages(data.messages);
        renderLogsTerminal(data.logs);
      })
      .catch(() => {
        renderLogsTerminal([]);
      });

    loadRunHistory("logs-replay-list");
  }

  // ── Init ────────────────────────────────────────────────────────────────

  document.addEventListener("DOMContentLoaded", () => {
    const page = document.body && document.body.dataset && document.body.dataset.page;
    if (page === "dashboard") initDashboard();
    else if (page === "graph") initGraphPage();
    else if (page === "logs") initLogsPage();
  });
})();
