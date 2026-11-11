import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import {
  Building2,
  FileSignature,
  LandPlot,
  LayoutDashboard,
  Map as MapIcon,
  Radar,
  Satellite,
  ScanSearch,
  ScrollText,
  Settings,
  ShieldCheck,
  Target,
} from "lucide-react";
import { AppShell, SessionGate } from "./components/AppShell.jsx";
import CommunePicker from "./components/CommunePicker.jsx";
import { Spinner } from "./components/ui.jsx";
import { hasRole, storage } from "./lib/format.js";
import { fetchCommunes } from "./services/api.js";

// Views load on demand: the first screen does not download the administration or the map code.
const TerritoireView = lazy(() => import("./views/TerritoireView.jsx"));
const CommuneView = lazy(() => import("./views/CommuneView.jsx"));
const AtlasView = lazy(() => import("./views/AtlasView.jsx"));
const DecisionView = lazy(() => import("./views/DecisionView.jsx"));
const VeilleView = lazy(() => import("./views/VeilleView.jsx"));
const EquipementsView = lazy(() => import("./views/EquipementsView.jsx"));
const AnalysesView = lazy(() => import("./views/AnalysesView.jsx"));
const ValidationView = lazy(() => import("./views/ValidationView.jsx"));
const RapportsView = lazy(() => import("./views/RapportsView.jsx"));
const EthicsView = lazy(() => import("./views/EthicsView.jsx"));
const AuditView = lazy(() => import("./views/AuditView.jsx"));
const AdminView = lazy(() => import("./views/AdminView.jsx"));

// ``commune``: the view is about one commune (its code follows in the address).
const NAV = [
  { id: "territoire", label: "Territoire", icon: LayoutDashboard, role: "viewer", commune: false, hint: "Les 22 communes comparées" },
  { id: "commune", label: "Commune", icon: Building2, role: "viewer", commune: true, hint: "Fiche statistique de la commune" },
  { id: "atlas", label: "Atlas", icon: MapIcon, role: "viewer", commune: true, hint: "Carte multi-couches et imagerie satellite" },
  { id: "decision", label: "Décision", icon: Target, role: "viewer", commune: true, hint: "Où implanter les équipements" },
  { id: "veille", label: "Veille", icon: Radar, role: "viewer", commune: true, hint: "Quartiers en croissance, Recensement Éclaireur" },
  { id: "equipements", label: "Équipements", icon: LandPlot, role: "viewer", commune: true, hint: "Inventaire et saisie des équipements" },
  { id: "analyses", label: "Analyses", icon: Satellite, role: "viewer", commune: false, hint: "Analyses satellitaires et données ouvertes" },
  { id: "validation", label: "Validation", icon: ScanSearch, role: "viewer", commune: true, hint: "Contrôle visuel du bâti satellitaire (50 carreaux)" },
  { id: "rapports", label: "Rapports", icon: FileSignature, role: "viewer", commune: false, hint: "Documents de décision signés" },
  { id: "audit", label: "Audit", icon: ScrollText, role: "supervisor", commune: false, hint: "Journal d'audit chaîné" },
  { id: "admin", label: "Administration", icon: Settings, role: "admin", commune: false, hint: "Comptes, paramètres, sources" },
];

/** "#/atlas/97311" → { view: "atlas", param: "97311" } */
function parseHash() {
  const [, view = "territoire", param = "", extra = ""] = window.location.hash.split("/");
  const known = NAV.some((n) => n.id === view) || view === "ethique";
  return { view: known ? view : "territoire", param, extra };
}

function CharterLink({ onClick, className }) {
  return (
    <a href="#/ethique" onClick={onClick} title="Charte d'usage : agrégation 200 m, aucun usage de contrôle" className={className}>
      <ShieldCheck size={12} /> Charte 200 m
    </a>
  );
}

function Console({ user, onLogout, onUserChange }) {
  const [route, setRoute] = useState(parseHash());
  const [communes, setCommunes] = useState(null);
  const [defaultCommune, setDefaultCommune] = useState("97311");

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const reloadCommunes = useCallback(() => {
    fetchCommunes(false)
      .then((d) => {
        setCommunes(d.communes);
        setDefaultCommune(d.default);
      })
      .catch(() => setCommunes([]));
  }, []);
  useEffect(() => { reloadCommunes(); }, [reloadCommunes]);

  const navigate = useCallback((view, param = "", extra = "") => {
    window.location.hash = `#/${view}${param ? `/${param}` : ""}${extra ? `/${extra}` : ""}`;
  }, []);

  const allowed = NAV.filter((n) => hasRole(user, n.role));
  const current = route.view === "ethique" ? "ethique" : allowed.some((n) => n.id === route.view) ? route.view : "territoire";
  const spec = NAV.find((n) => n.id === current);
  const remembered = storage.get("commune");
  const commune = /^\d{5}$/.test(route.param) ? route.param : /^\d{5}$/.test(remembered || "") ? remembered : defaultCommune;
  useEffect(() => {
    if (commune) storage.set("commune", commune);
  }, [commune]);
  const setCommune = (code) => navigate(spec?.commune ? current : "commune", code);
  const communeName = communes?.find((c) => c.code === commune)?.nom || commune;

  return (
    <AppShell
      user={user}
      nav={allowed}
      current={current}
      viewKey={`${current}:${commune}`}
      hrefFor={(item) => `#/${item.id}${item.commune && commune ? `/${commune}` : ""}`}
      onLogout={onLogout}
      onUserChange={onUserChange}
      headerExtras={
        <>
          {spec?.commune && <CommunePicker communes={communes} value={commune} onChange={setCommune} />}
          <CharterLink className="hidden items-center gap-1 border border-tactical-green/40 px-2 py-1 text-[10px] uppercase tracking-wider text-tactical-green lg:flex" />
        </>
      }
      drawerExtras={(close) => (
        <CharterLink onClick={close} className="flex items-center gap-1 border border-tactical-green/40 px-2 py-1 text-[10px] uppercase tracking-wider text-tactical-green" />
      )}
      menuExtras={(close) => (
        <a href="#/ethique" role="menuitem" onClick={close} className="flex w-full items-center gap-2 border-b border-tactical-line px-4 py-3 text-left text-xs text-tactical-green hover:bg-white/5 lg:hidden">
          <ShieldCheck size={14} /> Charte d&apos;usage (200 m)
        </a>
      )}
    >
      <Suspense fallback={<div className="flex h-full items-center justify-center"><Spinner /></div>}>
        {!communes ? (
          <Spinner label="Chargement du territoire…" />
        ) : (
          <>
            {current === "territoire" && <TerritoireView user={user} navigate={navigate} />}
            {current === "commune" && <CommuneView user={user} commune={commune} communeName={communeName} navigate={navigate} />}
            {current === "atlas" && <AtlasView user={user} commune={commune} communeName={communeName} navigate={navigate} />}
            {current === "decision" && <DecisionView user={user} commune={commune} communeName={communeName} navigate={navigate} />}
            {current === "veille" && <VeilleView user={user} commune={commune} communeName={communeName} navigate={navigate} />}
            {current === "equipements" && <EquipementsView user={user} commune={commune} communeName={communeName} />}
            {current === "validation" && <ValidationView user={user} commune={commune} communeName={communeName} />}
            {current === "analyses" && <AnalysesView user={user} communes={communes} navigate={navigate} onChange={reloadCommunes} />}
            {current === "rapports" && <RapportsView user={user} communes={communes} selected={route.param} navigate={navigate} />}
            {current === "ethique" && <EthicsView />}
            {current === "audit" && <AuditView />}
            {current === "admin" && <AdminView user={user} />}
          </>
        )}
      </Suspense>
    </AppShell>
  );
}

export default function App() {
  return <SessionGate>{(user, session) => <Console user={user} {...session} />}</SessionGate>;
}
