import assert from 'node:assert/strict';

process.env.NEXT_PUBLIC_API_URL = '/ai/video-claw/backend';
const { apiFetch, apiUrl } = await import('../VideoClaw/video-claw/video-claw/frontend/lib/apiClient.ts');
assert.equal(apiUrl('/api/models'), '/ai/video-claw/backend/api/models');
assert.equal(apiUrl('/code/result/video.mp4'), '/ai/video-claw/backend/code/result/video.mp4');
assert.equal(apiUrl('https://example.com/video.mp4'), 'https://example.com/video.mp4');
assert.equal(apiUrl('/ai/video-claw/backend/api/models'), '/ai/video-claw/backend/api/models');
const calls = [];
globalThis.fetch = async (input, init) => {
  calls.push({ input, init });
  return new Response('{}');
};
await apiFetch('/api/upload_media', { method: 'POST', body: 'payload' });
assert.equal(calls[0].input, '/ai/video-claw/backend/api/upload_media');
assert.equal(calls[0].init.body, 'payload');
console.log('VideoClaw API and asset URL checks passed');
