import React, { useState } from 'react';
import type { RetirementSettings } from '../../lib/budget-types';
import { updateRetirementSettings } from '../../lib/api';

interface Props {
  settings: RetirementSettings;
  onSaved: (next: RetirementSettings) => void;
}

interface FieldDef {
  key: keyof RetirementSettings;
  label: string;
  suffix?: string;
}

interface Group {
  title: string;
  fields: FieldDef[];
}

// Manual entry for now — this app only ever calls Plaid's
// /transactions/sync, never /accounts/balance or /investments/holdings, so
// there's no live portfolio balance to pull yet (tracked as a future TODO,
// 2026-08-02, user-specified).
const GROUPS: Group[] = [
  {
    title: 'Personal',
    fields: [
      { key: 'current_age', label: 'Current age' },
      { key: 'retirement_age', label: 'Retirement age' },
      { key: 'life_expectancy_age', label: 'Life expectancy age' },
    ],
  },
  {
    title: 'Portfolio & assumptions',
    fields: [
      { key: 'current_portfolio_balance', label: 'Current portfolio balance', suffix: '$' },
      { key: 'annual_savings', label: 'Annual savings (pre-retirement)', suffix: '$' },
      { key: 'annual_return_pct', label: 'Expected annual return', suffix: '%' },
      { key: 'inflation_pct', label: 'Expected inflation', suffix: '%' },
      { key: 'bond_yield_pct', label: 'Assumed bond yield', suffix: '%' },
    ],
  },
  {
    title: 'Withdrawal',
    fields: [
      { key: 'withdrawal_rate_pct', label: 'Base withdrawal rate (4% Rule etc.)', suffix: '%' },
      { key: 'risk_aversion', label: 'Risk aversion (Optimal Control gamma)' },
    ],
  },
  {
    title: 'Spending targets',
    fields: [
      { key: 'desired_annual_spending', label: 'Desired annual retirement spending', suffix: '$' },
      { key: 'lean_annual_spending', label: 'LeanFIRE annual spending', suffix: '$' },
      { key: 'fat_annual_spending', label: 'FatFIRE annual spending', suffix: '$' },
      { key: 'barista_annual_spending_gap', label: 'BaristaFIRE spending gap', suffix: '$' },
    ],
  },
  {
    title: 'Guaranteed income',
    fields: [
      { key: 'social_security_annual', label: 'Social Security (annual)', suffix: '$' },
      { key: 'pension_annual', label: 'Pension (annual)', suffix: '$' },
    ],
  },
];

const RetirementSettingsPanel: React.FC<Props> = ({ settings, onSaved }) => {
  const [draft, setDraft] = useState<RetirementSettings>(settings);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const update = (key: keyof RetirementSettings, value: string) => {
    const num = value === '' ? 0 : Number(value);
    setDraft(prev => ({ ...prev, [key]: Number.isFinite(num) ? num : prev[key] }));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const next = await updateRetirementSettings(draft);
      onSaved(next);
      setDirty(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-3 bg-white dark:bg-gray-900 mb-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {GROUPS.map(group => (
          <div key={group.title}>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1.5">{group.title}</h3>
            <div className="flex flex-col gap-1.5">
              {group.fields.map(f => (
                <label key={f.key} className="flex items-center justify-between gap-2 text-xs text-gray-700 dark:text-gray-300">
                  <span className="min-w-0 truncate">{f.label}</span>
                  <span className="flex items-center gap-1 flex-shrink-0">
                    {f.suffix === '$' && <span className="text-gray-400">$</span>}
                    <input
                      type="number"
                      value={draft[f.key]}
                      onChange={e => update(f.key, e.target.value)}
                      className="w-24 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-1.5 py-0.5 text-xs text-gray-900 dark:text-gray-100 text-right"
                    />
                    {f.suffix === '%' && <span className="text-gray-400">%</span>}
                  </span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="flex justify-end mt-3">
        <button
          onClick={save}
          disabled={saving || !dirty}
          className="px-3 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded disabled:opacity-50"
        >
          {saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
        </button>
      </div>
    </div>
  );
};

export default RetirementSettingsPanel;
