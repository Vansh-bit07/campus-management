const API_STORAGE_KEY = "gather.apiBase";
const USER_STORAGE_KEY = "gather.userId";
const DEFAULT_API_BASE = window.location.pathname.startsWith("/app/")
  ? window.location.origin
  : "http://127.0.0.1:5000";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const elements = {
  apiForm: document.querySelector("#api-form"),
  apiUrl: document.querySelector("#api-url"),
  connection: document.querySelector("#connection-status"),
  connectionLabel: document.querySelector("#connection-label"),
  eventGrid: document.querySelector("#event-grid"),
  eventsCount: document.querySelector("#events-count"),
  loadRegistrations: document.querySelector("#load-registrations"),
  profileForm: document.querySelector("#profile-form"),
  refreshButton: document.querySelector("#refresh-button"),
  registrationsList: document.querySelector("#registrations-list"),
  searchInput: document.querySelector("#search-input"),
  settingsButton: document.querySelector("#settings-button"),
  settingsDialog: document.querySelector("#settings-dialog"),
  statusFilter: document.querySelector("#status-filter"),
  toast: document.querySelector("#toast"),
  userId: document.querySelector("#user-id"),
};

const state = {
  apiBase: localStorage.getItem(API_STORAGE_KEY) || DEFAULT_API_BASE,
  events: [],
  userId: localStorage.getItem(USER_STORAGE_KEY) || "",
  toastTimer: null,
};

elements.userId.value = state.userId;
elements.apiUrl.value = state.apiBase;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function normalizeApiBase(value) {
  const parsed = new URL(value.trim());
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("Use an http:// or https:// API address.");
  }
  return parsed.origin + parsed.pathname.replace(/\/+$/, "");
}

async function apiRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(`${state.apiBase}${path}`, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new Error("Could not reach the API. Check the URL, server, and CORS settings.");
  }

  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = body && typeof body === "object" && body.detail
      ? body.detail
      : `The API returned ${response.status}.`;
    throw new Error(message);
  }

  return body;
}

function showToast(message, isError = false) {
  window.clearTimeout(state.toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", isError);
  elements.toast.classList.add("visible");
  state.toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("visible");
  }, 3600);
}

function setConnection(online, label) {
  elements.connection.classList.toggle("online", online);
  elements.connection.classList.toggle("offline", !online);
  elements.connectionLabel.textContent = label;
}

async function checkHealth() {
  setConnection(false, "Connecting");
  try {
    const health = await apiRequest("/health");
    const online = health.status === "ok";
    setConnection(online, online ? "API online" : "API degraded");
  } catch {
    setConnection(false, "API offline");
  }
}

function eventArtSymbol(title) {
  const symbols = ["✳", "✦", "◒", "✺", "⌁", "✷"];
  const total = [...String(title || "")].reduce((sum, character) => sum + character.charCodeAt(0), 0);
  return symbols[total % symbols.length];
}

function eventCard(event) {
  const id = String(event.id ?? "");
  const title = String(event.title || "Untitled event");
  const status = String(event.status || "unknown");
  const count = Number(event.registration_count) || 0;
  const capacity = Number(event.capacity);
  const hasCapacity = Number.isFinite(capacity) && capacity >= 0;
  const full = hasCapacity && count >= capacity;
  const canRegister = status === "published" && !full;
  const countLabel = hasCapacity ? `${count} / ${capacity} spots` : `${count} registered`;
  const buttonLabel = full ? "Full" : status === "published" ? "Join event" : "Not open";

  return `
    <article class="event-card">
      <div class="event-art" aria-hidden="true"><span class="event-symbol">${eventArtSymbol(title)}</span></div>
      <div class="event-card-body">
        <div class="event-meta">
          <span class="event-status ${escapeHtml(status)}">${escapeHtml(status)}</span>
          <span>ON CAMPUS</span>
        </div>
        <h3>${escapeHtml(title)}</h3>
        <p class="event-organizer">Organized by ${escapeHtml(event.organizer_id || "Campus community")}</p>
        <div class="event-bottom">
          <span class="capacity"><strong>${escapeHtml(countLabel)}</strong></span>
          <button class="register-button" type="button" data-register-id="${escapeHtml(id)}" ${canRegister ? "" : "disabled"}>
            ${escapeHtml(buttonLabel)}
          </button>
        </div>
      </div>
    </article>
  `;
}

function renderEvents() {
  const query = elements.searchInput.value.trim().toLocaleLowerCase();
  const visibleEvents = state.events.filter((event) => {
    const searchableText = `${event.title || ""} ${event.status || ""} ${event.organizer_id || ""}`.toLocaleLowerCase();
    return searchableText.includes(query);
  });
  const total = visibleEvents.length;
  elements.eventsCount.innerHTML = `${total} ${total === 1 ? "EVENT" : "EVENTS"}<span class="count-mark">✳</span>`;

  if (!total) {
    elements.eventGrid.innerHTML = `
      <div class="empty-state">
        <span class="empty-symbol" aria-hidden="true">✳</span>
        <p><strong>No events found</strong>Try a different search or event status.</p>
      </div>
    `;
    return;
  }

  elements.eventGrid.innerHTML = visibleEvents.map(eventCard).join("");
}

async function loadEvents() {
  elements.eventGrid.setAttribute("aria-busy", "true");
  elements.refreshButton.disabled = true;
  elements.eventGrid.innerHTML = '<div class="loading-card"><span class="loader" aria-hidden="true"></span><p>Finding the good stuff...</p></div>';
  const status = elements.statusFilter.value;
  const params = new URLSearchParams({ limit: "100", offset: "0" });
  if (status) params.set("status", status);

  try {
    const events = await apiRequest(`/api/events?${params.toString()}`);
    if (!Array.isArray(events)) throw new Error("The API returned events in an unexpected format.");
    state.events = events;
    renderEvents();
    checkHealth();
  } catch (error) {
    state.events = [];
    elements.eventsCount.textContent = "EVENTS UNAVAILABLE";
    elements.eventGrid.innerHTML = `
      <div class="error-state">
        <strong>We couldn’t load events.</strong>
        <p>${escapeHtml(error.message)}</p>
        <button class="retry-button" type="button" data-action="retry">Try again</button>
      </div>
    `;
    setConnection(false, "API offline");
  } finally {
    elements.eventGrid.setAttribute("aria-busy", "false");
    elements.refreshButton.disabled = false;
  }
}

async function registerForEvent(eventId, button) {
  if (!state.userId) {
    showToast("Save your user UUID below before registering.", true);
    elements.userId.focus();
    return;
  }
  if (!UUID_PATTERN.test(state.userId)) {
    showToast("Enter a valid user UUID before registering.", true);
    elements.userId.focus();
    return;
  }

  button.disabled = true;
  button.textContent = "Joining...";
  try {
    await apiRequest("/api/registrations", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": state.userId,
      },
      body: JSON.stringify({ event_id: eventId }),
    });
    showToast("You’re in. See you there!");
    await Promise.all([loadEvents(), loadRegistrations()]);
  } catch (error) {
    showToast(error.message, true);
    button.disabled = false;
    button.textContent = "Join event";
  }
}

function formatRegistrationDate(value) {
  if (!value) return "JOINED";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "JOINED";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

async function loadRegistrations() {
  if (!state.userId) {
    elements.registrationsList.innerHTML = '<p class="muted-message">Add your user ID to see the events you’ve joined.</p>';
    showToast("Save your user UUID to view your registrations.", true);
    elements.userId.focus();
    return;
  }
  if (!UUID_PATTERN.test(state.userId)) {
    showToast("Enter a valid user UUID to view registrations.", true);
    elements.userId.focus();
    return;
  }

  elements.registrationsList.innerHTML = '<p class="muted-message">Loading your events...</p>';
  try {
    const registrations = await apiRequest("/api/me/registrations", {
      headers: { "X-User-Id": state.userId },
    });
    if (!Array.isArray(registrations)) throw new Error("The API returned registrations in an unexpected format.");
    const eventById = new Map(state.events.map((event) => [String(event.id), event]));
    if (!registrations.length) {
      elements.registrationsList.innerHTML = '<p class="muted-message">No registrations yet. Pick an event and make a plan.</p>';
      return;
    }

    elements.registrationsList.innerHTML = registrations.map((registration) => {
      const eventId = String(registration.event_id || "");
      const event = eventById.get(eventId);
      const eventName = event ? event.title : `Event ${eventId.slice(0, 8)}`;
      return `
        <article class="registration-row">
          <span class="registration-date">${escapeHtml(formatRegistrationDate(registration.created_at))}</span>
          <span class="registration-info">
            <strong>${escapeHtml(eventName)}</strong>
            <span>CONFIRMED · ${escapeHtml(eventId)}</span>
          </span>
        </article>
      `;
    }).join("");
  } catch (error) {
    elements.registrationsList.innerHTML = `<p class="muted-message">${escapeHtml(error.message)}</p>`;
  }
}

elements.profileForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const userId = elements.userId.value.trim();
  if (!UUID_PATTERN.test(userId)) {
    showToast("Enter a valid UUID, for example 123e4567-e89b-12d3-a456-426614174000.", true);
    elements.userId.focus();
    return;
  }

  state.userId = userId;
  localStorage.setItem(USER_STORAGE_KEY, userId);
  showToast("User ID saved on this device.");
});

elements.apiForm.addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    state.apiBase = normalizeApiBase(elements.apiUrl.value);
    localStorage.setItem(API_STORAGE_KEY, state.apiBase);
    elements.settingsDialog.close();
    showToast("API connection updated.");
    checkHealth();
    loadEvents();
  } catch (error) {
    showToast(error.message || "Enter a valid API URL.", true);
  }
});

elements.settingsButton.addEventListener("click", () => {
  elements.apiUrl.value = state.apiBase;
  elements.settingsDialog.showModal();
});

elements.refreshButton.addEventListener("click", loadEvents);
elements.statusFilter.addEventListener("change", loadEvents);
elements.searchInput.addEventListener("input", renderEvents);
elements.loadRegistrations.addEventListener("click", loadRegistrations);

elements.eventGrid.addEventListener("click", (event) => {
  const retryButton = event.target.closest('[data-action="retry"]');
  if (retryButton) {
    loadEvents();
    return;
  }
  const registerButton = event.target.closest("[data-register-id]");
  if (registerButton) registerForEvent(registerButton.dataset.registerId, registerButton);
});

checkHealth();
loadEvents();
