import { MapPin } from "lucide-react";

/** Commune selector shared by every territorial view (✓ = satellite analysis available). */
export default function CommunePicker({ communes, value, onChange, className = "" }) {
  return (
    <label className={`flex min-w-0 items-center gap-2 text-xs ${className}`}>
      <MapPin size={14} className="shrink-0 text-tactical-cyan" />
      <span className="sr-only">Commune</span>
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-0 max-w-[11rem] border border-tactical-line sm:max-w-none bg-tactical-bg px-2 py-1.5 text-slate-100 focus:border-tactical-cyan/60 focus:outline-none"
      >
        {(communes || []).map((c) => (
          <option key={c.code} value={c.code}>
            {c.nom}
            {c.analysed_at ? " ✓" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
