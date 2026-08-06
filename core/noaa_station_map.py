"""Core data-fetching logic for the "Intro to NOAA Tides" nationwide
station map. Pulls water-level station metadata (location, name, state,
tide type) from NOAA CO-OPS's station metadata API.

Unlike the USGS nationwide fetch, NOAA's metadata API returns every water
level station in one single request (only ~300 nationwide) -- no
state-by-state chunking needed.

This module is Streamlit-agnostic on purpose: it can be imported, tested,
or reused from a plain script. The Streamlit page is a thin UI layer on
top of it.
"""

import time

import pandas as pd
import requests

STATIONS_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"


def hex_to_rgba(hex_color, alpha=220):
    """'#C76E4F' -> [199, 110, 79, 220], for deck.gl per-point color fields."""
    h = hex_color.lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha]


def fetch_all_tide_stations():
    """Fetch metadata for every NOAA water-level station nationwide.

    Returns a DataFrame with columns: id, name, lat, lng, state, tide_type.
    A couple of network retries are attempted before giving up, since this
    is a single request (no chunking) and worth being resilient about.
    """
    last_error = None
    for attempt in range(3):
        try:
            r = requests.get(STATIONS_URL, params={"type": "waterlevels"}, timeout=30)
            r.raise_for_status()
            stations = r.json().get("stations", [])
            break
        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    else:
        raise ValueError(f"Could not fetch NOAA station list: {last_error}")

    if not stations:
        raise ValueError("NOAA returned no water-level stations.")

    df = pd.DataFrame(stations)
    df = df.rename(columns={"tideType": "tide_type"})
    for col in ["id", "name", "lat", "lng", "state", "tide_type"]:
        if col not in df.columns:
            df[col] = None
    df = df[["id", "name", "lat", "lng", "state", "tide_type"]].copy()

    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lng"] = pd.to_numeric(df["lng"], errors="coerce")
    df = df.dropna(subset=["lat", "lng"])
    df = df.drop_duplicates(subset="id").reset_index(drop=True)
    df["name"] = df["name"].fillna("").str.strip()
    df["state"] = df["state"].fillna("").str.strip()
    df["tide_type"] = df["tide_type"].fillna("").str.strip()
    return df
