import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Database, Loader2, RefreshCw, Satellite, XCircle } from "lucide-react";
import { Button, ErrorBanner, Panel, Pill, Spinner } from "../components/ui.jsx";
import { fmt, formatDateTime, hasRole, pct } from "../lib/format.js";
import { errorMessage, fetchAnalyses, fetchDataStatus, startAnalysis, startSync } from "../services/api.js";

const STATUS = {
  queued: { color: "#94a3b8", label: "En attente" },
  running: { color: "#2dd4bf", label: "En cours" },
  done: { color: "#3dff8a", label: "Terminée" },
  failed: { color: "#ff3b3b", label: "Échec" },
};

export default function AnalysesView({ user, communes, navigate, onChange }) {
  const [jobs, setJobs] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    fetchAnalyses().then((d) => { setJobs(d.jobs); setError(""); }).catch((err) => setError(errorMessage(err)));
    fetchDataStatus().then(setData).catch(() => {});
  }, []);
  const running = (jobs || []).some((j) => ["queued", "running"].includes(j.status));
  useEffect(() => { load(); }, [load]);
  // Follow-up: every 4 s while a job runs, every 30 s otherwise; nothing while the tab is hidden.
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState !== "hidden") load();
    }, running ? 4000 : 30000);
    const onVisible = () => { if (document.visibilityState === "visible") load(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load, running]);
  useEffect(() => {
    if (!running) onChange?.();
  }, [running]); // eslint-disable-line react-hooks/exhaustive-deps

  const launch = async (label, action) => {
    setBusy(label);
    setError("");
    try {
      await action();
      load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  };
  const lastJob = (code) => (jobs || []).find((j) => j.commune_code === code && j.kind === "commune");

  return (
    <div className="h-full space-y-4 overflow-y-auto p-4 text-xs">
      <div>
        <p className="text-[10px] uppercase tracking-[0.3em] text-tactical-cyan">Analyses</p>
        <h1 className="text-xl text-white">Analyses satellitaires et données ouvertes</h1>
        <p className="max-w-4xl text-slate-400">
          Une analyse de commune fusionne WSF Evolution (1985-2015), WSF 2019 (10 m) et une série annuelle Sentinel-2 calibrée sur WSF 2019, compte
          les bâtiments par carreau (empreintes Microsoft, aucune emprise conservée), charge les routes OpenStreetMap et les aires protégées, puis calcule
          la population par carreau et la veille. Durée : quelques minutes par commune.
        </p>
      </div>
      <ErrorBanner message={error} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_420px]">
        <Panel title="Communes" icon={Satellite}>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="text-[10px] uppercase tracking-wider text-slate-500">
                <tr><th className="py-1">Commune</th><th>Dernière analyse</th><th>Qualité (vs WSF 2019)</th><th className="text-right">Action</th></tr>
              </thead>
              <tbody>
                {communes.map((c) => {
                  const job = lastJob(c.code);
                  const active = job && ["queued", "running"].includes(job.status);
                  const calib = job?.summary?.calibration;
                  return (
                    <tr key={c.code} className="border-t border-tactical-line">
                      <td className="py-2">
                        <button type="button" className="text-left text-slate-100 hover:text-tactical-cyan" onClick={() => navigate("atlas", c.code)}>{c.nom}</button>
                        <span className="block text-[10px] text-slate-600">{fmt(c.population)} hab.</span>
                      </td>
                      <td>
                        {active ? (
                          <div className="w-48">
                            <p className="flex items-center gap-1 text-tactical-cyan"><Loader2 size={12} className="animate-spin" /> {job.progress} %</p>
                            <div className="mt-1 h-1 bg-tactical-line"><div className="h-1 bg-tactical-cyan" style={{ width: `${job.progress}%` }} /></div>
                            <p className="mt-1 truncate text-[10px] text-slate-500" title={job.message}>{job.message}</p>
                          </div>
                        ) : c.analysed_at ? (
                          <span className="text-slate-300">{formatDateTime(c.analysed_at)}</span>
                        ) : job?.status === "failed" ? (
                          <span className="text-tactical-red" title={job.message}>échec</span>
                        ) : <span className="text-slate-600">jamais</span>}
                      </td>
                      <td className="text-slate-400">
                        {calib ? (
                          <span title={job.summary.quality?.advice}>
                            <span style={{ color: { bonne: "#3dff8a", moyenne: "#f5c542", faible: "#ff8c1a" }[job.summary.quality?.level] }}>{job.summary.quality?.level || "—"}</span>
                            {` · concordance ${pct(calib.concordance)} · r ${fmt(calib.correlation, 2)}`}
                          </span>
                        ) : c.analysed_at ? "voir l'atlas" : "—"}
                      </td>
                      <td className="text-right">
                        {hasRole(user, "analyst") && (
                          <Button icon={Satellite} busy={busy === c.code} disabled={active} onClick={() => launch(c.code, () => startAnalysis(c.code, true))}>
                            {c.analysed_at ? "Mettre à jour" : "Analyser"}
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
        <div className="space-y-4">
          <Panel title="Données ouvertes" icon={Database} actions={hasRole(user, "analyst") && (
            <Button icon={RefreshCw} busy={busy === "sync"} onClick={() => launch("sync", startSync)}>Synchroniser</Button>
          )}>
            {!data ? <Spinner /> : (
              <>
                <ul className="space-y-1.5">
                  {data.sources.map((s) => (
                    <li key={s.id}>
                      <p className="text-slate-300">{s.label}</p>
                      <p className="text-[10px] text-slate-500">{fmt(s.values)} valeurs · {formatDateTime(s.retrieved_at)}</p>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[10px] text-slate-500">Synchronisation automatique tous les {data.refresh_days} jours (Administration › Paramètres).</p>
              </>
            )}
          </Panel>
          <Panel title="Journal des traitements" icon={RefreshCw}>
            {!jobs ? <Spinner /> : jobs.length === 0 ? <p className="text-slate-500">Aucun traitement.</p> : (
              <ul className="space-y-2">
                {jobs.slice(0, 20).map((j) => (
                  <li key={j.id} className="border-b border-tactical-line pb-1.5 last:border-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-slate-200">{j.kind === "sync" ? "Données ouvertes" : communes.find((c) => c.code === j.commune_code)?.nom || j.commune_code}</span>
                      <Pill color={STATUS[j.status]?.color}>{j.status === "done" ? <CheckCircle2 size={10} /> : j.status === "failed" ? <XCircle size={10} /> : null} {STATUS[j.status]?.label}</Pill>
                    </div>
                    <p className="text-[10px] text-slate-500">{formatDateTime(j.created_at)} · {j.created_by} · {j.message}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
