import { useCallback, useEffect, useState } from "react";
import { Building2, FileSignature, Info, LineChart as ChartIcon, Map as MapIcon, Satellite, Target, Users } from "lucide-react";
import { Bars, Compare, LineChart } from "../components/Charts.jsx";
import { Button, ErrorBanner, Field, Panel, Spinner, inputClass } from "../components/ui.jsx";
import { fmt, hasRole, pct } from "../lib/format.js";
import { deleteHypothesis, errorMessage, fetchCommune, fetchCoverage, fetchGridMeta, saveHypothesis } from "../services/api.js";
import { CATEGORY } from "../theme.js";
import ReportDialog from "./ReportDialog.jsx";

function KpiCard({ k }) {
  return (
    <div className="border border-tactical-line bg-tactical-bg/40 p-3" title={`${k.formula}\nSource : ${k.sources.join(" ; ")}`}>
      <p className="text-[11px] leading-tight text-slate-400">{k.label}</p>
      <p className="mt-1 text-xl tabular-nums text-white">
        {k.value != null ? fmt(k.value, k.decimals) : "—"} <span className="text-[11px] text-slate-500">{k.unit}</span>
      </p>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-1 text-[10px] text-slate-500">
        <span>{k.year || "—"} · Guyane {k.guyane != null ? fmt(k.guyane, k.decimals) : "—"}</span>
        {k.rank && <span title="Rang parmi les 22 communes">{k.rank}/{k.ranked}</span>}
      </div>
      <Compare value={k.value} reference={k.guyane} better={k.better} />
    </div>
  );
}

function HypothesisPanel({ commune, hypothesis, legal, canEdit, onSaved }) {
  const [form, setForm] = useState(() => ({ year: new Date().getFullYear(), value: "", low: "", high: "", source: "", note: "", ...(hypothesis || {}),
    ...(hypothesis ? { low: hypothesis.low ?? "", high: hypothesis.high ?? "", source: hypothesis.source || "", note: hypothesis.note || "" } : {}) }));
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await saveHypothesis(commune, {
        ...form, year: Number(form.year), value: Number(form.value),
        low: form.low ? Number(form.low) : null, high: form.high ? Number(form.high) : null,
      });
      setOpen(false);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!window.confirm("Retirer l'estimation communale ? Les analyses utilisant l'hypothèse reviendront à la population légale INSEE.")) return;
    setBusy(true);
    setError("");
    try {
      await deleteHypothesis(commune);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Population : chiffre officiel et estimation communale" icon={Users}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="border-l-2 border-tactical-cyan pl-3">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">Population légale INSEE</p>
          <p className="text-2xl tabular-nums text-white">{legal ? fmt(legal.value) : "—"}</p>
          <p className="text-[10px] text-slate-500">millésime {legal?.year} (en vigueur au 1er janvier {legal ? legal.year + 3 : ""})</p>
        </div>
        <div className="border-l-2 border-tactical-amber pl-3">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">Estimation de la commune</p>
          {hypothesis ? (
            <>
              <p className="text-2xl tabular-nums text-tactical-amber">{fmt(hypothesis.value)}</p>
              <p className="text-[10px] text-slate-500">
                {hypothesis.year}{hypothesis.low ? ` · fourchette ${fmt(hypothesis.low)} – ${fmt(hypothesis.high)}` : ""} · {hypothesis.source || "source non précisée"}
              </p>
            </>
          ) : (
            <p className="text-xs text-slate-500">Aucune hypothèse saisie.</p>
          )}
        </div>
      </div>
      <p className="mt-3 text-[11px] text-slate-500">
        L&apos;estimation communale n&apos;est jamais substituée au chiffre officiel : elle peut servir d&apos;hypothèse explicite dans les analyses
        (option « hypothèse communale »), toujours nommée comme telle.
      </p>
      {canEdit && !open && (
        <div className="mt-2 flex gap-2">
          <Button onClick={() => setOpen(true)}>{hypothesis ? "Modifier l'hypothèse" : "Saisir une hypothèse"}</Button>
          {hypothesis && <Button variant="danger" busy={busy} onClick={remove}>Retirer</Button>}
        </div>
      )}
      {!open && <div className="mt-2"><ErrorBanner message={error} /></div>}
      {open && (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Field label="Année"><input className={inputClass} type="number" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} /></Field>
          <Field label="Habitants"><input className={inputClass} type="number" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} /></Field>
          <Field label="Source"><input className={inputClass} value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder="ex. estimation mairie" /></Field>
          <Field label="Bas de fourchette"><input className={inputClass} type="number" value={form.low || ""} onChange={(e) => setForm({ ...form, low: e.target.value })} /></Field>
          <Field label="Haut de fourchette"><input className={inputClass} type="number" value={form.high || ""} onChange={(e) => setForm({ ...form, high: e.target.value })} /></Field>
          <div className="flex items-end gap-2">
            <Button variant="primary" busy={busy} onClick={save} disabled={!form.value}>Enregistrer</Button>
            <Button onClick={() => setOpen(false)}>Annuler</Button>
          </div>
          <div className="sm:col-span-3"><ErrorBanner message={error} /></div>
        </div>
      )}
    </Panel>
  );
}

export default function CommuneView({ user, commune, communeName, navigate }) {
  const [data, setData] = useState(null);
  const [meta, setMeta] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [theme, setTheme] = useState("demographie");
  const [error, setError] = useState("");
  const [report, setReport] = useState(false);

  const load = useCallback(() => {
    setError("");
    fetchCommune(commune).then(setData).catch((err) => setError(errorMessage(err)));
    fetchGridMeta(commune).then(setMeta).catch(() => setMeta(null));
    fetchCoverage(commune).then(setCoverage).catch(() => setCoverage(null));
  }, [commune]);
  useEffect(() => { load(); }, [load]);

  if (error) return <div className="p-4"><ErrorBanner message={error} /></div>;
  if (!data) return <Spinner label={`Chargement de ${communeName}…`} />;
  const c = data.commune;
  const current = data.themes.find((t) => t.id === theme) || data.themes[0];
  const popSeries = data.series.population || [];
  const legal = popSeries.length ? { value: popSeries[popSeries.length - 1].value, year: popSeries[popSeries.length - 1].year } : null;
  const model = meta?.population?.available ? meta.population.series : null;
  const breakInfo = meta?.builtup?.series_break;

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.3em] text-tactical-cyan">{c.epci}</p>
          <h1 className="text-2xl text-white">{c.nom}</h1>
          <p className="text-xs text-slate-500">
            Code INSEE {c.code} · {fmt((c.surface_ha || 0) / 100)} km² · contours {c.source}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button icon={MapIcon} onClick={() => navigate("atlas", commune)}>Atlas</Button>
          <Button icon={Target} onClick={() => navigate("decision", commune)}>Aide à l&apos;implantation</Button>
          {hasRole(user, "analyst") && <Button icon={FileSignature} variant="primary" onClick={() => setReport(true)}>Diagnostic signé</Button>}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-1 border-b border-tactical-line">
            {data.themes.map((t) => (
              <button key={t.id} type="button" onClick={() => setTheme(t.id)}
                className={`border-b-2 px-3 py-2 text-xs ${theme === t.id ? "border-tactical-cyan text-tactical-cyan" : "border-transparent text-slate-400 hover:text-white"}`}>
                {t.label}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-3">
            {current.kpis.map((k) => <KpiCard key={k.id} k={k} />)}
          </div>

          <Panel title="Population : recensement et bâti mesuré par satellite" icon={ChartIcon}>
            <LineChart
              series={[
                { id: "insee", label: "Population municipale légale (INSEE)", color: "#2dd4bf", points: popSeries.map((p) => ({ x: p.year, y: p.value })) },
                ...(model ? [{ id: "model", label: "Population que le bâti pourrait loger (occupation constante, estimation)", color: "#f5c542", dashed: true,
                  points: model.filter((s) => s.year >= 2016).map((s) => ({ x: s.year, y: s.model })) }] : []),
                ...(data.hypothesis ? [{ id: "hyp", label: `Estimation communale (${data.hypothesis.source || "commune"})`, color: "#fb923c",
                  points: [{ x: data.hypothesis.year, y: data.hypothesis.value }] }] : []),
              ]}
            />
            {model ? (
              <>
              <p className="mt-2 text-[11px] text-slate-500">
                Courbe jaune : la population de référence INSEE ({meta.population.calibration?.year}) répartie sur la surface bâtie, puis prolongée au rythme
                de la croissance du bâti mesurée par Sentinel-2 ({fmt(meta.population.density_per_built_ha, 1)} habitants par hectare bâti). Indicateur
                indépendant et reproductible — ce n&apos;est pas un contre-recensement.
              </p>
              {meta.population.calibration?.level === "iris" && (
                <details className="mt-1 text-[11px] text-slate-400">
                  <summary className="cursor-pointer text-tactical-cyan">Calibré par quartier (IRIS INSEE) : densités de {fmt(Math.min(...meta.population.calibration.zones.map((z) => z.density)))} à {fmt(Math.max(...meta.population.calibration.zones.map((z) => z.density)))} habitants par hectare bâti</summary>
                  <ul className="mt-1 grid grid-cols-1 gap-x-4 sm:grid-cols-2">
                    {meta.population.calibration.zones.map((z) => (
                      <li key={z.code} className="flex justify-between gap-2"><span className="truncate">{z.nom}</span><span className="tabular-nums">{fmt(z.population)} hab. · {fmt(z.density)} /ha</span></li>
                    ))}
                  </ul>
                </details>
              )}
              </>
            ) : (
              <p className="mt-2 flex items-center gap-2 text-[11px] text-slate-500">
                <Satellite size={12} /> Lancez l&apos;analyse satellitaire de la commune (onglet Analyses) pour comparer avec la croissance du bâti.
              </p>
            )}
          </Panel>

          {meta?.builtup && (
            <Panel title="Surface bâtie 1985 → aujourd'hui (fusion WSF Evolution, WSF 2019, Sentinel-2)" icon={Satellite}>
              <LineChart
                series={[{ id: "bati", label: "Surface bâtie (ha)", color: "#f59e0b",
                  points: Object.entries(meta.builtup.totals_ha).map(([y, v]) => ({ x: Number(y), y: v })) }]}
                yFormat={(v) => fmt(v)}
                breakAt={breakInfo ? breakInfo.between[1] - 0.5 : null}
                breakLabel="changement de capteur"
              />
              {breakInfo && <p className="mt-1 text-[10px] text-tactical-amber">{breakInfo.reason}</p>}
            </Panel>
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Naissances domiciliées" icon={ChartIcon}>
              <LineChart series={[{ id: "n", label: "Naissances (INSEE, état civil)", color: "#f472b6", points: (data.series.naissances || []).map((p) => ({ x: p.year, y: p.value })) }]} height={150} />
            </Panel>
            <Panel title="Élèves des écoles publiques (1er degré)" icon={ChartIcon}>
              <LineChart series={[{ id: "e", label: "Élèves (Éducation nationale)", color: "#60a5fa", points: (data.series.ecoles_pub_eleves || []).map((p) => ({ x: p.year, y: p.value })) }]} height={150} />
            </Panel>
          </div>
        </div>

        <div className="space-y-4">
          {/* Keyed by the stored hypothesis: the form restarts from what is saved after each change. */}
          <HypothesisPanel key={data.hypothesis?.updated_at || "none"} commune={commune} hypothesis={data.hypothesis} legal={legal}
            canEdit={hasRole(user, "supervisor")} onSaved={load} />
          <Panel title="Desserte des habitants (rayons de la charte)" icon={Target}>
            {coverage?.available ? (
              <>
                <Bars
                  max={1}
                  items={Object.entries(coverage.families).map(([id, f]) => ({
                    id, label: `${CATEGORY[id]?.short || id} (≤ ${fmt(f.radius_m / 1000, 1)} km de trajet)`, value: f.served_rate ?? f.coverage_rate,
                    title: f.capacity_rule ? `${f.label} — avec une place (${f.capacity_rule}) ; proximité seule : ${pct(f.coverage_rate)}` : f.label,
                  }))}
                  format={(v) => pct(v)}
                  colorFor={(item) => CATEGORY[item.id]?.color || "#2dd4bf"}
                />
                <p className="mt-2 text-[10px] text-slate-500">
                  Part de la demande (habitants, ou enfants pour les écoles) à moins du rayon d&apos;un équipement — trajet estimé (vol d&apos;oiseau × facteur
                  de détour) —, en {coverage.year}. Pour les établissements scolaires : enfants ayant aussi une place (classes × effectif cible).
                  Les équipements hors écoles viennent d&apos;OpenStreetMap, dont la complétude varie : complétez-les dans l&apos;onglet Équipements.
                </p>
              </>
            ) : (
              <p className="text-xs text-slate-500">Disponible après l&apos;analyse satellitaire de la commune.</p>
            )}
          </Panel>
          <Panel title="Équipements recensés (données ouvertes + saisies)" icon={Building2}>
            <Bars items={Object.entries(data.equipments).map(([id, n]) => ({ id, label: CATEGORY[id]?.short || id, value: n }))} colorFor={(i) => CATEGORY[i.id]?.color} />
          </Panel>
          <Panel title="À savoir" icon={Info}>
            <ul className="list-disc space-y-1 pl-4 text-[11px] text-slate-400">
              {data.notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
          </Panel>
        </div>
      </div>
      {report && <ReportDialog user={user} kind="diagnostic" commune={commune} title={`Diagnostic — ${c.nom}`} onClose={() => setReport(false)} navigate={navigate} />}
    </div>
  );
}
