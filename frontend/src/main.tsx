import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { plainSystemText } from './plainLanguage';
import './style.css';
import './tailwind.css';
import { WorkspaceHub } from './components/WorkspaceHub';
import { Landing } from './components/Landing';
import { parseWorkspaceRoute, useWorkspaceLocation, workspaceHref } from './workspaceRoutes';
import { DocumentWorkflow } from './DocumentWorkflow';
import { createSampleWorkflow, SampleWorkflowError, SAMPLE_SUPPLIER } from './sampleWorkflow';
import './glass-theme.css';


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
      throw new Error(response.status === 401 ? 'Enter your app access key, then reconnect.' : plainSystemText(body?.error?.message || `Request failed (${response.status}).`));
    }
    return response.json();
  }, [token]);

  const connect = useCallback(async (signal?: AbortSignal) => {
    setError(''); setBusy(true);
    try {
      const readiness = await request('/ready', { signal });
      if (signal?.aborted) return;
      setStatus(readiness.inference === 'not_configured' ? 'App ready · AI setup needed' : 'App ready · AI key set; connection not checked');
      const rows = await request('/workspaces', { signal });
      if (!signal?.aborted) setWorkspaces(rows);
    } catch (e) { if (!signal?.aborted) { setError(e instanceof Error ? e.message : 'Connection failed'); setStatus('Could not connect'); } }
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
        setError(`${e.message} The sample workspace was saved, but setup stopped early. Open it to check what was saved, or delete it.`);
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
    <details><summary>App access</summary><label>App access key<input type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} placeholder="Only if your app asks for an access key" /></label><button disabled={busy} onClick={() => void connect()}>Reconnect</button><small>Use your app access key here, not your Nebius API key. This key is kept only while the app is open.</small></details>
    {error && <p className="error" role="alert">{error}</p>}
    {!workspaceMode && <div className="sample-start"><strong>Try a sample tender</strong><p>No AI key needed. This creates a separate demo with sample PDFs. The tender changes from 16 GB to 32 GB RAM, so the old 16 GB document no longer meets it. Reviews are saved and clearly marked as sample reviews.</p><button className="secondary" disabled={busy || status==='Connecting…'} onClick={()=>void createSample()}>{sampleProgress || 'Create sample workspace'}</button>{sampleProgress && <p role="status">{sampleProgress}</p>}<p className="muted">Your own tenders use Nemotron AI. If the AI key is missing, extraction stops; sample results are never shown as real AI results.</p></div>}
    </div>
    {!workspaceMode && <WorkspaceHub onRename={renameWorkspace} onDelete={deleteWorkspace} workspaces={workspaces} busy={busy || status==='Connecting…'} createForm={<form onSubmit={create}><label>Tender title<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="Laptops for a university"/></label><label>Registered company name<input required maxLength={200} value={supplier} onChange={e => setSupplier(e.target.value)} placeholder="Your company name"/></label><button disabled={busy || !title.trim() || !supplier.trim()}>{busy ? 'Working…' : 'Create workspace →'}</button></form>}/>}
    {workspaceMode && !selectedWorkspace && <section className="panel"><h2>{busy || status==='Connecting…' ? 'Loading workspace…' : 'Workspace unavailable'}</h2><p>{route ? 'Use App access above to reconnect, or choose another workspace.' : 'This workspace page does not exist.'}</p><a href="#workspace-start">Back to workspaces</a></section>}
    {selectedWorkspace && <DocumentWorkflow key={selectedWorkspace.id} workspace={selectedWorkspace} page={route!.page} initialStatus={route!.status} token={token} isSample={selectedWorkspace.supplier_name===SAMPLE_SUPPLIER} />}
    <footer>Check evidence against the original documents. A completed review does not guarantee that your bid qualifies or wins.</footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);
