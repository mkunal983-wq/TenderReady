import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { IconCircleCheckFilled, IconAlertTriangleFilled, IconBolt, IconFileText, IconCalendar, IconArrowRight, IconRefresh, IconSearch } from '@tabler/icons-react';
import './workspace-theme.css';
import { categoryLabel, obligationLabel, statusLabel, plainSystemText } from './plainLanguage';
import { workspaceHref, workspacePages, type WorkspacePage } from './workspaceRoutes';
import { RequirementVerification } from './EvidenceWorkflow';
import type { SourceContext } from './sourceContext';
import { ReconciledConditions, type QuantityCondition, type TemporalCondition } from './ReconciledConditions';
const PdfSource = lazy(() => import('./PdfSource'));
type Request = (path: string, init?: RequestInit) => Promise<Response>;
const statuses: Record<string, string> = Object.fromEntries(['reference_only','action_required','not_checked','supported','inconclusive','conflicting','missing','outdated'].map(key=>[key,statusLabel(key)]));
const statusIcons = {reference_only:IconFileText,action_required:IconFileText,not_checked:IconFileText,supported:IconCircleCheckFilled,inconclusive:IconBolt,conflicting:IconAlertTriangleFilled,missing:IconFileText,outdated:IconCalendar};
export type RequirementRow = {quantity_conditions?:QuantityCondition[];temporal_conditions?:TemporalCondition[];source_context?:SourceContext[]; requirement_id:string; stable_id:string; clause_id:string|null; version:number; text:string; filename:string; document_id:string; page:number; category:string; obligation:string; status:string; label:string; reasons:string[]; unresolved:boolean; blocking:boolean; active?:boolean; assessment:{id:string; review_state:string; explanation:string}|null};
type Task = {id:string; assessment_id:string; requirement_id:string; title:string; explanation:string; priority:string; status:string; due_date:string|null; revision:number; historical:boolean; history:{id:string; reviewer:string; comment:string; created_at:string; changes?:{before:Record<string,unknown>|null;after:Record<string,unknown>}}[]};
type Dashboard = {review_complete:boolean; notice:string; blockers:string[]; counts:Record<string,number>; requirements:RequirementRow[]; tasks:Task[]; snapshot_sequence:number|null};
type BulkResult = {total:number;checked:number;skipped:number;failed:number;provider_calls:number;results:{requirement_id:string;assessment_id:string|null;outcome:'checked'|'skipped'|'failed';status:string;reason:string}[]};
type TimelineEvent = {id:string; kind:string; created_at:string; title:string; description:string; requirement_id?:string; changes?:{before:Record<string,unknown>|null;after:Record<string,unknown>}};
export function filterRequirements(rows:RequirementRow[], status:string, category:string) {
  return rows.filter(r => (!status || r.status === status) && (!category || r.category === category));
}
function approvalPending(row:RequirementRow) { return row.status==='supported' && row.assessment?.review_state==='awaiting_review'; }
function message(error:unknown) { return error instanceof Error ? plainSystemText(error.message) : 'Could not complete this request. Please retry.'; }
export function SupplierDashboard({prefix, request, revision, onChanged, onUploadAmendment, page='all', workspaceId, initialStatus=''}:{page?:WorkspacePage|'all'; workspaceId?:string; initialStatus?:string; prefix:string; request:Request; revision:string; onChanged:()=>void; onUploadAmendment?:()=>void}) {
  const [data,setData] = useState<Dashboard|null>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState('');
  const [reload,setReload] = useState(0);
  const [status,setStatus] = useState(initialStatus in statuses ? initialStatus : '');
  const [search,setSearch] = useState('');
  const [sort,setSort] = useState('priority');
  const [category,setCategory] = useState('');
  const [selected,setSelected] = useState('');
  const [exporting,setExporting] = useState('');
  const [historical,setHistorical] = useState(false);
  const [checkingAll,setCheckingAll] = useState(false);
  const [bulkResult,setBulkResult] = useState<BulkResult|null>(null);
  const [bulkError,setBulkError] = useState('');
  const bulkRequest = useRef<AbortController|null>(null);
  useEffect(()=>{setStatus(initialStatus in statuses ? initialStatus : '');setSelected('');},[initialStatus,prefix,page]);
  useEffect(()=>{setBulkResult(null);setBulkError('');setCheckingAll(false);return ()=>{bulkRequest.current?.abort();bulkRequest.current=null;};},[prefix]);
  const requirementPage = page==='all' || page==='requirements';
  const overviewPage = page==='all' || page==='readiness';
  const changed = () => { setReload(v=>v+1); onChanged(); };
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    void request(`${prefix}/dashboard`,{signal:controller.signal}).then(r=>r.json()).then(body=>{
      if (!controller.signal.aborted) setData(body);
    }).catch(e=>{if (!controller.signal.aborted) {setData(null);setError(message(e));}})
      .finally(()=>{if (!controller.signal.aborted) setLoading(false);});
    return ()=>controller.abort();
  },[prefix,request,revision,reload]);
  async function checkAll() {
    if (bulkRequest.current) return;
    const controller = new AbortController(); bulkRequest.current = controller;
    setCheckingAll(true); setBulkResult(null); setBulkError('');
    try {
      const response = await request(`${prefix}/verify-all`, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:controller.signal});
      const result:BulkResult = await response.json();
      if (!controller.signal.aborted) {setBulkResult(result);changed();}
    } catch(e) {
      if (!controller.signal.aborted) {setBulkError(message(e));setReload(v=>v+1);}
    } finally {
      if (!controller.signal.aborted) setCheckingAll(false);
      if (bulkRequest.current === controller) bulkRequest.current = null;
    }
  }
  async function download(kind:string) {
    setExporting(kind); setError('');
    try {
      const response = await request(`${prefix}/exports/${kind}`);
      const blob = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href=blob; link.download=`${kind}.csv`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(()=>URL.revokeObjectURL(blob),1000);
    } catch(e) {setError(message(e));} finally {setExporting('');}
  }
  const visible = data ? filterRequirements(data.requirements,status,category).filter(r=>`${r.clause_id || r.stable_id} ${r.text} ${r.filename} ${(r.source_context || []).map(c=>c.text).join(' ')}`.toLowerCase().includes(search.toLowerCase())).sort((a,b)=>sort==='id' ? (a.clause_id || a.stable_id).localeCompare(b.clause_id || b.stable_id) : Number(b.blocking)-Number(a.blocking) || Number(b.unresolved)-Number(a.unresolved)) : [];
  return <section className={`supplier-dashboard ${requirementPage ? "ws-requirements-page" : ""}`} aria-label="Supplier readiness dashboard">
    <div className="ws-heading"><div><h3>{page==='all' || page==='readiness' ? 'Evidence readiness' : workspacePages[page]}</h3><p className="muted">{page==='tasks' ? 'See what needs fixing, when it is due, and who reviewed it.' : page==='export' ? 'Download the requirements checklist and document list, including items that still need attention.' : 'Check tender requirements, review company documents, and fix missing or incorrect details.'}</p></div><div className="document-actions">{(overviewPage || requirementPage) && <button disabled={checkingAll || loading || !data?.requirements.length} onClick={()=>void checkAll()}>{checkingAll ? 'Checking documents…' : 'Check all documents'}</button>}<button className="secondary" disabled={loading || checkingAll} onClick={()=>setReload(v=>v+1)}><IconRefresh size={15}/> Refresh results</button><a className="ws-primary-link" href={workspaceId ? workspaceHref(workspaceId,"amendments") : "#tender-upload"} onClick={onUploadAmendment}>Upload tender update <IconArrowRight size={15}/></a></div></div>
    {loading && <p role="status">Loading documents and reviews…</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {(overviewPage || requirementPage) && <details className="ws-check-help"><summary>How document checks work</summary><p>Check all current requirements using the documents in this workspace. Clear checks are prepared for you. Unclear details still need review; existing approvals are kept when nothing has changed.</p></details>}
    {checkingAll && <p role="status">Checking documents and saving results. No AI credits are used.</p>}
    {bulkError && <p role="alert" className="error">{bulkError} Check the latest results below before trying again.</p>}
    {bulkResult && <div className="ws-bulk-result" role="status"><strong>Document checks finished</strong><p>{bulkResult.checked} checked · {bulkResult.skipped} already up to date · {bulkResult.failed} could not be checked · {bulkResult.total} total</p><p>These are document checks, not approvals. Review any unclear or missing details.</p>{bulkResult.failed > 0 && <ul>{bulkResult.results.filter(r=>r.outcome==='failed').map(r=><li key={r.requirement_id}><button className="source-link" onClick={()=>setSelected(r.requirement_id)}>Open requirement</button>: {plainSystemText(r.reason)}</li>)}</ul>}</div>}
    {data && <div aria-busy={loading || checkingAll}>
      {overviewPage && <div className="readiness-counts">{Object.entries(statuses).map(([key,label])=>{const Icon=statusIcons[key as keyof typeof statusIcons];const count=data.counts[key] || 0;const content=<><Icon size={21}/><strong>{count}</strong><span>{label}</span><small>{data.requirements.length ? `${Math.round(count/data.requirements.length*100)}% of ${data.requirements.length} requirements` : 'Upload a tender to get started'}</small></>;return workspaceId ? <a className={`assessment ws-status-card assessment-${key}`} key={key} aria-label={`View ${label.toLowerCase()} requirements (${count})`} href={workspaceHref(workspaceId,'requirements',key)}>{content}</a> : <button className={`assessment ws-status-card assessment-${key}`} key={key} aria-label={`View ${label.toLowerCase()} requirements (${count})`} onClick={()=>{setStatus(key);document.getElementById('readiness-requirements')?.scrollIntoView?.({block:'start'});}}>{content}</button>;})}</div>}
      <div className="ws-snapshot"><span>Version {data.snapshot_sequence || '—'}</span><span className="ws-latest">{data.snapshot_sequence ? 'Current version' : 'Draft'}</span></div>
      <h4>{data.review_complete ? 'Evidence review complete' : 'Action required'}</h4>{data.review_complete && data.requirements.some(r=>r.unresolved) && <p className="warning">Some optional items still need attention. Review complete does not mean every optional item is supported.</p>}
      <details className="ws-review-note"><summary>Review scope & tender version</summary><p>{plainSystemText(data.notice)}</p><p className="muted">{data.snapshot_sequence ? `Current tender version ${data.snapshot_sequence}` : 'Draft tender · starting version not saved yet'} · The totals include all current requirements.</p></details>
      {data.blockers.length>0 && <div className="ws-attention"><strong>{plainSystemText(data.blockers[0])}</strong>{data.blockers.length>1 && <details><summary>{data.blockers.length-1} more items need attention</summary><ul className="readiness-blockers">{data.blockers.slice(1).map(b=><li key={b}>{plainSystemText(b)}</li>)}</ul></details>}</div>}
      {page==='readiness' && workspaceId && <div className="ws-page-links"><a className="ws-primary-link" href={workspaceHref(workspaceId,"requirements")}>Review requirements <IconArrowRight size={15}/></a><a className="ws-primary-link" href={workspaceHref(workspaceId,"evidence")}>Open evidence library</a></div>}
      {requirementPage && <>
      <div id="readiness-requirements" className="ws-status-tabs" role="group" aria-label="Requirement status filters"><button aria-pressed={status===''} className={status===''?'active':''} onClick={()=>setStatus('')}>All requirements ({data.requirements.length})</button>{Object.entries(statuses).filter(([key])=>(data.counts[key] || 0)>0 || status===key).map(([key,label])=><button aria-pressed={status===key} key={key} className={status===key?'active':''} onClick={()=>setStatus(key)}>{label} ({data.counts[key] || 0})</button>)}</div>
      <div className="ws-filterbar"><label className="ws-search">Search requirements<span><IconSearch size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search requirements…"/></span></label>
      <div className="criteria-grid"><label>Status<select value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{Object.entries(statuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label>Category<select value={category} onChange={e=>setCategory(e.target.value)}><option value="">All categories</option>{[...new Set(data.requirements.map(r=>r.category))].sort().map(c=><option key={c} value={c}>{categoryLabel(c)}</option>)}</select></label></div><label>Sort requirements<select value={sort} onChange={e=>setSort(e.target.value)}><option value="priority">Priority</option><option value="id">Requirement ID</option></select></label></div>
      {!data.requirements.length ? <p>No requirements yet. Open Amendments, upload a tender, read its requirements, and save the starting version after review.</p> : !visible.length ? <p>No requirements match these filters. The totals above still include all requirements.</p> : <div className="ws-table-scroll"><table className="ws-requirements"><thead><tr><th>ID</th><th>Requirement</th><th>Category</th><th>Status</th><th>Source</th><th>Actions</th></tr></thead><tbody>{visible.map(r=><tr key={r.requirement_id} className={`ws-row-${r.status}`}><td><strong>{r.clause_id || r.stable_id.slice(0,8)}</strong></td><td>{r.source_context?.map((context,i)=><small className="preserve-lines" key={`${context.source_document_id}-${context.page}-${i}`}><strong>{context.text}</strong> · page {context.page}</small>)}<span className="ws-clause">{r.text}</span><small>{obligationLabel(r.obligation)}</small></td><td><span className="ws-category">{categoryLabel(r.category)}</span></td><td><span className={`ws-status ws-status-${r.status}`}>{statusLabel(r.status)}</span>{approvalPending(r) && <small>Approval pending</small>}{r.status==='action_required' && workspaceId && <small><a href={workspaceHref(workspaceId,'tasks')}>Open tasks</a></small>}</td><td><span title={r.filename}>Page {r.page}</span></td><td><button className="ws-review" aria-label={`Review requirement ${r.clause_id || r.stable_id.slice(0,8)}`} onClick={()=>setSelected(r.requirement_id)}>Review <IconArrowRight size={14}/></button></td></tr>)}</tbody></table></div>}
      </>}
      {selected && <RequirementDialog key={selected} onClose={()=>setSelected('')}><RequirementDetail id={selected} prefix={prefix} request={request} revision={revision+reload} onChanged={changed}/></RequirementDialog>}
      {(page==='all' || page==='tasks') && <>
      <h3 id="workspace-tasks">Tasks to fix issues</h3><p className="muted">Marking a task done records your work. To update the result, run the document checks again and ask for review.</p>
      <label className="checkbox-label"><input type="checkbox" checked={historical} onChange={e=>setHistorical(e.target.checked)}/>Show tasks from older checks</label>
      {!data.tasks.filter(t=>historical || !t.historical).length && <p>No tasks for the current checks.</p>}
      {data.tasks.filter(t=>historical || !t.historical).map(t=><details key={`${t.id}-${t.revision}`}><summary>{t.title} · {t.priority} · {t.status}{t.historical ? ' · Older check' : ''}{t.due_date ? ` · Due ${t.due_date}` : ''}</summary><button className="source-link" onClick={()=>setSelected(t.requirement_id)}>View requirement</button><TaskForm task={t} prefix={prefix} request={request} onSaved={changed}/>{t.history.map(h=><p key={h.id}><strong>{h.reviewer}</strong> · <time>{new Date(h.created_at).toLocaleString()}</time>: {h.comment}{h.changes && <AuditChanges changes={h.changes}/>}</p>)}</details>)}
      </>}
      {(page==='all' || page==='export') && <>
      <h3 id="workspace-exports">Download reports</h3><p className="muted">These CSV files open in Excel or Google Sheets. They include every current requirement, items needing attention, PDF page links, and review status. Filters do not change the download.</p>
      <div className="document-actions">{['compliance-matrix','evidence-index'].map(kind=><button className="secondary" key={kind} disabled={!!exporting || loading} onClick={()=>void download(kind)}>{exporting===kind ? 'Preparing download…' : kind==='compliance-matrix' ? 'Download requirements checklist (CSV)' : 'Download document list (CSV)'}</button>)}</div>
      </>}
      {overviewPage && <VersionTimeline key={revision+reload} prefix={prefix} request={request} onSelect={setSelected}/>}
    </div>}
  </section>;
}

function RequirementDialog({children,onClose}:{children:ReactNode;onClose:()=>void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(()=>{
    const panel = dialog.current!;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    panel.showModal();
    document.body.style.overflow = 'hidden';
    close.current?.focus();
    return ()=>{panel.close();document.body.style.overflow=previousOverflow;if(previous?.isConnected)previous.focus({preventScroll:true});};
  },[]);
  return <dialog ref={dialog} className="ws-requirement-dialog" aria-label="Requirement review" onCancel={event=>{event.preventDefault();onClose();}} onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();onClose();}}}>
    <header className="ws-review-header"><h2>Review requirement</h2><button ref={close} className="secondary" onClick={onClose}>Close requirement detail</button></header>
    {children}
  </dialog>;
}

function RequirementDetail({id,prefix,request,revision,onChanged}:{id:string;prefix:string;request:Request;revision:string;onChanged:()=>void}) {
  const [row,setRow]=useState<RequirementRow|null>(null);
  const [error,setError]=useState('');
  const [source,setSource]=useState('');
  const [sourceBusy,setSourceBusy]=useState(false);
  const blob=useRef(''); const sourceAbort=useRef<AbortController|null>(null);
  useEffect(()=>{
    const controller=new AbortController(); setError('');
    void request(`${prefix}/requirements/${id}/detail`,{signal:controller.signal}).then(r=>r.json()).then(r=>{if(!controller.signal.aborted)setRow(r);}).catch(e=>{if(!controller.signal.aborted)setError(message(e));});
    return ()=>controller.abort();
  },[id,prefix,request,revision]);
  useEffect(()=>()=>{sourceAbort.current?.abort();if(blob.current)URL.revokeObjectURL(blob.current);},[]);
  async function inspect(page=row?.page,documentId=row?.document_id) {
    if(!row||!page||!documentId)return;sourceAbort.current?.abort();const controller=new AbortController();sourceAbort.current=controller;setSourceBusy(true);setError('');
    try {const response=await request(`${prefix}/documents/${documentId}/file`,{signal:controller.signal});const file=await response.blob();if(controller.signal.aborted)return;
      if(blob.current)URL.revokeObjectURL(blob.current);blob.current=URL.createObjectURL(file);setSource(`${blob.current}#page=${page}`);
    }catch(e){if(!controller.signal.aborted)setError(message(e));}finally{if(!controller.signal.aborted)setSourceBusy(false);}
  }
  return <section className="requirement requirement-detail" aria-label="Requirement detail"><h3>Tender clause</h3>
    {error && <p role="alert" className="error">{error}</p>}{!row&&!error&&<p role="status">Loading requirement and past reviews…</p>}
    {row&&<><h4>{row.clause_id || row.stable_id.slice(0,8)} · {statusLabel(row.status)}</h4>{approvalPending(row) && <p><strong>Approval pending.</strong> The document checks passed, but this result still needs a reviewer's approval.</p>}{row.active === false && <p className="warning">This is a draft or older requirement. It is not part of the saved current tender version.</p>}<p>{obligationLabel(row.obligation)} · {categoryLabel(row.category)} · version {row.version}</p><blockquote className="preserve-lines">{row.text}</blockquote>{row.source_context?.map((context,i)=><div className="muted" key={`${context.source_document_id}-${context.page}-${i}`}><strong>Related heading in the PDF</strong><p className="preserve-lines">{context.text}</p><button className="source-link" disabled={sourceBusy} onClick={()=>void inspect(context.page,context.source_document_id)}>Heading · page {context.page}</button></div>)}<button className="source-link" disabled={sourceBusy} onClick={()=>void inspect()}>{sourceBusy?'Opening PDF…':`${row.filename} · page ${row.page}`}</button><details className="review-explanation"><summary>Why this status?</summary>{[...new Set(row.reasons.map(plainSystemText))].map((reason,i)=><p key={i}>{reason}</p>)}</details><ReconciledConditions quantities={row.quantity_conditions} temporal={row.temporal_conditions} sourceBusy={sourceBusy} onSource={(sourcePage,documentId)=>void inspect(sourcePage,documentId)}/>
      {source&&<><button className="secondary" onClick={()=>setSource('')}>Close PDF</button><Suspense fallback={<p>Opening PDF…</p>}><PdfSource url={source}/></Suspense></>}
      <RequirementVerification prefix={prefix} requirementId={id} request={request} libraryRevision={revision} initialOpen onChanged={onChanged}/>
      {row.assessment ? <details><summary>Add a task</summary><TaskForm assessmentId={row.assessment.id} prefix={prefix} request={request} onSaved={onChanged}/></details>:<p>Run the document checks before adding a task for this requirement.</p>}
    </>}
  </section>;
}

function TaskForm({task,assessmentId,prefix,request,onSaved}:{task?:Task;assessmentId?:string;prefix:string;request:Request;onSaved:()=>void}) {
  const [title,setTitle]=useState(task?.title||'');const [description,setDescription]=useState(task?.explanation||'');
  const [priority,setPriority]=useState(task?.priority||'medium');const [status,setStatus]=useState(task?.status||'open');
  const [due,setDue]=useState(task?.due_date||'');const [reviewer,setReviewer]=useState('');const [comment,setComment]=useState('');
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  async function save(event:FormEvent){event.preventDefault();setBusy(true);setError('');try{
    await request(`${prefix}/tasks${task?'/'+task.id:''}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,explanation:description,priority,due_date:due||null,reviewer,comment,...(task?{status,expected_revision:task.revision}:{assessment_id:assessmentId})})});onSaved();
  }catch(e){setError(message(e));}finally{setBusy(false);}}
  return <form onSubmit={save}><label>Task title<input required maxLength={250} value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Action to take<textarea required maxLength={4000} value={description} onChange={e=>setDescription(e.target.value)}/></label><div className="criteria-grid"><label>Priority<select value={priority} onChange={e=>setPriority(e.target.value)}>{['low','medium','high'].map(v=><option key={v}>{v}</option>)}</select></label><label>Due date (optional)<input type="date" value={due} onChange={e=>setDue(e.target.value)}/></label>{task&&<label>Task status<select value={status} onChange={e=>setStatus(e.target.value)}>{['open','resolved','dismissed'].map(v=><option key={v} value={v}>{{open:'To do',resolved:'Done',dismissed:'Dismissed'}[v]}</option>)}</select></label>}</div><label>Your name<input required maxLength={200} value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label><label>Update notes<textarea required maxLength={4000} value={comment} onChange={e=>setComment(e.target.value)}/></label><button disabled={busy}>{busy?'Saving task…':task?'Save task changes':'Create task'}</button>{error&&<p role="alert" className="error">{error}</p>}</form>;
}

function VersionTimeline({prefix,request,onSelect}:{prefix:string;request:Request;onSelect:(id:string)=>void}) {
  const [events,setEvents]=useState<TimelineEvent[]>([]);const [total,setTotal]=useState(0);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [open,setOpen]=useState(false);
  const controller=useRef<AbortController|null>(null);
  const load=useCallback(async(offset=0)=>{controller.current?.abort();const abort=new AbortController();controller.current=abort;setBusy(true);setError('');try{const data=await(await request(`${prefix}/timeline?offset=${offset}&limit=30`,{signal:abort.signal})).json();if(!abort.signal.aborted){setEvents(old=>offset?[...old,...data.items]:data.items);setTotal(data.total);}}catch(e){if(!abort.signal.aborted)setError(message(e));}finally{if(!abort.signal.aborted)setBusy(false);}},[prefix,request]);
  useEffect(()=>()=>controller.current?.abort(),[]);
  return <section id="workspace-timeline" aria-label="Version timeline"><h3>Tender changes and review history</h3><button className="secondary" onClick={()=>{setOpen(v=>!v);if(!open)void load();}}>{open?'Hide history':'Show history'}</button>{open&&<>{busy&&<p role="status">Loading history…</p>}{error&&<p role="alert" className="error">{error}<button onClick={()=>void load()}>Try loading history again</button></p>}{!busy&&!error&&!events.length&&<p>No changes or reviews saved yet.</p>}<ol className="version-timeline">{events.map(e=><li key={e.id}><strong>{e.kind==='reassessment' ? 'Check reopened' : e.kind==='task' ? 'Task created' : e.title}</strong><time>{new Date(e.created_at).toLocaleString()}</time><p className="preserve-lines">{e.description}</p>{e.changes && <AuditChanges changes={e.changes}/>}{e.requirement_id&&<button className="source-link" onClick={()=>onSelect(e.requirement_id!)}>View requirement</button>}</li>)}</ol>{events.length<total&&<button disabled={busy} onClick={()=>void load(events.length)}>Show older changes</button>}</>}</section>;
}

function AuditChanges({changes}:{changes:{before:Record<string,unknown>|null;after:Record<string,unknown>}}) {
  return <span className="audit-changes">{Object.entries(changes.after).filter(([key,value])=>changes.before?.[key]!==value).map(([key,value])=><span key={key}><strong>{key.replaceAll('_',' ')}:</strong> {String(changes.before?.[key] ?? 'not set')} → {String(value ?? 'not set')}<br/></span>)}</span>;
}
