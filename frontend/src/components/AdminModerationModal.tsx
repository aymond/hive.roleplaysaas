import React, { useEffect, useRef, useState } from 'react';
import { ShieldAlert, Plus, Trash2, X, Check, FlaskConical } from 'lucide-react';
import { api } from '../api';
import type { ModerationPolicy } from '../types';

interface AdminModerationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AdminModerationModal: React.FC<AdminModerationModalProps> = ({
  isOpen,
  onClose,
}) => {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [policy, setPolicy] = useState<ModerationPolicy | null>(null);
  const [newWordInput, setNewWordInput] = useState('');
  const [newRegexInput, setNewRegexInput] = useState('');
  const [testInput, setTestInput] = useState('');
  const [testResult, setTestResult] = useState<{
    blocked: boolean;
    matched_terms: string[];
    sanitized_texts: string[];
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    if (isOpen && !dlg.open) {
      dlg.showModal();
      setError(null);
      api
        .getModerationPolicy()
        .then((p) => setPolicy(p))
        .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load policy'));
    } else if (!isOpen && dlg.open) {
      dlg.close();
    }
  }, [isOpen]);

  const handleAddWords = () => {
    if (!policy || !newWordInput.trim()) return;
    const incoming = newWordInput
      .split(',')
      .map((w) => w.trim())
      .filter(Boolean);
    const existing = new Set(policy.trigger_words.map((w) => w.toLowerCase()));
    const merged = [...policy.trigger_words];
    for (const w of incoming) {
      if (!existing.has(w.toLowerCase())) {
        merged.push(w);
        existing.add(w.toLowerCase());
      }
    }
    setPolicy({ ...policy, trigger_words: merged });
    setNewWordInput('');
  };

  const handleRemoveWord = (word: string) => {
    if (!policy) return;
    setPolicy({
      ...policy,
      trigger_words: policy.trigger_words.filter((w) => w !== word),
    });
  };

  const handleAddRegex = () => {
    if (!policy || !newRegexInput.trim()) return;
    if (!policy.regex_patterns.includes(newRegexInput.trim())) {
      setPolicy({
        ...policy,
        regex_patterns: [...policy.regex_patterns, newRegexInput.trim()],
      });
    }
    setNewRegexInput('');
  };

  const handleRemoveRegex = (pat: string) => {
    if (!policy) return;
    setPolicy({
      ...policy,
      regex_patterns: policy.regex_patterns.filter((p) => p !== pat),
    });
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!policy) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateModerationPolicy(policy);
      setPolicy(updated);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save policy');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!testInput.trim()) return;
    try {
      const res = await api.testModerationPolicy(testInput);
      setTestResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Test failed');
    }
  };

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      className="backdrop:bg-black/75 bg-[#0f131d] border border-white/15 text-slate-100 rounded-2xl max-w-2xl w-full p-0 m-auto shadow-2xl"
    >
      <div className="p-5 border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-emerald-500/15 border border-emerald-500/30">
            <ShieldAlert className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">
              Admin SFW Trigger-Word Moderation
            </h2>
            <p className="text-xs text-slate-400">
              Scans chat, scenes, character cards, and lore before calling any LLM or image API
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white cursor-pointer"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {policy ? (
        <form onSubmit={handleSave} className="p-5 space-y-4 max-h-[75vh] overflow-y-auto">
          {error && (
            <div className="p-2.5 rounded-lg bg-rose-500/15 border border-rose-500/40 text-xs text-rose-200">
              {error}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl bg-[#161b29] border border-white/10">
            <label className="flex items-center gap-2 text-xs font-semibold text-white cursor-pointer">
              <input
                type="checkbox"
                checked={policy.enabled}
                onChange={(e) => setPolicy({ ...policy, enabled: e.target.checked })}
              />
              Enable Pre-Flight Trigger-Word Detection
            </label>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Action:</span>
              <select
                value={policy.mode}
                onChange={(e) =>
                  setPolicy({ ...policy, mode: e.target.value as 'block' | 'redact' })
                }
                className="bg-[#0d111b] border border-white/15 rounded-lg px-2.5 py-1 text-xs text-white"
              >
                <option value="block">Block Request (HTTP 422)</option>
                <option value="redact">Redact Matched Words</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-xs font-bold uppercase tracking-wider text-emerald-300">
              Trigger Words ({policy.trigger_words.length})
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={newWordInput}
                onChange={(e) => setNewWordInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddWords();
                  }
                }}
                placeholder="Add word or comma-separated words..."
                className="flex-1 bg-[#161b29] border border-white/15 rounded-xl px-3 py-1.5 text-xs text-white"
              />
              <button
                type="button"
                onClick={handleAddWords}
                className="px-3 py-1.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-200 text-xs font-semibold flex items-center gap-1 cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5 p-2.5 rounded-xl bg-[#0b0e16] border border-white/10 max-h-36 overflow-y-auto">
              {policy.trigger_words.map((w) => (
                <span
                  key={w}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-500/15 border border-rose-500/30 text-[11px] text-rose-200"
                >
                  {w}
                  <button
                    type="button"
                    onClick={() => handleRemoveWord(w)}
                    className="hover:text-white cursor-pointer"
                    aria-label={`Remove ${w}`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
              Custom Regex Patterns ({policy.regex_patterns.length})
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={newRegexInput}
                onChange={(e) => setNewRegexInput(e.target.value)}
                placeholder="Optional regex pattern..."
                className="flex-1 bg-[#161b29] border border-white/15 rounded-xl px-3 py-1.5 text-xs font-mono text-white"
              />
              <button
                type="button"
                onClick={handleAddRegex}
                className="px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/15 text-xs text-white cursor-pointer"
              >
                Add Regex
              </button>
            </div>
            {policy.regex_patterns.length > 0 && (
              <div className="space-y-1">
                {policy.regex_patterns.map((pat) => (
                  <div
                    key={pat}
                    className="flex items-center justify-between px-2.5 py-1 rounded-lg bg-[#0b0e16] border border-white/10 text-[11px] font-mono text-slate-300"
                  >
                    <span>{pat}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveRegex(pat)}
                      className="text-slate-500 hover:text-rose-300 cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="p-3 rounded-xl bg-[#141824] border border-white/10 space-y-2">
            <div className="text-xs font-semibold text-cyan-300 flex items-center gap-1.5">
              <FlaskConical className="w-3.5 h-3.5" />
              Test Trigger-Word Scanner
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={testInput}
                onChange={(e) => setTestInput(e.target.value)}
                placeholder="Type sample chat, scene, or lore text..."
                className="flex-1 bg-[#0b0e16] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white"
              />
              <button
                type="button"
                onClick={handleTest}
                className="px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 text-cyan-200 text-xs font-semibold cursor-pointer"
              >
                Test
              </button>
            </div>
            {testResult && (
              <div className="text-[11px] text-slate-300">
                Status:{' '}
                <span className={testResult.blocked ? 'text-rose-400 font-bold' : 'text-emerald-400 font-bold'}>
                  {testResult.blocked
                    ? `BLOCKED (${testResult.matched_terms.join(', ')})`
                    : testResult.matched_terms.length > 0
                    ? `REDACTED (${testResult.matched_terms.join(', ')})`
                    : 'CLEAN (Allowed)'}
                </span>
              </div>
            )}
          </div>

          <div className="pt-2 border-t border-white/10 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs text-slate-300 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 cursor-pointer"
            >
              <Check className="w-4 h-4" />
              {saving ? 'Saving...' : 'Save Moderation Policy'}
            </button>
          </div>
        </form>
      ) : (
        <div className="p-6 text-xs text-slate-400">
          {error ? <span className="text-rose-300">{error}</span> : 'Loading moderation policy...'}
        </div>
      )}
    </dialog>
  );
};
