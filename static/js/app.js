/**
 * NetWatch — Core Application JavaScript
 * Shared utilities, sidebar, toasts, polling, and API helpers.
 */

/* ── Sidebar Toggle ─────────────────────────────────────────────── */
const sidebar     = document.getElementById('sidebar');
const mainContent = document.getElementById('mainContent');
const topbar      = document.getElementById('topbar');
const sidebarToggle = document.getElementById('sidebarToggle');

let sidebarCollapsed = window.innerWidth < 768;

function applySidebarState() {
  if (sidebarCollapsed) {
    sidebar.classList.add('collapsed');
    mainContent.classList.add('sidebar-collapsed');
    topbar.classList.add('sidebar-collapsed');
  } else {
    sidebar.classList.remove('collapsed');
    mainContent.classList.remove('sidebar-collapsed');
    topbar.classList.remove('sidebar-collapsed');
  }
}

if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => {
    sidebarCollapsed = !sidebarCollapsed;
    applySidebarState();
  });
}

// Mobile overlay click closes sidebar
document.addEventListener('click', (e) => {
  if (window.innerWidth <= 768 && !sidebarCollapsed) {
    if (!sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
      sidebarCollapsed = true;
      applySidebarState();
    }
  }
});

applySidebarState();


/* ── Toast Notifications ────────────────────────────────────────── */
let _toastId = 0;

function showToast(title, message, type = 'info', duration = 4000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const id    = ++_toastId;
  const icons = { online: '✅', offline: '🔴', info: 'ℹ️', warning: '⚠️', error: '❌' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.id = `toast-${id}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
    <div class="toast-body">
      <div class="toast-title">${escHtml(title)}</div>
      <div class="toast-msg">${escHtml(message)}</div>
    </div>
    <button onclick="dismissToast(${id})" style="background:none;border:none;color:var(--color-text-muted);cursor:pointer;margin-left:8px;font-size:1rem;">×</button>
  `;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  if (duration > 0) setTimeout(() => dismissToast(id), duration);
}

function dismissToast(id) {
  const toast = document.getElementById(`toast-${id}`);
  if (!toast) return;
  toast.classList.remove('show');
  setTimeout(() => toast.remove(), 300);
}


/* ── API Helpers ────────────────────────────────────────────────── */
async function apiFetch(url, options = {}) {
  const defaults = {
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
  };
  const merged = { ...defaults, ...options };
  if (merged.body && typeof merged.body === 'object') {
    merged.body = JSON.stringify(merged.body);
  }
  try {
    const resp = await fetch(url, merged);
    const json = await resp.json().catch(() => ({ success: false, message: 'Invalid JSON response' }));
    return { ok: resp.ok, status: resp.status, data: json };
  } catch (err) {
    return { ok: false, status: 0, data: { success: false, message: err.message } };
  }
}

async function apiGet(url)                 { return apiFetch(url, { method: 'GET' }); }
async function apiPost(url, body)          { return apiFetch(url, { method: 'POST',  body }); }
async function apiPut(url, body)           { return apiFetch(url, { method: 'PUT',   body }); }
async function apiDelete(url)              { return apiFetch(url, { method: 'DELETE' }); }
async function apiPatch(url, body = {})    { return apiFetch(url, { method: 'PATCH', body }); }


/* ── Formatting Helpers ─────────────────────────────────────────── */
function escHtml(str) {
  const d = document.createElement('div');
  d.textContent = str ?? '';
  return d.innerHTML;
}

function formatTs(isoStr) {
  if (!isoStr) return '—';
  try {
    return new Date(isoStr).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch { return isoStr; }
}

function formatTsRelative(isoStr) {
  if (!isoStr) return '—';
  const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
  if (diff < 5)   return 'just now';
  if (diff < 60)  return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
}

function formatRt(ms) {
  if (ms == null) return '<span class="rt-none">—</span>';
  const cls = ms < 50 ? 'rt-fast' : ms < 200 ? 'rt-medium' : 'rt-slow';
  return `<span class="${cls}">${ms.toFixed(1)} ms</span>`;
}

function statusBadge(status) {
  const map = {
    online:  ['badge-online',  'fa-circle-check',  'Online'],
    offline: ['badge-offline', 'fa-circle-xmark',  'Offline'],
    unknown: ['badge-unknown', 'fa-circle-question','Unknown'],
  };
  const [cls, icon, label] = map[status] || map.unknown;
  return `<span class="badge ${cls}"><span class="badge-dot"></span>${escHtml(label)}</span>`;
}

function deviceTypeIcon(type) {
  const icons = {
    Router:   'fa-wifi',
    Server:   'fa-server',
    Computer: 'fa-desktop',
    Switch:   'fa-shuffle',
    Printer:  'fa-print',
    Other:    'fa-microchip',
  };
  return icons[type] || icons.Other;
}

function severityBadge(sev) {
  const map = {
    info:     'badge-info',
    warning:  'badge-warning',
    error:    'badge-offline',
    critical: 'badge-offline',
  };
  return `<span class="badge ${map[sev] || 'badge-info'}">${escHtml(sev)}</span>`;
}

function eventTypeIcon(type) {
  const map = {
    device_online:    { cls: 'online',  icon: '✅' },
    device_offline:   { cls: 'offline', icon: '🔴' },
    device_added:     { cls: 'info',    icon: '➕' },
    device_updated:   { cls: 'info',    icon: '✏️' },
    device_deleted:   { cls: 'warning', icon: '🗑️' },
    monitoring_start: { cls: 'info',    icon: '▶️' },
    monitoring_stop:  { cls: 'warning', icon: '⏹️' },
    monitoring_error: { cls: 'error',   icon: '⚠️' },
    manual_test:      { cls: 'info',    icon: '🔍' },
    settings_changed: { cls: 'info',    icon: '⚙️' },
  };
  return map[type] || { cls: 'info', icon: 'ℹ️' };
}


/* ── Topbar polling ─────────────────────────────────────────────── */
async function updateTopbarStatus() {
  const r = await apiGet('/api/health');
  if (!r.ok) return;
  const dot  = document.getElementById('monitorDot');
  const txt  = document.getElementById('monitorStatusText');
  if (dot && txt) {
    if (r.data.data?.monitoring_running) {
      dot.classList.remove('offline');
      txt.textContent = 'Monitoring Active';
    } else {
      dot.classList.add('offline');
      txt.textContent = 'Monitoring Stopped';
    }
  }
  // Unread badge
  const unreadEl = document.getElementById('notifBadge');
  const sidebarUnread = document.getElementById('sidebar-unread');
  const r2 = await apiGet('/api/events?limit=1');
  if (r2.ok) {
    const cnt = r2.data?.unread_count ?? 0;
    [unreadEl, sidebarUnread].forEach(el => {
      if (!el) return;
      el.textContent = cnt > 99 ? '99+' : cnt;
      el.style.display = cnt > 0 ? 'flex' : 'none';
    });
  }
  // Refresh time
  const refreshEl = document.getElementById('topbarRefresh');
  if (refreshEl) refreshEl.textContent = `Refreshed ${formatTsRelative(new Date().toISOString())}`;
}

// Page-specific refresh callback — override in each page
window.triggerRefresh = function () { updateTopbarStatus(); };

// Poll every 5 seconds
setInterval(updateTopbarStatus, 5000);
updateTopbarStatus();


/* ── Confirm Dialog ─────────────────────────────────────────────── */
function confirmDialog(message) {
  return window.confirm(message);
}


/* ── Chart.js Default Styles ────────────────────────────────────── */
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.color = '#3b6189';
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.padding = 16;
Chart.defaults.elements.line.tension = 0.4;
Chart.defaults.elements.line.borderWidth = 2;
Chart.defaults.elements.point.radius = 3;
Chart.defaults.elements.point.hoverRadius = 5;


/* ── Tiny Modal helper ─────────────────────────────────────────── */
function openModal(id)  { document.getElementById(id)?.classList.add('open');  }
function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
  }
});
