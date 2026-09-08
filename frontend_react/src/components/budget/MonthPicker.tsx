import React from 'react';
import type { MonthSummary } from '../../lib/budget-types';

interface Props {
  months: MonthSummary[];
  selected: string;
  onChange: (yearMonth: string) => void;
  // How many months the prev/next arrows jump by. Single-month mode uses
  // the default of 1; range mode (see RangePicker/BudgetDashboard) passes
  // the range's own width (e.g. 3 for "3M") so paging steps through
  // non-overlapping windows instead of just sliding the anchor by one
  // month at a time within the same window.
  step?: number;
}

const MonthPicker: React.FC<Props> = ({ months, selected, onChange, step = 1 }) => {
  const index = months.findIndex(m => m.year_month === selected);
  // Clamp rather than disable outright when a step overshoots the
  // available history (e.g. stepping back 12 months for "1Y" with only 8
  // months of data) — still lands on the earliest/latest available month
  // rather than leaving the user stuck.
  const prev = index > 0 ? months[Math.max(0, index - step)] : null;
  const next = index >= 0 && index < months.length - 1 ? months[Math.min(months.length - 1, index + step)] : null;
  const current = index >= 0 ? months[index] : null;

  return (
    <div className="flex items-center gap-2">
      <button
        disabled={!prev}
        onClick={() => prev && onChange(prev.year_month)}
        className="w-6 h-6 flex items-center justify-center rounded text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent"
        aria-label="Previous month"
      >
        ‹
      </button>
      <select
        value={selected}
        onChange={e => onChange(e.target.value)}
        className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-sm text-gray-900 dark:text-gray-100"
      >
        {months.map(m => (
          <option key={m.year_month} value={m.year_month}>
            {m.label}
            {!m.has_sheet_tab ? ' (no budget)' : ''}
          </option>
        ))}
      </select>
      <button
        disabled={!next}
        onClick={() => next && onChange(next.year_month)}
        className="w-6 h-6 flex items-center justify-center rounded text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent"
        aria-label="Next month"
      >
        ›
      </button>
      {current && !current.has_sheet_tab && (
        <span className="text-xs text-yellow-700 dark:text-yellow-500">No budget targets for this month</span>
      )}
    </div>
  );
};

export default MonthPicker;
