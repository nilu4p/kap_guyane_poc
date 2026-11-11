import { useCallback, useEffect, useMemo, useState } from "react";
import { CircleMarker, Tooltip } from "react-leaflet";
import { Download, FileSignature, Radar, Users } from "lucide-react";
import GridLayer from "../components/GridLayer.jsx";
import MapBase, { FitBounds } from "../components/MapBase.jsx";
import { Button, ErrorBanner, Panel, Pill, Spinner } from "../components/ui.jsx";
import { fmt, hasRole, km } from "../lib/format.js";
import { downloadCensus, errorMessage, fetchCensus, fetchContour, fetchGridMeta, fetchWatch } from "../services/api.js";
import ReportDialog from "./ReportDialog.jsx";

export default function VeilleView({ user, commune, communeName, navigate }) {
  const [meta, setMeta] = useState(null);
  const [since, setSince] = useState(2019);
  const [watch, setWatch] = useState(null);
  const [census, setCensus] = useState(null);
  const [contour, setContour] = useState(null);
  const [focus, setFocus] = useState(null);
  const [report, setReport] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchGridMeta(commune).then(setMeta).catch((err) => setError(errorMessage(err)));
    fetchContour(commune).then(setContour).catch(() => {});
  }, [commune]);
  useEffect(() => {
    if (!meta?.analysed) return undefined;
    let current = true; // a slower answer for a previous year must not replace the latest one
    setWatch(null);
    setError("");
    fetchWatch(commune, since).then((d) => current && setWatch(d)).catch((err) => current && setError(errorMessage(err)));
    if (hasRole(user, "analyst")) fetchCensus(commune, since).then((d) => current && setCensus(d)).catch(() => current && setCensus(null));
    return () => { current = false; };
  }, [commune, meta, since, user]);

  const cells = useMemo(() => (watch?.clusters || []).flatMap((c, k) => c.cells.map(([r, col]) => [r, col, k])), [watch]);
  const colorFor = useCallback((cell) => (watch?.clusters[cell[2]]?.far_from_school ? "#fb7185" : "#f59e0b"), [watch]);
  const tooltip = useCallback((cell) => `Foyer ${cell[2] + 1} : +${fmt(watch?.clusters[cell[2]]?.growth_ha, 1)} ha`, [watch]);
  const years = meta?.builtup?.years || [];

  if (!meta) return error ? <div className="p-4"><ErrorBanner message={error} /></div> : <Spinner />;
  if (!meta.analysed) {
    return <div className="p-6"><Panel title="Veille territoriale" icon={Radar}><p className="text-sm text-slate-300">Analyse satellitaire de {communeName} requise (onglet Analyses).</p></Panel></div>;
  }
  const s = watch?.summary;

  return (
    <div className="split-view lg:grid-cols-[420px_1fr]">
      <aside className="split-pane space-y-3 border-t border-tactical-line p-3 text-xs lg:border-r lg:border-t-0">
        <div className="flex items-end justify-between gap-2">
          <div>
            <p className="text-[10px] uppercase tracking-[0.3em] text-tactical-cyan">Veille territoriale</p>
            <h1 className="text-lg text-white">Quartiers en croissance — {communeName}</h1>
          </div>
          <label className="text-[10px] text-slate-500">depuis
            <select value={since} onChange={(e) => setSince(Number(e.target.value))} className="ml-1 border border-tactical-line bg-tactical-bg px-1 py-0.5 text-slate-100">
              {years.filter((y) => y >= 2016 && y < years[years.length - 1]).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
        </div>
        <ErrorBanner message={error} />
        {!watch ? (error ? null : <Spinner />) : (
          <>
            <dl className="grid grid-cols-3 gap-2 border border-tactical-line p-2">
              <div><dt className="text-slate-500">Bâti gagné</dt><dd className="text-lg text-white">+{fmt(s.growth_ha, 1)} ha</dd></div>
              <div><dt className="text-slate-500">Foyers</dt><dd className="text-lg text-white">{s.clusters}</dd></div>
              <div><dt className="text-slate-500">Loin d&apos;une école</dt><dd className="text-lg text-tactical-red">{fmt(s.far_from_school_ha, 1)} ha</dd></div>
            </dl>
            <p className="text-[10px] text-slate-500">{s.since} → {s.until}. {watch.method}</p>
            <ul className="space-y-2">
              {watch.clusters.map((c, k) => (
                <li key={k}>
                  <button type="button" onClick={() => setFocus(c)} className={`w-full border p-2 text-left ${focus === c ? "border-tactical-cyan" : "border-tactical-line"} hover:border-tactical-cyan/60`}>
                    <div className="flex items-center justify-between">
                      <span className="text-white">+{fmt(c.growth_ha, 1)} ha · ≈ {fmt(c.new_inhabitants)} hab.</span>
                      {c.far_from_school ? <Pill color="#fb7185">école &gt; rayon</Pill> : <Pill color="#3dff8a">école proche</Pill>}
                    </div>
                    <p className="text-slate-400">près de {c.landmark || `${c.lat}, ${c.lon}`}</p>
                    <p className="text-[10px] text-slate-500">
                      {c.new_buildings != null ? `≈ ${fmt(c.new_buildings)} bâtiments · ` : ""}école {km(c.nearest?.ecole?.distance_m)} · eau {km(c.nearest?.eau?.distance_m)} · santé {km(c.nearest?.sante?.distance_m)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        {census && (
          <Panel title="Recensement Éclaireur (appui au RIL)" icon={Users}>
            <p className="text-slate-400">{census.rows.length} carreaux de 200 m à signaler à l&apos;INSEE avant la collecte de janvier ; {census.hidden.cells} carreaux non listés ({census.hidden.rule}).</p>
            <p className="mt-1 text-[10px] text-slate-500">{census.notice}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button icon={Download} onClick={() => downloadCensus(commune, since).catch((err) => setError(errorMessage(err, "Export impossible")))}>Exporter (CSV)</Button>
              <Button icon={FileSignature} variant="primary" onClick={() => setReport(true)}>Liste signée</Button>
            </div>
          </Panel>
        )}
      </aside>
      <div className="split-map">
        <MapBase contour={contour} bbox={contour?.properties?.bbox} imageryYear={years[years.length - 1]}>
          {cells.length > 0 && <GridLayer grid={watch.grid} cells={cells} colorFor={colorFor} opacity={0.8} tooltip={tooltip} />}
          {(watch?.clusters || []).slice(0, 15).map((c, k) => (
            <CircleMarker key={k} center={[c.lat, c.lon]} radius={6 + Math.min(14, c.growth_ha)} pathOptions={{ color: c.far_from_school ? "#fb7185" : "#f59e0b", weight: 2, fillOpacity: 0.1 }}
              eventHandlers={{ click: () => setFocus(c) }}>
              <Tooltip className="tactical-tip">+{fmt(c.growth_ha, 1)} ha · ≈ {fmt(c.new_inhabitants)} habitants</Tooltip>
            </CircleMarker>
          ))}
          {focus && <FitBounds bbox={[focus.lon - 0.01, focus.lat - 0.01, focus.lon + 0.01, focus.lat + 0.01]} />}
        </MapBase>
      </div>
      {report && <ReportDialog user={user} kind="recensement" commune={commune} since={since} title={`Recensement Éclaireur — ${communeName}`} onClose={() => setReport(false)} navigate={navigate} />}
    </div>
  );
}
