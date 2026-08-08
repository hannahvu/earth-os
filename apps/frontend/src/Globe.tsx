import { useRef } from "react";
import GlobeGL from "react-globe.gl";
import type { EarthEvent } from "./api";

const REGION_COLORS: Record<string, string> = {
  ERCO: "#f97316", // orange — Texas
  CISO: "#3b82f6", // blue — California
  PJM:  "#a855f7", // purple — Mid-Atlantic
  MISO: "#22c55e", // green — Midwest
  ISNE: "#f59e0b", // amber — New England
};

const DEFAULT_COLOR = "#00d4ff";

interface Props {
  events: EarthEvent[];
  onEventClick: (event: EarthEvent) => void;
}

export default function Globe({ events, onEventClick }: Props) {
  const globeRef = useRef(null);

  return (
    <GlobeGL
      ref={globeRef}
      globeImageUrl="//unpkg.com/three-globe/example/img/earth-night.jpg"
      backgroundImageUrl="//unpkg.com/three-globe/example/img/night-sky.png"
      pointsData={events}
      pointLat="latitude"
      pointLng="longitude"
      pointColor={(d) => REGION_COLORS[(d as EarthEvent).region] ?? DEFAULT_COLOR}
      pointAltitude={0.015}
      pointRadius={0.45}
      pointLabel={(d) => {
        const e = d as EarthEvent;
        return `<div style="
          background: rgba(0,0,0,0.75);
          color: #fff;
          padding: 6px 10px;
          border-radius: 6px;
          font-family: monospace;
          font-size: 13px;
          line-height: 1.5;
        ">
          <strong>${e.region}</strong><br/>
          ${e.value.toLocaleString()} ${e.unit}<br/>
          ${e.observed_at.replace("T", " ").replace("+00:00", " UTC")}
        </div>`;
      }}
      onPointClick={(point) => onEventClick(point as EarthEvent)}
    />
  );
}
