import React, { useState } from 'react';
import { Sparkles, User, Lock, Mail, ArrowRight } from 'lucide-react';
import type { AuthConfig } from '../types';
import {
  setMockSession,
  signInWithEmailPassword,
  signInWithOAuthProvider,
  type OAuthProviderId,
} from '../auth/firebase';

interface LoginScreenProps {
  authConfig: AuthConfig;
  initialError?: string | null;
  onAuthenticated: () => void;
}

const PROVIDER_META: Record<
  OAuthProviderId,
  { label: string; badge: string }
> = {
  google: { label: 'Continue with Google', badge: 'G' },
  apple: { label: 'Continue with Apple', badge: '' },
  github: { label: 'Continue with GitHub', badge: 'GH' },
  instagram: { label: 'Continue with Instagram', badge: 'IG' },
};

export const LoginScreen: React.FC<LoginScreenProps> = ({
  authConfig,
  initialError,
  onAuthenticated,
}) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [localIdentity, setLocalIdentity] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(initialError || null);

  const enabledProviders = (
    authConfig.enabled_providers?.length ? authConfig.enabled_providers : ['google']
  ).filter((p): p is OAuthProviderId => p in PROVIDER_META);

  const handleOAuth = async (providerId: OAuthProviderId) => {
    setSubmitting(true);
    setError(null);
    try {
      await signInWithOAuthProvider(authConfig, providerId);
      onAuthenticated();
    } catch (err: any) {
      setError(err?.message || `Sign-in with ${providerId} failed`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSaasSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setSubmitting(true);
    setError(null);
    try {
      await signInWithEmailPassword(authConfig, email, password, isSignUp);
      onAuthenticated();
    } catch (err: any) {
      setError(err?.message || 'Sign-in failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleLocalSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const raw = localIdentity.trim().toLowerCase();
    if (!raw) {
      setError('Please enter your username or email');
      return;
    }
    const cleanUid = raw.replace(/[^a-z0-9.@_-]/g, '-');
    setMockSession({
      uid: cleanUid,
      email: cleanUid.includes('@') ? cleanUid : `${cleanUid}@localhost`,
    });
    onAuthenticated();
  };

  return (
    <div className="min-h-screen w-screen bg-[#090b10] text-slate-100 flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-[#0d1017] border border-white/10 rounded-3xl p-7 shadow-2xl space-y-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-amber-400 via-orange-500 to-violet-600 flex items-center justify-center shadow-lg shadow-amber-500/20">
            <Sparkles className="w-5 h-5 text-slate-950" />
          </div>
          <div>
            <h1 className="text-lg font-extrabold tracking-tight text-white">HIVEMIND STUDIO</h1>
            <p className="text-xs text-slate-400">
              {authConfig.saas_auth_enabled
                ? 'Sign in to your private workspace'
                : 'Sign in with your account'}
            </p>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-xs text-rose-200">
            {error}
          </div>
        )}

        {authConfig.saas_auth_enabled ? (
          <div className="space-y-4">
            {enabledProviders.length > 0 && (
              <div className="space-y-2">
                {enabledProviders.map((providerId) => {
                  const meta = PROVIDER_META[providerId];
                  return (
                    <button
                      key={providerId}
                      type="button"
                      disabled={submitting}
                      onClick={() => handleOAuth(providerId)}
                      className="w-full py-2.5 px-4 rounded-xl bg-[#171c2b] hover:bg-white/10 border border-white/15 text-sm font-semibold text-white flex items-center justify-center gap-2.5 cursor-pointer disabled:opacity-50 transition"
                    >
                      <span className="w-5 h-5 rounded-full bg-white/10 text-[11px] font-bold flex items-center justify-center text-amber-300">
                        {meta.badge}
                      </span>
                      {meta.label}
                    </button>
                  );
                })}
              </div>
            )}

            <div className="relative flex items-center py-1">
              <div className="flex-grow border-t border-white/10" />
              <span className="shrink mx-3 text-[11px] uppercase tracking-wider text-slate-500">
                or email
              </span>
              <div className="flex-grow border-t border-white/10" />
            </div>

            <form onSubmit={handleSaasSubmit} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">Email</label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full bg-[#171c2b] border border-white/15 rounded-xl pl-9 pr-3 py-2 text-sm text-white placeholder:text-slate-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">Password</label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                  <input
                    type="password"
                    required
                    minLength={6}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full bg-[#171c2b] border border-white/15 rounded-xl pl-9 pr-3 py-2 text-sm text-white placeholder:text-slate-500"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              >
                {submitting
                  ? 'Authenticating...'
                  : isSignUp
                  ? 'Create Account'
                  : 'Sign In'}
                <ArrowRight className="w-4 h-4" />
              </button>

              <div className="text-center pt-1">
                <button
                  type="button"
                  onClick={() => {
                    setIsSignUp(!isSignUp);
                    setError(null);
                  }}
                  className="text-xs text-slate-400 hover:text-amber-300 cursor-pointer"
                >
                  {isSignUp
                    ? 'Already have an account? Sign in'
                    : 'Need an account? Create one'}
                </button>
              </div>
            </form>
          </div>
        ) : (
          <form onSubmit={handleLocalSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Username or Email
              </label>
              <div className="relative">
                <User className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                <input
                  type="text"
                  required
                  value={localIdentity}
                  onChange={(e) => {
                    setLocalIdentity(e.target.value);
                    setError(null);
                  }}
                  placeholder="Enter your username or email"
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl pl-9 pr-3 py-2 text-sm text-white placeholder:text-slate-500"
                />
              </div>
            </div>

            <button
              type="submit"
              className="w-full py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer"
            >
              Sign In
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
