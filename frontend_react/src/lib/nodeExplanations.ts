import { EXPANSION_SEPARATOR } from './sankeyExpansion';

// Explanation text for Sankey diagram nodes that don't correspond to a real
// LineItem — clicking one of these can't open the transactions drawer (there
// are no transactions to show), so it opens an explanation modal instead
// (2026-08-01, user-requested, prompted by "Untracked Income" showing up
// with no obvious meaning on click).

export interface NodeExplanation {
  title: string;
  body: string;
}

// Keep this prose in sync with the actual logic in budget_sankeymatic.py —
// these are user-facing descriptions of real behavior, not independent
// copy, so a change to the underlying rule (e.g. which labels count as
// "untracked income") should update both places together.
const STATIC_EXPLANATIONS: Record<string, NodeExplanation> = {
  Budget: {
    title: 'Budget',
    body: "The central hub for this month's money — every income source flows in here, and everything spent or saved flows back out. It's all of your available money for the month, in one place.",
  },
  'Untracked Income': {
    title: 'Untracked Income',
    body: "Some savings contributions never show up as tracked take-home income in the first place: 401(k) and pension contributions are deducted pre-tax, and a couple of items (Emergency Fund, Managed Brokerages) are split directly out of the paycheck before it ever reaches a tracked account. This flow adds that money back as income so it doesn't count as overspending — it was never available to spend to begin with, so leaving it out entirely would make Overspending look artificially worse than it really is.",
  },
  Overspending: {
    title: 'Overspending',
    body: 'This month, expenses and savings together added up to more than tracked income. This flow makes up the difference so the diagram balances — read it as a warning, not free money.',
  },
  Underspending: {
    title: 'Underspending',
    body: 'This month, tracked income was more than what was spent and saved combined. This flow represents that leftover amount, shown so the diagram balances.',
  },
  Needs: {
    title: 'Needs',
    body: 'Every expense line item tagged "Need" this month, added together — shown when the diagram is grouped by classification instead of by section. Edit which line items count as a Need vs. a Want from the Budget Rules tab ("Edit Need/Want classification").',
  },
  Wants: {
    title: 'Wants',
    body: 'Every expense line item tagged "Want" this month, added together — shown when the diagram is grouped by classification instead of by section. Edit which line items count as a Need vs. a Want from the Budget Rules tab ("Edit Need/Want classification").',
  },
};

/**
 * Resolves an explanation for a diagram node that isn't a real LineItem —
 * a structural hub (Budget), a balance flow (Overspending/Underspending/
 * Untracked Income), a section rollup (Home, Savings, ...), or (as a
 * fallback only — see below) a sub-category expansion node. Returns null if
 * the node is unrecognized (shouldn't normally happen for a non-LineItem
 * click, but callers should treat null as "no explanation available"
 * rather than assuming one).
 */
export function explainNode(nodeId: string, sectionLabels: ReadonlySet<string>): NodeExplanation | null {
  const staticExplanation = STATIC_EXPLANATIONS[nodeId];
  if (staticExplanation) return staticExplanation;

  if (sectionLabels.has(nodeId)) {
    return {
      title: nodeId,
      body: `The total of every ${nodeId} line item this month, added together. Click an individual item in the sidebar on the left to see the transactions behind it.`,
    };
  }

  // BudgetDashboard's handleSankeyNodeClick normally intercepts sub-category
  // expansion nodes before they ever reach here, opening the parent's own
  // transactions drawer pre-filtered to this category instead (2026-08-02,
  // user-requested: "make this show the same sidebar as the parent... only
  // filtered"). This branch only fires as a fallback if that parent lookup
  // somehow fails (e.g. a stale nodeId from a since-changed month).
  const sepIndex = nodeId.indexOf(EXPANSION_SEPARATOR);
  if (sepIndex !== -1) {
    const parent = nodeId.slice(0, sepIndex);
    const category = nodeId.slice(sepIndex + EXPANSION_SEPARATOR.length);
    return {
      title: nodeId,
      body: `Part of "${parent}", broken out by its underlying transaction category ("${category}"). This detail only appears while ${parent} is expanded — use its +/− toggle in the sidebar to collapse it back into one node.`,
    };
  }

  return null;
}
