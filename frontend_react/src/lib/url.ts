import LZString from 'lz-string';
import type { SkmSettings } from '../types';
import { serializeSettings } from './settings';

export function encodeForURL(flowsText: string, settings: SkmSettings): string {
  const settingsText = serializeSettings(settings);
  const combined = flowsText + '\n' + settingsText;
  return LZString.compressToEncodedURIComponent(combined);
}

export function decodeFromURL(param: string): string | null {
  try {
    return LZString.decompressFromEncodedURIComponent(param);
  } catch {
    return null;
  }
}

export function getURLParam(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get('i');
}

export function setURLParam(value: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set('i', value);
  window.history.replaceState(null, '', url.toString());
}

export function buildShareableURL(flowsText: string, settings: SkmSettings): string {
  const encoded = encodeForURL(flowsText, settings);
  const url = new URL(window.location.href);
  url.searchParams.set('i', encoded);
  return url.toString();
}

// Generic query-param helpers (unlike getURLParam/setURLParam above, which
// are hardcoded to the Sankeymatic-specific "i" payload param) — used by the
// top-level mode switch (?tab=) and the budget dashboard's month picker
// (?month=).
export function getQueryParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

export function setQueryParam(name: string, value: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set(name, value);
  window.history.replaceState(null, '', url.toString());
}

// Used when a param's absence itself means something (e.g. no "?range="
// means single-month mode) — setQueryParam alone can't express "remove this".
export function deleteQueryParam(name: string): void {
  const url = new URL(window.location.href);
  url.searchParams.delete(name);
  window.history.replaceState(null, '', url.toString());
}
