export const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/ai/video-claw/backend';

export function apiUrl(path: string): string {
  if (path.startsWith('/api/') || path.startsWith('/code/')) {
    return `${API_BASE.replace(/\/$/, '')}${path}`;
  }
  return path;
}

export function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return fetch(typeof input === 'string' ? apiUrl(input) : input, init);
}
