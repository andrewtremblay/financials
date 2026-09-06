import React from 'react';
import type { LineItem, SectionKind } from '../../lib/budget-types';
import { diffColorClass } from '../../lib/budgetColor';
import { isExpandable } from '../../lib/sankeyExpansion';

interface Props {
  item: LineItem;
  sectionKind: SectionKind;
  onClick: () => void;
  expanded: boolean;
  onToggleExpand: () => void;
}

function fmt(n: number | null): string {
  if (n === null) return '—';
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

const BudgetLineItemRow: React.FC<Props> = ({ item, sectionKind, onClick, expanded, onToggleExpand }) => {
  const txnCount = item.transactions.length;
  // Only line items whose transactions actually span more than one raw
  // category are worth drilling into — a single-category bucket would just
  // add a redundant duplicate node in the diagram (2026-08-01).
  const expandable = item.actual > 0 && isExpandable(item);

  return (
    <button
      onClick={onClick}
      className="w-full grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 px-3 py-1.5 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-800/60 rounded transition-colors"
    >
      <span className="text-gray-700 dark:text-gray-300 truncate flex items-center gap-1.5">
        {expandable && (
          <span
            role="button"
            tabIndex={0}
            onClick={e => { e.stopPropagation(); onToggleExpand(); }}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onToggleExpand(); }
            }}
            className="flex-shrink-0 w-3.5 h-3.5 flex items-center justify-center rounded-sm text-[10px] leading-none text-gray-500 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-200 dark:hover:bg-gray-700"
            title={expanded ? 'Collapse into one node in the diagram' : 'Expand into sub-category nodes in the diagram'}
          >
            {expanded ? '−' : '+'}
          </span>
        )}
        {item.label}
        {(item.is_fixed || item.is_copy_projected) && (
          <span className="text-[10px] text-gray-500" title={item.is_fixed ? 'Fixed value' : 'Mirrors projected'}>
            ●
          </span>
        )}
        {txnCount > 0 && <span className="text-[10px] text-gray-600">({txnCount})</span>}
      </span>
      <span className="text-gray-500 w-20 text-right tabular-nums">{fmt(item.projected)}</span>
      <span className="text-gray-900 dark:text-gray-100 w-20 text-right tabular-nums">{fmt(item.actual)}</span>
      <span className={`w-20 text-right tabular-nums ${diffColorClass(item.difference, sectionKind)}`}>
        {item.difference !== null ? fmt(item.difference) : '—'}
      </span>
    </button>
  );
};

export default BudgetLineItemRow;
