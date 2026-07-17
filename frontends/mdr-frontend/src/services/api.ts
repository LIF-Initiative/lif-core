import axios from "axios";
import authService from "./authService";
import { isCognitoEnabled } from "../config/auth";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  // Send/accept cookies on cross-origin requests. The MDR API issues the
  // `lif_workspace` selection cookie via Set-Cookie on /tenants/select;
  // without `withCredentials` the browser won't persist or replay it when
  // VITE_API_URL is a different origin (the common case — frontend on a
  // dev server, backend on docker-compose). Requires the backend's CORS
  // config to set Access-Control-Allow-Credentials: true and an explicit
  // origin (not "*"), which the MDR API already does.
  withCredentials: true,
  // Fail a stalled request instead of hanging indefinitely. Without a timeout, a request
  // whose response is lost hangs until the browser/OS gives up, surfacing as an ambiguous
  // "Network error" — the trigger for the orphaned-attribute class of bugs (#1028).
  timeout: 30000,
});

// Add a response interceptor to handle token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      console.warn("Received a 401 error. Trying to refresh the user session");

      try {
        const refreshed = await authService.refreshToken();

        if (refreshed) {
          originalRequest.headers["Authorization"] = `Bearer ${authService.getAccessToken()}`;
          return api(originalRequest);
        }
      } catch (refreshError) {
        console.error("Token refresh failed, redirecting to login");
      }

      authService.clearTokens();

      if (isCognitoEnabled) {
        // For Cognito, re-trigger the full login flow
        authService.loginWithCognito(window.location.pathname);
      } else {
        window.location.href = "/login";
      }
    }

    return Promise.reject(error);
  }
);

export default api;
