import React, { useState } from 'react';
import type { SkmSettings } from '../types';
import { buildShareableURL } from '../lib/url';

interface Props {
  svgRef: React.RefObject<SVGSVGElement>;
  settings: SkmSettings;
  flowsText: string;
}

const ExportButtons: React.FC<Props> = ({ svgRef, settings, flowsText }) => {
  const [copied, setCopied] = useState(false);

  const getSvgString = (): string | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const serializer = new XMLSerializer();
    let svgStr = serializer.serializeToString(svg);
    // Ensure proper XML namespace
    if (!svgStr.includes('xmlns="http://www.w3.org/2000/svg"')) {
      svgStr = svgStr.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
    }
    return svgStr;
  };

  const downloadSVG = () => {
    const svgStr = getSvgString();
    if (!svgStr) return;
    const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sankey-diagram.svg';
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadPNG = async () => {
    const svgStr = getSvgString();
    if (!svgStr) return;

    const { size_w, size_h } = settings;
    const scale = 2; // 2x for retina

    const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);

    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = size_w * scale;
      canvas.height = size_h * scale;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      canvas.toBlob(pngBlob => {
        if (!pngBlob) return;
        const pngUrl = URL.createObjectURL(pngBlob);
        const a = document.createElement('a');
        a.href = pngUrl;
        a.download = 'sankey-diagram.png';
        a.click();
        URL.revokeObjectURL(pngUrl);
      }, 'image/png');
    };
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  };

  const copyShareURL = async () => {
    const url = buildShareableURL(flowsText, settings);
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const el = document.createElement('textarea');
      el.value = url;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const btnClass = "flex-1 px-3 py-2 text-xs font-medium rounded-md transition-colors duration-150 border";
  const primaryClass = `${btnClass} bg-indigo-600 hover:bg-indigo-500 text-white border-indigo-500`;
  const secondaryClass = `${btnClass} bg-gray-700 hover:bg-gray-600 text-gray-200 border-gray-600`;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Export</p>
      <div className="flex gap-2">
        <button onClick={downloadSVG} className={secondaryClass} title="Download as SVG vector file">
          SVG
        </button>
        <button onClick={downloadPNG} className={secondaryClass} title="Download as PNG image (2x)">
          PNG
        </button>
        <button
          onClick={copyShareURL}
          className={primaryClass}
          title="Copy shareable URL with diagram encoded"
        >
          {copied ? 'Copied!' : 'Copy URL'}
        </button>
      </div>
    </div>
  );
};

export default ExportButtons;
