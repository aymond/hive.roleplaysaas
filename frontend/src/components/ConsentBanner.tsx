import React, { useEffect, useState } from 'react';

export const CONSENT_STORAGE_KEY = 'hivemind_consent_v1';

export interface ConsentPreferences {
  version: number;
  essential: true;
  optionalDiagnostics: boolean;
  updatedAt: string;
}

export function readStoredConsent(): ConsentPreferences | null {
  try {
    const raw = localStorage.getItem(CONSENT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ConsentPreferences>;
    if (typeof parsed.optionalDiagnostics !== 'boolean') return null;
    return {
      version: 1,
      essential: true,
      optionalDiagnostics: parsed.optionalDiagnostics,
      updatedAt: parsed.updatedAt || new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

export function saveStoredConsent(optionalDiagnostics: boolean): ConsentPreferences {
  const prefs: ConsentPreferences = {
    version: 1,
    essential: true,
    optionalDiagnostics,
    updatedAt: new Date().toISOString(),
  };
  try {
    localStorage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore storage quota errors
  }
  return prefs;
}

interface ConsentBannerProps {
  open: boolean;
  onClose: () => void;
  onOpenLegal: (tab: 'privacy' | 'imprint') => void;
}

export const ConsentBanner: React.FC<ConsentBannerProps> = ({ open, onClose, onOpenLegal }) => {
  const [showSettings, setShowSettings] = useState(false);
  const [optionalDiagnostics, setOptionalDiagnostics] = useState(false);

  useEffect(() => {
    if (open) {
      const existing = readStoredConsent();
      setOptionalDiagnostics(existing ? existing.optionalDiagnostics : false);
      setShowSettings(false);
    }
  }, [open]);

  if (!open) return null;

  const handleEssentialOnly = () => {
    saveStoredConsent(false);
    onClose();
  };

  const handleAcceptAll = () => {
    saveStoredConsent(true);
    onClose();
  };

  const handleSaveSettings = () => {
    saveStoredConsent(optionalDiagnostics);
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-label="Cookie and Privacy Consent (§ 25 TDDDG / DSGVO)"
      className="fixed bottom-4 left-4 right-4 z-[90] mx-auto max-w-3xl rounded-2xl border border-slate-700/80 bg-slate-950/95 p-5 shadow-2xl backdrop-blur-md text-slate-200"
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-white">
              Datenschutz &amp; Einwilligung (§ 25 TDDDG / DSGVO)
            </h2>
            <p className="mt-1 text-xs leading-relaxed text-slate-300">
              Wir verwenden technisch notwendige Cookies und lokalen Speicher (<code>hm_token</code>,{' '}
              <code>hivemind_id_token</code>, <code>hivemind_consent_v1</code>) für Anmeldung, Sitzungsverwaltung und
              Ihre Einwilligungspräferenzen (§ 25 Abs. 2 Nr. 2 TDDDG). Optionale Diagnose- und Komfortfunktionen werden
              nur mit Ihrer ausdrücklichen Einwilligung (Art. 6 Abs. 1 lit. a DSGVO, § 25 Abs. 1 TDDDG) aktiviert.
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
              We use strictly necessary storage for authentication and consent state, and optional diagnostics only with
              your explicit consent.
            </p>
          </div>
        </div>

        {showSettings && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3 text-xs space-y-2.5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-medium text-slate-100">Technisch notwendig / Strictly Necessary</div>
                <div className="text-[11px] text-slate-400">
                  Authentifizierung (<code>hm_token</code>, Firebase Auth) &amp; Consent-Speicher (§ 25 Abs. 2 TDDDG).
                </div>
              </div>
              <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-500/30">
                Immer aktiv
              </span>
            </div>

            <label className="flex items-center justify-between gap-3 cursor-pointer pt-2 border-t border-slate-800">
              <div>
                <div className="font-medium text-slate-100">Optionale Diagnose &amp; Komfort / Optional Diagnostics</div>
                <div className="text-[11px] text-slate-400">
                  Optionale Client-Fehlerdiagnose und UI-Komfortfunktionen (Standard: Aus).
                </div>
              </div>
              <input
                type="checkbox"
                checked={optionalDiagnostics}
                onChange={(e) => setOptionalDiagnostics(e.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-950 text-cyan-500 focus:ring-cyan-500"
              />
            </label>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <button
              type="button"
              onClick={() => onOpenLegal('privacy')}
              className="underline decoration-slate-600 underline-offset-2 hover:text-cyan-400 transition-colors"
            >
              Datenschutzerklärung
            </button>
            <span aria-hidden="true">·</span>
            <button
              type="button"
              onClick={() => onOpenLegal('imprint')}
              className="underline decoration-slate-600 underline-offset-2 hover:text-cyan-400 transition-colors"
            >
              Impressum
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {showSettings ? (
              <button
                type="button"
                onClick={handleSaveSettings}
                className="rounded-lg border border-cyan-500/60 bg-cyan-500/15 px-3.5 py-2 text-xs font-medium text-cyan-200 hover:bg-cyan-500/25 transition-colors"
              >
                Auswahl speichern / Save
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setShowSettings(true)}
                className="rounded-lg border border-slate-700 bg-slate-900 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800 transition-colors"
              >
                Einstellungen / Settings
              </button>
            )}
            <button
              type="button"
              onClick={handleEssentialOnly}
              className="rounded-lg border border-slate-600 bg-slate-800 px-3.5 py-2 text-xs font-medium text-white hover:bg-slate-700 transition-colors"
            >
              Nur notwendige / Essential Only
            </button>
            <button
              type="button"
              onClick={handleAcceptAll}
              className="rounded-lg border border-slate-600 bg-slate-800 px-3.5 py-2 text-xs font-medium text-white hover:bg-slate-700 transition-colors"
            >
              Alle akzeptieren / Accept All
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
