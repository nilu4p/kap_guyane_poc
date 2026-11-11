import { useEffect, useState } from "react";
import { FileSignature, RefreshCw, X } from "lucide-react";
import { Button, ErrorBanner, Field, Spinner, inputClass } from "../components/ui.jsx";
import { hasRole } from "../lib/format.js";
import { draftReport, errorMessage, issueReport } from "../services/api.js";

/**
 * Draft → preview → issue (sign) a decision document. Analysts preview, heads of department
 * (role "Responsable") issue: the text is then frozen, hashed, signed and registered.
 */
export default function ReportDialog({ user, kind, commune = null, scenarioId = null, since = 2019, title, onClose, navigate }) {
  const [form, setForm] = useState({ assessment: "", proposals: "", addressees: "" });
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const body = { kind, commune, scenario_id: scenarioId, since, ...form };
  const [previewed, setPreviewed] = useState(null);
  const stale = previewed !== JSON.stringify(form);

  const preview = async () => {
    setBusy("draft");
    setError("");
    try {
      setDraft(await draftReport(body));
      setPreviewed(JSON.stringify(form));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  };
  useEffect(() => {
    preview();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const issue = async () => {
    if (!window.confirm("Émettre et signer ce document ? Son texte sera figé, haché (SHA-256), signé et inscrit au registre.")) return;
    setBusy("issue");
    setError("");
    try {
      const report = await issueReport(body);
      onClose();
      navigate("rapports", String(report.id));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="fixed inset-0 z-[3000] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="flex max-h-full w-full max-w-5xl flex-col border border-tactical-line bg-tactical-panel" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between border-b border-tactical-line px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm text-white"><FileSignature size={16} className="text-tactical-cyan" /> {title}</h2>
          <button type="button" onClick={onClose} aria-label="Fermer" className="text-slate-400 hover:text-white"><X size={18} /></button>
        </header>
        <div className="grid grid-cols-1 min-h-0 flex-1 gap-4 overflow-y-auto p-4 lg:grid-cols-[320px_1fr]">
          <div className="space-y-3">
            <Field label="Destinataires"><input className={inputClass} value={form.addressees} onChange={(e) => setForm({ ...form, addressees: e.target.value })} placeholder="Maire, DGS, conseil municipal…" maxLength={600} /></Field>
            <Field label="Appréciation des services"><textarea className={`${inputClass} h-28`} value={form.assessment} maxLength={8000} onChange={(e) => setForm({ ...form, assessment: e.target.value })} /></Field>
            <Field label="Propositions"><textarea className={`${inputClass} h-28`} value={form.proposals} maxLength={8000} onChange={(e) => setForm({ ...form, proposals: e.target.value })} /></Field>
            <div className="flex flex-wrap gap-2">
              <Button icon={RefreshCw} busy={busy === "draft"} onClick={preview}>Mettre à jour l&apos;aperçu</Button>
              {hasRole(user, "supervisor") ? (
                <Button variant="primary" icon={FileSignature} busy={busy === "issue"} onClick={issue} disabled={!draft || stale}
                  title={stale ? "Mettez d'abord l'aperçu à jour : le document signé est celui que vous avez relu" : undefined}>Émettre et signer</Button>
              ) : (
                <p className="text-[11px] text-slate-500">L&apos;émission (signature) est réservée au rôle « Responsable ».</p>
              )}
            </div>
            <ErrorBanner message={error} />
          </div>
          <div className="min-h-[300px] overflow-auto">
            {!draft ? <Spinner label="Préparation du projet…" /> : <pre className="report-paper">{draft.content}</pre>}
          </div>
        </div>
      </div>
    </div>
  );
}
