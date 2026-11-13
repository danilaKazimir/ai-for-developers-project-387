import { QueryClient } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getGetHealthQueryOptions, getHealth } from './generated/calendar';
import { ApiHttpError } from './http';

afterEach(() => vi.unstubAllGlobals());

describe('generated Fetch and Query client', () => {
  it('requests the API and returns a typed response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ status: 'ok', database: 'ok' }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(getHealth()).resolves.toEqual({ status: 'ok', database: 'ok' });
    expect(fetchMock).toHaveBeenCalledWith('/api/health', expect.objectContaining({ method: 'GET' }));
  });

  it('exposes the HTTP status and body through the Query error state', async () => {
    const body = { code: 'DATABASE_UNAVAILABLE', message: 'Сервис временно недоступен. Повторите попытку позже' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body, { status: 503 })));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const options = getGetHealthQueryOptions();
    try {
      await expect(client.fetchQuery(options)).rejects.toMatchObject({ status: 503, body });
      const state = client.getQueryState(options.queryKey);
      expect(state?.status).toBe('error');
      expect(state?.error).toBeInstanceOf(ApiHttpError);
    } finally {
      client.clear();
    }
  });

  it('keeps non-JSON server errors readable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Bad gateway', { status: 502 })));
    await expect(getHealth()).rejects.toMatchObject({ status: 502, body: 'Bad gateway' });
  });

  it('propagates cancellation to fetch', async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError'));
    vi.stubGlobal('fetch', fetchMock);
    controller.abort();
    await expect(getHealth({ signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchMock).toHaveBeenCalledWith('/api/health', expect.objectContaining({ signal: controller.signal }));
  });
});

