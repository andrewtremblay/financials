// Greedy label-declutter: given a set of labels' natural (preferred) Y
// positions and how much vertical room each one needs, push overlapping
// labels apart to the minimum spacing required, then clamp the whole group
// back within [minBound, maxBound] without reintroducing overlap. Standard
// two-pass "stack down, then pull up" algorithm (the same approach used in
// most label-avoidance chart examples) — deterministic, no external deps.
//
// Node RECT positions are untouched by this (they still reflect proportional
// dollar value, which is the whole point of a Sankey diagram); only the TEXT
// label's vertical position moves, with a short leader line drawn back to
// the node when it does (see SankeyDiagram.tsx).

export interface DeclutterInput {
  id: string;
  y: number; // natural (preferred) center position
  height: number; // minimum vertical space this label needs
}

export function declutterPositions(items: DeclutterInput[], minBound: number, maxBound: number): Map<string, number> {
  const sorted = [...items].sort((a, b) => a.y - b.y);
  const n = sorted.length;
  const result = sorted.map(d => d.y);

  // Forward pass: push each label down if it's closer to the previous one
  // than their combined half-heights require.
  for (let i = 1; i < n; i++) {
    const minY = result[i - 1] + (sorted[i - 1].height + sorted[i].height) / 2;
    if (result[i] < minY) result[i] = minY;
  }

  // Backward pass: if that pushed the last label past the bottom bound,
  // pull everything back up, re-checking spacing as we go.
  if (n > 0 && result[n - 1] > maxBound) {
    result[n - 1] = maxBound;
    for (let i = n - 2; i >= 0; i--) {
      const maxY = result[i + 1] - (sorted[i].height + sorted[i + 1].height) / 2;
      if (result[i] > maxY) result[i] = maxY;
    }
  }

  // If content still doesn't fit (total required height exceeds the
  // available range), the pass above can push the first label above
  // minBound — clamp it and re-run the forward push once more. At that
  // point labels are as tightly packed as the algorithm allows; true
  // overlap only remains if minBound..maxBound is smaller than the sum of
  // every label's height, which computeSankeySize sizes the canvas to avoid.
  if (n > 0 && result[0] < minBound) {
    result[0] = minBound;
    for (let i = 1; i < n; i++) {
      const minY = result[i - 1] + (sorted[i - 1].height + sorted[i].height) / 2;
      if (result[i] < minY) result[i] = minY;
    }
  }

  const map = new Map<string, number>();
  sorted.forEach((d, i) => map.set(d.id, result[i]));
  return map;
}
