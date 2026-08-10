"""Core data-fetching and plotting logic for the NOAA Tide Gage Data tool.

Pulls water level data from the NOAA CO-OPS ("Tides and Currents") Data
Getter API, which caps how much date range a single request can cover
(31 days at 6-minute resolution, 1 year at hourly/high-low resolution) --
this module chunks a longer request into multiple calls and concatenates
the results, the same pattern used for the nationwide USGS station fetch
elsewhere in this app.

For each timestamp in the requested range, this blends two NOAA products:
  - "water_level" -- actual observed readings. Each reading carries a
    quality flag ("v" = verified, "p" = preliminary) that NOAA itself
    assigns; verified data usually lags real time by about a month while
    it goes through QA, so recent dates are typically preliminary.
  - "predictions" -- the astronomical tide prediction model, always
    available for any date (past or future) since it's computed, not
    measured.
Observed data (verified or preliminary) is used wherever NOAA has it;
predictions fill in everything else (recent un-verified gaps, or dates
that haven't happened yet).

This module is Streamlit-agnostic on purpose: it can be imported, tested,
or reused from a plain script. The Streamlit page is a thin UI layer on
top of it, including the progress display during a long chunked fetch.
"""

import datetime as dt

import pandas as pd
import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import rcParams

from core.branding import BRAND_FONT_STACK, BRAND_DARK, OCEAN_BLUE_SHADE, OCEAN_BLUE_TINT, TERRACOTA_SHADE

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = BRAND_FONT_STACK
rcParams["axes.titlesize"] = 13
rcParams["axes.labelsize"] = 11
rcParams["xtick.labelsize"] = 9
rcParams["ytick.labelsize"] = 9

BASE_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
METADATA_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{station_id}.json"
DATUMS_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{station_id}/datums.json"
APPLICATION_NAME = "WRA-Hydrology-Tools"

# NOAA's standard tidal/geodetic datums -- not every station supports every
# datum (e.g. Great Lakes stations only support IGLD); NOAA's own API
# returns a clear error message when an unsupported one is requested, which
# this module surfaces as-is rather than guessing which datums are valid.
DATUM_OPTIONS = [
    ("Mean Lower Low Water (MLLW)", "MLLW"),
    ("Mean Sea Level (MSL)", "MSL"),
    ("Mean Tide Level (MTL)", "MTL"),
    ("Mean High Water (MHW)", "MHW"),
    ("Mean Higher High Water (MHHW)", "MHHW"),
    ("Mean Low Water (MLW)", "MLW"),
    ("NAVD 88 (NAVD)", "NAVD"),
    ("Station Datum (STND)", "STND"),
]
UNITS_OPTIONS = [("English (feet)", "english"), ("Metric (meters)", "metric")]
TIMEZONE_OPTIONS = [
    ("GMT", "gmt"),
    ("Local Standard Time (LST)", "lst"),
    ("Local Time, with DST (LST/LDT)", "lst_ldt"),
]
INTERVAL_OPTIONS = [("6-minute", "6"), ("Hourly", "h"), ("High/Low only", "hilo")]
SOURCE_OPTIONS = [
    ("Auto (observed, filled with predictions)", "auto"),
    ("Observed only (verified/preliminary)", "observed"),
    ("Predictions only", "predicted"),
]

# NOAA's water_level (observed) product always returns raw 6-minute data --
# the interval parameter has no effect on it (verified against the live
# API: requesting interval=h or hilo silently still returns 6-min rows),
# and it always caps a single request at 31 days regardless of interval.
# Only the predictions product actually honors interval (6/h/hilo) and
# accepts much longer date ranges per request; PREDICTION_CHUNK_DAYS below
# is just a practical chunk size (keeps individual responses/progress steps
# reasonably sized), not a NOAA-enforced limit.
OBSERVED_CHUNK_DAYS = 31
PREDICTION_CHUNK_DAYS = 365

STATUS_LABELS = {"v": "Verified", "p": "Preliminary"}
STATUS_SORT_ORDER = {"Verified": 0, "Preliminary": 1, "Predicted": 2}


def date_chunks(begin, end, max_days):
    """Split [begin, end] (date objects, inclusive) into (start, end) pairs
    each spanning at most max_days days."""
    if begin > end:
        raise ValueError("Begin date must be on or before end date.")
    chunks = []
    cur = begin
    span = dt.timedelta(days=max_days - 1)
    while cur <= end:
        chunk_end = min(cur + span, end)
        chunks.append((cur, chunk_end))
        cur = chunk_end + dt.timedelta(days=1)
    return chunks


def fetch_station_name(station_id):
    """Best-effort station name lookup; falls back to a generic label."""
    try:
        r = requests.get(METADATA_URL.format(station_id=station_id), timeout=15)
        r.raise_for_status()
        stations = r.json().get("stations", [])
        if stations:
            return stations[0].get("name", "").strip() or f"Station {station_id}"
    except Exception:
        pass
    return f"NOAA Station {station_id}"


def fetch_station_datums(station_id):
    """Fetch the tidal/geodetic datums NOAA actually has on file for a
    specific station (not every station supports every datum -- e.g. only
    stations surveyed to NAVD 88 support "NAVD", and Great Lakes stations
    use IGLD instead of the standard tidal datums).

    Returns a dict: {
        "units": "feet" or "meters",
        "orthometric_datum": "NAVD88" (or "" if the station isn't tied to one),
        "datums": [{"name": "MLLW", "description": "...", "value": -0.123}, ...],
    }, or None if the lookup fails (unknown station, network error, etc.) --
    callers should treat None as "unavailable" and fall back to the full
    standard DATUM_OPTIONS list rather than blocking the user.
    """
    try:
        r = requests.get(DATUMS_URL.format(station_id=station_id), timeout=15)
        r.raise_for_status()
        data = r.json()
        if "error" in data or not data.get("datums"):
            return None
        return {
            "units": data.get("units", ""),
            "orthometric_datum": (data.get("OrthometricDatum") or "").strip(),
            "datums": data["datums"],
        }
    except Exception:
        return None


def available_datum_codes(station_datums):
    """Given a fetch_station_datums() result, return the subset of this
    module's standard DATUM_OPTIONS codes that this station actually
    supports. NAVD is exposed via the separate "OrthometricDatum" field
    rather than inside the "datums" list itself, so it's checked separately.
    STND (station datum) is always valid for every station."""
    if not station_datums:
        return {code for _, code in DATUM_OPTIONS}
    codes = {d["name"] for d in station_datums["datums"]}
    codes.add("STND")
    if station_datums.get("orthometric_datum"):
        codes.add("NAVD")
    return {code for _, code in DATUM_OPTIONS if code in codes}


def _fetch_one(station, product, begin, end, datum, units, time_zone, interval=None):
    """One datagetter call for a single chunk. Returns a DataFrame with
    columns t (timestamp string), v (value string), and q (quality flag,
    only present for water_level).

    interval is only honored for product="predictions" -- water_level
    (observed) silently ignores it and always returns raw 6-minute data
    regardless of what's requested, verified against the live API."""
    params = {
        "station": station,
        "product": product,
        "datum": datum,
        "units": units,
        "time_zone": time_zone,
        "format": "json",
        "application": APPLICATION_NAME,
        "begin_date": begin.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
    }
    if product == "predictions" and interval and interval != "6":
        params["interval"] = interval

    r = requests.get(BASE_URL, params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()

    if "error" in payload:
        message = payload["error"].get("message", "Unknown NOAA CO-OPS API error.")
        # "No data was found" for a chunk is a normal, expected outcome here
        # (e.g. a recent chunk NOAA hasn't verified yet, or a future chunk
        # for the observed product) -- not a real failure worth surfacing.
        if "no data was found" in message.lower():
            return pd.DataFrame(columns=["t", "v", "q"])
        raise ValueError(message)

    key = "predictions" if product == "predictions" else "data"
    rows = payload.get(key, [])
    if not rows:
        return pd.DataFrame(columns=["t", "v", "q"])

    df = pd.DataFrame(rows)
    if "q" not in df.columns:
        df["q"] = None
    return df[["t", "v", "q"]]


def fetch_tide_data(station, begin_date, end_date, datum, units, time_zone, interval,
                     source="auto", progress_callback=None):
    """Fetch and blend NOAA tide data for one station over an arbitrarily
    long date range.

    station              -- NOAA CO-OPS station ID (string)
    begin_date, end_date  -- python date objects, inclusive
    datum, units, time_zone, interval -- NOAA API parameter values (see the
        *_OPTIONS constants above for valid choices)
    source                -- "auto" (observed, predictions fill gaps),
        "observed" (verified/preliminary only, no predictions), or
        "predicted" (predictions only)
    progress_callback, if given, is called as progress_callback(done, total,
        label) after each chunked request -- lets a UI layer show progress
        without this module importing Streamlit.

    Returns a DataFrame with columns: date, time, water_level, status
    (status is one of "Verified", "Preliminary", "Predicted"), sorted by
    time, one row per available timestamp.
    """
    observed_chunks = date_chunks(begin_date, end_date, OBSERVED_CHUNK_DAYS)
    prediction_chunks = date_chunks(begin_date, end_date, PREDICTION_CHUNK_DAYS)
    total_calls = (len(observed_chunks) if source in ("auto", "observed") else 0) + \
                  (len(prediction_chunks) if source in ("auto", "predicted") else 0)
    done = 0

    observed = pd.DataFrame(columns=["t", "v", "q"])
    if source in ("auto", "observed"):
        frames = []
        for c_start, c_end in observed_chunks:
            frames.append(_fetch_one(station, "water_level", c_start, c_end, datum, units, time_zone))
            done += 1
            if progress_callback:
                progress_callback(done, total_calls, "observed water levels")
        if frames:
            observed = pd.concat(frames, ignore_index=True)

    predicted = pd.DataFrame(columns=["t", "v", "q"])
    if source in ("auto", "predicted"):
        frames = []
        for c_start, c_end in prediction_chunks:
            frames.append(_fetch_one(station, "predictions", c_start, c_end, datum, units, time_zone, interval))
            done += 1
            if progress_callback:
                progress_callback(done, total_calls, "tide predictions")
        if frames:
            predicted = pd.concat(frames, ignore_index=True)

    observed = observed.rename(columns={"v": "water_level"}).copy()
    if not observed.empty:
        observed["status"] = observed["q"].map(STATUS_LABELS).fillna("Verified")
    observed = observed.reindex(columns=["t", "water_level", "status"])

    predicted = predicted.rename(columns={"v": "water_level"}).copy()
    if not predicted.empty:
        predicted["status"] = "Predicted"
    predicted = predicted.reindex(columns=["t", "water_level", "status"])

    combined = pd.concat([observed, predicted], ignore_index=True)
    if combined.empty:
        return pd.DataFrame(columns=["date", "time", "water_level", "status"])

    combined["t"] = pd.to_datetime(combined["t"])
    combined["water_level"] = pd.to_numeric(combined["water_level"], errors="coerce")
    combined = combined.dropna(subset=["t", "water_level"])

    # Where both an observed reading and a prediction exist for the exact
    # same timestamp, keep the observed one (verified beats preliminary
    # beats predicted).
    combined["_sort"] = combined["status"].map(STATUS_SORT_ORDER)
    combined = combined.sort_values("_sort").drop_duplicates(subset="t", keep="first")
    combined = combined.sort_values("t").reset_index(drop=True)

    combined["date"] = combined["t"].dt.date
    combined["time"] = combined["t"].dt.strftime("%H:%M")
    return combined[["date", "time", "water_level", "status"]]


def make_plot(df, station_label, datum, units, custom_title="",
              predicted_color=OCEAN_BLUE_TINT, observed_color=OCEAN_BLUE_SHADE):
    """Build the water-level time series plot.

    df must have the columns returned by fetch_tide_data (date, time,
    water_level, status). Returns the matplotlib Figure.
    """
    d = df.copy()
    d["dt"] = pd.to_datetime(d["date"].astype(str) + " " + d["time"])

    observed = d[d["status"] != "Predicted"]
    predicted = d[d["status"] == "Predicted"]

    fig, ax = plt.subplots(figsize=(13, 6))

    if not predicted.empty:
        ax.plot(predicted["dt"], predicted["water_level"], color=predicted_color,
                 linestyle="--", linewidth=1.3, label="Predicted", zorder=1)
    if not observed.empty:
        ax.plot(observed["dt"], observed["water_level"], color=observed_color,
                 linewidth=1.5, label="Observed (verified/preliminary)", zorder=2)

    unit_label = "ft" if units == "english" else "m"
    ax.set_ylabel(f"Water Level ({datum}, {unit_label})", fontsize=11)
    ax.set_xlabel("Date", fontsize=11)

    title_str = custom_title.strip() if custom_title.strip() else f"Water Level — {station_label}"
    ax.set_title(title_str, fontsize=13, fontweight="bold", color=BRAND_DARK)
    ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.4)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9)

    fig.autofmt_xdate()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%Y"))

    fig.text(0.99, 0.01, "© WRA, Inc.  ·  Data: NOAA CO-OPS",
              ha="right", va="bottom", fontsize=7,
              fontfamily="sans-serif", color="#888888")

    fig.tight_layout()
    return fig
