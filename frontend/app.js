// change this to your Render/Railway URL when deploying
const API = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
  ? "http://localhost:8000"
  : "https://your-app.onrender.com";  // replace with your actual Render URL

// ── Core fetch wrapper ──────────────────────────────────────
async function api(path, options = {}) {
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
    return null;
  }

  if (response.status === 401) {
    localStorage.removeItem("token");
    window.location.href = "index.html";
    return null;
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
    return null;
  }

  if (response.status === 204) return null;

  try {
    return await response.json();
  } catch {
    return null;
  }
}

// ── Toast notifications ─────────────────────────────────────
function showToast(message, type = "error") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const icons = { error: "✕", success: "✓" };

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] ?? "ℹ"}</span>
    <span>${message}</span>
  `;

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

function initDashboard() {
  if (!document.getElementById("app-list")) return;

  const token = localStorage.getItem("token");
  if (!token) {
    window.location.href = "index.html";
    return;
  }

  // Display user email decoded from JWT payload
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    const emailEl = document.getElementById("user-email");
    if (emailEl && payload.sub) emailEl.textContent = payload.sub;
  } catch { /* ignore decode errors */ }

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

async function loadStats() {
  const data = await api("/applications/stats");
  if (!data) return;

  document.getElementById("stat-total").textContent = data.total ?? 0;
  document.getElementById("stat-applied").textContent = data.by_status?.Applied ?? 0;
  document.getElementById("stat-interview").textContent = data.by_status?.Interview ?? 0;
  document.getElementById("stat-offer").textContent = data.by_status?.Offer ?? 0;
  document.getElementById("stat-rejected").textContent = data.by_status?.Rejected ?? 0;
  document.getElementById("stat-withdrawn").textContent = data.by_status?.Withdrawn ?? 0;
}

async function loadApplications(filters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.search) params.set("search", filters.search);

  const query = params.toString() ? `?${params}` : "";
  const data = await api(`/applications${query}`);
  const list = document.getElementById("app-list");
  if (!list) return;

  if (!data || data.length === 0) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <h3>No applications found</h3>
        <p>${filters.status || filters.search ? "Try adjusting your filters." : "Add your first application to get started."}</p>
      </div>
    `;
    return;
  }

  list.innerHTML = data.map(app => `
    <div class="app-card" data-id="${app.id}">
      <div class="app-card-header">
        <div>
          <div class="app-card-company">${escapeHtml(app.company)}</div>
          <div class="app-card-role">${escapeHtml(app.role)}</div>
        </div>
        <div class="app-card-actions">
          <button class="btn btn-ghost btn-sm" onclick="openModal(${JSON.stringify(app).replace(/"/g, '&quot;')})">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteApplication(${app.id})">Delete</button>
        </div>
      </div>
      <div class="app-card-meta">
        ${statusBadge(app.status)}
        <span class="app-card-date">${formatDate(app.date_applied)}</span>
      </div>
      ${app.notes ? `<div class="app-card-notes">${escapeHtml(app.notes)}</div>` : ""}
      ${app.url ? `<a class="app-card-url" href="${escapeHtml(app.url)}" target="_blank" rel="noopener noreferrer">↗ View posting</a>` : ""}
    </div>
  `).join("");
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

  if (result !== null) {
    closeModal();
    await Promise.all([loadStats(), loadApplications(dashboardState)]);
    showToast(id ? "Application updated." : "Application added.", "success");
  }
}

async function deleteApplication(id) {
  if (!confirm("Delete this application? This cannot be undone.")) return;

  const token = localStorage.getItem("token");
  let ok = false;

  try {
    const response = await fetch(`${API}/applications/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });

    if (response.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "index.html";
      return;
    }

    if (response.status === 204) {
      ok = true;
    } else {
      let detail = `Delete failed (${response.status})`;
      try {
        const body = await response.json();
        if (body.detail) detail = typeof body.detail === "string" ? body.detail : detail;
      } catch { /* non-JSON */ }
      showToast(detail, "error");
    }
  } catch {
    showToast("Could not reach server", "error");
  }

  if (ok) {
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
