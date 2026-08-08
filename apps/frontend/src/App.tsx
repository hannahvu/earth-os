import { useEffect, useState } from "react";
import { fetchEvents } from "./api";
import type { EarthEvent } from "./api";
import Globe from "./Globe";

const panel: React.CSSProperties = {
  width: 380,
  background: "#0d0d1a",
  borderLeft: "1px solid #222",
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

export default function App() {
  const [events, setEvents] = useState<EarthEvent[]>([]);
  const [selected, setSelected] = useState<EarthEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchEvents({ limit: 1500 })
      .then((data) => { setEvents(data); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

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
            Loading {events.length} events…
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
        <Globe events={events} onEventClick={setSelected} />
      </div>

      {/* Inspector panel */}
      {selected && (
        <div style={panel}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "#60a5fa", fontSize: 14, fontWeight: 700 }}>
              Event Inspector
            </span>
            <button
              onClick={() => setSelected(null)}
              style={{
                background: "none", border: "none", color: "#94a3b8",
                cursor: "pointer", fontSize: 18, lineHeight: 1,
              }}
            >
              ✕
            </button>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <span style={badge}>{selected.region}</span>
            <span style={badge}>{selected.event_type}</span>
            <span style={{ ...badge, background: "#1a3a1a", color: "#4ade80" }}>
              {selected.origin}
            </span>
          </div>

          <div style={{ color: "#94a3b8", fontSize: 12 }}>
            {selected.value.toLocaleString()} {selected.unit}<br />
            {selected.observed_at.replace("T", " ").replace("+00:00", " UTC")}
          </div>

          <pre style={{
            fontSize: 11,
            lineHeight: 1.6,
            color: "#cbd5e1",
            background: "#080812",
            padding: 12,
            borderRadius: 6,
            overflowX: "auto",
            whiteSpace: "pre-wrap",
            margin: 0,
          }}>
            {JSON.stringify(selected, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
