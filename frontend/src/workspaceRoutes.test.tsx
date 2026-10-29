import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { parseWorkspaceRoute, useWorkspaceLocation, workspaceHref, workspacePages } from './workspaceRoutes';

afterEach(()=>window.history.replaceState(null,'','/'));
it('round trips each workspace-specific page and safely rejects malformed routes',()=>{
  for(const page of Object.keys(workspacePages) as (keyof typeof workspacePages)[]) {
    expect(parseWorkspaceRoute(workspaceHref('supplier workspace',page))).toEqual({workspaceId:'supplier workspace',page});
  }
  expect(parseWorkspaceRoute('#/workspaces/a/unknown')).toBeNull();
  expect(parseWorkspaceRoute('#/workspaces/%ZZ/evidence')).toBeNull();
  expect(parseWorkspaceRoute('#workspace-start')).toBeNull();
});
it('reads direct links and updates on browser hash navigation',()=>{
  window.history.replaceState(null,'',workspaceHref('w','requirements'));
  function Location(){return <output>{useWorkspaceLocation()}</output>;}
  render(<Location/>);
  expect(screen.getByRole('status')).toHaveTextContent('/workspaces/w/requirements');
  act(()=>{window.history.replaceState(null,'',workspaceHref('w','evidence'));window.dispatchEvent(new HashChangeEvent('hashchange'));});
  expect(screen.getByRole('status')).toHaveTextContent('/workspaces/w/evidence');
});
