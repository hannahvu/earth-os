import { useEffect, useState } from "react";
import { fetchEvents } from "./api";
import type { EarthEvent } from "./api";
import Globe from "./Globe";

// ── Layer definitions ────────────────────────────────────────────────────────

interface Layer {
  eventType: string;
  label: string;
  color: string;
  defaultOn: boolean;
  tag: "observed" | "derived";
}

const LAYERS: Layer[] = [
  // Observed
  { eventType: "grid_demand",             label: "Electricity Demand", color: "#f97316", defaultOn: true,  tag: "observed" },
  { eventType: "earthquake",              label: "Earthquakes",         color: "#ff4444", defaultOn: true,  tag: "observed" },
  { eventType: "sea_surface_temperature", label: "Sea Surface Temp",    color: "#06b6d4", defaultOn: true,  tag: "observed" },
  { eventType: "air_temperature",         label: "Weather Stations",    color: "#7dd3fc", defaultOn: false, tag: "observed" },
  // Derived
  { eventType: "demand_anomaly",          label: "Demand Anomalies",    color: "#fbbf24", defaultOn: true,  tag: "derived"  },
  { eventType: "heat_stress_index",       label: "Heat Stress",         color: "#f97316", defaultOn: true,  tag: "derived"  },
  { eventType: "seismic_proximity_alert", label: "Seismic Alerts",      color: "#ec4899", defaultOn: true,  tag: "derived"  },
];

const VISIBLE_EVENT_TYPES = new Set([
  "grid_demand", "earthquake", "sea_surface_temperature",
  "demand_anomaly", "heat_stress_index", "seismic_proximity_alert",
]);

// ── Styles ───────────────────────────────────────────────────────────────────

const panelStyle: React.CSSProperties = {
  width: 380,
  background: "#0d0d1a",
  borderLeft: "1px solid #1e1e3a",
  color: "#e2e8f0",
  padding: 20,
  overflowY: "auto",
  fontFamily: "monospace",
  display: "flex",
  flexDirection: "column",
  gap: 12,
};

const badge: React.CSSProperties = {
  display: "inline-block",
  padding: "2px 8px",
  borderRadius: 4,
  fontSize: 11,
  fontWeight: 700,
  background: "#1e3a5f",
  color: "#60a5fa",
  letterSpacing: "0.05em",
};

// ── Component ────────────────────────────────────────────────────────────────

export default function App() {
  const [events, setEvents] = useState<EarthEvent[]>([]);
  const [selected, setSelected] = useState<EarthEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeLayers, setActiveLayers] = useState<Set<string>>(
    () => new Set(LAYERS.filter(l => l.defaultOn).map(l => l.eventType))
  );

  useEffect(() => {
    fetchEvents({ limit: 5000 })
      .then((data) => {
        // Keep only the event types we display
        setEvents(data.filter(e => VISIBLE_EVENT_TYPES.has(e.event_type)));
        setLoading(false);
      })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

  const visibleEvents = events.filter(e => activeLayers.has(e.event_type));

  function toggleLayer(eventType: string) {
    setActiveLayers(prev => {
      const next = new Set(prev);
      next.has(eventType) ? next.delete(eventType) : next.add(eventType);
      return next;
    });
  }

  return (
    <div style={{ display: "flex", height: "100vh", background: "#050510" }}>

      {/* Globe */}
      <div style={{ flex: 1, position: "relative" }}>

        {loading && (
          <div style={{
            position: "absolute", inset: 0, display: "flex",
            alignItems: "center", justifyContent: "center",
            color: "#60a5fa", fontFamily: "monospace", zIndex: 10,
          }}>
            Loading…
          </div>
        )}

        {error && (
          <div style={{
            position: "absolute", top: 16, left: 16, zIndex: 10,
            background: "#3b0000", color: "#f87171", padding: "8px 14px",
            borderRadius: 6, fontFamily: "monospace", fontSize: 13,
          }}>
            {error} — is the API running on port 8000?
          </div>
        )}

        {/* Layer toggles */}
        <div style={{
          position: "absolute", top: 16, left: 16, zIndex: 10,
          background: "rgba(10,10,26,0.88)",
          border: "1px solid #1e1e3a",
          borderRadius: 8, padding: "12px 14px",
          fontFamily: "monospace", fontSize: 12, color: "#94a3b8",
          display: "flex", flexDirection: "column", gap: 4, minWidth: 180,
        }}>
          <div style={{ color: "#60a5fa", fontWeight: 700, marginBottom: 6, fontSize: 11, letterSpacing: "0.08em" }}>
            LAYERS
          </div>

          <div style={{ color: "#475569", fontSize: 10, marginBottom: 2 }}>OBSERVED</div>
          {LAYERS.filter(l => l.tag === "observed").map(layer => (
            <label key={layer.eventType} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={activeLayers.has(layer.eventType)}
                onChange={() => toggleLayer(layer.eventType)}
                style={{ display: "none" }}
              />
              <span style={{
                width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
                background: activeLayers.has(layer.eventType) ? layer.color : "#2d2d4a",
                border: `1px solid ${layer.color}`,
                transition: "background 0.15s",
              }} />
              <span style={{ color: activeLayers.has(layer.eventType) ? "#e2e8f0" : "#475569" }}>
                {layer.label}
              </span>
            </label>
          ))}

          <div style={{ color: "#475569", fontSize: 10, marginTop: 6, marginBottom: 2 }}>DERIVED</div>
          {LAYERS.filter(l => l.tag === "derived").map(layer => (
            <label key={layer.eventType} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={activeLayers.has(layer.eventType)}
                onChange={() => toggleLayer(layer.eventType)}
                style={{ display: "none" }}
              />
              <span style={{
                width: 10, height: 10, borderRadius: 2, flexShrink: 0,
                background: activeLayers.has(layer.eventType) ? layer.color : "#2d2d4a",
                border: `1px solid ${layer.color}`,
                transition: "background 0.15s",
              }} />
              <span style={{ color: activeLayers.has(layer.eventType) ? "#e2e8f0" : "#475569" }}>
                {layer.label}
              </span>
            </label>
          ))}

          <div style={{ marginTop: 8, color: "#334155", fontSize: 10 }}>
            {visibleEvents.length} events visible
          </div>
        </div>

        <Globe events={visibleEvents} onEventClick={setSelected} />
      </div>

      {/* Inspector panel */}
      {selected && (
        <div style={panelStyle}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "#60a5fa", fontSize: 14, fontWeight: 700 }}>Event Inspector</span>
            <button
              onClick={() => setSelected(null)}
              style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: 18 }}
            >✕</button>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <span style={badge}>{selected.region}</span>
            <span style={badge}>{selected.event_type}</span>
            <span style={{
              ...badge,
              background: selected.origin === "derived" ? "#3a1f1f" : "#1a3a1a",
              color: selected.origin === "derived" ? "#f97316" : "#4ade80",
            }}>
              {selected.origin}
            </span>
          </div>

          <div style={{ color: "#94a3b8", fontSize: 12 }}>
            {selected.value.toLocaleString()} {selected.unit}<br />
            {selected.observed_at.replace("T", " ").replace("+00:00", " UTC")}
          </div>

          <pre style={{
            fontSize: 11, lineHeight: 1.6, color: "#cbd5e1",
            background: "#080812", padding: 12, borderRadius: 6,
            overflowX: "auto", whiteSpace: "pre-wrap", margin: 0,
          }}>
            {JSON.stringify(selected, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
