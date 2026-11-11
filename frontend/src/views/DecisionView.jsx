import { Fragment, useCallback, useEffect, useState } from "react";
import L from "leaflet";
import { Circle, Marker, Tooltip, useMapEvents } from "react-leaflet";
import { Archive, CheckCircle2, FileSignature, MapPinPlus, Play, Save, Target, Trash2, Undo2 } from "lucide-react";
import GridLayer from "../components/GridLayer.jsx";
import MapBase from "../components/MapBase.jsx";
import { Button, ErrorBanner, Field, Panel, Pill, Spinner, inputClass } from "../components/ui.jsx";
import { fmt, hasRole, km, pct } from "../lib/format.js";
import {
  createScenario, deleteScenario, errorMessage, evaluateSites, fetchCategories, fetchContour, fetchGridMeta, fetchLayer,
  fetchScenarios, recommendSites, setScenarioStatus,
} from "../services/api.js";
import { CATEGORY, accessColor } from "../theme.js";
import { facilityIcon } from "./AtlasView.jsx";
import ReportDialog from "./ReportDialog.jsx";

const CHECK_COLORS = { ok: "#3dff8a", attention: "#f5c542", "non vérifié": "#94a3b8" };
const DEMAND_LABEL = { enfants_3_10: "enfants de 3-10 ans", enfants_11_14: "jeunes de 11-14 ans", jeunes_15_17: "jeunes de 15-17 ans", pop: "habitants" };

function siteIcon(label) {
  return L.divIcon({ className: "", html: `<span class="site-marker">${label}</span>`, iconSize: [26, 26], iconAnchor: [13, 13] });
}

function ClickToAdd({ active, onAdd }) {
  useMapEvents({ click: (e) => active && onAdd({ lat: Number(e.latlng.lat.toFixed(6)), lon: Number(e.latlng.lng.toFixed(6)) }) });
  return null;
}

export default function DecisionView({ user, commune, communeName, navigate }) {
  const [meta, setMeta] = useState(null);
  const [categories, setCategories] = useState([]);
  const [contour, setContour] = useState(null);
  const [form, setForm] = useState({ category: "ecole", k: 3, radius_m: "", use_hypothesis: false,
    constraints: { exclude_water: true, max_built_fraction: 0.6, road_max_m: 500, exclude_protected: false } });
  const [access, setAccess] = useState(null);
  const [result, setResult] = useState(null);
  const [sites, setSites] = useState([]);
  const [evaluation, setEvaluation] = useState(null);
  const [placing, setPlacing] = useState(false);
  const [scenarios, setScenarios] = useState([]);
  const [scenarioName, setScenarioName] = useState("");
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const loadScenarios = useCallback(() => fetchScenarios(commune).then((d) => setScenarios(d.scenarios)).catch(() => {}), [commune]);
  useEffect(() => {
    fetchGridMeta(commune).then(setMeta).catch((err) => setError(errorMessage(err)));
    fetchContour(commune).then(setContour).catch(() => {});
    fetchCategories().then((d) => setCategories(d.categories)).catch(() => {});
    loadScenarios();
    setResult(null);
    setSites([]);
    setEvaluation(null);
  }, [commune, loadScenarios]);

  useEffect(() => {
    if (!meta?.analysed) return undefined;
    let current = true; // switching family quickly: only the latest answer is drawn
    setAccess(null);
    fetchLayer(commune, { layer: "acces", category: form.category, hypothese: form.use_hypothesis })
      .then((d) => current && setAccess(d))
      .catch((err) => current && setError(errorMessage(err)));
    return () => { current = false; };
  }, [commune, meta, form.category, form.use_hypothesis]);

  const radius = Number(form.radius_m) || categories.find((c) => c.id === form.category)?.radius_m || 1500;
  // Trip radius → straight-line circle on the map (radius / detour factor, as computed by the API).
  const detour = access?.detour_factor || 1.3;
  const circleRadius = radius / Math.max(detour, 1);
  const colorFor = useCallback((cell) => accessColor(cell[2], access?.radius_m || radius / 1.3), [access, radius]);
  // Stable identity: a new function on every render would redraw every cell of the map (each keystroke).
  const accessTooltip = useCallback((c) => `${km(c[2])} · demande ${c[3] === -1 ? "non affichée (carreau peu bâti)" : fmt(c[3])}`, []);

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

  const recommend = () => run("recommend", async () => {
    const r = await recommendSites({ commune, category: form.category, k: Number(form.k), radius_m: form.radius_m ? Number(form.radius_m) : null,
      use_hypothesis: form.use_hypothesis, constraints: { ...form.constraints, road_max_m: form.constraints.road_max_m === "" ? null : Number(form.constraints.road_max_m) } });
    if (!r.available) throw new Error(r.reason || "Recommandation impossible");
    setResult(r);
    setSites(r.sites.map((s) => ({ lat: s.lat, lon: s.lon, name: `Site ${s.rank}` })));
    setEvaluation(null);
  });

  const evaluate = () => run("evaluate", async () => {
    const r = await evaluateSites({ commune, category: form.category, sites, use_hypothesis: form.use_hypothesis });
    if (!r.available) throw new Error(r.reason || "Évaluation impossible");
    setEvaluation(r);
  });

  const changeStatus = (scenario, status) => run(`status:${scenario.id}`, async () => {
    await setScenarioStatus(scenario.id, status);
    await loadScenarios();
  });

  const remove = (scenario) => {
    if (!window.confirm(`Supprimer « ${scenario.name} » ?`)) return;
    run(`delete:${scenario.id}`, async () => {
      await deleteScenario(scenario.id);
      await loadScenarios();
    });
  };

  const save = () => run("save", async () => {
    await createScenario({ commune_code: commune, category: form.category, name: scenarioName || `${CATEGORY[form.category].short} — ${new Date().toLocaleDateString("fr-FR")}`,
      description: result ? `Proposition automatique (${result.k} sites, rayon ${result.radius_m} m) ajustée par les services.` : "Sites placés par les services.",
      sites, params: { use_hypothesis: form.use_hypothesis, k: Number(form.k), radius_m: radius, constraints: form.constraints } });
    setScenarioName("");
    loadScenarios();
  });

  if (!meta) return error ? <div className="p-4"><ErrorBanner message={error} /></div> : <Spinner />;
  if (!meta.analysed) {
    return (
      <div className="p-6">
        <ErrorBanner message={error} />
        <Panel title="Aide à l'implantation" icon={Target}>
          <p className="text-sm text-slate-300">L&apos;aide à l&apos;implantation s&apos;appuie sur la population estimée carreau par carreau : lancez d&apos;abord l&apos;analyse satellitaire de {communeName}.</p>
          <Button className="mt-3" onClick={() => navigate("atlas", commune)}>Aller à l&apos;atlas</Button>
        </Panel>
      </div>
    );
  }
  const before = evaluation?.before || result?.before;
  const after = evaluation?.after || result?.after;

  return (
    <div className="split-view lg:grid-cols-[380px_1fr]">
      <aside className="split-pane space-y-3 border-t border-tactical-line p-3 text-xs lg:border-r lg:border-t-0">
        <div>
          <p className="text-[10px] uppercase tracking-[0.3em] text-tactical-cyan">Aide à la décision</p>
          <h1 className="text-lg text-white">Où implanter ? — {communeName}</h1>
        </div>
        <ErrorBanner message={error} />
        <Panel title="Besoin" icon={Target}>
          <div className="space-y-2">
            <Field label="Équipement">
              <select className={inputClass} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value, radius_m: "" })}>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Nombre de sites"><input className={inputClass} type="number" min={1} max={10} value={form.k} onChange={(e) => setForm({ ...form, k: e.target.value })} /></Field>
              <Field label="Rayon de desserte (m)" hint={`défaut ${categories.find((c) => c.id === form.category)?.radius_m || "—"}`}>
                <input className={inputClass} type="number" min={100} value={form.radius_m} placeholder={String(radius)} onChange={(e) => setForm({ ...form, radius_m: e.target.value })} />
              </Field>
            </div>
            <p className="text-[10px] text-slate-500">Demande prise en compte : {DEMAND_LABEL[categories.find((c) => c.id === form.category)?.demand] || "habitants"} estimés par carreau.
              Rayon = distance de trajet estimée (vol d&apos;oiseau × facteur de détour {String(detour).replace(".", ",")}). Pour les écoles, la demande rattachée
              au-delà des places (classes × effectif cible) compte comme non desservie.</p>
          </div>
        </Panel>
        <Panel title="Contraintes" icon={CheckCircle2}>
          <div className="space-y-2">
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.constraints.exclude_water} onChange={(e) => setForm({ ...form, constraints: { ...form.constraints, exclude_water: e.target.checked } })} /> Exclure les plans d&apos;eau (Sentinel-2)</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.constraints.exclude_protected} onChange={(e) => setForm({ ...form, constraints: { ...form.constraints, exclude_protected: e.target.checked } })} /> Exclure les aires de protection stricte (réserves, UICN I-IV)</label>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Bâti max. du carreau"><input className={inputClass} type="number" step={0.05} min={0} max={1} value={form.constraints.max_built_fraction} onChange={(e) => setForm({ ...form, constraints: { ...form.constraints, max_built_fraction: Number(e.target.value) } })} /></Field>
              <Field label="Route à moins de (m)"><input className={inputClass} type="number" min={0} value={form.constraints.road_max_m} onChange={(e) => setForm({ ...form, constraints: { ...form.constraints, road_max_m: e.target.value } })} /></Field>
            </div>
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.use_hypothesis} onChange={(e) => setForm({ ...form, use_hypothesis: e.target.checked })} /> Hypothèse communale de population</label>
          </div>
        </Panel>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon={Play} busy={busy === "recommend"} onClick={recommend}>Proposer {form.k} site(s)</Button>
          <Button icon={MapPinPlus} onClick={() => setPlacing((v) => !v)} className={placing ? "ring-1 ring-tactical-cyan" : ""}>{placing ? "Cliquez sur la carte…" : "Placer un site"}</Button>
          {sites.length > 0 && <Button icon={Undo2} onClick={() => { setSites(sites.slice(0, -1)); setEvaluation(null); }}>Retirer le dernier</Button>}
        </div>

        {before && (
          <Panel title="Effet sur la desserte" icon={Target}>
            <dl className="grid grid-cols-2 gap-2">
              <div><dt className="text-slate-500">Avant</dt><dd className="text-lg text-white">{pct(before.coverage_rate, 1)}</dd><dd className="text-[10px] text-slate-500">{fmt(before.demand_covered)} / {fmt(before.demand_total)}</dd></div>
              <div><dt className="text-slate-500">Après</dt><dd className="text-lg text-tactical-green">{pct(after?.coverage_rate, 1)}</dd><dd className="text-[10px] text-slate-500">{fmt(after?.demand_covered)} desservis</dd></div>
            </dl>
            {evaluation?.gain && <p className="mt-2 text-tactical-green">+{fmt(evaluation.gain.demand)} desservis · distance moyenne {km(before.mean_distance_m)} → {km(after.mean_distance_m)}</p>}
            {result?.classes?.pupils_per_class && <p className="mt-2 text-slate-400">≈ {result.classes.per_site.join(", ")} classe(s) par site ({fmt(result.classes.pupils_per_class, 1)} élèves par classe dans la commune)</p>}
            <p className="mt-2 text-[10px] text-slate-500">{result?.method || "Évaluation des sites placés : couverture à vol d'oiseau."}</p>
            <div className="mt-2 flex gap-2">
              <Button icon={Play} busy={busy === "evaluate"} onClick={evaluate} disabled={!sites.length}>Réévaluer les sites</Button>
            </div>
          </Panel>
        )}

        {result?.sites?.length > 0 && (
          <div className="space-y-2">
            {result.sites.map((s) => (
              <div key={s.rank} className="border border-tactical-line p-2">
                <p className="flex items-center justify-between text-white"><span>Site {s.rank}</span><span className="text-tactical-green">+{fmt(s.gain_demand)}</span></p>
                <p className="mt-1 text-slate-400">{s.why}</p>
                <ul className="mt-1 space-y-0.5">
                  {s.checks.map((c) => (
                    <li key={c.label} className="flex justify-between gap-2 text-[10px]">
                      <span className="text-slate-500">{c.label}</span>
                      <span style={{ color: CHECK_COLORS[c.status] }} title={c.detail}>{c.status}{c.detail && c.status !== "ok" ? ` — ${c.detail}` : ""}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {sites.length > 0 && hasRole(user, "analyst") && (
          <Panel title="Enregistrer comme scénario" icon={Save}>
            <div className="flex gap-2">
              <input className={inputClass} value={scenarioName} onChange={(e) => setScenarioName(e.target.value)} placeholder="ex. Écoles provisoires 2027" />
              <Button variant="primary" icon={Save} busy={busy === "save"} onClick={save}>Enregistrer</Button>
            </div>
          </Panel>
        )}

        <Panel title={`Scénarios — ${scenarios.length}`} icon={Archive}>
          {scenarios.length === 0 ? <p className="text-slate-500">Aucun scénario pour cette commune.</p> : (
            <ul className="space-y-2">
              {scenarios.map((sc) => (
                <li key={sc.id} className="border-b border-tactical-line pb-2 last:border-0">
                  <div className="flex items-center justify-between gap-2">
                    <button type="button" className="truncate text-left text-white hover:text-tactical-cyan" onClick={() => { setForm({ ...form, category: sc.category }); setSites(sc.sites); setResult(null); setEvaluation(null); setPlacing(false); }}>
                      {sc.name}
                    </button>
                    <Pill color={sc.status === "valide" ? "#3dff8a" : sc.status === "archive" ? "#64748b" : "#f5c542"}>{sc.status_label}</Pill>
                  </div>
                  <p className="text-[10px] text-slate-500">{CATEGORY[sc.category]?.short} · {sc.sites.length} site(s){sc.evaluation?.gain ? ` · +${fmt(sc.evaluation.gain.demand)} desservis` : ""} · {sc.created_by}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {hasRole(user, "analyst") && <Button icon={FileSignature} onClick={() => setReport(sc)}>Dossier</Button>}
                    {hasRole(user, "supervisor") && sc.status === "brouillon" && <Button icon={CheckCircle2} busy={busy === `status:${sc.id}`} onClick={() => changeStatus(sc, "valide")}>Valider</Button>}
                    {hasRole(user, "supervisor") && sc.status === "valide" && <Button icon={Archive} busy={busy === `status:${sc.id}`} onClick={() => changeStatus(sc, "archive")}>Archiver</Button>}
                    {hasRole(user, "analyst") && sc.status !== "valide" && <Button icon={Trash2} variant="danger" busy={busy === `delete:${sc.id}`} onClick={() => remove(sc)}>Supprimer</Button>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </aside>
      <div className="split-map">
        <MapBase contour={contour} bbox={contour?.properties?.bbox} baseDefault="osm">
          <ClickToAdd active={placing} onAdd={(s) => { setSites((list) => [...list, { ...s, name: `Site ${list.length + 1}` }]); setEvaluation(null); }} />
          {access?.available && <GridLayer grid={access.grid} cells={access.cells} colorFor={colorFor} opacity={0.55} tooltip={accessTooltip} />}
          {(access?.facilities || []).map((f, i) => (
            <Marker key={`f${i}`} position={[f.lat, f.lon]} icon={facilityIcon(form.category, f.status)}>
              <Tooltip className="tactical-tip"><b>{f.name}</b><br />demande dans le rayon ≈ {fmt(f.demand_in_radius)}
                {f.places ? <> · {fmt(f.places)} places{f.saturation > 1 ? <span style={{ color: "#ff3b3b" }}> · saturée ({Math.round(f.saturation * 100)} %)</span> : ""}</> : ""}
                {f.imprecise ? <><br /><span style={{ color: "#f5c542" }}>position approximative</span></> : null}</Tooltip>
            </Marker>
          ))}
          {sites.map((s, i) => (
            <Fragment key={`s${i}`}>
              <Circle center={[s.lat, s.lon]} radius={circleRadius} pathOptions={{ color: "#2dd4bf", weight: 1.5, fillOpacity: 0.06, dashArray: "4 4" }} />
              <Marker position={[s.lat, s.lon]} icon={siteIcon(i + 1)} draggable eventHandlers={{ dragend: (e) => {
                const p = e.target.getLatLng();
                setSites((list) => list.map((x, k) => (k === i ? { ...x, lat: Number(p.lat.toFixed(6)), lon: Number(p.lng.toFixed(6)) } : x)));
                setEvaluation(null);
              } }}>
                <Tooltip className="tactical-tip">{s.name} — glisser pour déplacer</Tooltip>
              </Marker>
            </Fragment>
          ))}
        </MapBase>
        <div className="pointer-events-none absolute bottom-6 left-3 right-3 z-[999] border sm:left-auto sm:max-w-md border-tactical-line bg-tactical-panel/90 px-2 py-1 text-[10px] text-slate-400">
          Couleur des carreaux : distance au {CATEGORY[form.category]?.short.toLowerCase()} le plus proche (vert = desservi) · foncier, PPRI et réseaux à vérifier
        </div>
      </div>
      {report && <ReportDialog user={user} kind="implantation" scenarioId={report.id} title={`Dossier d'implantation — ${report.name}`} onClose={() => setReport(null)} navigate={navigate} />}
    </div>
  );
}
