import React from 'react';
import type { RetirementModelResult } from '../../lib/budget-types';

function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function fmtMoney(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

// Every retirement_*.py model returns its own small, differently-shaped
// result dict (26 models — bespoke UI per model isn't practical). A
// KEYWORD-based guess (does the name contain "year"? "rung"?) turned out
// too fragile: fields like "year_one_withdrawal" and "value_per_rung" ARE
// dollar amounts despite containing exactly those words, while
// "years_in_retirement" and "number_of_rungs" are plain counts. Rather than
// keep patching an increasingly special-cased regex, this is an explicit
// list of every non-dollar numeric key actually returned across
// retirement_engine.MODELS (verified against a full run of all 26 models,
// 2026-08-02) — anything NOT in this list defaults to currency, which is
// the correct default for this domain (most numbers here are dollars).
const PLAIN_NUMBER_KEYS = new Set([
  'current_age', 'start_age', 'remaining_years_at_retirement', 'risk_aversion_gamma',
  'implied_median_lifespan', 'multiple', 'number_of_rungs', 'guardrail_cuts_triggered',
  'guardrail_raises_triggered', 'ratchets_triggered', 'trials', 'windows_tested',
  'years_clamped_to_ceiling', 'years_clamped_to_floor', 'years_in_retirement',
  'years_simulated', 'years_to_retirement', 'depleted_after_years_in_retirement',
  'depleted_after_years', 'worst_starting_year',
]);

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') {
    if (key.endsWith('_pct')) return `${value}%`;
    // A "probability" field with no "_pct" suffix is a raw 0-1 fraction
    // (e.g. gompertz_makeham's survival_probability_to_life_expectancy)
    // rather than an already-scaled percentage.
    if (/probability/i.test(key)) return `${(value * 100).toFixed(1)}%`;
    if (PLAIN_NUMBER_KEYS.has(key)) return String(value);
    return fmtMoney(value);
  }
  if (Array.isArray(value)) return `${value.length} entries`;
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${formatKey(k)}: ${formatValue(k, v)}`)
      .join(' · ');
  }
  return String(value);
}

const RetirementModelCard: React.FC<{ model: RetirementModelResult }> = ({ model }) => {
  const entries = Object.entries(model.result).filter(([, v]) => !Array.isArray(v));

  return (
    <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-3 bg-white dark:bg-gray-900">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">{model.label}</h3>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{model.description}</p>
      <dl className="text-xs space-y-0.5">
        {entries.map(([key, value]) => (
          <div key={key} className="flex justify-between gap-2">
            <dt className="text-gray-500 dark:text-gray-400 truncate">{formatKey(key)}</dt>
            <dd className="text-gray-900 dark:text-gray-100 tabular-nums text-right flex-shrink-0">{formatValue(key, value)}</dd>
          </div>
        ))}
      </dl>
      {model.caveat && (
        <p className="mt-2 text-[11px] text-amber-700 dark:text-amber-500 border-t border-gray-200 dark:border-gray-800 pt-1.5">
          ⚠ {model.caveat}
        </p>
      )}
    </div>
  );
};

export default RetirementModelCard;
