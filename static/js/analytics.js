/**
 * NetWatch — Analytics Page JavaScript
 */

let rtChart = null, trendChart = null;

async function initDeviceSelector() {
  const sel = document.getElementById('analyticsDevice');
  const r = await apiGet('/api/devices');
  if (!r.ok) return;
  const devices = r.data.data || [];
  devices.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d.id;
    opt.textContent = `${d.name} (${d.target})`;
    sel.appendChild(opt);
  });
}

async function loadAnalytics() {
  const deviceId = document.getElementById('analyticsDevice').value;
  const range    = document.getElementById('analyticsRange').value;

  let url = `/api/analytics?range=${range}`;
  if (deviceId) url += `&device_id=${deviceId}`;

  const r = await apiGet(url);
  if (!r.ok) { showToast('Error', 'Failed to load analytics', 'error'); return; }

  const data  = r.data.data;
  const a     = data.analytics || {};
  const trend = data.availability_trend || [];
  const ts    = data.time_series || [];

  // Stat grid
  document.getElementById('analyticsStatGrid').innerHTML = `
    <div class="stat-card online">
      <div class="stat-icon online"><i class="fa-solid fa-percent"></i></div>
      <div class="stat-value">${a.availability_pct != null ? a.availability_pct.toFixed(2)+'%' : '—'}</div>
      <div class="stat-label">Availability</div>
    </div>
    <div class="stat-card offline">
      <div class="stat-icon offline"><i class="fa-solid fa-triangle-exclamation"></i></div>
      <div class="stat-value">${a.packet_loss_pct != null ? a.packet_loss_pct.toFixed(2)+'%' : '—'}</div>
      <div class="stat-label">Packet Loss</div>
    </div>
    <div class="stat-card info">
      <div class="stat-icon info"><i class="fa-solid fa-clock"></i></div>
      <div class="stat-value" style="font-size:1.5rem;">${a.avg_response_ms != null ? a.avg_response_ms.toFixed(1) : '—'}</div>
      <div class="stat-label">Avg Response (ms)</div>
    </div>
    <div class="stat-card info">
      <div class="stat-icon info"><i class="fa-solid fa-bolt"></i></div>
      <div class="stat-value" style="font-size:1.5rem;">${a.min_response_ms != null ? a.min_response_ms.toFixed(1) : '—'}</div>
      <div class="stat-label">Min Response (ms)</div>
    </div>
    <div class="stat-card warning">
      <div class="stat-icon warning"><i class="fa-solid fa-hourglass-end"></i></div>
      <div class="stat-value" style="font-size:1.5rem;">${a.max_response_ms != null ? a.max_response_ms.toFixed(1) : '—'}</div>
      <div class="stat-label">Max Response (ms)</div>
    </div>
    <div class="stat-card online">
      <div class="stat-icon online"><i class="fa-solid fa-circle-check"></i></div>
      <div class="stat-value">${a.successful_probes ?? 0}</div>
      <div class="stat-label">Successful Probes</div>
    </div>
    <div class="stat-card offline">
      <div class="stat-icon offline"><i class="fa-solid fa-circle-xmark"></i></div>
      <div class="stat-value">${a.failed_probes ?? 0}</div>
      <div class="stat-label">Failed Probes</div>
    </div>
    <div class="stat-card info">
      <div class="stat-icon info"><i class="fa-solid fa-database"></i></div>
      <div class="stat-value">${a.total_probes ?? 0}</div>
      <div class="stat-label">Total Probes</div>
    </div>
  `;

  // RT Chart (only for specific device)
  const rtCanvas = document.getElementById('analyticsRtChart');
  if (rtChart) rtChart.destroy();
  if (ts.length > 0) {
    const labels = ts.map(p => new Date(p.checked_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}));
    const values = ts.map(p => p.is_reachable ? p.response_time_ms : null);
    rtChart = new Chart(rtCanvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Response Time (ms)',
          data: values,
          borderColor: '#1a78c2',
          backgroundColor: 'rgba(26,120,194,0.08)',
          fill: true,
          spanGaps: true,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: { y: { beginAtZero: true }, x: { ticks: { maxTicksLimit: 8 } } },
        plugins: { legend: { display: false } },
      },
    });
  } else {
    const ctx = rtCanvas.getContext('2d');
    ctx.clearRect(0, 0, rtCanvas.width, rtCanvas.height);
    ctx.fillStyle = '#3b6189';
    ctx.font = '0.85rem Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Select a specific device to see response time series.', rtCanvas.width / 2, 100);
  }

  // Availability Trend Chart
  const tCanvas = document.getElementById('analyticsTrendChart');
  if (trendChart) trendChart.destroy();
  if (trend.length > 0) {
    trendChart = new Chart(tCanvas, {
      type: 'bar',
      data: {
        labels: trend.map(t => t.bucket),
        datasets: [{
          label: 'Availability %',
          data: trend.map(t => t.availability_pct),
          backgroundColor: trend.map(t =>
            t.availability_pct == null ? '#78909c'
            : t.availability_pct >= 99 ? 'rgba(29,185,84,0.7)'
            : t.availability_pct >= 90 ? 'rgba(245,158,11,0.7)'
            : 'rgba(229,57,53,0.7)'
          ),
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          y: { min: 0, max: 100, title: { display: true, text: 'Availability %' } },
          x: { ticks: { maxTicksLimit: 12 } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }
}

document.getElementById('analyticsDevice')?.addEventListener('change', loadAnalytics);
document.getElementById('analyticsRange')?.addEventListener('change', loadAnalytics);

window.triggerRefresh = loadAnalytics;

initDeviceSelector().then(loadAnalytics);
