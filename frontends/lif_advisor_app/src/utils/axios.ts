import axios from 'axios';

const API_URL = import.meta.env.VITE_LIF_ADVISOR_API_URL;

const axiosInstance = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

axiosInstance.interceptors.request.use(
    (config) => {
        const accessToken = localStorage.getItem('token');
        if (accessToken) {
            config.headers.Authorization = `Bearer ${accessToken}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// A 401 from these is the endpoint's own answer, not a sign that our access token went
// stale, so neither may be refreshed and retried. They differ in what the answer means:
//
//   /login         -- "bad credentials". LoginPanel renders that itself, so the error has
//                     to reach it untouched. Ending the session here would navigate, and
//                     nginx try_files serves that as a full SPA reload, wiping both the
//                     message and the username the user typed.
//   /refresh-token -- "your refresh token is dead", so the session really is over. This is
//                     the branch that breaks the #527 loop: the refresh POST goes through
//                     this same interceptor, and without it a failing refresh re-enters
//                     the refresh branch forever.
//
// /logout is deliberately absent. It only 401s once the access token has already expired,
// and refreshing lets the retry reach the server so it can revoke the refresh token
// (refresh_tokens_store.pop in advisor_restapi). Exempting it would silently drop that.
const LOGIN_PATH = '/login';
const REFRESH_PATH = '/refresh-token';

let isRefreshing = false;
let failedQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = [];
let sessionEnded = false;

// Single exit point for "this session is over". #981 wants the redirect target changed
// from '/login' (a route the SPA does not actually define) to '/'; keeping every caller
// funnelled through here makes that a one-line change.
//
// Latched because a 401 on the refresh call reaches it twice -- once from the
// REFRESH_PATH short-circuit and again from the outer catch -- and assigning
// location.href a second time would ask the browser to navigate twice.
function endSession() {
    if (sessionEnded) {
        return;
    }
    sessionEnded = true;
    localStorage.removeItem('token');
    localStorage.removeItem('refreshToken');
    window.location.href = '/login';
}

/**
 * The request path as this interceptor matches it.
 *
 * Callers use relative paths, but the guards above are a correctness boundary rather than
 * a convenience, so tolerate an absolute URL, a query string, or a missing leading slash
 * instead of silently failing open on one.
 */
function pathOf(url: string | undefined): string {
    if (!url) {
        return '';
    }
    const path = url.replace(/^https?:\/\/[^/]+/i, '').split(/[?#]/)[0];
    return path.startsWith('/') ? path : `/${path}`;
}

/** Attach why the refresh failed to the error the caller actually receives. */
function withRefreshCause(error: unknown, refreshError: unknown): unknown {
    if (error && typeof error === 'object' && (error as Record<string, unknown>).cause === undefined) {
        (error as Record<string, unknown>).cause = refreshError;
    }
    return error;
}

function processQueue(refreshError: unknown, token: string | null) {
    failedQueue.forEach((prom) => {
        if (token) {
            prom.resolve(token);
        } else {
            // Each entry rejects with its own caller's 401 and takes this only as the
            // cause, so a queued caller can no longer be handed a falsy reason -- which
            // used to throw in any `err.message` handler and match no `instanceof Error`.
            prom.reject(refreshError);
        }
    });
    failedQueue = [];
}

axiosInstance.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        if (error.response?.status !== 401 || !originalRequest || originalRequest._retry) {
            return Promise.reject(error);
        }

        const path = pathOf(originalRequest.url);

        if (path === LOGIN_PATH) {
            return Promise.reject(error);
        }

        if (path === REFRESH_PATH) {
            endSession();
            return Promise.reject(error);
        }

        // Marked before queueing as well as on the direct path. A queued retry that 401s
        // again would otherwise re-enter this branch -- `finally` has already cleared
        // isRefreshing by the time it lands -- and start its own refresh, with its
        // siblings re-queued unmarked behind it. That is up to N refreshes and O(N^2)
        // retries per burst: a reduced form of the very storm this interceptor exists to
        // stop. (axios `mergeConfig` carries _retry through the retry, so the direct path
        // was already covered.)
        originalRequest._retry = true;

        if (isRefreshing) {
            return new Promise<string>((resolve, reject) => {
                // Reject with this caller's own 401 rather than the refresh's error, so
                // handlers reading error.response.status see the request they made.
                failedQueue.push({ resolve, reject: (refreshError) => reject(withRefreshCause(error, refreshError)) });
            }).then((token) => {
                originalRequest.headers.Authorization = `Bearer ${token}`;
                return axiosInstance(originalRequest);
            });
        }

        const refreshToken = localStorage.getItem('refreshToken');
        if (!refreshToken) {
            endSession();
            return Promise.reject(error);
        }

        isRefreshing = true;

        try {
            const response = await axiosInstance.post(REFRESH_PATH, { 'refresh_token': refreshToken });
            const newToken = response.data?.access_token;
            if (typeof newToken !== 'string' || !newToken) {
                // A 200 carrying no token is a failed refresh, not a successful one.
                // Storing it would put the string "undefined" in localStorage --
                // Storage.setItem coerces its value -- and that is truthy, so the request
                // interceptor would go on to send `Authorization: Bearer undefined`.
                throw new Error('Refresh response contained no access token');
            }
            localStorage.setItem('token', newToken);

            processQueue(null, newToken);

            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return axiosInstance(originalRequest);
        } catch (refreshError) {
            processQueue(refreshError, null);
            endSession();
            return Promise.reject(withRefreshCause(error, refreshError));
        } finally {
            isRefreshing = false;
        }
    }
);


export default axiosInstance;
