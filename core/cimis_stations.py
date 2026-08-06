"""Core data-fetching logic for the "Intro to CIMIS" statewide station map.

Pulls weather station metadata (location, name, county, elevation, active
status) from the California Dept. of Water Resources' CIMIS station
directory. Like NOAA's station metadata API (core/noaa_station_map.py),
this returns every station -- active and long-since-disconnected -- in one
single request, no chunking needed. Unlike the CIMIS *data* endpoint, this
station list endpoint does not require an appKey.

This module is Streamlit-agnostic on purpose: it can be imported, tested,
or reused from a plain script. The Streamlit page is a thin UI layer on
top of it.
"""

import re
import time

import pandas as pd
import requests

STATIONS_URL = "https://et.water.ca.gov/api/station"

# CIMIS's WAF rejects requests with no/unusual User-Agent header (verified
# directly against the live API -- a default `requests` UA on the /api/data
# endpoint gets a bare "Request Rejected" WAF page instead of JSON); sending
# a normal browser-style UA avoids that on every CIMIS endpoint.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WRA-Hydrology-Tools"}

# "36\xba20'10N / 36.336222" -> 36.336222 -- CIMIS gives lat/lng as a
# degrees-minutes-seconds string followed by the decimal equivalent after
# " / "; the decimal half is all we need.
_DECIMAL_RE = re.compile(r"/\s*(-?\d+\.\d+)")


def hex_to_rgba(hex_color, alpha=220):
    """'#175536' -> [23, 85, 54, 220], for deck.gl per-point color fields."""
    h = hex_color.lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha]


def _parse_decimal_coord(raw):
    if not raw:
        return None
    m = _DECIMAL_RE.search(raw)
    return float(m.group(1)) if m else None


def fetch_all_cimis_stations():
    """Fetch metadata for every CIMIS station in the network (active and
    historical/disconnected alike).

    Returns a DataFrame with columns: id, name, city, county, lat, lng,
    elevation_ft, ground_cover, is_active, is_eto_station, siting_desc,
    connect_date, disconnect_date.

    A couple of network retries are attempted before giving up -- CIMIS's
    station endpoint has been observed to occasionally time out on the
    first try even though it's a single request (no chunking).
    """
    last_error = None
    for attempt in range(3):
        try:
            r = requests.get(STATIONS_URL, headers=HEADERS, timeout=30)
            r.raise_for_status()
            stations = r.json().get("Stations", [])
            break
        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    else:
        raise ValueError(f"Could not fetch CIMIS station list: {last_error}")

    if not stations:
        raise ValueError("CIMIS returned no stations.")

    rows = []
    for s in stations:
        lat = _parse_decimal_coord(s.get("HmsLatitude"))
        lng = _parse_decimal_coord(s.get("HmsLongitude"))
        if lat is None or lng is None:
            continue
        rows.append({
            "id": str(s.get("StationNbr", "")).strip(),
            "name": (s.get("Name") or "").strip(),
            "city": (s.get("City") or "").strip(),
            "county": (s.get("County") or "").strip(),
            "lat": lat,
            "lng": lng,
            "elevation_ft": pd.to_numeric(s.get("Elevation"), errors="coerce"),
            "ground_cover": (s.get("GroundCover") or "").strip(),
            "is_active": str(s.get("IsActive", "")).strip().lower() == "true",
            "is_eto_station": str(s.get("IsEtoStation", "")).strip().lower() == "true",
            "siting_desc": (s.get("SitingDesc") or "").strip(),
            "connect_date": (s.get("ConnectDate") or "").strip(),
            "disconnect_date": (s.get("DisconnectDate") or "").strip(),
        })

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset="id").reset_index(drop=True)
    return df
