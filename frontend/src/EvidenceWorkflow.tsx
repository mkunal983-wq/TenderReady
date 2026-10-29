import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
const PdfSource = lazy(() => import('./PdfSource'));
type Request = (path: string, init?: RequestInit) => Promise<Response>;
type Evidence = { id: string; filename: string; evidence_type: string; page_count: number; version: number; is_current: boolean; supersedes_id: string | null };
type Criterion = { field: string; operator: string; expected: string; quote: string; evidence_type: string };
type Source = { filename?: string; fact_id: string; page: number; quote: string; document_version_id: string; raw_value: string };
type Check = { method: string; field?: string; outcome?: string; rationale?: string; sources?: Source[] };
type Assessment = { id: string; label: string; status: string; stale: boolean; review_state: string; explanation: string; created_at: string; checks: Check[]; reviews: { id: string; action: string; reviewer: string; comment: string; created_at: string }[]; tasks: { id: string; title: string; explanation: string }[] };
const types = [['datasheet', 'Product datasheet'], ['authorization', 'Manufacturer authorization'], ['certificate', 'Company certificate'], ['project_reference', 'Previous-project reference']];
const fields = [['model','Product model'], ['bidder','Bidder legal name'], ['ram_gb','RAM (GB)'], ['storage_gb','Storage (GB)'], ['valid_until','Valid until (ISO date)'], ['valid_from','Valid from (ISO date)'], ['project_value_inr','Project value (INR)'], ['certificate_number','Certificate number'], ['manufacturer','Manufacturer'], ['project_reference','Project reference']];
const statuses = [['supported','Supported by evidence'], ['missing','Missing'], ['conflicting','Conflict detected'], ['outdated','Outdated'], ['inconclusive','Needs human review']];

export function EvidenceLibrary({ prefix, request, onChange }: { prefix: string; request: Request; onChange: () => void }) {
  const [docs, setDocs] = useState<Evidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState('datasheet');
  const [replacesId, setReplacesId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [source, setSource] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const sourceAbort = useRef<AbortController | null>(null);
  const blob = useRef('');
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const response = await request(`${prefix}/evidence`, { signal });
    const rows = await response.json();
    if (!signal?.aborted) setDocs(rows);
  }, [prefix, request]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true);
    void refresh(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); sourceAbort.current?.abort(); if (blob.current) URL.revokeObjectURL(blob.current); };
  }, [refresh]);
  async function upload(event: FormEvent) {
    event.preventDefault(); if (!file) return;
    setBusy(true); setError('');
    try {
      const query = new URLSearchParams({evidence_type:kind});
      if (replacesId) query.set('replaces_id', replacesId);
      await request(`${prefix}/evidence?${query}`, { method: 'POST', headers: { 'Content-Type':'application/pdf', 'X-Filename':encodeURIComponent(file.name) }, body:file });
      setFile(null); setReplacesId(''); if (input.current) input.current.value = '';
      await refresh(); onChange();
    } catch (e) { setError(e instanceof Error ? e.message : 'Evidence upload failed'); }
    finally { setBusy(false); }
  }
  async function view(id: string) {
    sourceAbort.current?.abort(); const controller = new AbortController(); sourceAbort.current = controller;
    try {
      const response = await request(`${prefix}/documents/${id}/file`, { signal: controller.signal });
      const data = await response.blob(); if (controller.signal.aborted) return;
      if (blob.current) URL.revokeObjectURL(blob.current);
      blob.current = URL.createObjectURL(data); setSource(blob.current);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Source unavailable'); }
  }
  return <section className="evidence-library" aria-label="Supplier evidence library">
    <h3>Supplier evidence library</h3><p className="muted">Reuse these PDFs across requirements in this workspace. Uploading a document does not establish its authenticity or compliance.</p>
    <form onSubmit={upload}><label>Evidence type<select value={kind} onChange={e => { setKind(e.target.value); setReplacesId(''); }}>{types.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label>Replace an existing document (optional)<select value={replacesId} onChange={e => setReplacesId(e.target.value)}><option value="">Upload as a separate document</option>{docs.filter(doc => doc.is_current && doc.evidence_type === kind).map(doc => <option key={doc.id} value={doc.id}>{doc.filename} · version {doc.version}</option>)}</select></label>
      {replacesId && <p className="muted">The previous version and its review history remain available. Re-run affected assessments after upload.</p>}
      <label>Company PDF<input type="file" ref={input} accept="application/pdf,.pdf" onChange={e => setFile(e.target.files?.[0] || null)} disabled={busy}/></label>
      <button disabled={!file || busy}>{busy ? 'Saving evidence…' : 'Upload company evidence'}</button></form>
    {error && <p role="alert" className="error">{error}</p>}
    <ul>{docs.map(doc => <li key={doc.id}><strong>{doc.filename}</strong><span>{doc.evidence_type.replaceAll('_',' ')} · {doc.page_count} pages · version {doc.version} · {doc.is_current ? 'Current' : 'Replaced'}</span><button className="source-link" onClick={() => void view(doc.id)}>Inspect evidence PDF</button></li>)}</ul>
    {loading && <p role="status">Loading supplier documents…</p>}
    {!loading && !error && !docs.length && <p>No company evidence uploaded yet.</p>}
    {source && <div><button className="secondary" onClick={() => setSource('')}>Close evidence source</button><Suspense fallback={<p>Loading source…</p>}><PdfSource key={source} url={source}/></Suspense></div>}
  </section>;
}

export function RequirementVerification({ prefix, requirementId, request, libraryRevision, onChanged, initialOpen = false }: { prefix: string; requirementId: string; request: Request; libraryRevision: number; onChanged?: () => void; initialOpen?: boolean }) {
  const [open, setOpen] = useState(initialOpen);
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [reviewer, setReviewer] = useState('');
  const [comment, setComment] = useState('');
  const [correction, setCorrection] = useState('inconclusive');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [source, setSource] = useState('');
  const sourceAbort = useRef<AbortController | null>(null);
  const blob = useRef('');
  const endpoint = `${prefix}/requirements/${requirementId}`;
  const load = useCallback(async (signal?: AbortSignal, initialize = false) => {
    setLoading(true);
    try {
      const body = await (await request(`${endpoint}/verification`, { signal })).json();
      if (signal?.aborted) return;
      setAssessments(body.assessments);
      if (initialize) setCriteria(body.suggested_criteria);
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [request, endpoint]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void load(controller.signal, true).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    setConfirmed(false);
    return () => controller.abort();
  }, [open, load, libraryRevision]);
  useEffect(() => () => { sourceAbort.current?.abort(); if (blob.current) URL.revokeObjectURL(blob.current); }, []);
  function change(index: number, field: keyof Criterion, value: string) {
    setCriteria(old => old.map((c,i) => i === index ? { ...c, [field]:value } : c)); setConfirmed(false);
  }
  async function run() {
    setBusy(true); setError('');
    try { await request(`${endpoint}/verify`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ criteria, coverage_confirmed:confirmed, reviewer }) }); await load(); onChanged?.(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Verification failed'); }
    finally { setBusy(false); }
  }
  async function decide(id: string, action: string) {
    setBusy(true); setError('');
    try { await request(`${prefix}/assessments/${id}/reviews`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ action, reviewer, comment, ...(action === 'corrected' ? { corrected_status:correction } : {}) }) }); await load(); setComment(''); onChanged?.(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Review failed'); }
    finally { setBusy(false); }
  }
  async function inspect(ref: Source) {
    sourceAbort.current?.abort(); const controller = new AbortController(); sourceAbort.current = controller;
    try {
      const response = await request(`${prefix}/documents/${ref.document_version_id}/file`, { signal:controller.signal });
      const data = await response.blob(); if (controller.signal.aborted) return;
      if (blob.current) URL.revokeObjectURL(blob.current);
      blob.current = URL.createObjectURL(data); setSource(`${blob.current}#page=${ref.page}`);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Source unavailable'); }
  }
  return <div className="verification"><button className="secondary" onClick={() => setOpen(v => !v)}>{open ? 'Hide evidence verification' : 'Verify supporting evidence'}</button>
    {open && <>
      <p>Deterministic checks compare explicit labelled fields. Suggestions are not proof. Confirm document purpose, model scope, units, dates, and that every part of this requirement is covered.</p>
      <p className="muted">Supported formats: Model:, Bidder:, RAM: 16 GB, Storage: 512 GB, Valid until: YYYY-MM-DD, Valid from: YYYY-MM-DD, Project value: INR 1500000, Certificate number:, Manufacturer:, Project reference:. Other layouts require human review.</p>
      {criteria.map((c,i) => <fieldset key={i}><legend>Check {i+1}</legend><div className="criteria-grid">
        <label>Field<select value={c.field} onChange={e => change(i,'field',e.target.value)}>{fields.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label>Evidence type<select value={c.evidence_type} onChange={e => change(i,'evidence_type',e.target.value)}>{types.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label>Comparison<select value={c.operator} onChange={e => change(i,'operator',e.target.value)}><option value="eq">Equals</option><option value="gte">At least / on or after</option><option value="lte">At most / on or before</option><option value="present">Field must be present</option></select></label>
        <label>Expected value<input value={c.expected} maxLength={200} onChange={e => change(i,'expected',e.target.value)}/></label>
      </div><label>Exact requirement quotation<textarea value={c.quote} maxLength={5000} onChange={e => change(i,'quote',e.target.value)}/></label><button className="secondary" onClick={() => { setCriteria(old => old.filter((_, n) => i !== n)); setConfirmed(false); }}>Remove check</button></fieldset>)}
      <button className="secondary" disabled={criteria.length >= 30} onClick={() => { setCriteria(old => [...old,{field:'model',operator:'eq',expected:'',quote:'',evidence_type:'datasheet'}]); setConfirmed(false); }}>Add check</button>
      <label>Reviewer name<input value={reviewer} maxLength={200} onChange={e => setReviewer(e.target.value)}/></label>
      <label className="checkbox-label"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>I have checked the full requirement and inspected the candidate documents and confirm these criteria cover the requirement completely.</label>
      <button disabled={busy || loading || (confirmed && !reviewer.trim())} onClick={() => void run()}>{busy ? 'Saving…' : 'Run evidence verification'}</button>
      {error && <p role="alert" className="error">{error}</p>}
      <h4>Assessment history</h4>
      {loading && <p role="status">Loading saved assessments…</p>}
      {!loading && !error && !assessments.length && <p>No assessments yet.</p>}
      {assessments.map((a,index) => <article key={a.id} className={`assessment assessment-${a.status}`}>
        <h4>{a.label} {index === 0 ? '· Latest' : '· Historical'}</h4><small>{a.created_at} · {a.id}</small>
        {a.stale && <p className="warning">Workspace evidence or the assessment date changed. Rerun verification before approval.</p>}
        <p>{a.explanation}</p><p><strong>Review: {a.review_state.replaceAll('_',' ')}</strong> — approval records agreement with the finding, not official compliance.</p><p className="muted">{a.checks[0]?.method === 'human_correction' ? 'Human-corrected finding' : 'Deterministic checks with human-defined scope'} · Not officially verified</p>
        {a.checks.filter(c => c.rationale).map((c,i) => <div key={i}><strong>{c.field || c.method}: {c.outcome || 'Human judgment'}</strong><p>{c.rationale}</p>{c.sources?.map(ref => <div key={ref.fact_id}><blockquote>{ref.quote}</blockquote><button className="source-link" onClick={() => void inspect(ref)}>Evidence page {ref.page} · {ref.filename || ref.document_version_id.slice(0,8)}</button></div>)}</div>)}
        {a.tasks.map(t => <details key={t.id}><summary>{t.title}</summary><p className="preserve-lines">{t.explanation}</p></details>)}
        {a.reviews.map(r => <p key={r.id}><strong>{r.action} by {r.reviewer}</strong> · <time>{new Date(r.created_at.endsWith('Z') || /[+-]\d\d:\d\d$/.test(r.created_at) ? r.created_at : r.created_at+'Z').toLocaleString()}</time>: {r.comment}</p>)}
        {index === 0 && <><label>Review rationale<textarea value={comment} maxLength={4000} onChange={e => setComment(e.target.value)}/></label><div className="document-actions">
          <button disabled={busy || a.stale || !reviewer.trim() || !comment.trim()} onClick={() => void decide(a.id,'approved')}>Approve finding</button>
          <button className="secondary" disabled={busy || !reviewer.trim() || !comment.trim()} onClick={() => void decide(a.id,'rejected')}>Reject finding</button>
          <button className="secondary" disabled={busy || !reviewer.trim() || !comment.trim()} onClick={() => void decide(a.id,'reopened')}>Reopen review</button></div>
          <label>Correct finding to<select value={correction} onChange={e => setCorrection(e.target.value)}>{statuses.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <button className="secondary" disabled={busy || a.stale || !reviewer.trim() || !comment.trim()} onClick={() => void decide(a.id,'corrected')}>Save correction as new assessment</button></>}
      </article>)}
      {source && <div><button className="secondary" onClick={() => setSource('')}>Close cited evidence</button><Suspense fallback={<p>Loading evidence…</p>}><PdfSource key={source} url={source}/></Suspense></div>}
    </>}
  </div>;
}

export function ManualRequirementEntry({ prefix, documentId, request, onSaved }: { prefix:string; documentId:string; request:Request; onSaved:() => void }) {
  const [pages, setPages] = useState<{page:number;text:string}[]>([]);
  const [page, setPage] = useState(1);
  const [excerpt, setExcerpt] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function loadPages() { try { setPages(await (await request(`${prefix}/documents/${documentId}/pages`)).json()); } catch (e) { setError(e instanceof Error ? e.message : 'Source unavailable'); } }
  async function save(event:FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { await request(`${prefix}/documents/${documentId}/manual-requirements`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ page, excerpt, reviewer })}); setExcerpt(''); onSaved(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not save requirement'); }
    finally { setBusy(false); }
  }
  return <details><summary>Add a requirement by human transcription</summary><p>Use an exact tender excerpt. This is recorded as human transcription, not Nemotron extraction.</p><button className="secondary" onClick={() => void loadPages()}>Load page text</button>
    {pages.length > 0 && <><label>Source page<select value={page} onChange={e => setPage(Number(e.target.value))}>{pages.map(p => <option key={p.page} value={p.page}>Page {p.page}</option>)}</select></label><pre className="page-transcript">{pages.find(p => p.page === page)?.text}</pre></>}
    <form onSubmit={save}><label>Exact requirement excerpt<textarea required maxLength={5000} value={excerpt} onChange={e => setExcerpt(e.target.value)}/></label><label>Reviewer name<input required maxLength={200} value={reviewer} onChange={e => setReviewer(e.target.value)}/></label><button disabled={busy || !pages.length}>Save source-backed requirement</button></form>{error && <p role="alert" className="error">{error}</p>}
  </details>;
}
