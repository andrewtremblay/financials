import React, { useEffect, useState } from 'react';
import type { BudgetClassification, BudgetType } from '../../lib/budget-types';
import { getBudgetClassification, setBudgetClassification } from '../../lib/api';

interface Props {
  onClose: () => void;
}

// Lets the user correct budget_classification.py's best-guess Need/Want
// defaults per line item, plus the Housing/Debt sub-tags the 28/36 rule
// depends on — "need vs want" is genuinely subjective per household
// (2026-08-02, user-specified: defaults with override, not a blank slate).
const BudgetClassificationSettings: React.FC<Props> = ({ onClose }) => {
  const [items, setItems] = useState<BudgetClassification[]>([]);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  useEffect(() => {
    getBudgetClassification()
      .then(setItems)
      .catch(() => {
        /* panel just stays empty */
      });
  }, []);

  const update = (item: BudgetClassification, patch: Partial<BudgetClassification>) => {
    const next = { ...item, ...patch };
    const rowKey = `${item.section}␟${item.label}`;
    setItems(prev => prev.map(i => (i.section === item.section && i.label === item.label ? next : i)));
    setSavingKey(rowKey);
    setBudgetClassification(next.section, next.label, next.budget_type, next.housing, next.debt)
      .finally(() => setSavingKey(null));
  };

  const bySection = items.reduce<Record<string, BudgetClassification[]>>((acc, item) => {
    (acc[item.section] ??= []).push(item);
    return acc;
  }, {});

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-[36rem] max-w-full max-h-[85vh] bg-gray-850 border border-gray-300 dark:border-gray-700 rounded-lg shadow-2xl flex flex-col">
        <div className="px-4 py-3 border-b border-gray-300 dark:border-gray-700 flex items-start justify-between flex-shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Budget Classification</h2>
            <p className="text-xs text-gray-500 mt-0.5 max-w-md">
              Tag each expense line item as a Need or a Want, and whether it counts toward the 28/36 rule's Housing/Debt totals.
            </p>
          </div>
          <button onClick={onClose} className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white text-lg leading-none flex-shrink-0 ml-2">
            ×
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-2">
          {items.length === 0 && <p className="px-1 py-6 text-sm text-gray-500 text-center">Loading…</p>}
          {Object.entries(bySection).map(([section, rows]) => (
            <div key={section} className="mb-3">
              <h3 className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 mb-1 mt-2">{section}</h3>
              {rows.map(item => {
                const rowKey = `${item.section}␟${item.label}`;
                const saving = savingKey === rowKey;
                return (
                  <div key={rowKey} className="flex items-center gap-3 py-1.5 border-b border-gray-100 dark:border-gray-800/60 last:border-0">
                    <span className="flex-1 text-sm text-gray-800 dark:text-gray-200 truncate">{item.label}</span>
                    <select
                      value={item.budget_type}
                      onChange={e => update(item, { budget_type: e.target.value as BudgetType })}
                      disabled={saving}
                      className="bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs text-gray-900 dark:text-gray-100"
                    >
                      <option value="need">Need</option>
                      <option value="want">Want</option>
                    </select>
                    <label className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400">
                      <input
                        type="checkbox"
                        checked={item.housing}
                        onChange={e => update(item, { housing: e.target.checked })}
                        disabled={saving}
                      />
                      Housing
                    </label>
                    <label className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400">
                      <input
                        type="checkbox"
                        checked={item.debt}
                        onChange={e => update(item, { debt: e.target.checked })}
                        disabled={saving}
                      />
                      Debt
                    </label>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default BudgetClassificationSettings;
