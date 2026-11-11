import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import {
  Activity,
  BookOpen,
  CheckCircle2,
  Gauge,
  KeyRound,
  Loader2,
  Plug,
  Save,
  SlidersHorizontal,
  Trash2,
  Users,
  XCircle,
} from "lucide-react";
import {
  Button,
  ErrorBanner,
  Field,
  Panel,
  Pill,
  Spinner,
  Tabs,
  inputClass,
} from "../components/ui.jsx";
import SupervisionTab from "./SupervisionTab.jsx";
import UsersTab from "./UsersTab.jsx";
import { formatRelative } from "../lib/format.js";
import {
  errorMessage,
  fetchCatalogue,
  fetchKeys,
  fetchRuntimeSettings,
  fetchSystemHealth,
  saveKeys,
  saveRuntimeSettings,
  testService,
} from "../services/api.js";
import { HEALTH_COLORS } from "../theme.js";

// Large editor, loaded only when its tab is opened.
const CustomSourcesTab = lazy(() => import("./CustomSourcesTab.jsx"));

const TABS = [
  { id: "users", label: "Utilisateurs", icon: Users },
  { id: "settings", label: "Paramètres", icon: SlidersHorizontal },
  { id: "sources", label: "Sources de données", icon: BookOpen },
  { id: "custom", label: "Sources personnalisées", icon: Plug },
  { id: "keys", label: "Notifications", icon: KeyRound },
  { id: "supervision", label: "Supervision technique", icon: Gauge },
];

const CATALOGUE_STATUS = {
  "intégrée": "#3dff8a",
  "à brancher": "#2dd4bf",
  "clé requise": "#f5c542",
  "accès restreint": "#f5c542",
  "exclue": "#ff3b3b",
  "non diffusée": "#64748b",
};

function SourcesTab() {
  const [sources, setSources] = useState(null);
  const [health, setHealth] = useState(null);
  const [results, setResults] = useState({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(() => {
    fetchCatalogue().then((d) => setSources(d.sources)).catch((err) => setError(errorMessage(err)));
    fetchSystemHealth().then(setHealth).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);
  if (!sources) return error ? <ErrorBanner message={error} /> : <Spinner />;
  const categories = [...new Set(sources.map((s) => s.category))];
  const testable = new Set(health?.checks || []);
  const test = async (id) => {
    setBusy(id);
    try {
      const r = await testService(id);
      setResults((x) => ({ ...x, [id]: r }));
      load();
    } catch (err) {
      setResults((x) => ({ ...x, [id]: { ok: false, message: errorMessage(err) } }));
    } finally {
      setBusy("");
    }
  };
  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">
        Toutes les sources exploitées ou exploitables. Les sources intégrées sont ouvertes et sans clé ; les fournisseurs « clé requise » s&apos;activent
        dès que leur clé est saisie dans Paramètres › Clés API des sources ; les sources restreintes sont listées avec leur procédure d&apos;accès, à
        brancher via « Sources personnalisées » (WMS, WMTS, API JSON) une fois les droits obtenus.
      </p>
      <ErrorBanner message={error} />
      {categories.map((category) => (
        <Panel key={category} title={category} icon={BookOpen}>
          <ul className="space-y-2 text-xs">
            {sources.filter((s) => s.category === category).map((s) => {
              const live = s.live;
              const result = results[s.health];
              return (
                <li key={s.id} className="flex flex-wrap items-start justify-between gap-2 border-b border-tactical-line pb-2 last:border-0">
                  <div className="min-w-0 flex-1">
                    {s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="text-slate-100 hover:text-tactical-cyan">{s.name} ↗</a> : <span className="text-slate-100">{s.name}</span>}
                    <p className="text-slate-400">{s.usage}</p>
                    <p className="text-[10px] text-slate-600">Accès : {s.access} · Licence : {s.licence}</p>
                    {s.procedure && <p className="text-[10px] text-tactical-amber">Procédure : {s.procedure}</p>}
                    {live && (
                      <p className="text-[10px]" style={{ color: HEALTH_COLORS[live.status] }}>
                        {live.status} · dernier succès {live.last_success ? formatRelative(live.last_success) : "—"}{live.consecutive_failures ? ` · ${live.last_error}` : ""}
                      </p>
                    )}
                    {result && (
                      <p className={`flex items-center gap-1 text-[11px] ${result.ok ? "text-tactical-green" : "text-tactical-red"}`}>
                        {result.ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />} {result.message}{result.latency_ms ? ` (${result.latency_ms} ms)` : ""}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <Pill color={CATALOGUE_STATUS[s.status] || "#94a3b8"}>{s.status}</Pill>
                    {testable.has(s.health) && (
                      <Button icon={busy === s.health ? Loader2 : Activity} busy={busy === s.health} onClick={() => test(s.health)}>Tester</Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </Panel>
      ))}
    </div>
  );
}

function KeysTab() {
  const [keys, setKeys] = useState(null);
  const [draft, setDraft] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    fetchKeys().then((d) => setKeys(d.keys)).catch((err) => setError(errorMessage(err)));
  }, []);
  const run = async (label, action) => {
    setBusy(label);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  };
  if (!keys) return error ? <ErrorBanner message={error} /> : <Spinner />;
  const info = keys.alert_webhook_url || {};
  return (
    <div className="max-w-3xl space-y-4">
      <p className="text-xs text-slate-500">
        Le webhook de notification est un secret : chiffré au repos (clé maître hors base), jamais renvoyé au navigateur, chaque modification
        tracée. Les clés API des sources de données se règlent dans Paramètres › Clés API des sources.
      </p>
      <ErrorBanner message={error} />
      <Panel title="Webhook de notification (Slack / Mattermost / Teams)" icon={KeyRound}>
        <p className="mb-3 text-xs text-slate-500">
          Canaux : #veille (croissance loin des équipements), #analyses, #donnees, #decisions, #securite. « {"{channel}"} » ou « __CHANNEL__ » dans
          l&apos;URL est remplacé par le canal. PoC : serveur local http://notif-sink:8090/hooks/__CHANNEL__, consultable sur /notifs/.
        </p>
        <Field label={info.env} hint={info.configured ? `${info.hint} · ${info.origin === "dashboard" ? "coffre" : ".env"}` : "non configuré"}>
          <input className={inputClass} type="password" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={info.configured ? "Laisser vide pour conserver" : "https://…"}
            autoComplete="new-password" readOnly onFocus={(e) => { e.currentTarget.readOnly = false; }} spellCheck={false} />
        </Field>
        {result && (
          <p className={`mt-2 flex items-center gap-1 text-xs ${result.ok ? "text-tactical-green" : "text-tactical-red"}`}>
            {result.ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />} {result.message}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="primary" icon={Save} busy={busy === "save"} disabled={!draft.trim()} onClick={() => run("save", async () => {
            setKeys((await saveKeys({ alert_webhook_url: draft.trim() })).keys);
            setDraft("");
          })}>Enregistrer</Button>
          <Button icon={CheckCircle2} busy={busy === "test"} onClick={() => run("test", async () => setResult(await testService("webhook")))}>Envoyer un test sur chaque canal</Button>
          {info.origin === "dashboard" && (
            <Button icon={Trash2} busy={busy === "remove"} onClick={() => run("remove", async () => setKeys((await saveKeys({ alert_webhook_url: "" })).keys))}>Supprimer</Button>
          )}
        </div>
      </Panel>
    </div>
  );
}


const KEY_STATUS = {
  on: { color: "#3dff8a", label: "Active" },
  partial: { color: "#f5c542", label: "Incomplète" },
  off: { color: "#64748b", label: "Non configurée" },
};

// API keys of the data sources that accept one: write-only, encrypted at rest, applied without restart.
function SourceKeysSection() {
  const [keys, setKeys] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [results, setResults] = useState({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    fetchKeys().then((d) => setKeys(d.keys)).catch((err) => setError(errorMessage(err)));
  }, []);
  if (!keys) return error ? <ErrorBanner message={error} /> : <Spinner />;
  const groups = {};
  Object.entries(keys).forEach(([id, info]) => {
    if (info.kind === "source") (groups[info.service] ||= []).push([id, info]);
  });
  const run = async (label, action) => {
    setBusy(label);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  };
  return (
    <section className="space-y-3">
      <div>
        <h2 className="flex items-center gap-2 text-sm text-slate-100"><KeyRound size={14} className="text-tactical-cyan" /> Clés API des sources</h2>
        <p className="mt-1 max-w-3xl text-xs text-slate-500">
          Les sources intégrées fonctionnent sans clé ; une clé active un fournisseur de secours. Les valeurs sont chiffrées au repos, jamais
          renvoyées au navigateur (seuls les 4 derniers caractères sont rappelés), appliquées sans redémarrage et chaque modification est tracée.
          Une valeur du coffre remplace celle du fichier <code>.env</code> ; la supprimer rétablit celle-ci. Pour une autre API à clé, déclarez-la
          dans « Sources personnalisées ».
        </p>
      </div>
      <ErrorBanner message={error} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {Object.entries(groups).map(([service, fields]) => {
          const meta = fields[0][1];
          const count = fields.filter(([, info]) => info.configured).length;
          const status = KEY_STATUS[count === fields.length ? "on" : count ? "partial" : "off"];
          const pending = Object.fromEntries(fields.filter(([id]) => drafts[id]?.trim()).map(([id]) => [id, drafts[id].trim()]));
          const stored = fields.filter(([, info]) => info.origin === "dashboard").map(([id]) => id);
          const result = results[service];
          const clearDrafts = () => setDrafts((d) => Object.fromEntries(Object.entries(d).filter(([id]) => !fields.some(([f]) => f === id))));
          return (
            <Panel key={service} title={meta.provider} icon={KeyRound} actions={<Pill color={status.color}>{status.label}</Pill>}>
              {meta.usage && <p className="mb-3 text-xs text-slate-400">{meta.usage}</p>}
              <div className="space-y-2">
                {fields.map(([id, info]) => (
                  <Field key={id} label={`${info.label} · ${info.env}`}
                    hint={info.configured ? `${info.hint} · ${info.origin === "dashboard" ? "coffre" : ".env"}` : "non configuré"}>
                    <input className={inputClass} type={info.input === "text" ? "text" : "password"} value={drafts[id] || ""}
                      onChange={(e) => setDrafts((d) => ({ ...d, [id]: e.target.value }))}
                      placeholder={info.configured ? "Laisser vide pour conserver" : "Saisir la valeur"}
                      autoComplete="new-password" readOnly onFocus={(e) => { e.currentTarget.readOnly = false; }} spellCheck={false} />
                  </Field>
                ))}
              </div>
              {result && (
                <p className={`mt-2 flex items-center gap-1 text-xs ${result.ok ? "text-tactical-green" : "text-tactical-red"}`}>
                  {result.ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />} {result.message}{result.latency_ms ? ` (${result.latency_ms} ms)` : ""}
                </p>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button variant="primary" icon={Save} busy={busy === `save:${service}`} disabled={!Object.keys(pending).length}
                  onClick={() => run(`save:${service}`, async () => {
                    setKeys((await saveKeys(pending)).keys);
                    clearDrafts();
                    setResults((r) => ({ ...r, [service]: undefined }));
                  })}>Enregistrer</Button>
                <Button icon={Activity} busy={busy === `test:${service}`} disabled={!count}
                  onClick={() => run(`test:${service}`, async () => {
                    try {
                      const r = await testService(service);
                      setResults((x) => ({ ...x, [service]: r }));
                    } catch (err) {
                      setResults((x) => ({ ...x, [service]: { ok: false, message: errorMessage(err) } }));
                    }
                  })}>Tester</Button>
                {stored.length > 0 && (
                  <Button icon={Trash2} busy={busy === `remove:${service}`}
                    onClick={() => window.confirm(`Supprimer les clés ${meta.provider} enregistrées dans le coffre ?`) && run(`remove:${service}`, async () => {
                      setKeys((await saveKeys(Object.fromEntries(stored.map((id) => [id, ""])))).keys);
                      setResults((r) => ({ ...r, [service]: undefined }));
                    })}>Supprimer</Button>
                )}
                {meta.signup && (
                  <a href={meta.signup} target="_blank" rel="noreferrer" className="text-xs text-tactical-cyan underline">Obtenir une clé ↗</a>
                )}
              </div>
            </Panel>
          );
        })}
      </div>
    </section>
  );
}

function SettingsTab() {
  const [settings, setSettings] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetchRuntimeSettings().then((d) => setSettings(d.settings)).catch((err) => setError(errorMessage(err)));
  }, []);

  if (!settings) return error ? <ErrorBanner message={error} /> : <Spinner />;

  const save = async () => {
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      setSettings((await saveRuntimeSettings(drafts)).settings);
      setDrafts({});
      setSaved(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Sticky: the Apply button stays reachable while scrolling through the settings. */}
      <div className="sticky top-0 z-10 -mx-1 flex flex-wrap items-center justify-between gap-3 border-b border-tactical-line bg-tactical-bg/95 px-1 py-2 backdrop-blur">
        <p className="max-w-3xl text-xs text-slate-500">
          Ces réglages s&apos;appliquent immédiatement, sans redémarrage, et chaque modification est tracée dans l&apos;audit. Les rayons de
          desserte sont la norme locale de la commune : chaque résultat affiche le rayon utilisé.
        </p>
        <div className="flex items-center gap-3">
          <a href="/docs/administration/parametres/" target="_blank" rel="noopener" className="text-xs text-tactical-cyan underline">
            Guide des paramètres ↗
          </a>
          {saved && <span className="text-xs text-tactical-green">Paramètres appliqués et audités.</span>}
          {Object.keys(drafts).length > 0 && (
            <button type="button" onClick={() => setDrafts({})} className="text-xs text-slate-400 underline hover:text-white">
              Annuler les modifications
            </button>
          )}
          <Button variant="primary" icon={Save} busy={busy} disabled={!Object.keys(drafts).length} onClick={save}>
            Appliquer {Object.keys(drafts).length ? `(${Object.keys(drafts).length})` : ""}
          </Button>
        </div>
      </div>
      <SourceKeysSection />
      <h2 className="flex items-center gap-2 border-t border-tactical-line pt-4 text-sm text-slate-100">
        <SlidersHorizontal size={14} className="text-tactical-cyan" /> Paramètres opérationnels
      </h2>
      <ErrorBanner message={error} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {Object.entries(settings).map(([name, spec]) => {
          const value = drafts[name] ?? spec.value;
          const changed = name in drafts && drafts[name] !== spec.value;
          return (
            <Panel
              key={name}
              title={spec.label}
              icon={SlidersHorizontal}
              className={changed ? "ring-1 ring-tactical-amber" : ""}
              actions={
                value !== spec.default && (
                  <button type="button" onClick={() => setDrafts((d) => ({ ...d, [name]: spec.default }))} className="text-[10px] text-slate-500 underline hover:text-white">
                    défaut ({spec.default})
                  </button>
                )
              }
            >
              <div className="flex items-center gap-3">
                <input
                  className={`${inputClass} w-32`}
                  type="number"
                  step={spec.type === "int" ? 1 : 0.05}
                  min={spec.min}
                  max={spec.max}
                  value={value}
                  onChange={(e) => setDrafts((d) => ({ ...d, [name]: e.target.value === "" ? "" : Number(e.target.value) }))}
                  aria-label={spec.label}
                />
                <span className="text-xs text-slate-500">
                  {spec.unit} · plage {spec.min} – {spec.max}
                </span>
              </div>
              <dl className="mt-3 space-y-2 text-xs">
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-slate-500">Rôle</dt>
                  <dd className="text-slate-300">{spec.what}</dd>
                </div>
                {(spec.higher || spec.lower) && (
                  <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                    <div className="border-l-2 border-tactical-cyan/50 pl-2">
                      <dt className="text-[10px] uppercase tracking-wider text-tactical-cyan">▲ Augmenter</dt>
                      <dd className="text-slate-400">{spec.higher}</dd>
                    </div>
                    <div className="border-l-2 border-tactical-amber/50 pl-2">
                      <dt className="text-[10px] uppercase tracking-wider text-tactical-amber">▼ Diminuer</dt>
                      <dd className="text-slate-400">{spec.lower}</dd>
                    </div>
                  </div>
                )}
                <div>
                  <dt className="text-[10px] uppercase tracking-wider text-slate-500">Recommandation</dt>
                  <dd className="text-slate-300">{spec.advice}</dd>
                </div>
              </dl>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}


export default function AdminView({ user }) {
  const [tab, setTab] = useState("users");
  return (
    <div className="flex h-full flex-col">
      <Tabs tabs={TABS} value={tab} onChange={setTab} label="Administration" />
      <div className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-4">
        {tab === "users" && <UsersTab user={user} />}
        {tab === "settings" && <SettingsTab />}
        {tab === "sources" && <SourcesTab />}
        {tab === "custom" && (<Suspense fallback={<Spinner />}><CustomSourcesTab /></Suspense>)}
        {tab === "keys" && <KeysTab />}
        {tab === "supervision" && <SupervisionTab />}
      </div>
    </div>
  );
}
