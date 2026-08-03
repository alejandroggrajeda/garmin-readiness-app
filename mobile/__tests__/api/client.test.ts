import * as client from '../../src/api/client';

describe('api/client triggerSync', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.resetAllMocks();
  });

  function mockFetchOnce(status: number, body: unknown) {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    }) as unknown as typeof fetch;
  }

  it('maps 202 to an accepted result with run id', async () => {
    mockFetchOnce(202, { run_id: 'abc-123' });

    const result = await client.triggerSync();

    expect(result).toEqual({ kind: 'accepted', runId: 'abc-123' });
  });

  it('maps 409 to an in_progress result', async () => {
    mockFetchOnce(409, { run_id: 'running-1', started_at: '2026-08-03T08:00:00Z' });

    const result = await client.triggerSync();

    expect(result).toEqual({
      kind: 'in_progress',
      runId: 'running-1',
      startedAt: '2026-08-03T08:00:00Z',
    });
  });

  it('maps 423 to an auth_locked result', async () => {
    mockFetchOnce(423, { auth_locked: true });

    const result = await client.triggerSync();

    expect(result).toEqual({ kind: 'auth_locked' });
  });

  it('maps 429 to a cooldown result with retry-after seconds', async () => {
    mockFetchOnce(429, { retry_after: 21600 });

    const result = await client.triggerSync();

    expect(result).toEqual({ kind: 'cooldown', retryAfterSeconds: 21600 });
  });

  it('sends the X-API-Key header on every request', async () => {
    mockFetchOnce(202, { run_id: 'abc-123' });

    await client.triggerSync();

    const [, options] = (globalThis.fetch as jest.Mock).mock.calls[0];
    expect(options.headers['X-API-Key']).toBeDefined();
  });
});
