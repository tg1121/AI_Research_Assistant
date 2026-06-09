import { useEffect, useRef } from 'react';
import { pdfUrl } from '../api';

const PDFJS_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174';

function ensurePdfjsLoaded() {
  if (window.pdfjsLib) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `${PDFJS_CDN}/pdf.min.js`;
    script.onload = () => {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS_CDN}/pdf.worker.min.js`;
      resolve();
    };
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

export default function PdfViewer({ paperId, targetPage }) {
  const containerRef = useRef(null);

  // Render all pages when paperId changes
  useEffect(() => {
    if (!paperId) return;
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    container.innerHTML = '<div style="padding:20px;color:#9CA3AF">Loading PDF…</div>';

    const render = async () => {
      await ensurePdfjsLoaded();
      if (cancelled) return;

      const url = pdfUrl(paperId);
      let pdf;
      try {
        pdf = await window.pdfjsLib.getDocument(url).promise;
      } catch (err) {
        if (!cancelled)
          container.innerHTML = `<div style="padding:20px;color:#EF4444">Failed to load PDF: ${err.message}</div>`;
        return;
      }
      if (cancelled) return;

      container.innerHTML = '';
      const containerWidth = container.clientWidth - 20;

      for (let i = 1; i <= pdf.numPages; i++) {
        if (cancelled) break;
        const page = await pdf.getPage(i);
        const vp0   = page.getViewport({ scale: 1 });
        const scale = containerWidth / vp0.width;
        const dpr   = window.devicePixelRatio || 1;
        const vp    = page.getViewport({ scale: scale * dpr });

        const canvas = document.createElement('canvas');
        canvas.width  = vp.width;
        canvas.height = vp.height;
        canvas.dataset.page = i;   // ← stamped for scroll-to
        canvas.style.cssText = [
          'display:block',
          `width:${vp.width / dpr}px`,
          `height:${vp.height / dpr}px`,
          'margin:0 auto 10px',
          'box-shadow:0 2px 8px rgba(0,0,0,0.5)',
        ].join(';');

        container.appendChild(canvas);
        if (!cancelled)
          await page.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise;
      }
    };

    render();
    return () => { cancelled = true; };
  }, [paperId]);

  // Scroll to targetPage when it changes
  useEffect(() => {
    if (!targetPage || !containerRef.current) return;
    const canvas = containerRef.current.querySelector(`[data-page="${targetPage}"]`);
    if (canvas) canvas.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [targetPage]);

  return (
    <div
      ref={containerRef}
      style={{ background: '#525659', padding: 10, height: '100%', overflowY: 'auto' }}
    />
  );
}
