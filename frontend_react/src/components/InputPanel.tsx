import React from 'react';
import type { SkmSettings } from '../types';
import { DEFAULT_SETTINGS } from '../lib/settings';

interface Example {
  id: string;
  name: string;
  flows: string;
  settings: Partial<SkmSettings>;
}

const EXAMPLES: Example[] = [
  {
    id: 'default_budget',
    name: 'Budget',
    flows: `// Enter Flows between Nodes, like this:
//         Source [AMOUNT] Target

Wages [1500] Budget
Other [250] Budget

Budget [450] Taxes
Budget [420] Housing
Budget [400] Food
Budget [295] Transportation
Budget [25] Savings

// You can set a Node's color, like this:
:Budget #708090
//            ...or a color for a single Flow:
Budget [160] Other Necessities #0F0

// Use the controls below to customize
// your diagram's appearance...`,
    settings: {
      size_h: 600, size_w: 600, node_w: 12, node_h: 50,
      node_spacing: 75, node_border: 0, node_theme: 'a',
      flow_inheritfrom: 'outside-in', layout_justifyends: false,
      layout_order: 'automatic', labelname_size: 16, labelname_weight: 400,
      labelvalue_appears: true, labelvalue_position: 'below',
      themeoffset_a: 9, value_prefix: '',
    },
  },
  {
    id: 'job_search',
    name: 'Job Search',
    flows: `// Sample Job Search diagram:

Applications [4] 1st Interviews
Applications [9] Rejected
Applications [4] No Answer

1st Interviews [2] 2nd Interviews
1st Interviews [2] No Offer

2nd Interviews [2] Offers

Offers [1] Accepted
Offers [1] Declined`,
    settings: {
      size_h: 600, size_w: 700, node_w: 8, node_h: 60,
      node_spacing: 55, node_border: 0, node_theme: 'a',
      flow_inheritfrom: 'target', layout_justifyends: false,
      layout_order: 'automatic', labelname_size: 17, labelname_weight: 400,
      labelvalue_appears: true, labelvalue_position: 'above',
      themeoffset_a: 6, value_prefix: '',
    },
  },
  {
    id: 'financial_results',
    name: 'Financial Results',
    flows: `// Sample Financial Results diagram:

DivisionA [900] Revenue
DivisionB [750] Revenue
DivisionC [150] Revenue

Revenue [800] Cost of Sales
Revenue [1000] Gross Profit

Gross Profit [10] Amortization
Gross Profit [640] Selling, General & Administration
Gross Profit [350] Operating Profit

Operating Profit [90] Tax
Operating Profit [260] Net Profit

// Profit - blue
:Gross Profit #48e <<
:Operating Profit #48e <<
:Net Profit #48e <<

// Expenses - rust
:Tax #d97 <<
:Selling, General & Administration #d97 <<
:Amortization #d97 <<

// Cost - gray
:Cost of Sales #bbb <<

// main Revenue node: dark grey
:Revenue #555`,
    settings: {
      size_h: 600, size_w: 900, node_w: 20, node_h: 75,
      node_spacing: 30, node_border: 2, node_theme: 'b',
      flow_inheritfrom: 'source', layout_justifyends: false,
      layout_order: 'automatic', labelname_size: 18, labelname_weight: 400,
      labelvalue_appears: true, labelvalue_position: 'below',
      themeoffset_b: 3, value_prefix: '$',
    },
  },
];

interface Props {
  value: string;
  onChange: (value: string) => void;
  onLoadExample: (flows: string, settings: Partial<SkmSettings>) => void;
  onFileLoad: (content: string) => void;
}

const InputPanel: React.FC<Props> = ({ value, onChange, onLoadExample, onFileLoad }) => {
  const [showReplaceWarning, setShowReplaceWarning] = React.useState(false);
  const [pendingExample, setPendingExample] = React.useState<Example | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const handleExampleClick = (example: Example) => {
    if (value.trim()) {
      setPendingExample(example);
      setShowReplaceWarning(true);
    } else {
      onLoadExample(example.flows, example.settings);
    }
  };

  const handleConfirmReplace = () => {
    if (pendingExample) {
      onLoadExample(pendingExample.flows, pendingExample.settings);
    }
    setShowReplaceWarning(false);
    setPendingExample(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
      const content = ev.target?.result as string;
      if (content) onFileLoad(content);
    };
    reader.readAsText(file);
    // Reset so the same file can be re-loaded
    e.target.value = '';
  };

  const handleSave = () => {
    const blob = new Blob([value], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sankey-diagram.txt';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Example buttons */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Examples
        </p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map(ex => (
            <button
              key={ex.id}
              onClick={() => handleExampleClick(ex)}
              className="px-3 py-1.5 text-xs bg-gray-700 hover:bg-indigo-600 text-gray-200 hover:text-white rounded-md transition-colors duration-150 border border-gray-600 hover:border-indigo-500"
            >
              {ex.name}
            </button>
          ))}
        </div>
      </div>

      {/* Replace warning */}
      {showReplaceWarning && (
        <div className="bg-yellow-900/50 border border-yellow-600 rounded-lg p-3 text-sm">
          <p className="text-yellow-200 mb-2">
            This will <strong>erase</strong> your current diagram. Continue?
          </p>
          <div className="flex gap-2">
            <button
              onClick={handleConfirmReplace}
              className="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 text-white rounded text-xs font-medium transition-colors"
            >
              Yes, replace
            </button>
            <button
              onClick={() => { setShowReplaceWarning(false); setPendingExample(null); }}
              className="px-3 py-1 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-xs font-medium transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Textarea */}
      <div className="flex-1 flex flex-col min-h-0">
        <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Flows &amp; Nodes
        </label>
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          className="flex-1 w-full bg-gray-900 text-gray-100 border border-gray-700 rounded-lg p-3 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent leading-relaxed placeholder-gray-600 min-h-[200px]"
          placeholder={`// Enter flows like:\nWages [1500] Budget\nBudget [450] Taxes\n\n// Node color:\n:Budget #708090`}
          spellCheck={false}
        />
      </div>

      {/* Syntax help */}
      <div className="text-xs text-gray-500 leading-relaxed bg-gray-900 rounded-lg p-3 border border-gray-800">
        <p className="font-semibold text-gray-400 mb-1">Syntax</p>
        <p><span className="text-indigo-400">Source [amount] Target</span> — flow</p>
        <p><span className="text-indigo-400">:NodeName #color</span> — node color</p>
        <p><span className="text-indigo-400">// comment</span> — ignored line</p>
        <p><span className="text-indigo-400">move Name x, y</span> — offset node</p>
      </div>

      {/* File save/load */}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          className="flex-1 px-3 py-2 text-xs bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-md transition-colors border border-gray-600 font-medium"
        >
          Save to file
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex-1 px-3 py-2 text-xs bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-md transition-colors border border-gray-600 font-medium"
        >
          Load from file
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.text,.skm,text/plain"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>
    </div>
  );
};

export default InputPanel;
