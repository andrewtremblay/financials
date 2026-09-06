import React from 'react';

interface Props {
  label?: string;
  className?: string;
}

// Small, theme-aware loading indicator — shared by the budget dashboard's
// sidebar and diagram panel so a fetch in flight always reads as "loading",
// never as "blank/broken" (2026-08-02, user-reported: "the screen appears
// to have no data loaded for a long period of time before the data snaps
// in").
const Spinner: React.FC<Props> = ({ label, className = '' }) => (
  <div className={`flex flex-col items-center justify-center gap-3 ${className}`}>
    <div
      className="w-6 h-6 rounded-full border-2 border-gray-300 dark:border-gray-700 border-t-indigo-500 dark:border-t-indigo-400 animate-spin"
      role="status"
      aria-label={label ?? 'Loading'}
    />
    {label && <p className="text-sm text-gray-500">{label}</p>}
  </div>
);

export default Spinner;
