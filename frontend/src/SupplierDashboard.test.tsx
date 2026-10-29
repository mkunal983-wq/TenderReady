import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SupplierDashboard, filterRequirements, type RequirementRow } from './SupplierDashboard';
import { RequirementVerification } from './EvidenceWorkflow';
const ram:RequirementRow={requirement_id:'ram',stable_id:'ram-stable',clause_id:'RAM-01',version:2,text:'RAM: at least 32 GB',filename:'corrigendum.pdf',document_id:'doc',page:1,category:'numeric_threshold',obligation:'mandatory',status:'conflicting',label:'Conflict detected',reasons:['16 GB is below the required 32 GB.'],unresolved:true,blocking:true,assessment:{id:'assessment',review_state:'awaiting_review',explanation:'RAM too low'}};
const ssd:RequirementRow={...ram,requirement_id:'ssd',stable_id:'ssd-stable',clause_id:'SSD-01',text:'Storage: at least 512 GB',category:'product_identity',status:'supported',label:'Supported by evidence',unresolved:false,blocking:false};
const data={review_complete:false,notice:'Evidence review only. No legal eligibility or award guarantee.',blockers:['Mandatory RAM requirement remains unresolved.'],counts:{supported:1,conflicting:1,missing:0,outdated:0,inconclusive:0},requirements:[ram,ssd],tasks:[],snapshot_sequence:2};
const response=(body:unknown)=>new Response(JSON.stringify(body),{headers:{'Content-Type':'application/json'}});
const noop=()=>{};
const assessment={id:'assessment',label:'Conflict detected',status:'conflicting',stale:false,review_state:'awaiting_review',explanation:'RAM too low',created_at:'2026-10-26T10:00:00+00:00',checks:[{method:'deterministic',field:'ram_gb',outcome:'conflict',rationale:'16 GB is below 32 GB.',sources:[{fact_id:'fact',filename:'datasheet.pdf',page:2,quote:'RAM: 16 GB',document_version_id:'evidence',raw_value:'16 GB'}]}],reviews:[],tasks:[]};
afterEach(()=>vi.restoreAllMocks());

describe('supplier dashboard',()=>{
  it('filters by both status and category without changing global counts or blockers',async()=>{
    const request=vi.fn(async()=>response(data));
    render(<SupplierDashboard prefix="/workspaces/w" request={request} revision="1" onChanged={noop}/>);
    expect(screen.getByRole('status')).toHaveTextContent('Loading current evidence');
    await screen.findByText('Mandatory RAM requirement remains unresolved.');
    await userEvent.selectOptions(screen.getByLabelText('Filter by evidence status'),'supported');
    expect(screen.queryByRole('button',{name:'Review requirement RAM-01'})).not.toBeInTheDocument();
    expect(screen.getByRole('button',{name:'Review requirement SSD-01'})).toBeInTheDocument();
    expect(screen.getByText('Action required')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Filter by requirement category'),'numeric_threshold');
    expect(screen.getByText(/No requirements match/)).toBeInTheDocument();
    expect(filterRequirements([ram,ssd],'conflicting','numeric_threshold')).toEqual([ram]);
  });
  it('searches clauses, switches status tabs, and sorts persisted rows by ID',async()=>{
    const request=vi.fn(async()=>response(data));
    render(<SupplierDashboard prefix="/workspaces/w" request={request} revision="1" onChanged={noop}/>);
    await screen.findByRole('button',{name:'Review requirement RAM-01'});
    await userEvent.type(screen.getByLabelText('Search requirements'),'512');
    expect(screen.queryByRole('button',{name:'Review requirement RAM-01'})).not.toBeInTheDocument();
    expect(screen.getByRole('button',{name:'Review requirement SSD-01'})).toBeVisible();
    await userEvent.clear(screen.getByLabelText('Search requirements'));
    await userEvent.click(screen.getByRole('button',{name:'Conflict detected (1)'}));
    expect(screen.queryByRole('button',{name:'Review requirement SSD-01'})).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'All requirements (2)'}));
    await userEvent.selectOptions(screen.getByLabelText('Sort requirements'),'id');
    const rows=screen.getAllByRole('row');
    expect(rows[1]).toHaveTextContent('RAM-01');
    expect(rows[2]).toHaveTextContent('SSD-01');
  });
  it('renders isolated requirements, tasks and export pages against the same backend',async()=>{
    const request=vi.fn(async()=>response(data));
    const {rerender}=render(<SupplierDashboard page="requirements" workspaceId="w" prefix="/workspaces/w" request={request} revision="1" onChanged={noop}/>);
    await screen.findByRole('button',{name:'Review requirement RAM-01'});
    expect(screen.queryByRole('button',{name:'Export compliance matrix CSV'})).not.toBeInTheDocument();
    expect(screen.queryByText('Corrective tasks')).not.toBeInTheDocument();
    rerender(<SupplierDashboard page="tasks" workspaceId="w" prefix="/workspaces/w" request={request} revision="1" onChanged={noop}/>);
    expect(screen.getByText('Corrective tasks')).toBeVisible();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    rerender(<SupplierDashboard page="export" workspaceId="w" prefix="/workspaces/w" request={request} revision="1" onChanged={noop}/>);
    expect(screen.getByRole('button',{name:'Export compliance matrix CSV'})).toBeVisible();
    expect(screen.queryByText('Corrective tasks')).not.toBeInTheDocument();
    expect(screen.getByRole('link',{name:'Upload amendment'})).toHaveAttribute('href','#/workspaces/w/amendments');
  });
  it('keeps reviewer identity while verification refreshes the requirement detail',async()=>{
    const request=vi.fn(async(path:string)=>response(path.endsWith('/dashboard')?data:path.endsWith('/detail')?ram:path.endsWith('/verify')?assessment:{suggested_criteria:[],assessments:[assessment]}));
    render(<SupplierDashboard prefix="/workspaces/w" request={request} revision="1" onChanged={noop}/>);
    await userEvent.click(await screen.findByRole('button',{name:'Review requirement RAM-01'}));
    const reviewer=await screen.findByLabelText('Reviewer name');
    await userEvent.type(reviewer,'Reviewer retained across refresh');
    await userEvent.click(screen.getByRole('button',{name:'Run evidence verification'}));
    await waitFor(()=>expect(request.mock.calls.some(([path])=>path.endsWith('/verify'))).toBe(true));
    await waitFor(()=>expect(screen.getByLabelText('Reviewer name')).toHaveValue('Reviewer retained across refresh'));
    await userEvent.type(screen.getByLabelText('Review rationale'),'Evidence checked after refresh.');
    expect(screen.getByRole('button',{name:'Approve finding'})).toBeEnabled();
  });
  it('shows errors rather than a successful or empty dashboard when loading fails',async()=>{
    const request=vi.fn().mockRejectedValueOnce(new Error('Access denied')).mockResolvedValue(response({...data,requirements:[],counts:{},tasks:[]}));
    render(<SupplierDashboard prefix="/workspaces/w" request={request} revision="1" onChanged={noop}/>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied');
    expect(screen.queryByText('Evidence review complete')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'Refresh readiness'}));
    expect(await screen.findByText(/No requirements yet/)).toBeInTheDocument();
  });
  it('loads exact clause and evidence checks from detail and verification endpoints',async()=>{
    const request=vi.fn(async(path:string)=>response(path.endsWith('/dashboard')?data:path.endsWith('/detail')?ram:{suggested_criteria:[],assessments:[assessment]}));
    render(<SupplierDashboard prefix="/workspaces/w" request={request} revision="1" onChanged={noop}/>);
    await userEvent.click(await screen.findByRole('button',{name:'Review requirement RAM-01'}));
    const detail=await screen.findByRole('region',{name:'Requirement detail'});
    expect(await within(detail).findByText('RAM: 16 GB')).toBeInTheDocument();
    expect(within(detail).getByRole('button',{name:'corrigendum.pdf · page 1'})).toBeInTheDocument();
    expect(within(detail).getByText('16 GB is below 32 GB.')).toBeInTheDocument();
    expect(within(detail).getByRole('button',{name:/Evidence page 2/})).toBeInTheDocument();
  });
  it('saves task due date, linked assessment and reviewer comment through the API',async()=>{
    const request=vi.fn(async(path:string)=>response(path.endsWith('/dashboard')?data:path.endsWith('/detail')?ram:path.endsWith('/tasks')?{id:'task'}:{suggested_criteria:[],assessments:[assessment]}));
    const changed=vi.fn();render(<SupplierDashboard prefix="/workspaces/w" request={request} revision="1" onChanged={changed}/>);
    await userEvent.click(await screen.findByRole('button',{name:'Review requirement RAM-01'}));
    await userEvent.click(await screen.findByText('Create a corrective task'));
    await userEvent.type(screen.getByLabelText('Task title'),'Obtain 32 GB datasheet');
    await userEvent.type(screen.getByLabelText('Action to take'),'Request a matching model with 32 GB RAM and rerun checks.');
    fireEvent.change(screen.getByLabelText('Due date (optional)'),{target:{value:'2026-11-01'}});
    await userEvent.type(screen.getByLabelText('Task reviewer'),'Supplier reviewer');
    await userEvent.type(screen.getByLabelText('Task update comment'),'RAM discrepancy confirmed.');
    await userEvent.click(screen.getByRole('button',{name:'Create corrective task'}));
    await waitFor(()=>expect(changed).toHaveBeenCalled());
    const call=request.mock.calls.find(([path])=>path.endsWith('/tasks')) as unknown as [string,RequestInit];
    expect(JSON.parse(String(call[1].body))).toMatchObject({assessment_id:'assessment',due_date:'2026-11-01',reviewer:'Supplier reviewer',comment:'RAM discrepancy confirmed.'});
  });
  it('downloads a protected CSV and surfaces export errors',async()=>{
    const create=vi.fn(()=> 'blob:csv');Object.defineProperty(URL,'createObjectURL',{value:create,configurable:true});Object.defineProperty(URL,'revokeObjectURL',{value:vi.fn(),configurable:true});
    const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
    const request=vi.fn(async(path:string)=>{if(path.endsWith('evidence-index'))throw new Error('Export unavailable');return path.endsWith('/dashboard')?response(data):new Response('status,unresolved\nConflict detected,True');});
    render(<SupplierDashboard prefix="/workspaces/w" request={request} revision="1" onChanged={noop}/>);
    await userEvent.click(await screen.findByRole('button',{name:'Export compliance matrix CSV'}));
    await waitFor(()=>expect(click).toHaveBeenCalled());expect(create).toHaveBeenCalled();
    expect(request).toHaveBeenCalledWith('/workspaces/w/exports/compliance-matrix');
    await userEvent.click(screen.getByRole('button',{name:'Export evidence index CSV'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Export unavailable');
  });
  it('loads saved version and approval timeline with timestamps',async()=>{
    const request=vi.fn(async(path:string)=>response(path.endsWith('/dashboard')?data:{total:1,items:[{id:'event',kind:'review',created_at:'2026-10-26T10:00:00+00:00',title:'Approved by Reviewer',description:'Confirmed SSD evidence.',requirement_id:'ssd'}]}));
    render(<SupplierDashboard prefix="/workspaces/w" request={request} revision="1" onChanged={noop}/>);
    await userEvent.click(await screen.findByRole('button',{name:'Show timeline'}));
    expect(await screen.findByText('Approved by Reviewer')).toBeInTheDocument();
    expect(screen.getByText('Confirmed SSD evidence.')).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'View related requirement'})).toBeInTheDocument();
  });
});

it('approval failures remain errors; successful rejection submits reviewer rationale',async()=>{
  const changed=vi.fn();
  const request=vi.fn(async(path:string,init?:RequestInit)=>{if(path.endsWith('/reviews')){const payload=JSON.parse(String(init?.body));if(payload.action==='approved')throw new Error('Evidence changed; rerun verification.');return response({...assessment,review_state:'rejected'});}return response({suggested_criteria:[],assessments:[assessment]});});
  render(<RequirementVerification prefix="/workspaces/w" requirementId="ram" request={request} libraryRevision={0} initialOpen onChanged={changed}/>);
  await screen.findByText('RAM: 16 GB');
  expect(screen.getByRole('button',{name:'Approve finding'})).toBeDisabled();
  await userEvent.type(screen.getByLabelText('Reviewer name'),'Reviewer');
  await userEvent.type(screen.getByLabelText('Review rationale'),'Evidence needs replacement.');
  await userEvent.click(screen.getByRole('button',{name:'Approve finding'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Evidence changed');expect(changed).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button',{name:'Reject finding'}));
  await waitFor(()=>expect(changed).toHaveBeenCalledTimes(1));
  const post=request.mock.calls.filter(([p])=>p.endsWith('/reviews')).at(-1)!;
  expect(JSON.parse(String(post[1]?.body))).toEqual({action:'rejected',reviewer:'Reviewer',comment:'Evidence needs replacement.'});
});
