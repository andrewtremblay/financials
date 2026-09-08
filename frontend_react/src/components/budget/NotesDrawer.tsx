import React, { useState } from 'react';
import type { NeedsReviewTransaction, Transaction } from '../../lib/budget-types';
import { formatCategoryLabel } from '../../lib/sankeyExpansion';

interface Props {
  title: string;
  subtitle?: string;
  transactions: (Transaction | NeedsReviewTransaction)[];
  // Shown instead of the generic "No transactions." message when the empty
  // list has a specific, known reason (e.g. a copy-projected or fixed line
  // item — see BudgetDashboard.tsx) — otherwise an empty drawer with no
  // explanation reads as a bug rather than expected behavior.
  emptyExplanation?: string;
  // Pre-selects the category filter below — set when this drawer was
  // opened from a sub-category expansion node click in the diagram
  // (BudgetDashboard's handleSankeyNodeClick), so the user lands directly
  // on the subset they clicked instead of the parent's full list
  // (2026-08-02, user-requested: "the same sidebar as the parent... only
  // filtered").
  initialCategoryFilter?: string | null;
  // transaction_ids that just moved here as a result of the most recent
  // recategorize action — rendered muted/grayed-out (but still fully
  // clickable/editable) so a switched category's new destination is
  // visually obvious without hiding or disabling anything (2026-08-02,
  // user-requested: "any transactions that were moved during the update
  // should be grayed out, but still editable").
  recentlyMovedIds?: Set<string>;
  onClose: () => void;
  onRecategorize: (txn: Transaction | NeedsReviewTransaction) => void;
}

function fmtAmount(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

const NotesDrawer: React.FC<Props> = ({ title, subtitle, transactions, emptyExplanation, initialCategoryFilter, recentlyMovedIds, onClose, onRecategorize }) => {
  const [categoryFilter, setCategoryFilter] = useState<string | null>(initialCategoryFilter ?? null);

  // Only worth showing when the list actually spans more than one category
  // — a single-category list would just offer a filter that does nothing
  // (2026-08-02, user-requested: "an optional filter ... if it contains
  // subsections"). Formatted the same way sankeyExpansion.ts's diagram
  // sub-nodes are, so a filter value picked here always matches a value
  // reachable by clicking a sub-node, and vice versa.
  const categories = React.useMemo(() => {
    const set = new Set<string>();
    for (const t of transactions) set.add(formatCategoryLabel(t.category ?? 'Uncategorized'));
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [transactions]);

  const visibleTransactions = categoryFilter
    ? transactions.filter(t => formatCategoryLabel(t.category ?? 'Uncategorized') === categoryFilter)
    : transactions;

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-96 max-w-full h-full bg-gray-850 border-l border-gray-300 dark:border-gray-700 flex flex-col shadow-2xl">
        <div className="px-4 py-3 border-b border-gray-300 dark:border-gray-700 flex items-start justify-between flex-shrink-0">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white truncate">{title}</h2>
            {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white text-lg leading-none flex-shrink-0 ml-2">
            ×
          </button>
        </div>
        {categories.length > 1 && (
          <div className="px-4 py-2 border-b border-gray-300 dark:border-gray-700 flex-shrink-0">
            <select
              value={categoryFilter ?? ''}
              onChange={e => setCategoryFilter(e.target.value || null)}
              className="w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs text-gray-700 dark:text-gray-300"
            >
              <option value="">All categories ({transactions.length})</option>
              {categories.map(c => (
                <option key={c} value={c}>
                  {c} ({transactions.filter(t => formatCategoryLabel(t.category ?? 'Uncategorized') === c).length})
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="flex-1 overflow-y-auto divide-y divide-gray-200 dark:divide-gray-800">
          {visibleTransactions.length === 0 && (
            <p className="px-4 py-6 text-sm text-gray-500 text-center">
              {transactions.length === 0 ? (emptyExplanation ?? 'No transactions.') : 'No transactions in this category.'}
            </p>
          )}
          {visibleTransactions.map((t, i) => {
            const justMoved = !!(t.transaction_id && recentlyMovedIds?.has(t.transaction_id));
            return (
              <div
                key={t.transaction_id ?? i}
                className={`px-4 py-2 group flex items-start justify-between gap-2 hover:bg-gray-100 dark:hover:bg-gray-800/50 ${justMoved ? 'opacity-50' : ''}`}
                title={justMoved ? 'Just moved here by a recent recategorize' : undefined}
              >
                <div className="min-w-0">
                  <p className="text-sm text-gray-800 dark:text-gray-200 truncate">{t.description}</p>
                  <p className="text-xs text-gray-500">
                    {t.date ?? '—'} · {t.account ?? 'unknown account'}
                    {'needs_review_category' in t
                      ? <span className="ml-1 text-amber-700 dark:text-amber-500">· {t.needs_review_category}</span>
                      : t.category && <span className="ml-1 text-gray-400">· {t.category}</span>}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className="text-sm text-gray-900 dark:text-gray-100 tabular-nums">{fmtAmount(t.amount)}</span>
                  {t.transaction_id && (
                    <button
                      onClick={() => onRecategorize(t)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300"
                      title="Recategorize"
                    >
                      ✎
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default NotesDrawer;
