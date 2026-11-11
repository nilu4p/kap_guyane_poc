import { useMemo, useState } from "react";
import { fmt } from "../lib/format.js";

/**
 * Minimal responsive line chart (SVG). series = [{ id, label, color, dashed?, points: [{x, y}] }].
 * ``breakAt`` draws a vertical dashed rule (e.g. a change of sensor between two years).
 */
export function LineChart({ series, height = 180, yLabel = "", xFormat = (x) => x, yFormat = (y) => fmt(y), breakAt = null, breakLabel = "" }) {
  const [hover, setHover] = useState(null);
  const width = 640;
  const pad = { l: 56, r: 12, t: 12, b: 26 };
  const all = useMemo(() => series.flatMap((s) => s.points.filter((p) => p.y != null)), [series]);
  const { xMin, xMax, yMin, yMax } = useMemo(() => {
    if (!all.length) return { xMin: 0, xMax: 1, yMin: 0, yMax: 1 };
    const xs = all.map((p) => p.x);
    const ys = all.map((p) => p.y);
    const lo = Math.min(0, ...ys);
    const hi = Math.max(...ys);
    return { xMin: Math.min(...xs), xMax: Math.max(...xs), yMin: lo, yMax: hi === lo ? lo + 1 : hi * 1.08 };
  }, [all]);
  if (!all.length) return <p className="p-4 text-xs text-slate-500">Aucune donnée.</p>;
  const sx = (x) => pad.l + ((x - xMin) / Math.max(xMax - xMin, 1)) * (width - pad.l - pad.r);
  const sy = (y) => height - pad.b - ((y - yMin) / (yMax - yMin)) * (height - pad.t - pad.b);
  const ticks = 4;
  const xTicks = [...new Set(all.map((p) => p.x))].sort((a, b) => a - b);
  const step = Math.ceil(xTicks.length / 8);
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label={yLabel}>
        {[...Array(ticks + 1)].map((_, i) => {
          const y = yMin + ((yMax - yMin) * i) / ticks;
          return (
            <g key={i}>
              <line x1={pad.l} x2={width - pad.r} y1={sy(y)} y2={sy(y)} stroke="#1c2a38" />
              <text x={pad.l - 6} y={sy(y) + 3} textAnchor="end" fontSize="10" fill="#64748b">{yFormat(y)}</text>
            </g>
          );
        })}
        {xTicks.filter((_, i) => i % step === 0).map((x) => (
          <text key={x} x={sx(x)} y={height - 8} textAnchor="middle" fontSize="10" fill="#64748b">{xFormat(x)}</text>
        ))}
        {breakAt != null && (
          <g>
            <line x1={sx(breakAt)} x2={sx(breakAt)} y1={pad.t} y2={height - pad.b} stroke="#f5c542" strokeDasharray="3 3" />
            {breakLabel && <text x={sx(breakAt) + 4} y={pad.t + 10} fontSize="9" fill="#f5c542">{breakLabel}</text>}
          </g>
        )}
        {series.map((s) => {
          const pts = s.points.filter((p) => p.y != null);
          if (!pts.length) return null;
          const d = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
          return (
            <g key={s.id}>
              <path d={d} fill="none" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? "5 4" : undefined} />
              {pts.map((p) => (
                <circle key={p.x} cx={sx(p.x)} cy={sy(p.y)} r={hover?.x === p.x ? 4 : 2.5} fill={s.color}
                  onMouseEnter={() => setHover({ x: p.x })} onMouseLeave={() => setHover(null)} />
              ))}
            </g>
          );
        })}
      </svg>
      <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-slate-400">
        {series.map((s) => (
          <span key={s.id} className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-4" style={{ background: s.color, borderTop: s.dashed ? `2px dashed ${s.color}` : undefined }} />
            {s.label}
          </span>
        ))}
      </div>
      {hover && (
        <div className="pointer-events-none absolute right-2 top-2 border border-tactical-line bg-tactical-panel px-2 py-1 text-[11px]">
          <p className="text-slate-400">{xFormat(hover.x)}</p>
          {series.map((s) => {
            const p = s.points.find((q) => q.x === hover.x);
            return p && p.y != null ? <p key={s.id} style={{ color: s.color }}>{s.label} : {yFormat(p.y)}</p> : null;
          })}
        </div>
      )}
    </div>
  );
}

/** Horizontal bars (0-1 shares or values against a max). */
export function Bars({ items, max = null, format = (v) => fmt(v), colorFor = () => "#2dd4bf" }) {
  const top = max ?? Math.max(...items.map((i) => i.value || 0), 1);
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item.id} className="text-xs">
          <div className="flex justify-between gap-2">
            <span className="truncate text-slate-300" title={item.title || item.label}>{item.label}</span>
            <span className="shrink-0 tabular-nums text-slate-400">{format(item.value)}</span>
          </div>
          <div className="mt-0.5 h-1.5 bg-tactical-line">
            <div className="h-1.5" style={{ width: `${Math.max(0, Math.min(100, ((item.value || 0) / top) * 100))}%`, background: colorFor(item) }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Small "value vs Guyane" comparison marker. */
export function Compare({ value, reference, better }) {
  if (value == null || reference == null || reference === 0) return null;
  const ratio = value / reference;
  const higher = ratio > 1.05;
  const lower = ratio < 0.95;
  if (!higher && !lower) return <span className="text-[10px] text-slate-500">≈ Guyane</span>;
  const good = better ? (better === "higher" ? higher : lower) : null;
  const color = good == null ? "#94a3b8" : good ? "#3dff8a" : "#ff8c1a";
  return (
    <span className="text-[10px]" style={{ color }}>
      {higher ? "▲" : "▼"} {fmt(Math.abs(ratio - 1) * 100)} % vs Guyane
    </span>
  );
}
