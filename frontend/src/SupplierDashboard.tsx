import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { IconCircleCheckFilled, IconAlertTriangleFilled, IconBolt, IconFileText, IconCalendar, IconArrowRight, IconRefresh, IconSearch } from '@tabler/icons-react';
import './workspace-theme.css';
import { workspaceHref, workspacePages, type WorkspacePage } from './workspaceRoutes';
import { RequirementVerification } from './EvidenceWorkflow';
const PdfSource = lazy(() => import('./PdfSource'));
type Request = (path: string, init?: RequestInit) => Promise<Response>;
const statuses: Record<string, string> = {supported:'Supported by evidence', inconclusive:'Needs human review', conflicting:'Conflict detected', missing:'Missing', outdated:'Outdated'};
const statusIcons = {supported:IconCircleCheckFilled,inconclusive:IconBolt,conflicting:IconAlertTriangleFilled,missing:IconFileText,outdated:IconCalendar};
export type RequirementRow = {requirement_id:string; stable_id:string; clause_id:string|null; version:number; text:string; filename:string; document_id:string; page:number; category:string; obligation:string; status:string; label:string; reasons:string[]; unresolved:boolean; blocking:boolean; active?:boolean; assessment:{id:string; review_state:string; explanation:string}|null};
type Task = {id:string; assessment_id:string; requirement_id:string; title:string; explanation:string; priority:string; status:string; due_date:string|null; revision:number; historical:boolean; history:{id:string; reviewer:string; comment:string; created_at:string; changes?:{before:Record<string,unknown>|null;after:Record<string,unknown>}}[]};
type Dashboard = {review_complete:boolean; notice:string; blockers:string[]; counts:Record<string,number>; requirements:RequirementRow[]; tasks:Task[]; snapshot_sequence:number|null};
type TimelineEvent = {id:string; kind:string; created_at:string; title:string; description:string; requirement_id?:string; changes?:{before:Record<string,unknown>|null;after:Record<string,unknown>}};
export function filterRequirements(rows:RequirementRow[], status:string, category:string) {
  return rows.filter(r => (!status || r.status === status) && (!category || r.category === category));
}
function message(error:unknown) { return error instanceof Error ? error.message : 'Could not complete this request. Please retry.'; }
export function SupplierDashboard({prefix, request, revision, onChanged, onUploadAmendment, page='all', workspaceId}:{page?:WorkspacePage|'all'; workspaceId?:string; prefix:string; request:Request; revision:string; onChanged:()=>void; onUploadAmendment?:()=>void}) {
  const [data,setData] = useState<Dashboard|null>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState('');
  const [reload,setReload] = useState(0);
  const [status,setStatus] = useState('');
  const [search,setSearch] = useState('');
  const [sort,setSort] = useState('priority');
  const [category,setCategory] = useState('');
  const [selected,setSelected] = useState('');
  const [exporting,setExporting] = useState('');
  const [historical,setHistorical] = useState(false);
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
  const visible = data ? filterRequirements(data.requirements,status,category).filter(r=>`${r.clause_id || r.stable_id} ${r.text} ${r.filename}`.toLowerCase().includes(search.toLowerCase())).sort((a,b)=>sort==='id' ? (a.clause_id || a.stable_id).localeCompare(b.clause_id || b.stable_id) : Number(b.blocking)-Number(a.blocking) || Number(b.unresolved)-Number(a.unresolved)) : [];
  return <section className="supplier-dashboard" aria-label="Supplier readiness dashboard">
    <div className="ws-heading"><div><h3>{page==='all' || page==='readiness' ? 'Evidence readiness' : workspacePages[page]}</h3><p className="muted">{page==='tasks' ? 'Track corrective actions, deadlines, and reviewer updates.' : page==='export' ? 'Download the current compliance matrix and evidence index, including unresolved issues.' : 'Review requirements, verify supporting evidence, and resolve outstanding issues.'}</p></div><div className="document-actions"><button className="secondary" disabled={loading} onClick={()=>setReload(v=>v+1)}><IconRefresh size={15}/> Refresh readiness</button><a className="ws-primary-link" href={workspaceId ? workspaceHref(workspaceId,"amendments") : "#tender-upload"} onClick={onUploadAmendment}>Upload amendment <IconArrowRight size={15}/></a></div></div>
    {loading && <p role="status">Loading current evidence and approvals…</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {data && <div aria-busy={loading}>
      {overviewPage && <div className="readiness-counts">{Object.entries(statuses).map(([key,label])=>{const Icon=statusIcons[key as keyof typeof statusIcons];const count=data.counts[key] || 0;return <div className={`assessment assessment-${key}`} key={key}><Icon size={21}/><strong>{count}</strong><span>{label}</span><small>{data.requirements.length ? `${Math.round(count/data.requirements.length*100)}% of ${data.requirements.length} requirements` : 'Awaiting extraction'}</small></div>;})}</div>}
      <div className="ws-snapshot"><span>Version {data.snapshot_sequence || '—'}</span><span className="ws-latest">{data.snapshot_sequence ? 'Current snapshot' : 'Draft'}</span></div>
      <h4>{data.review_complete ? 'Evidence review complete' : 'Action required'}</h4>{data.review_complete && data.requirements.some(r=>r.unresolved) && <p className="warning">Optional issues remain disclosed below. Review completion does not mean every optional requirement is supported.</p>}
      <p>{data.notice}</p><p className="muted">{data.snapshot_sequence ? `Current tender snapshot ${data.snapshot_sequence}` : 'Draft tender · baseline not published'} · Counts always include every active requirement.</p>
      {data.blockers.length>0 && <ul className="readiness-blockers">{data.blockers.map(b=><li key={b}>{b}</li>)}</ul>}
      {page==='readiness' && workspaceId && <div className="ws-page-links"><a className="ws-primary-link" href={workspaceHref(workspaceId,"requirements")}>Review requirements <IconArrowRight size={15}/></a><a className="ws-primary-link" href={workspaceHref(workspaceId,"evidence")}>Open evidence library</a></div>}
      {requirementPage && <>
      <div id="readiness-requirements" className="ws-status-tabs" role="group" aria-label="Requirement status filters"><button className={status===''?'active':''} onClick={()=>setStatus('')}>All requirements ({data.requirements.length})</button>{Object.entries(statuses).map(([key,label])=><button key={key} className={status===key?'active':''} onClick={()=>setStatus(key)}>{label} ({data.counts[key] || 0})</button>)}</div>
      <div className="ws-filterbar"><label className="ws-search">Search requirements<span><IconSearch size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search requirements…"/></span></label>
      <div className="criteria-grid"><label>Filter by evidence status<select value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{Object.entries(statuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label>Filter by requirement category<select value={category} onChange={e=>setCategory(e.target.value)}><option value="">All categories</option>{[...new Set(data.requirements.map(r=>r.category))].sort().map(c=><option key={c} value={c}>{c.replaceAll('_',' ')}</option>)}</select></label></div><label>Sort requirements<select value={sort} onChange={e=>setSort(e.target.value)}><option value="priority">Priority</option><option value="id">Requirement ID</option></select></label></div>
      {!data.requirements.length ? <p>No requirements yet. Open Amendments to upload a tender, extract its requirements, and publish a reviewed baseline.</p> : !visible.length ? <p>No requirements match these filters. The readiness counts above remain unchanged.</p> : <div className="ws-table-scroll"><table className="ws-requirements"><thead><tr><th>ID</th><th>Requirement</th><th>Category</th><th>Status</th><th>Source</th><th>Actions</th></tr></thead><tbody>{visible.map(r=><tr key={r.requirement_id} className={`ws-row-${r.status}`}><td><strong>{r.clause_id || r.stable_id.slice(0,8)}</strong></td><td><span className="ws-clause">{r.text}</span><small>{r.obligation}</small></td><td><span className="ws-category">{r.category.replaceAll('_',' ')}</span></td><td><span className={`ws-status ws-status-${r.status}`}>{r.label}</span></td><td><span title={r.filename}>Page {r.page}</span></td><td><button className="ws-review" aria-label={`Review requirement ${r.clause_id || r.stable_id.slice(0,8)}`} onClick={()=>setSelected(r.requirement_id)}>Review <IconArrowRight size={14}/></button></td></tr>)}</tbody></table></div>}
      </>}
      {selected && <RequirementDetail key={selected} id={selected} prefix={prefix} request={request} revision={revision+reload} onChanged={changed} onClose={()=>setSelected('')}/>}
      {(page==='all' || page==='tasks') && <>
      <h3 id="workspace-tasks">Corrective tasks</h3><p className="muted">Resolving a task records work completed. It does not change the evidence finding; rerun verification and obtain review.</p>
      <label className="checkbox-label"><input type="checkbox" checked={historical} onChange={e=>setHistorical(e.target.checked)}/>Include tasks from earlier assessments</label>
      {!data.tasks.filter(t=>historical || !t.historical).length && <p>No corrective tasks for the current assessments.</p>}
      {data.tasks.filter(t=>historical || !t.historical).map(t=><details key={`${t.id}-${t.revision}`}><summary>{t.title} · {t.priority} · {t.status}{t.historical ? ' · Historical' : ''}{t.due_date ? ` · Due ${t.due_date}` : ''}</summary><button className="source-link" onClick={()=>setSelected(t.requirement_id)}>Open linked requirement</button><TaskForm task={t} prefix={prefix} request={request} onSaved={changed}/>{t.history.map(h=><p key={h.id}><strong>{h.reviewer}</strong> · <time>{new Date(h.created_at).toLocaleString()}</time>: {h.comment}{h.changes && <AuditChanges changes={h.changes}/>}</p>)}</details>)}
      </>}
      {(page==='all' || page==='export') && <>
      <h3 id="workspace-exports">Submission exports</h3><p className="muted">CSV exports include all current requirements, unresolved issues, source references, and the overall review state, regardless of filters.</p>
      <div className="document-actions">{['compliance-matrix','evidence-index'].map(kind=><button className="secondary" key={kind} disabled={!!exporting || loading} onClick={()=>void download(kind)}>{exporting===kind ? 'Preparing export…' : `Export ${kind.replaceAll('-',' ')} CSV`}</button>)}</div>
      </>}
      {overviewPage && <VersionTimeline key={revision+reload} prefix={prefix} request={request} onSelect={setSelected}/>}
    </div>}
  </section>;
}

function RequirementDetail({id,prefix,request,revision,onChanged,onClose}:{id:string;prefix:string;request:Request;revision:string;onChanged:()=>void;onClose:()=>void}) {
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
  async function inspect() {
    if(!row)return;sourceAbort.current?.abort();const controller=new AbortController();sourceAbort.current=controller;setSourceBusy(true);setError('');
    try {const response=await request(`${prefix}/documents/${row.document_id}/file`,{signal:controller.signal});const file=await response.blob();if(controller.signal.aborted)return;
      if(blob.current)URL.revokeObjectURL(blob.current);blob.current=URL.createObjectURL(file);setSource(`${blob.current}#page=${row.page}`);
    }catch(e){if(!controller.signal.aborted)setError(message(e));}finally{if(!controller.signal.aborted)setSourceBusy(false);}
  }
  return <section className="requirement requirement-detail" aria-label="Requirement detail"><button className="secondary" onClick={onClose}>Close requirement detail</button><h3>Requirement detail</h3>
    {error && <p role="alert" className="error">{error}</p>}{!row&&!error&&<p role="status">Loading clause and review history…</p>}
    {row&&<><h4>{row.clause_id || row.stable_id} · {row.label}</h4>{row.active === false && <p className="warning">This is a draft or historical requirement version outside the current published snapshot.</p>}<p>{row.obligation} · {row.category.replaceAll('_',' ')} · version {row.version}</p><blockquote className="preserve-lines">{row.text}</blockquote><button className="source-link" disabled={sourceBusy} onClick={()=>void inspect()}>{sourceBusy?'Loading source…':`${row.filename} · page ${row.page}`}</button><p>{row.reasons.join(' ')}</p>
      {source&&<><button className="secondary" onClick={()=>setSource('')}>Close tender source</button><Suspense fallback={<p>Loading PDF viewer…</p>}><PdfSource url={source}/></Suspense></>}
      <RequirementVerification prefix={prefix} requirementId={id} request={request} libraryRevision={0} initialOpen onChanged={onChanged}/>
      {row.assessment ? <details><summary>Create a corrective task</summary><TaskForm assessmentId={row.assessment.id} prefix={prefix} request={request} onSaved={onChanged}/></details>:<p>Run evidence verification before creating a linked corrective task.</p>}
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
  return <form onSubmit={save}><label>Task title<input required maxLength={250} value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Action to take<textarea required maxLength={4000} value={description} onChange={e=>setDescription(e.target.value)}/></label><div className="criteria-grid"><label>Priority<select value={priority} onChange={e=>setPriority(e.target.value)}>{['low','medium','high'].map(v=><option key={v}>{v}</option>)}</select></label><label>Due date (optional)<input type="date" value={due} onChange={e=>setDue(e.target.value)}/></label>{task&&<label>Task status<select value={status} onChange={e=>setStatus(e.target.value)}>{['open','resolved','dismissed'].map(v=><option key={v}>{v}</option>)}</select></label>}</div><label>Task reviewer<input required maxLength={200} value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label><label>Task update comment<textarea required maxLength={4000} value={comment} onChange={e=>setComment(e.target.value)}/></label><button disabled={busy}>{busy?'Saving task…':task?'Save task changes':'Create corrective task'}</button>{error&&<p role="alert" className="error">{error}</p>}</form>;
}

function VersionTimeline({prefix,request,onSelect}:{prefix:string;request:Request;onSelect:(id:string)=>void}) {
  const [events,setEvents]=useState<TimelineEvent[]>([]);const [total,setTotal]=useState(0);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [open,setOpen]=useState(false);
  const controller=useRef<AbortController|null>(null);
  const load=useCallback(async(offset=0)=>{controller.current?.abort();const abort=new AbortController();controller.current=abort;setBusy(true);setError('');try{const data=await(await request(`${prefix}/timeline?offset=${offset}&limit=30`,{signal:abort.signal})).json();if(!abort.signal.aborted){setEvents(old=>offset?[...old,...data.items]:data.items);setTotal(data.total);}}catch(e){if(!abort.signal.aborted)setError(message(e));}finally{if(!abort.signal.aborted)setBusy(false);}},[prefix,request]);
  useEffect(()=>()=>controller.current?.abort(),[]);
  return <section id="workspace-timeline" aria-label="Version timeline"><h3>Version and review timeline</h3><button className="secondary" onClick={()=>{setOpen(v=>!v);if(!open)void load();}}>{open?'Hide timeline':'Show timeline'}</button>{open&&<>{busy&&<p role="status">Loading history…</p>}{error&&<p role="alert" className="error">{error}<button onClick={()=>void load()}>Retry timeline</button></p>}{!busy&&!error&&!events.length&&<p>No saved events yet.</p>}<ol className="version-timeline">{events.map(e=><li key={e.id}><strong>{e.title}</strong><time>{new Date(e.created_at).toLocaleString()}</time><p className="preserve-lines">{e.description}</p>{e.changes && <AuditChanges changes={e.changes}/>}{e.requirement_id&&<button className="source-link" onClick={()=>onSelect(e.requirement_id!)}>View related requirement</button>}</li>)}</ol>{events.length<total&&<button disabled={busy} onClick={()=>void load(events.length)}>Load older events</button>}</>}</section>;
}

function AuditChanges({changes}:{changes:{before:Record<string,unknown>|null;after:Record<string,unknown>}}) {
  return <span className="audit-changes">{Object.entries(changes.after).filter(([key,value])=>changes.before?.[key]!==value).map(([key,value])=><span key={key}><strong>{key.replaceAll('_',' ')}:</strong> {String(changes.before?.[key] ?? 'not set')} → {String(value ?? 'not set')}<br/></span>)}</span>;
}
