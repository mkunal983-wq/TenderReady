import { useEffect, useRef, useState, type ReactNode, type FormEvent } from 'react';
import { IconArrowRight, IconBuilding, IconFolder, IconPlus, IconSearch, IconX, IconPencil, IconTrash } from '@tabler/icons-react';
import { workspaceHref } from '../workspaceRoutes';
import './workspace-hub.css';

export type HubWorkspace = { id: string; title: string; supplier_name: string };
export function WorkspaceHub({workspaces,busy,createForm,onRename,onDelete}:{workspaces:HubWorkspace[];busy:boolean;createForm:ReactNode;onRename:(workspace:HubWorkspace,title:string)=>Promise<void>;onDelete:(workspace:HubWorkspace)=>Promise<void>}) {
  const [action,setAction]=useState<{kind:'rename'|'delete';workspace:HubWorkspace}|null>(null);
  const [nextTitle,setNextTitle]=useState('');
  const [saving,setSaving]=useState(false);
  const [actionError,setActionError]=useState('');
  const modal=useRef<HTMLDialogElement>(null);
  useEffect(()=>{
    if(action)modal.current?.showModal();else modal.current?.close();
  },[action]);
  function openAction(kind:'rename'|'delete',workspace:HubWorkspace){setActionError('');setNextTitle(workspace.title);setAction({kind,workspace});}
  async function saveAction(event:FormEvent){
    event.preventDefault();if(!action || saving)return;setSaving(true);setActionError('');
    try{if(action.kind==='rename')await onRename(action.workspace,nextTitle.trim());else await onDelete(action.workspace);setAction(null);}
    catch(error){setActionError(error instanceof Error?error.message:'Could not save changes. Try again.');}
    finally{setSaving(false);}
  }
  const [search,setSearch]=useState('');
  const [sort,setSort]=useState('recent');
  const [creating,setCreating]=useState(false);
  const formPanel=useRef<HTMLDivElement>(null);
  useEffect(()=>{if(creating)formPanel.current?.querySelector('input')?.focus();},[creating]);
  const visible=workspaces.filter(w=>`${w.title} ${w.supplier_name}`.toLowerCase().includes(search.trim().toLowerCase()));
  if(sort==='name')visible.sort((a,b)=>a.title.localeCompare(b.title));
  return <section className="workspace-hub" id="workspace-start" aria-labelledby="workspace-hub-title">
    <div className="hub-topline"><a className="hub-brand" href="/"><span>T</span>TenderReady</a><span className="hub-location">Your tender workspaces</span></div>
    <div className="hub-heading"><div><p className="hub-eyebrow">YOUR WORKSPACES</p><h1 id="workspace-hub-title">All your bids, organized.</h1><p>Start a new bid workspace or open one you worked on before.</p></div><button className="hub-new" aria-expanded={creating} aria-controls="new-workspace-panel" onClick={()=>setCreating(v=>!v)}><IconPlus size={18}/>New workspace</button></div>
    {creating&&<div className="hub-create" id="new-workspace-panel" ref={formPanel}><div className="hub-create-heading"><div><h2>Start a new bid</h2><p>Give your tender a name and enter the company submitting it.</p></div><button className="hub-close" aria-label="Close new workspace form" onClick={()=>setCreating(false)}><IconX size={19}/></button></div>{createForm}</div>}
    <div className="hub-toolbar"><h2>All workspaces <span>{workspaces.length}</span></h2><div><label className="hub-search"><IconSearch size={17}/><input aria-label="Search workspaces" placeholder="Search by tender or company name…" value={search} onChange={e=>setSearch(e.target.value)}/></label><label className="hub-sort"><span className="sr-only">Sort workspaces</span><select value={sort} onChange={e=>setSort(e.target.value)}><option value="recent">Newest first</option><option value="name">Name A–Z</option></select></label></div></div>
    {busy&&!workspaces.length?<p className="hub-empty" role="status">Loading your workspaces…</p>:!workspaces.length?<div className="hub-empty"><IconFolder size={35}/><h3>Your first tender starts here</h3><p>Create a workspace to upload files and check proof documents.</p><button onClick={()=>setCreating(true)}>Create your first workspace <IconArrowRight size={16}/></button></div>:!visible.length?<div className="hub-empty"><IconSearch size={30}/><h3>No matching workspaces</h3><p>Try searching for a different tender title or company name.</p><button className="hub-clear" onClick={()=>setSearch('')}>Clear search</button></div>:<div className="hub-cards">{visible.map(w=><article className="hub-card" key={w.id}><div className="hub-card-top"><span className="hub-folder"><IconFolder size={24}/></span><span className="hub-card-label">TENDER WORKSPACE</span></div><div className="hub-card-menu"><button aria-label={`Rename workspace ${w.title}`} onClick={()=>openAction("rename",w)}><IconPencil size={14}/>Rename</button><button className="hub-delete" aria-label={`Delete workspace ${w.title}`} onClick={()=>openAction("delete",w)}><IconTrash size={14}/>Delete</button></div><h3>{w.title}</h3><p className="hub-supplier"><IconBuilding size={15}/>{w.supplier_name}</p><a href={workspaceHref(w.id,'readiness')} aria-label={`Open workspace ${w.title}`}>Open workspace <IconArrowRight size={17}/></a></article>)}</div>}
    <dialog ref={modal} className="hub-modal" aria-labelledby="workspace-action-title" onCancel={event=>{if(saving)event.preventDefault();else setAction(null);}}>
      {action&&<form onSubmit={saveAction}><h2 id="workspace-action-title">{action.kind==='rename'?'Rename workspace':'Delete workspace?'}</h2>
        {action.kind==='rename'?<label>Workspace name<input autoFocus required minLength={1} maxLength={200} value={nextTitle} onChange={event=>setNextTitle(event.target.value)} disabled={saving}/></label>:<><p>Delete <strong>{action.workspace.title}</strong>?</p><p>It will be removed from your active workspaces. Documents and review history are retained for recovery, and workspace access will be blocked.</p></>}
        {actionError&&<p role="alert" className="error">{actionError}</p>}
        <div className="hub-modal-actions"><button type="button" className="hub-cancel" disabled={saving} onClick={()=>setAction(null)}>Cancel</button><button className={action.kind==='delete'?'hub-confirm-delete':''} disabled={saving || (action.kind==='rename'&&!nextTitle.trim())}>{saving?'Saving…':action.kind==='rename'?'Save name':'Delete workspace'}</button></div>
      </form>}
    </dialog>
    {!!workspaces.length&&<p className="hub-results">Showing {visible.length} of {workspaces.length} workspaces</p>}
  </section>;
}
