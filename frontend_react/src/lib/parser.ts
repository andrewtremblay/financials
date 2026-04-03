import type { ParsedInput, FlowLine, NodeDef, MoveDef } from '../types';
import { parseSettingsFromLines, DEFAULT_SETTINGS } from './settings';
import type { SkmSettings } from '../types';

// Regex patterns matching constants.js
const reCommentLine = /^(?:'|\/\/)/;
const reNodeLine = /^:(.+?)\s*(?:(#[a-fA-F0-9]{0,6})?(\.\d{1,4})?)?\s*(?:>>|<<)*\s*(?:>>|<<)*\s*$/;
const reMoveLine = /^move (.+) (-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)$/;
// Flow line: Source [amount] Target or Source [amount] Target #color.opacity
const reFlowLine = /^(.+?)\s+\[([^\]]+)\]\s+(.+?)(?:\s+(#[a-fA-F0-9]{0,6}(?:\.\d{1,4})?))?$/;
const reSettingsValue = /^((?:\w+\s*){1,3})\s+(#?[\w.,-]+)$/;
const reSettingsText = /^((?:\w+\s*){1,3})\s+'(.*)'$/;
const reColorPlusOpacity = /^(#[a-fA-F0-9]{3,6})?(\.\d{1,4})?$/;

function parseColorOpacity(raw: string): { color?: string; opacity?: number } {
  if (!raw) return {};
  const m = reColorPlusOpacity.exec(raw);
  if (!m) return {};
  const color = m[1] || undefined;
  const opacity = m[2] ? parseFloat(m[2]) : undefined;
  return { color, opacity };
}

function parseAmount(raw: string): number | '*' | '?' | null {
  const trimmed = raw.trim();
  if (trimmed === '*') return '*';
  if (trimmed === '?') return '?';
  const n = parseFloat(trimmed);
  if (isNaN(n)) return null;
  return n;
}

export interface FullParseResult {
  parsed: ParsedInput;
  settings: Partial<SkmSettings>;
  flowsText: string; // just the flow/node/move lines (no settings lines)
}

export function parseInput(text: string): FullParseResult {
  const flows: FlowLine[] = [];
  const nodeDefs = new Map<string, NodeDef>();
  const moves: MoveDef[] = [];
  const errors: string[] = [];
  const settingLines: string[] = [];
  const flowLinesList: string[] = [];

  const lines = text.split('\n');

  for (const rawLine of lines) {
    const line = rawLine.trim();

    // Empty line
    if (!line) {
      flowLinesList.push(rawLine);
      continue;
    }

    // Comment line (including applied settings "// ✓ ...")
    if (reCommentLine.test(line)) {
      flowLinesList.push(rawLine);
      continue;
    }

    // Move line
    const moveMatch = reMoveLine.exec(line);
    if (moveMatch) {
      moves.push({
        name: moveMatch[1].trim(),
        x: parseFloat(moveMatch[2]),
        y: parseFloat(moveMatch[3]),
      });
      flowLinesList.push(rawLine);
      continue;
    }

    // Node definition: :NodeName #color.opacity
    if (line.startsWith(':')) {
      const nodeMatch = reNodeLine.exec(line);
      if (nodeMatch) {
        const name = nodeMatch[1].trim();
        const colorPart = nodeMatch[2] || '';
        const opacityPart = nodeMatch[3] || '';
        const color = colorPart || undefined;
        const opacity = opacityPart ? parseFloat(opacityPart) : undefined;
        nodeDefs.set(name, { name, color, opacity });
        flowLinesList.push(rawLine);
        continue;
      }
    }

    // Flow line: Source [amount] Target [optional #color]
    const flowMatch = reFlowLine.exec(line);
    if (flowMatch) {
      const sourcePart = flowMatch[1].trim();
      const amountStr = flowMatch[2].trim();
      const targetAndColor = flowMatch[3].trim();
      const trailingColor = flowMatch[4];

      // The target may have an appended color e.g. "Target Node #abc.5"
      // but the regex already captures it in group 4
      const amount = parseAmount(amountStr);
      if (amount === null) {
        errors.push(`Invalid amount "${amountStr}" in line: ${line}`);
        flowLinesList.push(rawLine);
        continue;
      }

      // Parse source and target — they may contain literal \n which becomes newlines in node names
      const source = sourcePart.replace(/\\n/g, '\n');
      const target = targetAndColor.replace(/\\n/g, '\n');

      const flowLine: FlowLine = { source, amount, target };

      if (trailingColor) {
        const { color, opacity } = parseColorOpacity(trailingColor);
        if (color) flowLine.color = color;
        if (opacity !== undefined) flowLine.opacity = opacity;
      }

      flows.push(flowLine);
      flowLinesList.push(rawLine);
      continue;
    }

    // Settings line: one or two words + value
    if (reSettingsText.test(line) || reSettingsValue.test(line)) {
      settingLines.push(line);
      // Don't add to flowLinesList - settings are separated
      continue;
    }

    // Unrecognized - treat as a comment / pass-through
    flowLinesList.push(rawLine);
  }

  const settings = parseSettingsFromLines(settingLines);

  return {
    parsed: { flows, nodeDefs, moves, errors },
    settings,
    flowsText: flowLinesList.join('\n'),
  };
}

// Parse only the settings portion (for URL deserialization)
export function parseSettingsOnly(text: string): Partial<SkmSettings> {
  const lines = text.split('\n').filter(l => {
    const t = l.trim();
    return t && !reCommentLine.test(t) && !t.startsWith(':') && !reFlowLine.test(t) && !reMoveLine.test(t);
  });
  return parseSettingsFromLines(lines);
}

// Build the unique set of node names from flows + explicit nodeDefs
export function collectNodeNames(flows: FlowLine[], nodeDefs: Map<string, NodeDef>): string[] {
  const names = new Set<string>();
  for (const f of flows) {
    names.add(f.source);
    names.add(f.target);
  }
  for (const k of nodeDefs.keys()) {
    names.add(k);
  }
  return Array.from(names);
}

// Detect if a node is an origin (no incoming flows)
export function getOrigins(flows: FlowLine[]): Set<string> {
  const hasIncoming = new Set<string>();
  for (const f of flows) {
    hasIncoming.add(typeof f.target === 'string' ? f.target : '');
  }
  const origins = new Set<string>();
  for (const f of flows) {
    if (!hasIncoming.has(f.source)) origins.add(f.source);
  }
  return origins;
}

// Detect if a node is an endpoint (no outgoing flows)
export function getEndpoints(flows: FlowLine[]): Set<string> {
  const hasOutgoing = new Set<string>();
  for (const f of flows) {
    hasOutgoing.add(f.source);
  }
  const endpoints = new Set<string>();
  for (const f of flows) {
    if (!hasOutgoing.has(f.target)) endpoints.add(f.target);
  }
  return endpoints;
}

// Resolve * and ? amounts
export function resolveAmounts(flows: FlowLine[]): FlowLine[] {
  // Sum all numeric flows by source and target to compute totals for * and ?
  // For simplicity, replace * with 0 and ? with 0 when we can't compute
  // A full implementation would compute remainder but for now we use simple approach

  // First pass: collect totals per source node
  const sourceTotals = new Map<string, number>();
  const targetTotals = new Map<string, number>();

  for (const f of flows) {
    if (typeof f.amount === 'number') {
      sourceTotals.set(f.source, (sourceTotals.get(f.source) || 0) + f.amount);
      targetTotals.set(f.target, (targetTotals.get(f.target) || 0) + f.amount);
    }
  }

  return flows.map(f => {
    if (f.amount === '*' || f.amount === '?') {
      // Compute remainder: incoming total to source - sum of other outgoing flows
      const incomingToSource = targetTotals.get(f.source) || 0;
      const otherOutgoing = flows
        .filter(o => o.source === f.source && o !== f && typeof o.amount === 'number')
        .reduce((sum, o) => sum + (o.amount as number), 0);
      const remainder = Math.max(0, incomingToSource - otherOutgoing);
      return { ...f, amount: remainder };
    }
    return f;
  });
}
