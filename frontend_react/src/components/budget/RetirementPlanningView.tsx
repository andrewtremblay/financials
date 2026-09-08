import React, { useEffect, useState } from 'react';
import type { RetirementModelResult, RetirementSettings } from '../../lib/budget-types';
import { getRetirementModels } from '../../lib/api';
import RetirementSettingsPanel from './RetirementSettingsPanel';
import RetirementModelCard from './RetirementModelCard';
import Spinner from '../Spinner';

const RetirementPlanningView: React.FC = () => {
  const [settings, setSettings] = useState<RetirementSettings | null>(null);
  const [models, setModels] = useState<RetirementModelResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(true);

  const reload = () => {
    setLoading(true);
    setError(null);
    getRetirementModels()
      .then(d => {
        setSettings(d.settings);
        setModels(d.models);
      })
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(reload, []);

  const categories = [...new Set(models.map(m => m.category))];

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h1 className="text-sm font-bold text-gray-900 dark:text-white">Retirement Planning</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              Calculations, frameworks, and models for evaluating a retirement plan, computed from the assumptions below.
            </p>
          </div>
          <button
            onClick={() => setShowSettings(v => !v)}
            className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 flex-shrink-0"
          >
            {showSettings ? 'Hide' : 'Show'} settings
          </button>
        </div>

        {settings && showSettings && (
          <RetirementSettingsPanel
            settings={settings}
            onSaved={next => {
              setSettings(next);
              reload();
            }}
          />
        )}

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        {loading && <Spinner label="Computing…" className="py-16" />}

        {!loading && !error && categories.map(category => (
          <div key={category} className="mb-6">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">{category}</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {models.filter(m => m.category === category).map(m => (
                <RetirementModelCard key={m.key} model={m} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default RetirementPlanningView;
