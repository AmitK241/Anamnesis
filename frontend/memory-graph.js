/**
 * Anamnesis — Memory Constellation Graph  v2
 * ============================================
 * D3 v7 force-directed graph. Reads CSS variables ONCE at init so SVG
 * .attr() calls always get real hex strings (never unresolved var(--...) refs).
 *
 * Public API
 * ----------
 *   renderMemoryGraph(containerId, graphData)   — initial render
 *   refreshMemoryGraph(containerId)             — fetch + re-render in place
 */

/* ─── Read computed CSS tokens (must be plain strings in SVG attrs) ────── */
const _cs = getComputedStyle(document.documentElement);
const GC = {
  TEXT:         _cs.getPropertyValue('--color-pale-mist').trim()    || '#c6c6c6',
  NODE_FILL:    _cs.getPropertyValue('--color-dusk-violet').trim()  || '#343755',
  NODE_STROKE:  _cs.getPropertyValue('--color-ghost-white').trim()  || '#ffffff',
  SMOKE:        _cs.getPropertyValue('--color-smoke').trim()         || '#808080',
  STRONG:       _cs.getPropertyValue('--color-strong-match').trim()  || '#4ade80',
  RELATED:      _cs.getPropertyValue('--color-related-match').trim() || '#d4a72c',
  POSSIBLE:     _cs.getPropertyValue('--color-possible-match').trim()|| '#5b8def',
  WEAK:         _cs.getPropertyValue('--color-weak-match').trim()    || '#6b6b6b',
  CRITICAL:     _cs.getPropertyValue('--color-critical').trim()      || '#e5484d',
};

/* ─── Edge color & weight by similarity ─────────────────────────────────── */
function edgeColor(sim) {
  if (sim >= 0.90) return GC.STRONG;
  if (sim >= 0.80) return GC.RELATED;
  if (sim >= 0.70) return GC.POSSIBLE;
  return GC.WEAK;
}
function edgeOpacity(sim) {
  return 0.35 + sim * 0.55;
}
function edgeWidth(sim) {
  return 1 + sim * 3;
}

/* ─── Node accent color by severity ───────────────────────────────── */
function nodeAccent(d, maxTs) {
  if (d.timestamp_ms === maxTs) return '#818cf8'; // newest — indigo
  const sev = (d.severity || '').toUpperCase();
  if (sev === 'CRITICAL') return GC.CRITICAL; // Red
  if (sev === 'HIGH') return GC.RELATED; // Amber
  if (sev === 'MEDIUM') return '#06b6d4'; // Cyan
  if (sev === 'LOW') return GC.STRONG; // Emerald
  return GC.NODE_FILL;
}

/* ─── Main render ────────────────────────────────────────────────────────── */
function renderMemoryGraph(containerId, graphData) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Clear any previous render + resize observer
  container.innerHTML = '';
  if (container._resizeObserver) {
    container._resizeObserver.disconnect();
    container._resizeObserver = null;
  }

  const nodes = (graphData.nodes || []).map(d => ({ ...d }));
  
  // Apply a visual threshold to prevent the graph from becoming a dense mesh
  // 0.85 clearly separates the 3-node Drop cluster and the 2-node Type-Change cluster
  const EDGE_DISPLAY_THRESHOLD = 0.85; 
  const edges = (graphData.edges || [])
    .filter(d => (d.similarity || 0) >= EDGE_DISPLAY_THRESHOLD)
    .map(d => ({ ...d }));

  if (nodes.length === 0) {
    container.innerHTML = `
      <div style="
        display:flex;align-items:center;justify-content:center;height:100%;
        color:${GC.SMOKE};font-family:'Space Grotesk',sans-serif;font-size:13px;
        flex-direction:column;gap:8px;
      ">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
          <path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"
                stroke="${GC.SMOKE}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        No incident memories in DataHub yet.
      </div>`;
    return;
  }

  let W = container.clientWidth  || 800;
  let H = container.clientHeight || 600;
  const maxTs = Math.max(...nodes.map(n => n.timestamp_ms || 0));

  /* ── SVG canvas ── */
  const svg = d3.select(`#${containerId}`)
    .append('svg')
    .attr('width', '100%')
    .attr('height', '100%')
    .attr('viewBox', [0, 0, W, H])
    .attr('preserveAspectRatio', 'xMidYMid meet')
    .style('display', 'block');

  /* ════════════════════════════════════════════════════════════════
     SVG DEFS — filters, gradients, markers
     ════════════════════════════════════════════════════════════════ */
  const defs = svg.append('defs');

  // ── 1. Per-node glow filters (one per accent color) ───────────────
  const GLOWS = [
    { id: 'glow-indigo', color: '#818cf8', blur: 8, strength: 1.8 },
    { id: 'glow-red',    color: GC.CRITICAL, blur: 7, strength: 1.6 },
    { id: 'glow-amber',  color: GC.RELATED,  blur: 7, strength: 1.6 },
    { id: 'glow-cyan',   color: '#06b6d4', blur: 7, strength: 1.6 },
    { id: 'glow-emerald',color: GC.STRONG, blur: 7, strength: 1.6 },
    { id: 'glow-blue',   color: GC.POSSIBLE, blur: 7, strength: 1.6 },
    { id: 'glow-default',color: '#818cf8',   blur: 5, strength: 1.3 },
  ];

  GLOWS.forEach(({ id, color, blur, strength }) => {
    const f = defs.append('filter')
      .attr('id', id)
      .attr('x', '-60%').attr('y', '-60%')
      .attr('width', '220%').attr('height', '220%');

    // Colorise SourceGraphic to the accent color, then blur it
    f.append('feColorMatrix')
      .attr('in', 'SourceGraphic')
      .attr('type', 'matrix')
      .attr('result', 'colored')
      .attr('values', (() => {
        // Parse hex → rgb fraction
        const hex = color.replace('#','');
        const r = parseInt(hex.slice(0,2),16)/255;
        const g = parseInt(hex.slice(2,4),16)/255;
        const b = parseInt(hex.slice(4,6),16)/255;
        // Matrix: output = accent color * alpha of source
        return `0 0 0 ${r} 0  0 0 0 ${g} 0  0 0 0 ${b} 0  0 0 0 ${strength} 0`;
      })());

    const blurEl = f.append('feGaussianBlur')
      .attr('in', 'colored')
      .attr('stdDeviation', blur)
      .attr('result', 'glow');

    // Animate the glow pulse (breathe between blur and blur+2)
    blurEl.append('animate')
      .attr('attributeName', 'stdDeviation')
      .attr('values', `${blur};${blur + 2};${blur}`)
      .attr('dur', '3.5s')
      .attr('repeatCount', 'indefinite');

    const merge = f.append('feMerge');
    merge.append('feMergeNode').attr('in', 'glow');
    merge.append('feMergeNode').attr('in', 'SourceGraphic');
  });

  // ── 2. Hover super-glow (stronger, applied on mouseenter) ─────────
  const hoverGlow = defs.append('filter')
    .attr('id', 'glow-hover')
    .attr('x', '-80%').attr('y', '-80%')
    .attr('width', '260%').attr('height', '260%');

  hoverGlow.append('feGaussianBlur')
    .attr('in', 'SourceGraphic')
    .attr('stdDeviation', 14)
    .attr('result', 'bigBlur');
  const hoverMerge = hoverGlow.append('feMerge');
  hoverMerge.append('feMergeNode').attr('in', 'bigBlur');
  hoverMerge.append('feMergeNode').attr('in', 'bigBlur'); // doubled for intensity
  hoverMerge.append('feMergeNode').attr('in', 'SourceGraphic');

  // ── 3. Per-edge linear gradients ──────────────────────────────────
  edges.forEach((e, i) => {
    const grad = defs.append('linearGradient')
      .attr('id', `edge-grad-${i}`)
      .attr('gradientUnits', 'userSpaceOnUse'); // positions updated each tick

    const c = edgeColor(e.similarity);
    grad.append('stop').attr('offset', '0%')
        .attr('stop-color', c).attr('stop-opacity', 0.15);
    grad.append('stop').attr('offset', '50%')
        .attr('stop-color', c).attr('stop-opacity', edgeOpacity(e.similarity));
    grad.append('stop').attr('offset', '100%')
        .attr('stop-color', c).attr('stop-opacity', 0.15);
    e._gradId = `edge-grad-${i}`;  // stash for tick updates
  });

  /* ════════════════════════════════════════════════════════════════
     FORCE SIMULATION
     ════════════════════════════════════════════════════════════════ */
  const sim = d3.forceSimulation(nodes)
    .force('link',      d3.forceLink(edges).id(d => d.id).distance(d => 260 - d.similarity * 40))
    .force('charge',    d3.forceManyBody().strength(-420))
    .force('center',    d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide().radius(60));

  /* ════════════════════════════════════════════════════════════════
     EDGES — animated gradient paths
     ════════════════════════════════════════════════════════════════ */
  const edgeGroup = svg.append('g').attr('class', 'mg-edges');

  // Outer glow path (blurred, wide) — the halo behind the edge
  const linkGlow = edgeGroup.selectAll('line.edge-glow')
    .data(edges)
    .join('line')
    .attr('class', 'edge-glow')
    .attr('stroke', d => edgeColor(d.similarity))
    .attr('stroke-opacity', 0.12)
    .attr('stroke-width', d => edgeWidth(d.similarity) * 4)
    .attr('stroke-linecap', 'round');

  // Main edge line — gradient stroke via gradient linearGradient
  const link = edgeGroup.selectAll('line.edge-main')
    .data(edges)
    .join('line')
    .attr('class', 'edge-main')
    .attr('stroke', d => `url(#${d._gradId})`)
    .attr('stroke-opacity', 1)
    .attr('stroke-width', d => edgeWidth(d.similarity))
    .attr('stroke-linecap', 'round')
    .attr('stroke-dasharray', d => d.similarity < 0.80 ? '6,5' : null)
    .style('transition', 'stroke-opacity 0.25s, stroke-width 0.25s');

  // Animated dash-offset on weak/possible edges (marching ants feel)
  link.filter(d => d.similarity < 0.80)
    .each(function(d) {
      d3.select(this).append('animate')
        .attr('attributeName', 'stroke-dashoffset')
        .attr('from', '0')
        .attr('to', '-22')
        .attr('dur', `${2.8 - d.similarity * 1.2}s`)
        .attr('repeatCount', 'indefinite');
    });

  /* ── Edge percentage labels ── */
  const edgeLabelGroup = svg.append('g').attr('class', 'mg-edge-labels');
  const edgeLabel = edgeLabelGroup.selectAll('text')
    .data(edges)
    .join('text')
    .attr('font-family', "'JetBrains Mono', monospace")
    .attr('font-size', '12px')
    .attr('font-weight', '500')
    .attr('fill', d => edgeColor(d.similarity))
    .attr('fill-opacity', d => edgeOpacity(d.similarity))
    .attr('text-anchor', 'middle')
    .attr('pointer-events', 'none')
    .style('filter', 'drop-shadow(0 0 3px rgba(0,0,0,0.9))')  // contrast shadow
    .text(d => `${(d.similarity * 100).toFixed(1)}%`);

  /* ════════════════════════════════════════════════════════════════
     NODES
     ════════════════════════════════════════════════════════════════ */
  const nodeGroup = svg.append('g').attr('class', 'mg-nodes');

  // ── Helper: pick the right idle glow filter per node ─────────────
  function nodeGlowFilter(d) {
    if (d.timestamp_ms === maxTs) return 'url(#glow-indigo)';
    const sev = (d.severity || '').toUpperCase();
    if (sev === 'CRITICAL') return 'url(#glow-red)';
    if (sev === 'HIGH') return 'url(#glow-amber)';
    if (sev === 'MEDIUM') return 'url(#glow-cyan)';
    if (sev === 'LOW') return 'url(#glow-emerald)';
    return 'url(#glow-default)';
  }

  const node = nodeGroup.selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', 'mg-node')
    .style('cursor', 'grab')
    .call(dragBehavior(sim));

  const NODE_R    = 24;
  const NODE_R_BIG = 28;  // newest node
  const nodeR = d => d.timestamp_ms === maxTs ? NODE_R_BIG : NODE_R;

  // Outer ring — accent color, low opacity, slightly larger than main circle
  node.append('circle')
    .attr('class', 'node-ring')
    .attr('r', d => nodeR(d) + 5)
    .attr('fill', 'none')
    .attr('stroke', d => nodeAccent(d, maxTs))
    .attr('stroke-width', 1)
    .attr('stroke-opacity', 0.25)
    .attr('pointer-events', 'none');

  // Main filled circle
  node.append('circle')
    .attr('class', 'node-circle')
    .attr('r', d => nodeR(d))
    .attr('fill', d => {
      const a = nodeAccent(d, maxTs);
      // Very dark fill tinted slightly with the accent colour
      return d.timestamp_ms === maxTs ? '#12122a' : '#0c0c0c';
    })
    .attr('stroke', d => nodeAccent(d, maxTs))
    .attr('stroke-width', d => d.timestamp_ms === maxTs ? 2 : 1.5)
    .attr('stroke-opacity', d => d.timestamp_ms === maxTs ? 0.9 : 0.55)
    .attr('filter', d => nodeGlowFilter(d));

  // Inner dot — accent glow centre
  node.append('circle')
    .attr('class', 'node-dot')
    .attr('r', 4)
    .attr('fill', d => nodeAccent(d, maxTs))
    .attr('fill-opacity', 0.8)
    .attr('pointer-events', 'none');

  // Dataset label below node
  node.append('text')
    .attr('class', 'node-label')
    .text(d => d.dataset)
    .attr('font-family', "'Space Grotesk', ui-sans-serif, sans-serif")
    .attr('font-size', '15px')
    .attr('font-weight', '600')
    .attr('fill', GC.TEXT)
    .attr('text-anchor', 'middle')
    .attr('dy', d => nodeR(d) + 20)
    .attr('pointer-events', 'none')
    .style('filter', 'drop-shadow(0 1px 4px rgba(0,0,0,1)) drop-shadow(0 0 8px rgba(0,0,0,0.9))');

  // Short incident ID beneath dataset name
  node.append('text')
    .attr('class', 'node-id')
    .text(d => d.id ? d.id.slice(-6) : '')
    .attr('font-family', "'JetBrains Mono', monospace")
    .attr('font-size', '10px')
    .attr('fill', GC.SMOKE)
    .attr('text-anchor', 'middle')
    .attr('dy', d => nodeR(d) + 34)
    .attr('pointer-events', 'none')
    .style('filter', 'drop-shadow(0 1px 3px rgba(0,0,0,1))');

  /* ════════════════════════════════════════════════════════════════
     TOOLTIP
     ════════════════════════════════════════════════════════════════ */
  const tooltip = d3.select(`#${containerId}`)
    .append('div')
    .style('position', 'absolute')
    .style('pointer-events', 'none')
    .style('background', 'rgba(5,5,15,0.92)')
    .style('border', `1px solid rgba(129,140,248,0.25)`)
    .style('border-radius', '8px')
    .style('padding', '10px 14px')
    .style('font-family', "'JetBrains Mono', monospace")
    .style('font-size', '11px')
    .style('color', GC.TEXT)
    .style('white-space', 'nowrap')
    .style('backdrop-filter', 'blur(8px)')
    .style('box-shadow', '0 4px 24px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04)')
    .style('opacity', '0')
    .style('transition', 'opacity 0.15s ease')
    .style('top', '0').style('left', '0')
    .style('z-index', '10');

  /* ════════════════════════════════════════════════════════════════
     HOVER INTERACTIONS
     ════════════════════════════════════════════════════════════════ */
  node.on('mouseenter', function(event, d) {
    const g = d3.select(this);

    // Grow and super-glow the node
    g.select('.node-circle')
      .transition().duration(200)
      .attr('r', nodeR(d) * 1.18)
      .attr('stroke-opacity', 1)
      .attr('stroke-width', 2.5)
      .attr('filter', 'url(#glow-hover)');

    g.select('.node-ring')
      .transition().duration(200)
      .attr('r', nodeR(d) * 1.18 + 7)
      .attr('stroke-opacity', 0.6);

    g.select('.node-dot')
      .transition().duration(200)
      .attr('r', 6)
      .attr('fill-opacity', 1);

    // Highlight connected edges — dim all others
    const connectedIds = new Set(
      edges.filter(e => e.source.id === d.id || e.target.id === d.id)
           .flatMap(e => [e.source.id, e.target.id])
    );

    link
      .transition().duration(200)
      .attr('stroke-opacity', e =>
        (e.source.id === d.id || e.target.id === d.id) ? 1 : 0.05)
      .attr('stroke-width', e =>
        (e.source.id === d.id || e.target.id === d.id)
          ? edgeWidth(e.similarity) * 1.8
          : edgeWidth(e.similarity) * 0.5);

    linkGlow
      .transition().duration(200)
      .attr('stroke-opacity', e =>
        (e.source.id === d.id || e.target.id === d.id) ? 0.28 : 0.03);

    edgeLabel
      .transition().duration(200)
      .attr('fill-opacity', e =>
        (e.source.id === d.id || e.target.id === d.id)
          ? 1
          : 0.08);

    // Dim non-connected nodes
    nodeGroup.selectAll('.mg-node')
      .filter(n => n.id !== d.id && !connectedIds.has(n.id))
      .transition().duration(200)
      .style('opacity', 0.25);

    // Tooltip
    tooltip
      .html(`
        <div style="color:${nodeAccent(d, maxTs)};font-weight:600;margin-bottom:4px">${d.id || '—'}</div>
        <div style="color:${GC.SMOKE}">${d.dataset_urn || d.dataset || '—'}</div>
        ${d.title ? `<div style="margin-top:4px;color:#818cf8;font-size:10px">${d.title}</div>` : ''}
      `)
      .style('opacity', '1');
  });

  node.on('mousemove', function(event) {
    const rect = container.getBoundingClientRect();
    const x = event.clientX - rect.left + 16;
    const y = event.clientY - rect.top  - 12;
    tooltip.style('left', `${x}px`).style('top', `${y}px`);
  });

  node.on('mouseleave', function(event, d) {
    const g = d3.select(this);

    // Restore node
    g.select('.node-circle')
      .transition().duration(250)
      .attr('r', nodeR(d))
      .attr('stroke-opacity', d.timestamp_ms === maxTs ? 0.9 : 0.55)
      .attr('stroke-width', d.timestamp_ms === maxTs ? 2 : 1.5)
      .attr('filter', nodeGlowFilter(d));

    g.select('.node-ring')
      .transition().duration(250)
      .attr('r', nodeR(d) + 5)
      .attr('stroke-opacity', 0.25);

    g.select('.node-dot')
      .transition().duration(250)
      .attr('r', 4)
      .attr('fill-opacity', 0.8);

    // Restore all edges
    link
      .transition().duration(250)
      .attr('stroke-opacity', 1)
      .attr('stroke-width', e => edgeWidth(e.similarity));

    linkGlow
      .transition().duration(250)
      .attr('stroke-opacity', 0.12);

    edgeLabel
      .transition().duration(250)
      .attr('fill-opacity', e => edgeOpacity(e.similarity));

    // Restore all nodes
    nodeGroup.selectAll('.mg-node')
      .transition().duration(250)
      .style('opacity', 1);

    tooltip.style('opacity', '0');
  });

  /* ════════════════════════════════════════════════════════════════
     TICK HANDLER
     ════════════════════════════════════════════════════════════════ */
  const PAD = 64;

  // Helper: update linearGradient endpoints to match the edge's current position
  function updateGradients() {
    edges.forEach(e => {
      const grad = defs.select(`#${e._gradId}`);
      if (grad.empty()) return;
      grad.attr('x1', e.source.x).attr('y1', e.source.y)
          .attr('x2', e.target.x).attr('y2', e.target.y);
    });
  }

  sim.on('tick', () => {
    nodes.forEach(d => {
      d.x = Math.max(PAD, Math.min(W - PAD, d.x));
      d.y = Math.max(PAD, Math.min(H - PAD, d.y));
    });

    updateGradients();

    linkGlow
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);

    link
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);

    edgeLabel
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2 - 8);

    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });

  /* ── On simulation end: snap cluster to container centre ── */
  sim.on('end', () => {
    if (nodes.length === 0) return;

    const xs = nodes.map(n => n.x);
    const ys = nodes.map(n => n.y);
    const clusterCx = (Math.min(...xs) + Math.max(...xs)) / 2;
    const clusterCy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const dx = W / 2 - clusterCx;
    const dy = H / 2 - clusterCy;

    nodes.forEach(n => {
      n.x = Math.max(PAD, Math.min(W - PAD, n.x + dx));
      n.y = Math.max(PAD, Math.min(H - PAD, n.y + dy));
    });

    updateGradients();

    linkGlow
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    link
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    edgeLabel
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2 - 8);
    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });

  /* ── Gentle perpetual floating ── */
  sim.on('end.float', () => {
    sim
      .force('jiggleX', d3.forceX(d => d.x).strength(0.008))
      .force('jiggleY', d3.forceY(d => d.y).strength(0.008))
      .alphaTarget(0.025)
      .alphaDecay(0)
      .restart();
  });

  /* ════════════════════════════════════════════════════════════════
     DRAG BEHAVIOUR — preserved exactly
     ════════════════════════════════════════════════════════════════ */
  function dragBehavior(simulation) {
    return d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
        d3.select(event.sourceEvent.target.closest('.mg-node'))
          .style('cursor', 'grabbing');
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.025);
        d.fx = null;
        d.fy = null;
        d3.select(event.sourceEvent.target.closest('.mg-node'))
          .style('cursor', 'grab');
      });
  }

  /* ── ResizeObserver: re-render when container size changes ── */
  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => {
      clearTimeout(container._resizeTimer);
      container._resizeTimer = setTimeout(() => {
        const newW = container.clientWidth;
        const newH = container.clientHeight;
        if (!newW || !newH) return;
        W = newW;
        H = newH;
        svg.attr('viewBox', [0, 0, W, H]);
        sim.force('center', d3.forceCenter(W / 2, H / 2));
        sim.alpha(0.3).restart();
      }, 150);
    });
    ro.observe(container);
    container._resizeObserver = ro;
  }
}

/* ─── Fetch from /api/incidents and (re)render ──────────────────────────── */
async function refreshMemoryGraph(containerId) {
  try {
    const res = await fetch(`${API}/api/incidents`);
    if (!res.ok) throw new Error(`/api/incidents returned ${res.status}`);
    const graphData = await res.json();
    renderMemoryGraph(containerId, graphData);
  } catch (err) {
    const el = document.getElementById(containerId);
    if (el) {
      el.innerHTML = `
        <div style="
          display:flex;align-items:center;justify-content:center;height:100%;
          color:#e5484d;font-family:'JetBrains Mono',monospace;font-size:12px;
        ">Graph unavailable: ${err.message}</div>`;
    }
    console.warn('[MemoryGraph] fetch failed:', err);
  }
}