// GCP Identity Platform / Firebase Auth + Local Multi-Tenant Session Store.
// In SaaS mode (saas_auth_enabled=true), signs in via Identity Platform REST API
// and stores the JWT ID token (`Authorization: Bearer <token>`).
// In local mode (saas_auth_enabled=false), stores the active mock profile
// (`X-Mock-Uid` / `X-Mock-Role`) so User vs Admin & multi-tenant isolation can be tested.

const TOKEN_KEY = 'hivemind_id_token';
const MOCK_SESSION_KEY = 'hivemind_mock_session';

export interface MockAuthSession {
  uid: string;
  email: string;
}

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

export function getMockSession(): MockAuthSession | null {
  try {
    const raw = window.localStorage.getItem(MOCK_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.uid === 'string' && parsed.uid.trim()) {
      return {
        uid: parsed.uid.trim(),
        email: typeof parsed.email === 'string' ? parsed.email : `${parsed.uid.trim()}@localhost`,
      };
    }
    return null;
  } catch {
    return null;
  }
}

export function setMockSession(session: MockAuthSession | null): void {
  try {
    if (session) {
      window.localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify(session));
    } else {
      window.localStorage.removeItem(MOCK_SESSION_KEY);
    }
  } catch {
    // ignore storage errors
  }
}

export function clearAllAuthSessions(): void {
  setAuthToken(null);
  setMockSession(null);
}

export async function signInWithIdentityPlatform(
  apiKey: string,
  email: string,
  password: string,
  isSignUp = false
): Promise<string> {
  const endpoint = isSignUp
    ? `https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=${encodeURIComponent(apiKey)}`
    : `https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${encodeURIComponent(apiKey)}`;

  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: email.trim(),
      password,
      returnSecureToken: true,
    }),
  });
  const data = await res.json();
  if (!res.ok || !data?.idToken) {
    const msg = data?.error?.message || 'Authentication failed';
    throw new Error(msg);
  }
  setAuthToken(data.idToken);
  return data.idToken as string;
}
