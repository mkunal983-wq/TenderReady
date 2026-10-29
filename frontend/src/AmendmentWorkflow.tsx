import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
const PdfSource = lazy(() => import('./PdfSource'));
type Request = (path: string, init?: RequestInit) => Promise<Response>;
type Ref = { requirement_id?: string; stable_id?: string; clause_id?: string; version?: number; text: string; document_id: string; filename: string; page: number | null };
type EvidenceRef = { fact_id: string; quote: string; page: number; document_version_id: string; filename?: string };
type Assessment = { id: string; status: string; label: string; review_state: string; stale: boolean; checks: { field?: string; outcome?: string; rationale?: string; execution?: string; sources?: EvidenceRef[] }[] };
type Impact = { reason: string; approval_ids: string[]; old_assessment: Assessment; new_assessment: Assessment | null };
type Change = { id?: string; classification: string; old_id: string | null; candidate_id: string | null; match_method: string; reason: string; before: Ref | null; after: Ref | null; impacts?: Impact[] };
type Snapshot = { id: string; sequence: number; document_id: string; mode: string; requirements: (Ref & { assessment: Assessment | null })[]; changes: Change[] };
type Preview = { fingerprint: string; changes: Change[]; warnings: string[] };
type Mapping = { candidate_id: string; previous_requirement_id: string };
type Removal = { requirement_id: string; page: number; quote: string };
const fieldNames: Record<string,string> = {ram_gb:'RAM',storage_gb:'Storage',model:'Model identity',product_scope:'Product scope',coverage:'Coverage',validity:'Validity',bidder_identity:'Bidder identity'};

export function AmendmentWorkflow({ prefix, documentId, request, onChanged, revision }: { prefix: string; documentId: string; request: Request; onChanged: () => void; revision: number | string }) {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [candidates, setCandidates] = useState<{id:string;text:string}[]>([]);
  const [reviewer,setReviewer]=useState('');
  const [mode,setMode]=useState('delta');
  const [confirmed,setConfirmed]=useState(false);
  const [preview,setPreview]=useState<Preview|null>(null);
  const [mappings,setMappings]=useState<Mapping[]>([]);
  const [removals,setRemovals]=useState<Removal[]>([]);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [source,setSource]=useState('');
  const blob=useRef(''); const controller=useRef<AbortController|null>(null);
  const latest=snapshots[0];
  const published=snapshots.some(s=>s.document_id===documentId);
  const base=`${prefix}/documents/${documentId}`;
  const load=useCallback(async(signal?:AbortSignal)=>{
    const [history,rows]=await Promise.all([request(`${prefix}/snapshots`,{signal}).then(r=>r.json()),request(`${base}/requirements`,{signal}).then(r=>r.json())]);
    if (!signal?.aborted) {setSnapshots(history);setCandidates(rows);}
  },[request,prefix,base]);
  useEffect(()=>{
    const abort=new AbortController(); void load(abort.signal).catch(e=>{if(!abort.signal.aborted)setError(e.message);});
    setPreview(null);setConfirmed(false);
    return()=>abort.abort();
  },[load,revision]);
  useEffect(()=>()=>{controller.current?.abort();if(blob.current)URL.revokeObjectURL(blob.current);},[]);
  const payload=()=>({reviewer,mode,coverage_confirmed:confirmed,mappings,removals});
  async function action(operation:string){
    setBusy(true);setError('');setMessage('');
    try{
      const body=operation==='extract-labelled'?undefined:JSON.stringify(operation==='baseline'?{reviewer,coverage_confirmed:confirmed}:{...payload(),...(operation==='apply-amendment'?{fingerprint:preview?.fingerprint}:{})});
      const result=await(await request(`${base}/${operation}`,{method:'POST',headers:{'Content-Type':'application/json'},body})).json();
      if(operation==='compare')setPreview(result);
      else {setPreview(null);await load();onChanged();setMessage(operation==='extract-labelled'?`${result.count} clauses extracted with the deterministic labelled parser. Review completeness.`:operation==='baseline'?'Original tender baseline preserved.':'Amendment applied. Changed checks reassessed; unaffected approvals preserved.');}
    }catch(e){setError(e instanceof Error?e.message:'Amendment operation failed');}
    finally{setBusy(false);}
  }
  async function view(ref:Ref){
    controller.current?.abort();const abort=new AbortController();controller.current=abort;
    try{const response=await request(`${prefix}/documents/${ref.document_id}/file`,{signal:abort.signal});const data=await response.blob();if(abort.signal.aborted)return;
      if(blob.current)URL.revokeObjectURL(blob.current);blob.current=URL.createObjectURL(data);setSource(`${blob.current}#page=${ref.page||1}`);
    }catch(e){if(!abort.signal.aborted)setError(e instanceof Error?e.message:'Source unavailable');}
  }
  function reference(ref:Ref|null,label:string){return <div><h5>{label}</h5>{ref?<><p className="preserve-lines">{ref.text}</p><button className="source-link" onClick={()=>void view(ref)}>{ref.filename}{ref.page?` · page ${ref.page}`:' · whole document'}</button></>:<p>Not present in this version.</p>}</div>;}
  function assessment(a:Assessment|null,label:string){return <div><h5>{label}</h5>{a?<><strong>{a.label}</strong><p>Review: {a.review_state.replaceAll('_',' ')}{a.stale?' · Requires reassessment':''}</p>
    {a.checks.filter(c=>c.field).map((c,i)=><div key={i}><p><strong>{fieldNames[c.field!]||c.field}: {c.outcome}</strong>{c.execution?` · ${c.execution==='reused'?'Prior result reused':'Check executed'}`:''}</p><p>{c.rationale}</p>{c.sources?.map(s=><div key={s.fact_id}><blockquote>{s.quote}</blockquote><button className="source-link" onClick={()=>void view({document_id:s.document_version_id,filename:s.filename||'Evidence PDF',page:s.page,text:s.quote})}>Evidence page {s.page}</button></div>)}</div>)}</>:<p>No replacement assessment for a removed requirement.</p>}</div>;}
  function changes(rows:Change[]){return rows.map((c,i)=><article className={`assessment amendment-${c.classification.toLowerCase()}`} key={c.id||i}>
    <h4>{c.classification} · {c.after?.clause_id||c.before?.clause_id||'Requirement'}</h4><p>{c.reason}</p><small>Mapping: {c.match_method.replaceAll('_',' ')}</small>
    <div className="amendment-comparison">{reference(c.before,'Previous requirement')}{reference(c.after,'Current requirement / amendment source')}</div>
    {c.impacts?.map(impact=><details key={impact.old_assessment.id} open><summary>{impact.approval_ids.length} prior approval(s) affected · Why reassessment was required</summary><p className="preserve-lines">{impact.reason}</p><div className="amendment-comparison">{assessment(impact.old_assessment,'Previous evidence assessment')}{assessment(impact.new_assessment,'Reassessed evidence')}</div></details>)}
    {c.classification==='Unchanged'&&<p>No checks rerun for this requirement. Existing assessment and reviewer history retained.</p>}
  </article>);}
  return <section className="amendment-workflow" aria-label="Amendment reassessment"><h3>Amendment reassessment</h3>
    <p>Preserve the original tender, compare revisions, and rerun only the checks whose assumptions changed.</p>
    {!published&&<>
      <button className="secondary" disabled={busy} onClick={()=>void action('extract-labelled')}>Extract labelled clauses (no AI)</button><p className="muted">For explicit “Requirement ID:” blocks with labelled fields. Use the existing Nemotron extraction button for prose; uncertain interpretations need review.</p>
      <label>Amendment reviewer<input value={reviewer} maxLength={200} onChange={e=>setReviewer(e.target.value)}/></label>
      {latest&&<><label>Revision scope<select value={mode} onChange={e=>{setMode(e.target.value);setPreview(null);setConfirmed(false);}}><option value="delta">Partial amendment / corrigendum — preserve omitted requirements</option><option value="full">Complete revised tender — omissions are removals</option></select></label>
      <details><summary>Resolve clause mappings and explicit removals</summary><p>Stable clause IDs and unique, source-backed capacity changes match automatically. Ambiguous or renamed clauses need an explicit predecessor mapping.</p>
        {candidates.map(c=><label key={c.id}>{c.text.slice(0,100)}<select value={mappings.find(m=>m.candidate_id===c.id)?.previous_requirement_id||''} onChange={e=>{setMappings(old=>[...old.filter(m=>m.candidate_id!==c.id),...(e.target.value?[{candidate_id:c.id,previous_requirement_id:e.target.value}]:[])]);setPreview(null);}}><option value="">Automatic ID / exact-text matching</option>{latest.requirements.map(r=><option key={r.requirement_id} value={r.requirement_id}>{r.clause_id||r.text.slice(0,80)}</option>)}</select></label>)}
        {removals.map((r,i)=><fieldset key={i}><legend>Explicit removal {i+1}</legend><label>Previous requirement<select value={r.requirement_id} onChange={e=>{setRemovals(old=>old.map((v,n)=>n===i?{...v,requirement_id:e.target.value}:v));setPreview(null);}}><option value="">Choose requirement</option>{latest.requirements.map(v=><option key={v.requirement_id} value={v.requirement_id}>{v.clause_id||v.text}</option>)}</select></label><label>Amendment page<input type="number" min={1} value={r.page} onChange={e=>{setRemovals(old=>old.map((v,n)=>n===i?{...v,page:Number(e.target.value)}:v));setPreview(null);}}/></label><label>Exact removal quotation<textarea value={r.quote} onChange={e=>{setRemovals(old=>old.map((v,n)=>n===i?{...v,quote:e.target.value}:v));setPreview(null);}}/></label><button className="secondary" onClick={()=>{setRemovals(old=>old.filter((_,n)=>n!==i));setPreview(null);}}>Remove entry</button></fieldset>)}
        <button className="secondary" onClick={()=>setRemovals(old=>[...old,{requirement_id:'',page:1,quote:''}])}>Add explicit removal</button>
      </details></>}
      <label className="checkbox-label"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>I reviewed requirement completeness, scope, mappings, and any removals against the uploaded source.</label>
      {!latest?<button disabled={busy||!confirmed||!reviewer.trim()||!candidates.length} onClick={()=>void action('baseline')}>Preserve original tender baseline</button>:<button disabled={busy||!reviewer.trim()} onClick={()=>void action('compare')}>Compare against active tender</button>}
      {preview&&<><h4>Change preview</h4>{preview.warnings.map(w=><p className="warning" key={w}>{w}</p>)}{changes(preview.changes)}<button disabled={busy||!confirmed||!reviewer.trim()} onClick={()=>void action('apply-amendment')}>Apply amendment and reassess affected checks</button></>}
    </>}
    {message&&<p role="status">{message}</p>}{error&&<p role="alert" className="error">{error}</p>}
    {latest&&<><h4>Active tender snapshot {latest.sequence}</h4><ul>{latest.requirements.map(r=><li key={r.requirement_id}><strong>{r.clause_id||r.text}</strong><span>Version {r.version} · {r.assessment?.label||'Not assessed'} · {r.assessment?.review_state.replaceAll('_',' ')||'Awaiting review'}{r.assessment?.stale?' · Requires reassessment':''}</span><small>Stable ID: {r.stable_id}</small></li>)}</ul>{changes(latest.changes)}
      <details><summary>Preserved snapshot history ({snapshots.length})</summary>{snapshots.map(s=><div key={s.id}><h5>Snapshot {s.sequence} · {s.mode}</h5>{s.requirements.map(r=><p key={r.requirement_id}>{r.clause_id||r.text} · requirement version {r.version} · {r.assessment?.review_state||'Not reviewed'}</p>)}</div>)}</details></>}
    {source&&<div><button className="secondary" onClick={()=>setSource('')}>Close amendment source</button><Suspense fallback={<p>Loading source…</p>}><PdfSource key={source} url={source}/></Suspense></div>}
  </section>;
}
