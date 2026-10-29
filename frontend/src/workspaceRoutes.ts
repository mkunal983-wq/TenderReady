import { useSyncExternalStore } from 'react';

export const workspacePages = {
  readiness: 'Evidence Readiness',
  requirements: 'Requirements',
  evidence: 'Evidence Library',
  amendments: 'Amendments',
  tasks: 'Tasks',
  export: 'Export',
} as const;
export type WorkspacePage = keyof typeof workspacePages;
export type WorkspaceRoute = { workspaceId: string; page: WorkspacePage };
export function parseWorkspaceRoute(hash: string): WorkspaceRoute | null {
  const match = /^#\/workspaces\/([^/]+)\/(readiness|requirements|evidence|amendments|tasks|export)$/.exec(hash);
  if (!match) return null;
  try { return {workspaceId: decodeURIComponent(match[1]), page: match[2] as WorkspacePage}; }
  catch { return null; }
}
export function workspaceHref(id: string, page: WorkspacePage) {
  return `#/workspaces/${encodeURIComponent(id)}/${page}`;
}
function subscribe(callback: () => void) {
  window.addEventListener('hashchange', callback);
  return () => window.removeEventListener('hashchange', callback);
}
export function useWorkspaceLocation() {
  return useSyncExternalStore(subscribe, () => window.location.hash, () => '');
}
