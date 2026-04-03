import React, { useState, useEffect, useRef, useCallback } from 'react';
import type { SkmSettings } from './types';
import { DEFAULT_SETTINGS, applyPartialSettings } from './lib/settings';
import { parseInput } from './lib/parser';
import { encodeForURL, decodeFromURL, getURLParam, setURLParam } from './lib/url';
import InputPanel from './components/InputPanel';
import SettingsPanel from './components/SettingsPanel';
import SankeyDiagram from './components/SankeyDiagram';
import ExportButtons from './components/ExportButtons';

const DEFAULT_FLOWS = `// Enter Flows between Nodes, like this:
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
// your diagram's appearance...`;

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

// Parse the ?i= URL parameter synchronously so the first render
// already has the correct flows and settings (canvas size, etc.).
function loadFromURL(): { inputText: string; settings: SkmSettings } | null {
  const param = getURLParam();
  if (!param) return null;
  const decoded = decodeFromURL(param);
  if (!decoded) return null;
  const result = parseInput(decoded);
  const text = result.flowsText.trim() || decoded;
  const settings = Object.keys(result.settings).length > 0
    ? applyPartialSettings(DEFAULT_SETTINGS, result.settings)
    : DEFAULT_SETTINGS;
  return { inputText: text, settings };
}

const App: React.FC = () => {
  // Compute URL state once for both initializers (lazy init runs only on mount).
  const [inputText, setInputText] = useState<string>(() => {
    const u = loadFromURL(); return u ? u.inputText : DEFAULT_FLOWS;
  });
  const [settings, setSettings] = useState<SkmSettings>(() => {
    const u = loadFromURL(); return u ? u.settings : DEFAULT_SETTINGS;
  });
  const [sidebarTab, setSidebarTab] = useState<'input' | 'settings'>('input');
  const svgRef = useRef<SVGSVGElement>(null);

  // Debounce input for diagram rendering (500ms)
  const debouncedInput = useDebounce(inputText, 500);

  // Parse the debounced input
  const parseResult = React.useMemo(() => {
    return parseInput(debouncedInput);
  }, [debouncedInput]);

  const { parsed } = parseResult;

  // URL sync: update whenever input or settings change (debounced 1s for input)
  const debouncedInputForURL = useDebounce(inputText, 1000);

  useEffect(() => {
    const encoded = encodeForURL(debouncedInputForURL, settings);
    setURLParam(encoded);
  }, [debouncedInputForURL, settings]);

  const handleSettingsChange = useCallback((updates: Partial<SkmSettings>) => {
    setSettings(prev => ({ ...prev, ...updates }));
  }, []);

  const handleLoadExample = useCallback((flows: string, exSettings: Partial<SkmSettings>) => {
    setInputText(flows);
    setSettings(prev => applyPartialSettings(DEFAULT_SETTINGS, exSettings));
  }, []);

  const handleFileLoad = useCallback((content: string) => {
    // Parse file content for flows + embedded settings
    const result = parseInput(content);
    setInputText(result.flowsText.trim() || content);
    if (Object.keys(result.settings).length > 0) {
      setSettings(prev => applyPartialSettings(prev, result.settings));
    }
  }, []);

  const errors = parsed.errors;

  // Imbalance detection
  const imbalances = React.useMemo(() => {
    if (!settings.meta_listimbalances) return [];
    const inFlow = new Map<string, number>();
    const outFlow = new Map<string, number>();
    for (const f of parsed.flows) {
      if (typeof f.amount !== 'number') continue;
      outFlow.set(f.source, (outFlow.get(f.source) || 0) + f.amount);
      inFlow.set(f.target, (inFlow.get(f.target) || 0) + f.amount);
    }
    const msgs: string[] = [];
    const allNodes = new Set([...inFlow.keys(), ...outFlow.keys()]);
    for (const n of allNodes) {
      const inn = inFlow.get(n) || 0;
      const out = outFlow.get(n) || 0;
      if (inn > 0 && out > 0 && Math.abs(inn - out) > 0.001) {
        msgs.push(`${n}: in=${inn.toFixed(2)}, out=${out.toFixed(2)}`);
      }
    }
    return msgs;
  }, [parsed.flows, settings.meta_listimbalances]);

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-80 flex-shrink-0 flex flex-col bg-gray-800 border-r border-gray-700 overflow-hidden">
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-700 bg-gray-850">
          <h1 className="text-sm font-bold text-white tracking-wide">
            Sankey Diagram Builder
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">Interactive flow visualization</p>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700">
          <button
            onClick={() => setSidebarTab('input')}
            className={`flex-1 py-2 text-xs font-medium transition-colors ${
              sidebarTab === 'input'
                ? 'bg-gray-900 text-white border-b-2 border-indigo-500'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-750'
            }`}
          >
            Input
          </button>
          <button
            onClick={() => setSidebarTab('settings')}
            className={`flex-1 py-2 text-xs font-medium transition-colors ${
              sidebarTab === 'settings'
                ? 'bg-gray-900 text-white border-b-2 border-indigo-500'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-750'
            }`}
          >
            Settings
          </button>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-4 min-h-0">
          {sidebarTab === 'input' ? (
            <InputPanel
              value={inputText}
              onChange={setInputText}
              onLoadExample={handleLoadExample}
              onFileLoad={handleFileLoad}
            />
          ) : (
            <SettingsPanel settings={settings} onChange={handleSettingsChange} />
          )}
        </div>

        {/* Export */}
        <div className="border-t border-gray-700 p-4 bg-gray-850">
          <ExportButtons
            svgRef={svgRef}
            settings={settings}
            flowsText={inputText}
          />
        </div>

        {/* Errors / warnings */}
        {(errors.length > 0 || imbalances.length > 0) && (
          <div className="border-t border-gray-700 px-4 py-3 bg-gray-900 max-h-32 overflow-y-auto">
            {errors.map((e, i) => (
              <p key={i} className="text-xs text-red-400 mb-1">{e}</p>
            ))}
            {imbalances.map((m, i) => (
              <p key={i} className="text-xs text-yellow-400 mb-1">Imbalance: {m}</p>
            ))}
          </div>
        )}
      </aside>

      {/* Main diagram area */}
      <main className="flex-1 flex flex-col bg-white overflow-hidden">
        {/* Diagram header bar */}
        <div className="h-10 flex items-center justify-between px-4 border-b border-gray-200 bg-gray-50 flex-shrink-0">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="w-2 h-2 rounded-full bg-green-400"></span>
            <span>
              {parsed.flows.length} flows, {parsed.nodeDefs.size} custom nodes
            </span>
          </div>
          <div className="text-xs text-gray-400">
            {settings.size_w} × {settings.size_h}
          </div>
        </div>

        {/* Diagram canvas */}
        <div className="flex-1 flex items-center justify-center overflow-auto p-6 bg-gray-50">
          <div
            className="shadow-xl rounded-sm overflow-hidden"
            style={{
              background: settings.bg_transparent ? 'transparent' : settings.bg_color,
              maxWidth: '100%',
              maxHeight: '100%',
            }}
          >
            <SankeyDiagram
              flows={parsed.flows}
              nodeDefs={parsed.nodeDefs}
              settings={settings}
              svgRef={svgRef}
            />
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;
