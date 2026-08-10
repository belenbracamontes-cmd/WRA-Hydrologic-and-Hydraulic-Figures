"""Core data-fetching and plotting logic for the PRISM Climate Data tool.

PRISM (the Parameter-elevation Regressions on Independent Slopes Model, run
by Oregon State University's PRISM Climate Group) is fundamentally
different from the USGS/NOAA/CIMIS networks elsewhere in this app: it's a
spatially continuous *gridded* climate dataset covering the contiguous US
(CONUS), not a network of discrete stations. There's no station list to
pick from -- you specify a point (latitude/longitude) and PRISM interpolates
its 4km or 800m grid to that point.

This module talks to the same backend the public PRISM Data Explorer
(https://prism.oregonstate.edu/explorer/) uses -- reverse-engineered by
reading that page's own JS (dataexplorer/js/explorer.js) and confirmed
directly against the live API, since it isn't otherwise documented. No
API key is needed (a pleasant contrast to CIMIS's appKey requirement).

Location search/geocoding uses OpenStreetMap's free Nominatim service (no
key needed either) purely as a convenience for turning a place name into
coordinates -- everything else here is PRISM's own API.

This module is Streamlit-agnostic on purpose: it can be imported, tested,
or reused from a plain script. The Streamlit pages are a thin UI layer on
top of it.
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

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = BRAND_FONT_STACK
rcParams["axes.titlesize"] = 13
rcParams["axes.labelsize"] = 11
rcParams["xtick.labelsize"] = 9
rcParams["ytick.labelsize"] = 9

RPC_URL = "https://prism.oregonstate.edu/explorer/dataexplorer/rpc.php"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "WRA-Hydrology-Tools (internal consulting use)"}

# PRISM's own CONUS grid extent (from the Data Explorer's map_extent) --
# points outside this box always come back as a clean LonLatOutOfRangeError,
# so this lets the page reject them before even making a request.
CONUS_BOUNDS = {"min_lon": -125.0208333, "max_lon": -66.4791667,
                 "min_lat": 24.0625000, "max_lat": 49.9375000}

# (label, code) -- code is PRISM's own variable slug, passed straight to
# the API's `stats` param (space-separated).
VARIABLES = [
    ("Precipitation", "ppt"),
    ("Mean Temperature", "tmean"),
    ("Minimum Temperature", "tmin"),
    ("Maximum Temperature", "tmax"),
    ("Mean Dew Point Temperature", "tdmean"),
    ("Minimum Vapor Pressure Deficit", "vpdmin"),
    ("Maximum Vapor Pressure Deficit", "vpdmax"),
    ("Total Solar Radiation", "soltotal"),
    ("Solar Radiation on Slope", "solslope"),
    ("Clear Sky Solar Radiation", "solclear"),
    ("Cloud Transmittance", "soltrans"),
]
RANGE_OPTIONS = [("Daily", "daily"), ("Monthly", "monthly"), ("Annual", "yearly")]
UNITS_OPTIONS = [("English", "eng"), ("Metric (SI)", "si")]
RESOLUTION_OPTIONS = [("4 km", "4km"), ("800 m", "800m")]

# Not a documented hard cap (PRISM's own explorer sets a generous 5-minute
# ajax timeout, suggesting large requests are tolerated) -- these just keep
# individual requests/progress steps reasonably sized, chunked in whole
# years so date keys stay simple to generate.
DAILY_CHUNK_YEARS = 5
MONTHLY_CHUNK_YEARS = 20


def in_conus(lat, lon):
    return (CONUS_BOUNDS["min_lat"] <= lat <= CONUS_BOUNDS["max_lat"]
            and CONUS_BOUNDS["min_lon"] <= lon <= CONUS_BOUNDS["max_lon"])


def _post(params):
    r = requests.post(RPC_URL, data=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        # PRISM returns errors as a list of [code, message] pairs, e.g.
        # [["LonLatOutOfRangeError", "Location is out of grid range"]]
        # (verified directly against the live API).
        msg = "; ".join(e[1] if isinstance(e, (list, tuple)) and len(e) > 1 else str(e)
                         for e in data["errors"])
        raise ValueError(msg)
    return data


def fetch_location_info(lat, lon):
    """State/county/elevation for a point, via PRISM's own lookup (the
    same one the Data Explorer uses to annotate a clicked point). Returns
    a dict: {state, county, elev_4km_ft, elev_800m_ft} (elevations in feet
    -- PRISM's location_data endpoint always returns them in feet
    regardless of the units chosen elsewhere)."""
    data = _post({"proc": "location_data", "lon": lon, "lat": lat})
    elev = data.get("elev") or {}
    return {
        "state": data.get("state") or "",
        "county": data.get("county") or "",
        "elev_4km_ft": (elev.get("4km") or {}).get("raw"),
        "elev_800m_ft": (elev.get("800m") or {}).get("raw"),
    }


def fetch_climate_normals(lat, lon, resolution="800m"):
    """1991-2020 monthly climate normals for a point -- a quick-reference
    lookup (mirrors the "which datum/QC flags apply here" info panels on
    the NOAA/CIMIS pages), not the main time-series pull.

    Returns {var_code: [12 monthly values], ...} plus "annual_normals":
    {var_code: annual value, ...}.
    """
    params = {
        "proc": "gridserv", "call": "pp/monthly_normals_timeseries",
        "lon": lon, "lat": lat, "elev": "",
        "spares": resolution, "interp": "0",
        "stats": "ppt tmin tmean tmax tdmean", "units": "eng",
        "range": "monthly_normals", "start": "", "end": "", "stability": "",
    }
    data = _post(params)
    result = data.get("result") or {}
    return {"monthly": result.get("data") or {}, "annual": result.get("annual_normals") or {}}


def _date_keys(range_key, begin, end):
    """Build the list of PRISM date-key strings PRISM's response values
    line up with, in order -- the API returns parallel value arrays with
    no timestamps of their own, one entry per year/month/day in range."""
    keys = []
    if range_key == "yearly":
        for y in range(begin.year, end.year + 1):
            keys.append(str(y))
    elif range_key == "monthly":
        y, m = begin.year, begin.month
        while (y, m) <= (end.year, end.month):
            keys.append(f"{y:04d}{m:02d}")
            m += 1
            if m > 12:
                m = 1
                y += 1
    else:  # daily
        cur = begin
        while cur <= end:
            keys.append(cur.strftime("%Y%m%d"))
            cur += dt.timedelta(days=1)
    return keys


def _date_chunks(range_key, begin, end):
    """Split a date range into whole-year chunks for daily/monthly
    requests (yearly requests are small enough to send in one call)."""
    if range_key == "yearly":
        return [(begin, end)]
    chunk_years = DAILY_CHUNK_YEARS if range_key == "daily" else MONTHLY_CHUNK_YEARS
    chunks = []
    cur_start = begin
    while cur_start <= end:
        cur_end_year = min(cur_start.year + chunk_years - 1, end.year)
        cur_end = dt.date(cur_end_year, 12, 31) if cur_end_year < end.year else end
        chunks.append((cur_start, cur_end))
        cur_start = dt.date(cur_end.year + 1, 1, 1)
    return chunks


def _format_bound(range_key, d):
    if range_key == "yearly":
        return str(d.year)
    if range_key == "monthly":
        return f"{d.year:04d}{d.month:02d}"
    return d.strftime("%Y%m%d")


def fetch_prism_timeseries(lat, lon, range_key, begin, end, item_labels_codes,
                            units, resolution, progress_callback=None):
    """Fetch one or more PRISM variables for a point over a date range,
    chunking as needed.

    item_labels_codes -- list of (label, code) tuples, e.g. a subset of
        VARIABLES. range_key -- "daily", "monthly", or "yearly".
    Returns a DataFrame with a Date column plus one column per requested
    variable (named by label).
    """
    codes = [code for _, code in item_labels_codes]
    chunks = _date_chunks(range_key, begin, end)

    all_dates, values_by_code = [], {code: [] for code in codes}
    for i, (c_begin, c_end) in enumerate(chunks):
        if progress_callback:
            progress_callback(i, len(chunks), f"{c_begin} to {c_end}")
        params = {
            "proc": "gridserv", "call": f"pp/{range_key}_timeseries",
            "lon": lon, "lat": lat, "elev": "",
            "spares": resolution, "interp": "0",
            "stats": " ".join(codes), "units": units,
            "range": range_key,
            "start": _format_bound(range_key, c_begin), "end": _format_bound(range_key, c_end),
            "stability": "",
        }
        data = _post(params)
        result_data = (data.get("result") or {}).get("data") or {}
        chunk_dates = _date_keys(range_key, c_begin, c_end)
        all_dates.extend(chunk_dates)
        for code in codes:
            vals = result_data.get(code) or []
            if len(vals) != len(chunk_dates):
                # Defensive -- PRISM's grid has no station-style data
                # gaps, but pad/truncate rather than crash if a chunk
                # ever comes back a different length than expected.
                vals = (list(vals) + [None] * len(chunk_dates))[: len(chunk_dates)]
            values_by_code[code].extend(vals)
    if progress_callback:
        progress_callback(len(chunks), len(chunks), "done")

    if not all_dates:
        return pd.DataFrame()

    if range_key == "yearly":
        date_index = pd.to_datetime([f"{k}-01-01" for k in all_dates])
    elif range_key == "monthly":
        date_index = pd.to_datetime([f"{k[:4]}-{k[4:6]}-01" for k in all_dates])
    else:
        date_index = pd.to_datetime(all_dates, format="%Y%m%d")

    df = pd.DataFrame({"Date": date_index})
    for label, code in item_labels_codes:
        df[label] = pd.to_numeric(pd.Series(values_by_code[code]), errors="coerce")
    return df.sort_values("Date").reset_index(drop=True)


def geocode_place(query, limit=5):
    """Turn a place name/address into candidate (display_name, lat, lon)
    matches via OpenStreetMap's free Nominatim service -- a convenience
    for users who don't already know a point's coordinates. Returns []
    on any failure rather than raising, since this is just a search-box
    helper, not the core data path."""
    try:
        r = requests.get(NOMINATIM_URL, params={"q": query, "format": "json", "limit": limit},
                          headers=HEADERS, timeout=15)
        r.raise_for_status()
        return [
            {"display_name": m.get("display_name", ""), "lat": float(m["lat"]), "lon": float(m["lon"])}
            for m in r.json()
        ]
    except Exception:
        return []


DEFAULT_ITEM_COLOR = "#175536"


def make_plot(df, location_label, item_labels, unit_label, custom_title="", colors=None):
    """One subplot per selected variable, stacked vertically and sharing
    an x-axis -- the same multi-parameter layout used for CIMIS weather
    data, since PRISM is likewise inherently multi-variable.

    colors -- optional {item_label: hex} dict overriding the default line
        color per subplot; any label not present falls back to
        DEFAULT_ITEM_COLOR.
    """
    colors = colors or {}
    n = len(item_labels)
    fig, axes = plt.subplots(n, 1, figsize=(13, 3.2 * n), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, label in zip(axes, item_labels):
        ax.plot(df["Date"], df[label], color=colors.get(label, DEFAULT_ITEM_COLOR), linewidth=1.4)
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.3)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()

    title_str = custom_title.strip() if custom_title.strip() else f"{location_label} — PRISM Climate Data"
    fig.suptitle(f"{title_str} ({unit_label})", fontweight="bold")
    fig.tight_layout()
    fig.text(0.99, 0.01, f"© {dt.date.today().year} WRA, Inc.",
              ha="right", va="bottom", fontsize=7, fontfamily="sans-serif", color="#888888")
    return fig
