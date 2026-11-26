import Constants from 'expo-constants';

/**
 * A small fetch wrapper for the Fatourati backend: JSON in and out, the bearer token on every signed-in
 * request, and one error type for anything that is not a 2xx.
 *
 * It knows nothing about features. The composition root (src/container.ts) gives it two callbacks:
 * `getToken` (the current access token, if any) and `onUnauthorized` (called when the backend rejects the
 * token, so the session can be cleared).
 */

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export type RequestOptions = {
  method?: HttpMethod;
  /** Sent as JSON. FormData is sent as is (receipt uploads). */
  body?: unknown;
  /** Query string values; undefined values are left out. */
  query?: Record<string, string | number | boolean | undefined>;
  /**
   * 'session' (default): send the signed-in user's token, and treat a 401 as an expired session.
   * 'none': send no token (sign in, create account); a 401 is just an error for the caller.
   * A string: send exactly this token (checking a saved token before it becomes the session).
   */
  auth?: 'session' | 'none' | string;
  signal?: AbortSignal;
  /** How long to wait for the whole answer before giving up as unreachable; the client's default otherwise. */
  timeoutMs?: number;
  /** Extra headers, e.g. the assistant's Idempotency-Key. */
  headers?: Record<string, string>;
};

/**
 * A request to an address nothing answers on (the laptop's Wi-Fi address changed, another network) can hang
 * for minutes, which left the sign-in button spinning. After this long it fails as a NetworkError instead.
 */
export const DEFAULT_TIMEOUT_MS = 15_000;

/** The backend answered with a status outside 2xx. `detail` is the backend's message, ready to show. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly body: unknown;

  constructor(status: number, detail: string, body: unknown) {
    super(`HTTP ${status}: ${detail}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

/** The backend could not be reached at all (no Wi-Fi, wrong EXPO_PUBLIC_API_URL, server stopped, no answer in time). */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super(`Could not reach the server: ${cause instanceof Error ? cause.message : String(cause)}`);
    this.name = 'NetworkError';
  }
}

export type HttpClientConfig = {
  /** A function so that a missing EXPO_PUBLIC_API_URL fails the request, not the app's start. */
  baseUrl: string | (() => string);
  getToken: () => string | null;
  onUnauthorized: () => void;
  fetchFn?: typeof fetch;
  /** DEFAULT_TIMEOUT_MS unless given. */
  timeoutMs?: number;
};

export type HttpClient = {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
};

/**
 * FastAPI sends `{"detail": "..."}` for domain errors and `{"detail": [{"msg": ...}, ...]}` for request
 * validation errors (422). Both become one readable sentence.
 */
export function detailFrom(body: unknown, status: number): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : null))
        .filter((message): message is string => Boolean(message));
      if (messages.length > 0) return messages.join('. ');
    }
  }
  return `The request failed (${status})`;
}

function buildUrl(baseUrl: string, path: string, query: RequestOptions['query']): string {
  const base = baseUrl.replace(/\/+$/, '');
  const route = path.startsWith('/') ? path : `/${path}`;
  const params = Object.entries(query ?? {})
    .filter(([, value]) => value !== undefined)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  return `${base}${route}${params.length > 0 ? `?${params.join('&')}` : ''}`;
}

export function createHttpClient(config: HttpClientConfig): HttpClient {
  const fetchFn = config.fetchFn ?? fetch;

  return {
    async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
      const { method = 'GET', body, query, auth = 'session', signal, timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS } = options;
      const headers: Record<string, string> = { Accept: 'application/json', ...options.headers };

      const token = auth === 'session' ? config.getToken() : auth === 'none' ? null : auth;
      if (token) headers.Authorization = `Bearer ${token}`;

      let payload: BodyInit | undefined;
      if (body instanceof FormData) {
        payload = body;
      } else if (body !== undefined) {
        headers['Content-Type'] = 'application/json';
        payload = JSON.stringify(body);
      }

      // One controller for the time limit and the caller's own signal.
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(new Error(`No answer within ${timeoutMs / 1000} s`)), timeoutMs);
      const forward = () => controller.abort(signal?.reason);
      if (signal?.aborted) forward();
      else signal?.addEventListener('abort', forward);

      let response: Response;
      let text: string;
      try {
        const baseUrl = typeof config.baseUrl === 'function' ? config.baseUrl() : config.baseUrl;
        response = await fetchFn(buildUrl(baseUrl, path, query), { method, headers, body: payload, signal: controller.signal });
        text = await response.text();
      } catch (error) {
        throw new NetworkError(controller.signal.aborted && !signal?.aborted ? controller.signal.reason : error);
      } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', forward);
      }

      let parsed: unknown = undefined;
      if (text.length > 0) {
        try {
          parsed = JSON.parse(text);
        } catch {
          parsed = text;
        }
      }

      if (!response.ok) {
        // Only a rejected session token means the session is over. A 401 from sign in means a wrong password.
        if (response.status === 401 && auth === 'session' && token) config.onUnauthorized();
        throw new ApiError(response.status, detailFrom(parsed, response.status), parsed);
      }
      return parsed as T;
    },
  };
}

/** The backend's port on the laptop (uvicorn ... --port 8000). */
export const BACKEND_PORT = 8000;

/**
 * Where the backend is. EXPO_PUBLIC_API_URL wins when it is set (a backend somewhere else). Otherwise it is the
 * laptop Expo Go loaded the app from, on port 8000: the backend runs on that same laptop, so this follows the
 * laptop to whatever Wi-Fi or hotspot it is on, with nothing to edit.
 */
export function backendUrl(configured: string | undefined, devServerHost: string | null | undefined): string {
  const fixed = configured?.trim();
  if (fixed) return fixed;
  const host = devServerHost?.replace(/^[a-z]+:\/\//i, '').split('/')[0]?.replace(/:\d+$/, '');
  if (!host) {
    throw new Error('Cannot tell where the backend is: open the app in Expo Go from `npm run phone`, or set EXPO_PUBLIC_API_URL in .env.');
  }
  return `http://${host}:${BACKEND_PORT}`;
}

/** The backend's address for this run of the app (see backendUrl). EXPO_PUBLIC_API_URL is read with dot notation so Expo inlines it. */
export function apiBaseUrl(): string {
  return backendUrl(process.env.EXPO_PUBLIC_API_URL, Constants.expoConfig?.hostUri ?? Constants.expoGoConfig?.debuggerHost);
}
