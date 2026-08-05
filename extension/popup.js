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

// Default hosted backend used by the extension.
// Developers running WatchWise locally can change this URL from
// Settings → Advanced → Backend URL (e.g., http://localhost:8000).
const DEFAULT_BACKEND_URL = "https://watchwise-o786.onrender.com";
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
  if (score >= 70) return "#2e7d32"; // green
  if (score >= 40) return "#f57f17"; // amber
  return "#b71c1c";                  // red
}

// ── DOM references ────────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

const states = {
  loading:    $("state-loading"),
  error:      $("state-error"),
  notYoutube: $("state-not-youtube"),
};
const results = $("results");

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
  if (!data || typeof data.watch_score !== "number") {
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

/**
 * Render a full analysis response object into the results section.
 * Uses only textContent — never innerHTML.
 */
function renderAnalysis(data) {
  // ── Watch score hero ────────────────────────────────────────────────────
  const watchScore = Math.max(0, Math.min(100, data.watch_score || 0));
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

  // ── Score breakdown ─────────────────────────────────────────────────────
  const bd = data.score_breakdown || {};
  renderScore("bd-educational", "bar-educational", bd.educational_value   ?? 0);
  renderScore("bd-community",   "bar-community",   bd.community_trust     ?? 0);
  renderScore("bd-clarity",     "bar-clarity",     bd.clarity             ?? 0);
  renderScore("bd-beginner",    "bar-beginner",     bd.beginner_friendliness ?? 0);

  // ── Risk pills ──────────────────────────────────────────────────────────
  renderRiskPill("outdated-pill", data.outdated_risk   || "low");
  renderRiskPill("misinfo-pill",  data.misinformation_risk || "low");

  const conf = $("outdated-conf");
  if (typeof data.outdated_confidence === "number") {
    conf.textContent = `${data.outdated_confidence}% conf.`;
  } else {
    conf.textContent = "";
  }

  // ── Community evidence (collapsible, hidden if empty) ──────────────────
  renderEvidenceSection(
    "community-evidence-section",
    "community-evidence-toggle",
    "community-evidence-list",
    data.community_evidence
  );
  wireToggle("community-evidence-toggle", "community-evidence-list");

  // ── Summary ─────────────────────────────────────────────────────────────
  $("summary-text").textContent = data.summary || "";
  // ── Pros / Cons ──────────────────────────────────────────────────────────
  renderList("pros-list", data.pros);
  renderList("cons-list", data.cons);

  // ── Evidence (collapsible, hidden if empty) ─────────────────────────────
  renderEvidenceSection(
    "outdated-evidence-section",
    "outdated-evidence-toggle",
    "outdated-evidence-list",
    data.outdated_evidence
  );
  renderEvidenceSection(
    "misinfo-evidence-section",
    "misinfo-evidence-toggle",
    "misinfo-evidence-list",
    data.misinformation_evidence
  );

  wireToggle("outdated-evidence-toggle", "outdated-evidence-list");
  wireToggle("misinfo-evidence-toggle",  "misinfo-evidence-list");

  showResults();
}

// ── Settings button ───────────────────────────────────────────────────────────

function wireSettingsButton() {
  $("settings-btn").addEventListener("click", () => {
    chrome.runtime.openOptionsPage();
  });
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
    // err.message is always a safe, key-free string — see fetchAnalysis
    showError("Analysis failed", err.message);
    return;
  }
  stopStages();

  // 5. Render the result
  renderAnalysis(data);
}

// Run when the popup DOM is ready
document.addEventListener("DOMContentLoaded", main);
