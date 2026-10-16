/**
 * NetWatch — Topology Visualization
 * Renders a logical star topology using SVG lines + positioned HTML nodes.
 */

const STATUS_COLORS = { online: '#1db954', offline: '#e53935', unknown: '#78909c' };
const TYPE_ICONS    = {
  Router: '📡', Server: '🖥️', Computer: '💻', Switch: '🔀', Printer: '🖨️', Other: '📟',
};

let _devices = [];

async function loadTopology() {
  const r = await apiGet('/api/devices');
  if (!r.ok) { showToast('Error', 'Failed to load topology', 'error'); return; }
  _devices = r.data.data || [];

  const emptyEl = document.getElementById('topologyEmpty');
  if (!_devices.length) {
    emptyEl.style.display = 'flex';
    return;
  }
  emptyEl.style.display = 'none';
  renderTopology(_devices);
}

function renderTopology(devices) {
  const container = document.getElementById('topologyNodes');
  const svg       = document.getElementById('topologySvg');
  container.innerHTML = '';
  svg.innerHTML      = '';

  const W = container.offsetWidth  || 800;
  const H = container.offsetHeight || 540;
  const cx = W / 2;
  const cy = H / 2;

  // Central hub
  const hub = createNode({
    label: 'Network Hub',
    icon: '🌐',
    color: '#1a78c2',
    x: cx - 40,
    y: cy - 40,
    isHub: true,
    id: null,
  });
  container.appendChild(hub);

  // Spread devices in a circle
  const n     = devices.length;
  const radii = Math.min(W, H) * 0.36;
  const angle_step = (2 * Math.PI) / n;

  devices.forEach((d, i) => {
    const angle = -Math.PI / 2 + i * angle_step;
    const nx = cx + radii * Math.cos(angle);
    const ny = cy + radii * Math.sin(angle);

    // SVG line from hub to node
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', cx);
    line.setAttribute('y1', cy);
    line.setAttribute('x2', nx);
    line.setAttribute('y2', ny);
    line.setAttribute('stroke', STATUS_COLORS[d.current_status] || '#78909c');
    line.setAttribute('stroke-width', '2');
    line.setAttribute('stroke-dasharray', d.current_status === 'online' ? 'none' : '6,4');
    line.setAttribute('opacity', '0.6');
    svg.appendChild(line);

    // Node element
    const node = createNode({
      label: d.name,
      icon: TYPE_ICONS[d.device_type] || TYPE_ICONS.Other,
      color: STATUS_COLORS[d.current_status],
      x: nx - 36,
      y: ny - 36,
      device: d,
    });
    container.appendChild(node);
  });
}

function createNode({ label, icon, color, x, y, isHub = false, device = null }) {
  const el = document.createElement('div');
  el.style.cssText = `
    position:absolute;
    left:${x}px; top:${y}px;
    width:72px;
    display:flex; flex-direction:column; align-items:center; gap:4px;
    cursor:${device ? 'pointer' : 'default'};
    transition:transform 0.18s ease;
    z-index:10;
  `;
  el.innerHTML = `
    <div style="
      width:52px;height:52px;
      border-radius:50%;
      background:${isHub ? 'linear-gradient(135deg,#1a78c2,#00bcd4)' : 'rgba(255,255,255,0.92)'};
      border:3px solid ${color};
      display:flex;align-items:center;justify-content:center;
      font-size:${isHub ? '1.3rem' : '1.1rem'};
      box-shadow:0 4px 14px rgba(0,0,0,0.12);
      transition:box-shadow 0.18s;
    ">${icon}</div>
    <span style="font-size:0.7rem;font-weight:600;color:var(--color-navy);text-align:center;
      max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
      background:rgba(255,255,255,0.85);padding:1px 5px;border-radius:5px;border:1px solid rgba(75,160,210,0.2);">
      ${escHtml(label)}
    </span>
  `;

  if (device) {
    el.addEventListener('mouseenter', (e) => showTooltip(e, device));
    el.addEventListener('mousemove',  (e) => moveTooltip(e));
    el.addEventListener('mouseleave', hideTooltip);
    el.addEventListener('click', () => window.location = `/devices/${device.id}`);
    el.style.cursor = 'pointer';
    el.addEventListener('mouseenter', () => el.style.transform = 'scale(1.1)');
    el.addEventListener('mouseleave', () => el.style.transform = 'scale(1)');
  }

  return el;
}

function showTooltip(e, device) {
  const tip = document.getElementById('topoTooltip');
  const sc  = STATUS_COLORS[device.current_status];
  document.getElementById('topoTipContent').innerHTML = `
    <div style="font-weight:700;color:var(--color-navy);margin-bottom:8px;">${escHtml(device.name)}</div>
    <div style="font-size:0.8rem;color:var(--color-text-secondary);display:grid;grid-template-columns:auto 1fr;gap:4px 10px;">
      <span class="text-muted">Target:</span><span><code>${escHtml(device.target)}</code></span>
      <span class="text-muted">Type:</span><span>${escHtml(device.device_type)}</span>
      <span class="text-muted">Status:</span><span style="color:${sc};font-weight:600;">${device.current_status.toUpperCase()}</span>
      <span class="text-muted">Checked:</span><span>${formatTsRelative(device.last_checked_at)}</span>
      ${device.location ? `<span class="text-muted">Location:</span><span>${escHtml(device.location)}</span>` : ''}
    </div>
    <div style="margin-top:8px;font-size:0.75rem;color:var(--color-blue);">Click to open details →</div>
  `;
  tip.style.display = 'block';
  moveTooltip(e);
}

function moveTooltip(e) {
  const tip = document.getElementById('topoTooltip');
  const pad = 12;
  let left = e.clientX + pad;
  let top  = e.clientY + pad;
  if (left + 280 > window.innerWidth)  left = e.clientX - 280 - pad;
  if (top  + 200 > window.innerHeight) top  = e.clientY - 180 - pad;
  tip.style.left = left + 'px';
  tip.style.top  = top  + 'px';
}

function hideTooltip() {
  document.getElementById('topoTooltip').style.display = 'none';
}

window.triggerRefresh = loadTopology;
loadTopology();
setInterval(loadTopology, 15000);
