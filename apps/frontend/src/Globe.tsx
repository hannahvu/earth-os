import { useRef } from "react";
import GlobeGL from "react-globe.gl";
import type { EarthEvent } from "./api";

// ── Color helpers ────────────────────────────────────────────────────────────

const REGION_COLORS: Record<string, string> = {
  ERCO: "#f97316",
  CISO: "#3b82f6",
  PJM:  "#a855f7",
  MISO: "#22c55e",
  ISNE: "#f59e0b",
};

function quakeColor(mag: number): string {
  if (mag >= 6.0) return "#ff1744";
  if (mag >= 5.0) return "#ff5722";
  if (mag >= 4.0) return "#ff8a65";
  return "#ffccbc";
}

function tempColor(degC: number): string {
  if (degC >= 28) return "#ef4444";   // hot
  if (degC >= 22) return "#f97316";   // warm
  if (degC >= 15) return "#22c55e";   // mild
  if (degC >= 8)  return "#3b82f6";   // cool
  return "#818cf8";                    // cold
}

function pointColor(e: EarthEvent): string {
  switch (e.event_type) {
    case "grid_demand":              return REGION_COLORS[e.region] ?? "#00d4ff";
    case "earthquake":               return quakeColor(e.value);
    case "sea_surface_temperature":  return tempColor(e.value);
    case "air_temperature":          return tempColor(e.value);
    case "demand_anomaly":           return e.value > 0 ? "#fbbf24" : "#60a5fa"; // amber=high, blue=low
    case "heat_stress_index":        return e.value > 5 ? "#f97316" : e.value > 0 ? "#fcd34d" : "#93c5fd";
    case "seismic_proximity_alert":  return "#ec4899";
    default:                         return "#00d4ff";
  }
}

// ── Radius helpers ───────────────────────────────────────────────────────────

const MIN_MAG = 2.5, MAX_MAG = 7.0;

function scaleRadius(value: number, min: number, max: number, lo = 0.25, hi = 1.0): number {
  if (max === min) return (lo + hi) / 2;
  return lo + Math.min((value - min) / (max - min), 1) * (hi - lo);
}

interface Props {
  events: EarthEvent[];
  onEventClick: (event: EarthEvent) => void;
}

export default function Globe({ events, onEventClick }: Props) {
  const globeRef = useRef(null);

  const eiaValues = events.filter(e => e.event_type === "grid_demand").map(e => e.value);
  const eiaMin = eiaValues.length ? Math.min(...eiaValues) : 0;
  const eiaMax = eiaValues.length ? Math.max(...eiaValues) : 1;

  function pointRadius(e: EarthEvent): number {
    switch (e.event_type) {
      case "grid_demand":    return scaleRadius(e.value, eiaMin, eiaMax);
      case "earthquake":     return scaleRadius(e.value, MIN_MAG, MAX_MAG, 0.15, 1.0);
      case "demand_anomaly": return scaleRadius(Math.abs(e.value), 1.5, 4.0, 0.4, 1.0);
      default:               return 0.35;
    }
  }

  // Derived events float above observed events
  function pointAltitude(e: EarthEvent): number {
    return e.origin === "derived" ? 0.06 : 0.015;
  }

  function pointLabel(e: EarthEvent): string {
    const wrap = (content: string) =>
      `<div style="background:rgba(0,0,0,0.85);color:#fff;padding:7px 11px;border-radius:6px;font-family:monospace;font-size:12px;line-height:1.7;max-width:240px">${content}</div>`;
    const ts = e.observed_at.replace("T", " ").replace("+00:00", " UTC");

    switch (e.event_type) {
      case "grid_demand":
        return wrap(`<strong>${e.region}</strong> electricity demand<br/>${e.value.toLocaleString()} ${e.unit}<br/>${ts}`);
      case "earthquake":
        return wrap(`<strong>M${e.value.toFixed(1)} Earthquake</strong><br/>${e.region}<br/>${ts}<br/><span style="color:#aaa">${e.confidence === 0.95 ? "reviewed" : "automatic"}</span>`);
      case "sea_surface_temperature":
        return wrap(`<strong>Sea surface temp</strong><br/>${e.region}<br/>${e.value.toFixed(1)}°C<br/>${ts}`);
      case "air_temperature":
        return wrap(`<strong>Air temp — ${e.region}</strong><br/>${e.value.toFixed(1)}°C<br/>${ts}`);
      case "demand_anomaly":
        const dir = e.value > 0 ? "above" : "below";
        return wrap(`<strong>⬆ Demand anomaly — ${e.region}</strong><br/>z = ${e.value.toFixed(2)} (${Math.abs(e.value).toFixed(1)}σ ${dir} normal)<br/>${ts}<br/><span style="color:#fbbf24">derived</span>`);
      case "heat_stress_index":
        return wrap(`<strong>Heat stress — ${e.region}</strong><br/>index: ${e.value.toFixed(2)}<br/>${ts}<br/><span style="color:#f97316">derived</span>`);
      case "seismic_proximity_alert":
        return wrap(`<strong>⚠ Seismic alert — ${e.region}</strong><br/>M${e.value.toFixed(1)} quake within 500km<br/>${ts}<br/><span style="color:#ec4899">derived</span>`);
      default:
        return wrap(`${e.event_type}<br/>${e.value} ${e.unit}`);
    }
  }

  return (
    <GlobeGL
      ref={globeRef}
      globeImageUrl="//unpkg.com/three-globe/example/img/earth-night.jpg"
      backgroundImageUrl="//unpkg.com/three-globe/example/img/night-sky.png"
      pointsData={events}
      pointLat="latitude"
      pointLng="longitude"
      pointColor={(d) => pointColor(d as EarthEvent)}
      pointAltitude={(d) => pointAltitude(d as EarthEvent)}
      pointRadius={(d) => pointRadius(d as EarthEvent)}
      pointLabel={(d) => pointLabel(d as EarthEvent)}
      onPointClick={(point) => onEventClick(point as EarthEvent)}
    />
  );
}
