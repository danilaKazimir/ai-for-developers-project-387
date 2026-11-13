export class ApiHttpError<T = unknown> extends Error {
  readonly status: number;
  readonly body: T;

  constructor(status: number, body: T) {
    super(`API request failed with HTTP ${status}`);
    this.name = 'ApiHttpError';
    this.status = status;
    this.body = body;
  }
}

// Orval uses this alias for errors exposed by TanStack Query hooks.
export type ErrorType<T> = ApiHttpError<T> | TypeError | DOMException;

export async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const text = await response.text();
  const body: unknown = text ? parseBody(text) : undefined;
  if (!response.ok) throw new ApiHttpError(response.status, body);
  return body as T;
}

function parseBody(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

