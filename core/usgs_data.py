"""Core data-fetching and plotting logic for the general-purpose USGS Data
Retrieval tool.

Unlike the flow-specific USGS tools elsewhere in this app (Peak Flow
Viewer, Annual Flow Chart, LP3, Daily Flow & Duration Analysis, Water Year
Type -- all built around parameter 00060 streamflow specifically), this
pulls WHATEVER data a given USGS site actually reports: streamflow, gage
height / water-surface elevation, water temperature, specific
conductance, dissolved oxygen, turbidity, and more -- discovered live per
station from NWIS's own site data-series catalog rather than assumed in
advance.

Two NWIS services are involved -- confirmed directly against the live
API before writing this -- and a given parameter is typically only
available from ONE of them for any given site:
  - Daily Values (dv) -- one aggregated value per day (Mean/Max/Min/etc),
    covering potentially decades in a single request (the same service
    the rest of this app's USGS tools already use).
  - Instantaneous Values (iv -- still labeled "uv" in the site catalog's
    own data_type_cd column, its older name) -- raw sensor readings at
    their native reporting interval (often 15 minutes). This is where
    gage height / water-surface elevation usually lives at most gauges,
    since it's rarely computed as a daily statistic. Native-interval data
    over a long date range can be a lot of rows (confirmed: ~92,000 rows
    for one parameter over 2.5 years), so the page surfaces a caution
    rather than silently fetching everything.
"""

import datetime as dt

import pandas as pd
import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import rcParams

from core.branding import BRAND_FONT_STACK, TERRACOTA_SHADE

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = BRAND_FONT_STACK
rcParams["axes.titlesize"] = 13
rcParams["axes.labelsize"] = 11
rcParams["xtick.labelsize"] = 9
rcParams["ytick.labelsize"] = 9

SITE_SERVICE_URL = "https://waterservices.usgs.gov/nwis/site/"
DV_SERVICE_URL = "https://waterservices.usgs.gov/nwis/dv/"
IV_SERVICE_URL = "https://waterservices.usgs.gov/nwis/iv/"

DEFAULT_ITEM_COLOR = TERRACOTA_SHADE

# A reasonably broad set of common USGS parameter codes -- not exhaustive
# (NWIS supports hundreds), but covers what most WRA projects actually
# pull: streamflow, gage height / water-surface elevation, temperature,
# and common water-quality sensors. Anything not listed here still
# works -- it just shows as "Parameter {code}" instead of a friendly name.
PARAMETER_NAMES = {
    "00010": "Water Temperature (deg C)",
    "00020": "Air Temperature (deg C)",
    "00025": "Barometric Pressure (mm Hg)",
    "00035": "Wind Speed (mph)",
    "00036": "Wind Direction (deg)",
    "00045": "Precipitation (in)",
    "00060": "Streamflow (cfs)",
    "00065": "Gage Height (ft)",
    "00095": "Specific Conductance (uS/cm)",
    "00300": "Dissolved Oxygen (mg/L)",
    "00301": "Dissolved Oxygen (% saturation)",
    "00400": "pH",
    "00480": "Salinity (ppt)",
    "62611": "Groundwater Level (ft below land surface)",
    "62614": "Lake/Reservoir Elevation, NGVD29 (ft)",
    "62615": "Lake/Reservoir Elevation, NAVD88 (ft)",
    "63680": "Turbidity (FNU)",
    "72019": "Depth to Water Level (ft below land surface)",
    "72020": "Water Surface Elevation, NGVD29 (ft)",
    "72137": "Tidally Filtered Discharge (cfs)",
    "72255": "Mean Water Velocity (ft/s)",
    "80154": "Suspended Sediment Concentration (mg/L)",
    "80155": "Suspended Sediment Discharge (tons/day)",
    "99133": "Nitrate + Nitrite (mg/L as N)",
}

STAT_NAMES = {
    "00001": "Max", "00002": "Min", "00003": "Mean",
    "00006": "Sum", "00008": "Median", "00011": "Instantaneous",
}

# Parameters most WRA projects reach for first -- surfaced at the top of
# the data-items list; everything else sorts alphabetically after these.
_PRIORITY_PARAMS = {"00060": 0, "00065": 1, "00010": 2}


def _parse_rdb(text):
    """Parse a USGS RDB-format response into a DataFrame. RDB has a
    header row, then a format-spec row (e.g. "5s\\t15s\\t..."), then data --
    confirmed directly against a live seriesCatalogOutput response."""
    lines = [l for l in text.splitlines() if not l.startswith("#") and l.strip()]
    if len(lines) < 3:
        return pd.DataFrame()
    header = lines[0].split("\t")
    rows = [l.split("\t") for l in lines[2:] if l.strip()]
    rows = [r for r in rows if len(r) == len(header)]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=header)


def fetch_available_parameters(site_no):
    """Query NWIS's site data-series catalog for every parameter this
    station actually reports, from either the Daily Values or
    Instantaneous Values service. Returns a list of dicts, sorted with
    the most commonly used parameters first:
        {parm_cd, stat_cd, service ("dv" or "iv"), label, begin_date,
         end_date, count}
    Returns [] if the station has no daily/instantaneous series on file,
    or the lookup fails outright.
    """
    try:
        r = requests.get(SITE_SERVICE_URL, params={
            "sites": site_no, "format": "rdb", "seriesCatalogOutput": "true",
        }, timeout=20)
        r.raise_for_status()
    except Exception:
        return []

    df = _parse_rdb(r.text)
    needed = {"data_type_cd", "parm_cd", "stat_cd", "begin_date", "end_date", "count_nu"}
    if not needed.issubset(df.columns):
        return []

    df = df[df["data_type_cd"].isin(["dv", "uv"])].copy()
    if df.empty:
        return []

    results = []
    for _, row in df.iterrows():
        parm_cd = row["parm_cd"]
        if not parm_cd:
            continue
        service = "dv" if row["data_type_cd"] == "dv" else "iv"
        stat_cd = row["stat_cd"] if service == "dv" else ""
        name = PARAMETER_NAMES.get(parm_cd, f"Parameter {parm_cd}")
        if service == "dv":
            stat_name = STAT_NAMES.get(stat_cd, stat_cd or "Daily")
            label = f"{name} (Daily {stat_name})"
        else:
            label = f"{name} (Instantaneous)"
        results.append({
            "parm_cd": parm_cd, "stat_cd": stat_cd, "service": service, "label": label,
            "begin_date": row["begin_date"], "end_date": row["end_date"], "count": row["count_nu"],
        })

    # De-dup identical (parm_cd, stat_cd, service) triples that sometimes
    # repeat in the catalog under different ts_id's (e.g. two sensors for
    # the same parameter over different date spans).
    seen, deduped = set(), []
    for item in results:
        key = (item["parm_cd"], item["stat_cd"], item["service"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    deduped.sort(key=lambda x: (_PRIORITY_PARAMS.get(x["parm_cd"], 99), x["label"]))
    return deduped


def fetch_usgs_series(site_no, items, begin_date, end_date, progress_callback=None):
    """Pull one or more catalog items (as returned by
    fetch_available_parameters) over a date range.

    Returns {label: DataFrame with columns [Date, value]} -- one entry
    per requested item, kept separate rather than merged into one wide
    table, since "dv" items are daily and "iv" items are at their own
    native interval (often 15 minutes) -- they don't share a common date
    grid to merge onto. Items that come back empty (no data in that
    range) are silently omitted from the result.
    """
    series = {}
    for i, item in enumerate(items):
        if progress_callback:
            progress_callback(i, len(items), item["label"])

        url = DV_SERVICE_URL if item["service"] == "dv" else IV_SERVICE_URL
        params = {
            "format": "json", "sites": site_no,
            "startDT": begin_date.isoformat(), "endDT": end_date.isoformat(),
            "parameterCd": item["parm_cd"],
        }
        if item["service"] == "dv" and item["stat_cd"]:
            params["statCd"] = item["stat_cd"]

        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue

        ts_list = data.get("value", {}).get("timeSeries", [])
        if not ts_list:
            continue
        values = ts_list[0]["values"][0]["value"]
        if not values:
            continue

        s = pd.DataFrame(values)
        # USGS timestamps carry a local UTC offset (e.g. "...T00:00:00.000-07:00")
        # that flips across DST transitions within a single request's date
        # range -- pandas rejects mixed offsets outright unless told to
        # normalize to UTC (which would shift the displayed clock time).
        # Since the offset is just local standard/daylight time for a
        # station that's always in one timezone, slicing it off keeps the
        # wall-clock reading exactly as USGS reported it, with no tz math.
        s["dateTime"] = pd.to_datetime(s["dateTime"].str.slice(0, 19), errors="coerce")
        s["value"] = pd.to_numeric(s["value"], errors="coerce")
        s = s.dropna(subset=["dateTime", "value"]).rename(columns={"dateTime": "Date"})[["Date", "value"]]
        if not s.empty:
            series[item["label"]] = s.sort_values("Date").reset_index(drop=True)

    if progress_callback:
        progress_callback(len(items), len(items), "done")
    return series


def make_plot(series, station_label, custom_title="", colors=None):
    """One subplot per requested data item, stacked vertically, sharing
    an x-axis -- same layout convention as the CIMIS/PRISM tools. Each
    subplot uses its own native time resolution (daily vs. instantaneous),
    since the series aren't merged onto a common date grid.
    """
    colors = colors or {}
    labels = list(series.keys())
    n = len(labels)
    fig, axes = plt.subplots(n, 1, figsize=(13, 3.2 * n), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, label in zip(axes, labels):
        df = series[label]
        ax.plot(df["Date"], df["value"], color=colors.get(label, DEFAULT_ITEM_COLOR), linewidth=1.2)
        ax.set_ylabel(label, fontsize=8.5)
        ax.grid(True, alpha=0.3)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()

    title_str = custom_title.strip() if custom_title.strip() else f"{station_label} — USGS Data"
    fig.suptitle(title_str, fontweight="bold")
    fig.tight_layout()
    fig.text(0.99, 0.01, f"© {dt.date.today().year} WRA, Inc.",
              ha="right", va="bottom", fontsize=7, fontfamily="sans-serif", color="#888888")
    return fig
