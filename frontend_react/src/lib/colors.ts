import type { SkmSettings, FlowLine, NodeDef } from '../types';

// D3 color schemes
// Theme a = schemeSet1 (9 colors)
const schemeSet1 = [
  '#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00',
  '#ffff33', '#a65628', '#f781bf', '#999999',
];
// Theme b = schemeSet2 (8 colors)
const schemeSet2 = [
  '#66c2a5', '#fc8d62', '#8da0cb', '#e78ac3', '#a6d854',
  '#ffd92f', '#e5c494', '#b3b3b3',
];
// Theme c = schemePastel1 (9 colors)
const schemePastel1 = [
  '#fbb4ae', '#b3cde3', '#ccebc5', '#decbe4', '#fed9a6',
  '#ffffcc', '#e5d8bd', '#fddaec', '#f2f2f2',
];
// Theme d = schemePastel2 (8 colors, but d3 has 8)
const schemePastel2 = [
  '#b3e2cd', '#fdcdac', '#cbd5e8', '#f4cae4', '#e6f5c9',
  '#fff2ae', '#f1e2cc', '#cccccc',
];

const themeColors: Record<string, string[]> = {
  a: schemeSet1,
  b: schemeSet2,
  c: schemePastel1,
  d: schemePastel2,
};

const themeMaxOffsets: Record<string, number> = {
  a: 9,
  b: 9,
  c: 7,
  d: 11,
};

// BFS to compute the topological "stage" (column depth) of each node.
// Origins (no incoming flows) are stage 0; their targets are stage 1, etc.
export function computeNodeStages(
  nodeNames: string[],
  flows: FlowLine[],
): { stages: Map<string, number>; maxStage: number } {
  const hasIncoming = new Set<string>();
  const outEdges = new Map<string, string[]>();

  for (const f of flows) {
    if (typeof f.amount !== 'number' || (f.amount as number) <= 0) continue;
    const src = f.source;
    const tgt = f.target;
    hasIncoming.add(tgt);
    if (!outEdges.has(src)) outEdges.set(src, []);
    outEdges.get(src)!.push(tgt);
  }

  const stages = new Map<string, number>();
  const queue: string[] = [];

  for (const name of nodeNames) {
    if (!hasIncoming.has(name)) {
      stages.set(name, 0);
      queue.push(name);
    }
  }

  // BFS — assign stage = max(parent stage + 1)
  let head = 0;
  while (head < queue.length) {
    const node = queue[head++];
    const stage = stages.get(node)!;
    for (const neighbor of (outEdges.get(node) ?? [])) {
      const existing = stages.get(neighbor) ?? -1;
      if (stage + 1 > existing) {
        stages.set(neighbor, stage + 1);
        queue.push(neighbor);
      }
    }
  }

  // Fill in any disconnected nodes
  for (const name of nodeNames) {
    if (!stages.has(name)) stages.set(name, 0);
  }

  const maxStage = Math.max(0, ...Array.from(stages.values()));
  return { stages, maxStage };
}

// Generate a visually pleasing, consistent color from a node name.
// stage/maxStage bias the hue: 0 = green/teal, 1 = pink/purple.
export function colorFromName(name: string, stage = 0, maxStage = 1): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = Math.imul(31, hash) + name.charCodeAt(i) | 0;
  }
  // Stage-biased hue: stage 0 → ~160° (teal/green), stage max → ~320° (pink/purple)
  const t = maxStage > 0 ? stage / maxStage : 0;
  const hueCenter = 160 + t * 160;
  const hueVariation = ((hash >>> 0) % 61) - 30; // ±30°
  const h = ((hueCenter + hueVariation) % 360 + 360) % 360;
  const s = 40 + ((hash >>> 8) % 20);   // 40–60%
  const l = 65 + ((hash >>> 16) % 15);  // 65–80%
  // Convert HSL → hex
  const hn = h / 360, sn = s / 100, ln = l / 100;
  const q = ln < 0.5 ? ln * (1 + sn) : ln + sn - ln * sn;
  const p = 2 * ln - q;
  const toRgb = (t: number) => {
    const t1 = ((t % 1) + 1) % 1;
    if (t1 < 1 / 6) return p + (q - p) * 6 * t1;
    if (t1 < 1 / 2) return q;
    if (t1 < 2 / 3) return p + (q - p) * (2 / 3 - t1) * 6;
    return p;
  };
  const r = Math.round(toRgb(hn + 1 / 3) * 255);
  const g = Math.round(toRgb(hn) * 255);
  const b = Math.round(toRgb(hn - 1 / 3) * 255);
  return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('');
}

// Expand 3-char hex to 6-char hex
export function expandHex(hex: string): string {
  const h = hex.replace('#', '');
  if (h.length === 3) {
    return '#' + h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  }
  return hex.startsWith('#') ? hex : '#' + hex;
}

// Convert hex color + opacity to rgba
export function hexToRgba(hex: string, opacity: number): string {
  const full = expandHex(hex);
  const r = parseInt(full.slice(1, 3), 16);
  const g = parseInt(full.slice(3, 5), 16);
  const b = parseInt(full.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${opacity})`;
}

export interface NodeColorMap {
  color: string;    // hex
  opacity: number;  // 0-1
}

export function resolveNodeColors(
  nodeNames: string[],
  nodeDefs: Map<string, NodeDef>,
  settings: SkmSettings,
  flows: FlowLine[]
): Map<string, NodeColorMap> {
  const result = new Map<string, NodeColorMap>();

  const theme = settings.node_theme;
  const themeArr = theme !== 'none' ? themeColors[theme] : null;
  const themeOffset = theme !== 'none'
    ? ((settings as unknown as Record<string, number>)[`themeoffset_${theme}`]) || 0
    : 0;

  // Compute stages only when using the default color scheme (no theme)
  const { stages, maxStage } = themeArr
    ? { stages: new Map<string, number>(), maxStage: 1 }
    : computeNodeStages(nodeNames, flows);

  nodeNames.forEach((name, idx) => {
    const def = nodeDefs.get(name);

    // Explicit color definition takes priority
    if (def?.color) {
      result.set(name, {
        color: expandHex(def.color),
        opacity: def.opacity ?? settings.node_opacity,
      });
      return;
    }

    // Theme color
    if (themeArr) {
      const maxOffset = themeMaxOffsets[theme] || themeArr.length - 1;
      const colorIdx = (idx + themeOffset) % themeArr.length;
      result.set(name, {
        color: themeArr[colorIdx],
        opacity: settings.node_opacity,
      });
      return;
    }

    // Default: derive a stage-biased consistent color from the node name
    const stage = stages.get(name) ?? 0;
    result.set(name, {
      color: colorFromName(name, stage, maxStage),
      opacity: settings.node_opacity,
    });
  });

  return result;
}

export function resolveFlowColor(
  flow: FlowLine,
  nodeColors: Map<string, NodeColorMap>,
  settings: SkmSettings,
  origins: Set<string>,
  endpoints: Set<string>
): { color: string; opacity: number } {
  const inheritFrom = settings.flow_inheritfrom;
  const defaultColor = expandHex(settings.flow_color);
  const defaultOpacity = settings.flow_opacity;

  // Explicit flow color overrides everything
  if (flow.color) {
    return {
      color: expandHex(flow.color),
      opacity: flow.opacity ?? defaultOpacity,
    };
  }

  if (inheritFrom === 'source') {
    const nc = nodeColors.get(flow.source);
    return { color: nc?.color || defaultColor, opacity: nc?.opacity ?? defaultOpacity };
  }

  if (inheritFrom === 'target') {
    const nc = nodeColors.get(flow.target);
    return { color: nc?.color || defaultColor, opacity: nc?.opacity ?? defaultOpacity };
  }

  if (inheritFrom === 'outside-in') {
    // Origins (no incoming) use source node color
    if (origins.has(flow.source)) {
      const nc = nodeColors.get(flow.source);
      return { color: nc?.color || defaultColor, opacity: nc?.opacity ?? defaultOpacity };
    }
    // Endpoints (no outgoing) use target node color
    if (endpoints.has(flow.target)) {
      const nc = nodeColors.get(flow.target);
      return { color: nc?.color || defaultColor, opacity: nc?.opacity ?? defaultOpacity };
    }
    // Middle flows use source color
    const nc = nodeColors.get(flow.source);
    return { color: nc?.color || defaultColor, opacity: nc?.opacity ?? defaultOpacity };
  }

  // 'none' - use default flow color
  return { color: defaultColor, opacity: defaultOpacity };
}
