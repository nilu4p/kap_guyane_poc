import { useCallback, useEffect, useState } from "react";
import { Rectangle } from "react-leaflet";
import { CheckCircle2, HelpCircle, ScanSearch, XCircle } from "lucide-react";
import MapBase, { FitBounds } from "../components/MapBase.jsx";
import { Button, ErrorBanner, Panel, Pill, Spinner } from "../components/ui.jsx";
import { fmt, hasRole, pct } from "../lib/format.js";
import { errorMessage, fetchValidation, recordVerdict } from "../services/api.js";

const VERDICT_COLORS = { bati: "#f59e0b", non_bati: "#3dff8a", incertain: "#94a3b8" };

/**
 * Visual control of the satellite layer: a reproducible sample of 200 m cells, each shown on the
 * cloudless mosaic of the year checked; the person says what they see, the platform measures the
 * agreement (success criterion of the brief: ≥ 80 % on 50 cells).
 */
export default function ValidationView({ user, commune, communeName }) {
  const [data, setData] = useState(null);
  const [year, setYear] = useState(null);
  const [index, setIndex] = useState(0);
  const [imagery, setImagery] = useState("EOX Sentinel-2 sans nuages");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback((y) => {
    setError("");
    fetchValidation(commune, y).then((d) => {
      setData(d);
      setYear(d.year);
      const next = d.cells.findIndex((c) => !c.my_verdict);
      setIndex(next >= 0 ? next : 0);
    }).catch((err) => setError(errorMessage(err)));
  }, [commune]);
  useEffect(() => load(null), [load]);

  // Without a sample there is nothing to show but the error; once loaded, a failed vote keeps the screen.
  if (!data) return error ? <div className="p-4"><ErrorBanner message={error} /></div> : <Spinner />;
  const cell = data.cells[index];
  const report = data.report;
  const done = data.cells.filter((c) => c.my_verdict).length;
  const canVote = hasRole(user, "analyst");

  const vote = async (verdict) => {
    setBusy(true);
    setError("");
    try {
      const res = await recordVerdict(commune, { cell: cell.cell, year, verdict, imagery });
      const cells = data.cells.map((c, k) => (k === index ? { ...c, my_verdict: verdict, predicted_share: res.predicted_share } : c));
      setData({ ...data, cells, report: res.report });
      const next = cells.findIndex((c, k) => k > index && !c.my_verdict);
      if (next >= 0) setIndex(next);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="split-view lg:grid-cols-[380px_1fr]">
      <aside className="split-pane space-y-3 border-t border-tactical-line p-3 text-xs lg:border-r lg:border-t-0">
        <div>
          <p className="text-[10px] uppercase tracking-[0.3em] text-tactical-cyan">Validation visuelle</p>
          <h1 className="text-lg text-white">Contrôle du bâti — {communeName}</h1>
          <p className="mt-1 text-slate-400">
            {data.cells.length} carreaux tirés au sort (moitié jugés bâtis, moitié non bâtis près des zones habitées). Pour chacun, dites ce que
            vous voyez sur l&apos;image : la plateforme mesure l&apos;accord. Objectif du dossier : ≥ 80 % sur 50 carreaux.
          </p>
        </div>
        <label className="flex items-center gap-2">Année contrôlée
          <select value={year} onChange={(e) => load(Number(e.target.value))} className="border border-tactical-line bg-tactical-bg px-2 py-1">
            {data.years.filter((y) => y >= 2016).map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
        <label className="block space-y-1">
          <span className="text-[10px] uppercase tracking-wider text-slate-500">Image utilisée pour juger</span>
          <input className="w-full border border-tactical-line bg-tactical-bg px-2 py-1" value={imagery} maxLength={80} onChange={(e) => setImagery(e.target.value)} />
          <span className="text-[10px] text-slate-600">L&apos;idéal : Pléiades / Pléiades Neo (SEAS Guyane), branchée en source personnalisée. La mosaïque EOX (≈ 10 m) suffit pour les cas francs.</span>
        </label>

        <Panel title="Accord avec la plateforme" icon={ScanSearch}>
          <dl className="grid grid-cols-3 gap-2">
            <div><dt className="text-slate-500">Accord</dt><dd className="text-lg" style={{ color: report.agreement == null ? "#94a3b8" : report.agreement >= report.target ? "#3dff8a" : "#f5c542" }}>{pct(report.agreement)}</dd></div>
            <div><dt className="text-slate-500">Jugés</dt><dd className="text-lg text-white">{report.decided}</dd></div>
            <div><dt className="text-slate-500">Incertains</dt><dd className="text-lg text-slate-400">{report.uncertain}</dd></div>
          </dl>
          <p className="mt-2 text-[11px] text-slate-400">Faux bâtis : {report.false_built} · bâti manqué : {report.missed_built}. {report.rule}.</p>
          <p className="mt-1 text-[11px]">{report.reached ? <Pill color="#3dff8a">Objectif atteint</Pill> : <span className="text-slate-500">Objectif : {Math.round(report.target * 100)} % sur au moins {Math.round(report.sample_size * 0.8)} carreaux jugés (tous contrôleurs confondus).</span>}</p>
        </Panel>

        <div className="flex flex-wrap gap-1">
          {data.cells.map((c, k) => (
            <button key={c.cell} type="button" onClick={() => setIndex(k)} title={c.cell}
              className={`h-6 w-6 border text-[9px] ${k === index ? "border-white" : "border-tactical-line"}`}
              style={{ background: c.my_verdict ? `${VERDICT_COLORS[c.my_verdict]}55` : "transparent" }}>
              {k + 1}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-slate-500">{done} / {data.cells.length} jugés par vous.</p>
        <ErrorBanner message={error} />
      </aside>
      <div className="split-map">
        {cell && (
          <>
            <MapBase imageryYear={year}>
              <FitBounds bbox={[cell.bounds[0] - 0.004, cell.bounds[1] - 0.004, cell.bounds[2] + 0.004, cell.bounds[3] + 0.004]} padding={10} />
              <Rectangle bounds={[[cell.bounds[1], cell.bounds[0]], [cell.bounds[3], cell.bounds[2]]]} pathOptions={{ color: "#ffffff", weight: 2, fill: false, dashArray: "5 4" }} />
            </MapBase>
            <div className="absolute bottom-6 left-1/2 z-[1000] w-[min(560px,90%)] -translate-x-1/2 border border-tactical-line bg-tactical-panel/95 p-3 text-xs">
              <p className="mb-2 text-slate-300">
                Carreau {index + 1} / {data.cells.length} ({cell.cell}) — <b>que voyez-vous dans le carré blanc en {year} ?</b>
                <span className="block text-[10px] text-slate-500">Bâti = au moins un cinquième du carreau couvert de constructions, toitures ou sols aménagés. La réponse de la plateforme reste masquée jusqu&apos;à votre vote.</span>
              </p>
              {canVote ? (
                <div className="flex flex-wrap gap-2">
                  <Button icon={CheckCircle2} busy={busy} onClick={() => vote("bati")}>Bâti</Button>
                  <Button icon={XCircle} busy={busy} onClick={() => vote("non_bati")}>Non bâti</Button>
                  <Button icon={HelpCircle} busy={busy} onClick={() => vote("incertain")}>Incertain (nuage, image floue)</Button>
                </div>
              ) : <p className="text-slate-500">Le vote est réservé aux chargés d&apos;études.</p>}
              {cell.my_verdict && (
                <p className="mt-2 text-[11px] text-slate-400">
                  Votre réponse : <b style={{ color: VERDICT_COLORS[cell.my_verdict] }}>{data.verdicts[cell.my_verdict]}</b> · plateforme : part bâtie {fmt(cell.predicted_share * 100)} % ({cell.predicted_share >= 0.2 ? "bâti" : "non bâti"})
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
