import { useCallback, useEffect, useMemo, useState } from "react";
import { Marker, Tooltip, useMapEvents } from "react-leaflet";
import { LandPlot, Plus, Save, Trash2 } from "lucide-react";
import MapBase from "../components/MapBase.jsx";
import { Button, ErrorBanner, Field, Panel, Pill, Spinner, inputClass } from "../components/ui.jsx";
import { fmt, hasRole } from "../lib/format.js";
import { createEquipment, deleteEquipment, errorMessage, fetchCategories, fetchContour, fetchEquipments, updateEquipment } from "../services/api.js";
import { CATEGORY, STATUS } from "../theme.js";
import { facilityIcon } from "./AtlasView.jsx";

const EMPTY = { category: "ecole", subtype: "", name: "", lat: "", lon: "", capacity: "", capacity_unit: "", status: "projet", note: "" };

function Picker({ active, onPick }) {
  useMapEvents({ click: (e) => active && onPick(e.latlng) });
  return null;
}

export default function EquipementsView({ user, commune, communeName }) {
  const [items, setItems] = useState(null);
  const [categories, setCategories] = useState([]);
  const [contour, setContour] = useState(null);
  const [filter, setFilter] = useState("");
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const canEdit = hasRole(user, "analyst");

  const load = useCallback(() => fetchEquipments(commune).then((d) => setItems(d.equipments)).catch((err) => setError(errorMessage(err))), [commune]);
  useEffect(() => {
    load();
    fetchCategories().then((d) => setCategories(d.categories)).catch(() => {});
    fetchContour(commune).then(setContour).catch(() => {});
  }, [commune, load]);

  const visible = useMemo(() => (items || []).filter((e) => !filter || e.category === filter), [items, filter]);
  // Position typed by hand: drawn only once it is a valid number (Leaflet throws on NaN while typing "5," or "-").
  const preview = useMemo(() => {
    if (!form || form.lat === "" || form.lon === "") return null;
    const lat = Number(String(form.lat).trim().replace(",", "."));
    const lon = Number(String(form.lon).trim().replace(",", "."));
    return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? [lat, lon] : null;
  }, [form]);

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const lat = Number(String(form.lat).trim().replace(",", ".")); // French decimal comma accepted
      const lon = Number(String(form.lon).trim().replace(",", "."));
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) throw new Error("Latitude et longitude doivent être des nombres (ex. 5.4930 et -54.0300)");
      // Only the fields of the API model (the facility read back carries ids, source, corrections…).
      const body = { category: form.category, subtype: form.subtype || "", name: form.name || "", status: form.status, note: form.note || "",
        capacity_unit: form.capacity_unit || "", commune: form.commune_code || commune, lat, lon,
        capacity: form.capacity === "" || form.capacity == null ? null : Number(form.capacity) };
      if (form.id) await updateEquipment(form.id, body);
      else await createEquipment(body);
      setForm(null);
      load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Supprimer cet équipement ?")) return;
    setBusy(true);
    setError("");
    try {
      await deleteEquipment(form.id);
      setForm(null);
      load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const edit = (e) => {
    if (!canEdit) return;
    setError("");
    setForm({ ...EMPTY, ...e, subtype: e.subtype || "", name: e.name || "", capacity: e.capacity ?? "", capacity_unit: e.capacity_unit || "",
      note: e.attributes?.note || "" });
  };

  return (
    <div className="split-view lg:grid-cols-[1fr_520px]">
      <div className="split-map">
        <MapBase contour={contour} bbox={contour?.properties?.bbox} baseDefault="osm">
          <Picker active={!!form} onPick={(p) => setForm((f) => ({ ...f, lat: p.lat.toFixed(6), lon: p.lng.toFixed(6) }))} />
          {visible.map((e) => (
            <Marker key={e.id} position={[e.lat, e.lon]} icon={facilityIcon(e.category, e.status)} eventHandlers={{ click: () => edit(e) }}>
              <Tooltip className="tactical-tip"><b>{e.name || CATEGORY[e.category]?.label}</b><br />{STATUS[e.status]?.label} · {e.source}</Tooltip>
            </Marker>
          ))}
          {preview && <Marker position={preview} icon={facilityIcon(form.category, "projet")} />}
        </MapBase>
      </div>
      <aside className="split-pane space-y-3 border-t border-tactical-line p-3 text-xs lg:border-l lg:border-t-0">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.3em] text-tactical-cyan">Équipements</p>
            <h1 className="text-lg text-white">{communeName}</h1>
          </div>
          {canEdit && !form && <Button icon={Plus} variant="primary" onClick={() => setForm({ ...EMPTY })}>Ajouter</Button>}
        </div>
        <p className="text-[11px] text-slate-500">
          Écoles, collèges et lycées : annuaire de l&apos;Éducation nationale (effectifs et classes). Les établissements que la source ne
          situe qu&apos;au centre du bourg sont marqués « position approximative » : corrigez leur position pour fiabiliser les distances. Santé, eau, commerces, transport, services : OpenStreetMap,
          dont la complétude est inégale en Guyane. Les services ajoutent ici les équipements manquants, provisoires ou en projet : ils sont pris en compte
          dans l&apos;accessibilité et l&apos;aide à l&apos;implantation.
        </p>
        <ErrorBanner message={error} />
        {form && (
          <Panel title={form.id ? "Modifier l'équipement" : "Nouvel équipement"} icon={LandPlot}>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Catégorie">
                <select className={inputClass} value={form.category} disabled={form.id && form.source !== "saisie"} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                </select>
              </Field>
              <Field label="Statut">
                <select className={inputClass} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  {Object.entries(STATUS).filter(([k]) => k !== "scenario").map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
              </Field>
              <Field label="Nom"><input className={inputClass} value={form.name} disabled={form.id && form.source !== "saisie"} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
              <Field label="Type précis"><input className={inputClass} value={form.subtype} disabled={form.id && form.source !== "saisie"} onChange={(e) => setForm({ ...form, subtype: e.target.value })} placeholder="ex. borne-fontaine" /></Field>
              <Field label="Latitude" hint="cliquer la carte"><input className={inputClass} value={form.lat} onChange={(e) => setForm({ ...form, lat: e.target.value })} /></Field>
              <Field label="Longitude"><input className={inputClass} value={form.lon} onChange={(e) => setForm({ ...form, lon: e.target.value })} /></Field>
              <Field label="Capacité"><input className={inputClass} type="number" value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} /></Field>
              <Field label="Unité"><input className={inputClass} value={form.capacity_unit} onChange={(e) => setForm({ ...form, capacity_unit: e.target.value })} placeholder="élèves, places…" /></Field>
              <div className="col-span-2"><Field label="Note"><input className={inputClass} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></Field></div>
            </div>
            {form.id && form.source !== "saisie" && (
              <p className="mt-2 text-[10px] text-slate-500">
                Équipement issu des données ouvertes ({form.source}) : position, capacité, statut et note sont des <b>corrections locales</b>,
                conservées lors des synchronisations (nom et catégorie restent ceux de la source).
                {form.imprecise && <span className="block text-tactical-amber">Position approximative dans la source (centre du bourg ou du lieu-dit) : cliquez la carte pour placer l&apos;établissement.</span>}
              </p>
            )}
            <div className="mt-3 flex gap-2">
              <Button variant="primary" icon={Save} busy={busy} onClick={save} disabled={!form.lat || !form.lon}>Enregistrer</Button>
              <Button onClick={() => setForm(null)}>Annuler</Button>
              {form.id && form.source === "saisie" && (
                <Button variant="danger" icon={Trash2} busy={busy} onClick={remove}>Supprimer</Button>
              )}
            </div>
          </Panel>
        )}
        <div className="flex flex-wrap gap-1">
          <button type="button" onClick={() => setFilter("")} className={`border px-2 py-1 ${!filter ? "border-tactical-cyan text-tactical-cyan" : "border-tactical-line text-slate-400"}`}>Tous ({items?.length ?? 0})</button>
          {Object.entries(CATEGORY).map(([id, c]) => (
            <button key={id} type="button" onClick={() => setFilter(id)} className={`border px-2 py-1 ${filter === id ? "border-tactical-cyan text-tactical-cyan" : "border-tactical-line text-slate-400"}`}>
              {c.short} ({(items || []).filter((e) => e.category === id).length})
            </button>
          ))}
        </div>
        {!items ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="py-1">Nom</th><th>Statut</th><th className="text-right">Capacité</th><th>Source</th></tr></thead>
              <tbody>
                {visible.map((e) => (
                  <tr key={e.id} className="cursor-pointer border-t border-tactical-line hover:bg-white/5" onClick={() => edit(e)}>
                    <td className="py-1.5"><span className="mr-1 inline-block h-2 w-2 rotate-45" style={{ background: CATEGORY[e.category]?.color }} />{e.name || CATEGORY[e.category]?.label}
                      <span className="block text-[10px] text-slate-600">{e.subtype}
                        {e.imprecise && <span className="ml-1 text-tactical-amber" title="Géolocalisée au centre du bourg / lieu-dit dans la source">· position approximative</span>}
                        {e.correction && <span className="ml-1 text-tactical-cyan" title={`par ${e.correction.by}`}>· corrigé ({e.correction.fields.join(", ") || "note"})</span>}
                      </span></td>
                    <td><Pill color={STATUS[e.status]?.color}>{STATUS[e.status]?.label}</Pill></td>
                    <td className="text-right tabular-nums">{e.capacity ? `${fmt(e.capacity)} ${e.capacity_unit}` : "—"}</td>
                    <td className="text-[10px] text-slate-500">{e.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </aside>
    </div>
  );
}
