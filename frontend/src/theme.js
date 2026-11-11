// Single source of truth for the colours of the map, legends and charts.

export const CATEGORY = {
  ecole: { color: "#60a5fa", label: "École (maternelle / élémentaire)", short: "Écoles" },
  college: { color: "#a78bfa", label: "Collège", short: "Collèges" },
  lycee: { color: "#c084fc", label: "Lycée", short: "Lycées" },
  sante: { color: "#f87171", label: "Santé", short: "Santé" },
  eau: { color: "#22d3ee", label: "Point d'eau potable", short: "Eau" },
  alimentation: { color: "#fb923c", label: "Commerce alimentaire / marché", short: "Alimentation" },
  transport: { color: "#4ade80", label: "Transport", short: "Transport" },
  services: { color: "#cbd5e1", label: "Services publics", short: "Services" },
  petite_enfance: { color: "#f472b6", label: "Petite enfance", short: "Petite enfance" },
};

export const STATUS = {
  existant: { color: "#94a3b8", label: "Existant" },
  provisoire: { color: "#f5c542", label: "Provisoire" },
  projet: { color: "#2dd4bf", label: "En projet" },
  scenario: { color: "#ffffff", label: "Site du scénario" },
};

// Sequential palettes (dark background): light value = more. Validated for contrast on #070b10.
const BUILT = ["#1e293b", "#334155", "#7c5c3b", "#b7791f", "#f59e0b", "#fde68a"];
const GROWTH = ["#3f1d5c", "#6d28d9", "#a21caf", "#e11d48", "#fb7185", "#fecdd3"];
const PEOPLE = ["#0c4a6e", "#0369a1", "#0ea5e9", "#38bdf8", "#7dd3fc", "#e0f2fe"];
const KIDS = ["#14532d", "#15803d", "#22c55e", "#4ade80", "#86efac", "#dcfce7"];
const WATER = ["#082f49", "#0c4a6e", "#075985", "#0369a1", "#0284c7", "#38bdf8"];

export const LAYERS = {
  bati: { label: "Part bâtie du carreau", palette: BUILT, breaks: [0.02, 0.1, 0.25, 0.45, 0.7], unit: "", format: (v) => `${Math.round(v * 100)} %` },
  croissance: { label: "Surface bâtie gagnée", palette: GROWTH, breaks: [0.1, 0.3, 0.6, 1, 2], unit: "ha", format: (v) => `${v > 0 ? "+" : ""}${v.toFixed(2)} ha` },
  population: { label: "Habitants estimés", palette: PEOPLE, breaks: [10, 50, 150, 300, 600], unit: "hab.", format: (v) => `${Math.round(v)} hab.` },
  enfants: { label: "Enfants de 3 à 10 ans estimés", palette: KIDS, breaks: [3, 10, 30, 60, 120], unit: "enf.", format: (v) => `${Math.round(v)} enfants` },
  batiments: { label: "Bâtiments (empreintes Microsoft)", palette: BUILT, breaks: [2, 10, 25, 50, 90], unit: "bât.", format: (v) => `${Math.round(v)} bâtiments` },
  eau: { label: "Plan d'eau (part du carreau)", palette: WATER, breaks: [0.4, 0.55, 0.7, 0.85, 0.95], unit: "", format: (v) => `${Math.round(v * 100)} %` },
};

// Accessibility: diverging around the coverage radius (green = covered, red = far).
export const ACCESS_COLORS = ["#16a34a", "#84cc16", "#facc15", "#f97316", "#dc2626", "#7f1d1d"];

export function accessColor(distance, radius) {
  if (distance == null || distance < 0) return ACCESS_COLORS[5];
  const r = distance / radius;
  if (r <= 0.5) return ACCESS_COLORS[0];
  if (r <= 1) return ACCESS_COLORS[1];
  if (r <= 1.5) return ACCESS_COLORS[2];
  if (r <= 2.5) return ACCESS_COLORS[3];
  if (r <= 4) return ACCESS_COLORS[4];
  return ACCESS_COLORS[5];
}

export function classColor(value, layer) {
  const spec = LAYERS[layer];
  if (!spec) return "#94a3b8";
  let k = 0;
  while (k < spec.breaks.length && value > spec.breaks[k]) k += 1;
  return spec.palette[k];
}

export const HEALTH_COLORS = { ok: "#3dff8a", degraded: "#f5c542", down: "#ff3b3b" };

// Choropleth of the communes (territory map): 5 classes by quantiles.
export const CHORO = ["#0f2e2b", "#115e59", "#0d9488", "#2dd4bf", "#99f6e4"];
export const CHORO_BAD = ["#2a0f12", "#7f1d1d", "#b91c1c", "#f87171", "#fecaca"];
