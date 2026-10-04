import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios';

// The interceptor keeps module-level state (isRefreshing, failedQueue, sessionEnded), so
// each test imports a fresh copy rather than leaking a half-finished refresh into the next.
async function freshInstance(storedTokens: Record<string, string>) {
    vi.resetModules();

    const store = new Map(Object.entries(storedTokens));
    vi.stubGlobal('localStorage', {
        getItem: (k: string) => store.get(k) ?? null,
        // String(v), not v: Storage.setItem coerces its value to a DOMString. Storing the
        // raw value instead would turn `setItem('token', undefined)` into a getItem() of
        // null, when a browser returns the *truthy* string "undefined" -- so the harness
        // would show a different failure mode than production for a malformed refresh.
        setItem: (k: string, v: string) => void store.set(k, String(v)),
        removeItem: (k: string) => void store.delete(k),
    });
    // Records every assignment, so a test can tell one navigation from two.
    const hrefWrites: string[] = [];
    const location = {
        get href() {
            return hrefWrites[hrefWrites.length - 1] ?? '';
        },
        set href(value: string) {
            hrefWrites.push(value);
        },
    };
    vi.stubGlobal('window', { location });

    const instance = (await import('./axios')).default as AxiosInstance;
    return { instance, store, location, hrefWrites };
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

const countOf = (calls: Call[], url: string) => calls.filter((c) => c.url === url).length;

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

        expect(countOf(calls, '/refresh-token')).toBe(1);
        expect(results.map((r) => r.data)).toEqual([{ ok: '/a' }, { ok: '/b' }, { ok: '/c' }]);
        expect(store.get('token')).toBe('fresh');
        // every retry carried the new token, not the stale one
        const retries = calls.filter((c) => c.url !== '/refresh-token' && c.auth === 'Bearer fresh');
        expect(retries).toHaveLength(3);
    });

    it('holds the mutex when a queued retry 401s again', async () => {
        // Queued retries used not to be marked _retry, so one that 401ed again re-entered
        // the refresh branch (`finally` has already cleared isRefreshing) and started its
        // own refresh, re-queueing its siblings unmarked behind it. Up to N refreshes per
        // burst — a reduced form of the storm in #527.
        const { instance } = await freshInstance({ token: 'stale', refreshToken: 'r1' });
        let generation = 0;
        const calls = stubTransport(instance, (call, n) => {
            if (call.url === '/refresh-token') {
                generation += 1;
                return { status: 200, data: { access_token: `fresh${generation}` } };
            }
            // the first retry 401s too, which is what re-entered the branch
            return n <= 2 ? { status: 401 } : { status: 200, data: { ok: call.url } };
        });

        await Promise.allSettled([instance.get('/a'), instance.get('/b'), instance.get('/c')]);

        expect(countOf(calls, '/refresh-token')).toBe(1);
    });

    it('passes a 401 from /login straight back to the caller', async () => {
        // The advisor API answers bad credentials with 401 (advisor_restapi core.py). That
        // is the endpoint's own answer, not a stale access token: LoginPanel renders the
        // message itself, so ending the session here would navigate, and nginx try_files
        // serves that as a full SPA reload — blanking the form the user is looking at.
        const { instance, hrefWrites } = await freshInstance({});
        const calls = stubTransport(instance, () => ({ status: 401 }));

        await expect(instance.post('/login', { username: 'u', password: 'wrong' })).rejects.toThrow();

        expect(hrefWrites).toEqual([]);
        expect(countOf(calls, '/refresh-token')).toBe(0);
        expect(countOf(calls, '/login')).toBe(1);
    });

    it('never refreshes or re-posts credentials when /login 401s with a stale session stored', async () => {
        // Same path with leftover tokens: the old code refreshed and then silently
        // re-POSTed the wrong password under a new access token.
        const { instance, hrefWrites } = await freshInstance({ token: 'stale', refreshToken: 'r1' });
        const calls = stubTransport(instance, (call) =>
            call.url === '/refresh-token' ? { status: 200, data: { access_token: 'fresh' } } : { status: 401 }
        );

        await expect(instance.post('/login', { username: 'u', password: 'wrong' })).rejects.toThrow();

        expect(countOf(calls, '/refresh-token')).toBe(0);
        expect(countOf(calls, '/login')).toBe(1);
        expect(hrefWrites).toEqual([]);
    });

    it('matches the auth paths through an absolute URL', async () => {
        // The guards are a correctness boundary, so they must not fail open just because a
        // caller spelled the URL differently.
        const { instance, hrefWrites } = await freshInstance({ token: 'stale', refreshToken: 'r1' });
        const calls = stubTransport(instance, () => ({ status: 401 }));

        await expect(instance.post('https://advisor-api.example.net/login?next=%2F', {})).rejects.toThrow();

        expect(countOf(calls, '/refresh-token')).toBe(0);
        expect(hrefWrites).toEqual([]);
    });

    it.each([
        ['no access_token field', {}],
        ['an empty access_token', { access_token: '' }],
    ])('treats a refresh 200 with %s as a failure', async (_label, body) => {
        // A malformed body used to be stored verbatim: Storage.setItem coerces, so
        // localStorage held the truthy string "undefined" and every later request sent
        // `Authorization: Bearer undefined`.
        const { instance, store, hrefWrites } = await freshInstance({ token: 'stale', refreshToken: 'r1' });
        const calls = stubTransport(instance, (call, n) => {
            if (call.url === '/refresh-token') return { status: 200, data: body };
            return n === 1 ? { status: 401 } : { status: 200, data: { ok: call.url } };
        });

        const settled = await Promise.allSettled([instance.get('/a'), instance.get('/b'), instance.get('/c')]);

        expect(settled.map((s) => s.status)).toEqual(['rejected', 'rejected', 'rejected']);
        expect(store.get('token')).toBeUndefined();
        expect(calls.some((c) => c.auth === 'Bearer undefined' || c.auth === 'Bearer ')).toBe(false);
        expect(hrefWrites).toEqual(['/login']);
    });

    it('drains queued requests with a real Error when the refresh fails', async () => {
        // processQueue(null, undefined) used to reject every queued caller with `null`,
        // a falsy non-Error: `err.message` throws on it and no handler matches.
        const { instance } = await freshInstance({ token: 'stale', refreshToken: 'r1' });
        stubTransport(instance, (call) => (call.url === '/refresh-token' ? { status: 200, data: {} } : { status: 401 }));

        const settled = await Promise.allSettled([instance.get('/a'), instance.get('/b'), instance.get('/c')]);

        expect(settled.every((s) => s.status === 'rejected' && s.reason instanceof Error)).toBe(true);
    });

    it('rejects each queued caller with its own 401, not the refresh error', async () => {
        const { instance } = await freshInstance({ token: 'stale', refreshToken: 'r1' });
        stubTransport(instance, (call) => (call.url === '/refresh-token' ? { status: 500 } : { status: 401 }));

        const settled = await Promise.allSettled([instance.get('/a'), instance.get('/b'), instance.get('/c')]);

        const reasons = settled.map((s) => (s.status === 'rejected' ? s.reason : null));
        expect(reasons.map((r) => r?.config?.url)).toEqual(['/a', '/b', '/c']);
        expect(reasons.map((r) => r?.response?.status)).toEqual([401, 401, 401]);
        // why it failed is preserved rather than dropped
        expect(reasons.every((r) => r?.cause?.response?.status === 500)).toBe(true);
    });

    it('logs out exactly once when the refresh call itself 401s', async () => {
        // Defect 2 and the bug in #527: the refresh POST goes through this same
        // interceptor, so a 401 on it used to re-enter the refresh branch forever. It
        // reaches endSession() twice — short-circuit plus outer catch — so the redirect
        // is latched to a single navigation.
        const { instance, store, hrefWrites } = await freshInstance({ token: 'stale', refreshToken: 'expired' });
        const calls = stubTransport(instance, () => ({ status: 401 }));

        await expect(instance.get('/a')).rejects.toThrow();

        expect(countOf(calls, '/refresh-token')).toBe(1);
        expect(store.get('token')).toBeUndefined();
        expect(store.get('refreshToken')).toBeUndefined();
        expect(hrefWrites).toEqual(['/login']);
    });

    it('rejects the caller rather than hanging when the refresh fails', async () => {
        // The old catch redirected and fell through to the trailing reject, so callers did
        // settle; this pins that they still do now that the branch returns explicitly.
        const { instance } = await freshInstance({ token: 'stale', refreshToken: 'r1' });
        stubTransport(instance, (call) => (call.url === '/refresh-token' ? { status: 500 } : { status: 401 }));

        await expect(instance.get('/a')).rejects.toThrow();
    });

    it('logs out without calling refresh when no refresh token is stored', async () => {
        const { instance, location } = await freshInstance({ token: 'stale' });
        const calls = stubTransport(instance, () => ({ status: 401 }));

        await expect(instance.get('/a')).rejects.toThrow();

        expect(countOf(calls, '/refresh-token')).toBe(0);
        expect(location.href).toBe('/login');
    });

    it('passes non-401 failures straight through', async () => {
        const { instance, location } = await freshInstance({ token: 't', refreshToken: 'r1' });
        const calls = stubTransport(instance, () => ({ status: 500 }));

        await expect(instance.get('/a')).rejects.toThrow();

        expect(countOf(calls, '/refresh-token')).toBe(0);
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
