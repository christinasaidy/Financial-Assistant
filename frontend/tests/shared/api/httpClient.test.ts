import { ApiError, NetworkError, createHttpClient, detailFrom } from '@/shared/api/httpClient';

import { fetchMock } from '../../fetchMock';

function client(fetchFn: typeof fetch, token: string | null = 'session-token') {
  const onUnauthorized = jest.fn();
  const http = createHttpClient({
    baseUrl: 'http://192.168.1.23:8000/',
    getToken: () => token,
    onUnauthorized,
    fetchFn,
  });
  return { http, onUnauthorized };
}

describe('httpClient', () => {
  it('sends JSON with the session token and returns the parsed body', async () => {
    const { fetchFn, requests } = fetchMock({ status: 200, body: { ok: true } });
    const { http } = client(fetchFn);

    const result = await http.request<{ ok: boolean }>('/budgets/3', {
      method: 'PUT',
      body: { month: '2026-11', limit_amount: '250' },
      query: { month: '2026-11', currency: undefined },
    });

    expect(result).toEqual({ ok: true });
    expect(requests[0]).toMatchObject({
      url: 'http://192.168.1.23:8000/budgets/3?month=2026-11',
      method: 'PUT',
      body: { month: '2026-11', limit_amount: '250' },
    });
    expect(requests[0]?.headers).toMatchObject({
      Authorization: 'Bearer session-token',
      'Content-Type': 'application/json',
    });
  });

  it("sends no token with auth: 'none', and an explicit one when given", async () => {
    const { fetchFn, requests } = fetchMock({ status: 200, body: {} }, { status: 200, body: {} });
    const { http } = client(fetchFn);
    await http.request('/auth/login', { method: 'POST', body: {}, auth: 'none' });
    await http.request('/auth/me', { auth: 'saved-token' });
    expect(requests[0]?.headers.Authorization).toBeUndefined();
    expect(requests[1]?.headers.Authorization).toBe('Bearer saved-token');
  });

  it('returns undefined for an empty body (204)', async () => {
    const { fetchFn } = fetchMock({ status: 204 });
    const { http } = client(fetchFn);
    await expect(http.request('/receipts/4', { method: 'DELETE' })).resolves.toBeUndefined();
  });

  it("turns an error status into ApiError with the backend's message", async () => {
    const { fetchFn } = fetchMock({ status: 404, body: { detail: 'Receipt 4 not found' } });
    const { http } = client(fetchFn);
    const error = await http.request('/receipts/4').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, detail: 'Receipt 4 not found' });
  });

  it('ends the session on a 401 for a request sent with the session token', async () => {
    const { fetchFn } = fetchMock({ status: 401, body: { detail: 'Invalid token' } });
    const { http, onUnauthorized } = client(fetchFn);
    await expect(http.request('/receipts')).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('does not end the session on a 401 from sign in (a wrong password)', async () => {
    const { fetchFn } = fetchMock({ status: 401, body: { detail: 'Invalid email or password' } });
    const { http, onUnauthorized } = client(fetchFn);
    await expect(http.request('/auth/login', { method: 'POST', body: {}, auth: 'none' })).rejects.toMatchObject({
      status: 401,
    });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('reports an unreachable server as NetworkError', async () => {
    const { fetchFn } = fetchMock({ networkError: 'Network request failed' });
    const { http } = client(fetchFn);
    await expect(http.request('/health')).rejects.toBeInstanceOf(NetworkError);
  });

  /** A fetch to an address nothing answers on: it waits until it is aborted. */
  const silentFetch = (async (_url: string, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
    })) as unknown as typeof fetch;

  it('gives up on a server that never answers, as a NetworkError, instead of waiting forever', async () => {
    const http = createHttpClient({
      baseUrl: 'http://192.168.1.71:8000',
      getToken: () => null,
      onUnauthorized: () => undefined,
      fetchFn: silentFetch,
      timeoutMs: 30,
    });
    const started = Date.now();
    await expect(http.request('/auth/login', { method: 'POST', body: {}, auth: 'none' })).rejects.toThrow(
      'Could not reach the server: No answer within 0.03 s',
    );
    expect(Date.now() - started).toBeLessThan(2_000);
  });

  it('lets one request wait longer than the default, and the caller cancel it', async () => {
    const { http } = client(silentFetch);
    const caller = new AbortController();
    const pending = http.request('/receipts', { method: 'POST', timeoutMs: 60_000, signal: caller.signal });
    caller.abort(new Error('left the screen'));
    await expect(pending).rejects.toThrow('Could not reach the server: aborted');
  });

  it('reports a missing EXPO_PUBLIC_API_URL when a request is made, not at start', async () => {
    const http = createHttpClient({
      baseUrl: () => {
        throw new Error('EXPO_PUBLIC_API_URL is not set');
      },
      getToken: () => null,
      onUnauthorized: () => undefined,
    });
    await expect(http.request('/health')).rejects.toThrow('EXPO_PUBLIC_API_URL is not set');
  });
});

describe('detailFrom', () => {
  it('joins FastAPI validation messages', () => {
    const body = { detail: [{ msg: 'Field required' }, { msg: 'Input should be a valid string' }] };
    expect(detailFrom(body, 422)).toBe('Field required. Input should be a valid string');
  });

  it('falls back to the status', () => {
    expect(detailFrom('Internal Server Error', 500)).toBe('The request failed (500)');
  });
});
