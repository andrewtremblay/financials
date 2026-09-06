import React, { useState } from 'react';
import type { IgnoredTransaction, NeedsReviewTransaction, Transaction } from '../../lib/budget-types';
import { updateIgnoreNote } from '../../lib/api';

interface Props {
  transactions: IgnoredTransaction[];
  onRecategorize: (t: Transaction | NeedsReviewTransaction | IgnoredTransaction) => void;
}

function fmtAmount(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

const IgnoredRow: React.FC<{ txn: IgnoredTransaction; onRecategorize: Props['onRecategorize'] }> = ({ txn, onRecategorize }) => {
  const [note, setNote] = useState(txn.note ?? '');
  const [saving, setSaving] = useState(false);

  const save = () => {
    if (!txn.transaction_id || note === (txn.note ?? '')) return;
    setSaving(true);
    updateIgnoreNote(txn.transaction_id, note)
      .catch(() => setNote(txn.note ?? '')) // revert on failure rather than showing an unsaved value as if it stuck
      .finally(() => setSaving(false));
  };

  return (
    <div className="px-3 py-2 group hover:bg-gray-100 dark:hover:bg-gray-800/50">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm text-gray-800 dark:text-gray-200 truncate">{txn.description}</p>
          <p className="text-xs text-gray-500">{txn.date ?? '—'} · {txn.account ?? 'unknown account'}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-sm text-gray-900 dark:text-gray-100 tabular-nums">{fmtAmount(txn.amount)}</span>
          {txn.transaction_id && (
            <button
              onClick={() => onRecategorize(txn)}
              className="opacity-0 group-hover:opacity-100 transition-opacity text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300"
              title="Recategorize (un-ignore)"
            >
              ✎
            </button>
          )}
        </div>
      </div>
      <input
        value={note}
        onChange={e => setNote(e.target.value)}
        onBlur={save}
        placeholder="Why was this ignored?"
        disabled={saving}
        className="mt-1 w-full bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs text-gray-700 dark:text-gray-300 disabled:opacity-60"
      />
    </div>
  );
};

// Rendered at the bottom of the sidebar's section list, below every real
// budget section — these transactions are excluded from every total and the
// Sankey diagram (see budget_aggregate._ignored_transactions_for_month),
// shown here purely for observation (2026-08-02, user-specified).
const IgnoredSection: React.FC<Props> = ({ transactions, onRecategorize }) => {
  const [collapsed, setCollapsed] = useState(false);
  if (transactions.length === 0) return null;

  return (
    <div className="border-b border-gray-200 dark:border-gray-800">
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-100 dark:hover:bg-gray-800/40 transition-colors"
      >
        <span className={`inline-block transition-transform ${collapsed ? '' : 'rotate-90'}`}>›</span>
        <span className="text-sm font-semibold text-gray-500 dark:text-gray-500">Ignored ({transactions.length})</span>
      </button>
      {!collapsed && (
        <div className="divide-y divide-gray-200 dark:divide-gray-800 pb-2">
          {transactions.map(t => (
            <IgnoredRow key={t.transaction_id} txn={t} onRecategorize={onRecategorize} />
          ))}
        </div>
      )}
    </div>
  );
};

export default IgnoredSection;
