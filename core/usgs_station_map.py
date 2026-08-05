"""Core data-fetching logic for the "Intro to USGS" nationwide streamgage
map. Pulls active streamgage metadata (location, name, drainage area) from
the same USGS NWIS site web service used throughout this app.

NWIS's site service requires at least one "major filter" per request (it
won't return every site nationwide in a single unfiltered call), so this
loops over every state/territory code and concatenates the results.

This module is Streamlit-agnostic on purpose: it can be imported, tested, or
reused from a plain script. The Streamlit page is a thin UI layer on top of
it, including the progress display during the (slow, one-time-per-cache)
nationwide fetch.
"""

import time

import pandas as pd
import requests

# USGS-recognized 2-letter codes for all 50 states, DC, and the major
# territories -- this is what makes the fetch "nationwide."
STATE_CODES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY", "PR", "VI", "GU", "AS", "MP",
]

SITE_COLUMNS = ["site_no", "station_nm", "dec_lat_va", "dec_long_va",
                 "huc_cd", "drain_area_va", "state_cd"]


def hex_to_rgba(hex_color, alpha=220):
    """'#C76E4F' -> [199, 110, 79, 220], for deck.gl per-point color fields."""
    h = hex_color.lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha]


def fetch_state_streamgages(state_cd):
    """Active, real-time stream sites for one state/territory code.
    Returns an empty DataFrame (not an error) if the state has none."""
    url = "https://waterservices.usgs.gov/nwis/site/"
    params = {
        "format": "rdb",
        "stateCd": state_cd,
        "siteType": "ST",
        "siteStatus": "active",
        "hasDataTypeCd": "iv",
        "siteOutput": "expanded",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()

    lines = [l for l in r.text.splitlines() if not l.startswith("#") and l.strip()]
    if len(lines) < 3:
        return pd.DataFrame(columns=SITE_COLUMNS)

    header = lines[0].split("\t")
    rows = [l.split("\t") for l in lines[2:] if l.strip()]
    if not rows:
        return pd.DataFrame(columns=SITE_COLUMNS)

    df = pd.DataFrame(rows, columns=header[: len(rows[0])])
    for col in SITE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[SITE_COLUMNS]


def fetch_all_active_streamgages(progress_callback=None):
    """Fetch active, real-time USGS stream sites for every state/territory
    and combine into one deduplicated, cleaned DataFrame.

    progress_callback, if given, is called as progress_callback(done, total,
    state_cd) after each state's request -- lets a UI layer show a progress
    bar without this module importing Streamlit itself. A state whose
    request fails is skipped (not fatal); failed codes are returned as the
    second item of the tuple.
    """
    frames = []
    failed = []
    total = len(STATE_CODES)
    for i, state_cd in enumerate(STATE_CODES):
        df = None
        # A handful of state requests fail transiently under the load of
        # ~56 back-to-back calls (timeouts / momentary connection resets)
        # even though the same request succeeds fine on its own -- retry a
        # couple of times with a short backoff before giving up on a state.
        for attempt in range(3):
            try:
                df = fetch_state_streamgages(state_cd)
                break
            except Exception:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        if df is not None:
            if not df.empty:
                frames.append(df)
        else:
            failed.append(state_cd)
        if progress_callback:
            progress_callback(i + 1, total, state_cd)

    if not frames:
        raise ValueError("Could not fetch USGS site data for any state.")

    all_sites = pd.concat(frames, ignore_index=True)
    all_sites["dec_lat_va"] = pd.to_numeric(all_sites["dec_lat_va"], errors="coerce")
    all_sites["dec_long_va"] = pd.to_numeric(all_sites["dec_long_va"], errors="coerce")
    all_sites["drain_area_va"] = pd.to_numeric(all_sites["drain_area_va"], errors="coerce")
    all_sites = all_sites.dropna(subset=["dec_lat_va", "dec_long_va"])
    all_sites = all_sites.drop_duplicates(subset=["site_no"]).reset_index(drop=True)
    all_sites["station_nm"] = all_sites["station_nm"].fillna("").str.strip().str.title()
    return all_sites, failed
