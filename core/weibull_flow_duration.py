"""Core data-fetching, Weibull plotting-position math, and plotting logic for
the Streamflow Analysis tool -- Flow-Duration / Exceedance Probability
(single station, with an optional independent second-station overlay curve).

    P_exceed (%) = 100 * m / (n + 1)

where m is the rank of a flow value (m = 1 for the highest flow) and n is
the number of retained daily values. A second station, if supplied, is NOT
combined/summed with the first -- each gets its own independent Weibull
analysis, computed and plotted separately for side-by-side comparison.

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
from matplotlib import rcParams

from core.branding import BRAND_FONT_STACK, BRAND_DARK, CALIFORNIA_SUNSET

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = BRAND_FONT_STACK
rcParams["axes.titlesize"] = 13
rcParams["axes.labelsize"] = 11
rcParams["xtick.labelsize"] = 8
rcParams["ytick.labelsize"] = 8

LINESTYLE_OPTIONS = [("Solid", "-"), ("Dashed", "--"), ("Dash-dot", "-."), ("Dotted", ":")]

# Standard percent-exceedance thresholds used for the interpolated summary table.
STANDARD_PROBS = [0.1, 1, 2, 5, 10, 20, 25, 30, 40, 50,
                  60, 70, 75, 80, 90, 95, 98, 99, 99.9]


# ── Helpers ────────────────────────────────────────────────────────────────
def water_year_of(date):
    """Water year = calendar year of the following Jan-Sep, i.e. Oct-Dec
    counts toward the NEXT calendar year's water year."""
    return date.year + 1 if date.month >= 10 else date.year


def fetch_full_daily_flow(site_no, start_date="1890-01-01", end_date=None):
    """Pull the FULL available daily-mean-flow (parameter 00060, stat 00003)
    history for one USGS station."""
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
    return df.rename(columns={"dateTime": "date"})[["date", "flow_cfs"]].sort_values("date")


def fetch_station_name(site_no):
    """Best-effort station name lookup; falls back to a generic label."""
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


def filter_by_years_months(df, start_wy, end_wy, months):
    """Restrict a daily-flow dataframe to a water-year range and a set of
    calendar months (1-12)."""
    d = df.copy()
    d["water_year"] = d["date"].apply(water_year_of)
    d = d[(d["water_year"] >= start_wy) & (d["water_year"] <= end_wy)]
    d = d[d["date"].dt.month.isin(months)]
    return d.dropna(subset=["flow_cfs"])


def compute_weibull_table(df):
    """Sort flows descending (rank 1 = highest flow) and assign the Weibull
    plotting-position exceedance probability to every retained daily value."""
    d = df.dropna(subset=["flow_cfs"]).copy()
    d = d.sort_values("flow_cfs", ascending=False).reset_index(drop=True)
    n = len(d)
    if n == 0:
        raise ValueError("No data available after filtering by water year(s) and month(s).")
    d["rank"] = np.arange(1, n + 1)
    d["exceedance_prob_pct"] = 100.0 * d["rank"] / (n + 1.0)
    return d


def summary_table(weibull_df, probs=None):
    """Interpolate the flow value at standard exceedance-probability
    thresholds from the full Weibull point set."""
    if probs is None:
        probs = STANDARD_PROBS
    x = weibull_df["exceedance_prob_pct"].values  # increases with rank
    y = weibull_df["flow_cfs"].values              # decreases with rank
    flows = np.interp(probs, x, y)
    out = pd.DataFrame({
        "Percent of Time Equaled or Exceeded (%)": probs,
        "Flow (cfs)": np.round(flows, 1),
    })
    return out


def full_point_table(weibull1, site1, weibull2=None, site2=None):
    """Combine the full daily point sets for CSV export, tagged by station."""
    out_cols = ["date", "flow_cfs", "rank", "exceedance_prob_pct"]
    t1 = weibull1[out_cols].copy()
    t1.insert(0, "station", site1)
    if weibull2 is not None:
        t2 = weibull2[out_cols].copy()
        t2.insert(0, "station", site2)
        return pd.concat([t1, t2], ignore_index=True)
    return t1


# ── Plot ──────────────────────────────────────────────────────────────────────
def make_plot(weibull1, label1, curve1_color, curve1_style,
              weibull2, label2, curve2_color, curve2_style,
              start_wy, end_wy, months, use_log, show_points, show_markers,
              custom_title=""):
    fig, ax = plt.subplots(figsize=(11, 6.5))

    points_labeled = False

    if show_points:
        ax.scatter(weibull1["exceedance_prob_pct"], weibull1["flow_cfs"],
                   s=6, color="#AAAAAA", alpha=0.5, zorder=1,
                   label="Individual daily values")
        points_labeled = True
        if weibull2 is not None:
            ax.scatter(weibull2["exceedance_prob_pct"], weibull2["flow_cfs"],
                       s=6, color="#AAAAAA", alpha=0.5, zorder=1,
                       label=None if points_labeled else "Individual daily values")

    ax.plot(weibull1["exceedance_prob_pct"], weibull1["flow_cfs"],
            color=curve1_color, linewidth=1.8, linestyle=curve1_style,
            zorder=2, label=label1)

    if weibull2 is not None:
        ax.plot(weibull2["exceedance_prob_pct"], weibull2["flow_cfs"],
                color=curve2_color, linewidth=1.8, linestyle=curve2_style,
                zorder=2, label=label2)

    if show_markers:
        summary1 = summary_table(weibull1, probs=[5, 10, 25, 50, 75, 90, 95])
        ax.scatter(summary1["Percent of Time Equaled or Exceeded (%)"],
                   summary1["Flow (cfs)"], color=CALIFORNIA_SUNSET, edgecolor=curve1_color,
                   s=40, zorder=3, label="Standard exceedance percentiles")
        if weibull2 is not None:
            summary2 = summary_table(weibull2, probs=[5, 10, 25, 50, 75, 90, 95])
            ax.scatter(summary2["Percent of Time Equaled or Exceeded (%)"],
                       summary2["Flow (cfs)"], color="white", edgecolor=curve2_color,
                       s=40, zorder=3, label=None)

    if use_log:
        ax.set_yscale("log")

    ax.set_xlim(0, 100)
    ax.set_xlabel("Percent of Time Flow Was Equaled or Exceeded (%)")
    ax.set_ylabel("Flow (cfs)")

    month_abbrs = ", ".join(calendar.month_abbr[m] for m in months)
    if weibull2 is not None:
        default_title = (
            f"Flow-Duration Curve Comparison (Weibull Plotting Position)\n"
            f"WY{start_wy}-WY{end_wy} — Months: {month_abbrs}"
        )
    else:
        default_title = (
            f"Flow-Duration Curve (Weibull Plotting Position)\n"
            f"{label1} — WY{start_wy}-WY{end_wy} — Months: {month_abbrs}"
        )
    ax.set_title(custom_title.strip() if custom_title.strip() else default_title,
                 fontsize=11, fontweight="bold")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)

    fig.text(0.99, 0.01, f"© {dt.date.today().year} WRA, Inc.",
              ha="right", va="bottom", fontsize=7,
              fontfamily="sans-serif", color="#888888")

    fig.tight_layout()
    return fig
