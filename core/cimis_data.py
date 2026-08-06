"""Core data-fetching and plotting logic for the CIMIS Weather Station Data
tool.

Pulls weather station data from the California Dept. of Water Resources'
CIMIS Web API. Unlike NOAA's tide API, CIMIS has no separate "observed vs.
predicted" split to blend -- every value is an actual station measurement,
each carrying a single QC flag (blank = good data; see QC_FLAG_MEANINGS
below for the rest). This module just chunks a long date range into
several requests and concatenates the results, the same pattern used
elsewhere in this app (NOAA tides, nationwide USGS fetch).

CIMIS's own client-library documentation recommends keeping a single
request to about a year for daily data and a week for hourly data (no hard
per-request cap is published, unlike NOAA's documented 31-day limit) --
DAILY_CHUNK_DAYS / HOURLY_CHUNK_DAYS below follow that guidance.

Every data request requires a personal, free "appKey" (register at
https://cimis.water.ca.gov/Auth/Register.aspx) -- the *station list*
(core/cimis_stations.py) does not need one, but actual data does.

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

from core.branding import BRAND_FONT_STACK
from core.cimis_stations import HEADERS

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = BRAND_FONT_STACK
rcParams["axes.titlesize"] = 13
rcParams["axes.labelsize"] = 11
rcParams["xtick.labelsize"] = 9
rcParams["ytick.labelsize"] = 9

DATA_URL = "https://et.water.ca.gov/api/data"

# (label, code) -- code is CIMIS's own dataItem slug, passed straight to the
# API's `dataItems` param. Every one of these is WSN (weather-station-
# network) data; CIMIS's spatial (gridded, non-station) products aren't
# exposed here since this tool is about a specific station.
DAILY_DATA_ITEMS = [
    ("Reference ETo (CIMIS)", "day-eto"),
    ("Reference ETo (ASCE)", "day-asce-eto"),
    ("Reference ETr (ASCE)", "day-asce-etr"),
    ("Precipitation", "day-precip"),
    ("Average Air Temperature", "day-air-tmp-avg"),
    ("Maximum Air Temperature", "day-air-tmp-max"),
    ("Minimum Air Temperature", "day-air-tmp-min"),
    ("Dew Point", "day-dew-pnt"),
    ("Average Relative Humidity", "day-rel-hum-avg"),
    ("Maximum Relative Humidity", "day-rel-hum-max"),
    ("Minimum Relative Humidity", "day-rel-hum-min"),
    ("Average Vapor Pressure", "day-vap-pres-avg"),
    ("Maximum Vapor Pressure", "day-vap-pres-max"),
    ("Average Solar Radiation", "day-sol-rad-avg"),
    ("Net Solar Radiation", "day-sol-rad-net"),
    ("Average Soil Temperature", "day-soil-tmp-avg"),
    ("Maximum Soil Temperature", "day-soil-tmp-max"),
    ("Minimum Soil Temperature", "day-soil-tmp-min"),
    ("Average Wind Speed", "day-wind-spd-avg"),
    ("Wind Run", "day-wind-run"),
]
HOURLY_DATA_ITEMS = [
    ("Reference ETo (CIMIS)", "hly-eto"),
    ("Reference ETo (ASCE)", "hly-asce-eto"),
    ("Reference ETr (ASCE)", "hly-asce-etr"),
    ("Precipitation", "hly-precip"),
    ("Air Temperature", "hly-air-tmp"),
    ("Dew Point", "hly-dew-pnt"),
    ("Relative Humidity", "hly-rel-hum"),
    ("Vapor Pressure", "hly-vap-pres"),
    ("Solar Radiation", "hly-sol-rad"),
    ("Net Radiation", "hly-net-rad"),
    ("Soil Temperature", "hly-soil-tmp"),
    ("Wind Speed", "hly-wind-spd"),
    ("Wind Direction", "hly-wind-dir"),
    ("Resultant Wind", "hly-res-wind"),
]
UNITS_OPTIONS = [("English", "E"), ("Metric", "M")]
SCOPE_OPTIONS = [("Daily", "daily"), ("Hourly", "hourly")]

# Not a NOAA-style hard API limit (CIMIS doesn't publish one) -- these
# follow the CIMIS client-library guidance of keeping a single request to
# roughly a year of daily data or a week of hourly data.
DAILY_CHUNK_DAYS = 365
HOURLY_CHUNK_DAYS = 7

# Documented CIMIS QC flags (CIMIS Data Quality Control Procedures, and the
# current-flags reference on cimis.water.ca.gov); a blank flag means the
# value passed QC cleanly. Other, rarer flags may still appear that aren't
# in this short list -- shown as-is rather than guessed at.
QC_FLAG_MEANINGS = {
    "": "Good / verified data",
    "Y": "Moderately out of historical limits",
    "M": "Missing",
    "S": "Sensor not in service, or reading outside sensor threshold",
    "R": "Far out of historical limits",
    "H": "Flagged because the underlying hourly data was flagged",
}


def _record_key(code):
    """'day-air-tmp-avg' -> 'DayAirTmpAvg' -- CIMIS's JSON response keys
    each requested item by a PascalCase version of its dataItems code."""
    return "".join(part.capitalize() for part in code.split("-"))


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


def _fetch_one(app_key, station_id, begin, end, item_codes, unit_of_measure):
    params = {
        "appKey": app_key,
        "targets": str(station_id),
        "startDate": begin.isoformat(),
        "endDate": end.isoformat(),
        "dataItems": ",".join(item_codes),
        "unitOfMeasure": unit_of_measure,
    }
    r = requests.get(DATA_URL, params=params, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        # CIMIS returns a clean, human-readable message like
        # '"[ERR1006-INVALID APP KEY] Invalid application key [...]."'
        # (verified directly against the live API) -- surface it as-is.
        raise ValueError(r.text.strip().strip('"'))
    data = r.json()
    providers = data.get("Data", {}).get("Providers", [])
    records = []
    for p in providers:
        records.extend(p.get("Records", []))
    return records


def fetch_cimis_data(app_key, station_id, begin_date, end_date, item_labels_codes,
                      unit_of_measure, scope="daily", progress_callback=None):
    """Fetch one or more CIMIS data items for a station over a date range,
    chunking as needed.

    item_labels_codes -- list of (label, code) tuples, e.g. a subset of
        DAILY_DATA_ITEMS/HOURLY_DATA_ITEMS.
    Returns a DataFrame with a Date (and Hour, if scope=="hourly") column
    plus two columns per requested item: "<label>" (the value) and
    "<label> QC" (its quality flag).
    """
    max_days = DAILY_CHUNK_DAYS if scope == "daily" else HOURLY_CHUNK_DAYS
    chunks = date_chunks(begin_date, end_date, max_days)
    codes = [code for _, code in item_labels_codes]

    all_records = []
    for i, (c_begin, c_end) in enumerate(chunks):
        if progress_callback:
            progress_callback(i, len(chunks), f"{c_begin} to {c_end}")
        all_records.extend(_fetch_one(app_key, station_id, c_begin, c_end, codes, unit_of_measure))
    if progress_callback:
        progress_callback(len(chunks), len(chunks), "done")

    if not all_records:
        return pd.DataFrame()

    rows = []
    for rec in all_records:
        row = {"Date": rec.get("Date")}
        if scope == "hourly":
            row["Hour"] = rec.get("Hour")
        for label, code in item_labels_codes:
            key = _record_key(code)
            item = rec.get(key) or {}
            value = item.get("Value")
            try:
                value = float(value)
            except (TypeError, ValueError):
                pass  # leave non-numeric placeholders (e.g. "--") as-is
            row[label] = value
            row[f"{label} QC"] = (item.get("Qc") or "").strip()
        rows.append(row)

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    if scope == "hourly":
        df = df.sort_values(["Date", "Hour"]).reset_index(drop=True)
    else:
        df = df.sort_values("Date").reset_index(drop=True)
    return df


def make_plot(df, station_label, item_labels, unit_label, custom_title=""):
    """One subplot per selected data item, stacked vertically and sharing
    an x-axis -- the natural layout for CIMIS's multi-parameter data
    (e.g. viewing ETo and Precipitation together), matching the stacked-
    subplot style used elsewhere in this app."""
    n = len(item_labels)
    fig, axes = plt.subplots(n, 1, figsize=(13, 3.2 * n), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, label in zip(axes, item_labels):
        ax.plot(df["Date"], df[label], color="#175536", linewidth=1.4)
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.3)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()

    title_str = custom_title.strip() if custom_title.strip() else f"{station_label} — CIMIS Weather Data"
    fig.suptitle(f"{title_str} ({unit_label})", fontweight="bold")
    fig.tight_layout()
    fig.text(0.99, 0.01, f"© {dt.date.today().year} WRA, Inc.",
              ha="right", va="bottom", fontsize=7, fontfamily="sans-serif", color="#888888")
    return fig
