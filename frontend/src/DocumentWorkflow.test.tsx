import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { DocumentWorkflow } from './DocumentWorkflow';
const workspace={id:'w',title:'Upload navigation regression'};
afterEach(()=>vi.unstubAllGlobals());
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
