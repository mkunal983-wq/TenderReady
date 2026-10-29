import {render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect, it, vi} from 'vitest';
import {AmendmentWorkflow} from './AmendmentWorkflow';

it('refreshes candidates after extraction and submits an automatic comparison without mappings', async()=>{
  let extracted=false;
  const request=vi.fn(async(path:string, init?:RequestInit)=>{
    if(path.endsWith('/compare')) return new Response(JSON.stringify({fingerprint:'a'.repeat(64),changes:[],warnings:[]}));
    if(path.endsWith('/snapshots')) return new Response(JSON.stringify([{id:'baseline',sequence:1,document_id:'original',mode:'baseline',requirements:[],changes:[]}]));
    expect(init?.method).toBeUndefined();
    return new Response(JSON.stringify(extracted?[{id:'new',text:'The Atlas A14 product must have at least 32 GB RAM.'}]:[]));
  });
  const props={prefix:'/workspaces/w',documentId:'amendment',request,onChanged:vi.fn()};
  const view=render(<AmendmentWorkflow {...props} revision="0-running-0"/>);
  await screen.findByText('Current tender version 1');
  await userEvent.click(screen.getByText('Match requirements or mark removals'));
  expect(screen.queryByLabelText('The Atlas A14 product must have at least 32 GB RAM.')).not.toBeInTheDocument();
  extracted=true;
  view.rerender(<AmendmentWorkflow {...props} revision="0-succeeded-1"/>);
  await screen.findByLabelText('The Atlas A14 product must have at least 32 GB RAM.');
  await userEvent.type(screen.getByLabelText('Reviewer name'),'Synthetic reviewer');
  await userEvent.click(screen.getByRole('button',{name:'Compare with current tender'}));
  await waitFor(()=>expect(request.mock.calls.some(([p])=>p.endsWith('/compare'))).toBe(true));
  const call=request.mock.calls.find(([p])=>p.endsWith('/compare'))!;
  expect(JSON.parse(call[1]!.body as string).mappings).toEqual([]);
});
