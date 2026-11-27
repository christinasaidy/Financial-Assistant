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

/** A fake XMLHttpRequest for form uploads: records the request and answers with `reply` (or a network error). */
export function xhrMock(reply: { status: number; body?: unknown } | { networkError: true }) {
  const sent: { method: string; url: string; headers: Record<string, string>; body: unknown; timeout: number }[] = [];
  const xhrFn = () => {
    const xhr = {
      status: 0,
      responseText: '',
      timeout: 0,
      method: '',
      url: '',
      headers: {} as Record<string, string>,
      onload: null as null | (() => void),
      onerror: null as null | (() => void),
      ontimeout: null as null | (() => void),
      onabort: null as null | (() => void),
      open(method: string, url: string) {
        xhr.method = method;
        xhr.url = url;
      },
      setRequestHeader(name: string, value: string) {
        xhr.headers[name] = value;
      },
      abort() {
        xhr.onabort?.();
      },
      send(body: unknown) {
        sent.push({ method: xhr.method, url: xhr.url, headers: xhr.headers, body, timeout: xhr.timeout });
        setTimeout(() => {
          if ('networkError' in reply) return xhr.onerror?.();
          xhr.status = reply.status;
          xhr.responseText = reply.body === undefined ? '' : JSON.stringify(reply.body);
          xhr.onload?.();
        }, 0);
      },
    };
    return xhr as unknown as XMLHttpRequest;
  };
  return { xhrFn, sent };
}
