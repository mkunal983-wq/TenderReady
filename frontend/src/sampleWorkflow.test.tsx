import {afterEach,expect,it,vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import {createSampleWorkflow,SampleWorkflowError} from './sampleWorkflow';
import {SampleGuide} from './SampleGuide';
afterEach(()=>vi.unstubAllGlobals());
it('does not create records when a required fixture cannot be downloaded',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>new Response('',{status:404})));
  const request=vi.fn();
  await expect(createSampleWorkflow(request,()=>{})).rejects.toThrow('Sample file unavailable');
  expect(request).not.toHaveBeenCalled();
});
it('preserves the partial workspace on API failure and never falls back to AI',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>new Response('%PDF-sample')));
  const workspace={id:'sample-id',title:'Sample',supplier_name:'Synthetic',revision:0};
  const request=vi.fn().mockResolvedValueOnce(workspace).mockRejectedValueOnce(new Error('Upload rejected'));
  try {await createSampleWorkflow(request,()=>{});throw new Error('Expected failure');}
  catch(error){expect(error).toBeInstanceOf(SampleWorkflowError);expect(error).toMatchObject({workspace,message:'Upload rejected'});}
  expect(request.mock.calls.some(([path])=>String(path).includes('/analyze'))).toBe(false);
});
it('marks scripted approvals and verifies the persisted amendment result',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>new Response('%PDF-sample')));
  const request=vi.fn(async(path:string)=>{
    if(path==='/workspaces')return {id:'w',title:'Sample',supplier_name:'Synthetic',revision:0};
    if(path.endsWith('/requirements'))return [{id:'ram'},{id:'ssd'}];
    if(path.endsWith('/verify'))return {id:'a',status:'supported'};
    if(path.endsWith('/compare'))return {fingerprint:'preview'};
    if(path.endsWith('/apply-amendment'))return {changes:[{classification:'Modified',impacts:[{new_assessment:{status:'conflicting'}}]},{classification:'Unchanged'}]};
    return {id:'document'};
  });
  await createSampleWorkflow(request as Parameters<typeof createSampleWorkflow>[0],()=>{});
  const calls=request.mock.calls as unknown as [string,RequestInit][];
  const reviews=calls.filter(([path])=>path.endsWith('/reviews'));
  expect(reviews).toHaveLength(2);
  expect(JSON.parse(String(reviews[0][1].body)).reviewer).toContain('SYNTHETIC DEMO');
  expect(calls.some(([path])=>path.endsWith('/analyze'))).toBe(false);
});
it('provides replacement download and existing workspace routes without claiming AI inference',()=>{
  render(<SampleGuide workspaceId="w"/>);
  expect(screen.getByText(/AI not used/)).toBeInTheDocument();
  expect(screen.getByText('32 GB replacement datasheet')).toHaveAttribute('download');
  expect(screen.getByText('Evidence Library')).toHaveAttribute('href','#/workspaces/w/evidence');
});
