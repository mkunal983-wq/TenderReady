import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, expect, it, vi } from 'vitest';
import { WorkspaceHub } from './WorkspaceHub';
const workspace={id:'w',title:'School laptops',supplier_name:'Supplier Ltd'};
beforeAll(()=>{
  HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
  HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
});
it('requires the confirmation dialog and lets cancellation leave backend data untouched',async()=>{
  const remove=vi.fn().mockResolvedValue(undefined);
  render(<WorkspaceHub workspaces={[workspace]} busy={false} createForm={null} onRename={vi.fn()} onDelete={remove}/>);
  await userEvent.click(screen.getByRole('button',{name:'Delete workspace School laptops'}));
  const dialog=screen.getByRole('dialog',{name:'Delete workspace?'});
  expect(within(dialog).getByText('School laptops')).toBeVisible();
  expect(remove).not.toHaveBeenCalled();
  await userEvent.click(within(dialog).getByRole('button',{name:'Cancel'}));
  expect(remove).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button',{name:'Delete workspace School laptops'}));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Delete workspace'}));
  await waitFor(()=>expect(remove).toHaveBeenCalledExactlyOnceWith(workspace));
});
it('renames via callback, keeps errors visible, and permits retry',async()=>{
  const rename=vi.fn().mockRejectedValueOnce(new Error('Workspace changed. Refresh the list.')).mockResolvedValue(undefined);
  render(<WorkspaceHub workspaces={[workspace]} busy={false} createForm={null} onRename={rename} onDelete={vi.fn()}/>);
  await userEvent.click(screen.getByRole('button',{name:'Rename workspace School laptops'}));
  await userEvent.clear(screen.getByRole('textbox',{name:'Workspace name'}));
  expect(screen.getByRole('button',{name:'Save name'})).toBeDisabled();
  await userEvent.type(screen.getByRole('textbox',{name:'Workspace name'}),'Revised school laptops');
  await userEvent.click(screen.getByRole('button',{name:'Save name'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Workspace changed. Refresh the list.');
  expect(rename).toHaveBeenCalledWith(workspace,'Revised school laptops');
  await userEvent.click(screen.getByRole('button',{name:'Save name'}));
  await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
});
