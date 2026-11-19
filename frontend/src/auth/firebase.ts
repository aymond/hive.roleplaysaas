// GCP Identity Platform / Firebase Auth + Local Session Store.
// Uses the official Firebase Auth SDK in SaaS mode for OAuth (Google, Apple, GitHub,
// custom OIDC such as Instagram/Meta) and Email/Password with automatic ID token refresh.

import { initializeApp, getApps, type FirebaseApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  GithubAuthProvider,
  OAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut as firebaseSignOut,
  onIdTokenChanged,
  type Auth,
} from 'firebase/auth';
import type { AuthConfig } from '../types';

const TOKEN_KEY = 'hivemind_id_token';
const MOCK_SESSION_KEY = 'hivemind_mock_session';

export interface MockAuthSession {
  uid: string;
  email: string;
}

export type OAuthProviderId = 'google' | 'apple' | 'github' | 'instagram';

let _firebaseApp: FirebaseApp | null = null;
let _firebaseAuth: Auth | null = null;
let _tokenListenerAttached = false;

export function ensureFirebaseAuth(config: AuthConfig): Auth {
  const apiKey =
    config.firebase_api_key ||
    (import.meta as any).env?.VITE_FIREBASE_API_KEY ||
    '';
  const authDomain =
    config.firebase_auth_domain ||
    (import.meta as any).env?.VITE_FIREBASE_AUTH_DOMAIN ||
    (config.firebase_project_id ? `${config.firebase_project_id}.firebaseapp.com` : '');
  const projectId =
    config.firebase_project_id ||
    (import.meta as any).env?.VITE_FIREBASE_PROJECT_ID ||
    '';

  if (!apiKey) {
    throw new Error('Firebase Web API key is not configured (FIREBASE_WEB_API_KEY).');
  }

  if (!_firebaseApp) {
    _firebaseApp = getApps()[0] || initializeApp({ apiKey, authDomain, projectId });
  }
  if (!_firebaseAuth) {
    _firebaseAuth = getAuth(_firebaseApp);
  }
  if (!_tokenListenerAttached && _firebaseAuth) {
    _tokenListenerAttached = true;
    onIdTokenChanged(_firebaseAuth, async (user) => {
      if (user) {
        const fresh = await user.getIdToken();
        setAuthToken(fresh);
      } else {
        setAuthToken(null);
      }
    });
  }
  return _firebaseAuth;
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
  if (_firebaseAuth) {
    firebaseSignOut(_firebaseAuth).catch(() => {});
  }
}

export async function signInWithOAuthProvider(
  config: AuthConfig,
  providerId: OAuthProviderId
): Promise<string> {
  const auth = ensureFirebaseAuth(config);
  let provider;
  switch (providerId) {
    case 'google':
      provider = new GoogleAuthProvider();
      break;
    case 'github':
      provider = new GithubAuthProvider();
      break;
    case 'apple':
      provider = new OAuthProvider('apple.com');
      provider.addScope('email');
      provider.addScope('name');
      break;
    case 'instagram':
      // Standard GCP Identity Platform OIDC provider ID for Instagram / Meta
      provider = new OAuthProvider('oidc.instagram');
      break;
  }
  const cred = await signInWithPopup(auth, provider);
  const token = await cred.user.getIdToken();
  setAuthToken(token);
  return token;
}

export async function signInWithEmailPassword(
  config: AuthConfig,
  email: string,
  password: string,
  isSignUp = false
): Promise<string> {
  const auth = ensureFirebaseAuth(config);
  const cred = isSignUp
    ? await createUserWithEmailAndPassword(auth, email.trim(), password)
    : await signInWithEmailAndPassword(auth, email.trim(), password);
  const token = await cred.user.getIdToken();
  setAuthToken(token);
  return token;
}
