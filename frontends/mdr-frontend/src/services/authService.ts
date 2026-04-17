import api from "./api";
import { cognitoConfig, isCognitoEnabled } from "../config/auth";
import { generateCodeVerifier, generateCodeChallenge } from "../utils/pkce";

// ---- Shared types ----

export interface UserDetails {
  email: string;
  name?: string;
  organization?: string;
  sub: string;
}

// ---- Legacy types (kept for transition) ----

export interface LoginCredentials {
  username: string;
  password: string;
}

interface LegacyLoginResponse {
  success: boolean;
  message: string;
  user: {
    username: string;
    firstname: string;
    lastname: string;
    identifier: string;
    identifier_type: string;
    identifier_type_enum: string;
  };
  access_token: string;
  refresh_token: string;
}

interface RefreshTokenResponse {
  access_token: string;
}

// ---- Storage keys ----

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";
const ID_TOKEN_KEY = "id_token";
const USER_KEY = "auth_user";
const PKCE_VERIFIER_KEY = "pkce_code_verifier";
const AUTH_RETURN_URL_KEY = "auth_return_url";

// ---- JWT helpers ----

function decodeJwtPayload(token: string): Record<string, unknown> {
  const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(atob(base64));
}

function isTokenExpired(token: string): boolean {
  try {
    const payload = decodeJwtPayload(token);
    return (payload.exp as number) <= Date.now() / 1000;
  } catch {
    return true;
  }
}

// ---- Cognito URL builders ----

function buildAuthorizeUrl(codeChallenge: string): string {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: cognitoConfig.clientId!,
    redirect_uri: cognitoConfig.redirectUri,
    scope: cognitoConfig.scopes.join(" "),
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
  });
  return `https://${cognitoConfig.domain}/oauth2/authorize?${params}`;
}

function buildLogoutUrl(): string {
  const params = new URLSearchParams({
    client_id: cognitoConfig.clientId!,
    logout_uri: cognitoConfig.logoutUri,
  });
  return `https://${cognitoConfig.domain}/logout?${params}`;
}

// ---- Token exchange ----

interface CognitoTokenResponse {
  id_token: string;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

async function exchangeCodeForTokens(code: string): Promise<CognitoTokenResponse> {
  const codeVerifier = sessionStorage.getItem(PKCE_VERIFIER_KEY);
  if (!codeVerifier) {
    throw new Error("PKCE code verifier not found — auth flow may have been interrupted");
  }

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: cognitoConfig.clientId!,
    redirect_uri: cognitoConfig.redirectUri,
    code,
    code_verifier: codeVerifier,
  });

  const response = await fetch(`https://${cognitoConfig.domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Token exchange failed: ${errorText}`);
  }

  sessionStorage.removeItem(PKCE_VERIFIER_KEY);
  return response.json();
}

async function refreshCognitoToken(refreshToken: string): Promise<CognitoTokenResponse> {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: cognitoConfig.clientId!,
    refresh_token: refreshToken,
  });

  const response = await fetch(`https://${cognitoConfig.domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!response.ok) {
    throw new Error("Cognito token refresh failed");
  }

  return response.json();
}

// ---- UserDetails extraction ----

function userDetailsFromCognitoToken(idToken: string): UserDetails {
  const payload = decodeJwtPayload(idToken);
  return {
    email: payload.email as string,
    name: (payload.name as string) || (payload.email as string),
    organization: payload["custom:organization"] as string | undefined,
    sub: payload.sub as string,
  };
}

function userDetailsFromLegacyUser(user: LegacyLoginResponse["user"]): UserDetails {
  return {
    email: user.username,
    name: `${user.firstname} ${user.lastname}`.trim() || user.username,
    sub: user.username,
  };
}

// ---- AuthService class ----

class AuthService {
  // ---- Cognito auth ----

  async loginWithCognito(returnUrl?: string): Promise<void> {
    const codeVerifier = generateCodeVerifier();
    const codeChallenge = await generateCodeChallenge(codeVerifier);

    sessionStorage.setItem(PKCE_VERIFIER_KEY, codeVerifier);
    if (returnUrl) {
      sessionStorage.setItem(AUTH_RETURN_URL_KEY, returnUrl);
    }

    window.location.assign(buildAuthorizeUrl(codeChallenge));
  }

  async handleCallback(code: string): Promise<UserDetails> {
    const tokens = await exchangeCodeForTokens(code);

    localStorage.setItem(ID_TOKEN_KEY, tokens.id_token);
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);

    const user = userDetailsFromCognitoToken(tokens.id_token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));

    // Set the ID token as the Bearer token for API calls
    api.defaults.headers.common["Authorization"] = `Bearer ${tokens.id_token}`;

    return user;
  }

  getReturnUrl(): string {
    const url = sessionStorage.getItem(AUTH_RETURN_URL_KEY) || "/";
    sessionStorage.removeItem(AUTH_RETURN_URL_KEY);
    return url;
  }

  // ---- Legacy auth (deprecated — kept for transition) ----

  async loginWithPassword(credentials: LoginCredentials): Promise<UserDetails> {
    const response = await api.post<LegacyLoginResponse>("/login", credentials);
    const loginData = response.data;

    localStorage.setItem(ACCESS_TOKEN_KEY, loginData.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, loginData.refresh_token);

    const user = userDetailsFromLegacyUser(loginData.user);
    localStorage.setItem(USER_KEY, JSON.stringify(user));

    api.defaults.headers.common["Authorization"] = `Bearer ${loginData.access_token}`;

    return user;
  }

  // ---- Common methods ----

  async logout(): Promise<void> {
    if (!isCognitoEnabled) {
      try {
        await api.post("/logout");
      } catch (error) {
        console.warn("Logout request failed:", error);
      }
    }

    this.clearTokens();

    if (isCognitoEnabled) {
      window.location.assign(buildLogoutUrl());
    }
  }

  async refreshToken(): Promise<boolean> {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!refreshToken) {
      console.warn("No refresh token found");
      this.clearTokens();
      return false;
    }

    try {
      if (isCognitoEnabled) {
        const tokens = await refreshCognitoToken(refreshToken);
        localStorage.setItem(ID_TOKEN_KEY, tokens.id_token);
        localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
        api.defaults.headers.common["Authorization"] = `Bearer ${tokens.id_token}`;
      } else {
        const response = await api.post<RefreshTokenResponse>("/refresh-token", {
          refresh_token: refreshToken,
        });
        localStorage.setItem(ACCESS_TOKEN_KEY, response.data.access_token);
        api.defaults.headers.common["Authorization"] = `Bearer ${response.data.access_token}`;
      }

      console.info("Successfully refreshed the user session");
      return true;
    } catch (error) {
      console.warn("Token refresh failed:", error);
      this.clearTokens();
      return false;
    }
  }

  getAccessToken(): string | null {
    // For Cognito, we send the ID token as the Bearer token (contains user claims)
    if (isCognitoEnabled) {
      return localStorage.getItem(ID_TOKEN_KEY);
    }
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  }

  isAuthenticated(): boolean {
    const token = this.getAccessToken();
    if (!token) return false;
    return !isTokenExpired(token);
  }

  getCurrentUser(): UserDetails | null {
    const userStr = localStorage.getItem(USER_KEY);
    return userStr ? JSON.parse(userStr) : null;
  }

  clearTokens(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(ID_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    delete api.defaults.headers.common["Authorization"];
  }

  initializeAuth(): void {
    const token = this.getAccessToken();
    if (token && !isTokenExpired(token)) {
      api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    } else {
      this.clearTokens();
    }
  }
}

export default new AuthService();
