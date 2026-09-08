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

  // Shared by PNG and PDF export: rasterize the current SVG onto a canvas
  // at 2x scale (retina-sharp), then hand the canvas to the caller.
  const renderToCanvas = (): Promise<HTMLCanvasElement | null> => {
    const svgStr = getSvgString();
    if (!svgStr) return Promise.resolve(null);

    const { size_w, size_h } = settings;
    const scale = 2;

    const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);

    return new Promise(resolve => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = size_w * scale;
        canvas.height = size_h * scale;
        const ctx = canvas.getContext('2d');
        URL.revokeObjectURL(url);
        if (!ctx) { resolve(null); return; }
        ctx.scale(scale, scale);
        ctx.drawImage(img, 0, 0);
        resolve(canvas);
      };
      img.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
      img.src = url;
    });
  };

  const downloadPNG = async () => {
    const canvas = await renderToCanvas();
    if (!canvas) return;
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

  const downloadPDF = async () => {
    // jsPDF pulls in html2canvas + DOMPurify as part of its bundle even
    // though addImage()/save() don't need either — lazy-load it so that
    // weight (~400KB) only hits users who actually click "PDF", not every
    // page load (2026-08-01).
    const [{ default: jsPDF }, canvas] = await Promise.all([import('jspdf'), renderToCanvas()]);
    if (!canvas) return;
    const { size_w, size_h } = settings;
    const pdf = new jsPDF({
      orientation: size_w >= size_h ? 'landscape' : 'portrait',
      unit: 'px',
      format: [size_w, size_h],
    });
    // JPEG, not PNG — an uncompressed PNG at 2x scale produced a ~13MB PDF;
    // JPEG at high quality looks identical for this mostly-solid-color
    // content at a fraction of the size (2026-08-01). Only when the
    // background is deliberately transparent does that matter — JPEG has no
    // alpha channel and would flatten it to black, so PNG stays the fallback
    // for that case (Sankey Builder supports transparent-background export;
    // the dashboard never enables it).
    if (settings.bg_transparent) {
      pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, size_w, size_h);
    } else {
      pdf.addImage(canvas.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, size_w, size_h);
    }
    pdf.save('sankey-diagram.pdf');
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
  const secondaryClass = `${btnClass} bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200 border-gray-300 dark:border-gray-600`;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Export</p>
      <div className="flex gap-2">
        <button onClick={downloadSVG} className={secondaryClass} title="Download as SVG vector file">
          SVG
        </button>
        <button onClick={downloadPNG} className={secondaryClass} title="Download as PNG image (2x)">
          PNG
        </button>
        <button onClick={downloadPDF} className={secondaryClass} title="Download as PDF">
          PDF
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
