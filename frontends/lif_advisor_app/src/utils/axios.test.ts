import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios';

// The interceptor keeps module-level state (isRefreshing, failedQueue), so each test
// imports a fresh copy rather than leaking a half-finished refresh into the next case.
async function freshInstance(storedTokens: Record<string, string>) {
    vi.resetModules();

    const store = new Map(Object.entries(storedTokens));
    vi.stubGlobal('localStorage', {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, v),
        removeItem: (k: string) => void store.delete(k),
    });
    const location = { href: '' };
    vi.stubGlobal('window', { location });

    const instance = (await import('./axios')).default as AxiosInstance;
    return { instance, store, location };
}

type Call = { url?: string; auth?: unknown };

/**
 * Replace the transport so no network is involved. `handler` decides, per request,
 * whether to resolve or reject — letting a test script "401 then 200" per URL.
 */
function stubTransport(instance: AxiosInstance, handler: (call: Call, n: number) => { status: number; data?: unknown }) {
    const calls: Call[] = [];
    instance.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
        const call: Call = { url: config.url, auth: config.headers?.Authorization };
        calls.push(call);
        const seen = calls.filter((c) => c.url === config.url).length;
        const { status, data } = handler(call, seen);
        const response = { data, status, statusText: '', headers: {}, config, request: {} };
        if (status >= 400) {
            const error = Object.assign(new Error(`Request failed with status code ${status}`), {
                isAxiosError: true,
                config,
                response,
            });
            throw error;
        }
        return response;
    };
    return calls;
}

describe('axios refresh-token interceptor', () => {
    beforeEach(() => vi.unstubAllGlobals());

    it('issues exactly one refresh for a burst of concurrent 401s', async () => {
        // Defect 1: every in-flight 401 used to start its own refresh, so all but the
        // winner retried with a token that had already been rotated away.
        const { instance, store } = await freshInstance({ token: 'stale', refreshToken: 'r1' });
        const calls = stubTransport(instance, (call, n) => {
            if (call.url === '/refresh-token') return { status: 200, data: { access_token: 'fresh' } };
            return n === 1 ? { status: 401 } : { status: 200, data: { ok: call.url } };
        });

        const results = await Promise.all([instance.get('/a'), instance.get('/b'), instance.get('/c')]);

        expect(calls.filter((c) => c.url === '/refresh-token')).toHaveLength(1);
        expect(results.map((r) => r.data)).toEqual([{ ok: '/a' }, { ok: '/b' }, { ok: '/c' }]);
        expect(store.get('token')).toBe('fresh');
        // every retry carried the new token, not the stale one
        const retries = calls.filter((c) => c.url !== '/refresh-token' && c.auth === 'Bearer fresh');
        expect(retries).toHaveLength(3);
    });

    it('logs out instead of looping when the refresh call itself 401s', async () => {
        // Defect 2 and the bug in #527: the refresh POST goes through this same
        // interceptor, so a 401 on it used to re-enter the refresh branch forever.
        const { instance, store, location } = await freshInstance({ token: 'stale', refreshToken: 'expired' });
        const calls = stubTransport(instance, () => ({ status: 401 }));

        await expect(instance.get('/a')).rejects.toThrow();

        expect(calls.filter((c) => c.url === '/refresh-token')).toHaveLength(1);
        expect(store.get('token')).toBeUndefined();
        expect(store.get('refreshToken')).toBeUndefined();
        expect(location.href).toBe('/login');
    });

    it('rejects the caller rather than hanging when the refresh fails', async () => {
        // Defect 3: the old catch redirected but never re-threw, leaving the caller's
        // promise pending forever.
        const { instance } = await freshInstance({ token: 'stale', refreshToken: 'r1' });
        stubTransport(instance, (call) => (call.url === '/refresh-token' ? { status: 500 } : { status: 401 }));

        await expect(instance.get('/a')).rejects.toThrow();
    });

    it('drains queued requests with a rejection when the refresh fails', async () => {
        const { instance } = await freshInstance({ token: 'stale', refreshToken: 'r1' });
        stubTransport(instance, (call) => (call.url === '/refresh-token' ? { status: 500 } : { status: 401 }));

        const settled = await Promise.allSettled([instance.get('/a'), instance.get('/b'), instance.get('/c')]);

        expect(settled.every((s) => s.status === 'rejected')).toBe(true);
    });

    it('logs out without calling refresh when no refresh token is stored', async () => {
        const { instance, location } = await freshInstance({ token: 'stale' });
        const calls = stubTransport(instance, () => ({ status: 401 }));

        await expect(instance.get('/a')).rejects.toThrow();

        expect(calls.filter((c) => c.url === '/refresh-token')).toHaveLength(0);
        expect(location.href).toBe('/login');
    });

    it('passes non-401 failures straight through', async () => {
        const { instance, location } = await freshInstance({ token: 't', refreshToken: 'r1' });
        const calls = stubTransport(instance, () => ({ status: 500 }));

        await expect(instance.get('/a')).rejects.toThrow();

        expect(calls.filter((c) => c.url === '/refresh-token')).toHaveLength(0);
        expect(location.href).toBe('');
    });

    it('leaves the happy path untouched', async () => {
        const { instance } = await freshInstance({ token: 'good', refreshToken: 'r1' });
        const calls = stubTransport(instance, () => ({ status: 200, data: { ok: true } }));

        const response = await instance.get('/a');

        expect(response.data).toEqual({ ok: true });
        expect(calls).toHaveLength(1);
        expect(calls[0].auth).toBe('Bearer good');
    });
});
