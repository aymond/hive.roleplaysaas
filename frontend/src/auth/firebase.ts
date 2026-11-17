// Lightweight GCP Identity Platform / Firebase Auth token store for SaaS mode.
// When VITE_FIREBASE_API_KEY is configured, the frontend stores the signed-in ID token here
// and api.ts automatically attaches `Authorization: Bearer <token>` on every API request.

const TOKEN_KEY = 'hivemind_id_token';

export function getAuthToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string | null): void {
  try {
    if (token) {
      window.localStorage.setItem(TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    // ignore storage errors
  }
}
