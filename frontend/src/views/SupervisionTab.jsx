import { useCallback, useEffect, useState } from "react";
import { Activity, Database, Gauge, HardDrive, RefreshCw, Satellite, Timer } from "lucide-react";
import { Button, ErrorBanner, Panel, Spinner } from "../components/ui.jsx";
import { fmt, formatDateTime, formatBytes } from "../lib/format.js";
import { errorMessage, fetchSupervision } from "../services/api.js";
import { HEALTH_COLORS } from "../theme.js";

function Tile({ label, value, hint, state = "ok" }) {
  const color = { ok: "#3dff8a", warn: "#f5c542", bad: "#ff3b3b", off: "#64748b" }[state];
  return (
    <div className="border border-tactical-line p-3" style={{ borderLeft: `3px solid ${color}` }}>
      <p className="text-[10px] uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-lg text-white">{value}</p>
      {hint && <p className="text-[10px] text-slate-500">{hint}</p>}
    </div>
  );
}

const age = (s) => (s == null ? "—" : s < 120 ? `${s} s` : s < 7200 ? `${Math.round(s / 60)} min` : s < 172800 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} j`);

export default function SupervisionTab() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => fetchSupervision().then((d) => { setData(d); setError(""); }).catch((err) => setError(errorMessage(err))), []);
  useEffect(() => {
    load();
    const timer = setInterval(() => { if (document.visibilityState !== "hidden") load(); }, 15000);
    return () => clearInterval(timer);
  }, [load]);
  if (!data) return error ? <ErrorBanner message={error} /> : <Spinner />;
  const down = data.sources.filter((s) => s.status === "down").length;
  const p95 = data.api[0]?.p95_ms;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-slate-500">Tableau local (aucun appel externe) · généré en {data.built_in_ms} ms · processus démarré le {formatDateTime(data.process_started_at)} · mode {data.background_mode}</p>
        <Button icon={RefreshCw} onClick={load}>Actualiser</Button>
      </div>
      <ErrorBanner message={error} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Sources externes" value={`${data.sources.length - down}/${data.sources.length} disponibles`} state={down ? "bad" : data.sources.length ? "ok" : "off"} hint="santé vue par les appels récents" />
        <Tile label="Analyses" value={`${data.jobs.running} en cours`} hint={`durée moyenne ${data.jobs.average_duration_s ? `${Math.round(data.jobs.average_duration_s / 60)} min` : "—"} · ${data.jobs.failed_recent} échec(s) récents`} state={data.jobs.failed_recent ? "warn" : "ok"} />
        <Tile label="API — p95 le plus lent" value={p95 != null ? `${p95} ms` : "—"} hint={data.api[0]?.area} state={p95 == null ? "off" : p95 > 3000 ? "warn" : "ok"} />
        <Tile label="Disque libre" value={formatBytes(data.disk.free_bytes)} hint={`sur ${formatBytes(data.disk.total_bytes)}`} state={data.disk.free_bytes != null && data.disk.free_bytes < 2e9 ? "warn" : "ok"} />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel title="Sources externes" icon={Activity}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <tbody>
                {data.sources.map((s) => (
                  <tr key={s.source} className="border-t border-tactical-line">
                    <td className="py-1.5 text-slate-200">{s.source}</td>
                    <td style={{ color: HEALTH_COLORS[s.status] }}>{s.status}</td>
                    <td className="text-slate-500">succès il y a {age(s.success_age_s)}</td>
                    <td className="text-slate-500">{s.consecutive_failures ? `${s.consecutive_failures} échec(s) · ${s.last_error}` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.sources.length === 0 && <p className="text-xs text-slate-500">Aucun appel externe depuis le démarrage.</p>}
        </Panel>
        <Panel title="Analyses récentes" icon={Satellite}>
          <ul className="space-y-1 text-xs">
            {data.jobs.recent.map((j) => (
              <li key={j.id} className="flex justify-between gap-2 border-t border-tactical-line pt-1">
                <span className="text-slate-300">#{j.id} {j.kind} {j.commune_code}</span>
                <span className="truncate text-slate-500" title={j.message}>{j.status} · {formatDateTime(j.finished_at || j.created_at)}</span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Temps de réponse de l'API" icon={Timer}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] uppercase text-slate-500"><tr><th>Domaine</th><th className="text-right">Requêtes</th><th className="text-right">p50</th><th className="text-right">p95</th><th className="text-right">Erreurs</th></tr></thead>
              <tbody>
                {data.api.map((a) => (
                  <tr key={a.area} className="border-t border-tactical-line">
                    <td className="py-1">{a.area}</td><td className="text-right">{a.requests}</td><td className="text-right">{a.p50_ms} ms</td><td className="text-right">{a.p95_ms} ms</td><td className="text-right">{a.errors}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel title="Base de données et stockage" icon={Database}>
          <p className="mb-2 text-xs text-slate-400">{data.database.engine} · {formatBytes(data.database.size_bytes)}</p>
          <dl className="grid grid-cols-2 gap-1 text-xs">
            {Object.entries(data.database.rows).map(([t, n]) => (
              <div key={t} className="flex justify-between border-b border-tactical-line py-0.5"><dt className="text-slate-500">{t}</dt><dd>{n == null ? "—" : fmt(n)}</dd></div>
            ))}
          </dl>
          <p className="mt-3 flex items-center gap-1 text-xs text-slate-500"><HardDrive size={12} /> cache {formatBytes(data.disk.cache)} · données {formatBytes(data.disk.data)} · sauvegardes {formatBytes(data.disk.backups)}</p>
          <p className="mt-1 flex items-center gap-1 text-[10px] text-slate-600"><Gauge size={11} /> Fraîcheur : {Object.entries(data.data).map(([k, v]) => `${k} ${formatDateTime(v.retrieved_at)}`).join(" · ") || "—"}</p>
        </Panel>
      </div>
    </div>
  );
}
