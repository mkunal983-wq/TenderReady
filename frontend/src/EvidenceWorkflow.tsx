import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { plainSystemText, reviewStateLabel, statusLabel } from './plainLanguage';
const PdfSource = lazy(() => import('./PdfSource'));
type Request = (path: string, init?: RequestInit) => Promise<Response>;
type Evidence = { id: string; filename: string; evidence_type: string; page_count: number; version: number; is_current: boolean; supersedes_id: string | null };
type Criterion = { field: string; operator: string; expected: string; quote: string; evidence_type: string };
type CheckPlan = {
  version:string; kind:'evidence'|'procedure'|'reference'; coverage:'complete'|'partial'|'manual';
  criteria:Criterion[]; review_reasons:string[]; unhandled:{text:string;reason:string}[];
  sources:{source_document_id:string;page:number;quote:string;source_span_id:string}[];
  scope_refs:{text:string;page:number;source_document_id:string}[];
  scope:{label:string|null;state:'matched'|'missing'|'needs_review'|'unscoped';reason:string;documents:{id:string;filename:string}[]};
  auto_coverage_eligible:boolean;
};
type Source = { filename?: string; fact_id: string; page: number; quote: string; document_version_id: string; raw_value: string };
type Check = { method: string; field?: string; outcome?: string; rationale?: string; sources?: Source[]; source_document_id?:string; page?:number; requirement_id?:string };
type Assessment = { id: string; label: string; status: string; stale: boolean; review_state: string; explanation: string; created_at: string; checks: Check[]; reviews: { id: string; action: string; reviewer: string; comment: string; created_at: string }[]; tasks: { id: string; title: string; explanation: string }[] };
const types = [['datasheet', 'Product datasheet'], ['authorization', 'Manufacturer approval letter'], ['certificate', 'Company certificate'], ['project_reference', 'Past project document']];
const fields = [['model','Product model'], ['bidder','Supplier legal name'], ['ram_gb','RAM (GB)'], ['storage_gb','Storage (GB)'], ['storage_type','Storage type'], ['memory_type','Memory type'], ['operating_system','Operating system'], ['bluetooth','Bluetooth'], ['wifi','Wifi'], ['webcam','Webcam'], ['speaker','Speaker'], ['usb','USB port'], ['screen_inches','Screen size (inches)'], ['display_backlight','Display backlight'], ['cpu_ghz','CPU speed (GHz)'], ['cpu_bits','CPU architecture (bits)'], ['cpu_cores','Physical CPU cores'], ['processor','Processor identity'], ['cpu_family','CPU family'], ['graphics','Graphics identity'], ['hdmi','HDMI'], ['vga','VGA'], ['ethernet','Ethernet connector'], ['usb2_ports','USB 2.0 port count'], ['usb3_ports','USB 3.0 port count'], ['valid_until','Valid until (YYYY-MM-DD)'], ['valid_from','Valid from (YYYY-MM-DD)'], ['project_value_inr','Project value (INR)'], ['certificate_number','Certificate number'], ['manufacturer','Manufacturer'], ['project_reference','Project reference']];
const statuses = ['supported', 'missing', 'conflicting', 'outdated', 'inconclusive'];
const checkFields: Record<string, string> = { ...Object.fromEntries(fields), product_scope: 'Product and model match', bidder_identity: 'Supplier name match', interpretation: 'Requirement meaning', coverage: 'All parts checked', component: 'Linked requirement', validity: 'Document dates', human_correction: 'Reviewer change' };
function comparisonText(criterion:Criterion) {
  const date = criterion.field === 'valid_from' || criterion.field === 'valid_until';
  return ({baseline:'Exact tender baseline; other models need review',lt:'Less than',eq:'Must match',gte:date?'On or after':'At least',lte:date?'On or before':'No more than',present:'Must be included'} as Record<string,string>)[criterion.operator] || criterion.operator;
}
const checkOutcomes: Record<string, string> = { pass: 'Matches', conflict: 'Does not match', review: 'Needs review', missing: 'Document missing', outdated: 'Out of date' };

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
    void refresh(controller.signal).catch(e => { if (!controller.signal.aborted) setError(plainSystemText(e.message)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
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
    } catch (e) { setError(e instanceof Error ? plainSystemText(e.message) : 'Could not upload the document. Please try again.'); }
    finally { setBusy(false); }
  }
  async function view(id: string) {
    sourceAbort.current?.abort(); const controller = new AbortController(); sourceAbort.current = controller;
    try {
      const response = await request(`${prefix}/documents/${id}/file`, { signal: controller.signal });
      const data = await response.blob(); if (controller.signal.aborted) return;
      if (blob.current) URL.revokeObjectURL(blob.current);
      blob.current = URL.createObjectURL(data); setSource(blob.current);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? plainSystemText(e.message) : 'Could not open the document. Please try again.'); }
  }
  return <section className="evidence-library" aria-label="Company documents">
    <h3>Company documents</h3><p className="muted">Use these company PDFs for more than one requirement in this workspace. An upload alone does not prove that a document is genuine or meets the tender rules.</p>
    <form onSubmit={upload}><label>Document type<select value={kind} onChange={e => { setKind(e.target.value); setReplacesId(''); }}>{types.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label>Replace an existing document (optional)<select value={replacesId} onChange={e => setReplacesId(e.target.value)}><option value="">Upload as a separate document</option>{docs.filter(doc => doc.is_current && doc.evidence_type === kind).map(doc => <option key={doc.id} value={doc.id}>{doc.filename} · version {doc.version}</option>)}</select></label>
      {replacesId && <p className="muted">The old file and its reviews will be kept. After uploading, run the checks again for requirements that used it.</p>}
      <label>Company PDF<input type="file" ref={input} accept="application/pdf,.pdf" onChange={e => setFile(e.target.files?.[0] || null)} disabled={busy}/></label>
      <button disabled={!file || busy}>{busy ? 'Saving document…' : 'Upload company document'}</button></form>
    {error && <p role="alert" className="error">{error}</p>}
    <ul>{docs.map(doc => <li key={doc.id}><strong>{doc.filename}</strong><span>{types.find(([value]) => value === doc.evidence_type)?.[1] || doc.evidence_type.replaceAll('_',' ')} · {doc.page_count} pages · version {doc.version} · {doc.is_current ? 'Current' : 'Replaced'}</span><button className="source-link" onClick={() => void view(doc.id)}>View document</button></li>)}</ul>
    {loading && <p role="status">Loading supplier documents…</p>}
    {!loading && !error && !docs.length && <p>No company documents yet. Upload a PDF to get started.</p>}
    {source && <div><button className="secondary" onClick={() => setSource('')}>Close document</button><Suspense fallback={<p>Opening document…</p>}><PdfSource key={source} url={source}/></Suspense></div>}
  </section>;
}

export function RequirementVerification({ prefix, requirementId, request, libraryRevision, onChanged, initialOpen = false }: { prefix: string; requirementId: string; request: Request; libraryRevision: number | string; onChanged?: () => void; initialOpen?: boolean }) {
  const [open, setOpen] = useState(initialOpen);
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [plan,setPlan] = useState<CheckPlan|null>(null);
  const [edited,setEdited] = useState(false);
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
    setLoading(true); setError('');
    try {
      const body = await (await request(`${endpoint}/verification`, { signal })).json();
      if (signal?.aborted) return;
      setAssessments(body.assessments);
      setPlan(body.check_plan ?? null);
      if (initialize) {setCriteria(body.suggested_criteria);setEdited(false);}
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [request, endpoint]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void load(controller.signal, true).catch(e => { if (!controller.signal.aborted) setError(plainSystemText(e.message)); });
    setConfirmed(false);
    return () => controller.abort();
  }, [open, load, libraryRevision]);
  useEffect(() => () => { sourceAbort.current?.abort(); if (blob.current) URL.revokeObjectURL(blob.current); }, []);
  function change(index: number, field: keyof Criterion, value: string) {
    setCriteria(old => old.map((c,i) => {
      if (i !== index) return c;
      const next = {...c,[field]:value};
      if (field==='field' && ['storage_type','memory_type','operating_system','bluetooth','wifi','webcam','speaker','usb','display_backlight','hdmi','vga','ethernet'].includes(value) && !['eq','present'].includes(next.operator)) next.operator='eq';
      return next;
    })); setConfirmed(false); setEdited(true);
  }
  async function run() {
    setBusy(true); setError('');
    try { await request(`${endpoint}/verify`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ criteria, coverage_confirmed:confirmed, reviewer }) }); await load(); onChanged?.(); }
    catch (e) { setError(e instanceof Error ? plainSystemText(e.message) : 'Could not check the documents. Please try again.'); }
    finally { setBusy(false); }
  }
  async function decide(id: string, action: string) {
    setBusy(true); setError('');
    try { await request(`${prefix}/assessments/${id}/reviews`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ action, reviewer, comment, ...(action === 'corrected' ? { corrected_status:correction } : {}) }) }); await load(); setComment(''); onChanged?.(); }
    catch (e) { setError(e instanceof Error ? plainSystemText(e.message) : 'Could not save your review. Please try again.'); }
    finally { setBusy(false); }
  }
  async function inspect(ref: Pick<Source,'page'|'document_version_id'>) {
    sourceAbort.current?.abort(); const controller = new AbortController(); sourceAbort.current = controller;
    try {
      const response = await request(`${prefix}/documents/${ref.document_version_id}/file`, { signal:controller.signal });
      const data = await response.blob(); if (controller.signal.aborted) return;
      if (blob.current) URL.revokeObjectURL(blob.current);
      blob.current = URL.createObjectURL(data); setSource(`${blob.current}#page=${ref.page}`);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? plainSystemText(e.message) : 'Could not open the document. Please try again.'); }
  }
  return <div className="verification"><button className="secondary" onClick={() => setOpen(v => !v)}>{open ? 'Hide document checks' : 'Check company documents'}</button>
    {open && <>
      <p>Run the prepared checks against your company documents. Unclear details stay in review; running checks does not approve the result.</p>
      {!loading && !error && plan?.kind !== 'procedure' && plan?.kind !== 'reference' && <p className="muted">{criteria.length ? `${criteria.length} ${criteria.length === 1 ? "check" : "checks"} prepared from the tender. You can run them without filling in the form below.` : 'No automatic checks could be prepared for this requirement. It needs a person to review the original wording.'}</p>}
      {criteria.length > 0 && <ul aria-label="Prepared document checks">{criteria.map((c,i) => <li key={i}><strong>{checkFields[c.field] || c.field.replaceAll('_',' ')}</strong>: {comparisonText(c)} {c.expected}</li>)}</ul>}
      {!loading && !error && plan && <AutomaticCheckPlan plan={plan} edited={edited} onSource={(documentId,page)=>void inspect({document_version_id:documentId,page})}/>}
      <button disabled={busy || loading || (confirmed && !reviewer.trim())} onClick={() => void run()}>{busy ? 'Checking documents…' : 'Run document checks'}</button>
      <details className="advanced-checks"><summary>Advanced: edit checks</summary>
        <p>Only change these checks when the tender supports your change. Use the exact words from its PDF.</p>
        <p className="muted">Automatic checks use details that can be read clearly from the tender and company documents. Unclear wording, units, dates or product options still need review.</p>
        {criteria.map((c,i) => <fieldset key={i}><legend>Check {i+1}</legend><div className="criteria-grid">
          <label>Detail to check<select value={c.field} onChange={e => change(i,'field',e.target.value)}>{!fields.some(([value])=>value===c.field) && <option value={c.field}>{c.field.replaceAll('_',' ')}</option>}{fields.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <label>Document type<select value={c.evidence_type} onChange={e => change(i,'evidence_type',e.target.value)}>{types.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <label>Comparison<select value={c.operator} onChange={e => change(i,'operator',e.target.value)}><option value="eq">Must match</option>{['processor','cpu_family','graphics'].includes(c.field) && <option value="baseline">Source baseline (other models need review)</option>}{!['storage_type','memory_type','operating_system','bluetooth','wifi','webcam','speaker','usb','display_backlight','hdmi','vga','ethernet'].includes(c.field) && <><option value="gte">At least / on or after</option><option value="lt">Less than</option><option value="lte">No more than / on or before</option></>}<option value="present">Must be included</option></select></label>
          <label>Value required by the tender<input value={c.expected} maxLength={200} onChange={e => change(i,'expected',e.target.value)}/></label>
        </div><label>Exact words from the requirement<textarea value={c.quote} maxLength={5000} onChange={e => change(i,'quote',e.target.value)}/></label><button className="secondary" onClick={() => { setCriteria(old => old.filter((_, n) => i !== n)); setConfirmed(false);setEdited(true); }}>Remove check</button></fieldset>)}
        <button className="secondary" disabled={criteria.length >= 30} onClick={() => { setCriteria(old => [...old,{field:'model',operator:'eq',expected:'',quote:'',evidence_type:'datasheet'}]); setConfirmed(false);setEdited(true); }}>Add check</button>
        <label className="checkbox-label"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>I have read the full requirement and the company documents. I confirm that these checks cover every part of the requirement.</label>
      </details>
      <label>Reviewer name<input value={reviewer} maxLength={200} onChange={e => setReviewer(e.target.value)}/></label>
      {error && <p role="alert" className="error">{error}</p>}
      <h4>Results & review</h4>
      {loading && <p role="status">Loading previous results…</p>}
      {!loading && !error && !assessments.length && <p>No checks run yet.</p>}
      {assessments.map((a,index) => <details key={a.id} className={`assessment assessment-${a.status}`} open={index === 0}><summary>{index === 0 ? 'Latest result' : 'Earlier result'} · {statusLabel(a.status)} · {new Date(a.created_at).toLocaleDateString()}</summary>
        <p><strong>{statusLabel(a.status)}</strong></p>
        {a.stale && <p className="warning">The documents, requirement or check date have changed. Run the checks again before approving this result.</p>}
        <p>{a.checks[0]?.method === 'human_correction' ? a.explanation : plainSystemText(a.explanation)}</p><p><strong>Review: {reviewStateLabel(a.review_state)}</strong> — approval means you agree with this result. It is not an official compliance certificate.</p><p className="muted">{a.checks[0]?.method === 'human_correction' ? 'Result changed by a reviewer' : 'Checks using fixed rules and the tender details'} · Not checked by an official authority</p>
        <details className="check-breakdown"><summary>Validation details & source passages ({a.checks.filter(c=>c.rationale).length})</summary>{a.checks.filter(c => c.rationale).map((c,i) => <div key={i}><strong>{checkFields[c.field || c.method] || (c.field || c.method).replaceAll('_', ' ')}: {c.outcome ? checkOutcomes[c.outcome] || c.outcome : 'Reviewer decision'}</strong><p>{c.method === 'deterministic' ? plainSystemText(c.rationale || '') : c.rationale}</p>{c.method === 'component_dependency' && c.source_document_id && c.page && <button className="source-link" onClick={() => void inspect({document_version_id:c.source_document_id!,page:c.page!})}>Component source · page {c.page}</button>}{c.sources?.map(ref => <div key={ref.fact_id}><blockquote>{ref.quote}</blockquote><button className="source-link" onClick={() => void inspect(ref)}>Document page {ref.page} · {ref.filename || ref.document_version_id.slice(0,8)}</button></div>)}</div>)}
        </details><details><summary>Saved tasks & review history ({a.tasks.length + a.reviews.length})</summary>{a.tasks.map(t => <details key={t.id}><summary>{t.title}</summary><p className="preserve-lines">{t.explanation}</p></details>)}
        {a.reviews.map(r => <p key={r.id}><strong>{reviewStateLabel(r.action)} by {r.reviewer}</strong> · <time>{new Date(r.created_at.endsWith('Z') || /[+-]\d\d:\d\d$/.test(r.created_at) ? r.created_at : r.created_at+'Z').toLocaleString()}</time>: {r.comment}</p>)}
        </details>{index === 0 && <><label>Review comments<textarea value={comment} maxLength={4000} onChange={e => setComment(e.target.value)}/></label><div className="document-actions">
          <button disabled={busy || a.stale || !reviewer.trim() || !comment.trim()} onClick={() => void decide(a.id,'approved')}>Approve result</button>
          <button className="secondary" disabled={busy || !reviewer.trim() || !comment.trim()} onClick={() => void decide(a.id,'rejected')}>Reject result</button>
          <button className="secondary" disabled={busy || !reviewer.trim() || !comment.trim()} onClick={() => void decide(a.id,'reopened')}>Review again</button></div>
          <details><summary>Correct this result</summary><label>Change result to<select value={correction} onChange={e => setCorrection(e.target.value)}>{statuses.map(value => <option key={value} value={value}>{statusLabel(value)}</option>)}</select></label>
          <button className="secondary" disabled={busy || a.stale || !reviewer.trim() || !comment.trim()} onClick={() => void decide(a.id,'corrected')}>Save as a new result</button></details></>}
      </details>)}
      {source && <div><button className="secondary" onClick={() => setSource('')}>Close document</button><Suspense fallback={<p>Opening document…</p>}><PdfSource key={source} url={source}/></Suspense></div>}
    </>}
  </div>;
}

function AutomaticCheckPlan({plan,edited,onSource}:{plan:CheckPlan;edited:boolean;onSource:(documentId:string,page:number)=>void}) {
  const ready=plan.kind==='evidence' && plan.coverage==='complete' && plan.auto_coverage_eligible && !edited;
  const title=edited ? 'Checks have been edited manually' : ready ? 'Automatic checks are ready to run' : plan.kind==='procedure' ? 'This is a submission instruction' : plan.kind==='reference' ? 'This is reference information' : 'Some details still need review';
  return <section aria-label="Automatic check plan">
    <h4>Automatic check plan</h4><p><strong>{title}</strong></p>
    <p className="muted">{edited ? 'Check your changes against the original tender. The automatic plan below describes the saved requirement.' : ready ? 'The tender gives enough detail to prepare these checks. Run them to compare your documents; this does not approve the result.' : plan.kind==='procedure' ? 'Follow the instruction and record what you did. A matching product value alone cannot show that this step is done.' : plan.kind==='reference' ? 'Check whether this text asks you to do anything. It is not proof that a product or company qualifies.' : 'The system will check what it can and keep the unclear parts for review.'}</p>
    {plan.scope.label && <p><strong>Product option:</strong> {plan.scope.label}</p>}
    {plan.scope.state==='matched' && <p><strong>Documents linked to this product option:</strong> {plan.scope.documents.map(doc=>doc.filename).join(', ')}</p>}
    {plan.scope.state==='missing' && <p className="warning">No company document is linked to this product option.</p>}
    {plan.scope.state==='needs_review' && <p className="warning">The product option and company document need to be matched by a reviewer.</p>}
    {plan.scope.reason && <p className="muted">{plainSystemText(plan.scope.reason)}</p>}
    {plan.review_reasons.length>0 && <ul aria-label="Why this plan needs review">{plan.review_reasons.map((reason,i)=><li key={i}>{plainSystemText(reason)}</li>)}</ul>}
    {plan.unhandled.length>0 && <details><summary>Parts that cannot be checked automatically ({plan.unhandled.length})</summary>{plan.unhandled.map((item,i)=><div key={i}><blockquote className="preserve-lines">{item.text}</blockquote><p>{plainSystemText(item.reason)}</p></div>)}</details>}
    {plan.scope_refs.map((ref,i)=><details key={`scope-${i}`}><summary>Product heading · page {ref.page}</summary><blockquote className="preserve-lines">{ref.text}</blockquote><button className="source-link" onClick={()=>onSource(ref.source_document_id,ref.page)}>Open product heading · page {ref.page}</button></details>)}
    {plan.sources.map((source,i)=><details key={`${source.source_span_id}-${i}`}><summary>Tender wording used for these checks · page {source.page}</summary><blockquote className="preserve-lines">{source.quote}</blockquote><button className="source-link" onClick={()=>onSource(source.source_document_id,source.page)}>Open tender page {source.page}</button></details>)}
  </section>;
}

export function ManualRequirementEntry({ prefix, documentId, request, onSaved }: { prefix:string; documentId:string; request:Request; onSaved:() => void }) {
  const [pages, setPages] = useState<{page:number;text:string}[]>([]);
  const [page, setPage] = useState(1);
  const [excerpt, setExcerpt] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function loadPages() { try { setPages(await (await request(`${prefix}/documents/${documentId}/pages`)).json()); } catch (e) { setError(e instanceof Error ? plainSystemText(e.message) : 'Could not open the document. Please try again.'); } }
  async function save(event:FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { await request(`${prefix}/documents/${documentId}/manual-requirements`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ page, excerpt, reviewer })}); setExcerpt(''); onSaved(); }
    catch (e) { setError(e instanceof Error ? plainSystemText(e.message) : 'Could not save the requirement. Please try again.'); }
    finally { setBusy(false); }
  }
  return <details><summary>Add a requirement manually</summary><p>Copy the exact words from the tender. The record will show that you added this requirement, rather than the AI.</p><button className="secondary" onClick={() => void loadPages()}>Show PDF text</button>
    {pages.length > 0 && <><label>PDF page<select value={page} onChange={e => setPage(Number(e.target.value))}>{pages.map(p => <option key={p.page} value={p.page}>Page {p.page}</option>)}</select></label><pre className="page-transcript">{pages.find(p => p.page === page)?.text}</pre></>}
    <form onSubmit={save}><label>Exact words from the tender<textarea required maxLength={5000} value={excerpt} onChange={e => setExcerpt(e.target.value)}/></label><label>Reviewer name<input required maxLength={200} value={reviewer} onChange={e => setReviewer(e.target.value)}/></label><button disabled={busy || !pages.length}>Save requirement</button></form>{error && <p role="alert" className="error">{error}</p>}
  </details>;
}
