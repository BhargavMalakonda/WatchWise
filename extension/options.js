/**
 * options.js — WatchWise Settings Page
 *
 * Reads and writes:
 *   chrome.storage.sync  → BACKEND_URL, provider  (synced across devices)
 *   chrome.storage.local → api_key                (device-only, sensitive)
 *
 * Security contract:
 *   - api_key is stored in local storage only, never sync storage.
 *   - The key field is a password input by default; Show/Hide toggles visibility.
 *   - All user-visible text uses textContent — never innerHTML.
 */

"use strict";

const DEFAULT_BACKEND_URL = "http://localhost:8000";

// ── DOM helpers ───────────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

// ── Load saved settings on page open ─────────────────────────────────────────

async function loadSettings() {
  const [syncData, localData] = await Promise.all([
    chrome.storage.sync.get(["BACKEND_URL", "provider"]),
    chrome.storage.local.get(["api_key"]),
  ]);

  $("backend-url").value = syncData.BACKEND_URL || DEFAULT_BACKEND_URL;

  const provider = syncData.provider || "server";
  $("provider").value = provider;
  toggleApiKeyField(provider);

  // Show a placeholder if a key is already saved (don't pre-fill for security)
  if (localData.api_key) {
    $("api-key").placeholder = "Key saved — paste to replace";
  }
}

// ── Toggle API key field visibility ──────────────────────────────────────────

function toggleApiKeyField(provider) {
  $("api-key-field").style.display = provider === "gemini" ? "" : "none";
}

// ── Save settings ─────────────────────────────────────────────────────────────

async function saveSettings() {
  const backendUrl = $("backend-url").value.trim().replace(/\/$/, "") || DEFAULT_BACKEND_URL;
  const provider   = $("provider").value;
  const apiKeyRaw  = $("api-key").value.trim();

  // Validate the backend URL is a well-formed http/https URL before saving
  try {
    const parsed = new URL(backendUrl);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new Error("Must be http or https");
    }
  } catch {
    showStatus("Invalid Backend URL — must start with http:// or https://", "err");
    return;
  }

  // Always save backend URL and provider to sync storage
  await chrome.storage.sync.set({ BACKEND_URL: backendUrl, provider });

  // Save api_key to local storage only if provider is gemini and a value was entered
  if (provider === "gemini" && apiKeyRaw) {
    await chrome.storage.local.set({ api_key: apiKeyRaw });
    $("api-key").value = ""; // clear the field after saving
    $("api-key").placeholder = "Key saved — paste to replace";
  } else if (provider === "server") {
    // Clear any stored key if the user switches back to server mode
    await chrome.storage.local.remove("api_key");
  }

  showStatus("Settings saved.", "ok");
}

// ── Clear saved API key ───────────────────────────────────────────────────────

async function clearApiKey() {
  await chrome.storage.local.remove("api_key");
  $("api-key").value = "";
  $("api-key").placeholder = "Paste your key here";
  showStatus("API key cleared.", "ok");
}

// ── Status message ────────────────────────────────────────────────────────────

function showStatus(msg, type) {
  const el = $("status-msg");
  el.textContent  = msg;
  el.className    = `status-msg status-${type}`;
  setTimeout(() => { el.textContent = ""; el.className = "status-msg"; }, 3000);
}

// ── Show/hide key toggle ──────────────────────────────────────────────────────

function wireShowHide() {
  const btn   = $("show-key-btn");
  const input = $("api-key");
  btn.addEventListener("click", () => {
    const isPassword = input.type === "password";
    input.type       = isPassword ? "text" : "password";
    btn.textContent  = isPassword ? "Hide" : "Show";
  });
}

// ── Event wiring ──────────────────────────────────────────────────────────────

function wireEvents() {
  // Advanced section toggle
  const advToggle = $("advanced-toggle");
  const advBody   = $("advanced-body");
  advToggle.addEventListener("click", () => {
    const isOpen = advBody.classList.contains("open");
    advBody.classList.toggle("open", !isOpen);
    advToggle.setAttribute("aria-expanded", String(!isOpen));
  });

  $("provider").addEventListener("change", (e) => toggleApiKeyField(e.target.value));

  $("save-btn").addEventListener("click", () => {
    saveSettings().catch(() => showStatus("Failed to save settings.", "err"));
  });

  $("clear-key-btn").addEventListener("click", () => {
    clearApiKey().catch(() => showStatus("Failed to clear key.", "err"));
  });

  wireShowHide();
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  loadSettings().catch(() => showStatus("Could not load settings.", "err"));
  wireEvents();
});
