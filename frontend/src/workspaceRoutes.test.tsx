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

it('round trips requirement status links and ignores unsupported filter values',()=>{
  expect(parseWorkspaceRoute(workspaceHref('w','requirements','not_checked'))).toEqual({workspaceId:'w',page:'requirements',status:'not_checked'});
  expect(parseWorkspaceRoute('#/workspaces/w/requirements?status=inconclusive')).toEqual({workspaceId:'w',page:'requirements',status:'inconclusive'});
  expect(parseWorkspaceRoute('#/workspaces/w/requirements?status=anything')).toEqual({workspaceId:'w',page:'requirements'});
  expect(parseWorkspaceRoute('#/workspaces/w/tasks?status=not_checked')).toEqual({workspaceId:'w',page:'tasks'});
  expect(workspaceHref('w','tasks','not_checked')).toBe('#/workspaces/w/tasks');
});
