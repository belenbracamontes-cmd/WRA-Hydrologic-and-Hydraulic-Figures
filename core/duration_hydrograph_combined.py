"""Core data-fetching, percentile-banding, and plotting logic for the
Streamflow Duration Hydrograph tool (TWO stations, combined) -- sums the
daily flow of two stations (e.g. two tributaries above a confluence) and
computes percentile bands (3-7, user's choice) locally with pandas, since
NWIS's stat service only computes percentiles for real gauges.

This module is Streamlit-agnostic on purpose: it can be imported, tested, or
reused from a plain script. The Streamlit page (pages/4_Daily_Flow_Duration_Analysis.py)
is a thin UI layer on top of it.
"""

import calendar
import datetime as dt

import numpy as np
import pandas as pd
import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import rcParams

from core.branding import (
    BRAND_FONT_STACK,
    TERRACOTA_SHADE, TERRACOTA, CALIFORNIA_SUNSET, MOSS_GREEN,
    FIELD_GREEN, OCEAN_BLUE, OCEAN_BLUE_SHADE,
)

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = BRAND_FONT_STACK
rcParams["axes.titlesize"] = 13
rcParams["axes.labelsize"] = 11
rcParams["xtick.labelsize"] = 8
rcParams["ytick.labelsize"] = 8

# ── Color palettes, low flow -> high flow (7-point gradient; fewer bands are
#    sampled evenly from this same gradient, see get_palette_colors) ---------
DUR_COLOR_PALETTES = {
    "rainbow":   ["#D7191C", "#FD8D3C", "#FED976", "#78C679", "#41B6C4", "#2C7FB8", "#6A51A3"],
    "wra":       [TERRACOTA_SHADE, TERRACOTA, CALIFORNIA_SUNSET, MOSS_GREEN,
                  FIELD_GREEN, OCEAN_BLUE, OCEAN_BLUE_SHADE],
    "brownblue": ["#8C510A", "#D8B365", "#F6E8C3", "#F5F5F5", "#C7EAE5", "#5AB4AC", "#01665E"],
    "viridis":   ["#440154", "#443983", "#31688E", "#21918C", "#35B779", "#90D743", "#FDE725"],
}
DUR_PALETTE_LABELS = [
    ("Rainbow", "rainbow"),
    ("WRA Colors", "wra"),
    ("BrownBlue (hyswap default)", "brownblue"),
    ("Viridis (colorblind-friendly)", "viridis"),
]

# ── Percentile-band boundary sets, by number of bands requested -------------
# p25/p75 are always present, so the "normal" band is always identifiable.
DUR_BAND_BOUNDARIES = {
    3: ["min_va", "p25_va", "p75_va", "max_va"],
    4: ["min_va", "p10_va", "p25_va", "p75_va", "max_va"],
    5: ["min_va", "p10_va", "p25_va", "p75_va", "p90_va", "max_va"],
    6: ["min_va", "p05_va", "p10_va", "p25_va", "p75_va", "p90_va", "max_va"],
    7: ["min_va", "p05_va", "p10_va", "p25_va", "p75_va", "p90_va", "p95_va", "max_va"],
}

DUR_LINESTYLE_OPTIONS = [("Solid", "-"), ("Dashed", "--"), ("Dash-dot", "-."), ("Dotted", ":")]


def get_palette_colors(name, n_bands):
    """Sample n_bands colors evenly from the 7-color gradient so any band
    count (3-7) still reads as a smooth low-flow -> high-flow gradient."""
    full = DUR_COLOR_PALETTES.get(name, DUR_COLOR_PALETTES["rainbow"])
    idx = np.round(np.linspace(0, len(full) - 1, n_bands)).astype(int)
    return [full[i] for i in idx]


def band_defs(n_bands):
    """Build the (lower, upper, label) tuples for the requested band count."""
    bounds = DUR_BAND_BOUNDARIES[n_bands]

    def pretty(col):
        return {"min_va": "Min", "max_va": "Max"}.get(col, col.replace("_va", "").upper())

    defs = []
    for lower, upper in zip(bounds[:-1], bounds[1:]):
        label = f"{pretty(lower)} – {pretty(upper)}"
        if lower == "p25_va" and upper == "p75_va":
            label += "  (normal)"
        defs.append((lower, upper, label))
    return defs


def build_monthly_table(combined_df):
    """Monthly average/maximum/minimum COMBINED daily flow, computed across
    every year in the (possibly range-restricted) combined series."""
    d = combined_df.copy()
    d["month"] = d["date"].dt.month
    g = d.groupby("month")["flow_cfs"].agg(["mean", "max", "min"])
    g = g.reindex(range(1, 13))
    g.index = [calendar.month_abbr[m] for m in g.index]
    g.index.name = "Month"
    g.columns = ["Average (cfs)", "Maximum (cfs)", "Minimum (cfs)"]
    return g.round(1)


def fetch_period_of_record(site_no, parameter_cd="00060"):
    """Full available period of record for a site/parameter, from the NWIS
    site service's series catalog (a lightweight metadata call)."""
    url = "https://waterservices.usgs.gov/nwis/site/"
    params = {"sites": site_no, "format": "rdb",
              "seriesCatalogOutput": "true", "parameterCd": parameter_cd}
    try:
        r = requests.get(url, params=params, timeout=15)
        lines = [l for l in r.text.splitlines() if not l.startswith("#") and l.strip()]
        if len(lines) < 3:
            return None, None
        header = lines[0].split("\t")
        rows = [l.split("\t") for l in lines[2:] if l.strip()]
        if not rows:
            return None, None
        df = pd.DataFrame(rows, columns=header[: len(rows[0])])
        if "begin_date" not in df.columns or "end_date" not in df.columns:
            return None, None
        begin = pd.to_datetime(df["begin_date"], errors="coerce").min()
        end = pd.to_datetime(df["end_date"], errors="coerce").max()
        if pd.isna(begin) or pd.isna(end):
            return None, None
        return water_year_of(begin.date()), water_year_of(end.date())
    except Exception:
        return None, None


def build_summary_table(table_data, site1, site2, total1, total2,
                         rec_start_wy, rec_end_wy):
    """The monthly table with three extra rows on top: each station's own
    full period of record, and the combined water-year range actually used."""
    monthly = build_monthly_table(table_data)
    t1_txt = f"WY{total1[0]}-WY{total1[1]}" if total1[0] else "Unknown"
    t2_txt = f"WY{total2[0]}-WY{total2[1]}" if total2[0] else "Unknown"
    info = pd.DataFrame(
        {"Average (cfs)": [f"Station {site1}: {t1_txt}",
                            f"Station {site2}: {t2_txt}",
                            f"WY{rec_start_wy}-WY{rec_end_wy}"],
         "Maximum (cfs)": ["—", "—", "—"],
         "Minimum (cfs)": ["—", "—", "—"]},
        index=["Station 1 total period available",
               "Station 2 total period available",
               "Combined period used"],
    )
    info.index.name = "Month"
    return pd.concat([info, monthly])


def build_monthly_avg_series(combined_df, plot_year, year_type):
    """Monthly-average COMBINED flow, one point per month (mid-month),
    placed on the same plot-date axis as the rest of the chart."""
    d = combined_df.copy()
    d["month"] = d["date"].dt.month
    monthly = d.groupby("month")["flow_cfs"].mean().reindex(range(1, 13))
    rows = []
    for m in range(1, 13):
        rows.append({
            "plot_date": plot_date(m, 15, plot_year, year_type),
            "avg": monthly.loc[m],
        })
    out = pd.DataFrame(rows).dropna()
    out["plot_date"] = pd.to_datetime(out["plot_date"])
    return out.sort_values("plot_date")


def palette_swatch_html(name, n_bands):
    colors = get_palette_colors(name, n_bands)
    swatches = "".join(
        f"<div style='width:22px;height:20px;background:{c};"
        "display:inline-block;border:1px solid #999;margin-right:1px'></div>"
        for c in colors
    )
    return f"<div style='margin-top:3px'>{swatches}</div>"


def water_year_of(date):
    return date.year + 1 if date.month >= 10 else date.year


def plot_date(month, day, ref_year, year_type):
    """Map a (month, day) onto a single reference year's calendar."""
    month, day, ref_year = int(month), int(day), int(ref_year)
    yr = ref_year - 1 if (year_type == "water" and month >= 10) else ref_year
    try:
        return dt.date(yr, month, day)
    except ValueError:      # Feb 29 landing on a non-leap reference year
        return dt.date(yr, 2, 28)


def fetch_full_daily_flow(site_no, start_date="1890-01-01", end_date=None):
    """Pull the FULL available daily-mean-flow history for one station
    (as opposed to a single year) so it can be summed with another
    station's history before computing percentiles."""
    url = "https://waterservices.usgs.gov/nwis/dv/"
    params = {
        "format": "json",
        "sites": site_no,
        "startDT": start_date,
        "parameterCd": "00060",
        "statCd": "00003",
    }
    if end_date:
        params["endDT"] = end_date
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    ts = data.get("value", {}).get("timeSeries", [])
    if not ts:
        raise ValueError(f"No daily-value data returned for site {site_no}.")
    values = ts[0]["values"][0]["value"]
    df = pd.DataFrame(values)
    if df.empty:
        raise ValueError(f"No daily-value data returned for site {site_no}.")
    df["dateTime"] = pd.to_datetime(df["dateTime"]).dt.tz_localize(None)
    df["flow_cfs"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["flow_cfs"])
    return df.rename(columns={"dateTime": "date"})[["date", "flow_cfs"]]


def combine_two_stations(df1, df2):
    """Sum two stations' daily flow on matching dates only (inner join) --
    a date only counts if BOTH stations reported a value that day."""
    merged = pd.merge(df1, df2, on="date", suffixes=("_1", "_2"))
    if merged.empty:
        raise ValueError(
            "The two stations have no overlapping dates with data -- "
            "cannot combine them."
        )
    merged["flow_cfs"] = merged["flow_cfs_1"] + merged["flow_cfs_2"]
    return merged[["date", "flow_cfs"]].sort_values("date")


def compute_percentiles(combined_df, start_wy=None, end_wy=None):
    """Compute day-of-year percentile statistics locally from a combined
    daily flow series (mirrors what the NWIS stat service returns for a
    single real gauge, but for our virtual combined 'gauge')."""
    df = combined_df.copy()
    df["water_year"] = df["date"].apply(lambda d: water_year_of(d))
    if start_wy is not None and end_wy is not None:
        df = df[(df["water_year"] >= start_wy) & (df["water_year"] <= end_wy)]
    if df.empty:
        raise ValueError("No combined data available in the requested water-year range.")

    df["month_nu"] = df["date"].dt.month
    df["day_nu"] = df["date"].dt.day

    records = []
    for (m, d), grp in df.groupby(["month_nu", "day_nu"]):
        s = grp["flow_cfs"].dropna()
        if s.empty:
            continue
        records.append({
            "month_nu": m, "day_nu": d,
            "min_va": s.min(),
            "p05_va": s.quantile(0.05),
            "p10_va": s.quantile(0.10),
            "p25_va": s.quantile(0.25),
            "p50_va": s.quantile(0.50),
            "p75_va": s.quantile(0.75),
            "p90_va": s.quantile(0.90),
            "p95_va": s.quantile(0.95),
            "max_va": s.max(),
            "n_years": s.shape[0],
        })
    out = pd.DataFrame(records)
    if out.empty:
        raise ValueError("Could not compute percentiles from the combined data.")
    return out, int(df["water_year"].min()), int(df["water_year"].max())


def fetch_station_name(site_no):
    url = "https://waterservices.usgs.gov/nwis/site/"
    params = {"sites": site_no, "format": "rdb", "siteOutput": "expanded"}
    try:
        r = requests.get(url, params=params, timeout=15)
        for line in r.text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) > 2 and parts[0] == site_no:
                return parts[2].strip().title()
    except Exception:
        pass
    return f"USGS Station {site_no}"


# ── Plot ──────────────────────────────────────────────────────────────────────
def make_plot(pctl_aligned, flow_aligned, combined_label, year_type, plot_year,
              use_log, palette_name, show_median, n_bands, custom_title="",
              median_color="#FFFFFF", median_style="--",
              year_color="#000000", year_style="-",
              show_monthly_avg=False, monthly_avg_color="#000000",
              monthly_avg_style="-.", monthly_avg_series=None):
    colors = get_palette_colors(palette_name, n_bands)
    defs = band_defs(n_bands)

    fig, ax = plt.subplots(figsize=(13, 6))

    for (lower, upper, _label), color in zip(defs, colors):
        ax.fill_between(pctl_aligned["plot_date"], pctl_aligned[lower],
                         pctl_aligned[upper], color=color, alpha=0.85,
                         linewidth=0, zorder=1)

    if show_median:
        ax.plot(pctl_aligned["plot_date"], pctl_aligned["p50_va"],
                color=median_color, linewidth=1.0, linestyle=median_style, alpha=0.8,
                zorder=2, label="Median (P50)")

    if show_monthly_avg and monthly_avg_series is not None:
        ax.plot(monthly_avg_series["plot_date"], monthly_avg_series["avg"],
                color=monthly_avg_color, linewidth=1.6, linestyle=monthly_avg_style,
                marker="o", markersize=3, zorder=4, label="Monthly average")

    if flow_aligned is not None:
        yr_label = f"Water Year {plot_year}" if year_type == "water" else f"{plot_year}"
        ax.plot(flow_aligned["plot_date"], flow_aligned["flow_cfs"],
                color=year_color, linewidth=1.8, linestyle=year_style,
                zorder=5, label=f"{yr_label} combined daily mean")

    if use_log:
        ax.set_yscale("log")

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_xlim(pctl_aligned["plot_date"].min(), pctl_aligned["plot_date"].max())
    ax.set_xlabel("Month")
    ax.set_ylabel("Combined Discharge (cfs)")

    title_str = (custom_title.strip() if custom_title.strip() else
                 f"Combined Streamflow Percentiles by Day of Year - {combined_label}")
    ax.set_title(title_str, fontweight="bold")
    ax.grid(True, which="both", alpha=0.25)

    band_handles = [plt.Rectangle((0, 0), 1, 1, color=c, alpha=0.85) for c in colors]
    band_labels = [lbl for _, _, lbl in defs]
    line_handles, line_labels = ax.get_legend_handles_labels()
    ax.legend(list(reversed(band_handles)) + line_handles,
              list(reversed(band_labels)) + line_labels,
              loc="upper right", fontsize=7, framealpha=0.9, ncol=1)

    fig.text(0.99, 0.01, f"© {dt.date.today().year} WRA, Inc.",
              ha="right", va="bottom", fontsize=7,
              fontfamily="sans-serif", color="#888888")

    fig.tight_layout()
    return fig
