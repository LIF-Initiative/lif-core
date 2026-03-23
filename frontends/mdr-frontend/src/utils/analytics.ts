/**
 * GA4 analytics utility. All calls are no-ops when gtag is not loaded
 * (i.e., when VITE_GA_MEASUREMENT_ID is not set).
 */

type GtagEventParams = Record<string, string | number | boolean>;

const MEASUREMENT_ID = import.meta.env.VITE_GA_MEASUREMENT_ID as string | undefined;

function loadGtag(): void {
  if (!MEASUREMENT_ID) return;

  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`;
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer || [];
  // Must use `arguments` (not rest params) — gtag.js checks for Arguments objects in dataLayer
  // eslint-disable-next-line prefer-rest-params
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag('js', new Date());
  window.gtag('config', MEASUREMENT_ID, { anonymize_ip: true });
}

// Initialize on module load
loadGtag();

function gtag(...args: unknown[]): void {
  if (typeof window.gtag === 'function') {
    window.gtag(...args);
  }
}

export function trackEvent(eventName: string, params?: GtagEventParams): void {
  gtag('event', eventName, params);
}

export function trackLogin(method: string): void {
  trackEvent('login', { method });
}

export function trackLoginFailed(method: string): void {
  trackEvent('login_failed', { method });
}

export function trackLogout(): void {
  trackEvent('logout');
}
