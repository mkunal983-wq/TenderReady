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
export type WorkspaceRoute = { workspaceId: string; page: WorkspacePage; status?: string };
const requirementStatuses = new Set(['reference_only', 'action_required', 'not_checked', 'supported', 'inconclusive', 'conflicting', 'missing', 'outdated']);
export function parseWorkspaceRoute(hash: string): WorkspaceRoute | null {
  const [path, query = ''] = hash.split('?');
  const match = /^#\/workspaces\/([^/]+)\/(readiness|requirements|evidence|amendments|tasks|export)$/.exec(path);
  if (!match) return null;
  try {
    const status = new URLSearchParams(query).get('status');
    return {workspaceId: decodeURIComponent(match[1]), page: match[2] as WorkspacePage,
      ...(match[2] === 'requirements' && status && requirementStatuses.has(status) ? {status} : {})};
  }
  catch { return null; }
}
export function workspaceHref(id: string, page: WorkspacePage, status?: string) {
  return `#/workspaces/${encodeURIComponent(id)}/${page}${page === 'requirements' && status && requirementStatuses.has(status) ? `?status=${encodeURIComponent(status)}` : ''}`;
}
function subscribe(callback: () => void) {
  window.addEventListener('hashchange', callback);
  return () => window.removeEventListener('hashchange', callback);
}
export function useWorkspaceLocation() {
  return useSyncExternalStore(subscribe, () => window.location.hash, () => '');
}
