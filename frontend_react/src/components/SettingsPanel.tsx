import React, { useState } from 'react';
import type { SkmSettings } from '../types';

interface Props {
  settings: SkmSettings;
  onChange: (updates: Partial<SkmSettings>) => void;
}

// Collapsible section wrapper
const Section: React.FC<{
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}> = ({ title, defaultOpen = false, children }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-gray-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-800 hover:bg-gray-750 text-left text-sm font-semibold text-gray-200 transition-colors"
      >
        <span>{title}</span>
        <span className="text-gray-500 text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="bg-gray-850 px-4 py-3 space-y-3">
          {children}
        </div>
      )}
    </div>
  );
};

// Helper row components
const Row: React.FC<{ label: string; children: React.ReactNode; className?: string }> = ({
  label, children, className = ''
}) => (
  <div className={`flex items-center justify-between gap-3 ${className}`}>
    <label className="text-xs text-gray-400 flex-shrink-0 w-28">{label}</label>
    <div className="flex-1 flex items-center justify-end gap-2">{children}</div>
  </div>
);

const NumberInput: React.FC<{
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
  className?: string;
}> = ({ value, min, max, step = 1, onChange, className = '' }) => (
  <input
    type="number"
    value={value}
    min={min}
    max={max}
    step={step}
    onChange={e => {
      const n = parseFloat(e.target.value);
      if (!isNaN(n)) onChange(n);
    }}
    className={`w-20 bg-gray-900 text-gray-100 border border-gray-700 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 ${className}`}
  />
);

const ColorInput: React.FC<{
  value: string;
  onChange: (v: string) => void;
}> = ({ value, onChange }) => (
  <div className="flex items-center gap-2">
    <input
      type="color"
      value={value.length === 4 || value.length === 7 ? value : '#888888'}
      onChange={e => onChange(e.target.value)}
      className="w-8 h-7 rounded cursor-pointer border border-gray-600 bg-gray-900 p-0.5"
    />
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-20 bg-gray-900 text-gray-100 border border-gray-700 rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500"
      maxLength={7}
      placeholder="#rrggbb"
    />
  </div>
);

const SliderInput: React.FC<{
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  showValue?: boolean;
}> = ({ value, min, max, step = 1, onChange, showValue = true }) => (
  <div className="flex items-center gap-2 flex-1">
    <input
      type="range"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={e => onChange(parseFloat(e.target.value))}
      className="flex-1 accent-indigo-500 h-1.5 rounded"
    />
    {showValue && (
      <span className="text-xs text-gray-400 w-10 text-right">{value}</span>
    )}
  </div>
);

const CheckBox: React.FC<{
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}> = ({ checked, onChange, label }) => (
  <label className="flex items-center gap-2 cursor-pointer">
    <input
      type="checkbox"
      checked={checked}
      onChange={e => onChange(e.target.checked)}
      className="w-3.5 h-3.5 accent-indigo-500 cursor-pointer"
    />
    {label && <span className="text-xs text-gray-300">{label}</span>}
  </label>
);

const RadioGroup: React.FC<{
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}> = ({ value, options, onChange }) => (
  <div className="flex flex-wrap gap-2">
    {options.map(opt => (
      <label key={opt.value} className="flex items-center gap-1.5 cursor-pointer">
        <input
          type="radio"
          value={opt.value}
          checked={value === opt.value}
          onChange={() => onChange(opt.value)}
          className="accent-indigo-500 w-3 h-3"
        />
        <span className="text-xs text-gray-300">{opt.label}</span>
      </label>
    ))}
  </div>
);

const SelectInput: React.FC<{
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}> = ({ value, options, onChange }) => (
  <select
    value={value}
    onChange={e => onChange(e.target.value)}
    className="bg-gray-900 text-gray-100 border border-gray-700 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
  >
    {options.map(opt => (
      <option key={opt.value} value={opt.value}>{opt.label}</option>
    ))}
  </select>
);

const SettingsPanel: React.FC<Props> = ({ settings, onChange }) => {
  const upd = <K extends keyof SkmSettings>(key: K) => (val: SkmSettings[K]) => {
    onChange({ [key]: val } as Partial<SkmSettings>);
  };

  return (
    <div className="space-y-2">

      {/* Canvas */}
      <Section title="Canvas" defaultOpen>
        <Row label="Width">
          <NumberInput value={settings.size_w} min={40} onChange={upd('size_w')} />
        </Row>
        <Row label="Height">
          <NumberInput value={settings.size_h} min={40} onChange={upd('size_h')} />
        </Row>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Row label="Margin L">
            <NumberInput value={settings.margin_l} min={0} onChange={upd('margin_l')} />
          </Row>
          <Row label="Margin R">
            <NumberInput value={settings.margin_r} min={0} onChange={upd('margin_r')} />
          </Row>
          <Row label="Margin T">
            <NumberInput value={settings.margin_t} min={0} onChange={upd('margin_t')} />
          </Row>
          <Row label="Margin B">
            <NumberInput value={settings.margin_b} min={0} onChange={upd('margin_b')} />
          </Row>
        </div>
        <Row label="Background">
          <ColorInput value={settings.bg_color} onChange={upd('bg_color')} />
        </Row>
        <Row label="">
          <CheckBox
            checked={settings.bg_transparent}
            onChange={upd('bg_transparent')}
            label="Transparent background"
          />
        </Row>
      </Section>

      {/* Nodes */}
      <Section title="Nodes">
        <Row label="Width">
          <NumberInput value={settings.node_w} min={0} onChange={upd('node_w')} />
        </Row>
        <Row label="Height">
          <SliderInput value={settings.node_h} min={0} max={100} onChange={upd('node_h')} />
        </Row>
        <Row label="Spacing">
          <SliderInput value={settings.node_spacing} min={0} max={100} onChange={upd('node_spacing')} />
        </Row>
        <Row label="Border">
          <NumberInput value={settings.node_border} min={0} onChange={upd('node_border')} />
        </Row>
        <Row label="Color theme">
          <RadioGroup
            value={settings.node_theme}
            options={[
              { value: 'none', label: 'None' },
              { value: 'a', label: 'A' },
              { value: 'b', label: 'B' },
              { value: 'c', label: 'C' },
              { value: 'd', label: 'D' },
            ]}
            onChange={v => onChange({ node_theme: v as SkmSettings['node_theme'] })}
          />
        </Row>
        {settings.node_theme === 'none' && (
          <Row label="Node color">
            <ColorInput value={settings.node_color} onChange={upd('node_color')} />
          </Row>
        )}
        {settings.node_theme !== 'none' && (
          <Row label="Theme offset">
            <NumberInput
              value={(settings as unknown as Record<string, number>)[`themeoffset_${settings.node_theme}`]}
              min={0}
              max={settings.node_theme === 'd' ? 11 : settings.node_theme === 'c' ? 7 : 9}
              onChange={v => onChange({ [`themeoffset_${settings.node_theme}`]: v } as Partial<SkmSettings>)}
            />
          </Row>
        )}
        <Row label="Opacity">
          <SliderInput
            value={Math.round(settings.node_opacity * 100)}
            min={0} max={100}
            onChange={v => upd('node_opacity')(v / 100)}
          />
        </Row>
      </Section>

      {/* Flows */}
      <Section title="Flows">
        <Row label="Curvature">
          <SliderInput
            value={Math.round(settings.flow_curvature * 100)}
            min={0} max={100}
            onChange={v => upd('flow_curvature')(v / 100)}
          />
        </Row>
        <Row label="Inherit color">
          <SelectInput
            value={settings.flow_inheritfrom}
            options={[
              { value: 'none', label: 'None' },
              { value: 'source', label: 'From source' },
              { value: 'target', label: 'From target' },
              { value: 'outside-in', label: 'Outside-in' },
            ]}
            onChange={v => onChange({ flow_inheritfrom: v as SkmSettings['flow_inheritfrom'] })}
          />
        </Row>
        <Row label="Flow color">
          <ColorInput value={settings.flow_color} onChange={upd('flow_color')} />
        </Row>
        <Row label="Opacity">
          <SliderInput
            value={Math.round(settings.flow_opacity * 100)}
            min={0} max={100}
            onChange={v => upd('flow_opacity')(v / 100)}
          />
        </Row>
      </Section>

      {/* Layout */}
      <Section title="Layout">
        <Row label="Order">
          <RadioGroup
            value={settings.layout_order}
            options={[
              { value: 'automatic', label: 'Automatic' },
              { value: 'exact', label: 'Exact input order' },
            ]}
            onChange={v => onChange({ layout_order: v as SkmSettings['layout_order'] })}
          />
        </Row>
        <Row label="">
          <CheckBox
            checked={settings.layout_justifyorigins}
            onChange={upd('layout_justifyorigins')}
            label="Justify origins (left)"
          />
        </Row>
        <Row label="">
          <CheckBox
            checked={settings.layout_justifyends}
            onChange={upd('layout_justifyends')}
            label="Justify ends (right)"
          />
        </Row>
        <Row label="">
          <CheckBox
            checked={settings.layout_reversegraph}
            onChange={upd('layout_reversegraph')}
            label="Reverse graph direction"
          />
        </Row>
        <Row label="Incomplete nodes">
          <SelectInput
            value={settings.layout_attachincompletesto}
            options={[
              { value: 'leading', label: 'Leading' },
              { value: 'nearest', label: 'Nearest' },
              { value: 'trailing', label: 'Trailing' },
            ]}
            onChange={v => onChange({ layout_attachincompletesto: v as SkmSettings['layout_attachincompletesto'] })}
          />
        </Row>
        <Row label="Iterations">
          <NumberInput value={settings.internal_iterations} min={0} max={50} onChange={upd('internal_iterations')} />
        </Row>
      </Section>

      {/* Labels */}
      <Section title="Labels">
        <Row label="">
          <CheckBox
            checked={settings.labels_hide}
            onChange={upd('labels_hide')}
            label="Hide all labels"
          />
        </Row>
        <Row label="Font">
          <RadioGroup
            value={settings.labels_fontface}
            options={[
              { value: 'sans-serif', label: 'Sans' },
              { value: 'serif', label: 'Serif' },
              { value: 'monospace', label: 'Mono' },
            ]}
            onChange={v => onChange({ labels_fontface: v as SkmSettings['labels_fontface'] })}
          />
        </Row>
        <Row label="Color">
          <ColorInput value={settings.labels_color} onChange={upd('labels_color')} />
        </Row>
        <Row label="Highlight">
          <SliderInput
            value={Math.round(settings.labels_highlight * 100)}
            min={0} max={100}
            onChange={v => upd('labels_highlight')(v / 100)}
          />
        </Row>
        <div className="pt-1 border-t border-gray-700">
          <p className="text-xs text-gray-500 mb-2">Names</p>
          <Row label="">
            <CheckBox
              checked={settings.labelname_appears}
              onChange={upd('labelname_appears')}
              label="Show names"
            />
          </Row>
          <Row label="Size">
            <NumberInput value={settings.labelname_size} min={6} step={0.5} onChange={upd('labelname_size')} />
          </Row>
          <Row label="Weight">
            <SliderInput
              value={settings.labelname_weight}
              min={100} max={700} step={300}
              onChange={upd('labelname_weight')}
            />
          </Row>
        </div>
        <div className="pt-1 border-t border-gray-700">
          <p className="text-xs text-gray-500 mb-2">Values</p>
          <Row label="">
            <CheckBox
              checked={settings.labelvalue_appears}
              onChange={upd('labelvalue_appears')}
              label="Show values"
            />
          </Row>
          <Row label="Position">
            <SelectInput
              value={settings.labelvalue_position}
              options={[
                { value: 'above', label: 'Above' },
                { value: 'below', label: 'Below' },
                { value: 'before', label: 'Before' },
                { value: 'after', label: 'After' },
              ]}
              onChange={v => onChange({ labelvalue_position: v as SkmSettings['labelvalue_position'] })}
            />
          </Row>
          <Row label="Weight">
            <SliderInput
              value={settings.labelvalue_weight}
              min={100} max={700} step={300}
              onChange={upd('labelvalue_weight')}
            />
          </Row>
        </div>
        <div className="pt-1 border-t border-gray-700">
          <p className="text-xs text-gray-500 mb-2">Size scales</p>
          <Row label="Rel. size">
            <SliderInput value={settings.labels_relativesize} min={50} max={150} onChange={upd('labels_relativesize')} />
          </Row>
          <Row label="Magnify">
            <SliderInput value={settings.labels_magnify} min={50} max={150} onChange={upd('labels_magnify')} />
          </Row>
        </div>
      </Section>

      {/* Values */}
      <Section title="Values">
        <Row label="Format">
          <SelectInput
            value={settings.value_format}
            options={[
              { value: ',.', label: '1,234.56 (US)' },
              { value: '.,', label: '1.234,56 (EU)' },
              { value: ' .', label: '1 234.56' },
              { value: ' ,', label: '1 234,56' },
              { value: 'X.', label: '1234.56 (no sep)' },
              { value: 'X,', label: '1234,56 (no sep)' },
            ]}
            onChange={upd('value_format')}
          />
        </Row>
        <Row label="Prefix">
          <input
            type="text"
            value={settings.value_prefix}
            onChange={e => upd('value_prefix')(e.target.value)}
            className="w-24 bg-gray-900 text-gray-100 border border-gray-700 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="e.g. $"
            maxLength={99}
          />
        </Row>
        <Row label="Suffix">
          <input
            type="text"
            value={settings.value_suffix}
            onChange={e => upd('value_suffix')(e.target.value)}
            className="w-24 bg-gray-900 text-gray-100 border border-gray-700 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="e.g. %"
            maxLength={99}
          />
        </Row>
        <Row label="">
          <CheckBox
            checked={settings.labelvalue_fullprecision}
            onChange={upd('labelvalue_fullprecision')}
            label="Full precision"
          />
        </Row>
      </Section>

      {/* Meta */}
      <Section title="Other">
        <Row label="">
          <CheckBox
            checked={settings.meta_mentionwebsite}
            onChange={upd('meta_mentionwebsite')}
            label="Show 'sankeymatic.com'"
          />
        </Row>
        <Row label="">
          <CheckBox
            checked={settings.meta_listimbalances}
            onChange={upd('meta_listimbalances')}
            label="List imbalances"
          />
        </Row>
      </Section>
    </div>
  );
};

export default SettingsPanel;
