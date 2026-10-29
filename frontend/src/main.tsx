import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import './tailwind.css';
import { WorkspaceHub } from './components/WorkspaceHub';
import { Landing } from './components/Landing';
import { parseWorkspaceRoute, useWorkspaceLocation, workspaceHref } from './workspaceRoutes';
import { DocumentWorkflow } from './DocumentWorkflow';
import { createSampleWorkflow, SampleWorkflowError, SAMPLE_SUPPLIER } from './sampleWorkflow';


type Workspace = { id: string; title: string; supplier_name: string; revision: number };

function App() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [token, setToken] = useState('');
  const [title, setTitle] = useState('');
  const [supplier, setSupplier] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('Connecting…');
  const [sampleProgress, setSampleProgress] = useState('');
  const location = useWorkspaceLocation();
  const route = parseWorkspaceRoute(location);
  const selectedWorkspace = route ? workspaces.find(w=>w.id===route.workspaceId) : undefined;
  const workspaceMode = location.startsWith('#/workspaces/');

  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await fetch(`/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
    });
    if (!response.ok) {
      const body=await response.json().catch(()=>null);
      throw new Error(response.status === 401 ? 'Enter the application access token and reconnect.' : body?.error?.message || `Request failed (${response.status}).`);
    }
    return response.json();
  }, [token]);

  const connect = useCallback(async (signal?: AbortSignal) => {
    setError(''); setBusy(true);
    try {
      const readiness = await request('/ready', { signal });
      if (signal?.aborted) return;
      setStatus(readiness.inference === 'not_configured' ? 'Database ready · AI not configured' : 'Database ready · AI configured, not verified');
      const rows = await request('/workspaces', { signal });
      if (!signal?.aborted) setWorkspaces(rows);
    } catch (e) { if (!signal?.aborted) { setError(e instanceof Error ? e.message : 'Connection failed'); setStatus('Connection needs attention'); } }
    finally { if (!signal?.aborted) setBusy(false); }
  }, [request]);

  useEffect(() => { const controller = new AbortController(); const timer = setTimeout(() => void connect(controller.signal), 250); return () => { clearTimeout(timer); controller.abort(); }; }, [connect]);

  useEffect(() => { if (location.startsWith('#/workspaces')) window.scrollTo(0,0); }, [location]);

  async function create(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      const created: Workspace = await request('/workspaces', { method: 'POST', body: JSON.stringify({ title, supplier_name: supplier }) });
      setWorkspaces(previous => [created, ...previous]); setTitle(''); setSupplier('');
      window.location.hash = workspaceHref(created.id, 'amendments');
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not create workspace'); }
    finally { setBusy(false); }
  }

  async function createSample() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const workspace = await createSampleWorkflow(request, setSampleProgress);
      setWorkspaces(rows => [workspace, ...rows]);
      window.location.hash = workspaceHref(workspace.id, 'requirements');
    } catch (e) {
      if (e instanceof SampleWorkflowError && e.workspace) {
        const workspace = e.workspace;
        setWorkspaces(rows => [workspace, ...rows.filter(w => w.id !== workspace.id)]);
        setError(`${e.message} Partial sample workspace was preserved; open it to inspect or delete it.`);
      } else setError(e instanceof Error ? e.message : 'Sample setup failed.');
    } finally { setBusy(false); setSampleProgress(''); }
  }

  async function renameWorkspace(workspace: Pick<Workspace, "id"|"title"|"supplier_name">, nextTitle: string) {
    const updated: Workspace = await request(`/workspaces/${workspace.id}/rename`, {method:'POST', body:JSON.stringify({title:nextTitle,expected_title:workspace.title})});
    setWorkspaces(rows=>rows.map(w=>w.id===updated.id?updated:w));
  }
  async function deleteWorkspace(workspace: Pick<Workspace, "id"|"title"|"supplier_name">) {
    await request(`/workspaces/${workspace.id}/delete`, {method:'POST', body:JSON.stringify({confirm:true,expected_title:workspace.title})});
    setWorkspaces(rows=>rows.filter(w=>w.id!==workspace.id));
  }

  return <main className="tr-app">
    {!workspaceMode && location!=="#/workspaces" && <Landing />}
    <div className="app-connection" hidden={workspaceMode && !!selectedWorkspace}>
    <div className="status" role="status">{status}</div>
    <details><summary>Application access</summary><label>Access token<input type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} placeholder="Only if configured on your server" /></label><button disabled={busy} onClick={() => void connect()}>Reconnect</button><small>This is the application token, never your Nebius API key. It stays in memory.</small></details>
    {error && <p className="error" role="alert">{error}</p>}
    {!workspaceMode && <div className="sample-start"><strong>Try the complete sample workflow</strong><p>No provider key needed. Creates a separate synthetic workspace with real PDF uploads, a RAM amendment, preserved review history and an unresolved 32 GB versus 16 GB finding. All scripted reviews are marked as samples.</p><button className="secondary" disabled={busy || status==='Connecting…'} onClick={()=>void createSample()}>{sampleProgress || 'Create sample workspace'}</button>{sampleProgress && <p role="status">{sampleProgress}</p>}<p className="muted">Your own tenders use the real Nemotron integration. A missing provider key never triggers simulated AI output.</p></div>}
    </div>
    {!workspaceMode && <WorkspaceHub onRename={renameWorkspace} onDelete={deleteWorkspace} workspaces={workspaces} busy={busy || status==='Connecting…'} createForm={<form onSubmit={create}><label>Tender title<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="University laptop procurement"/></label><label>Supplier legal name<input required maxLength={200} value={supplier} onChange={e => setSupplier(e.target.value)} placeholder="Your company name"/></label><button disabled={busy || !title.trim() || !supplier.trim()}>{busy ? 'Working…' : 'Create workspace →'}</button></form>}/>}
    {workspaceMode && !selectedWorkspace && <section className="panel"><h2>{busy || status==='Connecting…' ? 'Loading workspace…' : 'Workspace unavailable'}</h2><p>{route ? 'Use application access above to reconnect, or choose a workspace you can access.' : 'This workspace page does not exist.'}</p><a href="#workspace-start">Back to workspaces</a></section>}
    {selectedWorkspace && <DocumentWorkflow key={selectedWorkspace.id} workspace={selectedWorkspace} page={route!.page} token={token} isSample={selectedWorkspace.supplier_name===SAMPLE_SUPPLIER} />}
    <footer>Built for source-linked evidence review. No compliance or eligibility guarantees.</footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);
