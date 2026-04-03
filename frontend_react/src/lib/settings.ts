import type { SkmSettings } from '../types';

export const DEFAULT_SETTINGS: SkmSettings = {
  size_w: 600,
  size_h: 600,
  margin_l: 12,
  margin_r: 12,
  margin_t: 18,
  margin_b: 20,
  bg_color: '#ffffff',
  bg_transparent: false,
  node_w: 9,
  node_h: 50,
  node_spacing: 85,
  node_border: 0,
  node_theme: 'none',
  node_color: '#888888',
  node_opacity: 1.0,
  flow_curvature: 0.5,
  flow_inheritfrom: 'outside-in',
  flow_color: '#999999',
  flow_opacity: 0.45,
  layout_order: 'automatic',
  layout_justifyorigins: false,
  layout_justifyends: false,
  layout_reversegraph: false,
  layout_attachincompletesto: 'nearest',
  labels_color: '#000000',
  labels_hide: false,
  labels_highlight: 0.75,
  labels_fontface: 'sans-serif',
  labels_linespacing: 0.15,
  labels_relativesize: 100,
  labels_magnify: 100,
  labelname_appears: true,
  labelname_size: 16,
  labelname_weight: 400,
  labelvalue_appears: true,
  labelvalue_fullprecision: true,
  labelvalue_position: 'below',
  labelvalue_weight: 400,
  labelposition_autoalign: 0,
  labelposition_scheme: 'auto',
  labelposition_first: 'before',
  labelposition_breakpoint: 9999,
  value_format: ',.',
  value_prefix: '',
  value_suffix: '',
  themeoffset_a: 9,
  themeoffset_b: 0,
  themeoffset_c: 0,
  themeoffset_d: 0,
  meta_mentionwebsite: true,
  meta_listimbalances: true,
  internal_iterations: 25,
  internal_revealshadows: false,
};

// Settings ordering for serialization (matches original sankeymatic order)
const SETTINGS_ORDER: (keyof SkmSettings)[] = [
  'size_w', 'size_h',
  'margin_l', 'margin_r', 'margin_t', 'margin_b',
  'bg_color', 'bg_transparent',
  'node_w', 'node_h', 'node_spacing', 'node_border',
  'node_theme', 'node_color', 'node_opacity',
  'flow_curvature', 'flow_inheritfrom', 'flow_color', 'flow_opacity',
  'layout_order', 'layout_justifyorigins', 'layout_justifyends',
  'layout_reversegraph', 'layout_attachincompletesto',
  'labels_color', 'labels_hide', 'labels_highlight',
  'labels_fontface', 'labels_linespacing', 'labels_relativesize', 'labels_magnify',
  'labelname_appears', 'labelname_size', 'labelname_weight',
  'labelvalue_appears', 'labelvalue_fullprecision', 'labelvalue_position', 'labelvalue_weight',
  'labelposition_autoalign', 'labelposition_scheme', 'labelposition_first', 'labelposition_breakpoint',
  'value_format', 'value_prefix', 'value_suffix',
  'themeoffset_a', 'themeoffset_b', 'themeoffset_c', 'themeoffset_d',
  'meta_mentionwebsite', 'meta_listimbalances',
  'internal_iterations', 'internal_revealshadows',
];

function settingKeyToLine(key: keyof SkmSettings): string {
  // Convert size_w -> "size w", node_theme -> "node theme", etc.
  return key.replace(/_/g, ' ');
}

function boolToYN(val: boolean): string {
  return val ? 'y' : 'n';
}

function settingValueToString(key: keyof SkmSettings, val: unknown): string {
  if (typeof val === 'boolean') return boolToYN(val);
  if (key === 'value_prefix' || key === 'value_suffix') return `'${val}'`;
  return String(val);
}

export function serializeSettings(settings: SkmSettings): string {
  const lines: string[] = [];
  for (const key of SETTINGS_ORDER) {
    const val = settings[key];
    const lineKey = settingKeyToLine(key);
    const lineVal = settingValueToString(key, val);
    lines.push(`${lineKey} ${lineVal}`);
  }
  return lines.join('\n');
}

// Parse a group+key token string into a full settings key
// e.g. "size w" -> "size_w", "bg transparent" -> "bg_transparent"
function tokenToKey(token: string): keyof SkmSettings | null {
  const normalized = token.trim().replace(/\s+/g, '_').toLowerCase();

  // Direct match
  if (normalized in DEFAULT_SETTINGS) {
    return normalized as keyof SkmSettings;
  }

  // Try expanding abbreviations
  const expanded = normalized
    .replace(/\bw\b/, 'w')
    .replace(/\bh\b/, 'h')
    .replace(/\bl\b/, 'l')
    .replace(/\br\b/, 'r')
    .replace(/\bt\b/, 't')
    .replace(/\bb\b/, 'b');

  if (expanded in DEFAULT_SETTINGS) {
    return expanded as keyof SkmSettings;
  }

  return null;
}

function parseYN(val: string): boolean {
  return /^(?:y|yes)/i.test(val);
}

function parseSettingValue(key: keyof SkmSettings, rawVal: string): unknown {
  const def = DEFAULT_SETTINGS[key];
  if (typeof def === 'boolean') {
    return parseYN(rawVal);
  }
  if (typeof def === 'number') {
    const n = parseFloat(rawVal);
    return isNaN(n) ? def : n;
  }
  // string
  return rawVal;
}

export function parseSettingsFromLines(lines: string[]): Partial<SkmSettings> {
  const out: Partial<SkmSettings> = {};

  // reSettingsValue: one or two words then value (no quotes)
  const reSettingsValue = /^((?:\w+\s*){1,3})\s+(#?[\w.,-]+)$/;
  // reSettingsText: one or two words then 'quoted value'
  const reSettingsText = /^((?:\w+\s*){1,3})\s+'(.*)'$/;

  let lastGroup = '';

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;

    // Try text match first (for value_prefix / value_suffix)
    const textMatch = reSettingsText.exec(line);
    if (textMatch) {
      const [, keyPart, val] = textMatch;
      let key = tokenToKey(keyPart);
      if (!key && lastGroup) {
        key = tokenToKey(`${lastGroup} ${keyPart}`);
      }
      if (key) {
        (out as Record<string, unknown>)[key] = val;
        lastGroup = key.split('_')[0];
      }
      continue;
    }

    const valueMatch = reSettingsValue.exec(line);
    if (valueMatch) {
      const [, keyPart, val] = valueMatch;
      let key = tokenToKey(keyPart);
      if (!key && lastGroup) {
        key = tokenToKey(`${lastGroup} ${keyPart}`);
      }
      if (key) {
        (out as Record<string, unknown>)[key] = parseSettingValue(key, val);
        lastGroup = key.split('_')[0];
      }
    }
  }

  return out;
}

export function applyPartialSettings(
  base: SkmSettings,
  partial: Partial<SkmSettings>
): SkmSettings {
  return { ...base, ...partial };
}
