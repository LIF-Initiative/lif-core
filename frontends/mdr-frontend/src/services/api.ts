import axios from "axios";
import authService from "./authService";
import { isCognitoEnabled } from "../config/auth";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
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
