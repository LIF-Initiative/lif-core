import axios from "axios";
import authService from "./authService";

// The Learner Data Export (LDE) service is a separate host from the MDR API, so
// the export playground talks to it through its own axios instance. Auth is the
// signed-in user's Cognito access token — LDE accepts a Cognito JWT via its
// composite inbound auth (#1034). Requires VITE_LDE_API_URL at build time and
// LDE CORS to allow this frontend's origin.
const ldeApi = axios.create({
  baseURL: import.meta.env.VITE_LDE_API_URL,
  withCredentials: true,
});

ldeApi.interceptors.request.use((config) => {
  const token = authService.getAccessToken();
  if (token) {
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  return config;
});

export default ldeApi;
