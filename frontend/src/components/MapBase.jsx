import { useEffect } from "react";
import { GeoJSON, LayersControl, MapContainer, ScaleControl, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

// The site sends no Referer (nginx "no-referrer"), but the OpenStreetMap tile usage policy
// requires one: tile requests alone send the site origin (never the page path).
export const TILE_REFERRER = "strict-origin-when-cross-origin";

const EOX = (layer) => `https://tiles.maps.eox.at/wmts/1.0.0/${layer}/default/g/{z}/{y}/{x}.jpg`;

export function eoxLayer(year) {
  if (!year || year <= 2016) return { layer: "s2cloudless_3857", year: 2016 };
  const y = Math.min(year, 2025);
  return { layer: `s2cloudless-${y}_3857`, year: y };
}

/** Fits the map on a bounding box [west, south, east, north] when it changes. */
export function FitBounds({ bbox, padding = 20 }) {
  const map = useMap();
  const key = bbox ? bbox.join(",") : "";
  useEffect(() => {
    if (!bbox || bbox.length < 4) return;
    map.fitBounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]], { padding: [padding, padding] });
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

/**
 * Base map: yearly cloudless Sentinel-2 mosaic (EOX) synchronised with the time slider, or
 * OpenStreetMap; the commune contour on top.
 */
export default function MapBase({ children, imageryYear = 2024, contour = null, bbox = null, height = "100%", baseDefault = "satellite" }) {
  const eox = eoxLayer(imageryYear);
  return (
    <MapContainer
      center={[4.9, -53.0]}
      zoom={8}
      minZoom={6}
      maxZoom={17}
      style={{ height, width: "100%" }}
      preferCanvas
      attributionControl
    >
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked={baseDefault === "satellite"} name={`Satellite — Sentinel-2 sans nuages ${eox.year} (EOX)`}>
          <TileLayer
            key={eox.layer}
            url={EOX(eox.layer)}
            maxNativeZoom={14}
            maxZoom={17}
            referrerPolicy={TILE_REFERRER}
            attribution={`Sentinel-2 cloudless ${eox.year} — EOX IT Services GmbH (données Copernicus Sentinel modifiées)`}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer checked={baseDefault === "osm"} name="OpenStreetMap">
          <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} referrerPolicy={TILE_REFERRER}
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">contributeurs OpenStreetMap</a>' />
        </LayersControl.BaseLayer>
      </LayersControl>
      {contour && (
        <GeoJSON key={JSON.stringify(contour.properties || {})} data={contour} style={{ color: "#2dd4bf", weight: 2, fill: false, dashArray: "6 4" }} interactive={false} />
      )}
      {bbox && <FitBounds bbox={bbox} />}
      <ScaleControl position="bottomleft" imperial={false} />
      {children}
    </MapContainer>
  );
}
