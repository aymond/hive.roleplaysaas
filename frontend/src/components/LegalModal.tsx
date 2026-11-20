import React, { useEffect, useRef, useState } from 'react';
import { LegalConfig } from '../types';

interface LegalModalProps {
  open: boolean;
  initialTab: 'privacy' | 'imprint';
  legal?: LegalConfig;
  onClose: () => void;
  onOpenConsentSettings?: () => void;
}

export const LegalModal: React.FC<LegalModalProps> = ({
  open,
  initialTab,
  legal,
  onClose,
  onOpenConsentSettings,
}) => {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState<'privacy' | 'imprint'>(initialTab);
  const [lang, setLang] = useState<'de' | 'en'>('de');

  useEffect(() => {
    setTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  if (!open) return null;

  const imprintName = legal?.imprint_name?.trim() || '';
  const imprintAddress = legal?.imprint_address?.trim() || '';
  const imprintEmail = legal?.imprint_email?.trim() || '';
  const imprintPhone = legal?.imprint_phone?.trim() || '';
  const privacyEmail = legal?.privacy_email?.trim() || imprintEmail;
  const region = legal?.region || 'europe-west4';
  const isImprintConfigured = Boolean(imprintName && imprintAddress && imprintEmail);

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      className="m-auto w-full max-w-3xl rounded-2xl border border-slate-700/80 bg-slate-950 p-0 text-slate-200 shadow-2xl backdrop:bg-black/75 backdrop:backdrop-blur-sm"
    >
      <div className="flex flex-col max-h-[85vh]">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setTab('privacy')}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === 'privacy'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              Datenschutzerklärung / Privacy Policy
            </button>
            <button
              type="button"
              onClick={() => setTab('imprint')}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === 'imprint'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              Impressum / Imprint
            </button>
          </div>

          <div className="flex items-center gap-2">
            {tab === 'privacy' && (
              <div className="flex rounded-lg border border-slate-800 bg-slate-900 p-0.5 text-[11px]">
                <button
                  type="button"
                  onClick={() => setLang('de')}
                  className={`rounded-md px-2 py-0.5 font-medium ${
                    lang === 'de' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  DE
                </button>
                <button
                  type="button"
                  onClick={() => setLang('en')}
                  className={`rounded-md px-2 py-0.5 font-medium ${
                    lang === 'en' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  EN
                </button>
              </div>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close legal modal"
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="overflow-y-auto px-6 py-5 text-xs leading-relaxed text-slate-300 space-y-4">
          {tab === 'imprint' ? (
            <div className="space-y-4">
              <h2 className="text-base font-semibold text-white">Impressum (Angaben gemäß § 5 DDG)</h2>
              {!isImprintConfigured && (
                <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-amber-200">
                  Hinweis für den Betreiber: Die Pflichtangaben (<code>IMPRINT_NAME</code>,{' '}
                  <code>IMPRINT_ADDRESS</code>, <code>IMPRINT_EMAIL</code>) sind noch nicht in der Laufzeitumgebung
                  konfiguriert.
                </div>
              )}
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-2">
                <div>
                  <span className="text-slate-400">Anbieter / Operator:</span>{' '}
                  <span className="text-white font-medium">{imprintName || 'Nicht konfiguriert / Not configured'}</span>
                </div>
                <div>
                  <span className="text-slate-400">Anschrift / Address:</span>{' '}
                  <span className="text-white">{imprintAddress || 'Nicht konfiguriert / Not configured'}</span>
                </div>
                <div>
                  <span className="text-slate-400">E-Mail:</span>{' '}
                  {imprintEmail ? (
                    <a href={`mailto:${imprintEmail}`} className="text-cyan-400 hover:underline">
                      {imprintEmail}
                    </a>
                  ) : (
                    <span className="text-slate-400">Nicht konfiguriert / Not configured</span>
                  )}
                </div>
                {imprintPhone && (
                  <div>
                    <span className="text-slate-400">Telefon / Phone:</span>{' '}
                    <span className="text-white">{imprintPhone}</span>
                  </div>
                )}
              </div>
              <p className="text-[11px] text-slate-400">
                Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV: {imprintName || 'Siehe Anbieterangaben oben'}.
              </p>
            </div>
          ) : lang === 'de' ? (
            <div className="space-y-4">
              <h2 className="text-base font-semibold text-white">Datenschutzerklärung (Art. 13 DSGVO &amp; § 25 TDDDG)</h2>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">1. Verantwortlicher</h3>
                <p>
                  Verantwortlicher im Sinne der DSGVO ist {imprintName || 'der Betreiber dieser Instanz'} (
                  {imprintAddress || 'Anschrift siehe Impressum'}). Datenschutz-Kontakt:{' '}
                  {privacyEmail ? (
                    <a href={`mailto:${privacyEmail}`} className="text-cyan-400 hover:underline">
                      {privacyEmail}
                    </a>
                  ) : (
                    'siehe Impressum'
                  )}
                  .
                </p>
              </section>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">2. Verarbeitete Daten &amp; Zwecke</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>
                    <strong>Kontodaten (Art. 6 Abs. 1 lit. b DSGVO):</strong> E-Mail-Adresse, Benutzer-ID (UID),
                    Anmeldezeitpunkt, Tarif- und Rollenstatus zur Bereitstellung Ihres Kontos.
                  </li>
                  <li>
                    <strong>Nutzungsinhalte (Art. 6 Abs. 1 lit. b DSGVO):</strong> Von Ihnen erstellte Welten,
                    Charaktere, Chat-Verläufe, Workflows sowie generierte Bilder. Rohe Chat- und Bild-Prompts werden im
                    SaaS-Betrieb nicht in Klartext-Serverlogs protokolliert.
                  </li>
                  <li>
                    <strong>Technische Zugriffsdaten (Art. 6 Abs. 1 lit. f DSGVO):</strong> Server-Metadaten (Zeitpunkt,
                    HTTP-Status, Fehlerdiagnose) zur Gewährleistung von Sicherheit und Stabilität.
                  </li>
                </ul>
              </section>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">3. Cookies &amp; lokaler Speicher (§ 25 TDDDG)</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>
                    <code>hm_token</code> (HttpOnly-Session-Cookie, SameSite=Lax): Unbedingt erforderlich für die
                    Authentifizierung (§ 25 Abs. 2 Nr. 2 TDDDG).
                  </li>
                  <li>
                    <code>hivemind_id_token</code> &amp; Firebase Auth Speicher (<code>localStorage</code>/IndexedDB):
                    Unbedingt erforderlich für den Anmeldestatus (§ 25 Abs. 2 Nr. 2 TDDDG).
                  </li>
                  <li>
                    <code>hivemind_consent_v1</code> (<code>localStorage</code>): Speicherung Ihrer
                    Einwilligungsentscheidung (§ 25 Abs. 2 Nr. 2 TDDDG).
                  </li>
                  <li>
                    <strong>Optionale Diagnose:</strong> Nur aktiv nach ausdrücklicher Einwilligung (Art. 6 Abs. 1 lit. a
                    DSGVO, § 25 Abs. 1 TDDDG) und jederzeit widerrufbar.
                  </li>
                </ul>
              </section>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">4. Empfänger, Hosting &amp; Drittlandtransfer</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>
                    <strong>Google Cloud Platform ({region}, EU):</strong> Cloud Run, Cloud Firestore und Cloud Storage
                    (GCS) zur Speicherung Ihrer Kontodaten und generierten Medien in der EU.
                  </li>
                  <li>
                    <strong>Google Identity Platform / Firebase Authentication:</strong> Authentifizierungsdienst für
                    Google-Login und E-Mail/Passwort-Anmeldung.
                  </li>
                  <li>
                    <strong>Google Vertex AI (Gemini &amp; Imagen):</strong> Verarbeitung Ihrer KI-Prompts zur Text- und
                    Bildgenerierung (global/US-Endpunkte möglich; abgesichert durch EU-US Data Privacy Framework und
                    Standardvertragsklauseln gemäß Art. 46 DSGVO).
                  </li>
                </ul>
              </section>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">5. Speicherdauer &amp; Löschung (Art. 17 DSGVO)</h3>
                <p>
                  Ihre Inhalte werden bis zur Löschung durch Sie gespeichert. Über das Kontomenü („Konto &amp; Daten
                  löschen“) können Sie jederzeit die vollständige Löschung Ihres Kontos, Ihrer Firestore-Daten und
                  Ihrer GCS-Medien auslösen. Technische Betriebslogs werden maximal 90 Tage aufbewahrt.
                </p>
              </section>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">6. Ihre Rechte (Art. 15–21, 77 DSGVO)</h3>
                <p>
                  Sie haben das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung,
                  Datenübertragbarkeit, Widerspruch sowie auf Beschwerde bei einer Datenschutzaufsichtsbehörde (Art. 77
                  DSGVO).
                </p>
              </section>
            </div>
          ) : (
            <div className="space-y-4">
              <h2 className="text-base font-semibold text-white">Privacy Policy (Art. 13 GDPR &amp; § 25 TDDDG)</h2>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">1. Data Controller</h3>
                <p>
                  The controller under GDPR is {imprintName || 'the operator of this instance'} (
                  {imprintAddress || 'see Imprint'}). Privacy contact:{' '}
                  {privacyEmail ? (
                    <a href={`mailto:${privacyEmail}`} className="text-cyan-400 hover:underline">
                      {privacyEmail}
                    </a>
                  ) : (
                    'see Imprint'
                  )}
                  .
                </p>
              </section>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">2. Categories of Data &amp; Legal Bases</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>
                    <strong>Account data (Art. 6(1)(b) GDPR):</strong> Email address, user ID (UID), login timestamps,
                    plan and role status to provide your account.
                  </li>
                  <li>
                    <strong>User content (Art. 6(1)(b) GDPR):</strong> Worlds, characters, chat histories, workflows,
                    and generated images. Raw chat and image prompts are redacted from server action logs in SaaS mode.
                  </li>
                  <li>
                    <strong>Technical access metadata (Art. 6(1)(f) GDPR):</strong> Request timestamps and status codes
                    for security and stability.
                  </li>
                </ul>
              </section>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">3. Cookies &amp; Local Storage (§ 25 TDDDG)</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>
                    <code>hm_token</code> (HttpOnly session cookie) &amp; <code>hivemind_id_token</code> / Firebase Auth
                    storage: Strictly necessary for authentication (§ 25(2) no. 2 TDDDG).
                  </li>
                  <li>
                    <code>hivemind_consent_v1</code> (<code>localStorage</code>): Strictly necessary to persist your
                    consent choice.
                  </li>
                  <li>
                    <strong>Optional diagnostics:</strong> Disabled by default; enabled only with your explicit consent
                    (Art. 6(1)(a) GDPR, § 25(1) TDDDG).
                  </li>
                </ul>
              </section>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">4. Sub-processors &amp; International Transfers</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>
                    <strong>Google Cloud Platform ({region}, EU):</strong> Cloud Run, Cloud Firestore, and Cloud Storage
                    for EU-hosted user workspaces and media.
                  </li>
                  <li>
                    <strong>Google Identity Platform / Firebase Authentication:</strong> Authentication provider.
                  </li>
                  <li>
                    <strong>Google Vertex AI (Gemini &amp; Imagen):</strong> AI text and image inference (may use global
                    endpoints safeguarded by the EU-US Data Privacy Framework and Standard Contractual Clauses under Art.
                    46 GDPR).
                  </li>
                </ul>
              </section>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">5. Retention &amp; Self-Service Erasure (Art. 17 GDPR)</h3>
                <p>
                  You can permanently delete your account, Firestore workspace, and GCS media at any time via the
                  Account menu (“Delete Account &amp; Data”). Operational logs are retained for up to 90 days.
                </p>
              </section>

              <section className="space-y-1">
                <h3 className="font-semibold text-slate-100">6. Your Rights</h3>
                <p>
                  You have the rights of access, rectification, erasure, restriction, data portability, objection (Art.
                  15–21 GDPR), and the right to lodge a complaint with a supervisory authority (Art. 77 GDPR).
                </p>
              </section>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-slate-800 px-6 py-3">
          {onOpenConsentSettings ? (
            <button
              type="button"
              onClick={() => {
                onClose();
                onOpenConsentSettings();
              }}
              className="text-xs text-cyan-400 hover:underline"
            >
              Cookie-Einstellungen ändern / Privacy Settings
            </button>
          ) : (
            <span />
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-slate-800 px-4 py-1.5 text-xs font-medium text-white hover:bg-slate-700 transition-colors"
          >
            Schließen / Close
          </button>
        </div>
      </div>
    </dialog>
  );
};
