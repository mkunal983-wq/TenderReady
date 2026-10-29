import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { statusLabel, reviewStateLabel, plainSystemText } from './plainLanguage';
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
const changeLabels: Record<string,string> = {Added:'Added',Modified:'Changed',Removed:'Removed',Unchanged:'No change'};
const matchLabels: Record<string,string> = {reviewer_mapping:'your selection',explicit_clause_id:'requirement ID',exact_normalized_text:'matching text',source_grounded_threshold:'clear change in the number or amount',explicit_removal:'removal instruction in the PDF',full_document_omission:'missing from the full new tender',carried_forward:'kept from the earlier tender',unmatched:'no earlier requirement found'};
const checkLabels: Record<string,string> = {pass:'Matches',conflict:'Does not match',review:'Needs review',missing:'Missing',outdated:'Out of date'};
const fieldNames: Record<string,string> = {ram_gb:'RAM',storage_gb:'Storage',model:'Product model',product_scope:'Correct product',coverage:'All requirement details checked',validity:'Valid dates',bidder_identity:'Supplier name'};

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
      else {setPreview(null);await load();onChanged();setMessage(operation==='extract-labelled'?`${result.count} requirements found using fixed rules, without AI. Check that nothing is missing.`:operation==='baseline'?'Starting tender version saved.':'Tender update applied. Affected evidence was checked again. Other approvals were kept.');}
    }catch(e){setError(e instanceof Error?e.message:'Could not update the tender. Please try again.');}
    finally{setBusy(false);}
  }
  async function view(ref:Ref){
    controller.current?.abort();const abort=new AbortController();controller.current=abort;
    try{const response=await request(`${prefix}/documents/${ref.document_id}/file`,{signal:abort.signal});const data=await response.blob();if(abort.signal.aborted)return;
      if(blob.current)URL.revokeObjectURL(blob.current);blob.current=URL.createObjectURL(data);setSource(`${blob.current}#page=${ref.page||1}`);
    }catch(e){if(!abort.signal.aborted)setError(e instanceof Error?e.message:'Could not open the original PDF.');}
  }
  function reference(ref:Ref|null,label:string){return <div><h5>{label}</h5>{ref?<><p className="preserve-lines">{ref.text}</p><button className="source-link" onClick={()=>void view(ref)}>{ref.filename}{ref.page?` · page ${ref.page}`:' · whole document'}</button></>:<p>Not present in this version.</p>}</div>;}
  function assessment(a:Assessment|null,label:string){return <div><h5>{label}</h5>{a?<><strong>{statusLabel(a.status)}</strong><p>Review: {reviewStateLabel(a.review_state)}{a.stale?' · Needs another check':''}</p>
    {a.checks.filter(c=>c.field).map((c,i)=><div key={i}><p><strong>{fieldNames[c.field!]||c.field}: {checkLabels[c.outcome || ''] || c.outcome}</strong>{c.execution?` · ${c.execution==='reused'?'Earlier result kept':'Checked again'}`:''}</p><p>{plainSystemText(c.rationale || '')}</p>{c.sources?.map(s=><div key={s.fact_id}><blockquote>{s.quote}</blockquote><button className="source-link" onClick={()=>void view({document_id:s.document_version_id,filename:s.filename||'Evidence PDF',page:s.page,text:s.quote})}>Evidence page {s.page}</button></div>)}</div>)}</>:<p>No new evidence check is needed for a removed requirement.</p>}</div>;}
  function changes(rows:Change[]){return rows.map((c,i)=><article className={`assessment amendment-${c.classification.toLowerCase()}`} key={c.id||i}>
    <h4>{changeLabels[c.classification] || c.classification} · {c.after?.clause_id||c.before?.clause_id||'Requirement'}</h4><p>{plainSystemText(c.reason)}</p><small>Matched by: {matchLabels[c.match_method] || c.match_method}</small>
    <div className="amendment-comparison">{reference(c.before,'Previous requirement')}{reference(c.after,'Updated requirement or removal instruction')}</div>
    {c.impacts?.map(impact=><details key={impact.old_assessment.id} open><summary>{impact.approval_ids.length} earlier approval(s) affected · Why another check was needed</summary><p className="preserve-lines">{impact.reason}</p><div className="amendment-comparison">{assessment(impact.old_assessment,'Previous evidence check')}{assessment(impact.new_assessment,'New evidence check')}</div></details>)}
    {c.classification==='Unchanged'&&<p>This requirement did not change. Its evidence checks, approvals and history were kept.</p>}
  </article>);}
  return <section className="amendment-workflow" aria-label="Check tender changes"><h3>Check tender changes</h3>
    <p>Keep the original tender, compare it with an update, and check only the affected evidence again.</p>
    {!published&&<>
      <button className="secondary" disabled={busy} onClick={()=>void action('extract-labelled')}>Read labelled requirements (no AI)</button><p className="muted">Use this for documents with “Requirement ID:” and clearly labelled fields. For normal tender text, use “Find requirements” below. Review any unclear results.</p>
      <label>Reviewer name<input value={reviewer} maxLength={200} onChange={e=>setReviewer(e.target.value)}/></label>
      {latest&&<><label>What does this upload contain?<select value={mode} onChange={e=>{setMode(e.target.value);setPreview(null);setConfirmed(false);}}><option value="delta">A partial update — keep requirements that are not mentioned</option><option value="full">A full new tender — remove requirements that are not included</option></select></label>
      <details><summary>Match requirements or mark removals</summary><p>The app matches clear requirement IDs and simple changes, such as 16 GB to 32 GB. If a match is unclear, choose the earlier requirement yourself.</p>
        {candidates.map(c=><label key={c.id}>{c.text.slice(0,100)}<select value={mappings.find(m=>m.candidate_id===c.id)?.previous_requirement_id||''} onChange={e=>{setMappings(old=>[...old.filter(m=>m.candidate_id!==c.id),...(e.target.value?[{candidate_id:c.id,previous_requirement_id:e.target.value}]:[])]);setPreview(null);}}><option value="">Let the app match this requirement</option>{latest.requirements.map(r=><option key={r.requirement_id} value={r.requirement_id}>{r.clause_id||r.text.slice(0,80)}</option>)}</select></label>)}
        {removals.map((r,i)=><fieldset key={i}><legend>Requirement to remove {i+1}</legend><label>Previous requirement<select value={r.requirement_id} onChange={e=>{setRemovals(old=>old.map((v,n)=>n===i?{...v,requirement_id:e.target.value}:v));setPreview(null);}}><option value="">Choose requirement</option>{latest.requirements.map(v=><option key={v.requirement_id} value={v.requirement_id}>{v.clause_id||v.text}</option>)}</select></label><label>Page showing the removal<input type="number" min={1} value={r.page} onChange={e=>{setRemovals(old=>old.map((v,n)=>n===i?{...v,page:Number(e.target.value)}:v));setPreview(null);}}/></label><label>Copy the exact removal instruction from the PDF<textarea value={r.quote} onChange={e=>{setRemovals(old=>old.map((v,n)=>n===i?{...v,quote:e.target.value}:v));setPreview(null);}}/></label><button className="secondary" onClick={()=>{setRemovals(old=>old.filter((_,n)=>n!==i));setPreview(null);}}>Remove entry</button></fieldset>)}
        <button className="secondary" onClick={()=>setRemovals(old=>[...old,{requirement_id:'',page:1,quote:''}])}>Add a requirement to remove</button>
      </details></>}
      <label className="checkbox-label"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>I checked the PDF for missing requirements, correct matches, what each requirement applies to, and any removals.</label>
      {!latest?<button disabled={busy||!confirmed||!reviewer.trim()||!candidates.length} onClick={()=>void action('baseline')}>Save starting tender version</button>:<button disabled={busy||!reviewer.trim()} onClick={()=>void action('compare')}>Compare with current tender</button>}
      {preview&&<><h4>Preview changes</h4>{preview.warnings.map(w=><p className="warning" key={w}>{w}</p>)}{changes(preview.changes)}<button disabled={busy||!confirmed||!reviewer.trim()} onClick={()=>void action('apply-amendment')}>Apply update and check affected evidence</button></>}
    </>}
    {message&&<p role="status">{message}</p>}{error&&<p role="alert" className="error">{plainSystemText(error)}</p>}
    {latest&&<><h4>Current tender version {latest.sequence}</h4><ul>{latest.requirements.map(r=><li key={r.requirement_id}><strong>{r.clause_id||r.text}</strong><span>Version {r.version} · {r.assessment ? statusLabel(r.assessment.status) : 'Not checked yet'} · {r.assessment ? reviewStateLabel(r.assessment.review_state) : 'Needs review'}{r.assessment?.stale?' · Needs another check':''}</span><small>Requirement ID: {r.stable_id}</small></li>)}</ul>{changes(latest.changes)}
      <details><summary>Saved tender history ({snapshots.length})</summary>{snapshots.map(s=><div key={s.id}><h5>Tender version {s.sequence} · {s.mode === 'baseline' ? 'Starting version' : s.mode === 'delta' ? 'Partial update' : 'Full new tender'}</h5>{s.requirements.map(r=><p key={r.requirement_id}>{r.clause_id||r.text} · requirement version {r.version} · {r.assessment ? reviewStateLabel(r.assessment.review_state) : 'Not reviewed'}</p>)}</div>)}</details></>}
    {source&&<div><button className="secondary" onClick={()=>setSource('')}>Close original PDF</button><Suspense fallback={<p>Opening PDF…</p>}><PdfSource key={source} url={source}/></Suspense></div>}
  </section>;
}
