import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { DocumentWorkflow } from './DocumentWorkflow';
const workspace={id:'w',title:'Upload navigation regression'};
vi.mock('./PdfSource',()=>({default:({url}:{url:string})=><div data-testid="pdf-source">{url}</div>}));
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
it('clears a tender selection when leaving the upload page so an empty picker cannot submit an invisible file',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>new Response('[]',{headers:{'Content-Type':'application/json'}})));
  const {rerender}=render(<DocumentWorkflow workspace={workspace} token="" page="amendments"/>);
  const upload=screen.getByRole('button',{name:'Upload tender PDF'});
  expect(upload).toBeDisabled();
  await userEvent.upload(screen.getByLabelText('Tender PDF'),new File(['%PDF-1.7'],'fixture.pdf',{type:'application/pdf'}));
  expect(upload).toBeEnabled();
  rerender(<DocumentWorkflow workspace={workspace} token="" page="evidence"/>);
  rerender(<DocumentWorkflow workspace={workspace} token="" page="amendments"/>);
  expect(screen.getByRole('button',{name:'Upload tender PDF'})).toBeDisabled();
});

it('shows preserved configuration context with its own protected source page',async()=>{
  const sourceContext={text:'Laptop (Configuration B)',page:2,source_document_id:'original',source_url:'/workspaces/w/documents/original/file#page=2'};
  const row={source_document_id:'original',source_filename:'tender.pdf',id:'ram',requirement_id:'RAM-B',text:'RAM: at least 4 GB',category:'numeric_threshold',obligation:'unclear',page:3,excerpt:'RAM: at least 4 GB',confidence:'high',review_status:'awaiting_review',review_reasons:[],numeric_conditions:[],date_conditions:[],source_context:[sourceContext]};
  const doc={kind:'tender',id:'original',filename:'tender.pdf',version:1,page_count:3,analysis:{status:'succeeded',warnings:[],error_message:null,pages_completed:3,model:'model'}};
  const fetcher=vi.fn(async(path:string)=>path.endsWith('/file')?new Response('%PDF') : new Response(JSON.stringify(path.endsWith('/documents')?[doc]:path.endsWith('/requirements')?[row]:[]),{headers:{'Content-Type':'application/json'}}));
  vi.stubGlobal('fetch',fetcher);
  Object.defineProperty(URL,'createObjectURL',{value:vi.fn(()=> 'blob:context'),configurable:true});
  Object.defineProperty(URL,'revokeObjectURL',{value:vi.fn(),configurable:true});
  render(<DocumentWorkflow workspace={workspace} token="test-token" page="amendments"/>);
  expect(await screen.findByText('Laptop (Configuration B)')).toBeVisible();
  expect(screen.getByRole('button',{name:'Source: tender.pdf · page 3'})).toBeVisible();
  await userEvent.click(screen.getByRole('button',{name:'Heading · page 2'}));
  await waitFor(()=>expect(screen.getByTestId('pdf-source')).toHaveTextContent('blob:context#page=2'));
  expect(fetcher).toHaveBeenCalledWith('/api/workspaces/w/documents/original/file',expect.objectContaining({headers:{Authorization:'Bearer test-token'}}));
});

const cachedDoc = { published: false, kind: 'tender', id: 'original', filename: 'tender.pdf', version: 1, page_count: 4, analysis: { status: 'succeeded', warnings: [], error_message: null, pages_completed: 4, model: 'model' } };
const cachedRow = { source_document_id: 'original', source_filename: 'tender.pdf', id: 'quantity', requirement_id: 'QUANTITY', text: 'Anticipated quantity is 80 laptops.', category: 'technical', obligation: 'unclear', page: 2, excerpt: 'Anticipated quantity is 80 laptops.', confidence: 'high', review_status: 'awaiting_review', review_reasons: [], numeric_conditions: [], date_conditions: [] };
const jsonResponse = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });

it('reconciles only cached extraction, reloads persisted rows and preserves a source-linked revision history', async () => {
  const summary = { revision: 1, added: 1, modified: 1, reference: 1, unchanged: 3, provider_calls: 0, created_at: '2026-10-29T12:00:00Z' };
  const originalWarning = 'Original extraction could not reliably classify the quantity.';
  const updated = { ...cachedDoc, analysis: { ...cachedDoc.analysis, warnings: [originalWarning], reconciliation: summary } };
  const corrected = { ...cachedRow, id: 'quantity-revision-1', text: 'Corrected quantity interpretation', provenance: 'deterministic_source_reconciliation', quantity_conditions: [{ kind: 'anticipated', value_text: '80', unit_text: 'laptops', quote: cachedRow.excerpt, page: 2, source_document_id: 'original' }] };
  const changes = [{ previous_requirement_id: cachedRow.id, requirement_id: corrected.id, action: 'modified', page: 2, text: corrected.text, reason: 'Anticipated quantity is a schedule, not a minimum threshold.', source_url: '/workspaces/w/documents/original/file#page=2' }];
  let reconciled = false;
  let finish: ((value: Response) => void) | undefined;
  const fetcher = vi.fn(async (path: string) => {
    if (path.endsWith('/reconcile')) return new Promise<Response>(resolve => { finish = resolve; });
    if (path.endsWith('/reconciliations')) return jsonResponse([{ ...summary, changes }]);
    if (path.endsWith('/file')) return new Response('%PDF');
    if (path.endsWith('/documents')) return jsonResponse([reconciled ? updated : cachedDoc]);
    if (path.endsWith('/requirements')) return jsonResponse([reconciled ? corrected : cachedRow]);
    return jsonResponse([]);
  });
  vi.stubGlobal('fetch', fetcher);
  Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:revision'), configurable: true });
  Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true });
  render(<DocumentWorkflow workspace={workspace} token="test-token" page="amendments"/>);
  const reconcile = await screen.findByRole('button', { name: 'Update saved results' });
  await userEvent.click(reconcile);
  expect(screen.getByRole('button', { name: 'Updating saved results…' })).toBeDisabled();
  expect(screen.getByLabelText('Document version')).toBeDisabled();
  expect(fetcher).toHaveBeenCalledWith('/api/workspaces/w/documents/original/reconcile', expect.objectContaining({ method: 'POST', headers: { Authorization: 'Bearer test-token' } }));
  await act(async () => { reconciled = true; finish?.(jsonResponse(updated)); });
  expect(await screen.findByText(corrected.text)).toBeVisible();
  expect(screen.getByRole('status', { name: 'Saved results update' })).toHaveTextContent('1 added · 1 corrected · 1 reference or duplicate items · 3 unchanged · 0 new AI calls');
  expect(screen.getByText('Expected quantity: 80 laptops')).toBeVisible();
  expect(screen.getByText('Updated using rules and the original PDF · needs your review')).toBeVisible();
  expect(screen.queryByText('AI confidence: high')).not.toBeInTheDocument();
  expect(screen.getByText(originalWarning)).not.toBeVisible();
  await userEvent.click(screen.getByText('Original AI notes (before updates)'));
  expect(screen.getByText(originalWarning)).toBeVisible();
  expect(screen.getByText(/See the corrected results below/)).toBeVisible();
  expect(fetcher.mock.calls.some(([path]) => path.endsWith('/analyze'))).toBe(false);
  expect(fetcher.mock.calls.some(([path]) => path.endsWith('/reconciliations'))).toBe(false);
  await userEvent.click(screen.getByText('Previous result updates'));
  await userEvent.click(screen.getByRole('button', { name: 'Load previous results' }));
  await userEvent.click(await screen.findByText('Results update 1 · 1 added · 1 corrected · 1 reference or duplicate items'));
  expect(screen.getByText(changes[0].reason)).toBeVisible();
  expect(screen.getByText('Earlier result: quantity')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Original PDF · page 2' }));
  await waitFor(() => expect(screen.getByTestId('pdf-source')).toHaveTextContent('blob:revision#page=2'));
  expect(fetcher).toHaveBeenCalledWith('/api/workspaces/w/documents/original/file', expect.objectContaining({ headers: { Authorization: 'Bearer test-token' } }));
});

it('shows reconciliation failures without claiming a saved correction or removing existing requirements', async () => {
  const fetcher = vi.fn(async (path: string) => {
    if (path.endsWith('/reconcile')) return new Response(JSON.stringify({ error: { message: 'The document was already published. Preserve its existing review history.' } }), { status: 409 });
    if (path.endsWith('/documents')) return jsonResponse([cachedDoc]);
    if (path.endsWith('/requirements')) return jsonResponse([cachedRow]);
    return jsonResponse([]);
  });
  vi.stubGlobal('fetch', fetcher);
  render(<DocumentWorkflow workspace={workspace} token="" page="amendments"/>);
  await userEvent.click(await screen.findByRole('button', { name: 'Update saved results' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('The document was already published. Preserve its existing review history.');
  expect(screen.getByRole('button', { name: 'Update saved results' })).toBeEnabled();
  expect(screen.getAllByText(cachedRow.text).length).toBeGreaterThan(0);
  expect(screen.queryByRole('status', { name: 'Saved results update' })).not.toBeInTheDocument();
});

it('does not offer reconciliation for a published document', async () => {
  vi.stubGlobal('fetch', vi.fn(async (path: string) => jsonResponse(path.endsWith('/documents') ? [{ ...cachedDoc, published: true }] : path.endsWith('/requirements') ? [cachedRow] : [])));
  render(<DocumentWorkflow workspace={workspace} token="" page="amendments"/>);
  await screen.findByRole('button', { name: 'Tender read' });
  expect(screen.queryByRole('button', { name: 'Update saved results' })).not.toBeInTheDocument();
});
