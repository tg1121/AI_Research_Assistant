import { useEffect, useRef, useState } from 'react';
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

const STEP = 0.15;
const MIN  = 0.5;
const MAX  = 4.0;
const clamp = v => Math.min(MAX, Math.max(MIN, v));

export default function PdfViewer({ paperId, targetPage }) {
  const outerRef  = useRef(null);   // scroll container — never zoomed
  const innerRef  = useRef(null);   // pages wrapper — CSS zoom for instant preview
  const pdfDocRef = useRef(null);   // cached pdfjs document

  const [zoom, setZoom]             = useState(1);   // live — updates on every gesture tick
  const [renderZoom, setRenderZoom] = useState(1);   // debounced — triggers canvas re-render

  // Debounce: re-render canvas only after 300 ms of no gesture (Chrome does the same)
  useEffect(() => {
    const t = setTimeout(() => setRenderZoom(zoom), 300);
    return () => clearTimeout(t);
  }, [zoom]);

  // Canvas re-render — uses outerRef width so CSS zoom on innerRef doesn't affect it
  useEffect(() => {
    if (!paperId) return;
    const inner = innerRef.current;
    const outer = outerRef.current;
    if (!inner || !outer) return;

    let cancelled = false;
    inner.innerHTML = '<div style="padding:20px;color:#9CA3AF">Loading PDF…</div>';

    const render = async () => {
      await ensurePdfjsLoaded();
      if (cancelled) return;

      if (!pdfDocRef.current || pdfDocRef.current._paperId !== paperId) {
        try {
          const doc = await window.pdfjsLib.getDocument(pdfUrl(paperId)).promise;
          doc._paperId = paperId;
          pdfDocRef.current = doc;
        } catch (err) {
          if (!cancelled)
            inner.innerHTML = `<div style="padding:20px;color:#EF4444">Failed to load PDF: ${err.message}</div>`;
          return;
        }
      }
      if (cancelled) return;

      const pdf = pdfDocRef.current;
      inner.innerHTML = '';
      // Use outerRef width — unaffected by CSS zoom on innerRef
      const containerWidth = outer.clientWidth - 20;

      for (let i = 1; i <= pdf.numPages; i++) {
        if (cancelled) break;
        const page  = await pdf.getPage(i);
        const vp0   = page.getViewport({ scale: 1 });
        const scale = (containerWidth / vp0.width) * renderZoom;
        const dpr   = window.devicePixelRatio || 1;
        const vp    = page.getViewport({ scale: scale * dpr });

        const canvas = document.createElement('canvas');
        canvas.width  = vp.width;
        canvas.height = vp.height;
        canvas.dataset.page = i;
        canvas.style.cssText = [
          'display:block',
          `width:${vp.width / dpr}px`,
          `height:${vp.height / dpr}px`,
          'margin:0 auto 10px',
          'box-shadow:0 2px 8px rgba(0,0,0,0.5)',
        ].join(';');

        inner.appendChild(canvas);
        if (!cancelled)
          await page.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise;
      }
    };

    render();
    return () => { cancelled = true; };
  }, [paperId, renderZoom]);

  // Ctrl+scroll — instant CSS zoom + debounced re-render
  useEffect(() => {
    const el = outerRef.current;
    if (!el) return;
    const onWheel = (e) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      setZoom(z => clamp(+(z + (e.deltaY < 0 ? STEP : -STEP)).toFixed(2)));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  // Ctrl +/−/0
  useEffect(() => {
    const onKey = (e) => {
      if (!e.ctrlKey) return;
      if      (e.key === '=' || e.key === '+') { e.preventDefault(); setZoom(z => clamp(+(z + STEP).toFixed(2))); }
      else if (e.key === '-')                  { e.preventDefault(); setZoom(z => clamp(+(z - STEP).toFixed(2))); }
      else if (e.key === '0')                  { e.preventDefault(); setZoom(1); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Scroll to target page after re-render
  useEffect(() => {
    const page = targetPage?.page;
    if (!page || !innerRef.current) return;
    const canvas = innerRef.current.querySelector(`[data-page="${page}"]`);
    if (canvas) canvas.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [targetPage, renderZoom]);

  // CSS zoom = ratio between live zoom and last rendered zoom.
  // Gives instant visual scaling; resets to 1 when re-render catches up.
  const cssZoom = zoom / renderZoom;

  return (
    <div
      ref={outerRef}
      style={{ flex: 1, background: '#525659', overflowY: 'auto', overflowX: 'auto', padding: 10 }}
    >
      <div ref={innerRef} style={{ zoom: cssZoom }} />
    </div>
  );
}
