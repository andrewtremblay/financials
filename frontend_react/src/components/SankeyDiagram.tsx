import React, { useEffect, useRef, useState } from 'react';
import {
  sankey as d3Sankey,
  sankeyLinkHorizontal,
  sankeyLeft,
  sankeyRight,
  sankeyCenter,
  sankeyJustify,
  SankeyNode as D3SankeyNode,
  SankeyLink as D3SankeyLink,
  SankeyGraph,
} from 'd3-sankey';
import type { SkmSettings, FlowLine, NodeDef } from '../types';
import { resolveNodeColors, resolveFlowColor, expandHex } from '../lib/colors';
import { getOrigins, getEndpoints, resolveAmounts } from '../lib/parser';
import { formatValue } from '../lib/format';

interface Props {
  flows: FlowLine[];
  nodeDefs: Map<string, NodeDef>;
  settings: SkmSettings;
  svgRef?: React.RefObject<SVGSVGElement>;
}

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
    const minGap = 8;

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

    // Position each column: nodes sorted by d3-sankey order, gaps distributed evenly.
    for (const colNodes of byColumn.values()) {
      colNodes.sort((a, b) => (a.y0 ?? 0) - (b.y0 ?? 0));
      const n = colNodes.length;
      const heights = colNodes.map(
        nd => Math.max(1, ((nd as unknown as { value: number }).value ?? 0) * ky),
      );
      const totalNodeH = heights.reduce((a, b) => a + b, 0);
      const gap = n > 1 ? Math.max(minGap, (availableH - totalNodeH) / (n - 1)) : 0;
      let y = margin_t;
      for (let i = 0; i < n; i++) {
        colNodes[i].y0 = y;
        colNodes[i].y1 = y + heights[i];
        y += heights[i] + gap;
      }
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
}


const SankeyDiagram: React.FC<Props> = ({ flows, nodeDefs, settings, svgRef }) => {
  const [graphVersion, setGraphVersion] = useState(0);
  const graphRef = useRef<SankeyGraph<NodeDatum, LinkDatum> | null>(null);
  const generatorRef = useRef<SankeyGen | null>(null);

  const settingsRef = useRef(settings);
  useEffect(() => { settingsRef.current = settings; }, [settings]);

  const dragRef = useRef<{
    nodeId: string;
    startClientY: number;
    startY0: number;
    startY1: number;
  } | null>(null);

  useEffect(() => {
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

  // Global drag listeners (registered once).
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragRef.current || !graphRef.current || !generatorRef.current) return;
      const { nodeId, startClientY, startY0, startY1 } = dragRef.current;
      const dy = e.clientY - startClientY;

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

    const onUp = () => { dragRef.current = null; };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const handleNodeMouseDown = (e: React.MouseEvent, nodeId: string) => {
    e.preventDefault();
    const node = graphRef.current?.nodes.find(
      n => (n as LayoutNode & NodeDatum).id === nodeId,
    ) as (LayoutNode & NodeDatum) | undefined;
    if (!node) return;
    dragRef.current = {
      nodeId,
      startClientY: e.clientY,
      startY0: node.y0 ?? 0,
      startY1: node.y1 ?? 0,
    };
  };

  // --- Render ---
  const graph = graphRef.current;
  void graphVersion;

  const {
    size_w, size_h,
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

  const emptyDiagram = (
    <svg
      ref={svgRef}
      width={size_w}
      height={size_h}
      viewBox={`0 0 ${size_w} ${size_h}`}
      style={{ display: 'block' }}
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
  const linkPath = sankeyLinkHorizontal();

  const nameFontSize = labelname_size;
  const valueFontSize = nameFontSize;
  const lineGap = nameFontSize * (1 + (labels_linespacing ?? 0.15));

  function getLabelSide(node: LayoutNode): 'right' | 'left' {
    const cx = ((node.x0 ?? 0) + (node.x1 ?? 0)) / 2;
    return cx < size_w / 2 ? 'right' : 'left';
  }

  return (
    <svg
      ref={svgRef}
      width={size_w}
      height={size_h}
      viewBox={`0 0 ${size_w} ${size_h}`}
      style={{ display: 'block', maxWidth: '100%', maxHeight: '100%' }}
      xmlns="http://www.w3.org/2000/svg"
    >
      {!bg_transparent && <rect width={size_w} height={size_h} fill={bg_color} />}

      {/* Links */}
      <g>
        {layoutLinks.map((link, i) => {
          const ld = link as LayoutLink & LinkDatum;
          const d = linkPath(link as Parameters<typeof linkPath>[0]);
          return (
            <path
              key={i}
              d={d ?? ''}
              fill="none"
              stroke={ld.color ?? '#999999'}
              strokeOpacity={ld.opacity ?? 0.45}
              strokeWidth={Math.max(1, link.width ?? 1)}
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
              onMouseDown={e => handleNodeMouseDown(e, nd.id)}
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

            const nodeH = y1 - y0;
            // Always show the name label — it sits beside the node, not inside it.
            // Only suppress the value sub-label when the node is too small for two lines.
            const showName = labelname_appears;
            const showValue = labelvalue_appears && nodeH >= lineGap * 1.5;

            if (!showName && !showValue) return null;

            let nameY = midY;
            let valueY = midY;
            if (showName && showValue) {
              if (labelvalue_position === 'below') {
                nameY = midY - lineGap * 0.3;
                valueY = midY + lineGap * 0.7;
              } else if (labelvalue_position === 'above') {
                nameY = midY + lineGap * 0.3;
                valueY = midY - lineGap * 0.7;
              }
            }

            return (
              <g key={nd.id} style={{ pointerEvents: 'none' }}>
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
};

export default SankeyDiagram;
