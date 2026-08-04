/**
 * Anamnesis — Memory Constellation Graph
 * ========================================
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
  TEXT:         _cs.getPropertyValue('--color-pale-mist').trim()   || '#c6c6c6',
  NODE_FILL:    _cs.getPropertyValue('--color-dusk-violet').trim() || '#343755',
  NODE_STROKE:  _cs.getPropertyValue('--color-ghost-white').trim() || '#ffffff',
  SMOKE:        _cs.getPropertyValue('--color-smoke').trim()        || '#808080',
  STRONG:       _cs.getPropertyValue('--color-strong-match').trim() || '#4ade80',
  RELATED:      _cs.getPropertyValue('--color-related-match').trim()|| '#d4a72c',
  POSSIBLE:     _cs.getPropertyValue('--color-possible-match').trim()|| '#5b8def',
  WEAK:         _cs.getPropertyValue('--color-weak-match').trim()   || '#6b6b6b',
  CRITICAL:     _cs.getPropertyValue('--color-critical').trim()     || '#e5484d',
};

/* ─── Edge appearance by similarity score ──────────────────────────────── */
function edgeColor(sim) {
  if (sim >= 0.90) return GC.STRONG;
  if (sim >= 0.80) return GC.RELATED;
  if (sim >= 0.70) return GC.POSSIBLE;
  return GC.WEAK;
}

function edgeOpacity(sim) {
  // Strongest edges are fully opaque; weakest are ghosted
  return 0.30 + sim * 0.65;
}

/* ─── Main render ────────────────────────────────────────────────────────── */
function renderMemoryGraph(containerId, graphData) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Clear any previous render
  container.innerHTML = '';

  const nodes = (graphData.nodes || []).map(d => ({ ...d })); // shallow copy for D3 mutation
  const edges = (graphData.edges || []).map(d => ({ ...d }));

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

  const W = container.clientWidth  || 800;
  const H = container.clientHeight || 480;

  /* ── SVG canvas ── */
  const svg = d3.select(`#${containerId}`)
    .append('svg')
    .attr('width', W)
    .attr('height', H)
    .attr('viewBox', [0, 0, W, H])
    .style('display', 'block');

  /* ── Defs: glow filter + arrow marker ── */
  const defs = svg.append('defs');

  // Glow filter (applied to node circles)
  const glowFilter = defs.append('filter')
    .attr('id', 'mg-node-glow')
    .attr('x', '-50%').attr('y', '-50%')
    .attr('width', '200%').attr('height', '200%');
  glowFilter.append('feGaussianBlur')
    .attr('in', 'SourceGraphic')
    .attr('stdDeviation', '5')
    .attr('result', 'blur');
  const feMerge = glowFilter.append('feMerge');
  feMerge.append('feMergeNode').attr('in', 'blur');
  feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

  // Subtle pulse filter for "newest" node
  const pulseFilter = defs.append('filter')
    .attr('id', 'mg-node-pulse')
    .attr('x', '-80%').attr('y', '-80%')
    .attr('width', '360%').attr('height', '360%');
  pulseFilter.append('feGaussianBlur')
    .attr('in', 'SourceGraphic')
    .attr('stdDeviation', '8')
    .attr('result', 'blur');
  const pMerge = pulseFilter.append('feMerge');
  pMerge.append('feMergeNode').attr('in', 'blur');
  pMerge.append('feMergeNode').attr('in', 'SourceGraphic');

  /* ── Radial background gradient on the SVG itself ── */
  const grad = defs.append('radialGradient')
    .attr('id', 'mg-bg-grad')
    .attr('cx', '35%').attr('cy', '30%')
    .attr('r', '60%');
  grad.append('stop').attr('offset', '0%').attr('stop-color', GC.NODE_FILL).attr('stop-opacity', '0.12');
  grad.append('stop').attr('offset', '100%').attr('stop-color', 'transparent').attr('stop-opacity', '0');

  svg.append('rect')
    .attr('width', W).attr('height', H)
    .attr('fill', 'url(#mg-bg-grad)');

  /* ── Force simulation ── */
  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(d => 180 - d.similarity * 60))
    .force('charge', d3.forceManyBody().strength(-320))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide().radius(46));

  /* ── Edge lines ── */
  const edgeGroup = svg.append('g').attr('class', 'mg-edges');
  const link = edgeGroup.selectAll('line')
    .data(edges)
    .join('line')
    .attr('stroke', d => edgeColor(d.similarity))
    .attr('stroke-opacity', d => edgeOpacity(d.similarity))
    .attr('stroke-width', d => 1 + d.similarity * 3.5)
    .attr('stroke-dasharray', d => d.similarity < 0.80 ? '5,4' : null)
    .style('transition', 'stroke-opacity 0.2s');

  /* ── Edge percentage labels ── */
  const edgeLabelGroup = svg.append('g').attr('class', 'mg-edge-labels');
  const edgeLabel = edgeLabelGroup.selectAll('text')
    .data(edges)
    .join('text')
    .attr('font-family', "'JetBrains Mono', monospace")
    .attr('font-size', '10px')
    .attr('fill', d => edgeColor(d.similarity))
    .attr('fill-opacity', d => edgeOpacity(d.similarity))
    .attr('text-anchor', 'middle')
    .attr('pointer-events', 'none')
    .text(d => `${(d.similarity * 100).toFixed(1)}%`);

  /* ── Node groups (circle + label) ── */
  const nodeGroup = svg.append('g').attr('class', 'mg-nodes');

  // Determine "newest" node (highest timestamp) for subtle emphasis
  const maxTs = Math.max(...nodes.map(n => n.timestamp_ms || 0));

  const node = nodeGroup.selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', 'mg-node')
    .style('cursor', 'grab')
    .call(dragBehavior(sim));

  // Outer glow ring (only on newest node, if > 1 node)
  if (nodes.length > 1) {
    node.filter(d => d.timestamp_ms === maxTs)
      .append('circle')
      .attr('r', 22)
      .attr('fill', 'none')
      .attr('stroke', GC.STRONG)
      .attr('stroke-width', 1)
      .attr('stroke-opacity', 0.35)
      .attr('filter', 'url(#mg-node-pulse)');
  }

  // Main node circle
  node.append('circle')
    .attr('r', 14)
    .attr('fill', GC.NODE_FILL)
    .attr('stroke', GC.NODE_STROKE)
    .attr('stroke-width', 1.5)
    .attr('filter', 'url(#mg-node-glow)');

  // Dataset name below node
  node.append('text')
    .text(d => d.dataset)
    .attr('font-family', "'Space Grotesk', ui-sans-serif, sans-serif")
    .attr('font-size', '11px')
    .attr('font-weight', '600')
    .attr('fill', GC.TEXT)
    .attr('text-anchor', 'middle')
    .attr('dy', 30)
    .attr('pointer-events', 'none');

  // Short incident ID beneath dataset name
  node.append('text')
    .text(d => d.id ? d.id.slice(-6) : '')
    .attr('font-family', "'JetBrains Mono', monospace")
    .attr('font-size', '9px')
    .attr('fill', GC.SMOKE)
    .attr('text-anchor', 'middle')
    .attr('dy', 43)
    .attr('pointer-events', 'none');

  /* ── Tooltip on hover ── */
  const tooltip = d3.select(`#${containerId}`)
    .append('div')
    .style('position', 'absolute')
    .style('pointer-events', 'none')
    .style('background', 'rgba(0,0,0,0.88)')
    .style('border', `1px solid ${GC.NODE_STROKE}22`)
    .style('border-radius', '6px')
    .style('padding', '8px 12px')
    .style('font-family', "'JetBrains Mono', monospace")
    .style('font-size', '11px')
    .style('color', GC.TEXT)
    .style('white-space', 'nowrap')
    .style('opacity', '0')
    .style('transition', 'opacity 0.15s')
    .style('top', '0').style('left', '0');

  node.on('mouseenter', function(event, d) {
    d3.select(this).select('circle')
      .attr('stroke', GC.STRONG)
      .attr('stroke-width', 2.5);
    tooltip
      .html(`<strong>${d.id}</strong><br/>${d.dataset_urn || d.dataset}`)
      .style('opacity', '1');
  });
  node.on('mousemove', function(event) {
    const rect = container.getBoundingClientRect();
    const x = event.clientX - rect.left + 14;
    const y = event.clientY - rect.top - 10;
    tooltip.style('left', `${x}px`).style('top', `${y}px`);
  });
  node.on('mouseleave', function() {
    d3.select(this).select('circle')
      .attr('stroke', GC.NODE_STROKE)
      .attr('stroke-width', 1.5);
    tooltip.style('opacity', '0');
  });

  /* ── Tick handler ── */
  sim.on('tick', () => {
    // Clamp nodes inside SVG bounds
    nodes.forEach(d => {
      d.x = Math.max(30, Math.min(W - 30, d.x));
      d.y = Math.max(30, Math.min(H - 30, d.y));
    });

    link
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);

    edgeLabel
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2 - 5);

    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });

  /* ── Drag behaviour ── */
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
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
        d3.select(event.sourceEvent.target.closest('.mg-node'))
          .style('cursor', 'grab');
      });
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
