import React from 'react';

// 'single' means "no range" — the existing one-month-at-a-time mode,
// served by getMonth/getSankeymatic. The other four map straight onto the
// backend's range_key values (see api.ts's RangeKey / budget_aggregate.
// VALID_RANGE_KEYS) and are served by getRange/getRangeSankeymatic.
export type RangeMode = 'single' | '3M' | '6M' | '1Y' | 'YTD';

export const RANGE_MODES: RangeMode[] = ['single', '3M', '6M', '1Y', 'YTD'];

// How many months each mode's prev/next paging should jump by (see
// MonthPicker's `step` prop) — kept alongside the mode list since both
// describe the same "width" concept. YTD has no fixed width in the
// aggregation sense (it can be 1-12 months depending on the anchor), but
// paging by 12 steps a full calendar year at a time, which is the only
// sensible "next/prev" for a year-to-date view.
export const RANGE_STEP_MONTHS: Record<RangeMode, number> = {
  single: 1,
  '3M': 3,
  '6M': 6,
  '1Y': 12,
  YTD: 12,
};

const OPTIONS: { mode: RangeMode; label: string }[] = [
  { mode: 'single', label: '1M' },
  { mode: '3M', label: '3M' },
  { mode: '6M', label: '6M' },
  { mode: '1Y', label: '1Y' },
  { mode: 'YTD', label: 'YTD' },
];

interface Props {
  mode: RangeMode;
  onChange: (mode: RangeMode) => void;
}

const RangePicker: React.FC<Props> = ({ mode, onChange }) => (
  <div className="flex items-center gap-1" role="group" aria-label="Time range">
    {OPTIONS.map(opt => (
      <button
        key={opt.mode}
        onClick={() => onChange(opt.mode)}
        aria-pressed={mode === opt.mode}
        className={`px-2 py-1 text-xs rounded border transition-colors ${
          mode === opt.mode
            ? 'bg-indigo-600 border-indigo-600 text-white'
            : 'bg-gray-100 dark:bg-gray-800 border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
        }`}
      >
        {opt.label}
      </button>
    ))}
  </div>
);

export default RangePicker;
