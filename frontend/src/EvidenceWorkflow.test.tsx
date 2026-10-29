import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { EvidenceLibrary } from './EvidenceWorkflow';

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
  await userEvent.click(screen.getByRole('button', {name:'Upload company evidence'}));
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(request.mock.calls.some(([path, init]) => path.includes('evidence_type=datasheet&replaces_id=old') && init?.method === 'POST')).toBe(true);
  expect(screen.getByText(/version 1 · Replaced/)).toBeInTheDocument();
  expect(screen.getByText(/version 2 · Current/)).toBeInTheDocument();
});
