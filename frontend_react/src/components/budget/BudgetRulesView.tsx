import React, { useEffect, useState } from 'react';
import type { BudgetRule, MonthSummary } from '../../lib/budget-types';
import { getBudgetRules, getMonths, getRangeBudgetRules } from '../../lib/api';
import { getQueryParam, setQueryParam } from '../../lib/url';
import MonthPicker from './MonthPicker';
import RangePicker, { RANGE_STEP_MONTHS, type RangeMode } from './RangePicker';
import RuleCard from './RuleCard';
import BudgetClassificationSettings from './BudgetClassificationSettings';
import Spinner from '../Spinner';

// Persisted independently of BudgetDashboard's own collapsed-sections /
// expanded-node preferences — which rules to show is a preference about
// this tab specifically.
const STORAGE_KEY = 'financials.enabledBudgetRules';
const ALL_RULE_KEYS = ['50_30_20', '28_36', '70_20_10', '80_20'];

function loadEnabled(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set(ALL_RULE_KEYS);
  } catch {
    return new Set(ALL_RULE_KEYS);
  }
}

function saveEnabled(set: Set<string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
  } catch {
    // localStorage unavailable (private browsing etc) — preference just won't persist.
  }
}

const BudgetRulesView: React.FC = () => {
  const [months, setMonths] = useState<MonthSummary[]>([]);
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [rangeMode, setRangeMode] = useState<RangeMode>('single');
  const [rules, setRules] = useState<BudgetRule[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<Set<string>>(loadEnabled);
  const [showClassification, setShowClassification] = useState(false);

  // Distinct query param from BudgetDashboard's own ?month= so the two tabs'
  // month selections don't clobber each other when switching tabs.
  useEffect(() => {
    getMonths()
      .then(d => {
        setMonths(d.months);
        const fromUrl = getQueryParam('rulesMonth');
        const valid = fromUrl && d.months.some(m => m.year_month === fromUrl);
        setSelectedMonth(valid ? fromUrl! : d.default_year_month);
      })
      .catch(e => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    if (!selectedMonth) return;
    setLoading(true);
    setError(null);
    const promise = rangeMode === 'single' ? getBudgetRules(selectedMonth) : getRangeBudgetRules(rangeMode, selectedMonth);
    promise
      .then(d => setRules(d.rules))
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [selectedMonth, rangeMode]);

  const handleMonthChange = (ym: string) => {
    setSelectedMonth(ym);
    setQueryParam('rulesMonth', ym);
  };

  const toggleRule = (key: string) => {
    setEnabled(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      saveEnabled(next);
      return next;
    });
  };

  const visibleRules = (rules ?? []).filter(r => enabled.has(r.key));

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <div>
            <h1 className="text-sm font-bold text-gray-900 dark:text-white">Budget Rules</h1>
            <p className="text-xs text-gray-500 mt-0.5">How this period stacks up against common budgeting rules of thumb.</p>
          </div>
          <button
            onClick={() => setShowClassification(true)}
            className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 flex-shrink-0"
          >
            Edit Need/Want classification
          </button>
        </div>

        <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
          {months.length > 0 && selectedMonth ? (
            <MonthPicker months={months} selected={selectedMonth} onChange={handleMonthChange} step={RANGE_STEP_MONTHS[rangeMode]} />
          ) : (
            !error && <div className="h-6 w-40 rounded bg-gray-200 dark:bg-gray-800 animate-pulse" />
          )}
          <RangePicker mode={rangeMode} onChange={setRangeMode} />
        </div>

        <div className="flex flex-wrap gap-4 mb-4 text-xs">
          {ALL_RULE_KEYS.map(key => {
            const rule = (rules ?? []).find(r => r.key === key);
            return (
              <label key={key} className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400 cursor-pointer">
                <input type="checkbox" checked={enabled.has(key)} onChange={() => toggleRule(key)} />
                {rule?.label ?? key}
              </label>
            );
          })}
        </div>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        {loading && <Spinner label="Computing…" className="py-16" />}
        {!loading && !error && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {visibleRules.map(rule => (
              <RuleCard key={rule.key} rule={rule} />
            ))}
            {visibleRules.length === 0 && (
              <p className="text-sm text-gray-500 sm:col-span-2">No rules enabled — toggle one above.</p>
            )}
          </div>
        )}
      </div>

      {showClassification && <BudgetClassificationSettings onClose={() => setShowClassification(false)} />}
    </div>
  );
};

export default BudgetRulesView;
