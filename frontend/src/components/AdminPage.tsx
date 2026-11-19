import React, { useEffect, useState, useCallback } from 'react';
import {
  Shield,
  Users,
  Search,
  RefreshCw,
  Trash2,
  Ban,
  CheckCircle2,
  Settings,
  ShieldAlert,
  User as UserIcon,
} from 'lucide-react';
import { api } from '../api';
import type { AdminUserRecord, UserProfile } from '../types';

interface AdminPageProps {
  currentUser: UserProfile;
  onOpenEngineSettings: () => void;
  onOpenModeration: () => void;
}

export const AdminPage: React.FC<AdminPageProps> = ({
  currentUser,
  onOpenEngineSettings,
  onOpenModeration,
}) => {
  const [users, setUsers] = useState<AdminUserRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busyUid, setBusyUid] = useState<string | null>(null);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.listAdminUsers();
      setUsers(list);
    } catch (err: any) {
      setError(err?.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleUpdateUser = async (
    uid: string,
    patch: { role?: 'user' | 'admin'; plan?: string; disabled?: boolean; credit_balance?: number }
  ) => {
    setBusyUid(uid);
    setError(null);
    try {
      const updated = await api.updateAdminUser(uid, patch);
      setUsers((prev) => prev.map((u) => (u.uid === uid ? updated : u)));
    } catch (err: any) {
      setError(err?.message || 'Update failed');
    } finally {
      setBusyUid(null);
    }
  };

  const handleDeleteUser = async (user: AdminUserRecord) => {
    if (
      !window.confirm(
        `Delete user "${user.email || user.uid}"? They will lose access to their account.`
      )
    ) {
      return;
    }
    setBusyUid(user.uid);
    setError(null);
    try {
      await api.deleteAdminUser(user.uid);
      setUsers((prev) => prev.filter((u) => u.uid !== user.uid));
    } catch (err: any) {
      setError(err?.message || 'Delete failed');
    } finally {
      setBusyUid(null);
    }
  };

  const filtered = users.filter((u) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      u.uid.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      u.role.toLowerCase().includes(q) ||
      u.plan.toLowerCase().includes(q)
    );
  });

  const adminCount = users.filter((u) => u.role === 'admin').length;
  const activeCount = users.filter((u) => !u.disabled).length;

  return (
    <div className="h-full w-full overflow-y-auto bg-[#090b10] p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header & Platform Controls */}
        <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-white/10">
          <div>
            <h1 className="text-xl font-bold text-white flex items-center gap-2">
              <Shield className="w-5 h-5 text-emerald-400" />
              Administration &amp; User Management
            </h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Manage user roles, account status, plans, and platform-wide engine &amp; safety policies.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onOpenModeration}
              className="px-3.5 py-2 rounded-xl bg-[#151a28] hover:bg-white/10 border border-white/15 text-xs font-semibold text-emerald-200 flex items-center gap-1.5 cursor-pointer"
            >
              <ShieldAlert className="w-4 h-4 text-emerald-400" />
              SFW Guard Policy
            </button>
            <button
              type="button"
              onClick={onOpenEngineSettings}
              className="px-3.5 py-2 rounded-xl bg-[#151a28] hover:bg-white/10 border border-white/15 text-xs font-semibold text-slate-200 flex items-center gap-1.5 cursor-pointer"
            >
              <Settings className="w-4 h-4 text-amber-400" />
              Inference Engines
            </button>
          </div>
        </div>

        {/* Summary KPIs */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-[#111520] border border-white/10 rounded-2xl p-4">
            <div className="text-xs text-slate-400">Total Registered Users</div>
            <div className="text-2xl font-extrabold text-white mt-1">{users.length}</div>
          </div>
          <div className="bg-[#111520] border border-white/10 rounded-2xl p-4">
            <div className="text-xs text-slate-400">Active Accounts</div>
            <div className="text-2xl font-extrabold text-emerald-400 mt-1">{activeCount}</div>
          </div>
          <div className="bg-[#111520] border border-white/10 rounded-2xl p-4">
            <div className="text-xs text-slate-400">Administrators</div>
            <div className="text-2xl font-extrabold text-amber-400 mt-1">{adminCount}</div>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-xs text-rose-200">
            {error}
          </div>
        )}

        {/* User Directory Table */}
        <div className="bg-[#111520] border border-white/10 rounded-2xl overflow-hidden">
          <div className="p-4 border-b border-white/10 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-bold text-white">
              <Users className="w-4 h-4 text-amber-400" />
              Users ({filtered.length})
            </div>

            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search email, uid, role..."
                  className="bg-[#171c2b] border border-white/15 rounded-xl pl-8 pr-3 py-1.5 text-xs text-white placeholder:text-slate-500 w-56"
                />
              </div>
              <button
                type="button"
                onClick={loadUsers}
                disabled={loading}
                className="p-2 rounded-xl bg-[#171c2b] hover:bg-white/10 border border-white/15 text-slate-300 cursor-pointer disabled:opacity-50"
                title="Refresh user list"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#0d1017] text-slate-400 border-b border-white/10">
                <tr>
                  <th className="px-4 py-3 font-semibold">User</th>
                  <th className="px-4 py-3 font-semibold">Role</th>
                  <th className="px-4 py-3 font-semibold">Plan</th>
                  <th className="px-4 py-3 font-semibold">Credits</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filtered.map((u) => {
                  const isSelf = u.uid === currentUser.uid;
                  const isBusy = busyUid === u.uid;
                  return (
                    <tr key={u.uid} className="hover:bg-white/[0.02]">
                      <td className="px-4 py-3">
                        <div className="font-semibold text-white flex items-center gap-1.5">
                          {u.email || u.uid}
                          {isSelf && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/30">
                              You
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-500 font-mono">{u.uid}</div>
                      </td>

                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                            u.role === 'admin'
                              ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                              : 'bg-white/5 text-slate-300 border-white/15'
                          }`}
                        >
                          {u.role === 'admin' ? (
                            <Shield className="w-3 h-3" />
                          ) : (
                            <UserIcon className="w-3 h-3" />
                          )}
                          {u.role}
                        </span>
                      </td>

                      <td className="px-4 py-3">
                        <select
                          value={u.plan}
                          disabled={isBusy}
                          onChange={(e) => handleUpdateUser(u.uid, { plan: e.target.value })}
                          className="bg-[#171c2b] border border-white/15 rounded-lg px-2 py-1 text-xs text-slate-200"
                        >
                          <option value="free">free</option>
                          <option value="pro">pro</option>
                          <option value="local">local</option>
                        </select>
                      </td>

                      <td className="px-4 py-3 font-mono text-slate-200">{u.credit_balance}</td>

                      <td className="px-4 py-3">
                        {u.disabled ? (
                          <span className="inline-flex items-center gap-1 text-rose-300 text-[11px] font-semibold">
                            <Ban className="w-3.5 h-3.5" />
                            Disabled
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-emerald-300 text-[11px] font-semibold">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Active
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex items-center gap-1.5">
                          <button
                            type="button"
                            disabled={isSelf || isBusy}
                            onClick={() =>
                              handleUpdateUser(u.uid, {
                                role: u.role === 'admin' ? 'user' : 'admin',
                              })
                            }
                            className="px-2.5 py-1 rounded-lg bg-[#171c2b] hover:bg-white/10 border border-white/15 text-[11px] text-slate-200 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                            title={
                              isSelf
                                ? 'Cannot change your own role'
                                : u.role === 'admin'
                                ? 'Demote to User'
                                : 'Promote to Admin'
                            }
                          >
                            {u.role === 'admin' ? 'Make User' : 'Make Admin'}
                          </button>

                          <button
                            type="button"
                            disabled={isSelf || isBusy}
                            onClick={() =>
                              handleUpdateUser(u.uid, { disabled: !u.disabled })
                            }
                            className={`px-2.5 py-1 rounded-lg border text-[11px] cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
                              u.disabled
                                ? 'bg-emerald-500/15 hover:bg-emerald-500/25 border-emerald-500/30 text-emerald-200'
                                : 'bg-amber-500/15 hover:bg-amber-500/25 border-amber-500/30 text-amber-200'
                            }`}
                            title={isSelf ? 'Cannot disable your own account' : u.disabled ? 'Enable account' : 'Disable account'}
                          >
                            {u.disabled ? 'Enable' : 'Disable'}
                          </button>

                          <button
                            type="button"
                            disabled={isSelf || isBusy}
                            onClick={() => handleDeleteUser(u)}
                            className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/25 border border-rose-500/25 text-rose-300 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                            title={isSelf ? 'Cannot delete your own account' : 'Delete user'}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {!loading && filtered.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                      No matching users found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
