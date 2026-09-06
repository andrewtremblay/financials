import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  sankey as d3Sankey,
  sankeyLeft,
  sankeyRight,
  sankeyCenter,
  sankeyJustify,
  SankeyNode as D3SankeyNode,
  SankeyLink as D3SankeyLink,
  SankeyGraph,
} from 'd3-sankey';
import { select as d3Select } from 'd3-selection';
import { zoom as d3Zoom, zoomIdentity, type ZoomBehavior } from 'd3-zoom';
import type { SkmSettings, FlowLine, NodeDef } from '../types';
import { resolveNodeColors, resolveFlowColor, expandHex } from '../lib/colors';
import { getOrigins, getEndpoints, resolveAmounts } from '../lib/parser';
import { formatValue } from '../lib/format';
import { declutterPositions } from '../lib/labelDeclutter';

interface Props {
  flows: FlowLine[];
  nodeDefs: Map<string, NodeDef>;
  settings: SkmSettings;
  svgRef?: React.RefObject<SVGSVGElement>;
  // When true, the SVG scales to fill its container (width/height: 100%,
  // relying on the viewBox for the internal coordinate system) instead of
  // rendering at its literal size_w x size_h pixel dimensions. Defaults to
  // false, which preserves the Sankey Builder tool's existing exact-pixel-size
  // behavior (its size readout and PNG/SVG export assume literal dimensions).
  fitToContainer?: boolean;
  // When true, the SVG renders at its literal size_w x size_h with no CSS
  // max-width/max-height cap, so a diagram taller/wider than its panel
  // overflows rather than shrinking — the panel is expected to scroll (e.g.
  // `overflow-auto`). Used by the budget dashboard: shrinking to fit also
  // shrinks the SVG's fixed-px-size label text, making dense months
  // unreadable (2026-07-31, user-specified: scroll instead of shrink).
  scrollable?: boolean;
  // When true, adds mouse-wheel zoom, click-drag pan, and on-screen
  // zoom in/out/reset controls (2026-08-01, user-requested). Content
  // renders inside a transformed <g> so the underlying size_w/size_h
  // coordinate system — and everything computed from it — is unaffected.
  zoomable?: boolean;
  // When provided, clicking a node's rectangle OR its text label fires this
  // with the node's id (== its Sankeymatic node name, possibly disambiguated
  // — see budget_sankeymatic.py's node_name()). Opt-in: this component is
  // also used by the standalone Sankey Builder tool, which has no concept of
  // "line items" or drawers, so click-to-callback must never fire unless a
  // caller explicitly asks for it (2026-08-01, user-requested).
  onNodeClick?: (nodeId: string) => void;
}

// Pointer movement (px), measured between mousedown and mouseup, below which
// a gesture on a node/label counts as a click rather than a drag (moving a
// node) or a would-be pan (dragging the canvas background) — used to avoid
// firing onNodeClick after the user was actually dragging/panning.
const CLICK_MOVE_THRESHOLD_PX = 4;

interface NodeDatum {
  id: string;
  name: string;
  color: string;
  opacity: number;
}

interface LinkDatum {
  source: string;
  target: string;
  value: number;
  color: string;
  opacity: number;
}

type LayoutNode = D3SankeyNode<NodeDatum, LinkDatum>;
type LayoutLink = D3SankeyLink<NodeDatum, LinkDatum>;
type SankeyGen = ReturnType<typeof d3Sankey<NodeDatum, LinkDatum>>;


// Build layout from scratch. Returns null if there is nothing renderable.
function buildLayout(
  flows: FlowLine[],
  nodeDefs: Map<string, NodeDef>,
  settings: SkmSettings,
): { generator: SankeyGen; graph: SankeyGraph<NodeDatum, LinkDatum> } | null {
  const {
    size_w, size_h, margin_l, margin_r, margin_t, margin_b,
    node_w, node_spacing,
    layout_justifyorigins, layout_justifyends, layout_reversegraph,
    internal_iterations,
  } = settings;

  const resolvedFlows = resolveAmounts(flows);
  const validFlows = resolvedFlows.filter(
    f => typeof f.amount === 'number' && (f.amount as number) > 0,
  );
  if (validFlows.length === 0) return null;

  const nodeNameSet = new Set<string>();
  for (const f of validFlows) {
    nodeNameSet.add(f.source);
    nodeNameSet.add(f.target);
  }
  for (const k of nodeDefs.keys()) nodeNameSet.add(k);
  const nodeNames = Array.from(nodeNameSet);
  const nodeSet = new Set<string>(nodeNames);

  const nodes: NodeDatum[] = nodeNames.map(name => ({
    id: name, name, color: '#888888', opacity: 1,
  }));

  // Position within a column later uses this to keep siblings grouped under
  // their parent in the order they were emitted (e.g. Transportation's
  // children together, then Daily Living's, not interleaved) — nodeNameSet
  // is a Set, which preserves first-seen order across the parsed flows.
  const nodeEmissionOrder = new Map<string, number>();
  nodeNames.forEach((name, i) => nodeEmissionOrder.set(name, i));

  const linkMap = new Map<string, LinkDatum>();
  for (const f of validFlows) {
    if (f.source === f.target) continue;
    if (!nodeSet.has(f.source) || !nodeSet.has(f.target)) continue;
    const srcId = layout_reversegraph ? f.target : f.source;
    const tgtId = layout_reversegraph ? f.source : f.target;
    const key = `${srcId}\x00${tgtId}`;
    const amt = f.amount as number;
    if (linkMap.has(key)) {
      linkMap.get(key)!.value += amt;
    } else {
      linkMap.set(key, { source: srcId, target: tgtId, value: amt, color: '#999999', opacity: 0.45 });
    }
  }

  const links = Array.from(linkMap.values());
  if (links.length === 0) return null;

  // Default to sankeyLeft: nodes sit at their natural BFS depth.
  // sankeyJustify pushes leaf nodes right, creating long-range flows that
  // skip columns and cause heavy crossing; use it only if explicitly requested.
  let align = sankeyLeft;
  if (layout_justifyorigins && layout_justifyends) align = sankeyCenter;
  else if (layout_justifyends) align = sankeyJustify;
  else if (layout_justifyorigins) align = sankeyLeft;

  const nodePadding = Math.max(1, node_spacing * 0.3);

  const generator = d3Sankey<NodeDatum, LinkDatum>()
    .nodeId(d => d.id)
    .nodeAlign(align)
    .nodeWidth(node_w)
    .nodePadding(nodePadding)
    .extent([[margin_l, margin_t], [size_w - margin_r, size_h - margin_b]])
    .iterations(internal_iterations);

  try {
    const graph = generator({
      nodes: nodes.map(n => ({ ...n })),
      links: links.map(l => ({ ...l })),
    });

    // Redistribute nodes vertically in each column using node.value
    // (set by d3-sankey's computeNodeValues from link amounts) for heights.
    // This is more reliable than y1-y0 which can be 0 if ky collapses.
    const availableH = size_h - margin_t - margin_b;
    // A real, visible minimum — 8px reads as "touching" once a column has
    // more than a handful of nodes; this is a hard floor regardless of how
    // tall a node's proportional (value-driven) height ends up being
    // (2026-07-31, user-specified: "minimum padding between nodes
    // regardless of their height"). Bumped from 16 now that every node's
    // value label is always visible (2026-08-01) — a 2-line label needs more
    // breathing room than the old name-only default assumed.
    const minGap = 28;

    // Group nodes by d3-sankey column depth (more reliable than rounding x0).
    const byColumn = new Map<number, (LayoutNode & NodeDatum)[]>();
    for (const node of graph.nodes) {
      const nd = node as LayoutNode & NodeDatum;
      const col = (nd as unknown as { depth?: number }).depth ?? Math.round(nd.x0 ?? 0);
      if (!byColumn.has(col)) byColumn.set(col, []);
      byColumn.get(col)!.push(nd);
    }

    // Pure proportional ky: each column constrains ky independently.
    // ky = min over columns of (availableH - (n-1)*gap) / totalValue
    // This ensures flows and node heights stay consistent (no minimum-height mismatch).
    let ky = Infinity;
    for (const colNodes of byColumn.values()) {
      const n = colNodes.length;
      const totalValue = colNodes.reduce(
        (s, nd) => s + ((nd as unknown as { value: number }).value ?? 0), 0,
      );
      if (totalValue > 0) {
        const room = availableH - Math.max(0, n - 1) * minGap;
        if (room > 0) ky = Math.min(ky, room / totalValue);
      }
    }
    if (!isFinite(ky) || ky <= 0) ky = 1;

    // Link widths proportional to value × ky so they visually fill node height.
    for (const link of graph.links) {
      (link as unknown as { width: number }).width = Math.max(1, (link.value ?? 0) * ky);
    }

    // Position each column: nodes sorted by original emission order (not
    // d3-sankey's own y0), gaps distributed evenly. d3-sankey's default
    // ordering minimizes link crossings, which can interleave children from
    // different parent sections when that reduces visual crossings (e.g.
    // Transportation's and Daily Living's children mixed together) — using
    // the order flows were actually declared in keeps siblings grouped
    // (2026-07-31 fix).
    // A column with far fewer nodes than the busiest one (e.g. 6 top-level
    // sections vs. ~30 line items) would otherwise stretch its gaps to fill
    // the exact same availableH as the busiest column, since the loop below
    // used to divide 100% of the leftover space across every pair — a 6-node
    // column can end up with 80px+ between nodes vs. this 16px floor,
    // reading as a big blank "void" next to a ribbon (2026-07-31,
    // user-reported: looked like a missing ribbon fill, actually just an
    // oversized gap). Cap the gap and center the column's own (smaller)
    // block in the available height instead of force-stretching it.
    const maxGap = minGap * 3;
    for (const colNodes of byColumn.values()) {
      colNodes.sort((a, b) => (nodeEmissionOrder.get(a.id) ?? 0) - (nodeEmissionOrder.get(b.id) ?? 0));
      const n = colNodes.length;
      const heights = colNodes.map(
        nd => Math.max(1, ((nd as unknown as { value: number }).value ?? 0) * ky),
      );
      const totalNodeH = heights.reduce((a, b) => a + b, 0);
      const naturalGap = n > 1 ? (availableH - totalNodeH) / (n - 1) : 0;
      const gap = Math.min(maxGap, Math.max(minGap, naturalGap));
      const usedH = totalNodeH + Math.max(0, n - 1) * gap;
      let y = margin_t + Math.max(0, (availableH - usedH) / 2);
      for (let i = 0; i < n; i++) {
        colNodes[i].y0 = y;
        colNodes[i].y1 = y + heights[i];
        y += heights[i] + gap;
      }
    }
    // d3-sankey stacks each node's ribbon bands (via update() below) in
    // whatever order its sourceLinks/targetLinks arrays already happen to be
    // in — set once by its own crossing-minimization layout, before we
    // overrode node y-positions to emission order above. Left alone, that
    // stale order makes ribbons cross even though the nodes they connect no
    // longer do (2026-07-31, user-reported: overlapping ribbons in Savings).
    // Re-sort both arrays to match the node order we just established so
    // the bands stack top-to-bottom in the same order as the nodes.
    const idOf = (n: LayoutNode & NodeDatum | string): string =>
      typeof n === 'object' ? n.id : n;
    for (const node of graph.nodes) {
      const nd = node as LayoutNode & NodeDatum;
      nd.sourceLinks?.sort((a, b) =>
        (nodeEmissionOrder.get(idOf(a.target as LayoutNode & NodeDatum)) ?? 0) -
        (nodeEmissionOrder.get(idOf(b.target as LayoutNode & NodeDatum)) ?? 0));
      nd.targetLinks?.sort((a, b) =>
        (nodeEmissionOrder.get(idOf(a.source as LayoutNode & NodeDatum)) ?? 0) -
        (nodeEmissionOrder.get(idOf(b.source as LayoutNode & NodeDatum)) ?? 0));
    }

    generator.update(graph);

    return { generator, graph };
  } catch {
    return null;
  }
}

// Apply colors to existing graph nodes/links in-place.
function applyColors(
  graph: SankeyGraph<NodeDatum, LinkDatum>,
  flows: FlowLine[],
  nodeDefs: Map<string, NodeDef>,
  settings: SkmSettings,
) {
  const resolvedFlows = resolveAmounts(flows).filter(
    f => typeof f.amount === 'number' && (f.amount as number) > 0,
  );
  const nodeNames = graph.nodes.map(n => (n as LayoutNode & NodeDatum).id);
  const origins = getOrigins(resolvedFlows);
  const endpoints = getEndpoints(resolvedFlows);
  const nodeColors = resolveNodeColors(nodeNames, nodeDefs, settings, resolvedFlows);

  for (const node of graph.nodes) {
    const nd = node as LayoutNode & NodeDatum;
    const nc = nodeColors.get(nd.id);
    nd.color = nc?.color ?? expandHex(settings.node_color);
    nd.opacity = nc?.opacity ?? settings.node_opacity;
  }

  const rev = settings.layout_reversegraph;
  for (const link of graph.links) {
    const ld = link as LayoutLink & LinkDatum;
    const srcId: string = typeof ld.source === 'object'
      ? (ld.source as LayoutNode & NodeDatum).id
      : (ld.source as unknown as string);
    const tgtId: string = typeof ld.target === 'object'
      ? (ld.target as LayoutNode & NodeDatum).id
      : (ld.target as unknown as string);
    const flowSrc = rev ? tgtId : srcId;
    const flowTgt = rev ? srcId : tgtId;
    const matchFlow = resolvedFlows.find(f => f.source === flowSrc && f.target === flowTgt);
    const fakeFlow = matchFlow ?? { source: flowSrc, target: flowTgt, amount: 0 };
    const { color, opacity } = resolveFlowColor(fakeFlow, nodeColors, settings, origins, endpoints);
    ld.color = color;
    ld.opacity = opacity;
  }

  // A node's own rect is colored independently of its ribbons (hash-derived
  // from its name, same as any other node) — for a hub fed by exactly one
  // ribbon (the overwhelmingly common case here: Budget -> Savings, Budget
  // -> Needs, Budget -> Home, ...), that independent color is usually a
  // *similar but not identical* shade to the ribbon feeding it, since both
  // come from the same hash-based palette. The node's rect then reads as a
  // third, slightly-off-hue segment sitting between the ribbon's true color
  // and whatever comes next — reported as "odd vertical lines" / a
  // ribbon's right end not matching its own middle (2026-08-02,
  // user-reported, screenshots of the Savings and Needs hubs). When every
  // incoming ribbon agrees on one color, adopt it for the node too, so the
  // node reads as a seamless continuation of its own ribbon. Skipped when a
  // node has an explicit `:Name #color` directive (e.g. Needs/Wants — see
  // budget_sankeymatic.py) or a node theme is active, since both are
  // deliberate, curated color choices that must not be silently overridden.
  if (settings.node_theme === 'none') {
    const incomingColors = new Map<string, Set<string>>();
    for (const link of graph.links) {
      const ld = link as LayoutLink & LinkDatum;
      const tgtId = typeof ld.target === 'object' ? (ld.target as LayoutNode & NodeDatum).id : String(ld.target);
      if (!incomingColors.has(tgtId)) incomingColors.set(tgtId, new Set());
      incomingColors.get(tgtId)!.add(ld.color as string);
    }
    for (const node of graph.nodes) {
      const nd = node as LayoutNode & NodeDatum;
      if (nodeDefs.get(nd.id)?.color) continue; // explicit color always wins
      const colors = incomingColors.get(nd.id);
      if (colors && colors.size === 1) {
        nd.color = [...colors][0];
      }
    }
  }
}


const SankeyDiagram: React.FC<Props> = ({ flows, nodeDefs, settings, svgRef, fitToContainer, scrollable, zoomable, onNodeClick }) => {
  const [graphVersion, setGraphVersion] = useState(0);
  const graphRef = useRef<SankeyGraph<NodeDatum, LinkDatum> | null>(null);
  const generatorRef = useRef<SankeyGen | null>(null);

  const settingsRef = useRef(settings);
  useEffect(() => { settingsRef.current = settings; }, [settings]);

  // Zoom/pan (only wired up when zoomable). svgNode is STATE, not a plain
  // ref — the component swaps between two entirely different trees (a bare
  // <svg> for the "no data yet" empty state vs. <div><svg/>{controls}</div>
  // once a graph exists), which unmounts and remounts the <svg> DOM node.
  // A plain ref updated silently by setSvgNode wouldn't re-trigger the
  // binding effect below when that swap happens, leaving d3-zoom's native
  // listeners attached to the discarded throwaway node — the diagram would
  // render, the +/- buttons would work (they always read the ref fresh),
  // but wheel-zoom and drag-to-pan would silently do nothing (2026-08-01,
  // found via testing: d3-zoom's `__zoom` marker was missing from the live
  // <svg> entirely). Making it state means the effect's dependency array
  // sees every node change and rebinds.
  const [svgNode, setSvgNodeState] = useState<SVGSVGElement | null>(null);
  const zoomBehaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const [zoomTransform, setZoomTransform] = useState({ x: 0, y: 0, k: 1 });

  // Memoized so its identity is stable across renders — otherwise a fresh
  // inline function on every render makes React detach-then-reattach the
  // ref (null, then the node) on every single re-render, which would churn
  // the zoom effect below (unbind/rebind on every graphVersion change,
  // dragged node, month switch, etc.) instead of once per real node swap.
  const setSvgNode = useCallback((node: SVGSVGElement | null) => {
    setSvgNodeState(node);
    if (svgRef) (svgRef as React.MutableRefObject<SVGSVGElement | null>).current = node;
  }, [svgRef]);

  useEffect(() => {
    if (!zoomable || !svgNode) return;
    const behavior = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 8])
      .filter(event => !event.button && event.type !== 'dblclick')
      .on('zoom', event => setZoomTransform({ x: event.transform.x, y: event.transform.y, k: event.transform.k }));
    zoomBehaviorRef.current = behavior;
    const sel = d3Select(svgNode);
    sel.call(behavior);
    return () => { sel.on('.zoom', null); };
  }, [zoomable, svgNode]);

  const zoomBy = (factor: number) => {
    const behavior = zoomBehaviorRef.current;
    if (!svgNode || !behavior) return;
    d3Select(svgNode).transition().duration(150).call(behavior.scaleBy, factor);
  };

  const resetZoom = () => {
    const behavior = zoomBehaviorRef.current;
    if (!svgNode || !behavior) return;
    d3Select(svgNode).transition().duration(200).call(behavior.transform, zoomIdentity);
  };

  const dragRef = useRef<{
    nodeId: string;
    startClientX: number;
    startClientY: number;
    startY0: number;
    startY1: number;
    // False until the pointer moves past CLICK_MOVE_THRESHOLD_PX — lets
    // mouseup distinguish "this was a click" (fire onNodeClick) from "this
    // was a drag" (reposition already applied live by onMove, do nothing
    // further).
    moved: boolean;
  } | null>(null);

  // Kept current via effect (not read directly from the closure) because the
  // global mousedown/mouseup listeners below are registered once ([] deps)
  // and must not go stale if a parent re-renders with a new onNodeClick
  // identity.
  const onNodeClickRef = useRef(onNodeClick);
  useEffect(() => { onNodeClickRef.current = onNodeClick; }, [onNodeClick]);

  // Mirrors dragRef's mousedown bookkeeping but for text labels, which don't
  // support dragging — a mousedown here only ever resolves to "click" or
  // "not a click" at mouseup.
  const labelClickRef = useRef<{
    nodeId: string;
    startClientX: number;
    startClientY: number;
  } | null>(null);

  // Extracted so a manual "reset layout" action (see resetLayout below) can
  // recompute from scratch on demand, not just when flows/nodeDefs/settings
  // themselves change — dragging a node (handleNodeMouseDown/onMove below)
  // mutates graphRef.current's y0/y1 directly rather than going through
  // this effect, so nothing else naturally un-does a drag within the same
  // month/settings (2026-08-02, user-requested).
  const recomputeLayout = useCallback(() => {
    const result = buildLayout(flows, nodeDefs, settings);
    if (result) {
      applyColors(result.graph, flows, nodeDefs, settings);
      graphRef.current = result.graph;
      generatorRef.current = result.generator;
    } else {
      graphRef.current = null;
      generatorRef.current = null;
    }
    setGraphVersion(v => v + 1);
  }, [flows, nodeDefs, settings]);

  useEffect(() => {
    recomputeLayout();
  }, [recomputeLayout]);

  // Global drag listeners (registered once).
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragRef.current || !graphRef.current || !generatorRef.current) return;
      const { nodeId, startClientX, startClientY, startY0, startY1 } = dragRef.current;
      const dy = e.clientY - startClientY;

      if (!dragRef.current.moved) {
        const dx = e.clientX - startClientX;
        if (Math.abs(dx) > CLICK_MOVE_THRESHOLD_PX || Math.abs(dy) > CLICK_MOVE_THRESHOLD_PX) {
          dragRef.current.moved = true;
        }
      }

      const graph = graphRef.current;
      const node = graph.nodes.find(
        n => (n as LayoutNode & NodeDatum).id === nodeId,
      ) as (LayoutNode & NodeDatum) | undefined;
      if (!node) return;

      const { margin_t, margin_b, size_h } = settingsRef.current;
      const nodeH = (node.y1 ?? 0) - (node.y0 ?? 0);
      const newY0 = Math.max(margin_t, Math.min(size_h - margin_b - nodeH, startY0 + dy));
      node.y0 = newY0;
      node.y1 = newY0 + nodeH;

      generatorRef.current.update(graph);
      setGraphVersion(v => v + 1);
    };

    // A plain click on a node rect goes through the exact same
    // mousedown→mouseup cycle as a drag (handleNodeMouseDown always arms
    // dragRef) — the only difference is whether the pointer moved past the
    // threshold in between. If it didn't, this was a click: fire
    // onNodeClick instead of silently discarding the (no-op) gesture.
    const onUp = (e: MouseEvent) => {
      if (dragRef.current && !dragRef.current.moved) {
        onNodeClickRef.current?.(dragRef.current.nodeId);
      }
      dragRef.current = null;

      if (labelClickRef.current) {
        const { nodeId, startClientX, startClientY } = labelClickRef.current;
        const dx = e.clientX - startClientX;
        const dy = e.clientY - startClientY;
        if (Math.abs(dx) <= CLICK_MOVE_THRESHOLD_PX && Math.abs(dy) <= CLICK_MOVE_THRESHOLD_PX) {
          onNodeClickRef.current?.(nodeId);
        }
        labelClickRef.current = null;
      }
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const handleNodeMouseDown = (e: React.MouseEvent, nodeId: string) => {
    e.preventDefault();
    // Stop this from reaching d3-zoom's own native mousedown listener,
    // bound directly on the <svg> (when zoomable), which would otherwise
    // also start a pan-drag for the same gesture. Must be a CAPTURE-phase
    // handler (see onMouseDownCapture below) — d3-zoom's listener sits on an
    // ancestor and fires during the native bubble phase, which completes
    // before React's own (bubble-phase, root-delegated) dispatch would ever
    // call stopPropagation here; only stopping it during capture, before the
    // event reaches that ancestor at all, actually prevents it (2026-08-01,
    // found via testing: dragging a node was panning the canvas instead).
    e.stopPropagation();
    const node = graphRef.current?.nodes.find(
      n => (n as LayoutNode & NodeDatum).id === nodeId,
    ) as (LayoutNode & NodeDatum) | undefined;
    if (!node) return;
    dragRef.current = {
      nodeId,
      startClientX: e.clientX,
      startClientY: e.clientY,
      startY0: node.y0 ?? 0,
      startY1: node.y1 ?? 0,
      moved: false,
    };
  };

  const handleLabelMouseDownCapture = (e: React.MouseEvent, nodeId: string) => {
    e.preventDefault();
    // Same capture-phase requirement as handleNodeMouseDown above (see its
    // comment) — must stop the mousedown before it reaches d3-zoom's
    // ancestor listener, or clicking a label would also start a canvas pan.
    e.stopPropagation();
    labelClickRef.current = { nodeId, startClientX: e.clientX, startClientY: e.clientY };
  };

  // --- Render ---
  const graph = graphRef.current;
  void graphVersion;

  const {
    size_w, size_h,
    margin_t, margin_b,
    bg_color, bg_transparent,
    node_w: nodeWidth, node_border,
    labels_color, labels_hide, labels_highlight,
    labels_fontface,
    labelname_appears, labelname_size, labelname_weight,
    labelvalue_appears, labelvalue_position,
    labelvalue_fullprecision,
    value_format, value_prefix, value_suffix,
    labels_linespacing,
  } = settings;

  // fitToContainer: let the browser scale the whole viewBox to fit whatever
  // box the SVG sits in, instead of forcing literal size_w x size_h pixels.
  // scrollable: the opposite — no CSS size cap at all, so the SVG stays at
  // its literal (often large) pixel size and the parent panel scrolls to it.
  const svgSizeStyle: React.CSSProperties = fitToContainer
    ? { display: 'block', width: '100%', height: '100%' }
    : scrollable
      ? { display: 'block' }
      : { display: 'block', maxWidth: '100%', maxHeight: '100%' };

  const emptyDiagram = (
    <svg
      ref={setSvgNode}
      data-testid="sankey-diagram"
      width={size_w}
      height={size_h}
      viewBox={`0 0 ${size_w} ${size_h}`}
      preserveAspectRatio="xMidYMid meet"
      style={svgSizeStyle}
      xmlns="http://www.w3.org/2000/svg"
    >
      {!bg_transparent && <rect width={size_w} height={size_h} fill={bg_color} />}
      <text
        x={size_w / 2} y={size_h / 2}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={14} fill="#999" fontFamily="sans-serif"
      >
        Add flows in the input panel to get started
      </text>
    </svg>
  );

  if (!graph) return emptyDiagram;

  const { nodes: layoutNodes, links: layoutLinks } = graph;

  // Ribbons used to be a stroked centerline (fill="none", strokeWidth =
  // link.width) via d3-sankey's own sankeyLinkHorizontal(). That works for
  // thin flows, but once strokeWidth vastly exceeds the curve's own
  // geometric scale (e.g. a ~400px-wide ribbon over a few hundred px of
  // horizontal travel — routine for a big section like Home), the browser
  // has to offset the centerline by ±width/2 to turn the stroke into a
  // fillable shape, and those offset curves can self-intersect, rendering
  // as a hole/white gap punched through the middle of the ribbon (2026-07-31,
  // user-reported: "white void where a purple ribbon is expected"). Building
  // the band explicitly as a closed fill polygon (top edge out, bottom edge
  // back) sidesteps stroke-offset math entirely — this is how every
  // production Sankey renderer (d3's own gallery examples included) draws
  // ribbons thicker than a hairline.
  function ribbonPath(link: LayoutLink & LinkDatum): string {
    const source = link.source as LayoutNode & NodeDatum;
    const target = link.target as LayoutNode & NodeDatum;
    const x0 = source.x1 ?? 0;
    const x1 = target.x0 ?? 0;
    const y0 = (link as unknown as { y0: number }).y0 ?? 0;
    const y1 = (link as unknown as { y1: number }).y1 ?? 0;
    const w = Math.max(1, (link as unknown as { width: number }).width ?? 1);
    const xm = (x0 + x1) / 2;
    const y0Top = y0 - w / 2, y0Bot = y0 + w / 2;
    const y1Top = y1 - w / 2, y1Bot = y1 + w / 2;
    return `M${x0},${y0Top}C${xm},${y0Top} ${xm},${y1Top} ${x1},${y1Top}` +
      `L${x1},${y1Bot}C${xm},${y1Bot} ${xm},${y0Bot} ${x0},${y0Bot}Z`;
  }

  const nameFontSize = labelname_size;
  const valueFontSize = nameFontSize;
  const lineGap = nameFontSize * (1 + (labels_linespacing ?? 0.15));

  function getLabelSide(node: LayoutNode): 'right' | 'left' {
    const cx = ((node.x0 ?? 0) + (node.x1 ?? 0)) / 2;
    return cx < size_w / 2 ? 'right' : 'left';
  }

  // Label collision avoidance: node RECTANGLES stay at their proportional
  // (value-driven) y0/y1 — that's core Sankey semantics and must not
  // change. But adjacent small-value nodes can have rectangle centers only
  // a few pixels apart while their TEXT labels need ~20-40px of vertical
  // room each, which is what actually caused the overlapping-labels bug
  // (2026-07-31). Decouple label position from rect position: group nodes
  // by column, and within each column push overlapping labels apart to the
  // minimum spacing their (possibly two-line) content needs.
  const declutteredLabelY = new Map<string, number>();
  {
    const byColumn = new Map<number, (LayoutNode & NodeDatum)[]>();
    for (const node of layoutNodes) {
      const nd = node as LayoutNode & NodeDatum;
      const col = (nd as unknown as { depth?: number }).depth ?? Math.round(nd.x0 ?? 0);
      if (!byColumn.has(col)) byColumn.set(col, []);
      byColumn.get(col)!.push(nd);
    }
    for (const colNodes of byColumn.values()) {
      const items = colNodes.map(nd => {
        const y0 = nd.y0 ?? 0;
        const y1 = nd.y1 ?? y0;
        // Values now always render (2026-08-01, user-specified: "see all
        // values for every node"), so every label needs the taller 2-line
        // allowance, not just nodes that happened to be big enough before.
        const showsValue = labelvalue_appears;
        // +6px buffer beyond the label's own text height — packing to the
        // exact minimum still reads as cramped even with zero literal
        // overlap (2026-07-31, user-specified minimum padding).
        return { id: nd.id, y: (y0 + y1) / 2, height: (showsValue ? 2.0 : 1.2) * lineGap + 6 };
      });
      const resolved = declutterPositions(items, margin_t + lineGap / 2, size_h - margin_b - lineGap / 2);
      for (const [id, y] of resolved) declutteredLabelY.set(id, y);
    }
  }

  const diagramSvg = (
    <svg
      ref={setSvgNode}
      data-testid="sankey-diagram"
      width={size_w}
      height={size_h}
      viewBox={`0 0 ${size_w} ${size_h}`}
      preserveAspectRatio="xMidYMid meet"
      style={svgSizeStyle}
      xmlns="http://www.w3.org/2000/svg"
    >
      {!bg_transparent && <rect width={size_w} height={size_h} fill={bg_color} />}

      {/* Pan/zoom transform — identity (0,0,1) when zoomable is off, so this
          is a no-op wrapper in that case. Background rect and the
          sankeymatic.com watermark sit outside it so they stay fixed to the
          viewport instead of panning away with the content. */}
      <g transform={`translate(${zoomTransform.x},${zoomTransform.y}) scale(${zoomTransform.k})`}>

      {/* Links */}
      <g>
        {layoutLinks.map((link) => {
          const ld = link as LayoutLink & LinkDatum;
          const srcId = typeof ld.source === 'object' ? (ld.source as LayoutNode & NodeDatum).id : String(ld.source);
          const tgtId = typeof ld.target === 'object' ? (ld.target as LayoutNode & NodeDatum).id : String(ld.target);
          return (
            <path
              key={`${srcId}->${tgtId}`}
              d={ribbonPath(ld)}
              fill={ld.color ?? '#999999'}
              fillOpacity={ld.opacity ?? 0.45}
              stroke="none"
            />
          );
        })}
      </g>

      {/* Nodes */}
      <g>
        {layoutNodes.map(node => {
          const nd = node as LayoutNode & NodeDatum;
          const x0 = node.x0 ?? 0;
          const y0 = node.y0 ?? 0;
          const x1 = node.x1 ?? x0 + nodeWidth;
          const y1 = node.y1 ?? y0;
          return (
            <rect
              key={nd.id}
              x={x0}
              y={y0}
              width={x1 - x0}
              height={Math.max(1, y1 - y0)}
              fill={nd.color}
              fillOpacity={nd.opacity}
              stroke={node_border > 0 ? '#000000' : 'none'}
              strokeWidth={node_border > 0 ? node_border : 0}
              strokeOpacity={0.5}
              style={{ cursor: 'grab' }}
              onMouseDownCapture={e => handleNodeMouseDown(e, nd.id)}
            />
          );
        })}
      </g>

      {/* Labels */}
      {!labels_hide && (
        <g fontFamily={labels_fontface}>
          {layoutNodes.map(node => {
            const nd = node as LayoutNode & NodeDatum;
            const x0 = node.x0 ?? 0;
            const y0 = node.y0 ?? 0;
            const x1 = node.x1 ?? x0 + nodeWidth;
            const y1 = node.y1 ?? y0;
            const midY = (y0 + y1) / 2;
            const side = getLabelSide(node);
            const textX = side === 'right' ? x1 + 6 : x0 - 6;
            const anchor = side === 'right' ? 'start' : 'end';

            const nameDisplay = nd.name.replace(/\n/g, ' / ');
            const valueDisplay = formatValue(
              node.value ?? 0,
              value_format,
              value_prefix,
              value_suffix,
              labelvalue_fullprecision,
            );

            // Both labels sit beside the node, not inside it, so node height
            // doesn't gate them — every node shows its value regardless of
            // how thin its ribbon is (2026-08-01, user-specified: "see all
            // values for every node").
            const showName = labelname_appears;
            const showValue = labelvalue_appears;

            if (!showName && !showValue) return null;

            // Decluttered position (see the label-collision-avoidance pass
            // above) replaces the node's raw rect midpoint as the label's
            // anchor — the rect itself never moves.
            const labelCenterY = declutteredLabelY.get(nd.id) ?? midY;
            const labelOffset = labelCenterY - midY;

            let nameY = labelCenterY;
            let valueY = labelCenterY;
            if (showName && showValue) {
              if (labelvalue_position === 'below') {
                nameY = labelCenterY - lineGap * 0.3;
                valueY = labelCenterY + lineGap * 0.7;
              } else if (labelvalue_position === 'above') {
                nameY = labelCenterY + lineGap * 0.3;
                valueY = labelCenterY - lineGap * 0.7;
              }
            }

            return (
              <g
                key={nd.id}
                style={{
                  // pointerEvents stays 'none' unless a caller opted into
                  // onNodeClick — the Sankey Builder tool renders this same
                  // component with no click behavior at all, and labels must
                  // stay click-through there exactly as before.
                  pointerEvents: onNodeClick ? 'auto' : 'none',
                  cursor: onNodeClick ? 'pointer' : undefined,
                }}
                onMouseDownCapture={onNodeClick ? (e => handleLabelMouseDownCapture(e, nd.id)) : undefined}
              >
                {Math.abs(labelOffset) > 3 && (
                  <line
                    x1={side === 'right' ? x1 : x0}
                    y1={midY}
                    x2={side === 'right' ? x1 : x0}
                    y2={labelCenterY}
                    stroke={labels_color}
                    strokeOpacity={0.3}
                    strokeWidth={1}
                  />
                )}
                {showName && (
                  <>
                    <text
                      x={textX} y={nameY}
                      textAnchor={anchor} dominantBaseline="middle"
                      fontSize={nameFontSize} fontWeight={labelname_weight}
                      fill={bg_transparent ? 'none' : bg_color}
                      stroke={bg_transparent ? 'none' : bg_color}
                      strokeWidth={3} strokeLinejoin="round"
                      paintOrder="stroke"
                      fillOpacity={labels_highlight}
                      style={{ userSelect: 'none' }}
                    >
                      {nameDisplay}
                    </text>
                    <text
                      x={textX} y={nameY}
                      textAnchor={anchor} dominantBaseline="middle"
                      fontSize={nameFontSize} fontWeight={labelname_weight}
                      fill={labels_color}
                      style={{ userSelect: 'none' }}
                    >
                      {nameDisplay}
                    </text>
                  </>
                )}
                {showValue && (
                  <>
                    <text
                      x={textX} y={valueY}
                      textAnchor={anchor} dominantBaseline="middle"
                      fontSize={valueFontSize} fontWeight={labelname_weight}
                      fill={bg_transparent ? 'none' : bg_color}
                      stroke={bg_transparent ? 'none' : bg_color}
                      strokeWidth={3} strokeLinejoin="round"
                      paintOrder="stroke"
                      fillOpacity={labels_highlight}
                      style={{ userSelect: 'none' }}
                    >
                      {valueDisplay}
                    </text>
                    <text
                      x={textX} y={valueY}
                      textAnchor={anchor} dominantBaseline="middle"
                      fontSize={valueFontSize} fontWeight={labelname_weight}
                      fill={labels_color} fillOpacity={0.8}
                      style={{ userSelect: 'none' }}
                    >
                      {valueDisplay}
                    </text>
                  </>
                )}
              </g>
            );
          })}
        </g>
      )}
      </g>

      {settings.meta_mentionwebsite && (
        <text
          x={size_w - 4} y={size_h - 4}
          textAnchor="end" fontSize={9}
          fill={labels_color} fillOpacity={0.35}
          fontFamily={labels_fontface}
        >
          sankeymatic.com
        </text>
      )}
    </svg>
  );

  if (!zoomable) return diagramSvg;

  // Opaque either way (not translucent) so it's legible regardless of what's
  // underneath, but paired light/dark since the canvas itself can now be
  // black in dark mode (2026-08-01) — a light-only opaque square would sit
  // on a black canvas like a stray sticky note.
  const zoomBtnClass =
    'w-7 h-7 flex items-center justify-center rounded bg-white hover:bg-gray-100 text-gray-700 border-gray-300 ' +
    'dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 dark:border-gray-600 ' +
    'text-sm font-bold shadow border select-none';

  return (
    <div style={{ position: 'relative', display: fitToContainer ? 'block' : 'inline-block', width: fitToContainer ? '100%' : undefined, height: fitToContainer ? '100%' : undefined }}>
      {diagramSvg}
      {/* First iteration (2026-08-01): pinned to the diagram's own top-right
          corner, so it scrolls away with tall content rather than staying
          fixed in the viewport — a real limitation, but keeping controls
          bound to the diagram itself avoids more invasive plumbing (an
          imperative ref out to whichever parent panel is scrolling). Opaque
          background so it's still fully legible on whatever label happens
          to render underneath, since the corner isn't guaranteed empty. */}
      <div style={{ position: 'absolute', top: 8, right: 8 }} className="flex flex-col gap-1 z-10">
        <button type="button" className={zoomBtnClass} onClick={() => zoomBy(1.3)} title="Zoom in">+</button>
        <button type="button" className={zoomBtnClass} onClick={() => zoomBy(1 / 1.3)} title="Zoom out">−</button>
        <button type="button" className={zoomBtnClass} onClick={resetZoom} title="Reset zoom/pan">⤢</button>
        {/* Undoes any manually dragged node positions (see
            handleNodeMouseDown/onMove above, which mutate the layout
            in-place) and re-centers the view — nothing else resets a
            drag within the same month/settings otherwise
            (2026-08-02, user-requested). */}
        <button type="button" className={zoomBtnClass} onClick={() => { recomputeLayout(); resetZoom(); }} title="Reset layout (undo dragged nodes)">⟲</button>
      </div>
    </div>
  );
};

export default SankeyDiagram;
