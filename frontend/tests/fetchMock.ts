/** A fetch stand-in that records each request and answers from a queue. */
export type RecordedRequest = {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
};

type Reply = { status: number; body?: unknown } | { networkError: string };

export function fetchMock(...replies: Reply[]) {
  const requests: RecordedRequest[] = [];
  const queue = [...replies];
  const fetchFn = jest.fn(async (url: string, init: RequestInit = {}) => {
    requests.push({
      url,
      method: init.method ?? 'GET',
      headers: (init.headers ?? {}) as Record<string, string>,
      body: typeof init.body === 'string' ? JSON.parse(init.body) : init.body,
    });
    const reply = queue.shift();
    if (!reply) throw new Error(`No reply queued for ${url}`);
    if ('networkError' in reply) throw new TypeError(reply.networkError);
    const text = reply.body === undefined ? '' : JSON.stringify(reply.body);
    return {
      ok: reply.status >= 200 && reply.status < 300,
      status: reply.status,
      text: async () => text,
    } as Response;
  });
  return { fetchFn: fetchFn as unknown as typeof fetch, requests };
}
