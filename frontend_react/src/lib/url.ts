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
