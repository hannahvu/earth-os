"""
Exploration: NOAA NDBC (National Data Buoy Center) — ocean/buoy observations.
No API key required. Data served as fixed-width text files.

Run:
    uv run pytest sources/noaa/test/test_ndbc.py -s
"""
import io

import httpx
import pytest

NDBC_BASE = "https://www.ndbc.noaa.gov"

# Well-known buoys across different ocean regions
SAMPLE_BUOYS = {
    "41047": "NW Atlantic (offshore NC)",
    "46047": "NE Pacific (offshore CA)",
    "51001": "Pacific (Hawaii NW)",
    "21413": "NW Pacific (Japan)",
    "42060": "Gulf of Mexico",
}


def fetch_realtime(station_id: str) -> str:
    """Fetch real-time observation text file for a buoy station."""
    url = f"{NDBC_BASE}/data/realtime2/{station_id}.txt"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_station_list() -> str:
    """Fetch the full active station metadata table."""
    url = f"{NDBC_BASE}/data/stations/station_table.txt"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_realtime(text: str) -> list[dict]:
    """
    Parse NDBC fixed-width text into a list of row dicts.
    First two lines are headers (#YY MM DD...) and units (#yr mo dy...).
    Remaining lines are observations, newest first.
    """
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 3:
        return []

    columns = lines[0].lstrip("#").split()
    rows = []
    for line in lines[2:]:          # skip header + units row
        values = line.split()
        if len(values) == len(columns):
            rows.append(dict(zip(columns, values)))
    return rows


def test_realtime_text_format():
    """
    Print raw text and parsed rows for a Pacific buoy.
    Shows column names, units row, and what 'MM' sentinel means.
    """
    station_id = "46047"
    text = fetch_realtime(station_id)
    lines = text.strip().splitlines()

    print(f"\n=== Raw first 5 lines from buoy {station_id} ===")
    for line in lines[:5]:
        print(" ", line)

    rows = parse_realtime(text)
    print(f"\n=== Parsed {len(rows)} observation rows ===")
    if rows:
        print("=== Column names ===")
        print(list(rows[0].keys()))
        print("\n=== Most recent row ===")
        for k, v in rows[0].items():
            print(f"  {k}: {v}")

    assert len(rows) > 0


def test_column_meanings():
    """
    Print column definitions for key fields we care about.
    MM = missing/unavailable measurement.
    """
    print("""
=== NDBC column reference (key fields) ===
  YY MM DD hh mm  — timestamp (UTC)
  WDIR            — wind direction (degrees true)
  WSPD            — wind speed (m/s)
  GST             — peak gust speed (m/s)
  WVHT            — significant wave height (m)
  DPD             — dominant wave period (sec)
  APD             — average wave period (sec)
  MWD             — wave direction (degrees)
  PRES            — sea level pressure (hPa)
  ATMP            — air temperature (°C)
  WTMP            — sea surface temperature (°C)
  DEWP            — dewpoint temperature (°C)
  VIS             — visibility (nautical miles)
  TIDE            — water level above MLLW (ft)
  MM              — sentinel for missing/unavailable data
""")
    assert True


def test_multiple_buoys_availability():
    """
    Check which sample buoys are active and what ocean variables they report.
    Not all buoys report all fields — MM = unavailable.
    """
    for station_id, description in SAMPLE_BUOYS.items():
        try:
            text = fetch_realtime(station_id)
            rows = parse_realtime(text)
            if not rows:
                print(f"  {station_id} ({description}): no data")
                continue
            row = rows[0]
            wtmp = row.get("WTMP", "MM")
            wvht = row.get("WVHT", "MM")
            atmp = row.get("ATMP", "MM")
            pres = row.get("PRES", "MM")
            print(f"  {station_id} ({description}): WTMP={wtmp}°C  WVHT={wvht}m  ATMP={atmp}°C  PRES={pres}hPa")
        except httpx.HTTPStatusError as e:
            print(f"  {station_id} ({description}): HTTP {e.response.status_code}")


def test_station_table_format():
    """
    Peek at the station metadata table — IDs, types, lat/lon, names.
    """
    text = fetch_station_list()
    lines = text.strip().splitlines()

    print(f"\n=== station_table.txt — first 10 lines ===")
    for line in lines[:10]:
        print(" ", line)

    print(f"\n=== Total lines: {len(lines)} ===")
    assert len(lines) > 10
