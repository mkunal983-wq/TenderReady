import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react';

import { EvidenceLibrary, RequirementVerification, ManualRequirementEntry } from './EvidenceWorkflow';

import { IconHome, IconClipboardCheck, IconFileText, IconFiles, IconGitBranch, IconListCheck, IconDownload, IconChevronRight } from '@tabler/icons-react';
import './workspace-theme.css';
import { workspaceHref, workspacePages, type WorkspacePage } from './workspaceRoutes';
import { SupplierDashboard } from './SupplierDashboard';

import { AmendmentWorkflow } from './AmendmentWorkflow';
import { SampleGuide } from './SampleGuide';

const PdfSource = lazy(() => import('./PdfSource'));

type Analysis = { status: 'ready' | 'running' | 'succeeded' | 'failed'; warnings: string[]; error_message: string | null; pages_completed: number; model: string | null };
type Document = { kind: string; id: string; filename: string; version: number; page_count: number; analysis: Analysis | null };
type NumericCondition = { operator: string; value_text: string; unit_text: string | null; quote: string };
type DateCondition = { relation: string; boundary_text: string; quote: string };
type Requirement = { source_document_id: string; source_filename: string; id: string; requirement_id: string; text: string; category: string; obligation: string; page: number; excerpt: string; confidence: string; review_status: string; review_reasons: string[]; numeric_conditions: NumericCondition[]; date_conditions: DateCondition[] };

export function DocumentWorkflow({ workspace, token, page, isSample = false }: { workspace: { id: string; title: string }; token: string; page: WorkspacePage; isSample?: boolean }) {
  const [libraryRevision, setLibraryRevision] = useState(0);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selected, setSelected] = useState('');
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [documentKind, setDocumentKind] = useState('tender');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [source, setSource] = useState('');
  const blobRef = useRef('');
  const blobDocument = useRef('');
  const sourceRequest = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const prefix = `/workspaces/${workspace.id}`;
  const current = documents.find(d => d.id === selected);

  useEffect(() => {
    // The native file input is recreated when its page opens. Never retain an
    // invisible File from the previous visit while displaying an empty picker.
    setFile(null);
  }, [page]);

  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await fetch(`/api${path}`, { ...init, headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.error?.message || `Request failed (${response.status})`);
    }
    return response;
  }, [token]);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const [docs, rows] = await Promise.all([
      request(`${prefix}/documents`, { signal }).then(r => r.json()) as Promise<Document[]>,
      selected ? request(`${prefix}/documents/${selected}/requirements`, { signal }).then(r => r.json()) as Promise<Requirement[]> : Promise.resolve([]),
    ]);
    if (signal?.aborted) return;
    setDocuments(docs); setRequirements(rows);
    if (!selected && docs.length) setSelected(docs[0].id);
  }, [prefix, request, selected]);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    if (current?.analysis?.status !== 'running') return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { await refresh(controller.signal); }
      catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Could not refresh analysis'); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 2500);
    }
    timer = setTimeout(poll, 1500);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [current?.analysis?.status, refresh]);

  useEffect(() => {
    sourceRequest.current?.abort();
    setSource('');
    if (blobRef.current) URL.revokeObjectURL(blobRef.current);
    blobRef.current = '';
    return () => { sourceRequest.current?.abort(); if (blobRef.current) URL.revokeObjectURL(blobRef.current); };
  }, [selected]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError('');
    try {
      const response = await request(`${prefix}/documents?kind=${documentKind}`, { method: 'POST', headers: { 'Content-Type': 'application/pdf', 'X-Filename': encodeURIComponent(file.name) }, body: file });
      const document: Document = await response.json();
      setDocuments(old => [document, ...old]); setSelected(document.id); setRequirements([]); setFile(null);
      if (inputRef.current) inputRef.current.value = '';
    } catch (e) { setError(e instanceof Error ? e.message : 'Upload failed'); }
    finally { setBusy(false); }
  }

  async function analyze() {
    setBusy(true); setError('');
    try {
      const response = await request(`${prefix}/documents/${selected}/analyze`, { method: 'POST' });
      const updated: Document = await response.json();
      setDocuments(old => old.map(d => d.id === updated.id ? updated : d));
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Analysis failed'); }
    finally { setBusy(false); }
  }

  async function showSource(page = 1, documentId = selected) {
    setError('');
    sourceRequest.current?.abort();
    const controller = new AbortController();
    sourceRequest.current = controller;
    try {
      if (!blobRef.current || blobDocument.current !== documentId) {
        const response = await request(`${prefix}/documents/${documentId}/file`, { signal: controller.signal });
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        if (blobRef.current) URL.revokeObjectURL(blobRef.current);
        blobRef.current = URL.createObjectURL(blob); blobDocument.current = documentId;
      }
      setSource(`${blobRef.current}#page=${page}`);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Could not open source'); }
  }

  return <section className="workspace-shell" id="active-workspace" aria-label="Tender document analysis">
    <aside className="ws-sidebar"><a className="ws-brand" href="/"><span>T</span>TenderReady</a><nav aria-label="Workspace sections"><a href="#/workspaces"><IconHome size={17}/>Workspaces</a>{[{Icon:IconClipboardCheck,page:'readiness'},{Icon:IconFileText,page:'requirements'},{Icon:IconFiles,page:'evidence'},{Icon:IconGitBranch,page:'amendments'},{Icon:IconListCheck,page:'tasks'},{Icon:IconDownload,page:'export'}].map(item=><a href={workspaceHref(workspace.id,item.page as WorkspacePage)} aria-current={page===item.page?'page':undefined} key={item.page}><item.Icon size={17}/>{workspacePages[item.page as WorkspacePage]}</a>)}</nav><div className="ws-sidebar-note"><IconClipboardCheck size={21}/><strong>Evidence before assurance.</strong><span>Your decisions, connected to their sources.</span></div></aside>
    <div className="document-workflow ws-content"><div className="ws-breadcrumb"><a href="#/workspaces">Workspaces</a><IconChevronRight size={13}/><span>{workspace.title}</span><IconChevronRight size={13}/><span>{workspacePages[page]}</span></div>
    {error && <p className="error" role="alert">{error}</p>}
    {isSample && <SampleGuide workspaceId={workspace.id}/>}
    {["readiness","requirements","tasks","export"].includes(page) && <SupplierDashboard key={page} page={page} workspaceId={workspace.id} onUploadAmendment={()=>setDocumentKind("amendment")} prefix={prefix} request={request} revision={`${libraryRevision}-${selected}-${current?.analysis?.status}`} onChanged={() => setLibraryRevision(v => v + 1)}/>}
    {page==='amendments' && <><h2>Amendments & tender versions</h2><p className="muted">Upload an original tender or amendment, extract requirements, and review the impact of each version.</p>
    <form id="tender-upload" onSubmit={upload} className="upload-form"><h3>Tender documents</h3>
      <label>Document type<select value={documentKind} onChange={e => setDocumentKind(e.target.value)}><option value="tender">Original / complete revised tender</option><option value="amendment">Amendment / corrigendum</option></select></label>
      <label>Tender PDF<input ref={inputRef} type="file" accept=".pdf,application/pdf" onChange={e => setFile(e.target.files?.[0] || null)} disabled={busy} /></label>
      <p className="muted">Text-based PDF, up to 10 MB and 40 pages by default. Each upload creates a preserved tender version. Scanned-only PDFs are not supported.</p>
      <button disabled={!file || busy}>{busy ? 'Working…' : 'Upload tender PDF'}</button>
    </form>
    </>}
    {page==='evidence' && <EvidenceLibrary prefix={prefix} request={request} onChange={() => setLibraryRevision(v => v + 1)}/>}
    {page==='amendments' && <>
    <div id="workspace-amendments"/><h3>Amendments & document versions</h3><p className="muted">Select a version to inspect its clauses and amendment history. Upload a revised document above to begin reassessment.</p>
    {documents.length > 0 && <label className="document-select">Document version<select value={selected} onChange={e => { setSelected(e.target.value); setRequirements([]); }}>
      {documents.map(d => <option key={d.id} value={d.id}>{d.kind} v{d.version} · {d.filename}</option>)}
    </select></label>}
    {current && <>
      <AmendmentWorkflow key={`amendment-${current.id}`} prefix={prefix} documentId={current.id} request={request} revision={libraryRevision} onChanged={() => { setLibraryRevision(v=>v+1); void refresh().catch(e=>setError(e.message)); }}/>

      <ManualRequirementEntry key={`transcription-${current.id}`} prefix={prefix} documentId={current.id} request={request} onSaved={() => { setLibraryRevision(v => v + 1); void refresh().catch(e => setError(e.message)); }}/>
      <div className="document-actions"><button className="secondary" onClick={() => void showSource()}>View source PDF</button>
        <button onClick={() => void analyze()} disabled={busy || current.analysis?.status === 'running' || current.analysis?.status === 'succeeded'}>
          {current.analysis?.status === 'running' ? 'Analyzing…' : current.analysis?.status === 'succeeded' ? 'Analysis complete' : current.analysis?.status === 'failed' ? 'Retry analysis' : 'Extract requirements'}
        </button></div>
      <p role="status" className="muted">{current.page_count} pages · {current.analysis?.status || 'Not analyzed'}{current.analysis?.status === 'running' ? ` · ${current.analysis.pages_completed} pages processed` : ''}</p>
      {current.analysis?.error_message && <p className="error" role="alert">{current.analysis.error_message}</p>}
      {current.analysis?.warnings.map((warning, i) => <p className="warning" key={`${i}-${warning}`}>{warning}</p>)}
      {current.analysis?.status === 'succeeded' && <p className="muted">{requirements.length} requirements in this document view. Evidence findings and reviewer decisions are shown separately.</p>}
      <div className="requirements">{requirements.map(req => <article className="requirement" key={req.id}>
        <div className="requirement-meta"><span>{req.category.replaceAll('_', ' ')}</span><span>{req.obligation}</span><span>{req.confidence === 'deterministic' ? 'Deterministic extraction' : req.confidence === 'human_transcription' ? 'Human transcription' : `${req.confidence} model confidence`}</span><span>Source-linked interpretation</span></div>
        <small className="requirement-id">Requirement {req.requirement_id}</small>
        <p>{req.text}</p>
        <button className="source-link" onClick={() => void showSource(req.page, req.source_document_id)}>Source: {req.source_filename || current.filename} · page {req.page}</button>
        <blockquote>{req.excerpt}</blockquote>
        {req.numeric_conditions.length > 0 && <div><strong>Numeric conditions</strong><ul>{req.numeric_conditions.map((c, i) => <li key={i}>{c.operator} {c.value_text} {c.unit_text || ''}<small>{c.quote}</small></li>)}</ul></div>}
        {req.date_conditions.length > 0 && <div><strong>Date conditions</strong><ul>{req.date_conditions.map((c, i) => <li key={i}>{c.relation.replaceAll('_', ' ')} {c.boundary_text}<small>{c.quote}</small></li>)}</ul></div>}
        {req.review_reasons.map((reason, i) => <p className="warning" key={i}>{reason}</p>)}
        <RequirementVerification prefix={prefix} requirementId={req.id} request={request} libraryRevision={libraryRevision} onChanged={() => setLibraryRevision(v => v + 1)}/>
      </article>)}</div>
      {source && <div className="source-view"><a href={source} target="_blank" rel="noreferrer">Open source PDF in a new tab</a><button className="secondary" onClick={() => setSource('')}>Close source</button><Suspense fallback={<p>Loading PDF viewer…</p>}><PdfSource key={source} url={source}/></Suspense></div>}
    </>}
    </>}
    </div>
  </section>;
}
