import React, { useState } from 'react';
import { getQueryParam, setQueryParam } from './lib/url';
import BudgetDashboard from './components/budget/BudgetDashboard';
import BudgetRulesView from './components/budget/BudgetRulesView';
import RetirementPlanningView from './components/budget/RetirementPlanningView';
import SankeyBuilder from './components/SankeyBuilder';
import ThemeToggle from './components/ThemeToggle';

type Mode = 'dashboard' | 'rules' | 'retirement' | 'sankey';
const TAB_MODES: Mode[] = ['dashboard', 'rules', 'retirement', 'sankey'];

const App: React.FC = () => {
  const [mode, setMode] = useState<Mode>(() => {
    const tab = getQueryParam('tab');
    return (TAB_MODES as string[]).includes(tab ?? '') ? (tab as Mode) : 'dashboard';
  });

  const handleModeChange = (next: Mode) => {
    setMode(next);
    setQueryParam('tab', next);
  };

  return (
    <div className="flex flex-col h-screen bg-white text-gray-900 dark:bg-gray-900 dark:text-gray-100 overflow-hidden">
      {/* bg-gray-850 is a hand-defined utility (index.css) that switches
          itself between light/dark via a `.dark` ancestor selector — no
          `dark:` prefix needed/possible here since Tailwind's JIT never
          generated it. */}
      <nav className="flex-shrink-0 flex items-center gap-1 px-3 h-10 border-b border-gray-200 dark:border-gray-700 bg-gray-850">
        <button
          onClick={() => handleModeChange('dashboard')}
          className={`px-3 h-7 rounded text-xs font-medium transition-colors ${
            mode === 'dashboard'
              ? 'bg-indigo-600 text-white'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-800'
          }`}
        >
          Budget Dashboard
        </button>
        <button
          onClick={() => handleModeChange('rules')}
          className={`px-3 h-7 rounded text-xs font-medium transition-colors ${
            mode === 'rules'
              ? 'bg-indigo-600 text-white'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-800'
          }`}
        >
          Budget Rules
        </button>
        <button
          onClick={() => handleModeChange('retirement')}
          className={`px-3 h-7 rounded text-xs font-medium transition-colors ${
            mode === 'retirement'
              ? 'bg-indigo-600 text-white'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-800'
          }`}
        >
          Retirement Planning
        </button>
        <button
          onClick={() => handleModeChange('sankey')}
          className={`px-3 h-7 rounded text-xs font-medium transition-colors ${
            mode === 'sankey'
              ? 'bg-indigo-600 text-white'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-800'
          }`}
        >
          Sankey Builder
        </button>
        <div className="flex-1" />
        <ThemeToggle />
      </nav>
      <div className="flex-1 min-h-0 overflow-hidden">
        {mode === 'dashboard' && <BudgetDashboard />}
        {mode === 'rules' && <BudgetRulesView />}
        {mode === 'retirement' && <RetirementPlanningView />}
        {mode === 'sankey' && <SankeyBuilder />}
      </div>
    </div>
  );
};

export default App;
