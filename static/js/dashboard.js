/**
 * NetWatch — Dashboard Page JavaScript
 */

let donutChart = null;
let rtChart    = null;
let trendChart = null;

let _allDevices = [];

// ── Main Load ─────────────────────────────────────────────────────

async function loadDashboard() {
  const r = await apiGet('/api/dashboard');
  if (!r.ok) {
    showToast('Error', r.data?.message || 'Failed to load dashboard', 'error');
    return;
  }
  const d = r.data.data;

  // Stat cards
  const counts = d.counts || {};
  document.getElementById('statTotal').textContent   = counts.total   ?? 0;
  document.getElementById('statOnline').textContent  = counts.online  ?? 0;
  document.getElementById('statOffline').textContent = counts.offline ?? 0;
  document.getElementById('statUnknown').textContent = counts.unknown ?? 0;

  const avgRt = d.avg_response_ms;
  document.getElementById('statAvgRt').innerHTML = avgRt != null
    ? `<span style="font-size:1.5rem">${avgRt.toFixed(1)}</span><span style="font-size:0.9rem;margin-left:3px;">ms</span>`
    : '—';

  const avail = d.availability_pct;
  document.getElementById('statAvail').innerHTML = avail != null
    ? `${avail.toFixed(1)}<span style="font-size:1rem;">%</span>`
    : '—';

  // Store devices globally
  _allDevices = d.devices || [];

  // Populate device selector for RT chart
  populateDeviceSelector(_allDevices);

  // Donut chart
  renderDonut(counts);

  // RT chart (use first device or placeholder)
  const firstDevice = _allDevices.find(dv => dv.current_status === 'online') || _allDevices[0];
  if (firstDevice) {
    await loadRtChart(firstDevice.id);
  }

  // Availability trend
  await loadTrendChart(document.getElementById('trendRange').value);

  // Recent events
  renderRecentEvents(d.recent_events || []);

  // Device table
  renderDeviceTable(_allDevices);
}

// ── Donut Chart ───────────────────────────────────────────────────

function renderDonut(counts) {
  const online  = counts.online  || 0;
  const offline = counts.offline || 0;
  const unknown = counts.unknown || 0;
  const total   = counts.total   || 0;

  const canvas  = document.getElementById('donutChart');
  const emptyEl = document.getElementById('donutEmpty');

  if (total === 0) {
    canvas.style.display = 'none';
    emptyEl.style.display = 'block';
    return;
  }
  canvas.style.display = '';
  emptyEl.style.display = 'none';

  if (donutChart) donutChart.destroy();
  donutChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: ['Online', 'Offline', 'Unknown'],
      datasets: [{
        data: [online, offline, unknown],
        backgroundColor: ['rgba(29,185,84,0.8)', 'rgba(229,57,53,0.8)', 'rgba(120,144,156,0.8)'],
        borderColor:     ['#1db954', '#e53935', '#78909c'],
        borderWidth: 2,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      cutout: '68%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 12,
            padding: 12,
            font: { size: 11, family: "'Plus Jakarta Sans', sans-serif" },
          },
        },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.raw} (${total > 0 ? ((ctx.raw/total)*100).toFixed(1) : 0}%)`,
          },
        },
      },
    },
  });
}

// ── Response Time Chart ───────────────────────────────────────────

async function loadRtChart(deviceId) {
  const url = deviceId
    ? `/api/devices/${deviceId}/history?range=24h`
    : '/api/analytics?range=24h';

  const r = await apiGet(url);
  const series = r.ok ? (r.data.data?.time_series || []) : [];

  const labels = series.map(p => {
    const d = new Date(p.checked_at);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  });
  const values = series.map(p => p.is_reachable ? p.response_time_ms : null);

  const canvas = document.getElementById('rtChart');
  if (rtChart) rtChart.destroy();

  if (series.length === 0) {
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    rtChart = null;
    return;
  }

  rtChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Response Time (ms)',
        data: values,
        borderColor: '#1a78c2',
        backgroundColor: 'rgba(26,120,194,0.1)',
        fill: true,
        spanGaps: true,
        pointBackgroundColor: values.map(v => v == null ? '#e53935' : '#1a78c2'),
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: 'ms' } },
        x: { ticks: { maxTicksLimit: 8, maxRotation: 30 } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

// ── Availability Trend Chart ──────────────────────────────────────

async function loadTrendChart(range) {
  const r = await apiGet(`/api/analytics?range=${range}`);
  const trend = r.ok ? (r.data.data?.availability_trend || []) : [];

  const labels = trend.map(t => t.bucket);
  const values = trend.map(t => t.availability_pct);

  const canvas = document.getElementById('trendChart');
  if (trendChart) trendChart.destroy();

  if (trend.length === 0) {
    trendChart = null;
    return;
  }

  trendChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Availability %',
        data: values,
        borderColor: '#1db954',
        backgroundColor: 'rgba(29,185,84,0.08)',
        fill: true,
        spanGaps: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 100, title: { display: true, text: '%' } },
        x: { ticks: { maxTicksLimit: 10, maxRotation: 30 } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

// ── Recent Events ─────────────────────────────────────────────────

function renderRecentEvents(events) {
  const container = document.getElementById('recentEventsContainer');
  if (!events.length) {
    container.innerHTML = `<div class="empty-state" style="padding:20px;">
      <div class="empty-state-icon" style="font-size:2rem;">🔔</div>
      <p>No events yet. Add a device to start monitoring.</p>
    </div>`;
    return;
  }

  const html = events.slice(0, 15).map(ev => {
    const { cls, icon } = eventTypeIcon(ev.event_type);
    return `<div class="event-item ${cls}" style="margin-bottom:6px;">
      <span class="event-icon">${icon}</span>
      <div class="event-body">
        <div class="event-msg">${escHtml(ev.message)}</div>
        <div class="event-meta">${ev.device_name ? escHtml(ev.device_name) + ' · ' : ''}${formatTs(ev.created_at)}</div>
      </div>
    </div>`;
  }).join('');

  container.innerHTML = html;
}

// ── Device Table ──────────────────────────────────────────────────

function renderDeviceTable(devices) {
  const tbody = document.getElementById('deviceTableBody');

  if (!devices.length) {
    tbody.innerHTML = `<tr><td colspan="7">
      <div class="empty-state" style="padding:32px 24px;">
        <div class="empty-state-icon"><i class="fa-solid fa-server"></i></div>
        <h3>No Devices Registered</h3>
        <p>Add your first network device to start monitoring.</p>
        <a href="/devices" class="btn btn-primary"><i class="fa-solid fa-plus"></i> Add Device</a>
      </div>
    </td></tr>`;
    return;
  }

  tbody.innerHTML = devices.map(d => `
    <tr>
      <td>
        <div style="display:flex;align-items:center;gap:10px;">
          <div class="device-type-icon"><i class="fa-solid ${deviceTypeIcon(d.device_type)}"></i></div>
          <div>
            <div class="font-semibold">${escHtml(d.name)}</div>
            <div class="text-muted text-sm">${escHtml(d.location || '—')}</div>
          </div>
        </div>
      </td>
      <td><code style="font-size:0.82rem;background:rgba(26,120,194,0.08);padding:2px 7px;border-radius:5px;">${escHtml(d.target)}</code></td>
      <td><span class="badge badge-info">${escHtml(d.device_type)}</span></td>
      <td>${statusBadge(d.current_status)}</td>
      <td id="rt-${d.id}">—</td>
      <td class="text-muted text-sm">${formatTsRelative(d.last_checked_at)}</td>
      <td>
        <div style="display:flex;gap:5px;">
          <a href="/devices/${d.id}" class="btn btn-sm btn-outline" title="Details"><i class="fa-solid fa-eye"></i></a>
          <button class="btn btn-sm btn-success" onclick="quickTest(${d.id})" title="Test now"><i class="fa-solid fa-bolt"></i></button>
        </div>
      </td>
    </tr>
  `).join('');

  // Fill in response times from analytics cache
  devices.forEach(d => {
    const el = document.getElementById(`rt-${d.id}`);
    if (el) {
      // Fetch latest probe for this device
      apiGet(`/api/devices/${d.id}/history?range=1h`).then(r => {
        if (r.ok) {
          const series = r.data.data?.time_series || [];
          const latest = series[series.length - 1];
          if (latest && latest.is_reachable) {
            el.innerHTML = formatRt(latest.response_time_ms);
          } else {
            el.innerHTML = latest ? '<span class="rt-none">Offline</span>' : '—';
          }
        }
      });
    }
  });
}

// ── Device Selector for RT Chart ──────────────────────────────────

function populateDeviceSelector(devices) {
  const sel = document.getElementById('rtDeviceSelect');
  if (!sel) return;
  // Keep first "All" option
  const existing = Array.from(sel.options).map(o => o.value);
  devices.forEach(d => {
    if (!existing.includes(String(d.id))) {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = `${d.name} (${d.target})`;
      sel.appendChild(opt);
    }
  });
}

// ── Filters ───────────────────────────────────────────────────────

function applyFilters() {
  const q      = document.getElementById('devSearch').value.toLowerCase();
  const status = document.getElementById('devStatusFilter').value;
  const type   = document.getElementById('devTypeFilter').value;

  const filtered = _allDevices.filter(d => {
    const matchQ = !q || d.name.toLowerCase().includes(q) || d.target.toLowerCase().includes(q);
    const matchS = !status || d.current_status === status;
    const matchT = !type   || d.device_type === type;
    return matchQ && matchS && matchT;
  });
  renderDeviceTable(filtered);
}

['devSearch', 'devStatusFilter', 'devTypeFilter'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', applyFilters);
  document.getElementById(id)?.addEventListener('change', applyFilters);
});

// ── Quick Test ────────────────────────────────────────────────────

async function quickTest(deviceId) {
  showToast('Testing', 'Running connectivity test…', 'info', 2000);
  const r = await apiPost(`/api/devices/${deviceId}/test`, {});
  if (!r.ok && r.status === 429) {
    showToast('Rate Limited', r.data.message, 'warning');
    return;
  }
  if (!r.ok) {
    showToast('Error', r.data?.message || 'Test failed', 'error');
    return;
  }
  const result = r.data.data;
  if (result.is_reachable) {
    showToast('Online', `Device is reachable (${result.response_time_ms?.toFixed(1) ?? '?'} ms)`, 'online');
  } else {
    showToast('Offline', `Device is not reachable — ${result.error_category || 'no response'}`, 'offline');
  }
  setTimeout(loadDashboard, 1000);
}

// ── Refresh & Event Listeners ─────────────────────────────────────

window.triggerRefresh = loadDashboard;

document.getElementById('rtDeviceSelect')?.addEventListener('change', function() {
  loadRtChart(this.value ? parseInt(this.value) : null);
});

document.getElementById('trendRange')?.addEventListener('change', function() {
  loadTrendChart(this.value);
});

// Initial load
loadDashboard();

// Auto-refresh every 5 seconds
setInterval(loadDashboard, 5000);
