import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { EvidenceLibrary, RequirementVerification } from './EvidenceWorkflow';
vi.mock('./PdfSource',()=>({default:({url}:{url:string})=><div data-testid="plan-pdf-source">{url}</div>}));

it('uploads a replacement against the chosen current evidence and refreshes its history', async () => {
  const docs: {id:string; filename:string; evidence_type:string; page_count:number; version:number; is_current:boolean; supersedes_id:string | null}[] = [{id:'old', filename:'old.pdf', evidence_type:'datasheet', page_count:1, version:1, is_current:true, supersedes_id:null}];
  const request = vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      docs[0].is_current = false;
      docs.push({id:'new', filename:'new.pdf', evidence_type:'datasheet', page_count:1, version:2, is_current:true, supersedes_id:'old'});
    }
    return new Response(JSON.stringify(docs), {headers:{'Content-Type':'application/json'}});
  });
  const changed = vi.fn();
  render(<EvidenceLibrary prefix="/workspaces/w" request={request} onChange={changed}/>);
  await screen.findByText('old.pdf');
  await userEvent.selectOptions(screen.getByLabelText('Replace an existing document (optional)'), 'old');
  await userEvent.upload(screen.getByLabelText('Company PDF'), new File(['%PDF-1.7'], 'new.pdf', {type:'application/pdf'}));
  await userEvent.click(screen.getByRole('button', {name:'Upload company document'}));
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(request.mock.calls.some(([path, init]) => path.includes('evidence_type=datasheet&replaces_id=old') && init?.method === 'POST')).toBe(true);
  expect(screen.getByText(/version 1 · Replaced/)).toBeInTheDocument();
  expect(screen.getByText(/version 2 · Current/)).toBeInTheDocument();
});

it('runs prepared checks without manual fields or implicit approval and keeps edits behind Advanced', async () => {
  const criterion = {field:'ram_gb',operator:'gte',expected:'32 GB',quote:'RAM: at least 32 GB',evidence_type:'datasheet'};
  const request = vi.fn<(path:string, init?:RequestInit)=>Promise<Response>>().mockImplementation(async () => new Response(JSON.stringify({suggested_criteria:[criterion],assessments:[]})));
  render(<RequirementVerification prefix="/workspaces/w" requirementId="ram" request={request} libraryRevision={0} initialOpen/>);
  expect(await screen.findByText('1 check prepared from the tender. You can run them without filling in the form below.')).toBeVisible();
  const advanced = screen.getByText('Advanced: edit checks');
  expect(advanced.closest('details')).not.toHaveAttribute('open');
  await userEvent.click(screen.getByRole('button',{name:'Run document checks'}));
  await waitFor(() => expect(request).toHaveBeenCalledWith('/workspaces/w/requirements/ram/verify',expect.objectContaining({method:'POST'})));
  const call = request.mock.calls.find(([path]) => path.endsWith('/verify'));
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({criteria:[criterion],coverage_confirmed:false,reviewer:''});
  await userEvent.click(advanced);
  expect(advanced.closest('details')).toHaveAttribute('open');
  expect(screen.getByLabelText('Value required by the tender')).toHaveValue('32 GB');
});

const plannedCriterion = {field:'ram_gb',operator:'gte',expected:'32 GB',quote:'RAM: at least 32 GB',evidence_type:'datasheet'};
const checkPlan = {
  version:'1',kind:'evidence',coverage:'complete',criteria:[plannedCriterion],review_reasons:[],unhandled:[],
  sources:[{source_document_id:'tender',page:2,quote:'RAM: at least 32 GB',source_span_id:'span-ram'}],
  scope_refs:[{text:'Laptop Configuration A',page:2,source_document_id:'tender'}],
  scope:{label:'Configuration A',state:'matched',reason:'The document names the same product option.',documents:[{id:'datasheet',filename:'laptop-a.pdf'}]},
  auto_coverage_eligible:true,
};

it('shows the server check plan and exact source without treating prepared checks as approval',async()=>{
  const request=vi.fn(async(path:string)=>path.endsWith('/file')?new Response('%PDF'):new Response(JSON.stringify({check_plan:checkPlan,suggested_criteria:[plannedCriterion],assessments:[]})));
  Object.defineProperty(URL,'createObjectURL',{value:vi.fn(()=>'blob:plan-source'),configurable:true});
  Object.defineProperty(URL,'revokeObjectURL',{value:vi.fn(),configurable:true});
  render(<RequirementVerification prefix="/workspaces/w" requirementId="ram" request={request} libraryRevision={0} initialOpen/>);
  expect(await screen.findByText('Automatic checks are ready to run')).toBeVisible();
  expect(screen.getByText('laptop-a.pdf')).toBeVisible();
  expect(screen.getByText(/Run them to compare your documents; this does not approve/)).toBeVisible();
  const source=screen.getByText('Tender wording used for these checks · page 2');
  await userEvent.click(source);
  expect(source.closest('details')).toHaveTextContent('RAM: at least 32 GB');
  await userEvent.click(screen.getByRole('button',{name:'Open tender page 2'}));
  await waitFor(()=>expect(request).toHaveBeenCalledWith('/workspaces/w/documents/tender/file',expect.objectContaining({signal:expect.any(AbortSignal)})));
  expect(await screen.findByTestId('plan-pdf-source')).toHaveTextContent('blob:plan-source#page=2');
  await userEvent.click(screen.getByText('Advanced: edit checks'));
  await userEvent.clear(screen.getByLabelText('Value required by the tender'));
  await userEvent.type(screen.getByLabelText('Value required by the tender'),'64 GB');
  expect(screen.getByText('Checks have been edited manually')).toBeVisible();
  expect(screen.queryByText('Automatic checks are ready to run')).not.toBeInTheDocument();
});

it('keeps unclear product mapping and unhandled clauses visible without a false ready state',async()=>{
  const plan={...checkPlan,coverage:'partial',auto_coverage_eligible:false,
    scope:{...checkPlan.scope,state:'needs_review',documents:[],reason:'Two different product models are listed.'},
    review_reasons:['Choose the correct product before relying on these results.'],
    unhandled:[{text:'Guarantee valid at delivery.',reason:'The required period is unclear.'}],
  };
  const request=vi.fn(async()=>new Response(JSON.stringify({check_plan:plan,suggested_criteria:[plannedCriterion],assessments:[]})));
  render(<RequirementVerification prefix="/workspaces/w" requirementId="ram" request={request} libraryRevision={0} initialOpen/>);
  expect(await screen.findByText('Some details still need review')).toBeVisible();
  expect(screen.getByText('Two different product models are listed.')).toBeVisible();
  expect(screen.getByText('Choose the correct product before relying on these results.')).toBeVisible();
  expect(screen.queryByText('Automatic checks are ready to run')).not.toBeInTheDocument();
  await userEvent.click(screen.getByText('Parts that cannot be checked automatically (1)'));
  expect(screen.getByText('Guarantee valid at delivery.')).toBeVisible();
  expect(screen.getByText('The required period is unclear.')).toBeVisible();
  expect(screen.getByRole('button',{name:'Run document checks'})).toBeEnabled();
});

it('describes a procedural plan as an action to review instead of inventing a product check',async()=>{
  const plan={...checkPlan,kind:'procedure',coverage:'manual',criteria:[],auto_coverage_eligible:false,
    scope:{label:null,state:'unscoped',reason:'',documents:[]},scope_refs:[],
    sources:[{source_document_id:'tender',page:5,quote:'Upload the signed bid before the deadline.',source_span_id:'instruction'}],
  };
  const request=vi.fn(async()=>new Response(JSON.stringify({check_plan:plan,suggested_criteria:[],assessments:[]})));
  render(<RequirementVerification prefix="/workspaces/w" requirementId="procedure" request={request} libraryRevision={0} initialOpen/>);
  expect(await screen.findByText('This is a submission instruction')).toBeVisible();
  expect(screen.getByText(/Follow the instruction and record what you did/)).toBeVisible();
  expect(screen.queryByRole('list',{name:'Prepared document checks'})).not.toBeInTheDocument();
  expect(screen.getByText('Advanced: edit checks').closest('details')).not.toHaveAttribute('open');
});
