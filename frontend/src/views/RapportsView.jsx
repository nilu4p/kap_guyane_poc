import { useCallback, useEffect, useState } from "react";
import { Download, FileSignature, Printer, ShieldCheck, ShieldX } from "lucide-react";
import { Button, Empty, ErrorBanner, Panel, Pill, Spinner } from "../components/ui.jsx";
import { formatDateTime } from "../lib/format.js";
import { downloadReport, downloadRootCertificate, errorMessage, fetchReport, fetchReports, verifyReport } from "../services/api.js";
import Printable from "../components/Printable.jsx";

export default function RapportsView({ communes, selected, navigate }) {
  const [list, setList] = useState(null);
  const [report, setReport] = useState(null);
  const [check, setCheck] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => fetchReports().then((d) => setList(d.reports)).catch((err) => setError(errorMessage(err))), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    setCheck(null);
    setError("");
    if (!selected) {
      setReport(null);
      return undefined;
    }
    let current = true;
    fetchReport(selected).then((d) => current && setReport(d.report)).catch((err) => current && setError(errorMessage(err)));
    return () => { current = false; };
  }, [selected]);

  const name = (code) => communes.find((c) => c.code === code)?.nom || code || "—";

  return (
    <div className="split-view lg:grid-cols-[420px_1fr]">
      <aside className="split-pane border-tactical-line p-3 text-xs lg:border-r">
        <p className="text-[10px] uppercase tracking-[0.3em] text-tactical-cyan">Registre</p>
        <h1 className="mb-1 text-lg text-white">Documents de décision signés</h1>
        <p className="mb-3 text-[11px] text-slate-500">
          Diagnostics, dossiers d&apos;implantation et listes Recensement Éclaireur émis par les responsables : texte figé, haché (SHA-256) et signé (ECDSA,
          PKI de l&apos;instance). Les projets se préparent depuis les fiches commune, l&apos;aide à la décision et la veille.
        </p>
        <button type="button" onClick={() => downloadRootCertificate().catch((err) => setError(errorMessage(err)))}
          className="mb-3 text-[11px] text-tactical-cyan underline" title="Pour vérifier une signature hors de la plateforme (openssl)">
          Télécharger le certificat racine de l&apos;instance
        </button>
        <ErrorBanner message={error} />
        {!list ? <Spinner /> : list.length === 0 ? <Empty>Aucun document émis.</Empty> : (
          <ul className="space-y-1">
            {list.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => navigate("rapports", String(r.id))}
                  className={`w-full border p-2 text-left ${String(r.id) === selected ? "border-tactical-cyan" : "border-tactical-line"} hover:border-tactical-cyan/60`}>
                  <div className="flex items-center justify-between gap-2"><span className="font-mono text-white">{r.ref}</span>{r.signed ? <Pill color="#3dff8a">signé</Pill> : <Pill color="#f5c542">non signé</Pill>}</div>
                  <p className="truncate text-slate-300">{r.title}</p>
                  <p className="text-[10px] text-slate-500">{r.kind_label} · {name(r.commune_code)} · {formatDateTime(r.created_at)} · {r.created_by}</p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
      {/* On a narrow screen the open document comes before the registry. */}
      <div className={`split-pane border-tactical-line p-4 ${selected ? "order-first border-b lg:order-none lg:border-b-0" : "border-t lg:border-t-0"}`}>
        {!report ? <Empty>Sélectionnez un document du registre.</Empty> : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button icon={ShieldCheck} onClick={() => verifyReport(report.id).then(setCheck).catch((err) => setError(errorMessage(err)))}>Vérifier l&apos;intégrité</Button>
              <Button icon={Download} onClick={() => downloadReport(report.id, report.ref).catch((err) => setError(errorMessage(err, "Export impossible")))}>Exporter (texte + scellement)</Button>
              <Button icon={Printer} onClick={() => window.print()}>Imprimer / PDF</Button>
              {check && (
                <span className={`flex items-center gap-1 text-xs ${check.valid ? "text-tactical-green" : "text-tactical-red"}`}>
                  {check.valid ? <ShieldCheck size={14} /> : <ShieldX size={14} />}
                  {check.valid ? "Intègre : empreinte, signature et chaîne de certificats vérifiées" : "ALTÉRÉ : le texte ne correspond plus à sa signature"}
                </span>
              )}
            </div>
            <Panel title={`${report.ref} — ${report.kind_label}`} icon={FileSignature}>
              <p className="mb-2 break-all text-[10px] text-slate-500">SHA-256 {report.sha256} · certificat {report.cert_fingerprint?.slice(0, 16)}…</p>
              <Printable>
                <pre className="report-paper">{report.content}</pre>
              </Printable>
            </Panel>
          </div>
        )}
      </div>
    </div>
  );
}
