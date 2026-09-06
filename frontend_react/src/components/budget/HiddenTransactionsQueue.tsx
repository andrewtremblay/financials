import React, { useState } from 'react';
import type { HiddenBucket, NeedsReviewTransaction, Transaction } from '../../lib/budget-types';
import NotesDrawer from './NotesDrawer';

interface Props {
  buckets: HiddenBucket[];
  recentlyMovedIds?: Set<string>;
  onRecategorize: (t: Transaction | NeedsReviewTransaction) => void;
}

// System-recognized transfer/payment categories (self-transfers, credit
// card payments, Venmo payments, boilerplate noise) are excluded from
// every total automatically, with no prior way to confirm a transaction
// landed here correctly rather than being miscategorized (2026-08-02,
// user-requested: "I still need to be able to see hidden transactions").
// Data already rides along on monthData/rangeData (see
// budget_aggregate.py's "hidden" field) — no separate fetch needed, unlike
// NeedsReviewQueue.
const HiddenTransactionsQueue: React.FC<Props> = ({ buckets, recentlyMovedIds, onRecategorize }) => {
  const [open, setOpen] = useState(false);
  const transactions = buckets.flatMap(b => b.transactions);

  if (transactions.length === 0) return null;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex-shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-200 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 text-xs hover:bg-gray-300 dark:hover:bg-gray-700 transition-colors"
      >
        🔒 {transactions.length} hidden
      </button>
      {open && (
        <NotesDrawer
          title="Hidden Transactions"
          subtitle="Excluded from every total automatically (transfers, credit card payments, Venmo, ...) — shown here for observation only."
          transactions={transactions}
          recentlyMovedIds={recentlyMovedIds}
          onClose={() => setOpen(false)}
          onRecategorize={onRecategorize}
        />
      )}
    </>
  );
};

export default HiddenTransactionsQueue;
