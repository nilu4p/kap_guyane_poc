import { useEffect, useRef } from "react";
import L from "leaflet";
import { useMap } from "react-leaflet";

/**
 * The 200 m cells of a layer drawn on a canvas (thousands of squares stay fluid).
 * ``cells`` = [[row, col, value, …]] as sent by the API; ``grid`` = {lat0, lon0, dlat, dlon}.
 * Nothing finer than the 200 m cell is ever drawn (ethics charter).
 * Callers pass memoised ``colorFor`` / ``tooltip`` / ``onSelect``: a new function redraws every cell.
 */
export default function GridLayer({ grid, cells, colorFor, opacity = 0.72, onSelect, selected, tooltip }) {
  const map = useMap();
  const rendererRef = useRef(null);

  useEffect(() => {
    if (!rendererRef.current) rendererRef.current = L.canvas({ padding: 0.3 });
    const group = L.layerGroup();
    if (grid && cells) {
      for (const cell of cells) {
        const [row, col] = cell;
        const south = grid.lat0 + row * grid.dlat;
        const west = grid.lon0 + col * grid.dlon;
        const color = colorFor(cell);
        if (!color) continue;
        const id = `${row}_${col}`;
        const rect = L.rectangle([[south, west], [south + grid.dlat, west + grid.dlon]], {
          renderer: rendererRef.current,
          stroke: false,
          fillColor: color,
          fillOpacity: opacity,
        });
        if (tooltip) {
          rect.bindTooltip(() => {
            const tip = document.createElement("span"); // text only, never HTML
            tip.textContent = tooltip(cell);
            return tip;
          }, { sticky: true, className: "tactical-tip" });
        }
        if (onSelect) rect.on("click", () => onSelect(id, cell));
        group.addLayer(rect);
      }
    }
    group.addTo(map);
    return () => {
      group.remove();
    };
  }, [map, grid, cells, colorFor, opacity, onSelect, tooltip]);

  // The selected cell is outlined by its own layer: selecting a cell no longer redraws the whole grid
  // (``cells`` in the dependencies: after a redraw of the grid, the outline is put back on top).
  useEffect(() => {
    if (!grid || !selected) return undefined;
    const [row, col] = selected.split("_").map(Number);
    if (!Number.isFinite(row) || !Number.isFinite(col)) return undefined;
    const south = grid.lat0 + row * grid.dlat;
    const west = grid.lon0 + col * grid.dlon;
    const outline = L.rectangle([[south, west], [south + grid.dlat, west + grid.dlon]], {
      renderer: rendererRef.current || undefined,
      color: "#ffffff",
      weight: 2,
      fill: false,
      interactive: false,
    }).addTo(map);
    return () => {
      outline.remove();
    };
  }, [map, grid, cells, selected]);

  return null;
}
