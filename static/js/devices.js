/**
 * NetWatch — Devices Page JavaScript
 */

let _devices = [];

// ── Load Devices ──────────────────────────────────────────────────
async function loadDevices() {
  const q      = document.getElementById('devSearch')?.value || '';
  const status = document.getElementById('devStatusFilter')?.value || '';
  const type   = document.getElementById('devTypeFilter')?.value || '';

  let url = '/api/devices?';
  if (q)      url += `q=${encodeURIComponent(q)}&`;
  if (status) url += `status=${encodeURIComponent(status)}&`;
  if (type)   url += `type=${encodeURIComponent(type)}&`;

  const r = await apiGet(url);
  if (!r.ok) {
    showToast('Error', 'Failed to load devices', 'error');
    return;
  }
  _devices = r.data.data || [];
  renderDevices(_devices);
}

// ── Render Table ──────────────────────────────────────────────────
function renderDevices(devices) {
  const tbody = document.getElementById('devicesBody');
  if (!devices.length) {
    tbody.innerHTML = `<tr><td colspan="9">
      <div class="empty-state">
        <div class="empty-state-icon"><i class="fa-solid fa-server"></i></div>
        <h3>No Devices Found</h3>
        <p>Add a device to start monitoring, or clear your filters.</p>
        <button class="btn btn-primary" onclick="openModal('addDeviceModal')">
          <i class="fa-solid fa-plus"></i> Add Your First Device
        </button>
      </div>
    </td></tr>`;
    return;
  }

  tbody.innerHTML = devices.map(d => `
    <tr>
      <td>
        <div style="display:flex;align-items:center;gap:10px;">
          <div class="device-type-icon">
            <i class="fa-solid ${deviceTypeIcon(d.device_type)}"></i>
          </div>
          <div>
            <div class="font-semibold">${escHtml(d.name)}</div>
            <div class="text-muted text-sm">ID: ${d.id}</div>
          </div>
        </div>
      </td>
      <td><code style="font-size:0.82rem;background:rgba(26,120,194,0.08);padding:2px 8px;border-radius:5px;">${escHtml(d.target)}</code></td>
      <td><span class="badge badge-info"><i class="fa-solid ${deviceTypeIcon(d.device_type)} fa-sm"></i> ${escHtml(d.device_type)}</span></td>
      <td class="text-muted text-sm">${escHtml(d.location || '—')}</td>
      <td>${statusBadge(d.current_status)}</td>
      <td id="devRt-${d.id}">—</td>
      <td class="text-muted text-sm">${formatTsRelative(d.last_checked_at)}</td>
      <td>
        <button class="btn btn-sm ${d.is_monitoring_enabled ? 'btn-success' : 'btn-outline'}"
          onclick="toggleMonitoring(${d.id}, ${d.is_monitoring_enabled ? 0 : 1})"
          title="${d.is_monitoring_enabled ? 'Disable monitoring' : 'Enable monitoring'}">
          <i class="fa-solid ${d.is_monitoring_enabled ? 'fa-pause' : 'fa-play'}"></i>
          ${d.is_monitoring_enabled ? 'Active' : 'Paused'}
        </button>
      </td>
      <td>
        <div style="display:flex;gap:5px;">
          <a href="/devices/${d.id}" class="btn btn-sm btn-outline" title="Details">
            <i class="fa-solid fa-eye"></i>
          </a>
          <button class="btn btn-sm btn-outline" onclick="openEditModal(${d.id})" title="Edit">
            <i class="fa-solid fa-pen"></i>
          </button>
          <button class="btn btn-sm btn-success" onclick="quickTest(${d.id})" title="Test now">
            <i class="fa-solid fa-bolt"></i>
          </button>
          <button class="btn btn-sm btn-danger" onclick="deleteDevice(${d.id}, '${escHtml(d.name)}')" title="Delete">
            <i class="fa-solid fa-trash"></i>
          </button>
        </div>
      </td>
    </tr>
  `).join('');

  // Async-fill response times
  devices.forEach(d => {
    apiGet(`/api/devices/${d.id}/history?range=1h`).then(r => {
      if (!r.ok) return;
      const series = r.data.data?.time_series || [];
      const latest = series[series.length - 1];
      const el = document.getElementById(`devRt-${d.id}`);
      if (!el) return;
      if (latest && latest.is_reachable) {
        el.innerHTML = formatRt(latest.response_time_ms);
      } else if (latest) {
        el.innerHTML = '<span class="badge badge-offline">Offline</span>';
      }
    });
  });
}

// ── Add Device ────────────────────────────────────────────────────
async function submitAddDevice(e) {
  e.preventDefault();
  clearErrors(['errAddName', 'errAddTarget', 'errAddInterval']);

  const name     = document.getElementById('addName').value.trim();
  const target   = document.getElementById('addTarget').value.trim();
  const type     = document.getElementById('addType').value;
  const location = document.getElementById('addLocation').value.trim();
  const interval = parseInt(document.getElementById('addInterval').value);
  const desc     = document.getElementById('addDesc').value.trim();

  // Client-side validation
  let valid = true;
  if (!name) { showError('errAddName', 'Device name is required.'); valid = false; }
  if (!target) { showError('errAddTarget', 'IP address or hostname is required.'); valid = false; }
  if (isNaN(interval) || interval < 5 || interval > 300) {
    showError('errAddInterval', 'Interval must be 5–300 seconds.');
    valid = false;
  }
  if (!valid) return;

  const btn = document.getElementById('addSubmitBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;"></span> Adding…';

  const r = await apiPost('/api/devices', {
    name, target, device_type: type, location, monitoring_interval: interval, description: desc,
  });

  btn.disabled = false;
  btn.innerHTML = '<i class="fa-solid fa-plus"></i> Add Device';

  if (!r.ok) {
    const msg = r.data?.message || 'Failed to add device';
    const field = r.data?.field;
    if (field === 'name')   showError('errAddName', msg);
    else if (field === 'target') showError('errAddTarget', msg);
    else showToast('Error', msg, 'error');
    return;
  }

  showToast('Device Added', `${name} (${target}) added successfully.`, 'online');
  closeModal('addDeviceModal');
  document.getElementById('addDeviceForm').reset();
  document.getElementById('addInterval').value = '30';
  loadDevices();
}

// ── Edit Device ───────────────────────────────────────────────────
async function openEditModal(deviceId) {
  const r = await apiGet(`/api/devices/${deviceId}`);
  if (!r.ok) { showToast('Error', 'Could not load device', 'error'); return; }
  const d = r.data.data;

  document.getElementById('editDeviceId').value  = d.id;
  document.getElementById('editName').value      = d.name;
  document.getElementById('editTarget').value    = d.target;
  document.getElementById('editType').value      = d.device_type;
  document.getElementById('editLocation').value  = d.location;
  document.getElementById('editInterval').value  = d.monitoring_interval;
  document.getElementById('editDesc').value      = d.description;
  clearErrors(['errEditName', 'errEditTarget', 'errEditInterval']);
  openModal('editDeviceModal');
}

async function submitEditDevice(e) {
  e.preventDefault();
  clearErrors(['errEditName', 'errEditTarget', 'errEditInterval']);

  const id       = document.getElementById('editDeviceId').value;
  const name     = document.getElementById('editName').value.trim();
  const target   = document.getElementById('editTarget').value.trim();
  const type     = document.getElementById('editType').value;
  const location = document.getElementById('editLocation').value.trim();
  const interval = parseInt(document.getElementById('editInterval').value);
  const desc     = document.getElementById('editDesc').value.trim();

  let valid = true;
  if (!name) { showError('errEditName', 'Device name is required.'); valid = false; }
  if (!target) { showError('errEditTarget', 'IP or hostname is required.'); valid = false; }
  if (isNaN(interval) || interval < 5 || interval > 300) {
    showError('errEditInterval', 'Interval must be 5–300 seconds.');
    valid = false;
  }
  if (!valid) return;

  const r = await apiPut(`/api/devices/${id}`, {
    name, target, device_type: type, location, monitoring_interval: interval, description: desc,
  });

  if (!r.ok) {
    const msg = r.data?.message || 'Update failed';
    const field = r.data?.field;
    if (field === 'name')   showError('errEditName', msg);
    else if (field === 'target') showError('errEditTarget', msg);
    else showToast('Error', msg, 'error');
    return;
  }

  showToast('Updated', `${name} updated successfully.`, 'info');
  closeModal('editDeviceModal');
  loadDevices();
}

// ── Delete Device ─────────────────────────────────────────────────
async function deleteDevice(id, name) {
  if (!confirmDialog(`Delete device "${name}"?\nAll probe history will be deleted.`)) return;
  const r = await apiDelete(`/api/devices/${id}`);
  if (!r.ok) { showToast('Error', r.data?.message || 'Delete failed', 'error'); return; }
  showToast('Deleted', `${name} removed.`, 'warning');
  loadDevices();
}

// ── Toggle Monitoring ─────────────────────────────────────────────
async function toggleMonitoring(id, enable) {
  const r = await apiPost(`/api/devices/${id}/monitoring`, { enabled: enable === 1 });
  if (!r.ok) { showToast('Error', r.data?.message || 'Toggle failed', 'error'); return; }
  showToast(enable ? 'Monitoring Enabled' : 'Monitoring Paused', '', enable ? 'online' : 'warning', 2500);
  loadDevices();
}

// ── Quick Test ────────────────────────────────────────────────────
async function quickTest(deviceId) {
  showToast('Testing', 'Running connectivity test…', 'info', 2000);
  const r = await apiPost(`/api/devices/${deviceId}/test`, {});
  if (r.status === 429) { showToast('Rate Limited', r.data.message, 'warning'); return; }
  if (!r.ok) { showToast('Error', r.data?.message || 'Test failed', 'error'); return; }
  const res = r.data.data;
  if (res.is_reachable) {
    showToast('Online', `Reachable — ${res.response_time_ms?.toFixed(1) ?? '?'} ms`, 'online');
  } else {
    showToast('Offline', `Not reachable — ${res.error_category || 'no response'}`, 'offline');
  }
  setTimeout(loadDevices, 800);
}

// ── Helpers ───────────────────────────────────────────────────────
function showError(id, msg) {
  const el = document.getElementById(id);
  if (el) { el.textContent = msg; el.classList.add('visible'); }
}
function clearErrors(ids) {
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = ''; el.classList.remove('visible'); }
  });
}

// ── Filter Listeners ──────────────────────────────────────────────
['devSearch', 'devStatusFilter', 'devTypeFilter'].forEach(id => {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener('input',  () => loadDevices());
    el.addEventListener('change', () => loadDevices());
  }
});

window.triggerRefresh = loadDevices;

// Initial load + auto-refresh
loadDevices();
setInterval(loadDevices, 10000);
