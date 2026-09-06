import type { LineItem } from './budget-types';

// Sub-category expansion nodes (below) and NotesDrawer's category filter
// both need to agree on this exact separator and formatting — centralized
// here rather than duplicated (nodeExplanations.ts previously kept its own
// copy of the separator for parsing these node ids back apart).
export const EXPANSION_SEPARATOR = ' — ';

// Turns a raw Plaid-derived category ("E-COMMERCE", "INVESTMENT_METALS")
// into a readable node label ("E Commerce", "Investment Metals").
export function formatCategoryLabel(raw: string): string {
  // A raw category can itself be a legacy "PARENT → SPECIFIC" string — a
  // stray category created through the old free-text "type SECTION →
  // SUBCATEGORY" flow before it was replaced by the Section + subcategory
  // picker (see RecategorizeModal.tsx). Keep only the most specific (last)
  // segment rather than showing the whole thing doubly-nested under its own
  // line item's name (2026-08-02, user-reported: expanding "Other Savings"
  // showed "Other Savings — Savings → James 529", not the clean "James 529"
  // this is supposed to read as).
  const mostSpecific = raw.split(/\s*(?:→|->)\s*/).pop() ?? raw;
  return mostSpecific
    .replace(/[_-]+/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());
}

// Sums each line item's POSITIVE transactions by raw category — mirrors the
// >0 filter budget_sankeymatic.py itself applies everywhere, so the sum of
// sub-category amounts matches the line item's own flow amount exactly (no
// gap/imbalance introduced by expanding).
export function categoryBreakdown(item: LineItem): Map<string, number> {
  const byCategory = new Map<string, number>();
  for (const t of item.transactions) {
    if (t.amount <= 0) continue;
    const cat = t.category ?? 'Uncategorized';
    byCategory.set(cat, (byCategory.get(cat) ?? 0) + t.amount);
  }
  return byCategory;
}

// Only worth expanding when there's actually more than one bucket to reveal
// — a single-category line item would just show one sub-node duplicating
// the same total, which is confusing busywork for the user, not information.
export function isExpandable(item: LineItem): boolean {
  return categoryBreakdown(item).size > 1;
}

// Appends "{nodeId} [{amount}] {nodeId} — {Category}" flow lines for every
// expanded node, turning the line item into a hub with its own sub-nodes —
// the exact same Budget -> Section -> LineItem pattern one level deeper
// (2026-08-01, user-specified: "I want to see the sub-subsections as
// nodes"). Purely additive text manipulation on the server-generated
// Sankeymatic string — no backend round-trip needed, since the full
// per-transaction category detail is already sitting in monthData.
export function expandSankeymaticText(
  baseText: string,
  nodeIdToLineItem: Map<string, LineItem>,
  expandedNodeIds: Set<string>,
): string {
  if (expandedNodeIds.size === 0) return baseText;

  const extraLines: string[] = [];
  for (const nodeId of expandedNodeIds) {
    const item = nodeIdToLineItem.get(nodeId);
    if (!item) continue;
    const breakdown = categoryBreakdown(item);
    if (breakdown.size <= 1) continue;
    for (const [category, amount] of breakdown) {
      extraLines.push(`${nodeId} [${amount.toFixed(2)}] ${nodeId} — ${formatCategoryLabel(category)}`);
    }
  }
  return extraLines.length > 0 ? `${baseText}\n${extraLines.join('\n')}` : baseText;
}
