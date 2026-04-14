/**
 * Cognito authentication configuration.
 *
 * All values are injected at build time via Vite environment variables.
 * When VITE_COGNITO_DOMAIN is not set, Cognito auth is disabled and
 * the app falls back to legacy username/password login.
 */

export const cognitoConfig = {
  domain: import.meta.env.VITE_COGNITO_DOMAIN as string | undefined,
  clientId: import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined,
  redirectUri: `${window.location.origin}/auth/callback`,
  logoutUri: `${window.location.origin}/login`,
  scopes: ["openid", "email", "profile"],
};

export const isCognitoEnabled =
  !!cognitoConfig.domain && !!cognitoConfig.clientId;
