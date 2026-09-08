import React, { useEffect, useState } from 'react';
import type { NeedsReviewTransaction, Transaction } from '../../lib/budget-types';
import { getNeedsReview } from '../../lib/api';
import NotesDrawer from './NotesDrawer';
import RecategorizeModal from './RecategorizeModal';

interface Props {
  yearMonth?: string;
  refreshKey: number;
  onRecategorized: (affectedTransactionIds: string[]) => void;
}

const NeedsReviewQueue: React.FC<Props> = ({ yearMonth, refreshKey, onRecategorized }) => {
  const [transactions, setTransactions] = useState<NeedsReviewTransaction[]>([]);
  const [open, setOpen] = useState(false);
  const [recategorizing, setRecategorizing] = useState<Transaction | NeedsReviewTransaction | null>(null);
  // Self-contained (not the parent's own recentlyMovedIds) — a recategorize
  // from THIS queue always removes the transaction from the needs-review
  // list entirely on the next reload, so there's nothing left here to gray
  // out; kept only so this drawer's own instance doesn't need to know
  // about the dashboard's separate tracking (2026-08-02, user-requested).
  const [recentlyMovedIds, setRecentlyMovedIds] = useState<Set<string>>(new Set());

  const reload = () => {
    getNeedsReview(yearMonth)
      .then(d => setTransactions(d.transactions))
      .catch(() => {
        /* leave the last known list in place rather than clearing it on a transient error */
      });
  };

  useEffect(reload, [yearMonth, refreshKey]);

  if (transactions.length === 0) {
    return <span className="text-xs text-gray-600 flex-shrink-0">No items need review</span>;
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex-shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-100 dark:bg-amber-900/40 border border-amber-300 dark:border-amber-700/50 text-amber-800 dark:text-amber-300 text-xs hover:bg-amber-200 dark:hover:bg-amber-900/60 transition-colors"
      >
        ⚠ {transactions.length} need{transactions.length === 1 ? 's' : ''} review
      </button>
      {open && (
        <NotesDrawer
          title="Needs Review"
          subtitle={`${transactions.length} transaction${transactions.length === 1 ? '' : 's'} with an ambiguous or unresolved category`}
          transactions={transactions}
          recentlyMovedIds={recentlyMovedIds}
          onClose={() => setOpen(false)}
          onRecategorize={t => setRecategorizing(t)}
        />
      )}
      {recategorizing && (
        <RecategorizeModal
          transaction={recategorizing}
          onClose={() => setRecategorizing(null)}
          onSaved={affectedIds => {
            onRecategorized(affectedIds);
            setRecentlyMovedIds(new Set(affectedIds));
            reload();
          }}
        />
      )}
    </>
  );
};

export default NeedsReviewQueue;
