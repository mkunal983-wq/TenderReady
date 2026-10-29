import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react';

import { EvidenceLibrary, RequirementVerification, ManualRequirementEntry } from './EvidenceWorkflow';

import { IconHome, IconClipboardCheck, IconFileText, IconFiles, IconGitBranch, IconListCheck, IconDownload, IconChevronRight } from '@tabler/icons-react';
import './workspace-theme.css';
import { workspaceHref, workspacePages, type WorkspacePage } from './workspaceRoutes';
import { SupplierDashboard } from './SupplierDashboard';

import { AmendmentWorkflow } from './AmendmentWorkflow';
import { SampleGuide } from './SampleGuide';
import type { SourceContext } from './sourceContext';
import { ReconciledConditions, type QuantityCondition, type TemporalCondition } from './ReconciledConditions';
import { categoryLabel, obligationLabel, plainSystemText, numericOperatorLabel, dateRelationLabel } from './plainLanguage';

const PdfSource = lazy(() => import('./PdfSource'));

type Reconciliation = { revision: number; added: number; modified: number; reference: number; unchanged: number; provider_calls: number; created_at: string };
type ReconciliationHistory = Reconciliation & { changes: { previous_requirement_id: string | null; requirement_id: string; action: 'added' | 'modified' | 'reference'; page: number; text: string; reason: string; source_url: string }[] };
type Analysis = { reconciliation?: Reconciliation | null; status: 'ready' | 'running' | 'succeeded' | 'failed'; warnings: string[]; error_message: string | null; pages_completed: number; model: string | null };
type Document = { published?: boolean; kind: string; id: string; filename: string; version: number; page_count: number; analysis: Analysis | null };
type NumericCondition = { operator: string; value_text: string; unit_text: string | null; quote: string };
type DateCondition = { relation: string; boundary_text: string; quote: string };
type Requirement = { provenance?: string; quantity_conditions?: QuantityCondition[]; temporal_conditions?: TemporalCondition[]; source_context?: SourceContext[]; source_document_id: string; source_filename: string; id: string; requirement_id: string; text: string; category: string; obligation: string; page: number; excerpt: string; confidence: string; review_status: string; review_reasons: string[]; numeric_conditions: NumericCondition[]; date_conditions: DateCondition[] };

export function DocumentWorkflow({ workspace, token, page, isSample = false, initialStatus = '' }: { workspace: { id: string; title: string }; token: string; page: WorkspacePage; isSample?: boolean; initialStatus?: string }) {
  const [libraryRevision, setLibraryRevision] = useState(0);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selected, setSelected] = useState('');
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [documentKind, setDocumentKind] = useState('tender');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [reconciliationHistory, setReconciliationHistory] = useState<ReconciliationHistory[] | null>(null);
  const [historyBusy, setHistoryBusy] = useState(false);
  const historyRequest = useRef<AbortController | null>(null);
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
      catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Could not refresh the results. Please try again.'); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 2500);
    }
    timer = setTimeout(poll, 1500);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [current?.analysis?.status, refresh]);

  useEffect(() => {
    sourceRequest.current?.abort();
    historyRequest.current?.abort();
    setReconciliationHistory(null); setHistoryBusy(false);
    setSource('');
    if (blobRef.current) URL.revokeObjectURL(blobRef.current);
    blobRef.current = '';
    return () => { sourceRequest.current?.abort(); historyRequest.current?.abort(); if (blobRef.current) URL.revokeObjectURL(blobRef.current); };
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
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not upload the PDF. Please try again.'); }
    finally { setBusy(false); }
  }

  async function analyze() {
    setBusy(true); setError('');
    try {
      const response = await request(`${prefix}/documents/${selected}/analyze`, { method: 'POST' });
      const updated: Document = await response.json();
      setDocuments(old => old.map(d => d.id === updated.id ? updated : d));
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not read the tender. Please try again.'); }
    finally { setBusy(false); }
  }

  async function reconcile() {
    if (current?.analysis?.status !== 'succeeded' || current.published !== false) return;
    setBusy(true); setReconciling(true); setError('');
    try {
      const response = await request(`${prefix}/documents/${selected}/reconcile`, { method: 'POST' });
      const updated: Document = await response.json();
      setDocuments(old => old.map(d => d.id === updated.id ? updated : d));
      await refresh();
      setLibraryRevision(v => v + 1);
      setReconciliationHistory(null);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not update the saved results. Please try again.'); }
    finally { setBusy(false); setReconciling(false); }
  }

  async function loadReconciliationHistory() {
    historyRequest.current?.abort();
    const controller = new AbortController(); historyRequest.current = controller;
    setHistoryBusy(true); setError('');
    try {
      const history: ReconciliationHistory[] = await request(`${prefix}/documents/${selected}/reconciliations`, { signal: controller.signal }).then(r => r.json());
      if (!controller.signal.aborted) setReconciliationHistory(history);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Could not load previous results. Please try again.'); }
    finally { if (!controller.signal.aborted) setHistoryBusy(false); }
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
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Could not open the original PDF.'); }
  }

  return <section className="workspace-shell" id="active-workspace" aria-label="Tender workspace">
    <aside className="ws-sidebar"><a className="ws-brand" href="/"><span>T</span>TenderReady</a><nav aria-label="Workspace sections"><a href="#/workspaces"><IconHome size={17}/>Workspaces</a>{[{Icon:IconClipboardCheck,page:'readiness'},{Icon:IconFileText,page:'requirements'},{Icon:IconFiles,page:'evidence'},{Icon:IconGitBranch,page:'amendments'},{Icon:IconListCheck,page:'tasks'},{Icon:IconDownload,page:'export'}].map(item=><a href={workspaceHref(workspace.id,item.page as WorkspacePage)} aria-current={page===item.page?'page':undefined} key={item.page}><item.Icon size={17}/>{workspacePages[item.page as WorkspacePage]}</a>)}</nav><div className="ws-sidebar-note"><IconClipboardCheck size={21}/><strong>Check the evidence first.</strong><span>See the documents behind each decision.</span></div></aside>
    <div className="document-workflow ws-content"><div className="ws-breadcrumb"><a href="#/workspaces">Workspaces</a><IconChevronRight size={13}/><span>{workspace.title}</span><IconChevronRight size={13}/><span>{workspacePages[page]}</span></div>
    {error && <p className="error" role="alert">{plainSystemText(error)}</p>}
    {isSample && <SampleGuide workspaceId={workspace.id}/>}
    {["readiness","requirements","tasks","export"].includes(page) && <SupplierDashboard key={page} page={page} initialStatus={initialStatus} workspaceId={workspace.id} onUploadAmendment={()=>setDocumentKind("amendment")} prefix={prefix} request={request} revision={`${libraryRevision}-${selected}-${current?.analysis?.status}`} onChanged={() => setLibraryRevision(v => v + 1)}/>}
    {page==='amendments' && <><h2>Tender updates & versions</h2><p className="muted">Upload a tender or an update, find its requirements, and see what has changed.</p>
    <form id="tender-upload" onSubmit={upload} className="upload-form"><h3>Tender documents</h3>
      <label>Document type<select value={documentKind} onChange={e => setDocumentKind(e.target.value)}><option value="tender">Original tender or full new version</option><option value="amendment">Tender update (amendment or corrigendum)</option></select></label>
      <label>Tender PDF<input ref={inputRef} type="file" accept=".pdf,application/pdf" onChange={e => setFile(e.target.files?.[0] || null)} disabled={busy} /></label>
      <p className="muted">Upload a PDF with selectable text. The usual limits are 10 MB and 40 pages. Every version is saved. Image-only scans cannot be read yet.</p>
      <button disabled={!file || busy}>{busy ? 'Working…' : 'Upload tender PDF'}</button>
    </form>
    </>}
    {page==='evidence' && <EvidenceLibrary prefix={prefix} request={request} onChange={() => setLibraryRevision(v => v + 1)}/>}
    {page==='amendments' && <>
    <div id="workspace-amendments"/><h3>Saved tender versions</h3><p className="muted">Choose a version to see its requirements and history. Upload a new version above to check what changed.</p>
    {documents.length > 0 && <label className="document-select">Document version<select value={selected} disabled={busy} onChange={e => { setSelected(e.target.value); setRequirements([]); }}>
      {documents.map(d => <option key={d.id} value={d.id}>{d.kind === 'amendment' ? 'Tender update' : 'Tender'} v{d.version} · {d.filename}</option>)}
    </select></label>}
    {current && <>
      <AmendmentWorkflow key={`amendment-${current.id}`} prefix={prefix} documentId={current.id} request={request} revision={`${libraryRevision}-${current.analysis?.status}-${requirements.length}`} onChanged={() => { setLibraryRevision(v=>v+1); void refresh().catch(e=>setError(e.message)); }}/>

      <ManualRequirementEntry key={`transcription-${current.id}`} prefix={prefix} documentId={current.id} request={request} onSaved={() => { setLibraryRevision(v => v + 1); void refresh().catch(e => setError(e.message)); }}/>
      <div className="document-actions"><button className="secondary" onClick={() => void showSource()}>View original PDF</button>
        <button onClick={() => void analyze()} disabled={busy || current.analysis?.status === 'running' || current.analysis?.status === 'succeeded'}>
          {current.analysis?.status === 'running' ? 'Reading tender…' : current.analysis?.status === 'succeeded' ? 'Tender read' : current.analysis?.status === 'failed' ? 'Try reading again' : 'Find requirements'}
        </button>
        {current.analysis?.status === 'succeeded' && current.published === false && <button className="secondary" disabled={busy} onClick={() => void reconcile()}>{reconciling ? 'Updating saved results…' : 'Update saved results'}</button>}
      </div>
      {current.analysis?.status === 'succeeded' && current.published === false && <p className="muted">Check quantities, dates and submission instructions using the saved results and original PDF. No new AI calls are made. You still need to review the results.</p>}
      {current.analysis?.reconciliation && <div className="muted" role="status" aria-label="Saved results update"><strong>Results update {current.analysis.reconciliation.revision}</strong><p>{current.analysis.reconciliation.added} added · {current.analysis.reconciliation.modified} corrected · {current.analysis.reconciliation.reference} reference or duplicate items · {current.analysis.reconciliation.unchanged} unchanged · {current.analysis.reconciliation.provider_calls} new AI calls</p><time dateTime={current.analysis.reconciliation.created_at}>{new Date(current.analysis.reconciliation.created_at).toLocaleString()}</time><p>Check the updated results against the PDF before saving the starting tender version.</p></div>}
      {current.analysis?.reconciliation && <details><summary>Previous result updates</summary>
        <p className="muted">Earlier results are kept when a correction is saved. A correction still needs your review.</p>
        <button className="secondary" disabled={historyBusy || busy} onClick={() => void loadReconciliationHistory()}>{historyBusy ? 'Loading previous results…' : 'Load previous results'}</button>
        {reconciliationHistory?.length === 0 && <p>No result updates have been saved for this document.</p>}
        {reconciliationHistory?.map(revision => <details key={revision.revision}><summary>Results update {revision.revision} · {revision.added} added · {revision.modified} corrected · {revision.reference} reference or duplicate items</summary>
          <p><time dateTime={revision.created_at}>{new Date(revision.created_at).toLocaleString()}</time> · {revision.provider_calls} new AI calls</p>
          {revision.changes.map(change => <article className="requirement" key={change.requirement_id}><strong>{change.action === 'reference' ? 'Reference information or duplicate' : change.action === 'added' ? 'Added from the PDF' : 'Corrected result'}</strong><p className="preserve-lines">{change.text}</p><p>{plainSystemText(change.reason)}</p>{change.previous_requirement_id && <small>Earlier result: {change.previous_requirement_id}</small>}<button className="source-link" onClick={() => void showSource(change.page)}>Original PDF · page {change.page}</button></article>)}
        </details>)}
      </details>}
      <p role="status" className="muted">{current.page_count} pages · {current.analysis ? ({ready:'Ready to read',running:'Reading',succeeded:'Read complete',failed:'Could not read'}[current.analysis.status]) : 'Not read yet'}{current.analysis?.status === 'running' ? ` · ${current.analysis.pages_completed} pages read` : ''}</p>
      {current.analysis?.error_message && <p className="error" role="alert">{plainSystemText(current.analysis.error_message)}</p>}
      {current.analysis?.reconciliation && current.analysis.warnings.length > 0 ? <details><summary>Original AI notes (before updates)</summary><p className="muted">These are the original AI notes. They may no longer apply after an update. See the corrected results below.</p>{current.analysis.warnings.map((warning, i) => <p className="warning" key={`${i}-${warning}`}>{warning}</p>)}</details> : current.analysis?.warnings.map((warning, i) => <p className="warning" key={`${i}-${warning}`}>{warning}</p>)}
      {current.analysis?.status === 'succeeded' && <p className="muted">{requirements.length} requirements found in this document. Evidence checks and review decisions are shown separately.</p>}
      <div className="requirements">{requirements.map(req => <article className="requirement" key={req.id}>
        <div className="requirement-meta"><span>{categoryLabel(req.category)}</span><span>{obligationLabel(req.obligation)}</span><span>{req.provenance === 'deterministic_source_reconciliation' ? 'Updated using rules and the original PDF · needs your review' : req.confidence === 'deterministic' ? 'Read using fixed rules, without AI' : req.confidence === 'human_transcription' ? 'Entered by a person' : `AI confidence: ${req.confidence}`}</span><span>Linked to the original PDF</span></div>
        <small className="requirement-id">Requirement {req.requirement_id}</small>
        {req.source_context?.map((context, i) => <div className="muted" key={`${context.source_document_id}-${context.page}-${i}`}><strong>Related heading in the PDF</strong><p className="preserve-lines">{context.text}</p><button className="source-link" onClick={() => void showSource(context.page, context.source_document_id)}>Heading · page {context.page}</button></div>)}
        <p>{req.text}</p>
        <button className="source-link" onClick={() => void showSource(req.page, req.source_document_id)}>Source: {req.source_filename || current.filename} · page {req.page}</button>
        <blockquote>{req.excerpt}</blockquote>
        {req.numeric_conditions.length > 0 && <div><strong>Numbers and amounts</strong><ul>{req.numeric_conditions.map((c, i) => <li key={i}>{numericOperatorLabel(c.operator)} {c.value_text} {c.unit_text || ''}<small>{c.quote}</small></li>)}</ul></div>}
        {req.date_conditions.length > 0 && <div><strong>Dates and deadlines</strong><ul>{req.date_conditions.map((c, i) => <li key={i}>{dateRelationLabel(c.relation)} {c.boundary_text}<small>{c.quote}</small></li>)}</ul></div>}
        <ReconciledConditions quantities={req.quantity_conditions} temporal={req.temporal_conditions} onSource={(sourcePage, documentId) => void showSource(sourcePage, documentId)}/>
        {req.review_reasons.map((reason, i) => <p className="warning" key={i}>{plainSystemText(reason)}</p>)}
        <RequirementVerification prefix={prefix} requirementId={req.id} request={request} libraryRevision={libraryRevision} onChanged={() => setLibraryRevision(v => v + 1)}/>
      </article>)}</div>
      {source && <div className="source-view"><a href={source} target="_blank" rel="noreferrer">Open original PDF in a new tab</a><button className="secondary" onClick={() => setSource('')}>Close PDF</button><Suspense fallback={<p>Opening PDF…</p>}><PdfSource key={source} url={source}/></Suspense></div>}
    </>}
    </>}
    </div>
  </section>;
}
