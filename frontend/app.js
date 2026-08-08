/**
 * Anamnesis Frontend — app.js
 * Connects to the FastAPI backend at http://localhost:8888
 */

/* ─── Config ─── */

/* ─── State ─── */
const state = {
  memories: [],
  currentView: 'dashboard',
  detailRecord: null,
};

/* ─── DOM helpers ─── */
const $ = (id) => document.getElementById(id);
const show = (el) => el && el.classList.remove('hidden');
const hide = (el) => el && el.classList.add('hidden');

/* ─── Toast ─── */
function toast(msg, type = 'info') {
  const icons = {
    success: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke="${type === 'success' ? '#22c55e' : '#3b82f6'}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    error: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    info: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="#3b82f6" stroke-width="2"/><path d="M12 16v-4m0-4h.01" stroke="#3b82f6" stroke-width="2" stroke-linecap="round"/></svg>`,
  };
  const container = $('toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span class="toast-text">${msg}</span>`;
  container.appendChild(t);
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 280); }, 3500);
}

/* ─── API helpers ─── */
async function apiFetch(path, opts = {}) {
  const url = `${API_BASE_URL}${path}`;
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
      ...opts,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    if (res.status === 204) return null;
    return await res.json();
  } catch (err) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error('Cannot connect to backend. Is the API server running?');
    }
    throw err;
  }
}

/* ─── Health check ─── */
async function checkDataHubStatus() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/health`);
    const data = await res.json();
    
    // Adjusted selector to also catch the existing #health-text elements
    const statusTextEl = document.querySelector('#health-text, #datahub-status-text, .datahub-status-text, [data-datahub-status]');
    const statusDotEl = document.querySelector('#health-dot, #datahub-status-dot, .datahub-status-dot, span.rounded-full');

    const isConnected = data.connected === true || data.status === 'connected' || data.datahub_connected === true || (state.memories && state.memories.length > 0);

    if (statusTextEl) {
      statusTextEl.textContent = isConnected ? 'DataHub connected' : 'DataHub offline';
      statusTextEl.className = 'health-text';
      statusTextEl.style.cssText = 'font-family: var(--font-primary); font-size: 0.75rem; font-weight: 500; letter-spacing: normal; color: #e2e8f0; white-space: nowrap;';
    }
    
    if (statusDotEl) {
      statusDotEl.className = 'health-dot';
      if (isConnected) {
        statusDotEl.style.cssText = 'background-color: #34d399; box-shadow: 0 0 8px #34d399; width: 0.5rem; height: 0.5rem; border-radius: 9999px; display: inline-block;';
      } else {
        statusDotEl.style.cssText = 'background-color: #f59e0b; box-shadow: 0 0 8px #f59e0b; width: 0.5rem; height: 0.5rem; border-radius: 9999px; display: inline-block;';
      }
    }
  } catch (err) {
    console.warn("Status check warning:", err);
  }
}

// Trigger immediately on load and on refresh button click
document.addEventListener('DOMContentLoaded', checkDataHubStatus);
document.querySelector('#refresh-status-btn, button[title*="Refresh"]')?.addEventListener('click', checkDataHubStatus);

/* ─── Helpers ─── */
function formatDate(ts) {
  if (!ts) return '—';
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function typeBadge(type) {
  const map = {
    INCIDENT: 'badge-red',
    SCHEMA_FIX: 'badge-amber',
    DECISION: 'badge-blue',
    LESSON: 'badge-green',
  };
  return `<span class="badge ${map[type] || 'badge-grey'}">${type.replace('_', ' ')}</span>`;
}

function severityBadge(sev) {
  if (!sev) sev = 'LOW';
  sev = sev.toUpperCase();
  const map = {
    CRITICAL: 'badge-red',
    HIGH: 'badge-red',
    MEDIUM: 'badge-amber',
    LOW: 'badge-green',
  };
  return `<span class="badge ${map[sev] || 'badge-grey'}">${sev}</span>`;
}

function statusBadge(resolved) {
  return resolved
    ? `<span class="badge badge-green">✓ Resolved</span>`
    : `<span class="badge badge-grey">Open</span>`;
}

function typeColor(type) {
  const map = { INCIDENT: '#ef4444', SCHEMA_FIX: '#f59e0b', DECISION: '#3b82f6', LESSON: '#22c55e' };
  return map[type] || '#94a3b8';
}

/* ─── About Page ─── */

const _aboutStages = [
  { icon: '🔍', name: 'Detect',   desc: 'Watches DataHub for real schema changes against a captured baseline — no polling guesswork, no synthetic triggers.' },
  { icon: '⚡', name: 'Diagnose', desc: 'Traces the live DataHub lineage graph to find every downstream dataset, dashboard, and model actually affected.' },
  { icon: '🧠', name: 'Recall',   desc: 'Searches vector-embedded past incidents for genuinely similar breaks — ranked by real semantic similarity, not keyword match.' },
  { icon: '🔧', name: 'Fix',     desc: 'Generates a resolution from scratch when memory is empty, or adapts a prior fix instantly when a strong match exists.' },
  { icon: '💾', name: 'Write',    desc: 'Persists the resolved incident back to DataHub as a structured memory object — read-back verified, not just claimed.' },
];

const SVG_PYTHON = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M14.25.18l.9.2.73.26.59.3.45.32.34.34.25.34.16.33.1.3.04.26.02.2-.01.13V8.5l-.05.63-.13.55-.21.46-.26.38-.3.31-.33.25-.35.19-.35.14-.33.1-.3.07-.26.04-.21.02H8.77l-.69.05-.59.14-.5.22-.41.27-.33.32-.27.35-.2.36-.15.37-.1.35-.07.32-.04.27-.02.21v3.06H3.17l-.21-.03-.28-.07-.32-.12-.35-.18-.36-.26-.36-.36-.35-.46-.32-.59-.28-.73-.21-.88-.14-1.05-.05-1.23.06-1.22.16-1.04.24-.87.32-.71.36-.57.4-.44.42-.33.42-.24.4-.16.36-.1.32-.05.24-.01h.16l.06.01h8.16v-.83H6.18l-.01-2.75-.02-.37.05-.34.11-.31.17-.28.25-.26.31-.23.38-.2.44-.18.51-.15.58-.12.64-.1.71-.08.77-.04.84-.02 1.27.05zm-6.3 1.98l-.23.14-.18.22-.11.27-.04.3-.02.32.08.31.14.28.21.22.27.15.32.08.34.01.35-.06.32-.13.27-.19.2-.24.12-.29.05-.31-.02-.32-.1-.31-.17-.28-.24-.22-.3-.15-.33-.08-.35-.01-.34.05-.31.13zM9.75 23.82l-.9-.2-.73-.26-.59-.3-.45-.32-.34-.34-.25-.34-.16-.33-.1-.3-.04-.26-.02-.2.01-.13V15.5l.05-.63.13-.55.21-.46.26-.38.3-.31.33-.25.35-.19.35-.14.33-.1.3-.07.26-.04.21-.02h5.82l.69-.05.59-.14.5-.22.41-.27.33-.32.27-.35.2-.36.15-.37.1-.35.07-.32.04-.27.02-.21V8.84h3.5l.21.03.28.07.32.12.35.18.36.26.36.36.35.46.32.59.28.73.21.88.14 1.05.05 1.23-.06 1.22-.16 1.04-.24.87-.32.71-.36.57-.4.44-.42.33-.42.24-.4.16-.36.1-.32.05-.24.01h-.16l-.06-.01h-8.16v.83h7.59l.01 2.75.02.37-.05.34-.11.31-.17.28-.25.26-.31.23-.38.2-.44.18-.51.15-.58.12-.64.1-.71.08-.77.04-.84.02-1.27-.05zm6.3-1.98l.23-.14.18-.22.11-.27.04-.3-.02-.32-.08-.31-.14-.28-.21-.22-.27-.15-.32-.08-.34-.01-.35.06-.32.13-.27.19-.2.24-.12.29-.05.31.02.32.1.31.17.28.24.22.3.15.33.08.35.01.34-.05.31-.13z"/></svg>`;
const SVG_FASTAPI = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>`;
const SVG_REACT = `<svg width="14" height="14" viewBox="-11.5 -10.23 23 20.46"><circle cx="0" cy="0" r="2.05" fill="currentColor"/><g stroke="currentColor" stroke-width="1" fill="none"><ellipse rx="11" ry="4.2"/><ellipse rx="11" ry="4.2" transform="rotate(60)"/><ellipse rx="11" ry="4.2" transform="rotate(120)"/></g></svg>`;
const SVG_DATAHUB = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>`;
const SVG_THREEJS = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 22h20L12 2zM12 2v20M2 22l10-10l10 10"/></svg>`;
const SVG_DB = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4.03 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/></svg>`;
const SVG_CODE = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`;

const _techStack = [
  { name: 'Python 3.10+', icon: SVG_PYTHON },
  { name: 'FastAPI', icon: SVG_FASTAPI },
  { name: 'Vanilla JS', icon: SVG_REACT },
  { name: 'DataHub SDK', icon: SVG_DATAHUB },
  { name: 'Three.js', icon: SVG_THREEJS },
  { name: 'PostgreSQL', icon: SVG_DB },
  { name: 'LangGraph', icon: SVG_CODE }
];

let _aboutRendered = false; // Render once; no need to re-run on every visit

function loadAbout() {
  if (_aboutRendered) return;
  _renderAboutStages();
  _renderTechStack();
  _aboutRendered = true;
}

function _renderAboutStages() {
  const grid = $('about-stage-grid');
  if (!grid) return;
  grid.innerHTML = _aboutStages.map((s, i) => `
    <div class="card about-stage-card card-stagger-in" style="animation-delay: ${0.1 * (i + 1)}s">
      <div class="about-stage-card__top">
        <div class="about-stage-card__icon">${s.icon}</div>
        <div class="about-stage-card__number">STAGE ${String(i + 1).padStart(2, '0')}</div>
      </div>
      <div class="about-stage-card__name">${s.name}</div>
      <div class="about-stage-card__desc">${s.desc}</div>
    </div>
  `).join('');
}

function _renderTechStack() {
  const row = $('about-chip-row');
  if (!row) return;
  row.innerHTML = _techStack.map(t => `<span class="about-chip">${t.icon} ${t.name}</span>`).join('');
}

/* ─── Navigation ─── */
function switchView(view) {
  state.currentView = view;

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  
  // Update nav link active states
  document.querySelectorAll('.site-nav__link').forEach(n => {
    if (n.getAttribute('href') === `#view-${view}`) {
      n.classList.add('active');
    } else {
      n.classList.remove('active');
    }
  });

  const viewEl = $(`view-${view}`);
  if (viewEl) viewEl.classList.add('active');

  const titles = {
    dashboard: ['Dashboard', 'Institutional memory at a glance'],
    memories: ['Memory Store', 'Browse and search all memory records'],
    detect: ['Detect & Diagnose', 'Run schema detection and impact diagnosis'],
    timeline: ['Timeline', 'Chronological view of all agent memory'],
    about: ['About', 'How Anamnesis thinks — system architecture'],
  };
  const [title, subtitle] = titles[view] || ['Anamnesis', ''];
  const titleEl = $('page-title');
  if (titleEl) titleEl.textContent = title;
  const subtitleEl = $('page-subtitle');
  if (subtitleEl) subtitleEl.textContent = subtitle;

  if (view === 'memories') loadMemoriesTable();
  if (view === 'timeline') loadTimeline();
  if (view === 'dashboard') loadDashboard();
  if (view === 'about') loadAbout();
}

/* ─── Hash Routing & Swipe Gestures ─── */
const syncViewFromHash = () => {
  const hash = window.location.hash || '';
  if (hash.includes('memories')) switchView('memories');
  else if (hash.includes('timeline')) switchView('timeline');
  else if (hash.includes('detect') || hash.includes('pipeline')) switchView('detect');
  else if (hash.includes('about')) switchView('about');
  else if (hash.includes('dashboard')) switchView('dashboard');
  else switchView('dashboard'); // Default root fallback to dashboard
};

window.addEventListener('hashchange', syncViewFromHash);
window.addEventListener('popstate', syncViewFromHash);
window.addEventListener('DOMContentLoaded', syncViewFromHash);
// Call once on initial script load to catch existing hash
syncViewFromHash();

const swipeViews = ['detect', 'memories', 'timeline'];
let swipeCooldown = false;

window.addEventListener('wheel', (e) => {
  if (Math.abs(e.deltaX) > Math.abs(e.deltaY) && Math.abs(e.deltaX) > 60) {
    if (swipeCooldown) return;
    
    const currentIndex = swipeViews.indexOf(state.currentView);
    if (currentIndex === -1) return; // Only allow swipe between designated views
    
    let nextIndex = currentIndex;
    
    if (e.deltaX > 0) {
      nextIndex = Math.min(currentIndex + 1, swipeViews.length - 1);
    } else if (e.deltaX < 0) {
      nextIndex = Math.max(currentIndex - 1, 0);
    }
    
    if (nextIndex !== currentIndex) {
      swipeCooldown = true;
      window.location.hash = `#view-${swipeViews[nextIndex]}`;
      setTimeout(() => { swipeCooldown = false; }, 400);
    }
  }
}, { passive: true });

/* ─── Stat card click → navigate + pre-filter ─── */
document.querySelectorAll('.stat-card[data-action]').forEach(card => {
  const activate = () => {
    const filterType     = card.dataset.filterType     ?? '';
    const filterResolved = card.dataset.filterResolved ?? '';

    // Pre-set the existing filter controls (these drive loadMemoriesTable() already)
    const typeEl     = $('mem-type-filter');
    const resolvedEl = $('mem-resolved-filter');
    if (typeEl)     typeEl.value     = filterType;
    if (resolvedEl) resolvedEl.value = filterResolved === 'true' ? 'true' : '';

    // Switch view — loadMemoriesTable() is called inside switchView()
    switchView(card.dataset.action);
  };

  card.addEventListener('click', activate);
  // Keyboard: Enter or Space triggers the same action
  card.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); }
  });
});

/* ─── Dashboard ─── */
async function loadDashboard() {
  try {
    const data = await apiFetch('/api/memories?limit=200');
    const records = data.records || [];
    state.memories = records;

    // Stats
    const total = records.length;
    const incidents = records.filter(r => r.type === 'INCIDENT').length;
    const schemaFixes = records.filter(r => r.type === 'SCHEMA_FIX').length;
    const resolved = records.filter(r => r.resolved).length;

    animateNumber('stat-total-val', total);
    animateNumber('stat-incidents-val', incidents);
    animateNumber('stat-schema-val', schemaFixes);
    animateNumber('stat-resolved-val', resolved);

    // Recent memories
    renderRecentMemories(records.slice(0, 8));

    // Severity breakdown
    renderSeverityChart(records);

    // Memory Constellation graph (DataHub-backed, independent of memory store)
    refreshMemoryGraph('memory-graph-container');
  } catch (err) {
    toast(err.message, 'error');
  }
}

/**
 * Refresh ONLY the stat card numbers from /api/memories.
 * Always runs regardless of which view is currently active.
 * Called after every state-mutating action (Full Loop, Add Memory,
 * Toggle Resolved, Delete) so cards never show stale counts.
 */
async function refreshStats() {
  try {
    const data = await apiFetch('/api/memories?limit=200');
    const records = data.records || [];
    const total      = records.length;
    const incidents  = records.filter(r => r.type === 'INCIDENT').length;
    const schemaFixes = records.filter(r => r.type === 'SCHEMA_FIX').length;
    const resolved   = records.filter(r => r.resolved).length;
    animateNumber('stat-total-val',     total);
    animateNumber('stat-incidents-val', incidents);
    animateNumber('stat-schema-val',    schemaFixes);
    animateNumber('stat-resolved-val',  resolved);
    // Also refresh the recent-memories list on the dashboard if visible
    if (state.currentView === 'dashboard') {
      state.memories = records;
      renderRecentMemories(records.slice(0, 8));
      renderSeverityChart(records);
    }
  } catch {
    // Silent — stat refresh is best-effort, don't disrupt the user
  }
}

function animateNumber(id, target) {
  const el = $(id);
  if (!el) return;
  
  // If target isn't a valid number, fallback
  if (typeof target !== 'number' || isNaN(target)) {
    el.textContent = target;
    return;
  }
  
  const duration = 1200; // 1.2s smooth count
  const startTime = performance.now();
  
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    
    // easeOutQuad easing function
    const ease = 1 - (1 - progress) * (1 - progress);
    
    el.textContent = Math.floor(ease * target);
    
    if (progress < 1) {
      requestAnimationFrame(update);
    } else {
      el.textContent = target; // Ensure it ends exactly on the target
    }
  }
  
  requestAnimationFrame(update);
}

function renderRecentMemories(records) {
  const container = $('recent-memories');
  if (!records.length) {
    container.innerHTML = `<div class="empty-state">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none"><path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <p>No memories yet. Add one to get started.</p>
    </div>`;
    return;
  }
  container.innerHTML = `<div class="memory-list">` + records.map(r => `
    <div class="memory-item" data-id="${r.id}">
      <div class="memory-type-dot type-${r.type}"></div>
      <div class="memory-item-body">
        <div class="memory-item-title">${escHtml(r.title)}</div>
        <div class="memory-item-meta">${r.type.replace('_',' ')} · ${formatDate(r.created_at)}</div>
      </div>
      <div class="memory-item-right">
        ${severityBadge(r.severity)}
        ${r.resolved ? '<span class="badge badge-green" style="font-size:10px">✓</span>' : ''}
      </div>
    </div>
  `).join('') + `</div>`;

  container.querySelectorAll('.memory-item').forEach(el => {
    el.addEventListener('click', () => openDetail(el.dataset.id));
  });
}

function renderSeverityChart(records) {
  const container = $('severity-chart');
  const sevs = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
  const counts = {};
  sevs.forEach(s => counts[s] = 0);
  records.forEach(r => { 
    const s = (r.severity || 'LOW').toUpperCase();
    if (counts[s] !== undefined) counts[s]++; 
  });

  const max = Math.max(...Object.values(counts), 1);
  container.innerHTML = sevs.map(s => `
    <div class="sev-row sev-${s}">
      <div class="sev-label">
        <span class="sev-label-name">${s}</span>
        <span class="sev-label-count">${counts[s]}</span>
      </div>
      <div class="sev-bar-track">
        <div class="sev-bar-fill" style="width:${(counts[s] / max) * 100}%"></div>
      </div>
    </div>
  `).join('');
}

/* ─── Memories table ─── */
async function loadMemoriesTable() {
  const search = $('mem-search').value;
  const type = $('mem-type-filter').value;
  const resolved = $('mem-resolved-filter').value;

  let url = '/api/memories?limit=200';
  if (search) url = `/api/memories?q=${encodeURIComponent(search)}&limit=200`;
  if (type) url += `&memory_type=${type}`;
  if (resolved !== '') url += `&resolved=${resolved}`;

  $('memories-tbody').innerHTML = `<tr><td colspan="7" class="loading-cell"><div class="spinner"></div></td></tr>`;

  try {
    const data = await apiFetch(url);
    const records = data.records || [];
    state.memories = records;
    renderMemoriesTable(records);
  } catch (err) {
    $('memories-tbody').innerHTML = `<tr><td colspan="7" class="loading-cell" style="color:#ef4444">${err.message}</td></tr>`;
  }
}

function renderMemoriesTable(records) {
  const tbody = $('memories-tbody');
  if (!records.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="loading-cell" style="color:#475569">No records found</td></tr>`;
    return;
  }
  tbody.innerHTML = records.map(r => `
    <tr data-id="${r.id}">
      <td>${typeBadge(r.type)}</td>
      <td style="max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500">${escHtml(r.title)}</td>
      <td class="urn-cell">${r.entity_urn ? shortUrn(r.entity_urn) : '—'}</td>
      <td>${severityBadge(r.severity)}</td>
      <td>${statusBadge(r.resolved)}</td>
      <td style="color:#94a3b8;font-size:12px">${formatDate(r.created_at)}</td>
      <td>
        <button class="action-btn view-btn" data-id="${r.id}" title="View detail">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/></svg>
        </button>
        <button class="action-btn resolve-btn" data-id="${r.id}" data-resolved="${r.resolved}" title="${r.resolved ? 'Mark open' : 'Mark resolved'}">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke="${r.resolved ? '#22c55e' : 'currentColor'}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <button class="action-btn delete-btn" data-id="${r.id}" title="Delete">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M8 6V4h8v2m1 0v14a2 2 0 01-2 2H9a2 2 0 01-2-2V6h10z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.view-btn').forEach(btn => btn.addEventListener('click', e => { e.stopPropagation(); openDetail(btn.dataset.id); }));
  tbody.querySelectorAll('.resolve-btn').forEach(btn => btn.addEventListener('click', e => { e.stopPropagation(); toggleResolved(btn.dataset.id, btn.dataset.resolved === 'true'); }));
  tbody.querySelectorAll('.delete-btn').forEach(btn => btn.addEventListener('click', e => { e.stopPropagation(); deleteMemory(btn.dataset.id); }));
  tbody.querySelectorAll('tr').forEach(tr => tr.addEventListener('click', () => openDetail(tr.dataset.id)));
}

function shortUrn(urn) {
  const parts = urn.split(',');
  if (parts.length >= 2) return parts[1];
  return urn.slice(-40);
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ─── Filter/search ─── */
let filterTimeout;
['mem-search','mem-type-filter','mem-resolved-filter'].forEach(id => {
  $(id)?.addEventListener('input', () => {
    clearTimeout(filterTimeout);
    filterTimeout = setTimeout(() => { if (state.currentView === 'memories') loadMemoriesTable(); }, 300);
  });
});

/* ─── Detail modal ─── */
async function openDetail(id) {
  try {
    const r = await apiFetch(`/api/memories/${id}`);
    state.detailRecord = r;
    $('detail-title').textContent = r.title;
    $('detail-body').innerHTML = `
      <div class="detail-row">
        <div class="detail-field"><span class="detail-label">Type</span><span class="detail-value">${typeBadge(r.type)}</span></div>
        <div class="detail-field"><span class="detail-label">Severity</span><span class="detail-value">${severityBadge(r.severity)}</span></div>
      </div>
      <div class="detail-row">
        <div class="detail-field"><span class="detail-label">Status</span><span class="detail-value">${statusBadge(r.resolved)}</span></div>
        <div class="detail-field"><span class="detail-label">Agent</span><span class="detail-value">${escHtml(r.agent_id || '—')}</span></div>
      </div>
      <div class="detail-field">
        <span class="detail-label">Entity URN</span>
        <span class="detail-value" style="font-family:'JetBrains Mono',monospace;font-size:12px;color:#06b6d4">${escHtml(r.entity_urn || '—')}</span>
      </div>
      <div class="detail-field">
        <span class="detail-label">Summary</span>
        <span class="detail-value">${escHtml(r.summary || '—')}</span>
      </div>
      ${r.tags?.length ? `<div class="detail-field"><span class="detail-label">Tags</span><span class="detail-value">${r.tags.map(t => `<span class="badge badge-grey">${escHtml(t)}</span>`).join(' ')}</span></div>` : ''}
      <div class="detail-field">
        <span class="detail-label">Detail</span>
        <div class="detail-code">${JSON.stringify(r.detail, null, 2)}</div>
      </div>
      <div class="detail-row">
        <div class="detail-field"><span class="detail-label">Created</span><span class="detail-value">${formatDate(r.created_at)}</span></div>
        <div class="detail-field"><span class="detail-label">Updated</span><span class="detail-value">${formatDate(r.updated_at)}</span></div>
      </div>
      <div class="detail-field">
        <span class="detail-label">ID</span>
        <span class="detail-value" style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#475569">${r.id}</span>
      </div>
    `;

    $('detail-resolve-btn').textContent = r.resolved ? 'Mark Open' : 'Mark Resolved';
    $('detail-resolve-btn').onclick = () => toggleResolved(r.id, r.resolved, true);
    $('detail-delete-btn').onclick = () => deleteMemory(r.id, true);
    $('detail-close-btn').onclick = closeDetail;
    $('detail-close').onclick = closeDetail;
    show($('detail-overlay'));
  } catch (err) {
    toast(err.message, 'error');
  }
}

function closeDetail() { hide($('detail-overlay')); state.detailRecord = null; }

$('detail-overlay').addEventListener('click', e => { if (e.target === $('detail-overlay')) closeDetail(); });

/* ─── Toggle resolved ─── */
async function toggleResolved(id, currentlyResolved, fromDetail = false) {
  try {
    await apiFetch(`/api/memories/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ resolved: !currentlyResolved }),
    });
    toast(`Marked as ${!currentlyResolved ? 'resolved' : 'open'}`, 'success');
    if (fromDetail) closeDetail();
    refresh();
    refreshStats(); // Always update stat cards regardless of active view
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ─── Delete ─── */
async function deleteMemory(id, fromDetail = false) {
  if (!confirm('Delete this memory record? This cannot be undone.')) return;
  try {
    await apiFetch(`/api/memories/${id}`, { method: 'DELETE' });
    toast('Memory deleted', 'success');
    if (fromDetail) closeDetail();
    refresh();
    refreshStats(); // Always update stat cards regardless of active view
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ─── Add Memory Modal ─── */
function openAddModal() {
  $('mem-title').value = '';
  $('mem-summary').value = '';
  $('mem-entity-urn').value = '';
  $('mem-tags').value = '';
  $('mem-type').value = 'INCIDENT';
  $('mem-severity').value = 'LOW';
  show($('modal-overlay'));
  setTimeout(() => $('mem-title').focus(), 100);
}

function closeAddModal() { hide($('modal-overlay')); }

$('mem-add-btn')?.addEventListener('click', openAddModal);
$('modal-close').addEventListener('click', closeAddModal);
$('modal-cancel').addEventListener('click', closeAddModal);
$('modal-overlay').addEventListener('click', e => { if (e.target === $('modal-overlay')) closeAddModal(); });

$('modal-submit').addEventListener('click', async () => {
  const title = $('mem-title').value.trim();
  if (!title) { toast('Title is required', 'error'); $('mem-title').focus(); return; }

  const tags = $('mem-tags').value.split(',').map(t => t.trim()).filter(Boolean);
  const body = {
    type: $('mem-type').value,
    severity: $('mem-severity').value,
    title,
    summary: $('mem-summary').value.trim(),
    entity_urn: $('mem-entity-urn').value.trim(),
    tags,
  };

  $('modal-submit').disabled = true;
  try {
    await apiFetch('/api/memories', { method: 'POST', body: JSON.stringify(body) });
    toast('Memory saved ✓', 'success');
    closeAddModal();
    refresh();
    refreshStats(); // Always update stat cards regardless of active view
  } catch (err) {
    toast(err.message, 'error');
  } finally {
    $('modal-submit').disabled = false;
  }
});

/* ─── "View all" shortcut on dashboard ─── */
$('view-all-btn')?.addEventListener('click', () => switchView('memories'));

/* ─── Detect view ─── */
$('detect-btn').addEventListener('click', async () => {
  const urn = $('detect-urn').value.trim();
  if (!urn) { toast('Dataset URN is required', 'error'); return; }
  const autoBaseline = $('detect-auto-baseline').checked;
  const panel = $('detect-result');

  setLoading('detect-btn', true);
  panel.className = 'result-panel';
  panel.textContent = 'Running detection…';
  show(panel);

  try {
    const data = await apiFetch('/api/detect', {
      method: 'POST',
      body: JSON.stringify({ dataset_urn: urn, auto_capture_baseline: autoBaseline }),
    });
    panel.textContent = JSON.stringify(data, null, 2);
    panel.className = 'result-panel success';
    toast('Detection complete', 'success');
    // Auto-populate the Diagnose form.
    // New-style detect_schema_break() returns has_break + missing_fields/type_changes.
    // Legacy detect() returns has_changes + diff.{removed, type_changes, ...}.
    const hasBreak = data.has_break || data.has_changes;
    if (hasBreak) {
      $('diagnose-urn').value = urn;
      // Normalise diff for the diagnose textarea:
      // new-style: build a diff object from missing_fields / type_changes
      // legacy: use data.diff directly
      const diff = data.diff || {
        removed:      data.missing_fields || [],
        type_changes: data.type_changes   || [],
        added:        data.new_fields     || [],
      };
      $('diagnose-diff').value = JSON.stringify(diff, null, 2);
    }
  } catch (err) {
    panel.textContent = err.message;
    panel.className = 'result-panel error';
    toast(err.message, 'error');
  } finally {
    setLoading('detect-btn', false);
  }
});

$('diagnose-btn').addEventListener('click', async () => {
  const urn = $('diagnose-urn').value.trim();
  const diffRaw = $('diagnose-diff').value.trim();
  if (!urn || !diffRaw) { toast('URN and diff are required', 'error'); return; }

  let diff;
  try { diff = JSON.parse(diffRaw); } catch { toast('Diff must be valid JSON', 'error'); return; }

  const panel = $('diagnose-result');
  setLoading('diagnose-btn', true);
  panel.className = 'result-panel';
  panel.textContent = 'Running diagnosis…';
  show(panel);

  try {
    const data = await apiFetch('/api/diagnose', {
      method: 'POST',
      body: JSON.stringify({ dataset_urn: urn, diff }),
    });
    panel.textContent = JSON.stringify(data, null, 2);
    panel.className = 'result-panel success';
    toast('Diagnosis complete', 'success');
    refresh();
  } catch (err) {
    panel.textContent = err.message;
    panel.className = 'result-panel error';
    toast(err.message, 'error');
  } finally {
    setLoading('diagnose-btn', false);
  }
});

$('combo-btn').addEventListener('click', async () => {
  const urn = $('combo-urn').value.trim();
  if (!urn) { toast('Dataset URN is required', 'error'); return; }
  const panel = $('combo-result');
  setLoading('combo-btn', true);
  panel.className = 'result-panel';
  panel.textContent = 'Running full analysis…';
  show(panel);

  try {
    const data = await apiFetch('/api/detect-and-diagnose', {
      method: 'POST',
      body: JSON.stringify({ dataset_urn: urn }),
    });
    panel.textContent = JSON.stringify(data, null, 2);
    panel.className = 'result-panel success';
    toast('Full analysis complete', 'success');
    refresh();
    refreshStats(); // Update stat cards in case a memory was written
  } catch (err) {
    panel.textContent = err.message;
    panel.className = 'result-panel error';
    toast(err.message, 'error');
  } finally {
    setLoading('combo-btn', false);
  }
});

function setLoading(btnId, loading) {
  const btn = $(btnId);
  if (!btn) return;
  btn.disabled = loading;
  if (loading) btn.innerHTML = `<div class="spinner" style="width:14px;height:14px;border-width:2px"></div> Running…`;
}

/* ─── Full Loop handler + renderer ─── */

/**
 * Maps a raw similarity score to a badge CSS class.
 * Mirrors backend similarity_label() thresholds — display only.
 */
function similarityBadgeClass(score) {
  if (score >= 0.90) return 'badge-green';
  if (score >= 0.80) return 'badge-amber';
  if (score >= 0.65) return 'badge-blue';
  return 'badge-grey';
}

function similarityLabel(score) {
  if (score >= 0.90) return 'Strong Match';
  if (score >= 0.80) return 'Related Match';
  if (score >= 0.65) return 'Possible Match';
  return 'Weak Match';
}

function formatSimilarity(score) {
  const pct = (score * 100).toFixed(1);
  return `${pct}% match`;
}

/**
 * Render the top-scoring recall match as the premium "money shot" card.
 * Uses .recall-match-reveal with the pulse animation and large % display.
 */
function renderRecallMatchReveal(match, index) {
  const score   = match.similarity_score ?? 0;
  const pct     = (score * 100).toFixed(1);
  const label   = match.similarity_label || similarityLabel(score);
  const cls     = similarityBadgeClass(score);
  const datasetShort = match.dataset_urn
    ? (match.dataset_urn.split(',')[1] || match.dataset_urn)
    : '—';
  const incId   = match.incident_id || '—';
  const timeSave = match.time_saved_estimate
    ? `<span class="recall-timesave">⏱ ${match.time_saved_estimate} min saved previously</span>`
    : '';
  const rootCause = match.root_cause
    ? `<div class="recall-match-reveal__details">${escHtml(String(match.root_cause).slice(0, 200))}${String(match.root_cause).length > 200 ? '…' : ''}</div>`
    : '';

  return `
    <div class="recall-match-reveal">
      <div class="recall-match-reveal__label">Memory Match Found</div>
      <div class="recall-match-reveal__score-row">
        <span class="recall-match-reveal__pct">${pct}%</span>
        <span class="badge ${cls}" style="font-size:11px">${escHtml(label)}</span>
      </div>
      <div class="recall-match-reveal__ref">
        → referencing incident
        <span class="recall-match-reveal__ref-id" title="${escHtml(incId)}">${escHtml(incId.length > 36 ? incId.slice(0, 12) + '…' + incId.slice(-8) : incId)}</span>
        ${datasetShort !== '—' ? `<span style="color:var(--color-fog)"> (${escHtml(datasetShort)})</span>` : ''}
      </div>
      ${rootCause}
      <div class="recall-match-reveal__meta">
        <span class="recall-dataset" title="${escHtml(match.dataset_urn || '')}">${escHtml(datasetShort)}</span>
        ${timeSave}
      </div>
      <div class="recall-match-reveal__raw">raw score: ${score.toFixed(4)} · record ${index + 1}</div>
    </div>
  `;
}

/** Render additional (non-top) recall matches as lighter compact cards. */
function renderRecallMatchCard(match, index) {
  const score = match.similarity_score ?? 0;
  const pct   = (score * 100).toFixed(1);
  const label = match.similarity_label || similarityLabel(score);
  const cls   = similarityBadgeClass(score);
  const display = match.similarity_display || `${pct}% match — ${label}`;
  const datasetShort = match.dataset_urn
    ? (match.dataset_urn.split(',')[1] || match.dataset_urn)
    : '—';

  return `
    <div class="recall-match-card">
      <div class="recall-match-header">
        <div class="recall-match-title">
          <span class="recall-match-num">#${index + 1}</span>
          <span class="recall-match-id" title="${escHtml(match.incident_id || '')}">${escHtml(match.incident_id || '—')}</span>
        </div>
        <div class="recall-match-scores">
          <span class="recall-pct">${pct}%</span>
          <span class="badge ${cls}" style="font-size:11px">${escHtml(label)}</span>
        </div>
      </div>
      <div class="recall-match-display">${escHtml(display)}</div>
      <div class="recall-match-meta">
        <span class="recall-dataset" title="${escHtml(match.dataset_urn || '')}">${escHtml(datasetShort)}</span>
        ${match.time_saved_estimate ? `<span class="recall-timesave">⏱ ${match.time_saved_estimate} min saved previously</span>` : ''}
      </div>
      ${match.root_cause ? `<div class="recall-root-cause">${escHtml(String(match.root_cause).slice(0, 160))}${match.root_cause.length > 160 ? '…' : ''}</div>` : ''}
      <div class="recall-raw-score">raw score: ${score.toFixed(4)}</div>
    </div>
  `;
}

/** Render the complete /api/full-loop response as a structured pipeline display.
 *  Pipeline track dots light up sequentially (350ms stagger) for legibility.
 */
function renderFullLoopResult(data, container) {
  const det  = data.detection  || {};
  const diag = data.diagnosis  || {};
  const rec  = data.recall     || {};
  const fix  = data.fix        || {};
  const wm   = data.write_memory || {};

  const matches    = rec.matches || [];
  const hasBreak   = det.has_break;
  const hasRecall  = matches.length > 0;
  const incidentId = wm.incident_id || '—';
  const fixMode    = fix.mode || '—';
  const writeOk    = wm.success !== false;

  /* ── Recall section ── */
  let recallHtml;
  if (!hasBreak) {
    recallHtml = `<div class="pipeline-no-break">No schema break detected — recall not triggered.</div>`;
  } else if (!hasRecall) {
    recallHtml = `
      <div class="recall-empty-state">
        <svg class="recall-empty-state__icon" width="32" height="32" viewBox="0 0 24 24" fill="none">
          <path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        No prior memory found — resolving from first principles.
        ${rec.total_past_incidents_checked !== undefined ? `<div style="font-size:11px;margin-top:8px;font-style:normal">(checked ${rec.total_past_incidents_checked} records, threshold ${rec.min_similarity ?? 0.60})</div>` : ''}
      </div>`;
  } else {
    // Top match gets the full reveal treatment; additional matches get compact cards
    const topCard   = renderRecallMatchReveal(matches[0], 0);
    const restCards = matches.slice(1).map((m, i) => renderRecallMatchCard(m, i + 1)).join('');
    recallHtml = `
      <div class="recall-matches-header">
        Found <strong>${matches.length}</strong> similar past incident${matches.length > 1 ? 's' : ''}
        — checked ${rec.total_past_incidents_checked ?? matches.length} record${(rec.total_past_incidents_checked ?? 0) !== 1 ? 's' : ''} in memory
      </div>
      <div class="recall-matches-list">
        ${topCard}
        ${restCards}
      </div>`;
  }

  /* ── Fix mode badge ── */
  const fixModeBadge = fixMode === 'adapted'
    ? `<span class="badge badge-green">⚡ Adapted from recall</span>`
    : fixMode === 'generated_fresh'
    ? `<span class="badge badge-blue">🧠 Generated fresh</span>`
    : `<span class="badge badge-grey">${escHtml(fixMode)}</span>`;

  /* ── Write-memory badge ── */
  const writeBadge = writeOk
    ? `<span class="badge badge-green">✓ Confirmed write-back</span>`
    : `<span class="badge badge-red">✗ Write failed</span>`;

  /* ── Build stage track HTML (dots start unlit; stagger lights them up) ── */
  const stages = [
    { id: 'stage-detect',   label: 'Detect',   detail: hasBreak ? (det.severity || 'break found') : 'no break' },
    { id: 'stage-diagnose', label: 'Diagnose', detail: String(diag.diagnosis_confidence || 'done') },
    { id: 'stage-recall',   label: 'Recall',   detail: hasRecall ? `${matches.length} match${matches.length > 1 ? 'es' : ''}` : 'no memory' },
    { id: 'stage-fix',      label: 'Fix',      detail: fixMode },
    { id: 'stage-write',    label: 'Write',    detail: writeOk ? 'confirmed' : 'failed', error: !writeOk },
  ];

  const trackHtml = stages.map(s => `
    <div class="pipeline-track-stage" id="${s.id}">
      <div class="pipeline-dot"></div>
      <span class="pipeline-track-label">${s.label}</span>
      <span class="pipeline-track-detail">${escHtml(s.detail)}</span>
    </div>`).join('');

  container.className = 'fullloop-result-panel';
  container.innerHTML = `
    <!-- Stage pipeline track -->
    <div class="pipeline-track">${trackHtml}</div>

    <!-- Detection summary -->
    ${hasBreak ? `
    <div class="pipeline-section">
      <div class="pipeline-section-title">🔍 Detection</div>
      <div class="pipeline-section-body">
        <div class="pipeline-row">
          <span class="pipeline-key">Severity</span>
          <span>${severityBadge((det.severity || 'LOW').toUpperCase())}</span>
        </div>
        ${(det.missing_fields||[]).length ? `<div class="pipeline-row"><span class="pipeline-key">Dropped fields</span><span class="pipeline-mono">${escHtml((det.missing_fields||[]).join(', '))}</span></div>` : ''}
        ${(det.type_changes||[]).length ? `<div class="pipeline-row"><span class="pipeline-key">Type changes</span><span class="pipeline-mono">${escHtml((det.type_changes||[]).map(t => `${t.field}: ${t.was}→${t.now}`).join(', '))}</span></div>` : ''}
      </div>
    </div>` : ''}

    <!-- Root cause -->
    ${diag.root_cause ? `
    <div class="pipeline-section">
      <div class="pipeline-section-title">⚡ Root Cause</div>
      <div class="pipeline-section-body">
        <div class="pipeline-root-cause">${escHtml(String(diag.root_cause).slice(0, 280))}${String(diag.root_cause).length > 280 ? '…' : ''}</div>
      </div>
    </div>` : ''}

    <!-- Recall results (the key display section) -->
    <div class="pipeline-section pipeline-section-recall">
      <div class="pipeline-section-title">🧠 Memory Recall</div>
      <div class="pipeline-section-body">
        ${recallHtml}
      </div>
    </div>

    <!-- Fix -->
    <div class="pipeline-section">
      <div class="pipeline-section-title">🔧 Fix</div>
      <div class="pipeline-section-body">
        <div class="pipeline-row">
          <span class="pipeline-key">Mode</span>
          <span>${fixModeBadge}</span>
        </div>
        ${fix.estimated_time_saved_minutes ? `<div class="pipeline-row"><span class="pipeline-key">Est. time saved</span><span style="color:var(--color-strong-match);font-weight:500">${fix.estimated_time_saved_minutes} min</span></div>` : ''}
        ${fix.suggested_fix ? `<div class="pipeline-fix-preview">${escHtml(String(fix.suggested_fix).slice(0, 400))}${String(fix.suggested_fix).length > 400 ? '\n…' : ''}</div>` : ''}
      </div>
    </div>

    <!-- Write-memory confirmation -->
    <div class="pipeline-section">
      <div class="pipeline-section-title">💾 Write-Back to DataHub</div>
      <div class="pipeline-section-body">
        <div class="pipeline-row">
          <span class="pipeline-key">Status</span>
          <span>${writeBadge}</span>
        </div>
        <div class="pipeline-row">
          <span class="pipeline-key">Incident ID</span>
          <span class="pipeline-mono">${escHtml(incidentId)}</span>
        </div>
        ${wm.verification ? `<div class="pipeline-row"><span class="pipeline-key">Verification</span><span style="color:var(--color-fog);font-size:12px">${escHtml(wm.verification)}</span></div>` : ''}
      </div>
    </div>
  `;

  /* ── Staggered stage-dot reveal: 350 ms between each dot ── */
  stages.forEach((s, i) => {
    setTimeout(() => {
      const el = container.querySelector(`#${s.id}`);
      if (el) el.classList.add(s.error ? 'error' : 'complete');
    }, 350 * (i + 1));
  });
}

$('fullloop-btn')?.addEventListener('click', async () => {
  const urn      = $('fullloop-urn').value.trim();
  const simulate = $('fullloop-simulate').checked;
  if (!urn) { toast('Dataset URN is required', 'error'); return; }

  const resultEl = $('fullloop-result');
  setLoading('fullloop-btn', true);
  resultEl.className = 'fullloop-result-panel-loading';
  resultEl.innerHTML = `<div class="loading-cell"><div class="spinner"></div> Running full pipeline — Detect → Diagnose → Recall → Fix → Write…</div>`;
  show(resultEl);

  try {
    const data = await apiFetch('/api/full-loop', {
      method: 'POST',
      body: JSON.stringify({ dataset_urn: urn, simulate, top_k: 3, min_similarity: 0.60 }),
    });
    renderFullLoopResult(data, resultEl);
    const matches = (data.recall?.matches || []);
    if (matches.length > 0) {
      const top = matches[0];
      const score = top.similarity_score ?? 0;
      const pct = (score * 100).toFixed(1);
      const label = top.similarity_label || similarityLabel(score);
      toast(`Memory recalled: ${pct}% — ${label}`, 'success');
    } else {
      toast('Pipeline complete — no prior memory (first run)', 'info');
    }
    refresh();
    // Re-draw constellation so the new incident node appears live
    refreshMemoryGraph('memory-graph-container');
    // Always update stat cards — Full Loop writes a new memory record
    // regardless of which view the user is currently on
    refreshStats();
  } catch (err) {
    resultEl.className = 'result-panel error';
    resultEl.textContent = err.message;
    toast(err.message, 'error');
  } finally {
    const btn = $('fullloop-btn');
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Run Full Pipeline Loop`;
    }
  }
});


async function loadTimeline() {
  const container = $('timeline-list');
  container.innerHTML = `<div class="loading-cell"><div class="spinner"></div></div>`;

  try {
    const data = await apiFetch('/api/memories?limit=200');
    const records = data.records || [];
    $('timeline-count').textContent = `${records.length} records`;

    if (!records.length) {
      container.innerHTML = `<div class="empty-state"><p>No memory records yet.</p></div>`;
      return;
    }

    container.innerHTML = records.map(r => `
      <div class="timeline-item">
        <div class="timeline-dot" style="background:${typeColor(r.type)}20;border-color:${typeColor(r.type)}">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="${typeColor(r.type)}" style="flex-shrink:0"><circle cx="12" cy="12" r="6"/></svg>
        </div>
        <div class="timeline-body">
          <div class="timeline-title">
            ${escHtml(r.title)}
            <span style="margin-left:8px">${typeBadge(r.type)}</span>
            ${severityBadge(r.severity)}
            ${r.resolved ? `<span class="badge badge-green">✓ Resolved</span>` : ''}
          </div>
          <div class="timeline-meta">${formatDate(r.created_at)} · ${r.entity_urn ? shortUrn(r.entity_urn) : 'No entity'}</div>
          ${r.summary ? `<div class="timeline-summary">${escHtml(r.summary)}</div>` : ''}
        </div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = `<div class="empty-state" style="color:#ef4444"><p>${err.message}</p></div>`;
  }
}

/* ─── Refresh ─── */
function refresh() {
  const v = state.currentView;
  if (v === 'dashboard') loadDashboard();
  else if (v === 'memories') loadMemoriesTable();
  else if (v === 'timeline') loadTimeline();
}

$('refresh-btn')?.addEventListener('click', () => {
  const svg = $('refresh-btn')?.querySelector('svg');
  if (svg) svg.style.animation = 'spin 0.7s linear infinite';
  refresh();
  refreshStats(); // Stat cards update regardless of active view
  checkDataHubStatus();
  setTimeout(() => { const s = $('refresh-btn')?.querySelector('svg'); if (s) s.style.animation = ''; }, 800);
});

/* ─── Keyboard shortcuts ─── */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (!$('modal-overlay').classList.contains('hidden')) closeAddModal();
    if (!$('detail-overlay').classList.contains('hidden')) closeDetail();
  }
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    if (state.currentView === 'memories') $('mem-search')?.focus();
  }
});



/* ─── Init ─── */
(async function init() {
  await checkDataHubStatus();
  loadDashboard();          // also triggers refreshMemoryGraph internally
  setInterval(checkDataHubStatus, 30_000);
})();

