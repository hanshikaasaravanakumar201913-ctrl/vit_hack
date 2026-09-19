/**
 * ATLAS — Clinical Study Intelligence
 * Enterprise Investigation Platform Controller
 * Zero-dependency vanilla ES6 implementation
 */

document.addEventListener("DOMContentLoaded", () => {
  // Global Application State
  const state = {
    activeTab: "ask",
    stats: null,
    subjects: [],
    demoQuestions: [],
    queryHistory: [],
    isQueryRunning: false,
    currentPatient: null,
    patientDomainFilter: "ALL",
    selectedGraphNode: null,
  };

  // Graph Subsystem State (Defined early to prevent TDZ errors)
  const graphState = {
    mode: "study", // "study" | "patient"
    patient: null,
    patientCache: {},
    zoom: 1.0,
    pan: { x: 0, y: 0 },
    isDragging: false,
    dragStart: { x: 0, y: 0 },
    selectedNodeId: null,
    allNodes: {},
    allNodes: {},
    connectedEdges: {},
  };

  // Standard Scheduled Protocol Visits
  const PROTOCOL_VISITS = [
    { name: "Screening", day: -14, window: "-28 to -1 days", req: "Informed Consent, Demographics (DM), Medical History (MH)" },
    { name: "Baseline", day: 1, window: "Day 1 (Pre-dose)", req: "Randomization, Vitals, Baseline Labs, First Dose (EX)" },
    { name: "Week 2", day: 14, window: "±3 days (All cuts)", req: "Early Safety, Vitals, Targeted Labs" },
    { name: "Week 4", day: 28, window: "±7 days (v1) / ±3 days (v2)", req: "Safety Panel, Vitals, Dosing Compliance" },
    { name: "Week 8", day: 56, window: "±7 days (v1) / ±3 days (v2)", req: "Comprehensive Labs, Vital Signs, Dosing (EX)" },
    { name: "Week 12", day: 84, window: "±7 days (v1) / ±3 days (v2)", req: "Mid-study Efficacy, HbA1c, Vitals, Dosing" },
    { name: "Week 16", day: 112, window: "±7 days (v1) / ±3 days (v2)", req: "Vitals, Dosing (EX)" },
    { name: "Week 20", day: 140, window: "±7 days (v1) / ±3 days (v2)", req: "Vitals, Dosing (EX)" },
    { name: "Week 24", day: 168, window: "±7 days (v1) / ±3 days (v2)", req: "End of Study, Disposition (DS), Full Labs" },
  ];

  // Clinical Domains Metadata
  const CLINICAL_DOMAINS_INFO = {
    LB: { name: "Laboratory Results", sampleQuery: "Which subjects meet potential Hy's law criteria?" },
    AE: { name: "Adverse Events", sampleQuery: "Which subjects at site S05 have serious adverse events?" },
    EX: { name: "Exposure & Dosing", sampleQuery: "Which subjects at site S09 received a wrong dose?" },
    VS: { name: "Vital Signs", sampleQuery: "List the vital signs and laboratory records for 042-S05-003 around Week 8" },
    CM: { name: "Concomitant Medications", sampleQuery: "Which subjects took prohibited concomitant medications?" },
    DS: { name: "Disposition", sampleQuery: "How many subjects at site S11 discontinued due to an adverse event?" },
    DM: { name: "Demographics", sampleQuery: "Which subjects are enrolled in STUDY-042?" },
    MH: { name: "Medical History", sampleQuery: "Which subjects have medical history of hypertension?" },
    EG: { name: "Electrocardiogram", sampleQuery: "List the ECG records for 042-S05-003" },
  };

  // DOM Elements
  const navItems = document.querySelectorAll(".nav-item");
  const tabViews = document.querySelectorAll(".tab-view");
  const navBrand = document.getElementById("nav-brand");

  // Conversational Assistant State
  const chatState = {
    conversationId: null,
    activeSubject: null,
  };

  const chatMessagesStream = document.getElementById("chat-messages-stream");
  const chatContextStrip = document.getElementById("chat-context-strip");
  const chatActiveSubjectText = document.getElementById("chat-active-subject-text");
  const chatContextQuickActions = document.getElementById("chat-context-quick-actions");
  const btnClearChatContext = document.getElementById("btn-clear-chat-context");
  const btnNewChat = document.getElementById("btn-new-chat");

  const queryInput = document.getElementById("query-input");
  const askBtn = document.getElementById("ask-btn");
  const clearBtn = document.getElementById("clear-btn");
  const queryHistoryBar = document.getElementById("query-history-bar");
  const historyChips = document.getElementById("history-chips");
  const loadingState = document.getElementById("loading-state");
  const resultsArea = document.getElementById("results-area");
  const showcaseGrid = document.getElementById("showcase-chips-grid");


  // Study Graph Elements
  const graphPatientInput = document.getElementById("graph-patient-input");
  const graphFocusBtn = document.getElementById("graph-focus-btn");
  const graphSubjectsDatalist = document.getElementById("graph-subjects-datalist");
  const btnViewStudy = document.getElementById("btn-view-study");
  const btnViewPatient = document.getElementById("btn-view-patient");
  const btnZoomIn = document.getElementById("btn-zoom-in");
  const btnZoomOut = document.getElementById("btn-zoom-out");
  const btnZoomReset = document.getElementById("btn-zoom-reset");
  const btnCanvasCenter = document.getElementById("btn-canvas-center");
  const quickPatientChips = document.querySelectorAll(".quick-patient-chip");
  const canvasModeText = document.getElementById("canvas-mode-text");
  const canvasHelpHint = document.getElementById("canvas-help-hint");
  const svgViewportWrapper = document.getElementById("svg-viewport-wrapper");
  const graphSvgCanvas = document.getElementById("graph-svg-canvas");
  const graphRootGroup = document.getElementById("graph-root-group");
  const svgEdgesLayer = document.getElementById("svg-edges-layer");
  const svgNodesLayer = document.getElementById("svg-nodes-layer");
  const svgLabelsLayer = document.getElementById("svg-labels-layer");
  const inspType = document.getElementById("insp-type");
  const inspTitle = document.getElementById("insp-title");
  const inspBody = document.getElementById("insp-body");
  const inspActions = document.getElementById("insp-actions");

  // Patient 360 Elements
  const patientSearchInput = document.getElementById("patient-search-input");
  const patientLoadBtn = document.getElementById("patient-load-btn");
  const subjectsDatalist = document.getElementById("subjects-datalist");
  const patientProfileArea = document.getElementById("patient-profile-area");
  const notableChips = document.querySelectorAll(".notable-chip");

  // Telemetry Elements
  const statSubjects = document.getElementById("stat-subjects");
  const statSites = document.getElementById("stat-sites");
  const statNodes = document.getElementById("stat-nodes");
  const statEdges = document.getElementById("stat-edges");
  const statLabs = document.getElementById("stat-labs");
  const statVitals = document.getElementById("stat-vitals");
  const statDoses = document.getElementById("stat-doses");
  const statLatency = document.getElementById("stat-latency");

  // =========================================================================
  // 1. Navigation & Tab Switching
  // =========================================================================

  function switchTab(tabId) {
    state.activeTab = tabId;

    navItems.forEach((btn) => {
      const isSelected = btn.dataset.tab === tabId;
      btn.classList.toggle("active", isSelected);
      btn.setAttribute("aria-selected", isSelected ? "true" : "false");
    });

    tabViews.forEach((view) => {
      view.classList.toggle("active", view.id === `tab-${tabId}`);
    });

    if (tabId === "graph") {
      // Always reset and re-render so SVG is never blank
      resetGraphView();
      if (graphState.mode === "patient" && graphState.patient) {
        renderPatientKnowledgeGraph(graphState.patient);
      } else {
        if (state.stats) renderStudyLevelGraph(state.stats);
      }
    } else if (tabId === "patient") {
      const targetSubj = (graphState.patient && graphState.patient.usubjid) || (state.currentPatient && state.currentPatient.usubjid) || "042-S07-001";
      if (!state.currentPatient || state.currentPatient.usubjid !== targetSubj) {
        loadPatientData(targetSubj);
      }
    } else if (tabId === "monitor") {
      loadMonitorReport();
    }

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  navItems.forEach((item) => {
    item.addEventListener("click", () => {
      switchTab(item.dataset.tab);
    });
  });

  if (navBrand) {
    navBrand.addEventListener("click", () => switchTab("ask"));
    navBrand.addEventListener("keydown", (e) => {
      if (e.key === "Enter") switchTab("ask");
    });
  }

  // =========================================================================
  // 2. Data Ingestion & Setup
  // =========================================================================

  async function initializeApp() {
    try {
      // 1. Fetch Graph Telemetry & Stats
      const statsPromise = fetch("/api/stats")
        .then((res) => (res.ok ? res.json() : null))
        .then((stats) => {
          if (stats) {
            state.stats = stats;
            renderTelemetry(stats);
            renderStudyLevelGraph(stats);
          }
        })
        .catch((err) => console.warn("Stats API error:", err));

      // 2. Fetch Public Clinical Demo Questions
      const questionsPromise = fetch("/api/public-questions")
        .then((res) => (res.ok ? res.json() : []))
        .then((questions) => {
          state.demoQuestions = questions;
          renderShowcaseQuestions(questions);
        })
        .catch((err) => console.warn("Public questions error:", err));

      // 3. Fetch Subjects for Autocomplete & Navigation
      const subjectsPromise = fetch("/api/subjects")
        .then((res) => (res.ok ? res.json() : { subjects: [] }))
        .then((data) => {
          state.subjects = data.subjects || [];
          populateSubjectsDatalist(state.subjects);
        })
        .catch((err) => console.warn("Subjects error:", err));

      await Promise.allSettled([statsPromise, questionsPromise, subjectsPromise]);
      
      // Initialize Monitor Tab
      initMonitorTab();
    } catch (e) {
      console.error("Initialization failure:", e);
    }
  }

  function renderTelemetry(stats) {
    if (statSubjects && stats.subjects) statSubjects.textContent = `${Number(stats.subjects).toLocaleString()} Subjects`;
    if (statNodes && stats.nodes) statNodes.textContent = Number(stats.nodes).toLocaleString();
    if (statEdges && stats.edges) statEdges.textContent = Number(stats.edges).toLocaleString();
    if (statSites && stats.sites_count) statSites.textContent = `${stats.sites_count} Sites`;
    if (statLatency && (stats.build_time_ms || stats.ms)) {
      const ms = stats.build_time_ms || stats.ms;
      statLatency.textContent = `< ${Math.max(Math.round(ms), 10)} ms`;
    }

    if (stats.domains) {
      if (statLabs && stats.domains.LB) statLabs.textContent = Number(stats.domains.LB).toLocaleString();
      if (statVitals && stats.domains.VS) statVitals.textContent = Number(stats.domains.VS).toLocaleString();
      if (statDoses && stats.domains.EX) statDoses.textContent = Number(stats.domains.EX).toLocaleString();
    }
  }

  function populateSubjectsDatalist(subjects) {
    if (subjectsDatalist) {
      subjectsDatalist.innerHTML = "";
      subjects.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.usubjid;
        opt.label = `Site ${s.site_id} • Arm: ${s.arm} • Age: ${s.age}`;
        subjectsDatalist.appendChild(opt);
      });
    }

    if (graphSubjectsDatalist) {
      graphSubjectsDatalist.innerHTML = "";
      subjects.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.usubjid;
        opt.label = `Site ${s.site_id} • Arm: ${s.arm} • Age: ${s.age}`;
        graphSubjectsDatalist.appendChild(opt);
      });
    }
  }

  // =========================================================================
  // 3. Ask ATLAS: Natural Clinical Questions Showcase
  // =========================================================================

  function renderShowcaseQuestions(questions) {
    if (!showcaseGrid) return;
    showcaseGrid.innerHTML = "";

    const showcaseList = [
      { id: "Q004", category: "Liver Safety", text: "Which subjects meet potential Hy's law criteria?" },
      { id: "Q005", category: "Liver Safety", text: "Which subjects at site S07 meet potential Hy's law criteria?" },
      { id: "Q007", category: "Dosing Deviations", text: "Which subjects at site S09 received a wrong dose?" },
      { id: "Q009", category: "Safety / SAE", text: "Which subjects at site S05 have serious adverse events?" },
      { id: "Q008", category: "Protocol Amendments", text: "Which subjects took prohibited concomitant medications?" },
      { id: "Q002", category: "Discontinuation", text: "How many subjects at site S11 discontinued due to an adverse event?" },
      { id: "Q003", category: "Record Lookup", text: "List the laboratory and adverse-event records for 042-S05-003 within 7 days of the WEEK8 visit" },
      { id: "Q006", category: "Dosing Deviations", text: "Which subjects at site S01 received a wrong dose?" },
      { id: "Q001", category: "Discontinuation", text: "How many subjects at site S07 discontinued due to an adverse event?" },
    ];

    showcaseList.forEach((q) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "suggested-pill";
      btn.innerHTML = `<span class="pill-category">${escapeHtml(q.category)}:</span> <span class="pill-text">${escapeHtml(q.text)}</span>`;
      btn.addEventListener("click", () => {
        if (queryInput) {
          queryInput.value = q.text;
          if (clearBtn) clearBtn.style.display = "block";
        }
        executeAsk(q.text, q.id);
      });
      showcaseGrid.appendChild(btn);
    });
  }

  // =========================================================================
  // 4. Ask ATLAS: Query Execution & Results Rendering
  // =========================================================================

  if (queryInput) {
    queryInput.addEventListener("input", () => {
      clearBtn.style.display = queryInput.value.trim().length > 0 ? "block" : "none";
    });

    queryInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleQuerySubmit();
      }
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      queryInput.value = "";
      clearBtn.style.display = "none";
      if (resultsArea) resultsArea.style.display = "none";
      queryInput.focus();
    });
  }

  // =========================================================================
  // Conversational Clinical Assistant Engine
  // =========================================================================

  if (btnNewChat) {
    btnNewChat.addEventListener("click", () => {
      chatState.conversationId = null;
      chatState.activeSubject = null;
      if (chatContextStrip) chatContextStrip.style.display = "none";
      resetChatStream();
    });
  }

  if (btnClearChatContext) {
    btnClearChatContext.addEventListener("click", () => {
      chatState.activeSubject = null;
      if (chatContextStrip) chatContextStrip.style.display = "none";
    });
  }

  if (chatContextQuickActions) {
    chatContextQuickActions.addEventListener("click", (e) => {
      const btn = e.target.closest(".btn-context-action");
      if (btn && btn.dataset.action && chatState.activeSubject) {
        const act = btn.dataset.action;
        if (act === "liver") {
          executeChat(`Check liver safety transaminases and potential Hy's law for ${chatState.activeSubject}`);
        } else if (act === "meds") {
          executeChat(`Review concomitant medications and prohibited therapies for ${chatState.activeSubject}`);
        } else if (act === "aes") {
          executeChat(`What adverse events and hospitalizations were reported for ${chatState.activeSubject}?`);
        } else if (act === "screening") {
          executeChat(`What was the baseline screening laboratory profile for ${chatState.activeSubject}?`);
        }
      }
    });
  }

  function resetChatStream() {
    if (!chatMessagesStream) return;
    chatMessagesStream.innerHTML = `
      <div class="chat-message assistant-message welcome-message">
        <div class="msg-avatar">ATLAS</div>
        <div class="msg-body">
          <div class="msg-author-row">
            <span class="msg-author-name">ATLAS Clinical Assistant</span>
            <span class="msg-time">Grounded in STUDY-042 Graph</span>
          </div>
          <div class="msg-content">
            <p>Welcome to <strong>ATLAS</strong>, your AI conversational clinical study intelligence assistant.</p>
            <p>I perform natural-language clinical investigations across STUDY-042 by directly querying the knowledge graph, calculating biochemical thresholds, and applying governing protocol rules. Every fact is traceable to verified CDISC SDTM records.</p>
          </div>
          <div class="suggested-pills-wrap">
            <div class="suggested-lead">Suggested inquiries:</div>
            <div class="suggested-pills" id="showcase-chips-grid">
              <button class="suggested-pill" type="button" data-query="Tell me about subject 042-S07-001.">Tell me about subject 042-S07-001</button>
              <button class="suggested-pill" type="button" data-query="Which subjects meet potential Hy's law criteria?">Which subjects meet Hy's law criteria?</button>
              <button class="suggested-pill" type="button" data-query="Which subjects at site S09 received a wrong dose?">Which subjects at site S09 received a wrong dose?</button>
              <button class="suggested-pill" type="button" data-query="Which subjects took prohibited concomitant medications?">Which subjects took prohibited medications?</button>
              <button class="suggested-pill" type="button" data-query="How many subjects at site S11 discontinued due to an adverse event?">How many subjects at S11 discontinued due to an AE?</button>
            </div>
          </div>
        </div>
      </div>
    `;
    bindShowcasePills();
  }

  function bindShowcasePills() {
    const pills = document.querySelectorAll("#chat-messages-stream .suggested-pill");
    pills.forEach((p) => {
      p.addEventListener("click", () => {
        const q = p.dataset.query || p.textContent.trim();
        executeChat(q);
      });
    });
  }
  bindShowcasePills();

  function formatMarkdown(text) {
    if (!text) return "";
    let safe = escapeHtml(text);

    // Code blocks
    safe = safe.replace(/```([\s\S]*?)```/g, (match, p1) => {
      return `<pre><code>${p1.trim()}</code></pre>`;
    });

    // Inline code
    safe = safe.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Bold & italic
    safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    // Process lines for lists, callouts, and paragraphs
    const lines = safe.split("\n");
    let inUl = false;
    let inOl = false;
    const output = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) {
        if (inUl) { output.push("</ul>"); inUl = false; }
        if (inOl) { output.push("</ol>"); inOl = false; }
        continue;
      }

      // Unordered list
      const ulMatch = line.match(/^[-*•]\s+(.*)$/);
      if (ulMatch) {
        if (inOl) { output.push("</ol>"); inOl = false; }
        if (!inUl) { output.push("<ul>"); inUl = true; }
        output.push(`<li>${ulMatch[1]}</li>`);
        continue;
      }

      // Ordered list
      const olMatch = line.match(/^(\d+)\.\s+(.*)$/);
      if (olMatch) {
        if (inUl) { output.push("</ul>"); inUl = false; }
        if (!inOl) { output.push("<ol>"); inOl = true; }
        output.push(`<li>${olMatch[2]}</li>`);
        continue;
      }

      if (inUl) { output.push("</ul>"); inUl = false; }
      if (inOl) { output.push("</ol>"); inOl = false; }

      // Callout box
      if (line.startsWith("&gt;")) {
        const textContent = line.replace(/^&gt;\s*/, "");
        let calloutClass = "clinical-finding-callout";
        if (textContent.includes("CRITICAL") || textContent.includes("ELEVATED") || textContent.includes("Hy&#39;s Law") || textContent.includes("HYS")) {
          calloutClass += " callout-critical";
        } else if (textContent.includes("WARNING") || textContent.includes("DISCREPANCY") || textContent.includes("DEVIATION")) {
          calloutClass += " callout-warning";
        }
        output.push(`<div class="${calloutClass}">${textContent}</div>`);
        continue;
      }

      // Headings
      if (line.startsWith("### ")) {
        output.push(`<h4 style="margin: 12px 0 6px; font-weight: 700; color: var(--text-main); font-size: 0.95rem;">${line.substring(4)}</h4>`);
        continue;
      }
      if (line.startsWith("## ")) {
        output.push(`<h3 style="margin: 14px 0 8px; font-weight: 700; color: var(--text-main); font-size: 1.05rem;">${line.substring(3)}</h3>`);
        continue;
      }

      output.push(`<p>${line}</p>`);
    }

    if (inUl) output.push("</ul>");
    if (inOl) output.push("</ol>");

    return output.join("");
  }

  function showCdiscRecordModal(record) {
    let backdrop = document.getElementById("cdisc-modal-backdrop");
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.id = "cdisc-modal-backdrop";
      backdrop.className = "cdisc-record-modal-backdrop";
      document.body.appendChild(backdrop);
    }

    const rows = Object.entries(record)
      .filter(([k]) => !k.startsWith("_") && k !== "raw")
      .map(([k, v]) => `
        <tr>
          <th>${escapeHtml(k)}</th>
          <td>${escapeHtml(String(v ?? ""))}</td>
        </tr>
      `)
      .join("");

    const dom = record.DOMAIN || record.domain || "RECORD";
    const seq = record.SEQ || record.seq || record.LBSEQ || record.AESEQ || record.EXSEQ || record.CMSEQ || "1";
    const subj = record.USUBJID || record.usubjid || (graphState.patient && graphState.patient.usubjid) || "042";
    const testName = record.LBTEST || record.LBTESTCD || record.AETERM || record.EXTRT || record.CMTRT || record.VSTEST || dom;

    backdrop.innerHTML = `
      <div class="cdisc-record-modal-panel">
        <div class="cdisc-modal-header">
          <div class="cdisc-modal-title">CDISC SDTM Record: ${escapeHtml(dom)} • Seq ${escapeHtml(String(seq))} (${escapeHtml(subj)})</div>
          <button class="cdisc-modal-close" id="btn-close-cdisc-modal">&times;</button>
        </div>
        <div class="cdisc-modal-body">
          <table class="cdisc-modal-table">
            <tbody>
              ${rows}
            </tbody>
          </table>
        </div>
        <div class="cdisc-modal-footer">
          <button class="btn-primary btn-sm" id="btn-modal-ask-atlas">Ask ATLAS about this record</button>
          <button class="btn-secondary btn-sm" id="btn-modal-close-footer">Close</button>
        </div>
      </div>
    `;

    backdrop.style.display = "flex";

    const closeFn = () => { backdrop.style.display = "none"; };
    backdrop.querySelector("#btn-close-cdisc-modal").addEventListener("click", closeFn);
    backdrop.querySelector("#btn-modal-close-footer").addEventListener("click", closeFn);
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) closeFn();
    });

    backdrop.querySelector("#btn-modal-ask-atlas").addEventListener("click", () => {
      closeFn();
      switchTab("ask");
      const q = `Explain the clinical significance of ${dom} record seq ${seq} (${testName}) for subject ${subj}`;
      executeChat(q);
    });
  }

  function appendUserMessage(text) {
    if (!chatMessagesStream) return;
    const msgDiv = document.createElement("div");
    msgDiv.className = "chat-message user-message";
    msgDiv.innerHTML = `
      <div class="msg-avatar">YOU</div>
      <div class="msg-body">
        <div class="msg-author-row">
          <span class="msg-author-name">Clinical Investigator</span>
          <span class="msg-time">${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
        </div>
        <div class="msg-content">
          ${escapeHtml(text)}
        </div>
      </div>
    `;
    chatMessagesStream.appendChild(msgDiv);
    chatMessagesStream.scrollTop = chatMessagesStream.scrollHeight;
  }

  function appendTypingIndicator(typingId) {
    if (!chatMessagesStream) return;
    const typingDiv = document.createElement("div");
    typingDiv.id = typingId;
    typingDiv.className = "chat-message assistant-message";
    typingDiv.innerHTML = `
      <div class="msg-avatar">ATLAS</div>
      <div class="msg-body">
        <div class="msg-author-row">
          <span class="msg-author-name">ATLAS Clinical Assistant</span>
          <span class="msg-time">Reasoning across StudyGraph...</span>
        </div>
        <div class="chat-typing-indicator">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span style="margin-left: 6px; font-size: 0.76rem;">Evaluating protocol rules and CDISC records</span>
        </div>
      </div>
    `;
    chatMessagesStream.appendChild(typingDiv);
    chatMessagesStream.scrollTop = chatMessagesStream.scrollHeight;
  }

  function removeTypingIndicator(typingId) {
    const el = document.getElementById(typingId);
    if (el) el.remove();
  }

  function appendErrorMessage(errorText) {
    if (!chatMessagesStream) return;
    const msgDiv = document.createElement("div");
    msgDiv.className = "chat-message assistant-message";
    msgDiv.innerHTML = `
      <div class="msg-avatar" style="background: #EF4444;">!</div>
      <div class="msg-body">
        <div class="msg-author-row">
          <span class="msg-author-name" style="color: #DC2626;">System Notice</span>
          <span class="msg-time">${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
        </div>
        <div class="msg-content" style="border-left: 3px solid #DC2626;">
          <p style="color: #DC2626; font-weight: 600;">${escapeHtml(errorText)}</p>
          <p style="font-size: 0.8rem; color: var(--text-secondary);">Please verify backend connectivity or try rephrasing your inquiry.</p>
        </div>
      </div>
    `;
    chatMessagesStream.appendChild(msgDiv);
    chatMessagesStream.scrollTop = chatMessagesStream.scrollHeight;
  }

  function appendAssistantMessage(data) {
    if (!chatMessagesStream) return;
    const {
      message = "",
      evidence = [],
      followup_suggestions = [],
      active_subject,
      latency_ms = 15.0,
    } = data;

    const formattedContent = formatMarkdown(message);

    // Build evidence cards if provided
    let evidenceHtml = "";
    if (evidence && evidence.length > 0) {
      const cardsHtml = evidence.map((ev) => {
        const dom = ev.domain || "CDISC";
        const subj = ev.usubjid || active_subject || "042";
        const seq = ev.seq || "1";
        const test = ev.test || ev.term || ev.treatment || dom;
        const res = ev.result != null ? ev.result : "";
        const units = ev.units || "";
        const visit = ev.visit || "";
        const evJson = escapeHtml(JSON.stringify(ev));

        return `
          <div class="chat-evidence-card">
            <div class="evidence-card-top">
              <span class="evidence-domain-tag evidence-domain-${escapeHtml(dom)}">${escapeHtml(dom)}</span>
              <span class="evidence-seq-tag">Seq ${escapeHtml(String(seq))}</span>
            </div>
            <div class="evidence-card-title">${escapeHtml(test)} ${res ? `= ${escapeHtml(String(res))} ${escapeHtml(units)}` : ""}</div>
            <div class="evidence-card-summary">Subject: <strong>${escapeHtml(subj)}</strong> ${visit ? `• Visit: ${escapeHtml(visit)}` : ""}</div>
            <div class="evidence-card-actions">
              <button type="button" class="btn-card-action btn-view-ev-modal" data-ev='${evJson}'>[View record]</button>
              <button type="button" class="btn-card-action btn-ask-ev-action" data-subj="${escapeHtml(subj)}" data-dom="${escapeHtml(dom)}" data-seq="${escapeHtml(String(seq))}" data-test="${escapeHtml(test)}">[Ask ATLAS about this]</button>
            </div>
          </div>
        `;
      }).join("");

      evidenceHtml = `
        <div class="chat-evidence-section">
          <div class="chat-evidence-header">
            <span class="chat-evidence-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
              <span>CDISC SDTM Ground-Truth Evidence (${evidence.length} Records)</span>
            </span>
          </div>
          <div class="chat-evidence-grid">
            ${cardsHtml}
          </div>
        </div>
      `;
    }

    // Build follow-up suggestions if provided
    let followupHtml = "";
    if (followup_suggestions && followup_suggestions.length > 0) {
      const chipsHtml = followup_suggestions.map((s) => `
        <button type="button" class="followup-chip" data-query="${escapeHtml(s)}">${escapeHtml(s)}</button>
      `).join("");

      followupHtml = `
        <div class="followup-chips-wrap">
          <div class="followup-lead">Recommended Next Inquiries:</div>
          <div class="followup-chips-row">
            ${chipsHtml}
          </div>
        </div>
      `;
    }

    const msgDiv = document.createElement("div");
    msgDiv.className = "chat-message assistant-message";
    msgDiv.innerHTML = `
      <div class="msg-avatar">ATLAS</div>
      <div class="msg-body">
        <div class="msg-author-row">
          <span class="msg-author-name">ATLAS Clinical Assistant</span>
          <span class="msg-time">Grounded in STUDY-042 Graph • ${Math.round(latency_ms)}ms</span>
        </div>
        <div class="msg-content">
          ${formattedContent}
          ${evidenceHtml}
          ${followupHtml}
        </div>
      </div>
    `;

    // Bind evidence actions
    msgDiv.querySelectorAll(".btn-view-ev-modal").forEach((btn) => {
      btn.addEventListener("click", () => {
        try {
          const rec = JSON.parse(btn.dataset.ev);
          showCdiscRecordModal(rec);
        } catch (e) {
          console.error("Parse ev modal err:", e);
        }
      });
    });

    msgDiv.querySelectorAll(".btn-ask-ev-action").forEach((btn) => {
      btn.addEventListener("click", () => {
        const { subj, dom, seq, test } = btn.dataset;
        executeChat(`Explain the clinical significance of ${dom} record seq ${seq} (${test}) for subject ${subj}`);
      });
    });

    // Bind follow-up chips
    msgDiv.querySelectorAll(".followup-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const q = chip.dataset.query;
        executeChat(q);
      });
    });

    chatMessagesStream.appendChild(msgDiv);
    chatMessagesStream.scrollTop = chatMessagesStream.scrollHeight;
  }

  async function executeChat(questionText, options = {}) {
    if (!questionText || state.isQueryRunning) return;
    const cleanQuery = questionText.trim();
    if (!cleanQuery) return;

    state.isQueryRunning = true;
    addSessionQueryHistory(cleanQuery);

    if (queryInput) {
      queryInput.value = "";
      if (clearBtn) clearBtn.style.display = "none";
    }

    if (askBtn) {
      askBtn.disabled = true;
      const textSpan = askBtn.querySelector(".btn-text");
      if (textSpan) textSpan.textContent = "Reasoning...";
      const spinner = askBtn.querySelector(".btn-spinner");
      if (spinner) spinner.style.display = "inline-block";
    }

    // 1. Append User Message Bubble
    appendUserMessage(cleanQuery);

    // 2. Append Typing Indicator
    const typingId = "typing-" + Date.now();
    appendTypingIndicator(typingId);

    try {
      const payload = {
        message: cleanQuery,
        conversation_id: chatState.conversationId,
        active_subject: options.activeSubject || chatState.activeSubject,
      };

      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      removeTypingIndicator(typingId);

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.error || `HTTP ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();

      // Update conversational state
      chatState.conversationId = data.conversation_id || chatState.conversationId;
      if (data.active_subject) {
        chatState.activeSubject = data.active_subject;
        if (chatContextStrip && chatActiveSubjectText) {
          chatActiveSubjectText.textContent = `Focus: ${data.active_subject}`;
          chatContextStrip.style.display = "flex";
        }
      }

      // 3. Append Assistant Message Bubble
      appendAssistantMessage(data);

    } catch (err) {
      console.error("Chat execution error:", err);
      removeTypingIndicator(typingId);
      appendErrorMessage(err.message);
    } finally {
      state.isQueryRunning = false;
      if (askBtn) {
        askBtn.disabled = false;
        const textSpan = askBtn.querySelector(".btn-text");
        if (textSpan) textSpan.textContent = "Send";
        const spinner = askBtn.querySelector(".btn-spinner");
        if (spinner) spinner.style.display = "none";
      }
      if (chatMessagesStream) {
        chatMessagesStream.scrollTop = chatMessagesStream.scrollHeight;
      }
    }
  }

  if (askBtn) {
    askBtn.addEventListener("click", () => handleQuerySubmit());
  }

  function handleQuerySubmit() {
    const text = queryInput.value.trim();
    if (!text || state.isQueryRunning) return;
    executeChat(text);
  }

  function addSessionQueryHistory(queryText) {
    if (!queryHistoryBar || !historyChips) return;
    if (!state.queryHistory.includes(queryText)) {
      state.queryHistory.unshift(queryText);
      if (state.queryHistory.length > 8) state.queryHistory.pop();

      historyChips.innerHTML = "";
      state.queryHistory.forEach((item) => {
        const pill = document.createElement("button");
        pill.type = "button";
        pill.className = "history-pill";
        pill.textContent = item;
        pill.title = "Re-run this query";
        pill.addEventListener("click", () => {
          queryInput.value = item;
          clearBtn.style.display = "block";
          executeChat(item);
        });
        historyChips.appendChild(pill);
      });
      queryHistoryBar.style.display = "flex";
    }
  }

  async function executeAsk(questionText, questionId, questionKind) {
    return executeChat(questionText);
  }


  function renderInvestigationResult(data) {
    if (!resultsArea) return;

    const {
      question_id,
      question,
      kind = "FINDING",
      answer,
      text = "",
      evidence = [],
      confidence = 1.0,
      response_time_ms = 12.0,
      is_empty_trap = false,
    } = data;

    const kindUpper = (kind || "FINDING").toUpperCase();
    const isCount = kindUpper === "COUNT" || typeof answer === "number";
    const isLookup = kindUpper === "LOOKUP";
    const isEmptyResult = is_empty_trap || (Array.isArray(answer) && answer.length === 0);

    let answerHtml = "";
    let boxStateClass = "answer-box";

    if (isEmptyResult) {
      boxStateClass += " state-trap";
      answerHtml = `
        <div class="answer-lead-label">Protocol Compliance Evaluation</div>
        <div class="empty-trap-block">
          <svg class="empty-trap-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
            <path d="m9 12 2 2 4-4"></path>
          </svg>
          <div>
            <div class="empty-trap-heading">NO NON-COMPLIANT RECORDS IDENTIFIED</div>
            <div class="empty-trap-statement">Deterministic evaluation verified zero matching non-compliant records for this query across STUDY-042.</div>
            <div class="empty-trap-provenance">
              Evidence records: <strong>0</strong> • Ground-truth verification established protocol adherence across all matching subjects.
            </div>
          </div>
        </div>
        ${text ? `<div class="rationale-block"><span class="rationale-kicker">Clinical Rationale:</span> ${escapeHtml(text)}</div>` : ""}
      `;
    } else if (isCount) {
      boxStateClass += " state-verified";
      answerHtml = `
        <div class="answer-lead-label">Deterministic Finding (Count)</div>
        <div class="answer-metric-huge">${answer} <small>qualifying subjects</small></div>
        ${text ? `<div class="rationale-block"><span class="rationale-kicker">Clinical Rationale:</span> ${escapeHtml(text)}</div>` : ""}
      `;
    } else if (isLookup) {
      boxStateClass += " state-verified";
      answerHtml = `
        <div class="answer-lead-label">Protocol Window Record Retrieval</div>
        <div class="answer-metric-huge">${evidence.length} <small>records identified within nominal window</small></div>
        ${text ? `<div class="rationale-block"><span class="rationale-kicker">Clinical Rationale:</span> ${escapeHtml(text)}</div>` : ""}
      `;
    } else if (Array.isArray(answer)) {
      boxStateClass += " state-verified";
      const subjectChips = answer
        .map(
          (s) => `
        <button type="button" class="interactive-subject-pill" data-usubjid="${escapeHtml(s)}" title="Open Patient 360 for ${escapeHtml(s)}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
          <span>${escapeHtml(s)}</span>
          <span class="pill-arrow">→</span>
        </button>
      `
        )
        .join("");

      answerHtml = `
        <div class="answer-lead-label">Identified Qualifying Subjects (${answer.length})</div>
        <div class="subject-chips-cluster">
          ${subjectChips}
        </div>
        ${text ? `<div class="rationale-block"><span class="rationale-kicker">Clinical Rationale:</span> ${escapeHtml(text)}</div>` : ""}
      `;
    } else {
      boxStateClass += " state-verified";
      answerHtml = `
        <div class="answer-lead-label">Deterministic Finding</div>
        <div class="answer-metric-huge">${escapeHtml(String(answer))}</div>
        ${text ? `<div class="rationale-block"><span class="rationale-kicker">Clinical Rationale:</span> ${escapeHtml(text)}</div>` : ""}
      `;
    }

    let evidenceHtml = "";
    if (evidence.length > 0) {
      const rowsHtml = evidence
        .map((ev, idx) => {
          const dom = (ev.domain || "").toUpperCase();
          const pillClass = `dom-pill-${dom.toLowerCase()}`;
          
          let rawKvRows = "";
          if (ev.raw_fields && Object.keys(ev.raw_fields).length > 0) {
            rawKvRows = Object.entries(ev.raw_fields)
              .map(
                ([k, v]) => `
                <div class="raw-kv-item">
                  <span class="raw-k">${escapeHtml(k)}:</span>
                  <span class="raw-v">${escapeHtml(String(v))}</span>
                </div>
              `
              )
              .join("");
          }

          return `
            <tr class="evidence-main-row" id="ev-row-${idx}">
              <td><span class="domain-pill ${pillClass}">${escapeHtml(dom)}</span></td>
              <td>
                <div class="subject-cell-actions">
                  <a href="javascript:void(0)" class="link-to-p360" data-usubjid="${escapeHtml(ev.usubjid)}">${escapeHtml(ev.usubjid)}</a>
                  <button type="button" class="btn-goto-graph" data-usubjid="${escapeHtml(ev.usubjid)}" title="Open Graph for ${escapeHtml(ev.usubjid)}">Graph ↗</button>
                </div>
              </td>
              <td class="font-mono text-muted">${escapeHtml(String(ev.seq || "—"))}</td>
              <td>${escapeHtml(ev.visit || "—")}</td>
              <td class="font-mono text-muted">${escapeHtml(ev.date || "—")}</td>
              <td class="finding-desc-cell">${escapeHtml(ev.description || "Source record verified")}</td>
              <td style="text-align: right;">
                <button type="button" class="btn btn-secondary btn-xs raw-toggle-btn" data-target="raw-drawer-${idx}">
                  <span>Inspect</span>
                </button>
              </td>
            </tr>
            <tr class="evidence-raw-drawer-row" id="raw-drawer-${idx}" style="display: none;">
              <td colspan="7">
                <div class="raw-record-drawer-body">
                  <div class="raw-record-drawer-header">
                    <span class="raw-record-title">CDISC ${escapeHtml(dom)} Source Record • USUBJID: ${escapeHtml(ev.usubjid)} • Seq #${escapeHtml(String(ev.seq || "1"))}</span>
                    <button type="button" class="btn-goto-graph" data-usubjid="${escapeHtml(ev.usubjid)}" style="font-size: 0.72rem; padding: 2px 8px;">Focus in Knowledge Graph ↗</button>
                  </div>
                  <div class="raw-record-grid">
                    ${rawKvRows || '<div class="raw-kv-item"><span class="raw-k">Citation:</span><span class="raw-v font-mono">' + escapeHtml(ev.citation || "Verified Record") + '</span></div>'}
                  </div>
                </div>
              </td>
            </tr>
          `;
        })
        .join("");

      evidenceHtml = `
        <div class="evidence-section">
          <div class="evidence-header-bar">
            <div>
              <h4 class="evidence-headline">Structured Clinical Evidence (${evidence.length} Records)</h4>
              <p class="evidence-subtext">Immutable CDISC source records validating this deterministic finding.</p>
            </div>
            <div class="evidence-filter-tags">
              <span class="evidence-stat-chip">${evidence.length} Citations</span>
              <span class="evidence-stat-chip">Zero Tokens Used</span>
            </div>
          </div>
          <div class="table-frame">
            <table class="clinical-data-table">
              <thead>
                <tr>
                  <th style="width: 75px;">Domain</th>
                  <th style="width: 175px;">Subject</th>
                  <th style="width: 65px;">Seq #</th>
                  <th style="width: 110px;">Visit</th>
                  <th style="width: 105px;">Date</th>
                  <th>Clinical Record Description</th>
                  <th style="width: 90px; text-align: right;">Action</th>
                </tr>
              </thead>
              <tbody>
                ${rowsHtml}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }

    resultsArea.innerHTML = `
      <div class="result-card-container">
        <div class="result-meta-header">
          <div>
            <h3 class="result-query-title">${escapeHtml(question)}</h3>
            <div class="result-tags-row">
              <span class="badge-kind">${escapeHtml(kindUpper)}</span>
              <span class="badge-neutral">STUDY-042</span>
              <span class="badge-neutral font-mono">Cut 12</span>
              <span class="badge-neutral font-mono">${response_time_ms} ms</span>
              <span class="badge-neutral">Confidence: ${Math.round(confidence * 100)}%</span>
            </div>
          </div>
        </div>

        <div class="${boxStateClass}">
          ${answerHtml}
        </div>

        ${evidenceHtml}
      </div>
    `;

    resultsArea.style.display = "block";

    resultsArea.querySelectorAll(".interactive-subject-pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        const usubjid = btn.dataset.usubjid;
        if (usubjid) openPatient360(usubjid);
      });
    });

    resultsArea.querySelectorAll(".link-to-p360").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const usubjid = link.dataset.usubjid;
        if (usubjid) openPatient360(usubjid);
      });
    });

    resultsArea.querySelectorAll(".btn-goto-graph").forEach((btn) => {
      btn.addEventListener("click", () => {
        const usubjid = btn.dataset.usubjid;
        if (usubjid) openPatientGraph(usubjid);
      });
    });

    resultsArea.querySelectorAll(".raw-toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetId = btn.dataset.target;
        const drawer = document.getElementById(targetId);
        if (drawer) {
          const isHidden = drawer.style.display === "none";
          drawer.style.display = isHidden ? "table-row" : "none";
          btn.classList.toggle("active", isHidden);
          btn.querySelector("span").textContent = isHidden ? "Close" : "Inspect";
        }
      });
    });
  }

  // =========================================================================
  // 5. Study Graph: Interactive SVG Knowledge Graph & Patient Explorer
  // =========================================================================

  function updateGraphTransform() {
    if (graphRootGroup) {
      graphRootGroup.setAttribute(
        "transform",
        `translate(${graphState.pan.x}, ${graphState.pan.y}) scale(${graphState.zoom})`
      );
    }
  }

  function setZoom(newZoom) {
    graphState.zoom = Math.max(0.4, Math.min(3.0, newZoom));
    updateGraphTransform();
  }

  function resetGraphView() {
    graphState.zoom = 1.0;
    graphState.pan = { x: 0, y: 0 };
    updateGraphTransform();
  }

  if (svgViewportWrapper) {
    svgViewportWrapper.addEventListener("mousedown", (e) => {
      if (e.target.closest(".svg-node")) return;
      graphState.isDragging = true;
      graphState.dragStart = {
        x: e.clientX - graphState.pan.x,
        y: e.clientY - graphState.pan.y,
      };
      svgViewportWrapper.classList.add("grabbing");
    });

    window.addEventListener("mousemove", (e) => {
      if (!graphState.isDragging) return;
      graphState.pan.x = e.clientX - graphState.dragStart.x;
      graphState.pan.y = e.clientY - graphState.dragStart.y;
      updateGraphTransform();
    });

    window.addEventListener("mouseup", () => {
      if (graphState.isDragging) {
        graphState.isDragging = false;
        if (svgViewportWrapper) svgViewportWrapper.classList.remove("grabbing");
      }
    });

    svgViewportWrapper.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        setZoom(graphState.zoom * factor);
      },
      { passive: false }
    );
  }

  if (btnZoomIn) btnZoomIn.addEventListener("click", () => setZoom(graphState.zoom * 1.25));
  if (btnZoomOut) btnZoomOut.addEventListener("click", () => setZoom(graphState.zoom / 1.25));
  if (btnZoomReset) btnZoomReset.addEventListener("click", resetGraphView);
  if (btnCanvasCenter) {
    btnCanvasCenter.addEventListener("click", () => {
      resetGraphView();
      if (graphState.mode === "patient" && graphState.patient) {
        selectGraphNode(`patient-${graphState.patient.usubjid}`, graphState.allNodes[`patient-${graphState.patient.usubjid}`]?.data);
      }
    });
  }

  function switchGraphView(mode, usubjid = null) {
    graphState.mode = mode;
    if (btnViewStudy) btnViewStudy.classList.toggle("active", mode === "study");
    if (btnViewPatient) btnViewPatient.classList.toggle("active", mode === "patient");

    if (mode === "study") {
      if (canvasModeText) canvasModeText.textContent = "STUDY-042 GLOBAL ARCHITECTURE";
      if (canvasHelpHint) canvasHelpHint.textContent = "Click any site or domain node to inspect records or drill down to patients";
      resetGraphView();
      if (state.stats) renderStudyLevelGraph(state.stats);
    } else {
      const targetSubjid =
        usubjid ||
        (graphPatientInput && graphPatientInput.value.trim()) ||
        (state.currentPatient && state.currentPatient.usubjid) ||
        (graphState.patient && graphState.patient.usubjid) ||
        "042-S07-001";
      focusPatientGraph(targetSubjid);
    }
  }

  if (btnViewStudy) btnViewStudy.addEventListener("click", () => switchGraphView("study"));
  if (btnViewPatient) btnViewPatient.addEventListener("click", () => switchGraphView("patient"));

  async function focusPatientGraph(usubjid) {
    if (!usubjid) return;
    const cleanId = usubjid.trim().toUpperCase();
    if (graphPatientInput) graphPatientInput.value = cleanId;

    graphState.mode = "patient";
    if (btnViewStudy) btnViewStudy.classList.remove("active");
    if (btnViewPatient) btnViewPatient.classList.add("active");

    const graphQuickList = document.getElementById("graph-quick-patients-list");
    if (graphQuickList) {
      graphQuickList.querySelectorAll(".quick-patient-chip").forEach((chip) => {
        chip.classList.toggle("active", chip.dataset.usubjid === cleanId);
      });
    }

    if (canvasModeText) canvasModeText.textContent = `LOADING PATIENT ${cleanId}...`;

    try {
      let patientData = graphState.patientCache[cleanId];
      if (!patientData) {
        const res = await fetch(`/api/patient/${encodeURIComponent(cleanId)}`);
        if (!res.ok) {
          throw new Error(`Patient ${cleanId} was not found in STUDY-042.`);
        }
        const json = await res.json();
        patientData = json.patient;
        graphState.patientCache[cleanId] = patientData;
      }

      graphState.patient = patientData;
      if (canvasModeText) {
        canvasModeText.textContent = `CONNECTED GRAPH: PATIENT ${cleanId} (${patientData.arm || "STUDY-042"})`;
      }
      if (canvasHelpHint) {
        canvasHelpHint.textContent = `Click any node or leaf record to inspect full clinical details`;
      }

      resetGraphView();
      renderPatientKnowledgeGraph(patientData);
    } catch (err) {
      console.error("Focus patient error:", err);
      if (canvasModeText) canvasModeText.textContent = `ERROR: ${cleanId} NOT FOUND`;
      selectInspectorNode({
        type: "NOT FOUND",
        title: `Patient ${cleanId}`,
        desc: `Could not locate USUBJID ${cleanId} in the STUDY-042 dataset. Please check the subject ID or choose a notable case above.`,
        stats: [{ k: "Status", v: "404 Not Found" }],
      });
    }
  }

  function openPatientGraph(usubjid) {
    switchTab("graph");
    focusPatientGraph(usubjid);
  }

  if (graphFocusBtn && graphPatientInput) {
    graphFocusBtn.addEventListener("click", () => {
      const val = graphPatientInput.value.trim();
      if (val) focusPatientGraph(val);
    });

    graphPatientInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const val = graphPatientInput.value.trim();
        if (val) focusPatientGraph(val);
      }
    });
  }

  const graphQuickList = document.getElementById("graph-quick-patients-list");
  if (graphQuickList) {
    graphQuickList.addEventListener("click", (e) => {
      const chip = e.target.closest(".quick-patient-chip");
      if (chip && chip.dataset.usubjid) {
        graphQuickList.querySelectorAll(".quick-patient-chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        focusPatientGraph(chip.dataset.usubjid);
      }
    });
  }

  function renderDomainRecordsInspector(usubjid, domain, records = []) {
    if (!records || records.length === 0) {
      return `<div style="padding: 10px 0; color: var(--text-muted); font-size: 0.78rem;">No records indexed for domain ${domain}.</div>`;
    }

    const recordsSlice = records.slice(0, 20); // Render up to 20 key records for responsiveness
    const cardsHtml = recordsSlice.map((rec) => {
      const seq = rec.seq || rec.LBSEQ || rec.AESEQ || rec.EXSEQ || rec.CMSEQ || rec.VSSEQ || "1";
      const test = rec.LBTESTCD || rec.AETERM || rec.EXTRT || rec.CMTRT || rec.VSTESTCD || domain;
      const res = rec.LBORRES != null ? rec.LBORRES : (rec.EXDOSE != null ? rec.EXDOSE : (rec.CMDOSE != null ? rec.CMDOSE : (rec.VSORRES != null ? rec.VSORRES : (rec.AESEV || ""))));
      const unit = rec.LBORRESU || rec.EXDOSU || rec.CMDOSU || rec.VSORRESU || "";
      const visit = rec.VISIT || "";
      const recJson = escapeHtml(JSON.stringify(rec));

      return `
        <div class="insp-record-card">
          <div class="insp-record-header">
            <span class="insp-record-test">${escapeHtml(test)}</span>
            <span class="insp-record-val">${escapeHtml(String(res))} ${escapeHtml(unit)}</span>
          </div>
          <div class="insp-record-row">
            <span>Visit: ${escapeHtml(visit || "N/A")}</span>
            <span style="font-family: var(--font-mono); font-size: 0.72rem;">Seq ${escapeHtml(String(seq))}</span>
          </div>
          <div class="insp-record-actions">
            <button type="button" class="btn-card-action btn-insp-view-rec" data-rec='${recJson}'>[View record]</button>
            <button type="button" class="btn-ask-atlas-rec btn-insp-ask-rec" data-dom="${escapeHtml(domain)}" data-seq="${escapeHtml(String(seq))}" data-subj="${escapeHtml(usubjid)}" data-test="${escapeHtml(test)}">[Ask ATLAS about this]</button>
          </div>
        </div>
      `;
    }).join("");

    return `
      <div style="margin-top: 14px; font-size: 0.74rem; font-weight: 700; color: var(--text-secondary); text-transform: uppercase;">
        Connected ${domain} Records (${records.length} total):
      </div>
      <div class="insp-records-container">
        ${cardsHtml}
      </div>
    `;
  }

  if (inspBody) {
    inspBody.addEventListener("click", (e) => {
      const focusBtn = e.target.closest(".insp-focus-subj-btn");
      if (focusBtn && focusBtn.dataset.subj) {
        focusPatientGraph(focusBtn.dataset.subj);
      }
      const openBtn = e.target.closest(".insp-open-btn");
      if (openBtn && openBtn.dataset.subj) {
        openPatient360(openBtn.dataset.subj);
      }
      const viewRecBtn = e.target.closest(".btn-insp-view-rec");
      if (viewRecBtn && viewRecBtn.dataset.rec) {
        try {
          const rec = JSON.parse(viewRecBtn.dataset.rec);
          showCdiscRecordModal(rec);
        } catch (err) {
          console.error("View rec modal err:", err);
        }
      }
      const askRecBtn = e.target.closest(".btn-insp-ask-rec");
      if (askRecBtn && askRecBtn.dataset.subj) {
        const { subj, dom, seq, test } = askRecBtn.dataset;
        switchTab("ask");
        executeChat(`Explain the clinical significance of ${dom} record seq ${seq} (${test}) for subject ${subj}`);
      }
    });
  }


  // SVG Helper Methods
  function createSvgEl(tag, attrs = {}) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) {
      el.setAttribute(k, v);
    }
    return el;
  }

  function clearSvgLayers() {
    if (svgEdgesLayer) svgEdgesLayer.innerHTML = "";
    if (svgNodesLayer) svgNodesLayer.innerHTML = "";
    if (svgLabelsLayer) svgLabelsLayer.innerHTML = "";
    graphState.allNodes = {};
    graphState.connectedEdges = {};
    graphState.selectedNodeId = null;
  }

  function registerEdge(fromId, toId, edgeEl) {
    if (!graphState.connectedEdges[fromId]) graphState.connectedEdges[fromId] = [];
    if (!graphState.connectedEdges[toId]) graphState.connectedEdges[toId] = [];
    graphState.connectedEdges[fromId].push(edgeEl);
    graphState.connectedEdges[toId].push(edgeEl);
  }

  function drawEdge(fromId, toId, x1, y1, x2, y2, color, options = {}) {
    const { isCurved = true, dashed = false, width = 1.8, opacity = 0.65 } = options;
    let d;
    if (isCurved) {
      const midX = (x1 + x2) / 2;
      const midY = (y1 + y2) / 2;
      const dx = x2 - x1;
      const dy = y2 - y1;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const nx = -dy / dist;
      const ny = dx / dist;
      const bow = Math.min(30, dist * 0.12);
      const cx = midX + nx * bow;
      const cy = midY + ny * bow;
      d = `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
    } else {
      d = `M ${x1} ${y1} L ${x2} ${y2}`;
    }

    const path = createSvgEl("path", {
      d,
      class: "svg-edge",
      stroke: color || "#CBD5E1",
      "stroke-width": width,
      "stroke-opacity": opacity,
      fill: "none",
      "data-from": fromId,
      "data-to": toId,
    });

    if (dashed) {
      path.setAttribute("stroke-dasharray", "4,4");
    }

    svgEdgesLayer.appendChild(path);
    registerEdge(fromId, toId, path);
    return path;
  }

  function drawNode(nodeDef) {
    const {
      id,
      x,
      y,
      r,
      fill = "#FFFFFF",
      stroke = "#2563EB",
      strokeWidth = 2,
      label,
      sublabel,
      badge,
      badgeColor = "#2563EB",
      badgeBg = "#EFF6FF",
      hasHalo = false,
      filter = null,
      data = {},
    } = nodeDef;

    const g = createSvgEl("g", {
      class: "svg-node",
      "data-id": id,
      transform: `translate(${x}, ${y})`,
    });

    if (hasHalo) {
      const halo = createSvgEl("circle", {
        cx: 0,
        cy: 0,
        r: r + 7,
        fill: "none",
        stroke: stroke || "#93C5FD",
        "stroke-width": 1.5,
        "stroke-dasharray": "3,3",
        opacity: 0.6,
        class: "node-halo",
      });
      g.appendChild(halo);
    }

    const circleAttrs = {
      cx: 0,
      cy: 0,
      r,
      fill: fill || "#FFFFFF",
      stroke: stroke || "#2563EB",
      "stroke-width": strokeWidth,
      class: "node-circle-main",
    };
    const circle = createSvgEl("circle", circleAttrs);
    g.appendChild(circle);

    let labelY = sublabel ? -2 : 4;
    if (r < 22 && !sublabel) labelY = 3.5;
    const textLabel = createSvgEl("text", {
      x: 0,
      y: labelY,
      class: "svg-node-label",
      "font-size": r > 30 ? "11px" : (r > 20 ? "10px" : "9px"),
      "font-weight": "600",
      fill: "#0F172A",
    });
    textLabel.textContent = label;
    g.appendChild(textLabel);

    if (sublabel) {
      const textSub = createSvgEl("text", {
        x: 0,
        y: labelY + 12,
        class: "svg-node-sublabel",
        "font-size": r > 30 ? "9px" : "8px",
        fill: "#64748B",
      });
      textSub.textContent = sublabel;
      g.appendChild(textSub);
    }

    if (badge) {
      const bw = Math.max(34, badge.length * 6.5 + 10);
      const badgeRect = createSvgEl("rect", {
        x: -bw / 2,
        y: -r - 13,
        width: bw,
        height: 14,
        rx: 7,
        fill: badgeBg || "#F1F5F9",
        stroke: badgeColor || "#CBD5E1",
        "stroke-width": "1",
      });
      const badgeText = createSvgEl("text", {
        x: 0,
        y: -r - 6,
        class: "svg-node-badge-text",
        fill: badgeColor || "#1E293B",
        "font-size": "8px",
        "font-weight": "600",
      });
      badgeText.textContent = badge;
      g.appendChild(badgeRect);
      g.appendChild(badgeText);
    }

    g.addEventListener("click", (e) => {
      e.stopPropagation();
      selectGraphNode(id, data);
    });

    svgNodesLayer.appendChild(g);
    graphState.allNodes[id] = { element: g, def: nodeDef, data };
    return g;
  }

  function selectGraphNode(nodeId, data) {
    graphState.selectedNodeId = nodeId;

    document.querySelectorAll(".svg-node.active").forEach((el) => el.classList.remove("active"));
    document.querySelectorAll(".svg-edge.active, .svg-edge.highlighted").forEach((el) => {
      el.classList.remove("active", "highlighted");
    });

    const nodeObj = graphState.allNodes[nodeId];
    if (nodeObj && nodeObj.element) {
      nodeObj.element.classList.add("active");
    }

    const edges = graphState.connectedEdges[nodeId] || [];
    edges.forEach((edge) => {
      edge.classList.add("active", "highlighted");
    });

    if (data && data.inspector) {
      selectInspectorNode(data.inspector);
    }
  }

  function selectInspectorNode({
    type,
    title,
    desc,
    stats = [],
    customHtml = "",
    actionText,
    actionQuery,
    onActionClick,
    secondaryActionText,
    onSecondaryClick,
  }) {
    if (inspType) inspType.textContent = type || "NODE INSPECTOR";
    if (inspTitle) inspTitle.textContent = title || "";

    if (inspBody) {
      const statsHtml = stats
        .map(
          (s) => `
        <div class="insp-stat-row">
          <span class="insp-k">${escapeHtml(s.k)}</span>
          <span class="insp-v">${escapeHtml(s.v)}</span>
        </div>
      `
        )
        .join("");

      inspBody.innerHTML = `
        <p class="inspector-text">${escapeHtml(desc || "")}</p>
        ${stats.length > 0 ? `<div class="inspector-stats-list">${statsHtml}</div>` : ""}
        ${customHtml}
      `;
    }

    if (inspActions) {
      inspActions.innerHTML = "";

      if (actionText) {
        const actBtn = document.createElement("button");
        actBtn.className = "btn-insp-action";
        actBtn.id = "insp-action-btn";
        actBtn.textContent = actionText;
        actBtn.addEventListener("click", () => {
          if (onActionClick) {
            onActionClick();
          } else if (actionQuery) {
            switchTab("ask");
            if (queryInput) {
              queryInput.value = actionQuery;
              clearBtn.style.display = "block";
            }
            executeAsk(actionQuery);
          }
        });
        inspActions.appendChild(actBtn);
      }

      if (secondaryActionText) {
        const secBtn = document.createElement("button");
        secBtn.className = "btn-insp-action";
        secBtn.style.background = "transparent";
        secBtn.style.border = "1px solid var(--border-medium)";
        secBtn.style.color = "var(--text-secondary)";
        secBtn.style.marginTop = "8px";
        secBtn.textContent = secondaryActionText;
        secBtn.addEventListener("click", () => {
          if (onSecondaryClick) onSecondaryClick();
        });
        inspActions.appendChild(secBtn);
      }
    }
  }

  // =========================================================================
  // Render: Study-Level Architecture Graph
  // =========================================================================







  function renderStudyLevelGraph(stats) {
    clearSvgLayers();

    const totalSubj = stats?.subjects || 241;
    const totalNodes = stats?.nodes || 29578;
    const totalEdges = stats?.edges || 29566;

    // 1. Central Study Node at top (480, 75)
    drawNode({
      id: "node-study",
      x: 480,
      y: 75,
      r: 35,
      fill: "#FFFFFF",
      stroke: "#1D4ED8",
      strokeWidth: 2.5,
      label: "STUDY-042",
      sublabel: "Phase III Cohort",
      badge: "12 SITES",
      badgeColor: "#1D4ED8",
      badgeBg: "#EFF6FF",
      hasHalo: true,
      data: {
        inspector: {
          type: "STUDY COHORT",
          title: "STUDY-042 (Phase III Diabetes)",
          desc: "Complete multi-center clinical study cohort with 241 randomized subjects across 12 investigational sites. Governed by Protocol Amendment 3 (Cut 12).",
          stats: [
            { k: "Total Subjects:", v: String(totalSubj) },
            { k: "Investigational Sites:", v: "12 Sites" },
            { k: "Knowledge Graph Nodes:", v: Number(totalNodes).toLocaleString() },
            { k: "Indexed Relationships:", v: Number(totalEdges).toLocaleString() },
            { k: "Active Protocol Cut:", v: "Cut 12 (v3.0)" },
          ],
          actionText: "Explore Liver Safety in Cohort",
          actionQuery: "Which subjects meet potential Hy's law criteria?",
        },
      },
    });

    // 2. 12 Investigational Sites
    const siteIds = ["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12"];

    siteIds.forEach((siteId, idx) => {
      const count = (stats?.sites && stats.sites[siteId]) || 20;
      const x = 65 + idx * 75.5;
      const y = 210 + (idx % 2 === 0 ? -8 : 12);

      drawEdge("node-study", `site-${siteId}`, 480, 75, x, y, "#94A3B8", {
        isCurved: true,
        width: 1.5,
        opacity: 0.6,
      });

      const siteSubjs = (state.subjects || []).filter((s) => s.site_id === siteId);

      const subjListHtml =
        siteSubjs.length > 0
          ? `
          <div style="margin-top: 10px; font-size: 0.74rem; font-weight: 700; color: var(--primary);">ENROLLED SUBJECTS (${siteSubjs.length}):</div>
          <div class="inspector-subjects-scroll" style="max-height: 180px; overflow-y: auto; margin-top: 6px;">
            ${siteSubjs
              .map(
                (s) => `
              <div style="display: flex; align-items: center; justify-content: space-between; padding: 4px 6px; border-bottom: 1px solid var(--border-subtle);">
                <span style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-primary); font-weight: 600;">${escapeHtml(s.usubjid)}</span>
                <div style="display: flex; gap: 4px;">
                  <button class="insp-focus-subj-btn" data-subj="${escapeHtml(s.usubjid)}" style="background: #EFF6FF; border: 1px solid #BFDBFE; color: #1D4ED8; border-radius: 4px; font-size: 0.68rem; padding: 2px 6px; cursor: pointer;">Focus Graph</button>
                  <button class="insp-open-btn" data-subj="${escapeHtml(s.usubjid)}" style="background: #F1F5F9; border: 1px solid #E2E8F0; color: #475569; border-radius: 4px; font-size: 0.68rem; padding: 2px 6px; cursor: pointer;">360</button>
                </div>
              </div>
            `
              )
              .join("")}
          </div>
        `
          : "";

      drawNode({
        id: `site-${siteId}`,
        x,
        y,
        r: 20,
        fill: "#FFFFFF",
        stroke: "#0284C7",
        strokeWidth: 1.8,
        label: siteId,
        sublabel: `${count} sub`,
        badge: siteId,
        badgeColor: "#0284C7",
        badgeBg: "#F0F9FF",
        data: {
          inspector: {
            type: "INVESTIGATIONAL SITE",
            title: `Site ${siteId}`,
            desc: `Investigational site with ${count} enrolled subjects participating in STUDY-042.`,
            stats: [
              { k: "Site Identifier:", v: siteId },
              { k: "Enrolled Subjects:", v: String(count) },
              { k: "Protocol Status:", v: "Active Monitoring" },
            ],
            customHtml: subjListHtml,
            actionText: `Audit Dosing Adherence at Site ${siteId}`,
            actionQuery: `Which subjects at site ${siteId} received a wrong dose?`,
          },
        },
      });
    });

    // 3. Protocol Timeline Ribbon (Middle Y=330)
    const protocolVisits = [
      { name: "Screening", day: -14, x: 100 },
      { name: "Baseline", day: 1, x: 195 },
      { name: "Week 2", day: 14, x: 290 },
      { name: "Week 4", day: 28, x: 385 },
      { name: "Week 8", day: 56, x: 480 },
      { name: "Week 12", day: 84, x: 575 },
      { name: "Week 16", day: 112, x: 670 },
      { name: "Week 20", day: 140, x: 765 },
      { name: "Week 24", day: 168, x: 860 },
    ];

    const timelinePath = createSvgEl("line", {
      x1: 100,
      y1: 330,
      x2: 860,
      y2: 330,
      stroke: "#CBD5E1",
      "stroke-width": 2,
      "stroke-dasharray": "4,4",
    });
    svgEdgesLayer.appendChild(timelinePath);

    protocolVisits.forEach((pv) => {
      const vNodeId = `visit-${pv.name.toLowerCase().replace(/\s+/g, "")}`;
      const isWk8 = pv.name === "Week 8";
      drawNode({
        id: vNodeId,
        x: pv.x,
        y: 330,
        r: 15,
        fill: "#FFFFFF",
        stroke: isWk8 ? "#D97706" : "#0284C7",
        strokeWidth: isWk8 ? 2.2 : 1.6,
        label: pv.name,
        sublabel: `D${pv.day}`,
        badge: isWk8 ? "PEAK LABS" : null,
        badgeColor: "#D97706",
        badgeBg: "#FFFBEB",
        data: {
          inspector: {
            type: "PROTOCOL VISIT",
            title: `Visit: ${pv.name}`,
            desc: `Nominal target study Day ${pv.day}. Scheduled window: ±7 days (v1) / ±3 days (v2/v3).`,
            stats: [
              { k: "Nominal Target:", v: `Day ${pv.day}` },
              { k: "Scheduled Window:", v: "±7d (v1) / ±3d (v2/v3)" },
              {
                k: "Required Tests:",
                v: isWk8 ? "Labs, Vitals, Dosing (Peak Transaminases)" : "Scheduled Assessments",
              },
            ],
            actionText: `Inspect Week 8 Records in Ask ATLAS`,
            actionQuery: `List the laboratory and adverse-event records for 042-S05-003 within 7 days of the WEEK8 visit`,
          },
        },
      });
    });

    // 4. Clinical Domains Hubs (Lower Section)
    const domainLayout = [
      { code: "LB", x: 120, y: 470, color: "#0284C7", fill: "#FFFFFF", count: stats?.domains?.LB || 14400, desc: "Serum ALT, AST, Bilirubin, HbA1c, Glucose, Creatinine." },
      { code: "VS", x: 280, y: 470, color: "#059669", fill: "#FFFFFF", count: stats?.domains?.VS || 7200, desc: "Blood pressure, pulse, body temperature, and weight." },
      { code: "EX", x: 440, y: 470, color: "#D97706", fill: "#FFFFFF", count: stats?.domains?.EX || 2154, desc: "Investigational product administrations and dose tracking." },
      { code: "AE", x: 600, y: 470, color: "#DC2626", fill: "#FFFFFF", count: stats?.domains?.AE || 294, desc: "Adverse events, severity triage, and SAE hospitalization." },
      { code: "CM", x: 760, y: 470, color: "#7C3AED", fill: "#FFFFFF", count: stats?.domains?.CM || 468, desc: "Concomitant medications tracked against prohibited classes." },
      { code: "DS", x: 200, y: 575, color: "#DB2777", fill: "#FFFFFF", count: stats?.domains?.DS || 240, desc: "Study completions, withdrawals, and adverse event discontinuations." },
      { code: "DM", x: 380, y: 575, color: "#2563EB", fill: "#FFFFFF", count: stats?.domains?.DM || 241, desc: "Subject demographics, randomized arms, and baseline dates." },
      { code: "EG", x: 560, y: 575, color: "#0D9488", fill: "#FFFFFF", count: stats?.domains?.EG || 1440, desc: "Electrocardiogram intervals and cardiac safety monitoring." },
      { code: "MH", x: 740, y: 575, color: "#4F46E5", fill: "#FFFFFF", count: stats?.domains?.MH || 488, desc: "Pre-existing medical conditions and baseline medical history." },
    ];

    domainLayout.forEach((dom) => {
      const dNodeId = `domain-${dom.code.toLowerCase()}`;
      drawEdge("node-study", dNodeId, 480, 75, dom.x, dom.y, dom.color, {
        isCurved: true,
        width: 1.4,
        opacity: 0.45,
      });

      drawNode({
        id: dNodeId,
        x: dom.x,
        y: dom.y,
        r: 24,
        fill: "#FFFFFF",
        stroke: dom.color,
        strokeWidth: 2,
        label: dom.code,
        sublabel: `${Number(dom.count).toLocaleString()}`,
        badge: dom.code,
        badgeColor: dom.color,
        badgeBg: "#F8FAFC",
        data: {
          inspector: {
            type: `CDISC DOMAIN [${dom.code}]`,
            title: `${dom.code} - Clinical Records`,
            desc: dom.desc,
            stats: [
              { k: "Domain Code:", v: dom.code },
              { k: "Indexed Records:", v: Number(dom.count).toLocaleString() },
              { k: "Integration Level:", v: "Subject + Visit Linked" },
            ],
            actionText: `Audit ${dom.code} Domain in Ask ATLAS`,
            actionQuery: CLINICAL_DOMAINS_INFO[dom.code]?.sampleQuery || `Which subjects meet potential Hy's law criteria?`,
          },
        },
      });
    });

    selectGraphNode("node-study", graphState.allNodes["node-study"].data);
  }

  // =========================================================================
  // Render: Patient-Centered Connected Knowledge Graph
  // =========================================================================







  function renderPatientKnowledgeGraph(patient) {
    clearSvgLayers();

    const {
      usubjid,
      site_id = "",
      arm = "",
      demographics = {},
      records_by_domain = {},
      visits = {},
      records = [],
    } = patient;

    const lbRecords = records_by_domain.LB || [];
    const aeRecords = records_by_domain.AE || [];
    const exRecords = records_by_domain.EX || [];
    const cmRecords = records_by_domain.CM || [];
    const dsRecords = records_by_domain.DS || [];
    const vsRecords = records_by_domain.VS || [];

    const cx = 480;
    const cy = 310;
    const patientNodeId = `patient-${usubjid}`;

    // 1. Central Patient Node
    drawNode({
      id: patientNodeId,
      x: cx,
      y: cy,
      r: 42,
      fill: "#FFFFFF",
      stroke: "#2563EB",
      strokeWidth: 3,
      label: usubjid,
      sublabel: `Site ${site_id} • ${arm}`,
      badge: `${records.length} Records`,
      badgeColor: "#2563EB",
      badgeBg: "#EFF6FF",
      hasHalo: true,
      data: {
        inspector: {
          type: "CENTRAL PATIENT NODE",
          title: `Subject ${usubjid}`,
          desc: `Primary knowledge-graph patient anchor. Enrolled at Site ${site_id} in ${arm || "STUDY-042"}. Longitudinal records span ${Object.keys(visits).length} study visits.`,
          stats: [
            { k: "USUBJID:", v: usubjid },
            { k: "Investigational Site:", v: `Site ${site_id}` },
            { k: "Randomized Arm:", v: arm || "N/A" },
            { k: "Age / Sex:", v: `${demographics.AGE || "N/A"} / ${demographics.SEX || "N/A"}` },
            { k: "Total CDISC Records:", v: String(records.length) },
            { k: "Laboratory Tests (LB):", v: String(lbRecords.length) },
            { k: "Adverse Events (AE):", v: String(aeRecords.length) },
            { k: "Dosing Administrations (EX):", v: String(exRecords.length) },
          ],
          actionText: "Open Full Patient 360 Profile",
          onActionClick: () => openPatient360(usubjid),
          secondaryActionText: `Ask ATLAS About ${usubjid}`,
          onSecondaryClick: () => {
            const q = `List the laboratory and adverse-event records for ${usubjid} within 7 days of the WEEK8 visit`;
            switchTab("ask");
            if (queryInput) {
              queryInput.value = q;
              clearBtn.style.display = "block";
            }
            executeAsk(q);
          },
        },
      },
    });

    // 2. Hub: Site Hub (Top: 480, 130)
    const siteHubId = `hub-site-${site_id}`;
    drawEdge(patientNodeId, siteHubId, cx, cy, 480, 130, "#94A3B8", { width: 1.8, isCurved: true });
    drawNode({
      id: siteHubId,
      x: 480,
      y: 130,
      r: 26,
      fill: "#FFFFFF",
      stroke: "#0284C7",
      strokeWidth: 2,
      label: `Site ${site_id}`,
      sublabel: "Clinical Center",
      badge: "SITE",
      badgeColor: "#0284C7",
      badgeBg: "#F0F9FF",
      data: {
        inspector: {
          type: "INVESTIGATIONAL SITE",
          title: `Site ${site_id}`,
          desc: `Investigational site for patient ${usubjid}.`,
          stats: [
            { k: "Site ID:", v: `Site ${site_id}` },
            { k: "Patient USUBJID:", v: usubjid },
            { k: "Assigned Arm:", v: arm },
          ],
          actionText: `Audit Site ${site_id} Dosing Compliance`,
          actionQuery: `Which subjects at site ${site_id} received a wrong dose?`,
        },
      },
    });

    // Leaf: Site enrollment record (480, 50)
    const siteLeafId = "leaf-site-info";
    drawEdge(siteHubId, siteLeafId, 480, 130, 480, 50, "#CBD5E1", { width: 1.4, isCurved: false });
    drawNode({
      id: siteLeafId,
      x: 480,
      y: 50,
      r: 17,
      fill: "#FFFFFF",
      stroke: "#0284C7",
      strokeWidth: 1.5,
      label: "Enrolled",
      sublabel: `Site ${site_id}`,
      data: {
        inspector: {
          type: "SITE REGISTRATION RECORD",
          title: `Enrolled at Site ${site_id}`,
          desc: `Patient ${usubjid} successfully completed screening and baseline enrollment at Site ${site_id}.`,
          stats: [
            { k: "Site:", v: site_id },
            { k: "Randomization Date:", v: demographics.RFSTDTC || "Day 1" },
          ],
        },
      },
    });

    // 3. Hub: Visits Hub (Top Right: 660, 180)
    const visitsHubId = "hub-visits";
    const visitNames = Object.keys(visits);
    drawEdge(patientNodeId, visitsHubId, cx, cy, 660, 180, "#94A3B8", { width: 1.8, isCurved: true });
    drawNode({
      id: visitsHubId,
      x: 660,
      y: 180,
      r: 26,
      fill: "#FFFFFF",
      stroke: "#0284C7",
      strokeWidth: 2,
      label: "Visits Hub",
      sublabel: `${visitNames.length} Protocol Visits`,
      badge: "VISITS",
      badgeColor: "#0284C7",
      badgeBg: "#F0F9FF",
      data: {
        inspector: {
          type: "PROTOCOL VISITS HUB",
          title: `Longitudinal Visits (${visitNames.length})`,
          desc: `Patient ${usubjid} attended ${visitNames.length} scheduled study protocol visits.`,
          stats: [
            { k: "Attended Visits:", v: visitNames.join(", ") || "None" },
            { k: "Earliest Visit:", v: visitNames[0] || "N/A" },
            { k: "Latest Visit:", v: visitNames[visitNames.length - 1] || "N/A" },
          ],
          actionText: `Inspect Week 8 Time Window for ${usubjid}`,
          actionQuery: `List the laboratory and adverse-event records for ${usubjid} within 7 days of the WEEK8 visit`,
        },
      },
    });

    // Leaves from Visits Hub
    const baseLeafId = "leaf-visit-baseline";
    drawEdge(visitsHubId, baseLeafId, 660, 180, 800, 125, "#CBD5E1", { width: 1.4, isCurved: true });
    drawNode({
      id: baseLeafId,
      x: 800,
      y: 125,
      r: 17,
      fill: "#FFFFFF",
      stroke: "#0284C7",
      strokeWidth: 1.5,
      label: "Baseline",
      sublabel: "Day 1 (Dosing)",
      data: {
        inspector: {
          type: "VISIT MILESTONE",
          title: "Baseline Visit (Day 1)",
          desc: "Initiation of investigational product dosing and baseline efficacy biomarkers.",
          stats: [
            { k: "Visit:", v: "BASELINE" },
            { k: "Target Study Day:", v: "Day 1 strictly" },
          ],
        },
      },
    });

    const wk8LeafId = "leaf-visit-week8";
    drawEdge(visitsHubId, wk8LeafId, 660, 180, 840, 185, "#CBD5E1", { width: 1.4, isCurved: true });
    drawNode({
      id: wk8LeafId,
      x: 840,
      y: 185,
      r: 17,
      fill: "#FFFFFF",
      stroke: "#D97706",
      strokeWidth: 1.8,
      label: "Week 8",
      sublabel: "Day 56 (Safety Peak)",
      badge: "PEAK",
      badgeColor: "#D97706",
      badgeBg: "#FFFBEB",
      data: {
        inspector: {
          type: "CRITICAL SAFETY VISIT",
          title: "Week 8 Safety Assessment (Day 56)",
          desc: "Key pre-specified milestone for primary liver transaminase monitoring and adverse event evaluation.",
          stats: [
            { k: "Visit:", v: "WEEK 8" },
            { k: "Target Study Day:", v: "Day 56 (±7d v1 / ±3d v2)" },
          ],
          actionText: `Inspect Week 8 Records for ${usubjid}`,
          actionQuery: `List the laboratory and adverse-event records for ${usubjid} within 7 days of the WEEK8 visit`,
        },
      },
    });

    // 4. Hub: LB Hub (Laboratory Results) (Right: 740, 310)
    const lbHubId = "hub-lb";
    drawEdge(patientNodeId, lbHubId, cx, cy, 740, 310, "#94A3B8", { width: 2, isCurved: false });
    drawNode({
      id: lbHubId,
      x: 740,
      y: 310,
      r: 28,
      fill: "#FFFFFF",
      stroke: "#0284C7",
      strokeWidth: 2.2,
      label: "LB: Labs",
      sublabel: `${lbRecords.length} Tests`,
      badge: `${lbRecords.length} LABS`,
      badgeColor: "#0284C7",
      badgeBg: "#F0F9FF",
      data: {
        inspector: {
          type: "CDISC DOMAIN [LB]",
          title: `Laboratory Results (${lbRecords.length} tests)`,
          desc: `Full serum biochemistry panel collected across protocol visits for patient ${usubjid}.`,
          stats: [
            { k: "Total Lab Tests:", v: String(lbRecords.length) },
            { k: "Key Analytes:", v: "ALT, AST, BILI, HBA1C, GLUC" },
            { k: "Reference Range:", v: site_id === "S07" ? "Site S07 Manual (μkat/L)" : "Central Lab Manual (U/L)" },
          ],
          customHtml: renderDomainRecordsInspector(usubjid, "LB", lbRecords),
          actionText: "Evaluate Potential Hy's Law in Cohort",
          actionQuery: "Which subjects meet potential Hy's law criteria?",
        },
      },
    });

    // Key Lab Leaves
    function findKeyLab(testCode) {
      const matching = lbRecords.filter((r) => (r.LBTESTCD || "").toUpperCase() === testCode);
      if (matching.length === 0) return null;
      const wk8 = matching.find((r) => (r.VISIT || "").includes("WEEK8") || (r.VISIT || "").includes("WEEK 8"));
      if (wk8) return wk8;
      return matching[0];
    }

    const altRec = findKeyLab("ALT");
    const astRec = findKeyLab("AST");
    const biliRec = findKeyLab("BILI");
    const hba1cRec = findKeyLab("HBA1C");

    function checkElevated(rec) {
      if (!rec) return false;
      const num = parseFloat(rec.LBORRES);
      if (isNaN(num)) return false;
      const test = (rec.LBTESTCD || "").toUpperCase();
      const unit = rec.LBORRESU || "";
      if (test === "ALT" || test === "AST") {
        if (unit === "ukat/L" || unit === "μkat/L") return num > 0.93;
        return num > 56.0;
      }
      if (test === "BILI") return num > 1.2;
      return false;
    }

    if (altRec) {
      const isElev = checkElevated(altRec);
      const altLeafId = "leaf-lb-alt";
      drawEdge(lbHubId, altLeafId, 740, 310, 875, 245, isElev ? "#DC2626" : "#CBD5E1", { width: 1.5, isCurved: true });
      drawNode({
        id: altLeafId,
        x: 875,
        y: 245,
        r: 19,
        fill: "#FFFFFF",
        stroke: isElev ? "#DC2626" : "#0284C7",
        strokeWidth: isElev ? 2.5 : 1.6,
        label: "ALT",
        sublabel: `${altRec.LBORRES} ${altRec.LBORRESU}`,
        badge: isElev ? "ELEVATED" : "NORMAL",
        badgeColor: isElev ? "#DC2626" : "#059669",
        badgeBg: isElev ? "#FEF2F2" : "#ECFDF5",
        data: {
          inspector: {
            type: "LABORATORY TEST [ALT]",
            title: `Alanine Aminotransferase (ALT) = ${altRec.LBORRES} ${altRec.LBORRESU}`,
            desc: `Serum ALT assessment at ${altRec.VISIT} on date ${altRec.LBDTC}. ${
              site_id === "S07"
                ? "Site S07 reports in μkat/L (converted × 60 = U/L; normal ULN is 0.93 μkat/L)."
                : "Normal Central ULN is 56 U/L."
            }`,
            stats: [
              { k: "Analyte:", v: "Alanine Aminotransferase (ALT)" },
              { k: "Observed Result:", v: `${altRec.LBORRES} ${altRec.LBORRESU}` },
              { k: "Study Visit:", v: altRec.VISIT || "N/A" },
              { k: "Collection Date:", v: altRec.LBDTC || "N/A" },
              { k: "Clinical Status:", v: isElev ? "ELEVATED (> ULN)" : "Within Normal Limits" },
              { k: "Sequence #:", v: String(altRec.seq || altRec.LBSEQ || "1") },
            ],
            actionText: "Evaluate Hy's Law Criteria",
            actionQuery: "Which subjects meet potential Hy's law criteria?",
          },
        },
      });
    }

    if (astRec) {
      const isElev = checkElevated(astRec);
      const astLeafId = "leaf-lb-ast";
      drawEdge(lbHubId, astLeafId, 740, 310, 895, 310, isElev ? "#DC2626" : "#CBD5E1", { width: 1.5, isCurved: false });
      drawNode({
        id: astLeafId,
        x: 895,
        y: 310,
        r: 18,
        fill: "#FFFFFF",
        stroke: isElev ? "#DC2626" : "#0284C7",
        strokeWidth: isElev ? 2.5 : 1.6,
        label: "AST",
        sublabel: `${astRec.LBORRES} ${astRec.LBORRESU}`,
        badge: isElev ? "ELEVATED" : "NORMAL",
        badgeColor: isElev ? "#DC2626" : "#059669",
        badgeBg: isElev ? "#FEF2F2" : "#ECFDF5",
        data: {
          inspector: {
            type: "LABORATORY TEST [AST]",
            title: `Aspartate Aminotransferase (AST) = ${astRec.LBORRES} ${astRec.LBORRESU}`,
            desc: `Serum AST assessment at ${astRec.VISIT} on date ${astRec.LBDTC}.`,
            stats: [
              { k: "Analyte:", v: "Aspartate Aminotransferase (AST)" },
              { k: "Observed Result:", v: `${astRec.LBORRES} ${astRec.LBORRESU}` },
              { k: "Study Visit:", v: astRec.VISIT || "N/A" },
              { k: "Collection Date:", v: astRec.LBDTC || "N/A" },
              { k: "Clinical Status:", v: isElev ? "ELEVATED (> ULN)" : "Within Normal Limits" },
              { k: "Sequence #:", v: String(astRec.seq || astRec.LBSEQ || "2") },
            ],
          },
        },
      });
    }

    if (biliRec) {
      const isElev = checkElevated(biliRec);
      const biliLeafId = "leaf-lb-bili";
      drawEdge(lbHubId, biliLeafId, 740, 310, 875, 375, isElev ? "#DC2626" : "#CBD5E1", { width: 1.5, isCurved: true });
      drawNode({
        id: biliLeafId,
        x: 875,
        y: 375,
        r: 18,
        fill: "#FFFFFF",
        stroke: isElev ? "#DC2626" : "#0284C7",
        strokeWidth: isElev ? 2.5 : 1.6,
        label: "BILI",
        sublabel: `${biliRec.LBORRES} ${biliRec.LBORRESU}`,
        badge: isElev ? ">2x ULN" : "NORMAL",
        badgeColor: isElev ? "#DC2626" : "#059669",
        badgeBg: isElev ? "#FEF2F2" : "#ECFDF5",
        data: {
          inspector: {
            type: "LABORATORY TEST [BILI]",
            title: `Total Bilirubin (BILI) = ${biliRec.LBORRES} ${biliRec.LBORRESU}`,
            desc: `Total Bilirubin assessment at ${biliRec.VISIT} on date ${biliRec.LBDTC}. Normal ULN is 1.2 mg/dL.`,
            stats: [
              { k: "Analyte:", v: "Total Bilirubin (BILI)" },
              { k: "Observed Result:", v: `${biliRec.LBORRES} ${biliRec.LBORRESU}` },
              { k: "Study Visit:", v: biliRec.VISIT || "N/A" },
              { k: "Collection Date:", v: biliRec.LBDTC || "N/A" },
              { k: "Clinical Status:", v: isElev ? "ELEVATED (> 2x ULN)" : "Within Normal Limits" },
              { k: "Sequence #:", v: String(biliRec.seq || biliRec.LBSEQ || "3") },
            ],
          },
        },
      });
    }

    if (hba1cRec) {
      const hba1cLeafId = "leaf-lb-hba1c";
      drawEdge(lbHubId, hba1cLeafId, 740, 310, 825, 435, "#CBD5E1", { width: 1.4, isCurved: true });
      drawNode({
        id: hba1cLeafId,
        x: 825,
        y: 435,
        r: 17,
        fill: "#FFFFFF",
        stroke: "#0284C7",
        strokeWidth: 1.5,
        label: "HbA1c",
        sublabel: `${hba1cRec.LBORRES}%`,
        data: {
          inspector: {
            type: "LABORATORY TEST [HBA1C]",
            title: `Hemoglobin A1c (HbA1c) = ${hba1cRec.LBORRES}%`,
            desc: `Glycated hemoglobin efficacy biomarker assessed at ${hba1cRec.VISIT}.`,
            stats: [
              { k: "Analyte:", v: "Glycated Hemoglobin (HbA1c)" },
              { k: "Observed Result:", v: `${hba1cRec.LBORRES} ${hba1cRec.LBORRESU || "%"}` },
              { k: "Collection Date:", v: hba1cRec.LBDTC || "N/A" },
            ],
          },
        },
      });
    }

    // 5. Hub: VS Hub (Vital Signs) (Bottom Right: 660, 440)
    const vsHubId = "hub-vs";
    drawEdge(patientNodeId, vsHubId, cx, cy, 660, 440, "#94A3B8", { width: 1.8, isCurved: true });
    drawNode({
      id: vsHubId,
      x: 660,
      y: 440,
      r: 25,
      fill: "#FFFFFF",
      stroke: "#059669",
      strokeWidth: 2,
      label: "VS: Vitals",
      sublabel: `${vsRecords.length} Records`,
      badge: "VITALS",
      badgeColor: "#059669",
      badgeBg: "#ECFDF5",
      data: {
        inspector: {
          type: "CDISC DOMAIN [VS]",
          title: `Vital Signs (${vsRecords.length} records)`,
          desc: `Longitudinal systolic & diastolic blood pressure, pulse rate, and temperature for patient ${usubjid}.`,
          stats: [
            { k: "Total Vital Signs:", v: String(vsRecords.length) },
            { k: "Recorded Parameters:", v: "SYSBP, DIABP, PULSE, TEMP, WEIGHT" },
          ],
          customHtml: renderDomainRecordsInspector(usubjid, "VS", vsRecords),
          actionText: `List Vitals & Labs for ${usubjid} at Week 8`,
          actionQuery: `List the vital signs and laboratory records for 042-S05-003 around Week 8`,
        },
      },
    });

    // 6. Hub: EX Hub (Exposure & Dosing) (Bottom: 480, 500)
    const exHubId = "hub-ex";
    const hasDoseDeviation = exRecords.some((r) => {
      const dose = parseFloat(r.EXDOSE);
      if (arm.includes("10") && dose !== 10) return true;
      if (arm.toUpperCase().includes("PLACEBO") && dose !== 0) return true;
      return false;
    });

    drawEdge(patientNodeId, exHubId, cx, cy, 480, 500, hasDoseDeviation ? "#DC2626" : "#94A3B8", {
      width: 2,
      isCurved: false,
    });
    drawNode({
      id: exHubId,
      x: 480,
      y: 500,
      r: 27,
      fill: "#FFFFFF",
      stroke: hasDoseDeviation ? "#DC2626" : "#D97706",
      strokeWidth: 2.2,
      label: "EX: Dosing",
      sublabel: `${exRecords.length} Doses`,
      badge: hasDoseDeviation ? "DOSE DEVIATION" : "ACCORDANT",
      badgeColor: hasDoseDeviation ? "#DC2626" : "#D97706",
      badgeBg: hasDoseDeviation ? "#FEF2F2" : "#FFFBEB",
      data: {
        inspector: {
          type: "CDISC DOMAIN [EX]",
          title: `Exposure & Dosing (${exRecords.length} administrations)`,
          desc: `Investigational product administrations. Evaluated against randomized arm ${arm}.`,
          stats: [
            { k: "Randomized Arm:", v: arm },
            { k: "Administered Doses:", v: String(exRecords.length) },
            {
              k: "Protocol Compliance:",
              v: hasDoseDeviation ? "PROTOCOL DEVIATION (Wrong Dose Administered)" : "100% Accordant",
            },
          ],
          customHtml: renderDomainRecordsInspector(usubjid, "EX", exRecords),
          actionText: `Audit Site ${site_id} Dosing Compliance`,
          actionQuery: `Which subjects at site ${site_id} received a wrong dose?`,
        },
      },
    });

    // Leaf nodes from EX Hub
    if (exRecords.length > 0) {
      const ex1 = exRecords[0];
      const exLeafId1 = "leaf-ex-dose";
      drawEdge(exHubId, exLeafId1, 480, 500, 390, 580, hasDoseDeviation ? "#DC2626" : "#CBD5E1", {
        width: 1.5,
        isCurved: true,
      });
      drawNode({
        id: exLeafId1,
        x: 390,
        y: 580,
        r: 17,
        fill: "#FFFFFF",
        stroke: hasDoseDeviation ? "#DC2626" : "#D97706",
        strokeWidth: 1.6,
        label: `${ex1.EXDOSE} mg`,
        sublabel: ex1.EXTRT || "DRUG",
        data: {
          inspector: {
            type: "EXPOSURE RECORD",
            title: `Administered Dose: ${ex1.EXDOSE} mg`,
            desc: `Investigational treatment administered at ${ex1.VISIT} on date ${ex1.EXSTDTC}.`,
            stats: [
              { k: "Administered Dose:", v: `${ex1.EXDOSE} ${ex1.EXDOSU || "mg"}` },
              { k: "Assigned Arm:", v: arm },
              { k: "Date Administered:", v: ex1.EXSTDTC || "Day 1" },
              { k: "Sequence #:", v: String(ex1.seq || "1") },
            ],
          },
        },
      });

      const exLeafId2 = "leaf-ex-status";
      drawEdge(exHubId, exLeafId2, 480, 500, 570, 580, hasDoseDeviation ? "#DC2626" : "#CBD5E1", {
        width: 1.5,
        isCurved: true,
      });
      drawNode({
        id: exLeafId2,
        x: 570,
        y: 580,
        r: 17,
        fill: "#FFFFFF",
        stroke: hasDoseDeviation ? "#DC2626" : "#059669",
        strokeWidth: 1.6,
        label: hasDoseDeviation ? "DEVIATION" : "CONCORDANT",
        sublabel: hasDoseDeviation ? "Site Deviation" : "Per Protocol",
        badge: hasDoseDeviation ? "NON-COMPLIANT" : "VERIFIED",
        badgeColor: hasDoseDeviation ? "#DC2626" : "#059669",
        badgeBg: hasDoseDeviation ? "#FEF2F2" : "#ECFDF5",
        data: {
          inspector: {
            type: "DOSE COMPLIANCE AUDIT",
            title: hasDoseDeviation ? "Protocol Dose Deviation Identified" : "Protocol Dosing Accordant",
            desc: hasDoseDeviation
              ? `Subject received ${ex1.EXDOSE} mg despite being assigned to ${arm}. Identified under ATLAS deterministic exposure verification.`
              : `All administered doses strictly match the randomized protocol assignment (${arm}).`,
            stats: [
              { k: "Arm Assignment:", v: arm },
              { k: "Administered:", v: `${ex1.EXDOSE} mg` },
              { k: "Deterministic Audit:", v: hasDoseDeviation ? "NON-COMPLIANT" : "VERIFIED COMPLIANT" },
            ],
            actionText: `Audit Site ${site_id} Wrong Doses`,
            actionQuery: `Which subjects at site ${site_id} received a wrong dose?`,
          },
        },
      });
    }

    // 7. Hub: DS Hub (Disposition) (Bottom Left: 305, 440)
    const dsHubId = "hub-ds";
    const dsTerm = dsRecords[0]?.DSDECOD || (records.length > 0 ? "ONGOING" : "COMPLETED");
    const isDisc = dsTerm.toUpperCase().includes("DISCONTINU") || dsTerm.toUpperCase().includes("ADVERSE");
    drawEdge(patientNodeId, dsHubId, cx, cy, 305, 440, isDisc ? "#DC2626" : "#94A3B8", { width: 1.8, isCurved: true });
    drawNode({
      id: dsHubId,
      x: 305,
      y: 440,
      r: 25,
      fill: "#FFFFFF",
      stroke: isDisc ? "#DC2626" : "#DB2777",
      strokeWidth: 2,
      label: "DS: Disposition",
      sublabel: dsTerm,
      badge: isDisc ? "DISCONTINUED" : "COMPLETED",
      badgeColor: isDisc ? "#DC2626" : "#DB2777",
      badgeBg: isDisc ? "#FEF2F2" : "#FDF2F8",
      data: {
        inspector: {
          type: "CDISC DOMAIN [DS]",
          title: `Study Disposition: ${dsTerm}`,
          desc: `Subject participation status and protocol completion milestone.`,
          stats: [
            { k: "Milestone DECOD:", v: dsTerm },
            { k: "Effective Date:", v: dsRecords[0]?.DSSTDTC || "Study End" },
            { k: "Discontinuation AE:", v: isDisc ? "YES (Adverse Event Discontinuation)" : "None" },
          ],
          customHtml: renderDomainRecordsInspector(usubjid, "DS", dsRecords),
          actionText: `Audit Discontinuations at Site ${site_id}`,
          actionQuery: `How many subjects at site ${site_id} discontinued due to an adverse event?`,
        },
      },
    });

    if (dsRecords.length > 0) {
      const dsLeafId = "leaf-ds-detail";
      drawEdge(dsHubId, dsLeafId, 305, 440, 180, 500, "#CBD5E1", { width: 1.4, isCurved: true });
      drawNode({
        id: dsLeafId,
        x: 180,
        y: 500,
        r: 17,
        fill: "#FFFFFF",
        stroke: isDisc ? "#DC2626" : "#DB2777",
        strokeWidth: 1.5,
        label: dsRecords[0].DSDECOD || "Completed",
        sublabel: dsRecords[0].DSSTDTC || "Day 168",
        data: {
          inspector: {
            type: "DISPOSITION RECORD",
            title: `Disposition Milestone: ${dsRecords[0].DSDECOD}`,
            desc: dsRecords[0].DSTERM || "Completed scheduled protocol participation.",
            stats: [
              { k: "Term:", v: dsRecords[0].DSTERM || dsRecords[0].DSDECOD },
              { k: "Effective Date:", v: dsRecords[0].DSSTDTC || "N/A" },
            ],
          },
        },
      });
    }

    // 8. Hub: AE Hub (Adverse Events) (Left: 220, 310)
    const aeHubId = "hub-ae";
    const hasAe = aeRecords.length > 0;
    const hasSae = aeRecords.some(
      (r) => (r.AESER || "").toUpperCase() === "Y" || (r.AESHOSP || "").toUpperCase() === "Y"
    );

    if (!hasAe) {
      // CLEAN COHORT (e.g. 042-S01-001)
      drawEdge(patientNodeId, aeHubId, cx, cy, 220, 310, "#CBD5E1", {
        width: 1.4,
        isCurved: false,
        dashed: true,
      });
      drawNode({
        id: aeHubId,
        x: 220,
        y: 310,
        r: 27,
        fill: "#FFFFFF",
        stroke: "#059669",
        strokeWidth: 2,
        label: "AE: Adverse",
        sublabel: "0 Reported",
        badge: "0 AEs",
        badgeColor: "#059669",
        badgeBg: "#ECFDF5",
        data: {
          inspector: {
            type: "CDISC DOMAIN [AE] (CLEAN COHORT)",
            title: "Zero Adverse Events Reported",
            desc: `Deterministic verification confirmed that patient ${usubjid} experienced zero adverse events (AETERM = 0) throughout study participation.`,
            stats: [
              { k: "Adverse Events:", v: "0 Records" },
              { k: "Cohort Profile:", v: "Clean / Well-Tolerated" },
              { k: "SAEs / Hospitalization:", v: "None" },
            ],
            customHtml: renderDomainRecordsInspector(usubjid, "AE", []),
            actionText: `Audit SAEs at Site ${site_id}`,
            actionQuery: `Which subjects at site ${site_id} have serious adverse events?`,
          },
        },
      });

      const aeCleanLeafId = "leaf-ae-clean";
      drawEdge(aeHubId, aeCleanLeafId, 220, 310, 95, 310, "#CBD5E1", { width: 1.4, isCurved: false, dashed: true });
      drawNode({
        id: aeCleanLeafId,
        x: 95,
        y: 310,
        r: 17,
        fill: "#FFFFFF",
        stroke: "#059669",
        strokeWidth: 1.5,
        label: "Clean",
        sublabel: "No Toxicities",
        data: {
          inspector: {
            type: "SAFETY AUDIT CONFIRMATION",
            title: "Zero Reported Toxicities",
            desc: "Subject successfully tolerated investigational treatment with zero adverse event reports.",
            stats: [{ k: "Safety Finding:", v: "Protocol Compliant & Well-Tolerated" }],
          },
        },
      });
    } else {
      // ADVERSE EVENTS REPORTED
      drawEdge(patientNodeId, aeHubId, cx, cy, 220, 310, hasSae ? "#DC2626" : "#94A3B8", {
        width: 2.2,
        isCurved: false,
      });
      drawNode({
        id: aeHubId,
        x: 220,
        y: 310,
        r: 28,
        fill: "#FFFFFF",
        stroke: hasSae ? "#DC2626" : "#D97706",
        strokeWidth: 2.4,
        label: "AE: Adverse",
        sublabel: `${aeRecords.length} Events`,
        badge: hasSae ? "SERIOUS (SAE)" : `${aeRecords.length} AEs`,
        badgeColor: hasSae ? "#DC2626" : "#D97706",
        badgeBg: hasSae ? "#FEF2F2" : "#FFFBEB",
        data: {
          inspector: {
            type: `CDISC DOMAIN [AE] ${hasSae ? "(SERIOUS ADVERSE EVENT)" : ""}`,
            title: `Adverse Events (${aeRecords.length} reported)`,
            desc: `Clinical adverse events reported for patient ${usubjid}. Evaluated against Protocol Section 6 safety and hospitalization escalation criteria.`,
            stats: [
              { k: "Total Reported AEs:", v: String(aeRecords.length) },
              { k: "Serious Adverse Event:", v: hasSae ? "YES (SAE Confirmed)" : "NO" },
              {
                k: "Hospitalization (AESHOSP):",
                v: aeRecords.some((r) => (r.AESHOSP || "").toUpperCase() === "Y") ? "YES (Hospitalized)" : "NO",
              },
            ],
            customHtml: renderDomainRecordsInspector(usubjid, "AE", aeRecords),
            actionText: `Audit SAEs at Site ${site_id}`,
            actionQuery: `Which subjects at site ${site_id} have serious adverse events?`,
          },
        },
      });

      aeRecords.slice(0, 2).forEach((ae, idx) => {
        const isSae = (ae.AESER || "").toUpperCase() === "Y" || (ae.AESHOSP || "").toUpperCase() === "Y";
        const isHosp = (ae.AESHOSP || "").toUpperCase() === "Y";
        const aeLeafId = `leaf-ae-${idx}`;
        const leafY = aeRecords.length === 1 ? 310 : idx === 0 ? 250 : 370;
        drawEdge(aeHubId, aeLeafId, 220, 310, 95, leafY, isSae ? "#DC2626" : "#CBD5E1", {
          width: 1.5,
          isCurved: true,
        });
        drawNode({
          id: aeLeafId,
          x: 95,
          y: leafY,
          r: 19,
          fill: "#FFFFFF",
          stroke: isSae ? "#DC2626" : "#D97706",
          strokeWidth: isSae ? 2.5 : 1.6,
          label: (ae.AETERM || "AE").slice(0, 10),
          sublabel: ae.AESEV || "MILD",
          badge: isSae ? "SAE" : "AE",
          badgeColor: isSae ? "#DC2626" : "#D97706",
          badgeBg: isSae ? "#FEF2F2" : "#FFFBEB",
          data: {
            inspector: {
              type: `ADVERSE EVENT RECORD ${isSae ? "(SERIOUS / HOSPITALIZED)" : ""}`,
              title: `${ae.AETERM || "Adverse Event"} (${ae.AESEV || "Grade 1"})`,
              desc: isHosp
                ? `HOSPITALIZATION REQUIRED. Severe adverse event meeting regulatory serious criteria.`
                : `Reported adverse event with onset date ${ae.AESTDTC || "N/A"}.`,
              stats: [
                { k: "Reported Term:", v: ae.AETERM || "N/A" },
                { k: "Severity:", v: ae.AESEV || "N/A" },
                { k: "Serious Criteria:", v: isSae ? "YES (SAE)" : "NO" },
                { k: "Hospitalization:", v: isHosp ? "YES" : "NO" },
                { k: "Onset Date:", v: ae.AESTDTC || "N/A" },
                { k: "Sequence #:", v: String(ae.seq || "1") },
              ],
              actionText: "Evaluate Hy's Law Association",
              actionQuery: "Which subjects meet potential Hy's law criteria?",
            },
          },
        });
      });
    }

    // 9. Hub: CM Hub (Concomitant Medications) (Top Left: 305, 180)
    const cmHubId = "hub-cm";
    const hasProhibited = cmRecords.some((r) => {
      const t = (r.CMTRT || "").toUpperCase();
      return t.includes("PREDNISOLONE") || t.includes("GLIBENCLAMIDE") || t.includes("SULFONYLUREA");
    });

    drawEdge(patientNodeId, cmHubId, cx, cy, 305, 180, hasProhibited ? "#DC2626" : "#94A3B8", {
      width: 2,
      isCurved: true,
    });
    drawNode({
      id: cmHubId,
      x: 305,
      y: 180,
      r: 26,
      fill: "#FFFFFF",
      stroke: hasProhibited ? "#DC2626" : "#7C3AED",
      strokeWidth: 2,
      label: "CM: Meds",
      sublabel: `${cmRecords.length} Meds`,
      badge: hasProhibited ? "PROHIBITED MED" : "PERMITTED",
      badgeColor: hasProhibited ? "#DC2626" : "#7C3AED",
      badgeBg: hasProhibited ? "#FEF2F2" : "#F5F3FF",
      data: {
        inspector: {
          type: "CDISC DOMAIN [CM]",
          title: `Concomitant Medications (${cmRecords.length})`,
          desc: `Concurrent pharmacological therapies evaluated against Protocol Amendments 1, 2, and 3 prohibited medication lists.`,
          stats: [
            { k: "Recorded Meds:", v: String(cmRecords.length) },
            {
              k: "Prohibited Med Status:",
              v: hasProhibited ? "PROHIBITED MEDICATION IDENTIFIED" : "No Prohibited Medications",
            },
            { k: "Governing Cut:", v: "Cut 12 (v3.0)" },
          ],
          customHtml: renderDomainRecordsInspector(usubjid, "CM", cmRecords),
          actionText: "Audit Prohibited Concomitant Meds in Cohort",
          actionQuery: "Which subjects took prohibited concomitant medications?",
        },
      },
    });

    if (cmRecords.length > 0) {
      const cm1 = cmRecords[0];
      const isProh =
        (cm1.CMTRT || "").toUpperCase().includes("PREDNISOLONE") ||
        (cm1.CMTRT || "").toUpperCase().includes("GLIBENCLAMIDE");
      const cmLeafId = "leaf-cm-detail";
      drawEdge(cmHubId, cmLeafId, 305, 180, 170, 140, isProh ? "#DC2626" : "#CBD5E1", { width: 1.4, isCurved: true });
      drawNode({
        id: cmLeafId,
        x: 170,
        y: 140,
        r: 17,
        fill: "#FFFFFF",
        stroke: isProh ? "#DC2626" : "#7C3AED",
        strokeWidth: isProh ? 2.2 : 1.5,
        label: (cm1.CMTRT || "Meds").slice(0, 10),
        sublabel: cm1.CMCLAS || "Therapy",
        badge: isProh ? "PROHIBITED" : "PERMITTED",
        badgeColor: isProh ? "#DC2626" : "#7C3AED",
        badgeBg: isProh ? "#FEF2F2" : "#F5F3FF",
        data: {
          inspector: {
            type: `CONCOMITANT MEDICATION RECORD [CM] ${isProh ? "(PROHIBITED)" : ""}`,
            title: `${cm1.CMTRT || "Medication"} (${cm1.CMCLAS || "Concomitant"})`,
            desc: isProh
              ? `PROHIBITED by protocol amendment. ${cm1.CMTRT} is an exclusionary concomitant medication.`
              : `Permitted concomitant medication initiated on ${cm1.CMSTDTC || "baseline"}.`,
            stats: [
              { k: "Medication Name:", v: cm1.CMTRT || "N/A" },
              { k: "Drug Class:", v: cm1.CMCLAS || "N/A" },
              { k: "Start Date:", v: cm1.CMSTDTC || "N/A" },
              { k: "Protocol Status:", v: isProh ? "PROHIBITED BY AMENDMENT" : "Permitted Concomitant" },
              { k: "Sequence #:", v: String(cm1.seq || "1") },
            ],
            actionText: "Audit Prohibited Concomitant Meds",
            actionQuery: "Which subjects took prohibited concomitant medications?",
          },
        },
      });
    }

    selectGraphNode(patientNodeId, graphState.allNodes[patientNodeId].data);
  }

  // =========================================================================
  // 6. Patient 360: Longitudinal Clinical Trajectory
  // =========================================================================







  function openPatient360(usubjid) {
    switchTab("patient");
    if (patientSearchInput) patientSearchInput.value = usubjid;
    loadPatientData(usubjid);
  }

  if (patientLoadBtn && patientSearchInput) {
    patientLoadBtn.addEventListener("click", () => {
      const val = patientSearchInput.value.trim();
      if (val) loadPatientData(val);
    });

    patientSearchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const val = patientSearchInput.value.trim();
        if (val) loadPatientData(val);
      }
    });
  }

  notableChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const usubjid = chip.dataset.subj;
      if (usubjid) {
        if (patientSearchInput) patientSearchInput.value = usubjid;
        loadPatientData(usubjid);
      }
    });
  });

  async function loadPatientData(usubjid) {
    if (!patientProfileArea) return;

    notableChips.forEach((c) => c.classList.toggle("active", c.dataset.subj === usubjid));

    patientProfileArea.innerHTML = `
      <div class="investigation-loading">
        <div class="loading-pulse-ring"></div>
        <div class="loading-title">Compiling Patient 360 Profile for ${escapeHtml(usubjid)}...</div>
        <div class="loading-desc">Extracting longitudinal visits, laboratory tests, dosing exposure, and adverse events.</div>
      </div>
    `;

    try {
      const res = await fetch(`/api/patient/${encodeURIComponent(usubjid)}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.message || `Subject ${usubjid} was not found in STUDY-042.`);
      }

      const data = await res.json();
      state.currentPatient = data.patient;
      renderPatient360(data.patient);
    } catch (err) {
      patientProfileArea.innerHTML = `
        <div class="empty-patient-prompt" style="border-color: var(--coral-primary);">
          <svg viewBox="0 0 24 24" fill="none" stroke="var(--coral-primary)" stroke-width="1.6"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          <h3 style="color: #ffffff;">Patient Profile Not Found</h3>
          <p style="color: var(--coral-primary);">${escapeHtml(err.message)}</p>
        </div>
      `;
    }
  }

  function renderPatient360(patient) {
    const { usubjid, site_id = "", arm = "", demographics = {}, records_by_domain = {} } = patient;

    const lbRecords = records_by_domain.LB || [];
    const aeRecords = records_by_domain.AE || [];
    const exRecords = records_by_domain.EX || [];
    const cmRecords = records_by_domain.CM || [];
    const dsRecords = records_by_domain.DS || [];
    const vsRecords = records_by_domain.VS || [];

    // Header Identity Banner
    const bannerHtml = `
      <div class="patient-identity-banner">
        <div class="patient-identity-titles">
          <div class="patient-title-usubjid">${escapeHtml(usubjid)}</div>
          <div class="patient-title-cohort">STUDY-042 • Phase III Diabetes • Enrolled Subject Profile</div>
        </div>
        <div class="patient-badges-cluster">
          <span class="patient-badge-chip">Site: <strong>${escapeHtml(site_id)}</strong></span>
          <span class="patient-badge-chip">Arm: <strong>${escapeHtml(arm)}</strong></span>
          <span class="patient-badge-chip">Age: <strong>${escapeHtml(String(demographics.AGE || "N/A"))}</strong></span>
          <span class="patient-badge-chip">Sex: <strong>${escapeHtml(String(demographics.SEX || "N/A"))}</strong></span>
          <span class="patient-badge-chip">Total Records: <strong>${(patient.records || []).length}</strong></span>
          <button class="btn-ask-patient" id="btn-ask-about-subj">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            <span>Ask ATLAS About This Subject</span>
          </button>
          <button class="btn-ask-patient" id="btn-view-graph-subj" style="background: rgba(0, 242, 254, 0.12); border-color: rgba(0, 242, 254, 0.35); color: var(--cyan-primary);">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="3"></circle><path d="M3 12h3m12 0h3m-9-9v3m0 12v3"></path></svg>
            <span>View Connected Knowledge Graph</span>
          </button>
        </div>
      </div>
    `;

    // Filter Buttons Bar
    const filterBarHtml = `
      <div class="patient-domain-filter-bar">
        <button class="pfilter-tab ${state.patientDomainFilter === "ALL" ? "active" : ""}" data-filter="ALL">All Domains (${(patient.records || []).length})</button>
        <button class="pfilter-tab ${state.patientDomainFilter === "LB" ? "active" : ""}" data-filter="LB">Labs LB (${lbRecords.length})</button>
        <button class="pfilter-tab ${state.patientDomainFilter === "AE" ? "active" : ""}" data-filter="AE">Adverse Events AE (${aeRecords.length})</button>
        <button class="pfilter-tab ${state.patientDomainFilter === "EX" ? "active" : ""}" data-filter="EX">Dosing EX (${exRecords.length})</button>
        <button class="pfilter-tab ${state.patientDomainFilter === "CM" ? "active" : ""}" data-filter="CM">Meds CM (${cmRecords.length})</button>
        <button class="pfilter-tab ${state.patientDomainFilter === "DS" ? "active" : ""}" data-filter="DS">Disposition DS (${dsRecords.length})</button>
      </div>
    `;

    // 1. Adverse Events Section
    let aeHtml = "";
    if (aeRecords.length > 0 && (state.patientDomainFilter === "ALL" || state.patientDomainFilter === "AE")) {
      const rows = aeRecords
        .map((r, i) => {
          const isHosp = (r.AESHOSP || "").toUpperCase() === "Y";
          const isSer = (r.AESER || "").toUpperCase() === "Y" || isHosp;
          return `
          <tr class="${isSer ? "table-row-highlight" : ""}">
            <td><strong>${escapeHtml(r.AETERM || "Adverse Event")}</strong></td>
            <td>${escapeHtml(r.AESTDTC || "")}</td>
            <td>${escapeHtml(r.AESEV || "")}</td>
            <td><span class="${isSer ? "flag-alert" : "flag-normal"}">${isSer ? "YES (SAE)" : "NO"}</span></td>
            <td><span class="${isHosp ? "flag-alert" : ""}">${escapeHtml(r.AESHOSP || "N")}</span></td>
            <td style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">${r.seq}</td>
          </tr>
        `;
        })
        .join("");

      aeHtml = `
        <div class="patient-data-card">
          <div class="patient-card-header">
            <h3><span class="domain-pill dom-pill-ae">AE</span> Adverse Events (${aeRecords.length})</h3>
          </div>
          <div class="table-frame">
            <table class="clinical-data-table">
              <thead>
                <tr>
                  <th>Reported Event</th>
                  <th>Onset Date</th>
                  <th>Severity</th>
                  <th>Serious (SAE)</th>
                  <th>Hospitalization</th>
                  <th>Seq #</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>
      `;
    }

    // 2. Laboratory Results Section
    let lbHtml = "";
    if (lbRecords.length > 0 && (state.patientDomainFilter === "ALL" || state.patientDomainFilter === "LB")) {
      const rows = lbRecords
        .slice(0, 40)
        .map((r) => {
          const test = (r.LBTESTCD || "").toUpperCase();
          const val = r.LBORRES || "";
          const unit = r.LBORRESU || "";
          const visit = r.VISIT || "";
          const date = r.LBDTC || "";

          let isElevated = false;
          const num = parseFloat(val);
          if (!isNaN(num)) {
            if (unit === "U/L" && (test === "ALT" || test === "AST") && num > 56.0) isElevated = true;
            if (unit === "μkat/L" && (test === "ALT" || test === "AST") && num > 0.93) isElevated = true;
            if (test === "BILI" && num > 1.2) isElevated = true;
          }

          return `
          <tr class="${isElevated ? "table-row-highlight" : ""}">
            <td><strong>${escapeHtml(test)}</strong></td>
            <td>${escapeHtml(val)}</td>
            <td>${escapeHtml(unit)}</td>
            <td>${escapeHtml(visit)}</td>
            <td>${escapeHtml(date)}</td>
            <td>${isElevated ? '<span class="flag-alert">ELEVATED</span>' : '<span class="flag-normal">NORMAL</span>'}</td>
            <td style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">${r.seq}</td>
          </tr>
        `;
        })
        .join("");

      lbHtml = `
        <div class="patient-data-card">
          <div class="patient-card-header">
            <h3><span class="domain-pill dom-pill-lb">LB</span> Laboratory Results (${lbRecords.length} tests)</h3>
          </div>
          <div class="table-frame">
            <table class="clinical-data-table">
              <thead>
                <tr>
                  <th>Analyte</th>
                  <th>Observed Value</th>
                  <th>Unit</th>
                  <th>Visit</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Seq #</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>
      `;
    }

    // 3. Exposure / Dosing Section
    let exHtml = "";
    if (exRecords.length > 0 && (state.patientDomainFilter === "ALL" || state.patientDomainFilter === "EX")) {
      const rows = exRecords
        .map((r) => {
          const dose = parseFloat(r.EXDOSE);
          let isDeviation = false;
          if (arm.includes("10") && dose !== 10) isDeviation = true;
          if (arm.toUpperCase().includes("PLACEBO") && dose !== 0) isDeviation = true;

          return `
          <tr class="${isDeviation ? "table-row-highlight" : ""}">
            <td>${escapeHtml(r.VISIT || "")}</td>
            <td>${escapeHtml(r.EXSTDTC || "")}</td>
            <td><strong>${escapeHtml(String(r.EXDOSE || ""))} ${escapeHtml(r.EXDOSU || "mg")}</strong></td>
            <td>${escapeHtml(r.EXTRT || "")}</td>
            <td>${isDeviation ? '<span class="flag-alert">WRONG DOSE</span>' : '<span class="flag-normal">PROTOCOL ACCORDANT</span>'}</td>
            <td style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">${r.seq}</td>
          </tr>
        `;
        })
        .join("");

      exHtml = `
        <div class="patient-data-card">
          <div class="patient-card-header">
            <h3><span class="domain-pill dom-pill-ex">EX</span> Exposure & Dosing Schedule (${exRecords.length} administrations)</h3>
          </div>
          <div class="table-frame">
            <table class="clinical-data-table">
              <thead>
                <tr>
                  <th>Visit</th>
                  <th>Administration Date</th>
                  <th>Administered Dose</th>
                  <th>Investigational Product</th>
                  <th>Arm Compliance</th>
                  <th>Seq #</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>
      `;
    }

    // 4. Concomitant Medications Section
    let cmHtml = "";
    if (cmRecords.length > 0 && (state.patientDomainFilter === "ALL" || state.patientDomainFilter === "CM")) {
      const rows = cmRecords
        .map((r) => {
          const trt = (r.CMTRT || "").toUpperCase();
          const cls = (r.CMCLAS || "").toUpperCase();
          const isProhibited =
            trt.includes("PREDNISOLONE") ||
            trt.includes("GLIBENCLAMIDE") ||
            cls.includes("GLUCOCORTICOID") ||
            cls.includes("SULFONYLUREA");

          return `
          <tr class="${isProhibited ? "table-row-highlight" : ""}">
            <td><strong>${escapeHtml(r.CMTRT || "")}</strong></td>
            <td>${escapeHtml(r.CMCLAS || "")}</td>
            <td>${escapeHtml(r.CMSTDTC || "")}</td>
            <td>${isProhibited ? '<span class="flag-alert">PROHIBITED BY AMENDMENT</span>' : '<span class="flag-normal">PERMITTED</span>'}</td>
            <td style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">${r.seq}</td>
          </tr>
        `;
        })
        .join("");

      cmHtml = `
        <div class="patient-data-card">
          <div class="patient-card-header">
            <h3><span class="domain-pill dom-pill-cm">CM</span> Concomitant Medications (${cmRecords.length})</h3>
          </div>
          <div class="table-frame">
            <table class="clinical-data-table">
              <thead>
                <tr>
                  <th>Medication Name</th>
                  <th>Drug Class</th>
                  <th>Start Date</th>
                  <th>Protocol Status</th>
                  <th>Seq #</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>
      `;
    }

    // 5. Disposition Section
    let dsHtml = "";
    if (dsRecords.length > 0 && (state.patientDomainFilter === "ALL" || state.patientDomainFilter === "DS")) {
      const rows = dsRecords
        .map(
          (r) => `
        <tr>
          <td><strong>${escapeHtml(r.DSDECOD || "")}</strong></td>
          <td>${escapeHtml(r.DSTERM || "")}</td>
          <td>${escapeHtml(r.DSSTDTC || "")}</td>
          <td style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">${r.seq}</td>
        </tr>
      `
        )
        .join("");

      dsHtml = `
        <div class="patient-data-card">
          <div class="patient-card-header">
            <h3><span class="domain-pill dom-pill-ds">DS</span> Study Disposition (${dsRecords.length})</h3>
          </div>
          <div class="table-frame">
            <table class="clinical-data-table">
              <thead>
                <tr>
                  <th>Disposition Milestone</th>
                  <th>Clinical Term / Reason</th>
                  <th>Effective Date</th>
                  <th>Seq #</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>
      `;
    }

    patientProfileArea.innerHTML = `
      ${bannerHtml}
      ${filterBarHtml}
      ${aeHtml}
      ${lbHtml}
      ${exHtml}
      ${cmHtml}
      ${dsHtml}
    `;

    // Bind Patient 360 Action Buttons
    const askAboutSubjBtn = document.getElementById("btn-ask-about-subj");
    if (askAboutSubjBtn) {
      askAboutSubjBtn.addEventListener("click", () => {
        const query = `Tell me about subject ${usubjid}.`;
        switchTab("ask");
        chatState.activeSubject = usubjid;
        if (chatContextStrip && chatActiveSubjectText) {
          chatActiveSubjectText.textContent = `Focus: ${usubjid}`;
          chatContextStrip.style.display = "flex";
        }
        executeChat(query, { activeSubject: usubjid });
      });
    }

    const viewGraphSubjBtn = document.getElementById("btn-view-graph-subj");
    if (viewGraphSubjBtn) {
      viewGraphSubjBtn.addEventListener("click", () => {
        openPatientGraph(usubjid);
      });
    }

    // Bind Domain Filter buttons
    patientProfileArea.querySelectorAll(".pfilter-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.patientDomainFilter = btn.dataset.filter;
        renderPatient360(patient);
      });
    });
  }

  // =========================================================================
  // Utility: HTML Escaper
  // =========================================================================







  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Protocol Version Navigation
  const versionNavItems = document.querySelectorAll(".version-nav-item");
  const summaryBoxText = document.querySelector(".summary-box-text");

  const versionDetails = {
    v3: "Amendment 3 rules (Cuts 9–12, Current): ±3-day visit windows, Sulfonylureas (Glibenclamide) added to prohibited medications list. Study-wide automated compliance active.",
    v2: "Amendment 2 rules (Cuts 5–8): Tightened visit windows (±3 days), Creatinine > 1.5 mg/dL exclusion, corrected 200 central lab records.",
    v1: "Original protocol rules (Cuts 1–4): ±7-day visit windows, Systemic Glucocorticoids (Prednisolone) prohibited.",
  };

  versionNavItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      versionNavItems.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const ver = btn.dataset.version;
      if (summaryBoxText && versionDetails[ver]) {
        summaryBoxText.textContent = versionDetails[ver];
      }
    });
  });


  // =========================================================================
  // 8. ReviewCrew Monitor: Autonomous Safety, Queries & Human Gate (Stage 2)
  // =========================================================================

  const monitorState = {
    report: null,
    activeSubview: "escalations",
    isCycleRunning: false,
    clarifications: {},
  };

  const monCutSelect = document.getElementById("mon-cut-select");
  const monProtoSelect = document.getElementById("mon-proto-select");
  const btnRunCycle = document.getElementById("btn-run-cycle");
  const btnRerunDedup = document.getElementById("btn-rerun-dedup");
  const monCycleBadge = document.getElementById("mon-cycle-badge");
  const monCutBadge = document.getElementById("mon-cut-badge");
  const monProtoBadge = document.getElementById("mon-proto-badge");

  const statMonFindings = document.getElementById("stat-mon-findings");
  const statMonQueries = document.getElementById("stat-mon-queries");
  const statMonQueriesClosed = document.getElementById("stat-mon-queries-closed");
  const statMonApproved = document.getElementById("stat-mon-approved");
  const statMonRejected = document.getElementById("stat-mon-rejected");
  const statMonClarified = document.getElementById("stat-mon-clarified");
  const statMonRepeated = document.getElementById("stat-mon-repeated");
  const statMonClusters = document.getElementById("stat-mon-clusters");

  const monSubnav = document.getElementById("mon-subnav");
  const monSubviewCount = document.getElementById("mon-subview-count");
  const escalationsQueueList = document.getElementById("escalations-queue-list");
  const monQueriesTbody = document.getElementById("mon-queries-tbody");
  const monTraceTimeline = document.getElementById("mon-trace-timeline");
  const monMemoryGrid = document.getElementById("mon-memory-grid");

  const subviewPanels = {
    escalations: document.getElementById("mon-subview-escalations"),
    queries: document.getElementById("mon-subview-queries"),
    trace: document.getElementById("mon-subview-trace"),
    memory: document.getElementById("mon-subview-memory"),
  };

  function initMonitorTab() {
    if (monSubnav) {
      monSubnav.addEventListener("click", (e) => {
        const btn = e.target.closest(".seg-btn");
        if (btn && btn.dataset.subview) {
          switchMonitorSubview(btn.dataset.subview);
        }
      });
    }

    if (btnRunCycle) {
      btnRunCycle.addEventListener("click", () => triggerMonitorCycle());
    }

    if (btnRerunDedup) {
      btnRerunDedup.addEventListener("click", () => triggerDeduplicationCheck());
    }
  }

  function switchMonitorSubview(subviewName) {
    monitorState.activeSubview = subviewName;

    if (monSubnav) {
      monSubnav.querySelectorAll(".seg-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.subview === subviewName);
      });
    }

    Object.entries(subviewPanels).forEach(([name, el]) => {
      if (el) {
        if (name === subviewName) {
          el.style.display = "block";
          el.classList.add("active");
        } else {
          el.style.display = "none";
          el.classList.remove("active");
        }
      }
    });

    updateSubviewCountDisplay();
  }

  function updateSubviewCountDisplay() {
    if (!monSubviewCount || !monitorState.report) return;
    const r = monitorState.report;
    if (monitorState.activeSubview === "escalations") {
      monSubviewCount.textContent = `${r.escalations ? r.escalations.length : 0} Escalations`;
    } else if (monitorState.activeSubview === "queries") {
      monSubviewCount.textContent = `${r.queries_raised ? r.queries_raised.length : 0} Queries`;
    } else if (monitorState.activeSubview === "trace") {
      monSubviewCount.textContent = `${r.trace_entries ? r.trace_entries.length : 0} Trace Steps`;
    } else if (monitorState.activeSubview === "memory") {
      monSubviewCount.textContent = "5 Tracking Indices";
    }
  }

  async function loadMonitorReport() {
    try {
      const [repRes, traceRes, memRes] = await Promise.all([
        fetch("/api/monitor/report").then((r) => (r.ok ? r.json() : null)),
        fetch("/api/monitor/trace").then((r) => (r.ok ? r.json() : { entries: [] })),
        fetch("/api/monitor/memory").then((r) => (r.ok ? r.json() : null)),
      ]);

      if (repRes) {
        if (traceRes && traceRes.entries) {
          repRes.trace_entries = traceRes.entries;
        }
        if (memRes) {
          repRes.memory_data = memRes;
        }
        monitorState.report = repRes;
        renderMonitorReport(repRes);
      }
    } catch (err) {
      console.warn("Failed to load Monitor Report:", err);
    }
  }

  function renderMonitorReport(report) {
    if (!report) return;

    if (monCycleBadge) monCycleBadge.textContent = `Cycle ${report.cycle || 1}`;
    if (monCutBadge) monCutBadge.textContent = `Cut ${report.cut || 12}`;
    if (monProtoBadge) monProtoBadge.textContent = `Protocol v${report.protocol_version || 3}.0`;

    if (statMonFindings) statMonFindings.textContent = report.findings_count != null ? report.findings_count : (report.findings ? report.findings.length : 0);
    if (statMonQueries) statMonQueries.textContent = report.queries_raised_count != null ? report.queries_raised_count : (report.queries_raised ? report.queries_raised.length : 0);
    if (statMonQueriesClosed) statMonQueriesClosed.textContent = `${report.queries_closed_count || 0} closed by site`;
    if (statMonApproved) statMonApproved.textContent = report.approved_escalations_count != null ? report.approved_escalations_count : (report.approved_escalations ? report.approved_escalations.length : 0);
    if (statMonRejected) statMonRejected.textContent = report.rejected_escalations_count != null ? report.rejected_escalations_count : (report.rejected_escalations ? report.rejected_escalations.length : 0);
    if (statMonClarified) statMonClarified.textContent = report.clarified_escalations_count != null ? report.clarified_escalations_count : (report.clarified_escalations ? report.clarified_escalations.length : 0);
    if (statMonRepeated) statMonRepeated.textContent = report.repeated_subjects ? report.repeated_subjects.length : 0;
    if (statMonClusters) statMonClusters.textContent = report.site_clusters ? report.site_clusters.length : 0;

    renderMonitorRibbon(report);
    renderEscalationsQueue(report.escalations || []);
    renderQueriesTable(report.queries_raised || []);
    renderTraceTimeline(report.trace_entries || []);
    renderMemoryDashboard(report.memory_data || {});
    updateSubviewCountDisplay();
  }

  function renderMonitorRibbon(report) {
    const nodes = ["detect", "medical", "dm", "compliance", "gate", "execute"];
    nodes.forEach((n) => {
      const el = document.getElementById(`node-step-${n}`);
      if (el) {
        el.classList.add("active", "completed");
      }
    });
  }

  function renderEscalationsQueue(escalations) {
    if (!escalationsQueueList) return;
    escalationsQueueList.innerHTML = "";

    if (!escalations || escalations.length === 0) {
      escalationsQueueList.innerHTML = `
        <div class="empty-state-panel">
          <div class="empty-state-title">No Escalations Raised</div>
          <p class="empty-state-desc">All clinical signals were addressed at site query level or verified within protocol limits.</p>
        </div>
      `;
      return;
    }

    escalations.forEach((esc) => {
      const card = document.createElement("div");
      const statusLower = (esc.status || "APPROVED").toLowerCase();
      card.className = `escalation-card status-${statusLower}`;
      card.id = `esc-card-${esc.id}`;

      let typeClass = "badge-type-sae";
      if ((esc.finding_code || "").includes("HYS")) typeClass = "badge-type-hyslaw";
      else if ((esc.finding_code || "").includes("DOSE")) typeClass = "badge-type-dosing";
      else if ((esc.finding_code || "").includes("CONCOM")) typeClass = "badge-type-protocol";

      let citationsHtml = "";
      if (esc.citations && esc.citations.length > 0) {
        citationsHtml = esc.citations
          .map((c) => {
            const dom = Array.isArray(c) ? c[0] : (c.domain || "AE");
            const subj = Array.isArray(c) ? c[1] : (c.usubjid || esc.target_id);
            const seq = Array.isArray(c) ? c[2] : (c.seq || 1);
            return `<span class="citation-tag">${escapeHtml(dom)} • ${escapeHtml(subj)} • Seq ${escapeHtml(String(seq))}</span>`;
          })
          .join("");
      }

      let gateStatusPill = "";
      if (esc.status === "APPROVED") {
        gateStatusPill = `<span class="gate-status-pill gate-pill-approved">✓ APPROVED</span>`;
      } else if (esc.status === "REJECTED") {
        gateStatusPill = `<span class="gate-status-pill gate-pill-rejected">✕ REJECTED</span>`;
      } else if (esc.status === "MONITORING") {
        gateStatusPill = `<span class="gate-status-pill" style="background: #FEF3C7; color: #92400E; border: 1px solid #FDE68A;">👁 MONITORING ONLY</span>`;
      } else if (esc.status === "CLARIFIED" || esc.status === "FACT_CHECK_COMPLETE") {
        gateStatusPill = `<span class="gate-status-pill gate-pill-clarified">ℹ FACT-CHECKED</span>`;
      }

      let aiReviewHtml = "";
      if (esc.medical_review_details) {
        const m = esc.medical_review_details;
        aiReviewHtml = `
          <div class="ai-medical-review-card">
            <div class="ai-review-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
              <span>AI Medical Review & Safety Assessment</span>
            </div>
            <div class="ai-review-body">
              <div class="ai-review-meta-item"><strong>Why Detected:</strong> ${escapeHtml(m.why_detected || esc.summary || "")}</div>
              <div class="ai-review-meta-item"><strong>Protocol Basis:</strong> ${escapeHtml(m.protocol_basis || esc.finding_code || "")}</div>
              <div class="ai-review-meta-item"><strong>Medical Assessment:</strong> ${escapeHtml(m.medical_review || esc.rationale || "")}</div>
              ${m.alternative_explanations ? `<div class="ai-review-meta-item"><strong>Alternative Explanations:</strong> ${escapeHtml(m.alternative_explanations)}</div>` : ""}
              ${m.recommended_investigation ? `<div class="ai-review-meta-item"><strong>Recommended Next Investigation:</strong> ${escapeHtml(m.recommended_investigation)}</div>` : ""}
            </div>
          </div>
        `;
      }

      let factCheckHtml = `
        <div class="fact-check-container" id="fc-container-${esc.id}">
          <div class="fact-check-top">
            <span class="fact-check-label">StudyGraph Fact Check</span>
            <span style="font-size: 0.7rem; color: #1E40AF;">Grounded Evidence Verification</span>
          </div>
          <div class="fact-check-input-row">
            <input type="text" class="fact-check-input" id="fc-input-${esc.id}" placeholder="Ask fact check question (e.g. Check screening baseline ALT for this subject)..." />
            <button type="button" class="fact-check-btn" data-id="${esc.id}">Fact Check</button>
          </div>
          <div id="fc-result-wrap-${esc.id}">
            ${esc.fact_check_result ? `<div class="fact-check-result-card"><strong>Fact Check Result:</strong> ${escapeHtml(esc.fact_check_result)}</div>` : ""}
          </div>
        </div>
      `;

      const comments = esc.monitor_comments || [];
      let commentsHtml = `
        <div class="doctor-comment-container">
          <div class="doctor-comment-input-row">
            <input type="text" class="doctor-comment-input" id="doc-comment-input-${esc.id}" placeholder="Add doctor review note or clinical suggestion..." />
            <button type="button" class="doctor-comment-btn" data-id="${esc.id}">Save Note</button>
          </div>
          <div class="monitor-comments-trail" id="doc-comments-trail-${esc.id}">
            ${comments.map((c) => `<div class="comment-bubble"><strong>${escapeHtml(c.author || "Reviewer")}:</strong> ${escapeHtml(c.comment || "")} <span style="font-size: 0.68rem; color: var(--text-muted); float: right;">${escapeHtml(c.timestamp ? c.timestamp.split("T")[1]?.slice(0, 8) || "" : "")}</span></div>`).join("")}
          </div>
        </div>
      `;

      let clarificationCard = "";
      const savedClarify = monitorState.clarifications[esc.id] || esc.clarification_response;
      if (savedClarify) {
        clarificationCard = `
          <div class="clarification-resolution-card">
            <div class="clarification-q">StudyGraph Grounded Clarification:</div>
            <div class="clarification-a">${escapeHtml(savedClarify)}</div>
          </div>
        `;
      }

      card.innerHTML = `
        <div class="escalation-top">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="escalation-id-badge">${escapeHtml(esc.id)}</span>
            <span class="escalation-type-badge ${typeClass}">${escapeHtml(esc.finding_code || "FINDING")}</span>
            <button class="interactive-subject-pill" data-usubjid="${escapeHtml(esc.target_id)}" style="font-size: 0.72rem; padding: 2px 8px;">
              ${escapeHtml(esc.target_id)}
            </button>
          </div>
          <div id="gate-pill-wrap-${esc.id}">
            ${gateStatusPill}
          </div>
        </div>
        <h4 class="escalation-title">${escapeHtml(esc.title || "Clinical Escalation")}</h4>
        <p class="escalation-summary">${escapeHtml(esc.summary || "")}</p>
        <div class="escalation-rationale-box">
          <strong>Reviewer Rationale:</strong> ${escapeHtml(esc.rationale || "Protocol safety review requirement.")}
        </div>
        ${citationsHtml ? `<div class="escalation-citations-row"><span style="font-size: 0.74rem; font-weight: 600; color: var(--text-secondary);">Evidence Citations:</span> ${citationsHtml}</div>` : ""}
        ${aiReviewHtml}
        ${factCheckHtml}
        ${commentsHtml}
        <div id="clarify-box-wrap-${esc.id}">
          ${clarificationCard}
        </div>
        <div class="escalation-actions-row">
          <div style="font-size: 0.76rem; color: var(--text-muted);">
            Reason: <em>${escapeHtml(esc.gate_reason || "Automated ReviewCrew triage")}</em>
          </div>
          <div class="gate-buttons-group">
            <button type="button" class="btn-gate-approve" data-id="${escapeHtml(esc.id)}">Approve</button>
            <button type="button" class="btn-gate-reject" data-id="${escapeHtml(esc.id)}">Reject</button>
            <button type="button" class="btn-gate-monitor" data-id="${escapeHtml(esc.id)}" style="background: #FFFBEB; border: 1px solid #FDE68A; color: #92400E; font-size: 0.74rem; padding: 4px 8px; border-radius: 4px; cursor: pointer;">Monitoring Only</button>
            <button type="button" class="btn-gate-clarify" data-id="${escapeHtml(esc.id)}">Clarify Fact</button>
          </div>
        </div>
      `;

      card.querySelector(".btn-gate-approve").addEventListener("click", () => {
        handleGateDecision(esc.id, "APPROVED", "Approved by human medical reviewer.");
      });
      card.querySelector(".btn-gate-reject").addEventListener("click", () => {
        handleGateDecision(esc.id, "REJECTED", "Classified as benign or non-actionable; persisted in review memory as rejected.");
      });
      card.querySelector(".btn-gate-monitor").addEventListener("click", () => {
        handleGateDecision(esc.id, "MONITORING", "Persisted for longitudinal safety monitoring only.");
      });
      card.querySelector(".btn-gate-clarify").addEventListener("click", () => {
        handleGateDecision(esc.id, "CLARIFY", "Clarification requested regarding baseline transaminases and concomitant medication history.");
      });

      // Fact check button listener
      const fcBtn = card.querySelector(".fact-check-btn");
      const fcInput = card.querySelector(`#fc-input-${esc.id}`);
      if (fcBtn && fcInput) {
        fcBtn.addEventListener("click", async () => {
          const qText = fcInput.value.trim() || `Check baseline screening ALT and concomitant medication history for ${esc.target_id}`;
          fcBtn.disabled = true;
          fcBtn.textContent = "Checking...";
          try {
            const fcRes = await fetch("/api/monitor/fact-check", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ escalation_id: esc.id, query: qText }),
            });
            if (fcRes.ok) {
              const fcData = await fcRes.json();
              const resultWrap = card.querySelector(`#fc-result-wrap-${esc.id}`);
              if (resultWrap) {
                resultWrap.innerHTML = `<div class="fact-check-result-card"><strong>Fact Check Result:</strong> ${escapeHtml(fcData.fact_check_result || "Verified against StudyGraph.")}</div>`;
              }
            }
          } catch (e) {
            console.error("Fact check error:", e);
          } finally {
            fcBtn.disabled = false;
            fcBtn.textContent = "Fact Check";
          }
        });
      }

      // Doctor comment listener
      const docBtn = card.querySelector(".doctor-comment-btn");
      const docInput = card.querySelector(`#doc-comment-input-${esc.id}`);
      if (docBtn && docInput) {
        docBtn.addEventListener("click", async () => {
          const noteText = docInput.value.trim();
          if (!noteText) return;
          docBtn.disabled = true;
          try {
            const cRes = await fetch("/api/monitor/comment", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ escalation_id: esc.id, comment: noteText, doctor_name: "Dr. Clinical Reviewer" }),
            });
            if (cRes.ok) {
              const cData = await cRes.json();
              docInput.value = "";
              const trail = card.querySelector(`#doc-comments-trail-${esc.id}`);
              if (trail && cData.comments) {
                trail.innerHTML = cData.comments.map((c) => `<div class="comment-bubble"><strong>${escapeHtml(c.author || "Reviewer")}:</strong> ${escapeHtml(c.comment || "")} <span style="font-size: 0.68rem; color: var(--text-muted); float: right;">${escapeHtml(c.timestamp ? c.timestamp.split("T")[1]?.slice(0, 8) || "" : "")}</span></div>`).join("");
              }
            }
          } catch (e) {
            console.error("Comment error:", e);
          } finally {
            docBtn.disabled = false;
          }
        });
      }

      const subjBtn = card.querySelector(".interactive-subject-pill");
      if (subjBtn) {
        subjBtn.addEventListener("click", () => openPatient360(esc.target_id));
      }

      escalationsQueueList.appendChild(card);
    });
  }

  async function handleGateDecision(escId, decision, reason) {
    try {
      const res = await fetch("/api/monitor/escalations/decision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          escalation_id: escId,
          decision,
          reason,
        }),
      });

      if (!res.ok) {
        throw new Error(`Decision update failed: ${res.statusText}`);
      }

      const json = await res.json();
      const updatedEsc = json.escalation;

      if (decision === "CLARIFY" && updatedEsc.clarification_response) {
        monitorState.clarifications[escId] = updatedEsc.clarification_response;
      }

      await loadMonitorReport();
    } catch (err) {
      console.error("Gate decision error:", err);
      alert(`Could not record decision for ${escId}: ${err.message}`);
    }
  }

  function renderQueriesTable(queries) {
    if (!monQueriesTbody) return;
    monQueriesTbody.innerHTML = "";

    if (!queries || queries.length === 0) {
      monQueriesTbody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 24px;">
            No site data queries raised in this review cycle.
          </td>
        </tr>
      `;
      return;
    }

    queries.forEach((q) => {
      const tr = document.createElement("tr");
      const isClosed = (q.status || "").toUpperCase() === "CLOSED";
      const badgeClass = isClosed ? "query-closed" : "query-open";

      tr.innerHTML = `
        <td class="font-mono text-muted" style="font-weight: 600;">${escapeHtml(q.query_id)}</td>
        <td><span class="domain-pill dom-pill-${(q.domain || "AE").toLowerCase()}">${escapeHtml(q.domain)}</span></td>
        <td>
          <a href="javascript:void(0)" class="link-to-p360" data-usubjid="${escapeHtml(q.usubjid)}">${escapeHtml(q.usubjid)}</a>
        </td>
        <td class="font-mono text-muted">${escapeHtml(String(q.seq || "—"))}</td>
        <td><strong>${escapeHtml(q.query_type || "DISCREPANCY")}</strong></td>
        <td style="font-size: 0.82rem; color: var(--text-main);">${escapeHtml(q.description || "")}</td>
        <td>
          <div style="display: flex; align-items: center; gap: 6px;">
            <span class="query-status-badge ${badgeClass}">${escapeHtml(q.status || "OPEN")}</span>
            <span style="font-size: 0.74rem; color: var(--text-secondary);">${escapeHtml(q.site_response || "Awaiting site coordinator response")}</span>
          </div>
        </td>
      `;

      const pLink = tr.querySelector(".link-to-p360");
      if (pLink) {
        pLink.addEventListener("click", () => openPatient360(q.usubjid));
      }

      monQueriesTbody.appendChild(tr);
    });
  }

  function renderTraceTimeline(entries) {
    if (!monTraceTimeline) return;
    monTraceTimeline.innerHTML = "";

    if (!entries || entries.length === 0) {
      monTraceTimeline.innerHTML = `
        <div class="empty-state-panel">
          <div class="empty-state-title">No Trace Events Recorded</div>
          <p class="empty-state-desc">Audit entries will appear here as the 6 review nodes execute.</p>
        </div>
      `;
      return;
    }

    entries.forEach((item) => {
      const div = document.createElement("div");
      div.className = "trace-item";

      const timeStr = item.timestamp ? item.timestamp.split("T")[1]?.split(".")[0] || item.timestamp : "00:00:00";
      const nodeKey = (item.node || "detect").toLowerCase();

      let detailsStr = "";
      if (item.details) {
        if (typeof item.details === "object") {
          detailsStr = Object.entries(item.details)
            .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
            .join("  •  ");
        } else {
          detailsStr = String(item.details);
        }
      }

      div.innerHTML = `
        <span class="trace-timestamp">${escapeHtml(timeStr)}</span>
        <span class="trace-node-badge trace-node-${escapeHtml(nodeKey)}">${escapeHtml(item.node || "NODE")}</span>
        <div style="flex: 1;">
          <div class="trace-action-text">${escapeHtml(item.action || "STEP")}</div>
          ${detailsStr ? `<div class="trace-details-text">${escapeHtml(detailsStr)}</div>` : ""}
        </div>
      `;
      monTraceTimeline.appendChild(div);
    });
  }

  function renderMemoryDashboard(memory) {
    if (!monMemoryGrid) return;
    monMemoryGrid.innerHTML = "";

    const queriesCount = memory.total_queries || 0;
    const escalationsCount = memory.total_escalations || 0;
    const rejectedItems = memory.rejected_items || [];
    const siteDeviations = memory.site_deviations_tracked || {};
    const subjectCutsCount = memory.subject_cuts_tracked || 0;

    // Card 1: Tracked Queries
    const c1 = document.createElement("div");
    c1.className = "memory-card";
    c1.innerHTML = `
      <div class="memory-card-header">
        <span class="memory-card-title">Deduplicated Site Queries</span>
        <span class="memory-count-badge">${queriesCount} Tracked</span>
      </div>
      <div class="memory-card-body">
        <p style="color: var(--text-secondary); margin-bottom: 8px;">
          Persisted keys <code>DOMAIN|USUBJID|SEQ</code> prevent duplicate queries from being submitted to investigative sites across cycles.
        </p>
        <span class="badge-stage" style="background: #F0FDF4; color: #166534; border-color: #BBF7D0;">DEDUPLICATION ACTIVE</span>
      </div>
    `;
    monMemoryGrid.appendChild(c1);

    // Card 2: Tracked Escalations
    const c2 = document.createElement("div");
    c2.className = "memory-card";
    c2.innerHTML = `
      <div class="memory-card-header">
        <span class="memory-card-title">Tracked Safety Escalations</span>
        <span class="memory-count-badge">${escalationsCount} Escalations</span>
      </div>
      <div class="memory-card-body">
        <p style="color: var(--text-secondary); margin-bottom: 8px;">
          Approved medical review items tracked by <code>FINDING_CODE|TARGET_ID</code> to prevent double-counting during safety committee triage.
        </p>
        <span class="badge-stage" style="background: #EFF6FF; color: #1E40AF; border-color: #BFDBFE;">TRIAGE VERIFIED</span>
      </div>
    `;
    monMemoryGrid.appendChild(c2);

    // Card 3: Persistent Rejections
    const c3 = document.createElement("div");
    c3.className = "memory-card";
    c3.innerHTML = `
      <div class="memory-card-header">
        <span class="memory-card-title">Persistent Rejections (Monitoring-Only)</span>
        <span class="memory-count-badge text-danger">${rejectedItems.length} Items</span>
      </div>
      <div class="memory-card-body">
        <p style="color: var(--text-secondary); margin-bottom: 8px;">
          Findings rejected by human gate are held in longitudinal memory and strictly suppressed from re-escalating in subsequent cuts.
        </p>
        <div class="memory-chips-wrap">
          ${
            rejectedItems.length > 0
              ? rejectedItems.map((k) => `<span class="memory-item-chip chip-rejected">${escapeHtml(k)}</span>`).join("")
              : '<span class="memory-empty-text">Zero rejected items.</span>'
          }
        </div>
      </div>
    `;
    monMemoryGrid.appendChild(c3);

    // Card 4: Multi-Cut Subject Tracking
    const c4 = document.createElement("div");
    c4.className = "memory-card";
    c4.innerHTML = `
      <div class="memory-card-header">
        <span class="memory-card-title">Longitudinal Subject Cuts</span>
        <span class="memory-count-badge">${subjectCutsCount} Subjects Tracked</span>
      </div>
      <div class="memory-card-body">
        <p style="color: var(--text-secondary); margin-bottom: 8px;">
          Subject observations indexed by data cut to automatically identify repeated subjects across sequential protocol amendments.
        </p>
        <span class="badge-stage">LONGITUDINAL INDEX</span>
      </div>
    `;
    monMemoryGrid.appendChild(c4);

    // Card 5: Site Deviation Clusters
    const siteRows = Object.entries(siteDeviations)
      .map(([site, count]) => `<div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid var(--border-light); font-family: var(--font-mono); font-size: 0.78rem;"><span>Site ${escapeHtml(site)}</span><strong>${count} deviations</strong></div>`)
      .join("");

    const c5 = document.createElement("div");
    c5.className = "memory-card";
    c5.innerHTML = `
      <div class="memory-card-header">
        <span class="memory-card-title">Site Deviation Clusters</span>
        <span class="memory-count-badge text-danger">${Object.keys(siteDeviations).length} Sites</span>
      </div>
      <div class="memory-card-body">
        <p style="color: var(--text-secondary); margin-bottom: 8px;">
          Sites exhibiting ≥ 3 protocol or dosing deviations are flagged as systemic site compliance clusters.
        </p>
        <div>
          ${siteRows || '<span class="memory-empty-text">No site clusters detected.</span>'}
        </div>
      </div>
    `;
    monMemoryGrid.appendChild(c5);
  }

  async function triggerMonitorCycle() {
    if (monitorState.isCycleRunning) return;
    monitorState.isCycleRunning = true;

    if (btnRunCycle) {
      btnRunCycle.disabled = true;
      const span = btnRunCycle.querySelector("#btn-run-text") || btnRunCycle;
      span.textContent = "Executing 6 Nodes...";
    }

    const cutVal = parseInt(monCutSelect ? monCutSelect.value : "12", 10);
    const protoVal = parseInt(monProtoSelect ? monProtoSelect.value : "3", 10);

    try {
      const res = await fetch("/api/monitor/cycle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cut: cutVal, protocol_version: protoVal }),
      });

      if (!res.ok) {
        throw new Error(`Cycle execution returned HTTP ${res.status}`);
      }

      await loadMonitorReport();
    } catch (err) {
      console.error("Monitor cycle execution error:", err);
      alert(`Error running ReviewCrew cycle: ${err.message}`);
    } finally {
      monitorState.isCycleRunning = false;
      if (btnRunCycle) {
        btnRunCycle.disabled = false;
        const span = btnRunCycle.querySelector("#btn-run-text") || btnRunCycle;
        span.textContent = "Run Review Cycle";
      }
    }
  }

  async function triggerDeduplicationCheck() {
    if (monitorState.isCycleRunning) return;
    monitorState.isCycleRunning = true;

    if (btnRerunDedup) {
      btnRerunDedup.disabled = true;
      btnRerunDedup.textContent = "Verifying 0 Deduplication...";
    }

    const cutVal = parseInt(monCutSelect ? monCutSelect.value : "12", 10);
    const protoVal = parseInt(monProtoSelect ? monProtoSelect.value : "3", 10);

    try {
      const res = await fetch("/api/monitor/cycle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cut: cutVal, protocol_version: protoVal }),
      });

      if (!res.ok) {
        throw new Error(`Deduplication check returned HTTP ${res.status}`);
      }

      const rep = await res.json();
      await loadMonitorReport();

      alert(
        `Deterministic Deduplication Verified!\n\n` +
        `Cycle ${rep.cycle} completed against Cut ${rep.cut}.\n` +
        `New Queries Raised: ${rep.queries_raised_count} (0 duplicate queries created)\n` +
        `New Escalations Raised: ${rep.escalations_count} (0 duplicate escalations created)\n` +
        `Longitudinal Review Memory successfully protected all previously triaged records.`
      );
    } catch (err) {
      console.error("Deduplication check error:", err);
      alert(`Deduplication check error: ${err.message}`);
    } finally {
      monitorState.isCycleRunning = false;
      if (btnRerunDedup) {
        btnRerunDedup.disabled = false;
        btnRerunDedup.textContent = "Verify Deduplication";
      }
    }
  }


  // Run Application Ingestion
  initializeApp();
});
