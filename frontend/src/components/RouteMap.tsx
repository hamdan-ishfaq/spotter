import { useEffect } from "react";
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import { Box, Typography } from "@mui/material";

type Stop = {
  type?: string;
  label?: string;
  lat?: number | null;
  lng?: number | null;
  duration_hours?: number;
};

type Props = {
  geometry: [number, number][];
  stops: Stop[];
  highlight?: { lat: number; lng: number } | null;
};

const icon = (color: string) =>
  L.divIcon({
    className: "",
    html: `<div style="background:${color};width:14px;height:14px;border-radius:50%;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });

const COLORS: Record<string, string> = {
  current: "#1B3A4B",
  pickup: "#2E7D32",
  dropoff: "#C62828",
  fuel: "#EF6C00",
  break_30: "#6A1B9A",
  rest_off: "#455A64",
  rest_sb: "#455A64",
  restart_34: "#AD1457",
  pretrip: "#00838F",
};

function FitBounds({ geometry }: { geometry: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (geometry.length >= 2) {
      map.fitBounds(L.latLngBounds(geometry.map(([lat, lng]) => [lat, lng])), {
        padding: [28, 28],
      });
    }
  }, [geometry, map]);
  return null;
}

function PanToHighlight({ highlight }: { highlight?: { lat: number; lng: number } | null }) {
  const map = useMap();
  useEffect(() => {
    if (highlight?.lat != null && highlight?.lng != null) {
      map.panTo([highlight.lat, highlight.lng], { animate: true });
    }
  }, [highlight, map]);
  return null;
}

export function RouteMap({ geometry, stops, highlight }: Props) {
  const center: [number, number] =
    geometry[0] ?? ([39.5, -98.35] as [number, number]);

  return (
    <Box sx={{ height: { xs: 320, md: 420 }, borderRadius: 2, overflow: "hidden", border: "1px solid #d5d0c6" }}>
      <MapContainer center={center} zoom={5} style={{ height: "100%", width: "100%" }} scrollWheelZoom>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {geometry.length >= 2 && (
          <Polyline positions={geometry} pathOptions={{ color: "#1B3A4B", weight: 4, opacity: 0.85 }} />
        )}
        <FitBounds geometry={geometry} />
        <PanToHighlight highlight={highlight} />
        {stops
          .filter((s) => s.lat != null && s.lng != null)
          .map((s, i) => (
            <Marker
              key={`${s.type}-${i}`}
              position={[s.lat as number, s.lng as number]}
              icon={icon(COLORS[s.type || ""] || "#1B3A4B")}
            >
              <Popup>
                <Typography variant="subtitle2">{s.type}</Typography>
                <Typography variant="body2">{s.label}</Typography>
                {s.duration_hours != null && (
                  <Typography variant="caption">{s.duration_hours}h</Typography>
                )}
              </Popup>
            </Marker>
          ))}
        {highlight && (
          <Marker position={[highlight.lat, highlight.lng]} icon={icon("#FFD600")} />
        )}
      </MapContainer>
    </Box>
  );
}
