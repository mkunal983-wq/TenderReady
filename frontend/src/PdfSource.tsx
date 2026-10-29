import { useEffect, useRef, useState } from 'react';
import { getDocument, GlobalWorkerOptions, type RenderTask } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

GlobalWorkerOptions.workerSrc = workerUrl;

export default function PdfSource({ url }: { url: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [page, setPage] = useState(Number(url.match(/#page=(\d+)/)?.[1] || 1));
  const [count, setCount] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [pageText, setPageText] = useState('');
  useEffect(() => {
    let active = true;
    let rendering: RenderTask | undefined;
    setLoading(true); setError(''); setPageText('');
    const task = getDocument({ url: url.split('#')[0], enableXfa: false });
    void (async () => {
      try {
        const pdf = await task.promise;
        if (!active) return;
        setCount(pdf.numPages);
        const sourcePage = await pdf.getPage(page);
        if (!active || !canvas.current) return;
        const viewport = sourcePage.getViewport({ scale: 1.4 });
        const context = canvas.current.getContext('2d');
        if (!context) throw new Error('Canvas is unavailable');
        canvas.current.width = viewport.width; canvas.current.height = viewport.height;
        rendering = sourcePage.render({ canvas: canvas.current, canvasContext: context, viewport });
        await rendering.promise;
        const content = await sourcePage.getTextContent();
        if (active) {
          setPageText(content.items.map(item => 'str' in item ? item.str : '').join('\n'));
          setLoading(false);
        }
      } catch {
        if (active) { setError('Could not show this page. Please close the PDF and open it again.'); setLoading(false); }
      }
    })();
    return () => { active = false; rendering?.cancel(); void task.destroy(); };
  }, [url, page]);
  return <div className="pdf-page">
    <div className="document-actions"><button className="secondary" disabled={page <= 1 || loading} onClick={() => setPage(p => p - 1)}>Previous page</button><span role="status">Page {page}{count ? ` of ${count}` : ''}</span><button className="secondary" disabled={!count || page >= count || loading} onClick={() => setPage(p => p + 1)}>Next page</button></div>
    {loading && <p role="status">Loading PDF page…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <canvas ref={canvas} aria-label={`Source PDF page ${page}`} />
    {pageText && <details><summary>Read page text</summary><pre>{pageText}</pre></details>}
  </div>;
}
