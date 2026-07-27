"""Core data-fetching and plotting logic for the Historical Daily Flow Range
Viewer tool (min-max band + mean daily flow for one or two USGS gauges,
aligned onto a single water-year or calendar-year timeline).

This module is Streamlit-agnostic on purpose: it can be imported, tested, or
reused from a plain script. The Streamlit page (pages/4_Daily_Flow_Duration_Analysis.py)
is a thin UI layer on top of it.
"""

import calendar
import datetime as dt
from io import StringIO

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
rcParams["xtick.labelsize"] = 8
rcParams["ytick.labelsize"] = 8


# ── Water-year helpers ────────────────────────────────────────────────────────
def water_year_of(date):
    return date.year + 1 if date.month >= 10 else date.year


def to_plot_date(date, target_wy):
    ref_year = target_wy - 1 if date.month >= 10 else target_wy
    try:
        return dt.date(ref_year, date.month, date.day)
    except ValueError:
        return dt.date(ref_year, 2, 28)


# ── Data fetch / transform ────────────────────────────────────────────────────
def fetch_site_daily_flow(site_no, start, end=None):
    url = "https://waterservices.usgs.gov/nwis/dv/"
    params = {
        "format": "json",
        "sites": site_no,
        "startDT": start,
        "parameterCd": "00060",
        "statCd": "00003",
    }
    if end:
        params["endDT"] = end
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    values = data["value"]["timeSeries"][0]["values"][0]["value"]
    df = pd.DataFrame(values)
    if df.empty:
        raise ValueError(f"No daily-value data returned for site {site_no}.")
    df["dateTime"] = pd.to_datetime(df["dateTime"]).dt.tz_localize(None)
    df["flow_cfs"] = pd.to_numeric(df["value"])
    return df.rename(columns={"dateTime": "date"})[["date", "flow_cfs"]]


def process_site(df_all, target_wy):
    df_all = df_all.copy()
    df_all["water_year"] = df_all["date"].apply(water_year_of)
    df_all["plot_date"] = df_all["date"].apply(lambda d: to_plot_date(d, target_wy))
    stats = df_all.groupby("plot_date")["flow_cfs"].agg(["min", "mean", "max"]).reset_index()
    stats["plot_date"] = pd.to_datetime(stats["plot_date"])
    stats = stats.sort_values("plot_date")
    return stats


def build_monthly_table(raw_df):
    """Monthly average/maximum/minimum daily flow, computed across every
    year in the fetched record (calendar-month grouping, Jan-Dec)."""
    d = raw_df.copy()
    d["month"] = d["date"].dt.month
    g = d.groupby("month")["flow_cfs"].agg(["mean", "max", "min"])
    g = g.reindex(range(1, 13))
    g.index = [calendar.month_abbr[m] for m in g.index]
    g.index.name = "Month"
    g.columns = ["Average (cfs)", "Maximum (cfs)", "Minimum (cfs)"]
    return g.round(1)


def fetch_period_of_record(site_no, parameter_cd="00060"):
    """Full available period of record for a site/parameter, from the NWIS
    site service's series catalog (a lightweight metadata call, not a full
    daily-values pull)."""
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
        return begin.date(), end.date()
    except Exception:
        return None, None


def build_summary_table(raw_df, total_start, total_end):
    """The monthly table with two extra rows on top: the full period of
    record available for the site, and the period actually used here."""
    monthly = build_monthly_table(raw_df)
    used_start, used_end = raw_df["date"].min().date(), raw_df["date"].max().date()
    total_txt = (f"{total_start} to {total_end}" if total_start else "Unknown")
    info = pd.DataFrame(
        {"Average (cfs)": [total_txt, f"{used_start} to {used_end}"],
         "Maximum (cfs)": ["—", "—"],
         "Minimum (cfs)": ["—", "—"]},
        index=["Total period available", "Period used"],
    )
    info.index.name = "Month"
    return pd.concat([info, monthly])


def build_monthly_avg_series(raw_df, target_wy):
    """Monthly-average flow, one point per month, placed on the same
    plot-date axis as everything else (mid-month, day 15)."""
    d = raw_df.copy()
    d["month"] = d["date"].dt.month
    monthly = d.groupby("month")["flow_cfs"].mean().reindex(range(1, 13))
    rows = []
    for m in range(1, 13):
        mid_date = dt.date(2001, m, 15)
        rows.append({"plot_date": to_plot_date(mid_date, target_wy), "avg": monthly.loc[m]})
    out = pd.DataFrame(rows).dropna()
    out["plot_date"] = pd.to_datetime(out["plot_date"])
    return out.sort_values("plot_date")


# ── Plot ──────────────────────────────────────────────────────────────────────
def make_plot(datasets, wy_start, wy_end, use_log, custom_title=""):
    """Build the historical daily-flow min-max band + mean chart for one or
    two stations.

    ``datasets`` is a list of dicts, each with keys:
        stats (from process_site), station_id, label, color, line_style,
        monthly_avg (optional DataFrame from build_monthly_avg_series, or
        None if the monthly-average overlay wasn't requested for this station)
    Returns the matplotlib Figure (does not call plt.show()).
    """
    fig, ax = plt.subplots(figsize=(13, 6))

    line_handles, line_labels = [], []
    patch_handles, patch_labels = [], []

    for d in datasets:
        stats = d["stats"]
        fill = ax.fill_between(stats["plot_date"], stats["min"], stats["max"],
                                color=d["color"], alpha=0.4)
        patch_handles.append(fill)
        patch_labels.append(f"{d['label']} - max and min")

        (line,) = ax.plot(stats["plot_date"], stats["mean"], color=d["color"],
                           linestyle=d.get("line_style", "-"), linewidth=2)
        line_handles.append(line)
        line_labels.append(f"{d['label']} - daily averages")

        monthly_avg = d.get("monthly_avg")
        if monthly_avg is not None:
            (avg_line,) = ax.plot(monthly_avg["plot_date"], monthly_avg["avg"],
                                   color=d.get("monthly_avg_color", "#000000"),
                                   linestyle=d.get("monthly_avg_style", "-"),
                                   linewidth=1.6, marker="o", markersize=3)
            line_handles.append(avg_line)
            line_labels.append(f"{d['label']} - monthly average")

    title_str = (custom_title.strip() if custom_title.strip() else
                 "Hydrologic Year Daily Flow — " +
                 " vs ".join(d["label"] for d in datasets) +
                 f" (WY {wy_start}-{wy_end})")
    ax.set_title(title_str, fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Mean Daily Flow (cfs)")
    if use_log:
        ax.set_yscale("log")

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    all_dates = pd.concat([d["stats"]["plot_date"] for d in datasets])
    ax.set_xlim(all_dates.min(), all_dates.max())

    ax.grid(True, alpha=0.3)
    ax.legend(line_handles + patch_handles, line_labels + patch_labels,
              loc="upper right", fontsize=8, ncol=1)
    fig.tight_layout()

    fig.text(0.99, 0.01, f"© {dt.date.today().year} WRA, Inc.",
             ha="right", va="bottom", fontsize=7,
             fontfamily="sans-serif", color="#888888")

    return fig
