import type { SectionKind } from './budget-types';

// difference = actual - projected everywhere (see budget_aggregate.py). The
// meaning of "good" flips by section kind: for income/savings, earning or
// saving MORE than planned (positive difference) is good; for expenses,
// spending MORE than planned (positive difference) is overspending — bad.
// Getting this backwards (as an earlier version of this file did) makes
// overspending look green, which defeats the entire point of the diff
// column (2026-07-31 fix).
export function diffColorClass(difference: number | null, kind: SectionKind): string {
  if (difference === null || Math.abs(difference) <= 0.5) return 'text-gray-600';
  const good = kind === 'expense' ? difference < 0 : difference > 0;
  // green/red-400 read fine on the dashboard's dark background but wash out
  // badly against white (contrast ~2:1) — darker shade for light mode,
  // original 400 kept for dark (2026-08-01).
  return good ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';
}
