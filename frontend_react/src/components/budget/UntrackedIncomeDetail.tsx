import React, { useEffect, useState } from 'react';
import type { RangeMode } from './RangePicker';
import type { UntrackedIncomeLabelStatus, UntrackedIncomeRule, UntrackedIncomeScope } from '../../lib/budget-types';
import {
  createUntrackedIncomeRule, deleteUntrackedIncomeRule, getRangeUntrackedIncome,
  getUntrackedIncome, getUntrackedIncomeLabels, getUntrackedIncomeRules,
} from '../../lib/api';

interface Props {
  // The single anchor month edits are scoped against — always the
  // dashboard's own selected month, even in range mode (a rule always
  // targets one concrete month; "current"/"current and future" need a
  // concrete starting point to be meaningful) (2026-08-02, user-requested).
  yearMonth: string;
  // Which breakdown to *display*: matches whatever the diagram itself is
  // currently showing (single month or a summed range), so the numbers
  // here always match the "Untracked Income" node's own width.
  rangeMode: RangeMode;
  onChanged?: () => void;
}

const SCOPE_OPTIONS: { value: UntrackedIncomeScope; label: string }[] = [
  { value: 'current', label: 'This month only' },
  { value: 'current_and_future', label: 'This month onward' },
  { value: 'all', label: 'All months (past and future)' },
];

function fmtMoney(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

function fmtMonth(ym: string | null): string {
  if (!ym) return '';
  const [y, m] = ym.split('-');
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

function scopeSummary(rule: UntrackedIncomeRule): string {
  if (rule.start_month === null && rule.end_month === null) return 'All months';
  if (rule.start_month === rule.end_month) return fmtMonth(rule.start_month);
  return `${fmtMonth(rule.start_month)} onward`;
}

const UntrackedIncomeDetail: React.FC<Props> = ({ yearMonth, rangeMode, onChanged }) => {
  const [breakdown, setBreakdown] = useState<Record<string, number> | null>(null);
  const [labels, setLabels] = useState<UntrackedIncomeLabelStatus[]>([]);
  const [rules, setRules] = useState<UntrackedIncomeRule[]>([]);
  const [editingLabel, setEditingLabel] = useState<{ label: string; enabled: boolean } | null>(null);
  const [scope, setScope] = useState<UntrackedIncomeScope>('current');
  const [saving, setSaving] = useState(false);
  const [showManage, setShowManage] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = () => {
    const breakdownPromise = rangeMode === 'single' ? getUntrackedIncome(yearMonth) : getRangeUntrackedIncome(rangeMode, yearMonth);
    breakdownPromise.then(d => setBreakdown(d.breakdown)).catch(() => setBreakdown({}));
    getUntrackedIncomeLabels(yearMonth).then(setLabels).catch(() => setLabels([]));
    getUntrackedIncomeRules().then(setRules).catch(() => setRules([]));
  };

  useEffect(reload, [yearMonth, rangeMode]);

  const startEdit = (label: string, currentlyUntracked: boolean) => {
    setEditingLabel({ label, enabled: !currentlyUntracked });
    setScope('current');
    setError(null);
  };

  const save = async () => {
    if (!editingLabel) return;
    setSaving(true);
    setError(null);
    try {
      await createUntrackedIncomeRule(editingLabel.label, editingLabel.enabled, scope, yearMonth);
      setEditingLabel(null);
      reload();
      onChanged?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const removeRule = async (ruleId: string) => {
    await deleteUntrackedIncomeRule(ruleId);
    reload();
    onChanged?.();
  };

  return (
    <div className="mt-3 border-t border-gray-200 dark:border-gray-800 pt-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1.5">
        Breakdown{rangeMode !== 'single' ? ' (this period)' : ` (${fmtMonth(yearMonth)})`}
      </h3>
      {breakdown === null ? (
        <p className="text-xs text-gray-500">Loading…</p>
      ) : Object.keys(breakdown).length === 0 ? (
        <p className="text-xs text-gray-500">Nothing counted as untracked income right now.</p>
      ) : (
        <ul className="text-sm text-gray-800 dark:text-gray-200 space-y-0.5 mb-1">
          {Object.entries(breakdown).map(([label, amount]) => (
            <li key={label} className="flex justify-between gap-2">
              <span className="truncate">{label}</span>
              <span className="tabular-nums flex-shrink-0">{fmtMoney(amount)}</span>
            </li>
          ))}
        </ul>
      )}

      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mt-3 mb-1.5">
        Which Savings items count as untracked income ({fmtMonth(yearMonth)})
      </h3>
      <ul className="space-y-1">
        {labels.map(l => (
          <li key={l.label} className="flex items-center justify-between gap-2 text-sm">
            <label className="flex items-center gap-2 text-gray-800 dark:text-gray-200 min-w-0">
              <input
                type="checkbox"
                checked={l.is_untracked}
                onChange={() => startEdit(l.label, l.is_untracked)}
              />
              <span className="truncate">{l.label}</span>
            </label>
            {l.amount > 0 && <span className="text-xs text-gray-500 flex-shrink-0 tabular-nums">{fmtMoney(l.amount)}</span>}
          </li>
        ))}
      </ul>

      {editingLabel && (
        <div className="mt-2 p-2 rounded border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800">
          <p className="text-xs text-gray-700 dark:text-gray-300 mb-1.5">
            {editingLabel.enabled ? 'Mark' : 'Unmark'} <span className="font-medium">{editingLabel.label}</span> as untracked income for:
          </p>
          <div className="flex flex-col gap-1 mb-2">
            {SCOPE_OPTIONS.map(opt => (
              <label key={opt.value} className="flex items-center gap-2 text-xs text-gray-700 dark:text-gray-300">
                <input type="radio" checked={scope === opt.value} onChange={() => setScope(opt.value)} />
                {opt.label}
              </label>
            ))}
          </div>
          {error && <p className="text-xs text-red-600 dark:text-red-400 mb-1.5">{error}</p>}
          <div className="flex justify-end gap-2">
            <button onClick={() => setEditingLabel(null)} className="px-2 py-1 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
              Cancel
            </button>
            <button
              onClick={save}
              disabled={saving}
              className="px-2 py-1 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      )}

      <button
        onClick={() => setShowManage(v => !v)}
        className="mt-3 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300"
      >
        {showManage ? 'Hide' : 'Manage'} existing rules ({rules.length})
      </button>
      {showManage && (
        <ul className="mt-1.5 space-y-1">
          {rules.length === 0 && <li className="text-xs text-gray-500">No custom rules yet — every label is using its default.</li>}
          {rules.map(r => (
            <li key={r.id} className="flex items-center justify-between gap-2 text-xs text-gray-600 dark:text-gray-400">
              <span className="truncate">
                {r.label}: {r.enabled ? 'untracked' : 'not untracked'} — {scopeSummary(r)}
              </span>
              <button
                onClick={() => removeRule(r.id)}
                className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 flex-shrink-0"
                title="Remove this rule"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default UntrackedIncomeDetail;
