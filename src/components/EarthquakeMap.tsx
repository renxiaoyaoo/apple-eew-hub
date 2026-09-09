import { useEffect } from "react";
import L from "leaflet";
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

function FitMap({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length >= 2) map.fitBounds(points, { padding: [44, 44] });
  }, [map, points]);
  return null;
}

type Props = {
  epicenter: [number, number];
  user: [number, number];
  waveKm: number;
  level: string;
  epicenterLabel: string;
  userLabel: string;
};

export function EarthquakeMap({ epicenter, user, waveKm, level, epicenterLabel, userLabel }: Props) {
  return (
    <section className="mapPanel">
      <div className="sectionHead"><div><h2>震中、你的位置和地震波</h2></div><span>{userLabel}</span></div>
      <MapContainer center={user} zoom={7} scrollWheelZoom={false} className="map">
        <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <FitMap points={[epicenter, user]} />
        <Circle center={epicenter} radius={waveKm * 1000} pathOptions={{ color: level === "red" ? "#dc2626" : level === "yellow" ? "#d97706" : "#2563eb", fillOpacity: 0.08, weight: 2 }} />
        <Polyline positions={[epicenter, user]} pathOptions={{ color: "#1f2937", weight: 2, dashArray: "7 9" }} />
        <Marker position={epicenter} icon={L.divIcon({ className: `pin epicenter pulse ${level}`, html: "<span>震</span>" })}><Popup>{epicenterLabel}</Popup></Marker>
        <Marker position={user} icon={L.divIcon({ className: "pin user", html: "我" })}><Popup>{userLabel}</Popup></Marker>
      </MapContainer>
    </section>
  );
}
