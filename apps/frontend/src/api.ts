const API_BASE = "http://localhost:8000";

export interface EarthEvent {
  event_id: string;
  event_type: string;
  observed_at: string;
  latitude: number;
  longitude: number;
  region: string;
  value: number;
  unit: string;
  origin: "observed" | "derived" | "simulated";
  source: string;
  confidence: number;
  ingested_at: string;
}

export async function fetchEvents(params?: {
  region?: string;
  limit?: number;
}): Promise<EarthEvent[]> {
  const url = new URL(`${API_BASE}/events`);
  if (params?.region) url.searchParams.set("region", params.region);
  if (params?.limit) url.searchParams.set("limit", String(params.limit));

  const resp = await fetch(url.toString());
  if (!resp.ok) throw new Error(`API error ${resp.status}: ${resp.statusText}`);
  return resp.json();
}
