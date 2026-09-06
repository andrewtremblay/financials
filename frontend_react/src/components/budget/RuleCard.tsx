import React from 'react';
import type { BudgetRule, RuleSegment } from '../../lib/budget-types';

function fmtMoney(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

// Distinct hues per segment position so a 3-segment rule's bar reads as
// three different categories at a glance, not just "colored by pass/fail"
// (the on_target ring around each segment's percentage already carries the
// pass/fail signal — see below).
const SEGMENT_COLORS = ['bg-indigo-500', 'bg-amber-500', 'bg-emerald-500', 'bg-rose-500'];

const SegmentRow: React.FC<{ segment: RuleSegment; color: string }> = ({ segment, color }) => {
  const widthPct = segment.actual_pct !== null ? Math.min(100, segment.actual_pct) : 0;
  const statusClass =
    segment.on_target === null
      ? 'text-gray-500 dark:text-gray-400'
      : segment.on_target
        ? 'text-emerald-600 dark:text-emerald-400'
        : 'text-rose-600 dark:text-rose-400';

  return (
    <div className="mb-2 last:mb-0">
      <div className="flex items-baseline justify-between text-xs mb-0.5">
        <span className="text-gray-700 dark:text-gray-300">{segment.label}</span>
        <span className={statusClass}>
          {segment.actual_pct !== null ? `${segment.actual_pct}%` : '—'}
          <span className="text-gray-400 dark:text-gray-600"> / {segment.target_pct}% target</span>
          {' · '}
          {fmtMoney(segment.actual_amount)}
        </span>
      </div>
      <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-800 overflow-hidden relative">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${widthPct}%` }} />
        {/* Target marker: a thin line at the target percentage so over/under is visible at a glance. */}
        <div
          className="absolute top-0 bottom-0 w-px bg-gray-500 dark:bg-gray-300"
          style={{ left: `${Math.min(100, segment.target_pct)}%` }}
        />
      </div>
    </div>
  );
};

const RuleCard: React.FC<{ rule: BudgetRule }> = ({ rule }) => (
  <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-3 bg-white dark:bg-gray-900">
    <div className="flex items-baseline justify-between mb-1">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{rule.label}</h3>
      <span className="text-xs text-gray-500">Income {fmtMoney(rule.income)}</span>
    </div>
    <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{rule.description}</p>
    {rule.segments.map((segment, i) => (
      <SegmentRow key={segment.key} segment={segment} color={SEGMENT_COLORS[i % SEGMENT_COLORS.length]} />
    ))}
    {rule.caveat && (
      <p className="mt-3 text-xs text-amber-700 dark:text-amber-500 border-t border-gray-200 dark:border-gray-800 pt-2">
        ⚠ {rule.caveat}
      </p>
    )}
  </div>
);

export default RuleCard;
