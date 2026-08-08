import { useRef } from "react";
import GlobeGL from "react-globe.gl";
import type { EarthEvent } from "./api";

// EIA demand — color by BA region
const REGION_COLORS: Record<string, string> = {
  ERCO: "#f97316", // orange — Texas
  CISO: "#3b82f6", // blue — California
  PJM:  "#a855f7", // purple — Mid-Atlantic
  MISO: "#22c55e", // green — Midwest
  ISNE: "#f59e0b", // amber — New England
};

// USGS earthquakes — red scale by magnitude
function quakeColor(mag: number): string {
  if (mag >= 6.0) return "#ff1744"; // major — bright red
  if (mag >= 5.0) return "#ff5722"; // strong — deep orange-red
  if (mag >= 4.0) return "#ff8a65"; // moderate — salmon
  return "#ffccbc";                 // minor — pale peach
}

function pointColor(e: EarthEvent): string {
  if (e.event_type === "earthquake") return quakeColor(e.value);
  return REGION_COLORS[e.region] ?? "#00d4ff";
}

// Radius scaling — separate ranges per event type
function scaleEiaRadius(value: number, min: number, max: number): number {
  if (max === min) return 0.5;
  const t = (value - min) / (max - min);
  return 0.25 + t * 0.75;
}

const MIN_MAG = 2.5;
const MAX_MAG = 7.0;
function scaleQuakeRadius(mag: number): number {
  const t = Math.min((mag - MIN_MAG) / (MAX_MAG - MIN_MAG), 1);
  return 0.15 + t * 0.85; // radius range: 0.15 (M2.5) → 1.0 (M7+)
}

interface Props {
  events: EarthEvent[];
  onEventClick: (event: EarthEvent) => void;
}

export default function Globe({ events, onEventClick }: Props) {
  const globeRef = useRef(null);

  // Compute EIA demand range for relative scaling
  const eiaValues = events.filter(e => e.event_type === "grid_demand").map(e => e.value);
  const eiaMin = eiaValues.length ? Math.min(...eiaValues) : 0;
  const eiaMax = eiaValues.length ? Math.max(...eiaValues) : 1;

  function pointRadius(e: EarthEvent): number {
    if (e.event_type === "earthquake") return scaleQuakeRadius(e.value);
    return scaleEiaRadius(e.value, eiaMin, eiaMax);
  }

  function pointLabel(e: EarthEvent): string {
    if (e.event_type === "earthquake") {
      return `<div style="background:rgba(0,0,0,0.8);color:#fff;padding:6px 10px;border-radius:6px;font-family:monospace;font-size:13px;line-height:1.6">
        <strong>M${e.value.toFixed(1)} Earthquake</strong><br/>
        ${e.region}<br/>
        ${e.observed_at.replace("T", " ").replace("+00:00", " UTC")}<br/>
        <span style="color:#aaa;font-size:11px">${e.confidence === 0.95 ? "reviewed" : "automatic"}</span>
      </div>`;
    }
    return `<div style="background:rgba(0,0,0,0.8);color:#fff;padding:6px 10px;border-radius:6px;font-family:monospace;font-size:13px;line-height:1.6">
      <strong>${e.region}</strong> grid demand<br/>
      ${e.value.toLocaleString()} ${e.unit}<br/>
      ${e.observed_at.replace("T", " ").replace("+00:00", " UTC")}
    </div>`;
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
      pointAltitude={0.015}
      pointRadius={(d) => pointRadius(d as EarthEvent)}
      pointLabel={(d) => pointLabel(d as EarthEvent)}
      onPointClick={(point) => onEventClick(point as EarthEvent)}
    />
  );
}
