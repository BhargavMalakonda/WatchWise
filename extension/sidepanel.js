/**
 * popup.js — WatchWise Chrome Extension
 *
 * Responsibilities:
 *  1. Detect whether the active tab is a YouTube watch page.
 *  2. Read backend URL, provider, and optional api_key from storage.
 *  3. POST to /api/v1/analyze and render the structured response.
 *
 * Security contract:
 *  - All user-visible text is set via textContent only — never innerHTML.
 *  - The api_key is read from chrome.storage.local and sent in the request
 *    body only. It is never logged, rendered, or stored elsewhere.
 */

"use strict";

// ── Constants ─────────────────────────────────────────────────────────────────

// Default backend URL for a local WatchWise instance.
// If you're running the FastAPI backend on a different host or port,
// update this value in Settings → Advanced → Backend URL.
const DEFAULT_BACKEND_URL = "http://localhost:8000";
const ANALYZE_PATH        = "/api/v1/analyze";

/**
 * Fetch timeout in milliseconds.
 * The backend can take 20–40 s for a cold analysis (transcript + LLM).
 * 90 s covers slow networks without leaving users stuck indefinitely.
 */
const FETCH_TIMEOUT_MS = 90_000;

/**
 * Staged loading messages shown while the backend request is in flight.
 * Cycled every ~1 s to give the user a sense of progress.
 */
const LOADING_STAGES = [
  "Reading video information",
  "Fetching comments",
  "Reading transcript",
  "Analyzing with AI",
  "Preparing recommendation",
];

/** Maps a recommendation string to a CSS class suffix. */
const REC_CLASS_MAP = {
  "Highly Recommended": "highly-recommended",
  "Recommended":        "recommended",
  "Watch with Caution": "watch-with-caution",
  "Not Recommended":    "not-recommended",
};

/** Maps a risk level to a CSS class. */
const RISK_CLASS_MAP = {
  "low":    "risk-low",
  "medium": "risk-medium",
  "high":   "risk-high",
};

/** Maps a 0-100 score to a CSS colour for bars and score value text. */
function scoreColor(score) {
  if (score >= 70) return "#16a34a"; // green
  if (score >= 40) return "#f59e0b"; // amber
  return "#dc2626";                  // red
}

/** Maps a level string to a pill CSS class. */
const LEVEL_PILL_MAP = {
  low:    "pill-low",
  medium: "pill-medium",
  high:   "pill-high",
};

/** Plain-language verification status labels. */
const VERIFY_STATUS_LABELS = {
  supported:               "Supported by evidence",
  needs_context:           "More context needed",
  needs_verification:      "Needs independent verification",
  insufficient_information: "Not enough information available",
};

/** Maps verification status to a CSS class. */
const VERIFY_STATUS_CLASS = {
  supported:               "verify-supported",
  needs_context:           "verify-needs-context",
  needs_verification:      "verify-needs-verification",
  insufficient_information: "verify-insufficient-information",
};

/** Maps before_you_share status to a CSS class. */
const SHARE_STATUS_CLASS = {
  pass:    "status-pass",
  warning: "status-warning",
  fail:    "status-fail",
};

// ── DOM references ────────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

const states = {
  loading:    $("state-loading"),
  error:      $("state-error"),
  notYoutube: $("state-not-youtube"),
};
const results = $("results");


// Last analyzed YouTube video ID.
// Used to detect when the user navigates to another video.
let currentVideoId = null;
let latestAnalysis = null;


// ── Loading stage cycler ──────────────────────────────────────────────────────

/**
 * Start cycling through LOADING_STAGES roughly every 1 second.
 * Updates the #loading-stage element via textContent.
 * Returns a stop function — call it immediately when the request resolves.
 */
function startLoadingStages() {
  const el = $("loading-stage");
  // The dots span must survive textContent replacement, so we rebuild it each tick.
  let index = 0;

  function render() {
    // Clear the element, set the stage text, re-append the animated dots span.
    el.textContent = LOADING_STAGES[index];
    const dots = document.createElement("span");
    dots.className    = "stage-dots";
    dots.setAttribute("aria-hidden", "true");
    el.appendChild(dots);
  }

  render(); // show first stage immediately

  const timer = setInterval(() => {
    index = (index + 1) % LOADING_STAGES.length;
    render();
  }, 1000);

  return function stop() {
    clearInterval(timer);
  };
}



/** Hide all state panels and the results block. */
function hideAll() {
  Object.values(states).forEach((el) => (el.style.display = "none"));
  results.style.display = "none";
}

/** Show a named state panel. */
function showState(name) {
  hideAll();
  states[name].style.display = "flex";
}

/**
 * Show the error state with a title and detail message.
 * Never includes an api_key in either string.
 */
function showError(title, msg) {
  hideAll();
  $("error-title").textContent = title;
  $("error-msg").textContent   = msg;
  states.error.style.display = "flex";
}

/** Show the results block. */
function showResults() {
  hideAll();
  results.style.display = "block";
}

// ── URL utilities ─────────────────────────────────────────────────────────────

/**
 * Return the 11-character video ID from a YouTube watch URL, or null.
 * Handles:
 *   https://www.youtube.com/watch?v=VIDEO_ID
 *   https://www.youtube.com/watch?v=VIDEO_ID&t=30s
 */
function extractVideoId(url) {
  try {
    const parsed = new URL(url);
    if (
      (parsed.hostname === "www.youtube.com" || parsed.hostname === "youtube.com") &&
      parsed.pathname === "/watch"
    ) {
      const v = parsed.searchParams.get("v");
      return v && v.length === 11 ? v : null;
    }
  } catch {
    // malformed URL
  }
  return null;
}

// ── Storage helpers ───────────────────────────────────────────────────────────

/**
 * Read BACKEND_URL and provider from chrome.storage.sync,
 * and api_key from chrome.storage.local.
 *
 * Returns { backendUrl, provider, apiKey }.
 */
async function readSettings() {
  const [syncData, localData] = await Promise.all([
    chrome.storage.sync.get(["BACKEND_URL", "provider"]),
    chrome.storage.local.get(["api_key"]),
  ]);

  return {
    backendUrl: (syncData.BACKEND_URL || DEFAULT_BACKEND_URL).replace(/\/$/, ""),
    provider:   syncData.provider || "server",
    apiKey:     localData.api_key  || null,
  };
}

// ── API call ──────────────────────────────────────────────────────────────────

/**
 * POST to the backend /api/v1/analyze endpoint.
 *
 * @param {string} backendUrl   Base URL, no trailing slash.
 * @param {string} videoUrl     Full YouTube watch URL.
 * @param {string} provider     "server" | "gemini"
 * @param {string|null} apiKey  Required when provider === "gemini".
 * @returns {Promise<object>}   Parsed response JSON.
 * @throws {Error}              With a safe, non-sensitive message.
 */
async function fetchAnalysis(backendUrl, videoUrl, provider, apiKey) {
  const body = { video_url: videoUrl };

  if (provider === "gemini" && apiKey) {
    body.provider = "gemini";
    body.api_key  = apiKey;   // only in-memory for this request; never logged
  }
  // If provider === "server", send no provider field — backend defaults to server.

  const endpoint = `${backendUrl}${ANALYZE_PATH}`;

  // Use AbortController so we can enforce a hard timeout.
  const controller = new AbortController();
  const timeoutId  = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  let response;
  try {
    response = await fetch(endpoint, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
      signal:  controller.signal,
    });
  } catch (networkErr) {
    if (networkErr.name === "AbortError") {
      throw new Error(
        "The request timed out. The backend may be overloaded or unreachable. Try again."
      );
    }
    // Network error — safe to describe without including any keys
    throw new Error(
      `Could not reach the WatchWise backend at ${backendUrl}. ` +
      "Check that the server is running and your Backend URL in Settings is correct."
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (response.status === 429) {
    throw new Error(
      "The server's daily analysis quota has been reached. " +
      "Try again tomorrow, or add your own Gemini API key in Settings."
    );
  }

  if (response.status === 422) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "The video could not be analysed (422).");
  }

  if (!response.ok) {
    throw new Error(`Backend returned an error (HTTP ${response.status}). Try again later.`);
  }

  const data = await response.json().catch(() => null);
  if (!data || typeof data.overall_assessment !== "object" || !data.recommendation) {
    throw new Error("Received an unexpected response from the backend. Try again.");
  }
  return data;
}

// ── Rendering ─────────────────────────────────────────────────────────────────

/** Set a score value and its mini bar. */
function renderScore(valueId, barId, score) {
  const el   = $(valueId);
  const bar  = $(barId);
  const pct  = Math.max(0, Math.min(100, score));
  const col  = scoreColor(pct);

  el.textContent    = pct;
  el.style.color    = col;
  bar.style.width      = `${pct}%`;
  bar.style.background = col;
}

/** Apply a risk CSS class and label text to a pill element. */
function renderRiskPill(pillId, level) {
  const pill = $(pillId);
  // Remove any existing risk class
  pill.className = "risk-pill";
  const cls = RISK_CLASS_MAP[level] || "risk-medium";
  pill.classList.add(cls);
  pill.textContent = level || "unknown";
}

/** Populate a <ul> with plain-text <li> items. All via textContent. */
function renderList(listId, items) {
  const ul = $(listId);
  ul.textContent = ""; // clear
  const arr = Array.isArray(items) ? items : [];
  if (arr.length === 0) {
    const li = document.createElement("li");
    li.textContent = "None noted.";
    li.style.color = "#aaa";
    ul.appendChild(li);
    return;
  }
  arr.forEach((text) => {
    const li = document.createElement("li");
    li.textContent = String(text);
    ul.appendChild(li);
  });
}

/** Populate an evidence list section. Hides the section if evidence is empty. */
function renderEvidenceSection(sectionId, toggleId, listId, items) {
  const section = $(sectionId);
  const arr = Array.isArray(items) ? items : [];

  if (arr.length === 0) {
    section.style.display = "none";
    return;
  }

  section.style.display = "";
  const list = $(listId);
  list.textContent = ""; // clear

  arr.forEach((text) => {
    const div = document.createElement("div");
    div.className   = "evidence-item";
    div.textContent = String(text);
    div.setAttribute("role", "listitem");
    list.appendChild(div);
  });
}

/** Wire up a collapsible evidence toggle button. */
function wireToggle(toggleId, listId) {
  const btn  = $(toggleId);
  const list = $(listId);
  btn.addEventListener("click", () => {
    const isOpen = list.classList.contains("open");
    list.classList.toggle("open", !isOpen);
    btn.classList.toggle("open", !isOpen);
    btn.setAttribute("aria-expanded", String(!isOpen));
  });
}

/** Show or hide a section by element id. */
function setSectionVisible(sectionId, visible) {
  $(sectionId).style.display = visible ? "" : "none";
}

/** Create a level pill with text label (never color-only). */
function createLevelPill(label, level) {
  const pill = document.createElement("span");
  pill.className = `signal-pill ${LEVEL_PILL_MAP[level] || "pill-medium"}`;
  const labelEl = document.createElement("span");
  labelEl.className = "pill-label";
  labelEl.textContent = `${label}: `;
  const valueEl = document.createElement("span");
  valueEl.textContent = level || "unknown";
  pill.appendChild(labelEl);
  pill.appendChild(valueEl);
  return pill;
}

/** Build a single claim card element. All text via textContent. */
function createClaimCard(claim) {
  const card = document.createElement("div");
  card.className = "claim-card";

  const textEl = document.createElement("div");
  textEl.className = "claim-text";
  textEl.textContent = claim.claim || "";
  card.appendChild(textEl);

  const meta = document.createElement("div");
  meta.className = "claim-meta";

  if (claim.claim_type) {
    const typeTag = document.createElement("span");
    typeTag.className = "claim-tag";
    typeTag.textContent = claim.claim_type;
    meta.appendChild(typeTag);
  }
  if (claim.importance) {
    const impTag = document.createElement("span");
    impTag.className = "claim-tag";
    impTag.textContent = `${claim.importance} importance`;
    meta.appendChild(impTag);
  }
  const status = claim.verification_status || "";
  if (status) {
    const statusTag = document.createElement("span");
    statusTag.className = `claim-tag ${VERIFY_STATUS_CLASS[status] || ""}`;
    statusTag.textContent = status.replace(/_/g, " ");
    meta.appendChild(statusTag);
  }
  card.appendChild(meta);

  const statusNote = document.createElement("div");
  statusNote.className = "verify-status-note";
  statusNote.textContent = VERIFY_STATUS_LABELS[status] || "";
  if (statusNote.textContent) card.appendChild(statusNote);

  const questions = Array.isArray(claim.why_question) ? claim.why_question : [];
  if (questions.length > 0) {
    const qList = document.createElement("ul");
    qList.className = "claim-questions";
    qList.setAttribute("aria-label", "Questions to consider");
    questions.forEach((q) => {
      const li = document.createElement("li");
      li.textContent = String(q);
      qList.appendChild(li);
    });
    card.appendChild(qList);
  }

  if (claim.mil_skill) {
    const skillEl = document.createElement("div");
    skillEl.className = "claim-skill";
    skillEl.textContent = `Skill: ${claim.mil_skill}`;
    card.appendChild(skillEl);
  }

  return card;
}

/** Render claims — first 3 visible, rest behind collapsible. */
function renderClaims(claims) {
  const arr = Array.isArray(claims) ? claims : [];
  const section = $("claims-section");
  const list = $("claims-list");
  const moreSection = $("claims-more-section");
  const moreList = $("claims-more-list");

  list.textContent = "";
  moreList.textContent = "";

  if (arr.length === 0) {
    section.style.display = "none";
    moreSection.style.display = "none";
    return;
  }

  section.style.display = "";
  const visible = arr.slice(0, 3);
  const hidden = arr.slice(3);

  visible.forEach((claim) => {
    list.appendChild(createClaimCard(claim));
  });

  if (hidden.length === 0) {
    moreSection.style.display = "none";
    return;
  }

  moreSection.style.display = "";
  $("claims-more-label").textContent = `Show ${hidden.length} more claim${hidden.length === 1 ? "" : "s"}`;
  hidden.forEach((claim) => {
    moreList.appendChild(createClaimCard(claim));
  });
}

/** Render before_you_share checklist rows. */
function renderBeforeYouShare(items) {
  const arr = Array.isArray(items) ? items : [];
  const section = $("before-share-section");
  const container = $("before-share-list");
  container.textContent = "";

  if (arr.length === 0) {
    section.style.display = "none";
    return;
  }

  section.style.display = "";
  arr.forEach((item) => {
    const row = document.createElement("div");
    row.className = "share-row";

    const question = document.createElement("div");
    question.className = "share-question";
    question.textContent = item.question || "";
    row.appendChild(question);

    const status = item.status || "warning";
    const chip = document.createElement("span");
    chip.className = `status-chip ${SHARE_STATUS_CLASS[status] || "status-warning"}`;
    chip.textContent = status;
    chip.setAttribute("aria-label", `Status: ${status}`);
    row.appendChild(chip);

    container.appendChild(row);
  });
}

/** Render community_perspective pills and notes. */
function renderCommunityPerspective(perspective) {
  const cp = perspective || {};
  const pillsEl = $("community-pills");
  const notesEl = $("community-notes");
  pillsEl.textContent = "";
  notesEl.textContent = "";

  let hasContent = false;

  if (cp.agreement) {
    pillsEl.appendChild(createLevelPill("Agreement", cp.agreement));
    hasContent = true;
  }
  if (cp.disagreement) {
    pillsEl.appendChild(createLevelPill("Disagreement", cp.disagreement));
    hasContent = true;
  }

  const notes = Array.isArray(cp.notes) ? cp.notes : [];
  notes.forEach((note) => {
    const li = document.createElement("li");
    li.textContent = String(note);
    notesEl.appendChild(li);
    hasContent = true;
  });

  return hasContent;
}

/** Render signal pills for information_signals or inclusion_signals. */
function renderSignalPills(containerId, sectionId, signals, labels) {
  const container = $(containerId);
  const section = $(sectionId);
  container.textContent = "";

  if (!signals || typeof signals !== "object") {
    section.style.display = "none";
    return;
  }

  let hasAny = false;
  labels.forEach(([key, label]) => {
    const val = signals[key];
    if (val) {
      container.appendChild(createLevelPill(label, val));
      hasAny = true;
    }
  });

  section.style.display = hasAny ? "" : "none";
}

/** Render the Learn More collapsible section. */
function renderLearnMore(data) {
  const section = $("learn-more-section");
  const content = $("learn-more-content");
  content.textContent = "";

  const milItems = Array.isArray(data.mil_learning) ? data.mil_learning : [];
  const outcomes = Array.isArray(data.learning_outcomes) ? data.learning_outcomes : [];
  const prompts = Array.isArray(data.critical_thinking_prompts) ? data.critical_thinking_prompts : [];

  const hasMil = milItems.length > 0;
  const hasOutcomes = outcomes.length > 0;
  const hasPrompts = prompts.length > 0;

  if (!hasMil && !hasOutcomes && !hasPrompts) {
    section.style.display = "none";
    return;
  }

  section.style.display = "";

  if (hasMil) {
    const title = document.createElement("div");
    title.className = "section-title";
    title.textContent = "Media Literacy Skills";
    title.style.marginBottom = "8px";
    content.appendChild(title);

    milItems.forEach((item) => {
      const card = document.createElement("div");
      card.className = "mil-card";

      if (item.skill) {
        const skillEl = document.createElement("div");
        skillEl.className = "mil-skill";
        skillEl.textContent = item.skill;
        card.appendChild(skillEl);
      }
      if (item.lesson) {
        const lessonEl = document.createElement("div");
        lessonEl.className = "mil-lesson";
        lessonEl.textContent = item.lesson;
        card.appendChild(lessonEl);
      }
      if (item.why_it_matters) {
        const whyEl = document.createElement("div");
        whyEl.className = "mil-why";
        whyEl.textContent = item.why_it_matters;
        card.appendChild(whyEl);
      }
      if (item.question_to_ask) {
        const qEl = document.createElement("div");
        qEl.className = "mil-question";
        qEl.textContent = `Ask: ${item.question_to_ask}`;
        card.appendChild(qEl);
      }
      content.appendChild(card);
    });
  }

  if (hasOutcomes) {
    const title = document.createElement("div");
    title.className = "section-title";
    title.textContent = "Key Takeaways";
    title.style.marginTop = hasMil ? "12px" : "0";
    title.style.marginBottom = "6px";
    content.appendChild(title);

    const ul = document.createElement("ul");
    ul.className = "bullet-list";
    ul.setAttribute("aria-label", "Learning outcomes");
    outcomes.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item.takeaway ? String(item.takeaway) : "";
      ul.appendChild(li);
    });
    content.appendChild(ul);
  }

  if (hasPrompts) {
    const title = document.createElement("div");
    title.className = "section-title";
    title.textContent = "Questions to Ask Yourself";
    title.style.marginTop = (hasMil || hasOutcomes) ? "12px" : "0";
    title.style.marginBottom = "6px";
    content.appendChild(title);

    const ul = document.createElement("ul");
    ul.className = "bullet-list";
    ul.setAttribute("aria-label", "Critical thinking prompts");
    prompts.forEach((text) => {
      const li = document.createElement("li");
      li.textContent = String(text);
      ul.appendChild(li);
    });
    content.appendChild(ul);
  }
}

/** Determine whether the viewers section should be shown. */
function updateViewersSection(hasPerspective, hasEvidence) {
  setSectionVisible("viewers-section", hasPerspective || hasEvidence);
}

/**
 * Render a full analysis response object into the results section.
 * Uses only textContent — never innerHTML.
 */
function renderAnalysis(data) {
  // ── Trust & Learning Score hero ─────────────────────────────────────────
  const bdForScore = data.score_breakdown || {};
    const computedScore = Math.round(
      ((bdForScore.educational_value ?? 0) +
      (bdForScore.community_reception ?? 0) +
      (bdForScore.clarity ?? 0) +
      (bdForScore.beginner_friendliness ?? 0)) / 4
    );
  const watchScore = Math.max(0, Math.min(100, computedScore));

  const scoreEl    = $("watch-score");
  scoreEl.textContent    = watchScore;
  scoreEl.style.color    = scoreColor(watchScore);
  $("score-bar").style.width      = `${watchScore}%`;
  $("score-bar").style.background = scoreColor(watchScore);

  // ── Recommendation badge ────────────────────────────────────────────────
  const rec     = data.recommendation || "";
  const badge   = $("rec-badge");
  badge.textContent = rec;
  badge.className   = "rec-badge";
  const recCls = REC_CLASS_MAP[rec];
  if (recCls) badge.classList.add(`rec-${recCls}`);

  // ── Overall assessment ────────────────────────────────────────────────
  const assessment = data.overall_assessment || {};
  const assessBlock = $("assessment-block");
  const assessLabel = $("assessment-label");
  const assessConf  = $("assessment-confidence");

  if (assessment.label) {
    assessBlock.style.display = "";
    assessLabel.textContent = assessment.label;
    if (typeof assessment.confidence === "number") {
      assessConf.textContent = `${assessment.confidence}% confidence`;
    } else {
      assessConf.textContent = "";
    }
  } else {
    assessLabel.textContent = "";
    assessConf.textContent = "";
    assessBlock.style.display = assessment.confidence != null ? "" : "none";
    if (typeof assessment.confidence === "number") {
      assessConf.textContent = `${assessment.confidence}% confidence`;
    }
  }

  // ── Score breakdown ─────────────────────────────────────────────────────
  const bd = data.score_breakdown || {};
  renderScore("bd-educational", "bar-educational", bd.educational_value      ?? 0);
  renderScore("bd-community",   "bar-community",   bd.community_reception    ?? 0);
  renderScore("bd-clarity",     "bar-clarity",     bd.clarity                ?? 0);
  renderScore("bd-beginner",    "bar-beginner",    bd.beginner_friendliness  ?? 0);

  // ── Pros / Cons ──────────────────────────────────────────────────────────
  renderList("pros-list", data.pros);
  renderList("cons-list", data.cons);

  // ── Summary ─────────────────────────────────────────────────────────────
  $("summary-text").textContent = data.summary || "";

  // ── Top Claims ──────────────────────────────────────────────────────────
  renderClaims(data.claims);

  // ── Before You Share ────────────────────────────────────────────────────
  renderBeforeYouShare(data.before_you_share);

  // ── What Viewers Are Saying ─────────────────────────────────────────────
  const hasPerspective = renderCommunityPerspective(data.community_perspective);
  const communityEvidence = Array.isArray(data.community_evidence) ? data.community_evidence : [];
  const hasEvidence = communityEvidence.length > 0;

  if (hasEvidence) {
    const ceList = $("community-evidence-list");
    ceList.textContent = "";
    communityEvidence.forEach((text) => {
      const div = document.createElement("div");
      div.className   = "evidence-item";
      div.textContent = String(text);
      div.setAttribute("role", "listitem");
      ceList.appendChild(div);
    });
    $("community-evidence-section").style.display = "";
  } else {
    $("community-evidence-section").style.display = "none";
  }
  updateViewersSection(hasPerspective, hasEvidence);

  // ── Information & Inclusion Signals ─────────────────────────────────────
  renderSignalPills("info-signals-pills", "info-signals-section", data.information_signals, [
    ["evidence_quality",      "Evidence Quality"],
    ["context_completeness",  "Context"],
    ["recency",               "Recency"],
  ]);
  renderSignalPills("inclusion-signals-pills", "inclusion-signals-section", data.inclusion_signals, [
    ["accessible_for_beginners", "Beginner Access"],
    ["jargon_level",             "Jargon"],
    ["learning_barrier",         "Learning Barrier"],
  ]);

  // ── Risk pills (shown inside evidence sections) ─────────────────────────
  renderRiskPill("outdated-pill", data.outdated_risk || "low");
  renderRiskPill("misinfo-pill",  data.misinformation_risk || "low");

  const conf = $("outdated-conf");
  if (typeof data.outdated_confidence === "number") {
    conf.textContent = `${data.outdated_confidence}% confidence`;
  } else {
    conf.textContent = "";
  }

  // ── Information Age Check ───────────────────────────────────────────────
  renderEvidenceSection(
    "outdated-evidence-section",
    "outdated-evidence-toggle",
    "outdated-evidence-list",
    data.outdated_evidence
  );

  // ── Claims Worth Double-Checking ────────────────────────────────────────
  renderEvidenceSection(
    "misinfo-evidence-section",
    "misinfo-evidence-toggle",
    "misinfo-evidence-list",
    data.misinformation_evidence
  );

  // ── Learn More (collapsed by default) ───────────────────────────────────
  renderLearnMore(data);

  wireToggle("community-evidence-toggle", "community-evidence-list");
  wireToggle("outdated-evidence-toggle", "outdated-evidence-list");
  wireToggle("misinfo-evidence-toggle",  "misinfo-evidence-list");
  wireToggle("learn-more-toggle",          "learn-more-content");
  wireToggle("claims-more-toggle",         "claims-more-list");

  showResults();
}

// ── Settings button ───────────────────────────────────────────────────────────

function wireSettingsButton() {
  $("settings-btn").addEventListener("click", () => {
    chrome.runtime.openOptionsPage();
  });
}


/**
 * Checks whether the active YouTube video has changed.
 */
async function checkForNewVideo() {

    const tabs = await chrome.tabs.query({
        active: true,
        currentWindow: true
    });

    if (!tabs.length)
        return;

    const newVideoId = extractVideoId(tabs[0].url);

    if (!newVideoId) {

      $("refresh-btn").disabled = true;
      $("refresh-btn").textContent = "Current Video";

    return;
}

    if (newVideoId !== currentVideoId) {

        document.getElementById("refresh-btn").disabled = false;
        document.getElementById("refresh-btn").textContent = "Analyze New Video";

    } else {

        document.getElementById("refresh-btn").disabled = true;
        document.getElementById("refresh-btn").textContent = "Current Video";

    }
}

/**
 * Refresh analysis for the currently open YouTube video.
 */
async function refreshAnalysis() {

    // Forget previous analysis completely
    latestAnalysis = null;
    currentVideoId = null;

    document.getElementById("refresh-btn").disabled = true;
    document.getElementById("refresh-btn").textContent = "Refreshing...";

    showState("loading");

    await main();
}

// ── Main entry point ──────────────────────────────────────────────────────────

async function main() {
  wireSettingsButton();
  showState("loading");

  // 1. Get the active tab
  let tabs;
  try {
    tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch {
    showError("Permission error", "Could not access the active tab.");
    return;
  }

  const tab = tabs[0];
  if (!tab || !tab.url) {
    showState("notYoutube");
    return;
  }

  // 2. Validate it's a YouTube watch page
  const videoId = extractVideoId(tab.url);

  if (!videoId) {
    showState("notYoutube");
    return;
  }

  // 3. Read settings from storage
  let settings;
  try {
    settings = await readSettings();
  } catch {
    showError("Storage error", "Could not read extension settings.");
    return;
  }

  const { backendUrl, provider, apiKey } = settings;

  // Guard: if the user explicitly chose provider="gemini" but has no saved key,
  // surface a clear error rather than silently falling back to server quota.
  if (provider === "gemini" && !apiKey) {
    showError(
      "Gemini API key required",
      "You have selected your own Gemini key as the provider but no key is saved. " +
      "Open Settings and paste your Gemini API key, then try again."
    );
    return;
  }

  // 4. Fetch analysis from the backend — start stage cycler, stop on completion
  const stopStages = startLoadingStages();
  let data;

  try {
      data = await fetchAnalysis(backendUrl, tab.url, provider, apiKey);
  } catch (err) {
      stopStages();
      showError("Analysis failed", err.message);
      return;
  }

  stopStages();

  // This analysis is now the current one
  currentVideoId = videoId;
  latestAnalysis = data;

  // 5. Render the result
  renderAnalysis(data);
}

/*
  it is used to actively monitor current chrome tab
  so if it is not youtube it will display text on the sidepanel that watchwise only works on youtube
*/

async function monitorActiveTab() {

    const tabs = await chrome.tabs.query({
        active: true,
        currentWindow: true
    });

    if (!tabs.length)
        return;

    const tab = tabs[0];

    const url = tab.url || "";

    const isYoutube =
        url.startsWith("https://www.youtube.com") ||
        url.startsWith("https://youtu.be");

    const id = extractVideoId(url);

    //
    // Not on a YouTube watch page
    //
    // User left YouTube completely
    if (!isYoutube) {

        hideAll();

        $("state-not-youtube").style.display = "flex";

        return;
    }

    // User is on YouTube but not watching a video
    if (!id) {

        return;
    }

    //
    // Back on YouTube
    //
    if (latestAnalysis) {

        renderAnalysis(latestAnalysis);

        if (id !== currentVideoId) {

            $("refresh-btn").disabled = false;
            $("refresh-btn").textContent = "Analyze New Video";

        }
        else {

            $("refresh-btn").disabled = true;
            $("refresh-btn").textContent = "Current Video";

        }

    }

}

// Run when the popup DOM is ready
document.addEventListener("DOMContentLoaded", async () => {

    await main();

    document
        .getElementById("refresh-btn")
        .addEventListener("click", refreshAnalysis);

    setInterval(async () => {

      await checkForNewVideo();

      await monitorActiveTab();

    }, 1000);

});
