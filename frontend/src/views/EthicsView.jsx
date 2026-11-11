import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { ErrorBanner, Panel, Spinner } from "../components/ui.jsx";
import { errorMessage, fetchEthics } from "../services/api.js";

export default function EthicsView() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    fetchEthics().then(setData).catch((err) => setError(errorMessage(err)));
  }, []);
  if (error) return <div className="p-4"><ErrorBanner message={error} /></div>;
  if (!data) return <Spinner />;
  return (
    <div className="mx-auto h-full max-w-4xl space-y-4 overflow-y-auto p-4 sm:p-6">
      <div>
        <p className="text-[10px] uppercase tracking-[0.3em] text-tactical-green">Éthique dès la conception</p>
        <h1 className="text-2xl text-white">{data.title}</h1>
        <p className="mt-1 text-sm text-slate-400">« Pas une seule maison n&apos;est désignée : c&apos;est un outil de planification, pas de contrôle. »</p>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {data.principles.map((p) => (
          <Panel key={p.title} title={p.title} icon={ShieldCheck}>
            <p className="text-sm text-slate-300">{p.text}</p>
          </Panel>
        ))}
      </div>
      <Panel title="Références" icon={ShieldCheck}>
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-400">
          {data.references.map((r) => <li key={r}>{r}</li>)}
        </ul>
      </Panel>
    </div>
  );
}
