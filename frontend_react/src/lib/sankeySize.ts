import type { FlowLine } from '../types';

// The dashboard's Sankey diagram has far more nodes than the Sankey
// Builder's hand-typed examples (WAGES/TAXES/HOUSING style, a handful of
// nodes) — dozens of line items stacked in the rightmost column. The fixed
// 600x600 default squishes them close enough that labels overlap. Size the
// canvas from the actual graph shape instead: tall enough that the busiest
// column's nodes get real breathing room, wide enough for every BFS depth
// level (source -> Budget -> section -> line item) to have its own lane.
// Actual overlap avoidance is now SankeyDiagram.tsx's label-declutter pass
// (lib/labelDeclutter.ts), which guarantees non-overlapping labels within
// whatever size_h it's given. This sizing only needs to supply "enough"
// room for that pass to work with reasonable label density — it doesn't
// need to be generous enough to solve overlap by brute force alone anymore.
// The dashboard renders these at literal pixel size and scrolls its panel
// to fit (see BudgetDashboard's `scrollable` SankeyDiagram), so there's no
// shrink-to-fit tax on going tall/wide — the caps below just guard against
// a pathological input producing an unusably huge canvas.
// Bumped from 50 (2026-08-02, user-reported: "the layout needs even more
// vertical space" — the busiest column's nodes still read as cramped even
// after the panel-fill fix, since PX_PER_NODE sets the floor each node's
// label needs, not just the container's overall height). MAX_HEIGHT raised
// by the same ~30% so the increase doesn't immediately run back into the
// cap on an already-busy month.
const PX_PER_NODE = 65; // headroom per node in the busiest column
const PX_PER_LEVEL = 240; // link span + label text width per depth level
const MIN_SIZE = 600;
const MAX_HEIGHT = 5200;
const MAX_WIDTH = 2200;
const MARGIN = 60;

export function computeSankeySize(
  flows: FlowLine[],
  // Actual measured size of the panel the diagram will sit in. Node-count
  // sizing alone left real, empty gutter whenever a month's graph was
  // smaller than its panel (e.g. a quiet month with few line items in a
  // wide window) — the diagram should fill the space it's given as a floor,
  // and only exceed it (triggering the panel's own scroll) when there are
  // enough nodes to actually need more room (2026-08-01, user-specified:
  // "must fill the parent container so that there isn't unused negative
  // space"). Omitted by the Sankey Builder tool, which has its own
  // literal-pixel-size contract (export dimensions, size readout) that must
  // not silently grow to fill its canvas panel.
  minSize?: { width: number; height: number },
): { size_w: number; size_h: number } {
  const minW = minSize?.width ?? MIN_SIZE;
  const minH = minSize?.height ?? MIN_SIZE;

  const nodes = new Set<string>();
  const outgoing = new Map<string, string[]>();
  const hasIncoming = new Set<string>();

  for (const f of flows) {
    if (typeof f.amount !== 'number' || f.amount <= 0) continue;
    if (f.source === f.target) continue;
    nodes.add(f.source);
    nodes.add(f.target);
    hasIncoming.add(f.target);
    if (!outgoing.has(f.source)) outgoing.set(f.source, []);
    outgoing.get(f.source)!.push(f.target);
  }

  if (nodes.size === 0) return { size_w: minW, size_h: minH };

  // Longest-path depth from root nodes (no incoming edge) — matches the
  // diagram's default sankeyLeft alignment, where nodes sit at their
  // natural source-side depth rather than being justified to one edge.
  const depth = new Map<string, number>();
  const queue: string[] = [];
  for (const n of nodes) {
    if (!hasIncoming.has(n)) {
      depth.set(n, 0);
      queue.push(n);
    }
  }
  // Every node has an incoming edge (a cycle, or malformed input) — seed
  // everything at depth 0 rather than never entering the BFS below.
  if (queue.length === 0) {
    for (const n of nodes) {
      depth.set(n, 0);
      queue.push(n);
    }
  }

  let qi = 0;
  while (qi < queue.length) {
    const node = queue[qi++];
    const d = depth.get(node) ?? 0;
    for (const next of outgoing.get(node) ?? []) {
      const nd = depth.get(next);
      if (nd === undefined || nd < d + 1) {
        depth.set(next, d + 1);
        queue.push(next);
      }
    }
  }

  const nodesByLevel = new Map<number, number>();
  let maxLevel = 0;
  for (const n of nodes) {
    const d = depth.get(n) ?? 0;
    nodesByLevel.set(d, (nodesByLevel.get(d) ?? 0) + 1);
    maxLevel = Math.max(maxLevel, d);
  }
  const maxNodesInLevel = Math.max(...nodesByLevel.values());
  const numLevels = maxLevel + 1;

  // Bug (2026-08-01): this used the hardcoded MIN_SIZE constant here instead
  // of the minW/minH computed from the caller's measured panel size above —
  // minSize was applied correctly in the empty-diagram early return, but
  // silently ignored for every real diagram, so the panel-fill fix never
  // actually took effect outside the empty case. That's why a real month's
  // diagram kept leaving a wide empty gutter instead of filling its panel.
  return {
    size_h: Math.min(MAX_HEIGHT, Math.max(minH, maxNodesInLevel * PX_PER_NODE + MARGIN)),
    size_w: Math.min(MAX_WIDTH, Math.max(minW, numLevels * PX_PER_LEVEL)),
  };
}
