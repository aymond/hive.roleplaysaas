import React, { useState } from 'react';
import { Sparkles, Shield, User, Lock, Mail, ArrowRight } from 'lucide-react';
import type { AuthConfig } from '../types';
import { setMockSession, signInWithIdentityPlatform } from '../auth/firebase';

interface LoginScreenProps {
  authConfig: AuthConfig;
  initialError?: string | null;
  onAuthenticated: () => void;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({
  authConfig,
  initialError,
  onAuthenticated,
}) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);

  // Local multi-tenant sandbox profile state (when saas_auth_enabled === false)
  const [localUid, setLocalUid] = useState('alice');
  const [localRole, setLocalRole] = useState<'user' | 'admin'>('user');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(initialError || null);

  const handleSaasSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return;
    const apiKey =
      authConfig.firebase_api_key ||
      (import.meta as any).env?.VITE_FIREBASE_API_KEY ||
      '';
    if (!apiKey) {
      setError('Firebase Web API key is not configured (FIREBASE_WEB_API_KEY / VITE_FIREBASE_API_KEY).');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await signInWithIdentityPlatform(apiKey, email, password, isSignUp);
      onAuthenticated();
    } catch (err: any) {
      setError(err?.message || 'Sign-in failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleLocalSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanUid = localUid.trim().toLowerCase().replace(/[^a-z0-9._-]/g, '-') || 'user';
    setMockSession({
      uid: cleanUid,
      email: `${cleanUid}@localhost`,
      role: localRole,
    });
    onAuthenticated();
  };

  const quickLocalLogin = (uid: string, role: 'user' | 'admin') => {
    setMockSession({
      uid,
      email: `${uid}@localhost`,
      role,
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
                : 'Multi-Tenant Studio Login'}
            </p>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-xs text-rose-200">
            {error}
          </div>
        )}

        {authConfig.saas_auth_enabled ? (
          <form onSubmit={handleSaasSubmit} className="space-y-4">
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
        ) : (
          <div className="space-y-5">
            <form onSubmit={handleLocalSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Account / Tenant ID
                </label>
                <input
                  type="text"
                  required
                  value={localUid}
                  onChange={(e) => setLocalUid(e.target.value)}
                  placeholder="e.g. alice, bob, or local-owner"
                  className="w-full bg-[#171c2b] border border-white/15 rounded-xl px-3 py-2 text-sm text-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Profile Type
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setLocalRole('user')}
                    className={`p-2.5 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer transition ${
                      localRole === 'user'
                        ? 'bg-amber-500/20 border-amber-500/60 text-amber-200'
                        : 'bg-[#171c2b] border-white/10 text-slate-400 hover:text-white'
                    }`}
                  >
                    <User className="w-3.5 h-3.5" />
                    Standard User
                  </button>
                  <button
                    type="button"
                    onClick={() => setLocalRole('admin')}
                    className={`p-2.5 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer transition ${
                      localRole === 'admin'
                        ? 'bg-emerald-500/20 border-emerald-500/60 text-emerald-200'
                        : 'bg-[#171c2b] border-white/10 text-slate-400 hover:text-white'
                    }`}
                  >
                    <Shield className="w-3.5 h-3.5" />
                    Administrator
                  </button>
                </div>
              </div>

              <button
                type="submit"
                className="w-full py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer"
              >
                Enter Studio
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>

            <div className="pt-4 border-t border-white/10 space-y-2">
              <p className="text-[11px] text-slate-400 font-medium">Quick Switch Profiles:</p>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => quickLocalLogin('alice', 'user')}
                  className="px-2.5 py-2 rounded-xl bg-[#171c2b] hover:bg-white/10 border border-white/10 text-[11px] text-slate-200 cursor-pointer"
                >
                  User: Alice
                </button>
                <button
                  type="button"
                  onClick={() => quickLocalLogin('bob', 'user')}
                  className="px-2.5 py-2 rounded-xl bg-[#171c2b] hover:bg-white/10 border border-white/10 text-[11px] text-slate-200 cursor-pointer"
                >
                  User: Bob
                </button>
                <button
                  type="button"
                  onClick={() => quickLocalLogin('local-owner', 'admin')}
                  className="px-2.5 py-2 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-[11px] text-emerald-200 cursor-pointer"
                >
                  Admin
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
