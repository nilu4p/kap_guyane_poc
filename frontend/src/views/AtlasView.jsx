import { useCallback, useEffect, useMemo, useState } from "react";
import L from "leaflet";
import { GeoJSON, Marker, TileLayer, Tooltip } from "react-leaflet";
import { Layers, Satellite, ShieldCheck, Square, X } from "lucide-react";
import GridLayer from "../components/GridLayer.jsx";
import { LineChart } from "../components/Charts.jsx";
import MapBase from "../components/MapBase.jsx";
import { Button, ErrorBanner, Pill, Spinner } from "../components/ui.jsx";
import { fmt, hasRole, km, pct } from "../lib/format.js";
import {
  errorMessage, fetchCell, fetchConstraints, fetchContour, fetchEquipments, fetchGridMeta, fetchLayer, fetchSentinel2Scenes,
  sentinel2TileUrl, startAnalysis,
} from "../services/api.js";
import { ACCESS_COLORS, CATEGORY, LAYERS, STATUS, accessColor, classColor } from "../theme.js";

const LAYER_ORDER = ["bati", "croissance", "population", "enfants", "acces", "batiments", "eau"];
const SECRET = -1; // value withheld by the API (fewer buildings than the secrecy threshold)
const QUALITY_COLORS = { bonne: "#3dff8a", moyenne: "#f5c542", faible: "#ff8c1a", absente: "#94a3b8" };
const ACCESS_LABELS = ["≤ ½ rayon", "≤ rayon", "≤ 1,5 rayon", "≤ 2,5 rayons", "≤ 4 rayons", "au-delà"];

export function facilityIcon(category, status) {
  const color = CATEGORY[category]?.color || "#94a3b8";
  return L.divIcon({
    className: "",
    html: `<span class="facility-marker${status !== "existant" ? " is-planned" : ""}" style="--marker:${color}"></span>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
  });
}

function Legend({ layer, data }) {
  if (!data?.available) return null;
  if (layer === "acces") {
    return (
      <div>
        <p className="mb-1 text-[10px] text-slate-400">Distance au plus proche · rayon {km(data.radius_trip_m)} de trajet ≈ {km(data.radius_m)} à vol d&apos;oiseau</p>
        <div className="flex gap-0.5">
          {ACCESS_COLORS.map((c, i) => (
            <div key={c} className="flex-1"><div className="h-2" style={{ background: c }} /><p className="mt-0.5 text-[8px] leading-tight text-slate-500">{ACCESS_LABELS[i]}</p></div>
          ))}
        </div>
      </div>
    );
  }
  const spec = LAYERS[layer];
  return (
    <div>
      <p className="mb-1 text-[10px] text-slate-400">{spec.label}</p>
      <div className="flex gap-0.5">
        {spec.palette.map((c, i) => (
          <div key={c} className="flex-1"><div className="h-2" style={{ background: c }} />
            <p className="mt-0.5 text-[8px] text-slate-500">{i === 0 ? "≤" : ">"} {spec.format(i === 0 ? spec.breaks[0] : spec.breaks[i - 1])}</p></div>
        ))}
      </div>
    </div>
  );
}

function CellPanel({ commune, cell, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true; // clicking cells quickly: only the last one is shown
    setData(null);
    setError("");
    fetchCell(commune, cell).then((d) => current && setData(d)).catch((err) => current && setError(errorMessage(err)));
    return () => { current = false; };
  }, [commune, cell]);
  return (
    <div className="absolute left-3 right-3 top-3 z-[1000] max-h-[calc(100%-24px)] sm:left-auto sm:w-[360px] overflow-y-auto border border-tactical-line bg-tactical-panel/97 p-3 text-xs shadow-2xl">
      <div className="mb-2 flex items-start justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-tactical-cyan">Carreau 200 m · {cell}</p>
          {data && <p className="text-slate-400">{fmt(data.lat, 5)}, {fmt(data.lon, 5)}</p>}
        </div>
        <button type="button" onClick={onClose} aria-label="Fermer" className="text-slate-400 hover:text-white"><X size={16} /></button>
      </div>
      <ErrorBanner message={error} />
      {!data ? (error ? null : <Spinner />) : (
        <div className="space-y-3">
          {data.built_series && (
            <LineChart height={120}
              series={[{ id: "b", label: "Part bâtie du carreau (%)", color: "#f59e0b", points: data.built_series.map((p) => ({ x: p.year, y: p.fraction * 100 })) }]}
              yFormat={(v) => `${fmt(v)} %`} />
          )}
          {data.population && (
            <dl className="grid grid-cols-2 gap-2">
              <div><dt className="text-slate-500">Habitants estimés ({data.population_year})</dt><dd className="text-base text-white">{fmt(data.population.pop)}</dd></div>
              <div><dt className="text-slate-500">Enfants 3-10 ans</dt><dd className="text-base text-white">{fmt(data.population.enfants_3_10)}</dd></div>
            </dl>
          )}
          {data.buildings && (
            <p className="text-slate-400">
              {data.buildings.count === SECRET ? `moins de ${data.secrecy?.min_buildings ?? 5}` : fmt(data.buildings.count)} bâtiments ({data.buildings.source})
            </p>
          )}
          {data.sparse && <p className="border-l-2 border-tactical-green/60 pl-2 text-[11px] text-tactical-green">{data.secrecy.note}</p>}
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">Équipement le plus proche (vol d&apos;oiseau · trajet estimé)</p>
            <ul className="space-y-1">
              {Object.entries(data.nearest).map(([cat, n]) => (
                <li key={cat} className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span className="h-2 w-2 shrink-0" style={{ background: CATEGORY[cat]?.color }} />
                    <span className="truncate" title={n?.name}>{CATEGORY[cat]?.short}</span>
                  </span>
                  {n ? (
                    <span className={`shrink-0 tabular-nums ${n.covered ? "text-tactical-green" : "text-tactical-amber"}`} title={n.name}>
                      {km(n.distance_m)} · ~{km(n.walk_m)}
                    </span>
                  ) : <span className="text-slate-600">aucun recensé</span>}
                </li>
              ))}
            </ul>
          </div>
          <p className="text-[10px] text-slate-600">{data.population_method}</p>
        </div>
      )}
    </div>
  );
}

export default function AtlasView({ user, commune, communeName, navigate }) {
  const [meta, setMeta] = useState(null);
  const [contour, setContour] = useState(null);
  const [layer, setLayer] = useState("croissance");
  const [year, setYear] = useState(null);
  const [since, setSince] = useState(2019);
  const [category, setCategory] = useState("ecole");
  const [hypothesis, setHypothesis] = useState(false);
  const [data, setData] = useState(null);
  const [equipments, setEquipments] = useState([]);
  const [shown, setShown] = useState({ ecole: true, sante: true, eau: false, alimentation: false, transport: false, college: false, lycee: false, services: false, petite_enfance: false });
  const [constraints, setConstraints] = useState(null);
  const [showProtected, setShowProtected] = useState(false);
  const [scenes, setScenes] = useState(null);
  const [showS2, setShowS2] = useState(false);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setMeta(null);
    setSelected(null);
    fetchGridMeta(commune).then((m) => {
      setMeta(m);
      const years = m.builtup?.years || [];
      setYear(years.length ? years[years.length - 1] : null);
    }).catch((err) => setError(errorMessage(err)));
    fetchContour(commune).then(setContour).catch(() => setContour(null));
    fetchEquipments(commune).then((d) => setEquipments(d.equipments)).catch(() => setEquipments([]));
    fetchConstraints(commune).then(setConstraints).catch(() => setConstraints(null));
  }, [commune]);

  useEffect(() => {
    if (!meta?.analysed || year == null) return undefined;
    let current = true; // moving the time slider: a slower answer for a previous year must not win
    setData(null);
    setError("");
    fetchLayer(commune, { layer, year, since, category, hypothese: hypothesis })
      .then((d) => current && setData(d))
      .catch((err) => current && setError(errorMessage(err)));
    return () => { current = false; };
  }, [commune, meta, layer, year, since, category, hypothesis]);

  // "Growth since" must stay before the year shown (the slider can move below it).
  useEffect(() => {
    const years = meta?.builtup?.years || [];
    if (year == null || since < year) return;
    const earlier = years.filter((y) => y < year);
    if (earlier.length) setSince(earlier.includes(2019) ? 2019 : earlier[earlier.length - 1]);
  }, [meta, year, since]);

  useEffect(() => {
    if (showS2 && !scenes) fetchSentinel2Scenes(commune).then(setScenes).catch(() => setScenes({ features: [] }));
  }, [showS2, scenes, commune]);

  const below = data?.secrecy?.min_buildings ?? 5;
  const colorFor = useCallback((cell) => {
    if (layer === "acces") return accessColor(cell[2], data?.radius_m || 1000);
    if (layer === "croissance" && cell[2] <= 0) return null;
    if (cell[2] === SECRET) return "#475569"; // sparse cell: value withheld (statistical secrecy)
    return classColor(cell[2], layer);
  }, [layer, data]);
  const tooltip = useCallback((cell) => {
    if (layer === "acces") return `${km(cell[2])} · demande ${cell[3] === SECRET ? "non affichée (carreau peu bâti)" : fmt(cell[3])}`;
    if (cell[2] === SECRET) return `Carreau peu bâti (< ${below} bâtiments) : effectif non affiché`;
    return LAYERS[layer].format(cell[2]);
  }, [layer, below]);
  const onSelect = useCallback((id) => setSelected(id), []);

  const years = meta?.builtup?.years || [];
  const visibleEquipments = useMemo(() => equipments.filter((e) => shown[e.category]), [equipments, shown]);
  const calib = meta?.builtup?.calibration;

  const launch = async () => {
    setBusy(true);
    try {
      await startAnalysis(commune, true);
      navigate("analyses");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="split-view lg:grid-cols-[300px_1fr]">
      <aside className="split-pane space-y-4 border-t border-tactical-line p-3 text-xs lg:border-r lg:border-t-0">
        <div>
          <p className="text-[10px] uppercase tracking-[0.3em] text-tactical-cyan">Atlas</p>
          <h1 className="text-lg text-white">{communeName}</h1>
        </div>
        <ErrorBanner message={error} />
        {!meta ? <Spinner /> : !meta.analysed ? (
          <div className="space-y-2 border border-tactical-amber/40 bg-tactical-amber/10 p-3 text-tactical-amber">
            <p>L&apos;analyse satellitaire de cette commune n&apos;a pas encore été réalisée (bâti 1985 → aujourd&apos;hui, population, accessibilité).</p>
            {hasRole(user, "analyst") ? (
              <Button variant="primary" icon={Satellite} busy={busy} onClick={launch}>Lancer l&apos;analyse (quelques minutes)</Button>
            ) : <p className="text-slate-400">Demandez-la à un chargé d&apos;études.</p>}
          </div>
        ) : (
          <>
            <section className="space-y-2">
              <p className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-slate-500"><Layers size={12} /> Couche (carreaux de 200 m)</p>
              {LAYER_ORDER.map((id) => (
                <label key={id} className="flex cursor-pointer items-center gap-2">
                  <input type="radio" name="layer" checked={layer === id} onChange={() => setLayer(id)} />
                  <span className={layer === id ? "text-white" : "text-slate-400"}>{id === "acces" ? "Accessibilité aux équipements" : LAYERS[id].label}</span>
                </label>
              ))}
            </section>
            {["bati", "croissance", "population", "enfants", "acces"].includes(layer) && years.length > 0 && (
              <section className="space-y-1">
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Année : <span className="text-white">{year}</span></p>
                <input type="range" min={0} max={years.length - 1} value={Math.max(0, years.indexOf(year))} onChange={(e) => setYear(years[Number(e.target.value)])} className="w-full" />
                <div className="flex justify-between text-[9px] text-slate-600"><span>{years[0]}</span><span>{years[years.length - 1]}</span></div>
                <p className="text-[10px] text-slate-600">Le fond satellite suit l&apos;année (mosaïque Sentinel-2 sans nuages EOX, dès 2016).</p>
              </section>
            )}
            {layer === "croissance" && (
              <label className="block space-y-1">
                <span className="text-[10px] uppercase tracking-wider text-slate-500">Croissance depuis</span>
                {years.some((y) => y < year) ? (
                  <select value={since} onChange={(e) => setSince(Number(e.target.value))} className="w-full border border-tactical-line bg-tactical-bg px-2 py-1">
                    {years.filter((y) => y < year).map((y) => <option key={y} value={y}>{y}</option>)}
                  </select>
                ) : <p className="text-[10px] text-slate-500">Première année de la série : choisissez une année plus récente.</p>}
              </label>
            )}
            {layer === "acces" && (
              <label className="block space-y-1">
                <span className="text-[10px] uppercase tracking-wider text-slate-500">Famille d&apos;équipements</span>
                <select value={category} onChange={(e) => setCategory(e.target.value)} className="w-full border border-tactical-line bg-tactical-bg px-2 py-1">
                  {Object.entries(CATEGORY).map(([id, c]) => <option key={id} value={id}>{c.label}</option>)}
                </select>
              </label>
            )}
            {["population", "enfants", "acces"].includes(layer) && (
              <label className="flex items-center gap-2"><input type="checkbox" checked={hypothesis} onChange={(e) => setHypothesis(e.target.checked)} /> Utiliser l&apos;hypothèse communale de population</label>
            )}
            <div className="border border-tactical-line p-2">
              <Legend layer={layer} data={data} />
              {["population", "enfants", "batiments", "acces"].includes(layer) && (
                <p className="mt-1 flex items-center gap-1 text-[10px] text-slate-500"><span className="inline-block h-2 w-2" style={{ background: "#475569" }} /> carreau peu bâti : effectif non affiché (secret)</p>
              )}
              {layer === "croissance" && data?.growth_floor_ha && <p className="mt-1 text-[10px] text-slate-500">Gains inférieurs à {fmt(data.growth_floor_ha, 2)} ha non affichés (secret).</p>}
            </div>
            {data?.stats && (
              <dl className="grid grid-cols-2 gap-2 border border-tactical-line p-2">
                <div><dt className="text-slate-500">Demande desservie</dt><dd className="text-base text-white">{pct(data.stats.coverage_rate)}</dd>
                  {data.stats.capacity_rule && <dd className="text-[10px] text-slate-500" title={data.stats.capacity_rule}>avec une place : {pct(data.stats.served_rate)}</dd>}</div>
                <div><dt className="text-slate-500">Non desservie</dt><dd className="text-base text-tactical-amber">{fmt(data.stats.demand_uncovered)}</dd>
                  {data.stats.demand_saturated > 0 && <dd className="text-[10px] text-tactical-red">+ {fmt(data.stats.demand_saturated)} sans place ({data.stats.saturated_facilities} école(s) saturée(s))</dd>}</div>
                <div><dt className="text-slate-500">Distance moyenne</dt><dd>{km(data.stats.mean_distance_m)}</dd></div>
                <div><dt className="text-slate-500">Équipements</dt><dd>{data.stats.facilities}{data.stats.facilities_imprecise ? <span className="text-tactical-amber" title="positions approximatives à corriger (onglet Équipements)"> · {data.stats.facilities_imprecise} approx.</span> : null}</dd></div>
              </dl>
            )}
            {data?.model && (
              <p className="text-[10px] text-slate-500">{fmt(data.model.total)} habitants estimés · {data.model.calibration?.basis}{data.model.extrapolated ? " · année postérieure au recensement : extrapolation" : ""}</p>
            )}
          </>
        )}
        <section className="space-y-1">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">Équipements</p>
          {Object.entries(CATEGORY).map(([id, c]) => (
            <label key={id} className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" checked={!!shown[id]} onChange={(e) => setShown({ ...shown, [id]: e.target.checked })} />
              <span className="h-2 w-2 rotate-45" style={{ background: c.color }} />
              <span className="text-slate-300">{c.short}</span>
              <span className="ml-auto text-slate-600">{equipments.filter((e) => e.category === id).length}</span>
            </label>
          ))}
          <p className="pt-1 text-[10px] text-slate-600">Losange pointillé = provisoire ou en projet. Écoles : annuaire de l&apos;Éducation nationale ; autres : OpenStreetMap + saisies.</p>
        </section>
        <section className="space-y-1">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">Imagerie et contraintes</p>
          <label className="flex items-center gap-2"><input type="checkbox" checked={showS2} onChange={(e) => setShowS2(e.target.checked)} /> Sentinel-2 récente (10 m, la plus claire des 90 j)</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={showProtected} onChange={(e) => setShowProtected(e.target.checked)} /> Aires protégées (WDPA)</label>
        </section>
        {calib && (
          <section className="space-y-1 border border-tactical-line p-2 text-[11px]">
            <p className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-slate-500"><ShieldCheck size={12} /> Qualité de l&apos;analyse satellitaire</p>
            {meta.builtup.quality && (
              <p style={{ color: QUALITY_COLORS[meta.builtup.quality.level] }}>
                <b>{meta.builtup.quality.label}</b> — {meta.builtup.quality.advice}
              </p>
            )}
            <p>Concordance avec WSF 2019 : <b>{pct(calib.concordance)}</b> des carreaux bâtis / non bâtis</p>
            <p>Corrélation r = {fmt(calib.correlation, 2)} · F1 = {fmt(calib.f1_built, 2)} ({fmt(calib.cells_compared)} carreaux)</p>
            <p className="text-slate-500">Années observées : {(meta.builtup.observed_years || []).join(", ")}</p>
            <p className="text-slate-600">Calculé le {new Date(meta.computed_at).toLocaleDateString("fr-FR")}</p>
          </section>
        )}
      </aside>
      <div className="split-map">
        <MapBase imageryYear={year || 2024} contour={contour} bbox={contour?.properties?.bbox}>
          {showS2 && scenes?.features?.map((f) => (
            <TileLayer key={f.properties.item_id} url={sentinel2TileUrl(f.properties.item_id)} minZoom={8} maxZoom={17} maxNativeZoom={16} opacity={0.95}
              attribution={`Copernicus Sentinel-2 ${f.properties.datetime?.slice(0, 10)}`} />
          ))}
          {showProtected && constraints?.protected?.features?.length > 0 && (
            <GeoJSON data={constraints.protected} style={{ color: "#10b981", weight: 1.5, fillOpacity: 0.08, dashArray: "4 3" }}
              onEachFeature={(f, l) => {
                // External data (WDPA): inserted as text, never as HTML.
                const tip = document.createElement("span");
                tip.textContent = `${f.properties.name} — ${f.properties.designation}${f.properties.level ? ` (protection ${f.properties.level})` : ""}`;
                l.bindTooltip(tip, { className: "tactical-tip" });
              }} />
          )}
          {data?.available && <GridLayer grid={data.grid} cells={data.cells} colorFor={colorFor} tooltip={tooltip} onSelect={onSelect} selected={selected} />}
          {visibleEquipments.map((e) => (
            <Marker key={e.id} position={[e.lat, e.lon]} icon={facilityIcon(e.category, e.status)}>
              <Tooltip className="tactical-tip">
                <b>{e.name || CATEGORY[e.category]?.label}</b><br />
                {CATEGORY[e.category]?.label} · {STATUS[e.status]?.label}
                {e.capacity ? <><br />{fmt(e.capacity)} {e.capacity_unit}</> : null}
                <br /><span style={{ color: "#64748b" }}>{e.source}</span>
                {e.imprecise && <><br /><span style={{ color: "#f5c542" }}>position approximative (centre du bourg)</span></>}
              </Tooltip>
            </Marker>
          ))}
        </MapBase>
        {selected && <CellPanel commune={commune} cell={selected} onClose={() => setSelected(null)} />}
        <div className="pointer-events-none absolute bottom-6 right-3 z-[999] hidden items-center gap-1 sm:flex border border-tactical-line bg-tactical-panel/90 px-2 py-1 text-[10px] text-slate-400">
          <Square size={10} /> carreaux de 200 m — aucune construction individuelle n&apos;est représentée
        </div>
        {data && !data.available && meta?.analysed && <div className="absolute left-1/2 top-4 z-[1000] max-w-[calc(100%-24px)] -translate-x-1/2"><Pill color="#f5c542">{data.reason || "Couche indisponible"}</Pill></div>}
      </div>
    </div>
  );
}
