import { useEffect, useMemo, useState } from "react";
import { GeoJSON } from "react-leaflet";
import { Database, Info, LayoutDashboard, ListOrdered } from "lucide-react";
import MapBase from "../components/MapBase.jsx";
import { ErrorBanner, Panel, Spinner } from "../components/ui.jsx";
import { fmt, formatDateTime } from "../lib/format.js";
import { errorMessage, fetchCommunes, fetchDataStatus, fetchTerritoryKpis } from "../services/api.js";
import { CHORO, CHORO_BAD } from "../theme.js";

const HEADLINE = ["population", "croissance_pop", "naissances", "eleves_1er_degre", "medecins", "sans_electricite", "eau_froide_sans_point", "chomage"];

function quantileBreaks(values, n = 5) {
  const sorted = [...values].sort((a, b) => a - b);
  return [...Array(n - 1)].map((_, i) => sorted[Math.floor(((i + 1) * sorted.length) / n)] ?? sorted[sorted.length - 1]);
}

export default function TerritoireView({ navigate }) {
  const [data, setData] = useState(null);
  const [geo, setGeo] = useState(null);
  const [fresh, setFresh] = useState(null);
  const [kpi, setKpi] = useState("croissance_pop");
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([fetchTerritoryKpis(), fetchCommunes(true)])
      .then(([k, c]) => {
        setData(k);
        setGeo(c.communes);
      })
      .catch((err) => setError(errorMessage(err)));
    fetchDataStatus().then(setFresh).catch(() => {});
  }, []);

  const spec = data?.kpis.find((k) => k.id === kpi);
  const values = useMemo(() => {
    if (!data) return {};
    return Object.fromEntries(data.communes.map((c) => [c.code, data.values[c.code]?.[kpi]?.value]).filter(([, v]) => v != null));
  }, [data, kpi]);
  const breaks = useMemo(() => quantileBreaks(Object.values(values)), [values]);
  const palette = spec?.better === "lower" ? CHORO_BAD : CHORO;
  const colorOf = (v) => {
    if (v == null) return "#1e293b";
    let k = 0;
    while (k < breaks.length && v > breaks[k]) k += 1;
    return palette[k];
  };
  const collection = useMemo(
    () => geo && { type: "FeatureCollection", features: geo.map((c) => ({ type: "Feature", geometry: c.contour, properties: { code: c.code, nom: c.nom } })) },
    [geo],
  );

  if (error) return <div className="p-4"><ErrorBanner message={error} /></div>;
  if (!data || !geo) return <Spinner label="Chargement des indicateurs des 22 communes…" />;
  const dep = data.values[data.department.code] || {};
  const ranking = data.communes
    .map((c) => ({ ...c, value: values[c.code], year: data.values[c.code]?.[kpi]?.year }))
    .filter((c) => c.value != null)
    .sort((a, b) => (spec?.better === "lower" ? a.value - b.value : b.value - a.value));
  const themes = [...new Set(data.kpis.map((k) => k.theme))];

  return (
    <div className="split-view lg:grid-cols-[1fr_420px]">
      <div className="split-map">
        <MapBase bbox={[-54.62, 2.11, -51.61, 5.78]} baseDefault="osm">
          <GeoJSON
            key={kpi}
            data={collection}
            style={(f) => ({ color: "#0f172a", weight: 1, fillColor: colorOf(values[f.properties.code]), fillOpacity: 0.78 })}
            onEachFeature={(f, layer) => {
              const v = values[f.properties.code];
              // Built as DOM text (no HTML string): names come from an external API.
              const tip = document.createElement("span");
              const name = document.createElement("b");
              name.textContent = f.properties.nom;
              tip.append(name, document.createElement("br"), `${spec?.label} : ${v != null ? fmt(v, spec?.decimals ?? 0) : "—"} ${spec?.unit || ""}`);
              layer.bindTooltip(tip, { sticky: true, className: "tactical-tip" });
              layer.on("click", () => navigate("commune", f.properties.code));
            }}
          />
        </MapBase>
        <div className="absolute bottom-6 left-3 z-[1000] w-[min(18rem,calc(100%-24px))] border border-tactical-line bg-tactical-panel/95 p-3 text-xs">
          <label className="mb-2 block text-[10px] uppercase tracking-wider text-slate-500">Indicateur cartographié</label>
          <select value={kpi} onChange={(e) => setKpi(e.target.value)} className="w-full border border-tactical-line bg-tactical-bg px-2 py-1.5 text-slate-100">
            {themes.map((t) => (
              <optgroup key={t} label={data.themes[t]}>
                {data.kpis.filter((k) => k.theme === t).map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
              </optgroup>
            ))}
          </select>
          <div className="mt-2 flex items-center gap-1">
            {palette.map((c, i) => (
              <div key={c} className="flex-1">
                <div className="h-2" style={{ background: c }} />
                <p className="mt-0.5 text-center text-[9px] text-slate-500">{i === 0 ? "≤ " : "> "}{fmt(i === 0 ? breaks[0] : breaks[i - 1], spec?.decimals ?? 0)}</p>
              </div>
            ))}
          </div>
          <p className="mt-1 text-[10px] text-slate-500">{spec?.unit} · quintiles · {spec?.better === "lower" ? "rouge = situation plus difficile" : spec?.better === "higher" ? "clair = mieux doté" : "clair = valeur élevée"}</p>
          <p className="mt-1 text-[10px] text-slate-600">Cliquer une commune pour ouvrir sa fiche.</p>
        </div>
      </div>
      <div className="split-pane space-y-3 border-t border-tactical-line p-3 lg:border-l lg:border-t-0">
        <Panel title="Guyane — chiffres clés" icon={LayoutDashboard}>
          <dl className="grid grid-cols-2 gap-3">
            {HEADLINE.map((id) => {
              const k = data.kpis.find((x) => x.id === id);
              const v = dep[id];
              return (
                <div key={id} className="border-l-2 border-tactical-cyan/40 pl-2">
                  <dt className="text-[10px] leading-tight text-slate-500">{k?.label}</dt>
                  <dd className="text-base tabular-nums text-white">{v ? fmt(v.value, k.decimals) : "—"} <span className="text-[10px] text-slate-500">{k?.unit}</span></dd>
                  <dd className="text-[10px] text-slate-600">{v?.year}</dd>
                </div>
              );
            })}
          </dl>
        </Panel>
        <Panel title={`Classement — ${spec?.label}`} icon={ListOrdered}>
          <ol className="space-y-1 text-xs">
            {ranking.map((c, i) => (
              <li key={c.code}>
                <button type="button" onClick={() => navigate("commune", c.code)} className="flex w-full items-center gap-2 text-left hover:text-tactical-cyan">
                  <span className="w-5 text-right text-slate-500">{i + 1}</span>
                  <span className="h-2.5 w-2.5 shrink-0" style={{ background: colorOf(c.value) }} />
                  <span className="flex-1 truncate">{c.nom}</span>
                  <span className="tabular-nums text-slate-300">{fmt(c.value, spec?.decimals ?? 0)}</span>
                </button>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-[10px] text-slate-500">Guyane : {dep[kpi] ? fmt(dep[kpi].value, spec?.decimals ?? 0) : "—"} {spec?.unit}. {spec?.formula}</p>
          <p className="mt-1 text-[10px] text-slate-600">Source : {spec?.sources.join(" ; ")}</p>
        </Panel>
        <Panel title="Fraîcheur des données" icon={Database}>
          {!fresh ? <Spinner /> : (
            <ul className="space-y-1 text-[11px]">
              {fresh.sources.map((s) => (
                <li key={s.id} className="flex justify-between gap-2">
                  <span className="truncate text-slate-400" title={s.label}>{s.label}</span>
                  <span className="shrink-0 text-slate-500">{formatDateTime(s.retrieved_at)}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 flex items-start gap-1 text-[10px] text-slate-600">
            <Info size={11} className="mt-0.5 shrink-0" /> FiLoSoFi (revenus) n&apos;est pas diffusé pour les communes de Guyane : aucun indicateur de revenu n&apos;est affiché.
          </p>
        </Panel>
      </div>
    </div>
  );
}
