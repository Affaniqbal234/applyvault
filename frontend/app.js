const API = (() => {
  try {
    const configured = window.APPLYVAULT_CONFIG?.apiUrl;
    const url = new URL(configured);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
        || url.pathname !== '/' || url.search || url.hash
        || (location.protocol === 'https:' && url.protocol !== 'https:')) {
      throw new Error('Invalid API origin');
    }
    return url.origin;
  } catch {
    document.addEventListener('DOMContentLoaded', () => {
      document.querySelectorAll('button').forEach(button => { button.disabled = true; });
      showToast('Service configuration is unavailable. Please contact the site owner.', 'error');
    });
    return null;
  }
})();

// ── Core fetch wrapper ──────────────────────────────────────
async function api(path, options = {}) {
  if (!API) return { ok: false, data: null };
  const token = localStorage.getItem("token");

  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers ?? {}),
  };

  let response;
  try {
    response = await fetch(`${API}${path}`, { ...options, headers });
  } catch {
    showToast("Could not reach server", "error");
    return { ok: false, data: null };
  }

  if (response.status === 401) {
    localStorage.removeItem("token");
    window.location.href = "index.html";
    return { ok: false, data: null };
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body.detail) {
        detail = typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
      }
    } catch { /* non-JSON error body */ }
    showToast(detail, "error");
    return { ok: false, data: null };
  }

  if (response.status === 204) return { ok: true, data: null };

  try {
    return { ok: true, data: await response.json() };
  } catch {
    showToast("Server returned an invalid response", "error");
    return { ok: false, data: null };
  }
}

// ── Toast notifications ─────────────────────────────────────
function showToast(message, type = "error") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const icons = { error: "✕", success: "✓" };

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  const icon = document.createElement("span");
  icon.className = "toast-icon";
  icon.textContent = icons[type] ?? "ℹ";
  const text = document.createElement("span");
  text.textContent = message;
  toast.append(icon, text);

  container.appendChild(toast);

  const dismiss = () => {
    toast.classList.add("leaving");
    toast.addEventListener("animationend", () => toast.remove(), { once: true });
  };

  setTimeout(dismiss, 4000);
  toast.addEventListener("click", dismiss);
}

// ── Auth page logic ─────────────────────────────────────────
(function initAuth() {
  // Only run on auth page
  const loginForm = document.getElementById("login-form");
  const registerForm = document.getElementById("register-form");
  if (!loginForm && !registerForm) return;

  // Tab switching
  const tabs = document.querySelectorAll(".auth-tab");
  const panels = document.querySelectorAll(".auth-panel");

  function switchTab(target) {
    tabs.forEach(tab => {
      const active = tab.dataset.tab === target;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });

    panels.forEach(panel => {
      panel.classList.toggle("hidden", panel.id !== `panel-${target}`);
    });
  }

  tabs.forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  // Redirect if already logged in
  if (localStorage.getItem("token")) {
    window.location.href = "dashboard.html";
    return;
  }

  // Login handler
  loginForm?.addEventListener("submit", async e => {
    e.preventDefault();

    const errorEl = document.getElementById("login-error");
    const submitBtn = document.getElementById("login-submit");
    const email = loginForm.email.value.trim();
    const password = loginForm.password.value;

    errorEl.textContent = "";
    submitBtn.disabled = true;
    submitBtn.textContent = "Signing in…";

    const data = await loginRequest(email, password);

    submitBtn.disabled = false;
    submitBtn.textContent = "Sign In";

    if (!data) return; // api() already showed toast for network errors

    if (data.access_token) {
      localStorage.setItem("token", data.access_token);
      window.location.href = "dashboard.html";
    }
  });

  // Register handler
  registerForm?.addEventListener("submit", async e => {
    e.preventDefault();

    const errorEl = document.getElementById("register-error");
    const successEl = document.getElementById("register-success");
    const submitBtn = document.getElementById("register-submit");
    const email = registerForm.email.value.trim();
    const password = registerForm.password.value;

    errorEl.textContent = "";
    successEl.textContent = "";
    submitBtn.disabled = true;
    submitBtn.textContent = "Creating account…";

    const result = await registerRequest(email, password, errorEl);

    submitBtn.disabled = false;
    submitBtn.textContent = "Create Account";

    if (result !== null) {
      successEl.textContent = "Account created! You can now sign in.";
      registerForm.reset();
      setTimeout(() => switchTab("login"), 1200);
    }
  });
})();

// ── Auth API calls ──────────────────────────────────────────
async function loginRequest(email, password) {
  if (!API) return null;
  const errorEl = document.getElementById("login-error");

  let response;
  try {
    response = await fetch(`${API}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    if (errorEl) errorEl.textContent = "Could not reach server.";
    return null;
  }

  if (!response.ok) {
    let msg = `Sign in failed (${response.status})`;
    try {
      const body = await response.json();
      if (body.detail) msg = typeof body.detail === "string" ? body.detail : msg;
    } catch { /* non-JSON */ }
    if (errorEl) errorEl.textContent = msg;
    return null;
  }

  return response.json();
}

async function registerRequest(email, password, errorEl) {
  if (!API) return null;
  let response;
  try {
    response = await fetch(`${API}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    if (errorEl) errorEl.textContent = "Could not reach server.";
    return null;
  }

  if (!response.ok) {
    let msg = `Registration failed (${response.status})`;
    try {
      const body = await response.json();
      if (body.detail) msg = typeof body.detail === "string" ? body.detail : msg;
    } catch { /* non-JSON */ }
    if (errorEl) errorEl.textContent = msg;
    return null;
  }

  return response.json();
}

// ── Dashboard logic ─────────────────────────────────────────

const dashboardState = { status: null, search: "" };
let debounceTimer = null;
let applicationsRequestId = 0;

function initDashboard() {
  if (!document.getElementById("app-list")) return;

  const token = localStorage.getItem("token");
  if (!token) {
    window.location.href = "index.html";
    return;
  }

  loadAuthenticatedUser();
  loadStats();
  loadApplications();

  // Search — debounced 300 ms
  document.getElementById("search-input")?.addEventListener("input", e => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      dashboardState.search = e.target.value.trim();
      loadApplications(dashboardState);
    }, 300);
  });

  // Status filter pills
  document.querySelectorAll(".filter-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      dashboardState.status = pill.dataset.status || null;
      loadApplications(dashboardState);
    });
  });

  // Add button
  document.getElementById("add-btn")?.addEventListener("click", () => openModal());

  // Modal close / cancel
  document.getElementById("modal-close-btn")?.addEventListener("click", closeModal);
  document.getElementById("modal-cancel-btn")?.addEventListener("click", closeModal);

  // Close modal on overlay backdrop click
  document.getElementById("modal-overlay")?.addEventListener("click", e => {
    if (e.target === document.getElementById("modal-overlay")) closeModal();
  });

  // Form submit
  document.getElementById("modal-save-btn")?.addEventListener("click", handleFormSubmit);
  document.getElementById("app-form")?.addEventListener("submit", e => {
    e.preventDefault();
    handleFormSubmit();
  });

  // Logout
  document.getElementById("logout-btn")?.addEventListener("click", () => {
    localStorage.removeItem("token");
    window.location.href = "index.html";
  });
}

async function loadAuthenticatedUser() {
  const result = await api("/me");
  if (!result.ok || typeof result.data?.email !== "string") return;

  const emailEl = document.getElementById("user-email");
  if (emailEl) emailEl.textContent = result.data.email;
}

async function loadStats() {
  const result = await api("/applications/stats");
  if (!result.ok) return;
  const data = result.data;

  document.getElementById("stat-total").textContent = data.total ?? 0;
  document.getElementById("stat-applied").textContent = data.by_status?.Applied ?? 0;
  document.getElementById("stat-interview").textContent = data.by_status?.Interview ?? 0;
  document.getElementById("stat-offer").textContent = data.by_status?.Offer ?? 0;
  document.getElementById("stat-rejected").textContent = data.by_status?.Rejected ?? 0;
  document.getElementById("stat-withdrawn").textContent = data.by_status?.Withdrawn ?? 0;
}

async function loadApplications(filters = {}) {
  const requestId = ++applicationsRequestId;
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.search) params.set("search", filters.search);

  const query = params.toString() ? `?${params}` : "";
  const result = await api(`/applications${query}`);
  if (requestId !== applicationsRequestId) return;

  const list = document.getElementById("app-list");
  if (!list || !result.ok) return;
  const data = result.data;

  if (data.length === 0) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <h3>No applications found</h3>
        <p>${filters.status || filters.search ? "Try adjusting your filters." : "Add your first application to get started."}</p>
      </div>
    `;
    return;
  }

  list.replaceChildren(...data.map(app => {
    const card = document.createElement("div");
    card.className = "app-card";
    card.dataset.id = app.id;
    card.innerHTML = `
      <div class="app-card-header">
        <div>
          <div class="app-card-company">${escapeHtml(app.company)}</div>
          <div class="app-card-role">${escapeHtml(app.role)}</div>
        </div>
        <div class="app-card-actions">
          <button class="btn btn-ghost btn-sm" data-action="edit">Edit</button>
          <button class="btn btn-danger btn-sm" data-action="delete">Delete</button>
        </div>
      </div>
      <div class="app-card-meta">
        ${statusBadge(app.status)}
        <span class="app-card-date">${formatDate(app.date_applied)}</span>
      </div>
      ${app.notes ? `<div class="app-card-notes">${escapeHtml(app.notes)}</div>` : ""}
    `;
    card.querySelector('[data-action="edit"]').addEventListener("click", () => openModal(app));
    card.querySelector('[data-action="delete"]').addEventListener("click", () => deleteApplication(app.id));

    // Older records can contain URLs that predate server-side validation.
    const url = safePostingUrl(app.url);
    if (url) {
      const link = document.createElement("a");
      link.className = "app-card-url";
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "↗ View posting";
      card.appendChild(link);
    }
    return card;
  }));
}

function safePostingUrl(value) {
  if (typeof value !== "string" || !/^https?:\/\//i.test(value.trim())) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function openModal(app = null) {
  const overlay = document.getElementById("modal-overlay");
  const title = document.getElementById("modal-title");
  const form = document.getElementById("app-form");
  const errorEl = document.getElementById("app-form-error");

  errorEl.textContent = "";

  if (app) {
    title.textContent = "Edit Application";
    document.getElementById("app-id").value = app.id;
    document.getElementById("field-company").value = app.company ?? "";
    document.getElementById("field-role").value = app.role ?? "";
    document.getElementById("field-date").value = app.date_applied ?? "";
    document.getElementById("field-status").value = app.status ?? "Applied";
    document.getElementById("field-url").value = app.url ?? "";
    document.getElementById("field-notes").value = app.notes ?? "";
  } else {
    title.textContent = "Add Application";
    document.getElementById("app-id").value = "";
    form.reset();
  }

  overlay.classList.remove("hidden");
  document.getElementById("field-company").focus();
}

function closeModal() {
  document.getElementById("modal-overlay").classList.add("hidden");
  document.getElementById("app-form-error").textContent = "";
}

async function handleFormSubmit() {
  const errorEl = document.getElementById("app-form-error");
  errorEl.textContent = "";

  const id = document.getElementById("app-id").value;
  const company = document.getElementById("field-company").value.trim();
  const role = document.getElementById("field-role").value.trim();
  const date_applied = document.getElementById("field-date").value;
  const status = document.getElementById("field-status").value;
  const url = document.getElementById("field-url").value.trim() || null;
  const notes = document.getElementById("field-notes").value.trim() || null;

  if (!company) { errorEl.textContent = "Company is required."; return; }
  if (!role) { errorEl.textContent = "Role is required."; return; }
  if (!date_applied) { errorEl.textContent = "Date applied is required."; return; }
  if (url && !safePostingUrl(url)) {
    errorEl.textContent = "Job posting URL must be an absolute HTTP or HTTPS URL.";
    return;
  }

  const saveBtn = document.getElementById("modal-save-btn");
  saveBtn.disabled = true;
  saveBtn.textContent = "Saving…";

  const payload = { company, role, date_applied, status, url, notes };
  let result;

  if (id) {
    result = await api(`/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  } else {
    result = await api("/applications", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  saveBtn.disabled = false;
  saveBtn.textContent = "Save";

  if (result.ok) {
    closeModal();
    await Promise.all([loadStats(), loadApplications(dashboardState)]);
    showToast(id ? "Application updated." : "Application added.", "success");
  }
}

async function deleteApplication(id) {
  if (!confirm("Delete this application? This cannot be undone.")) return;

  const result = await api(`/applications/${id}`, { method: "DELETE" });
  if (result.ok) {
    await Promise.all([loadStats(), loadApplications(dashboardState)]);
    showToast("Application deleted.", "success");
  }
}

function statusBadge(status) {
  const cls = {
    Applied: "badge-applied",
    Interview: "badge-interview",
    Offer: "badge-offer",
    Rejected: "badge-rejected",
    Withdrawn: "badge-withdrawn",
  }[status] ?? "badge-applied";

  return `<span class="badge ${cls}">${escapeHtml(status)}</span>`;
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  const [year, month, day] = dateStr.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Boot dashboard on load
initDashboard();
