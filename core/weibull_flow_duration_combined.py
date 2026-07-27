"""Core data-fetching, Weibull plotting-position math, and plotting logic for
the Streamflow Analysis tool -- COMBINED TWO-STATION Flow-Duration /
Exceedance Probability, with a water-year range plus a recurring
month/day window applied within every one of those water years.

    P_exceed (%) = 100 * m / (n + 1)
    Return Period (years) = 100 / P_exceed (%)

where m is the rank of a flow value (m = 1 for the highest flow) and n is
the number of retained daily values.

A month/day window that starts in Oct-Dec and ends in Jan-Sep (e.g. Nov 1
to Feb 28) is treated as spanning the turn of the calendar year WITHIN a
single water year -- e.g. for WY2020 that means Nov 1, 2019 to Feb 28, 2020.

NOTE on "return period": this is computed directly from the day-based
Weibull exceedance percentage of the selected years/season. It describes
how rare a given DAILY flow is within that selection -- it is NOT the same
as a flood-frequency return period derived from annual peak flows (e.g. via
LP3/EMA on annual maxima). Keep that distinction in mind for reports.

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

# Standard return periods (years) shown in the summary table -- classic
# flood/duration-reporting values, from very frequent to very rare.
TABLE_RETURN_PERIODS = [1.01, 1.05, 1.1, 1.25, 1.5, 2, 5, 10, 25, 50, 100, 200, 500]

# A smaller subset used for the gold markers plotted directly on the curve
# (keeps the chart readable).
PLOT_MARKER_RETURN_PERIODS = [2, 5, 10, 25, 50, 100]

MONTH_OPTIONS = [(calendar.month_abbr[m], m) for m in range(1, 13)]
DAY_OPTIONS = list(range(1, 32))


# ── Helpers ────────────────────────────────────────────────────────────────
def water_year_of(date):
    """Water year = calendar year of the following Jan-Sep, i.e. Oct-Dec
    counts toward the NEXT calendar year's water year."""
    return date.year + 1 if date.month >= 10 else date.year


def wy_month_index(month):
    """Position of a calendar month within the water-year timeline, where
    Oct=0, Nov=1, ..., Sep=11. Lets us check that a (start_month, end_month)
    pair is in valid chronological order WITHIN a single water year, since
    raw calendar-month numbers don't reflect that Oct-Dec comes before
    Jan-Sep in water-year terms."""
    return (int(month) - 10) % 12


def calendar_date_for_wy(wy, month, day):
    """Map a (month, day) with no year onto the actual calendar date within
    a given water year -- Oct/Nov/Dec fall in the PRIOR calendar year,
    Jan-Sep fall in the water year's own calendar year. Clamps to the last
    valid day of the month if the day doesn't exist (e.g. Feb 30, or Feb 29
    in a non-leap year)."""
    wy, month, day = int(wy), int(month), int(day)
    calendar_year = wy - 1 if month >= 10 else wy
    last_day = calendar.monthrange(calendar_year, month)[1]
    day = min(day, last_day)
    return dt.date(calendar_year, month, day)


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


def filter_by_years_and_season(df, start_wy, end_wy, start_month, start_day,
                                end_month, end_day):
    """Restrict a daily-flow dataframe to a water-year range, keeping only
    dates that fall inside the recurring (month, day) window in EACH of
    those water years (the window can cross the calendar-year turn, e.g.
    Nov 1 - Feb 28, and stays correct within a single water year)."""
    start_idx = wy_month_index(start_month)
    end_idx = wy_month_index(end_month)
    if start_idx > end_idx or (start_idx == end_idx and start_day > end_day):
        raise ValueError(
            "Start month/day must come before end month/day within a single "
            "water year (Oct 1 - Sep 30 order). For example, Jun 15 -> Sep 15 "
            "is valid; Nov 1 -> Feb 28 is valid (crosses the calendar-year "
            "turn); but Jan 1 -> Dec 31 is NOT valid since Dec falls earlier "
            "in the water year than Jan. Use Oct 1 -> Sep 30 for a full year."
        )

    mask = pd.Series(False, index=df.index)
    for wy in range(int(start_wy), int(end_wy) + 1):
        window_start = calendar_date_for_wy(wy, start_month, start_day)
        window_end = calendar_date_for_wy(wy, end_month, end_day)
        start_ts = pd.Timestamp(window_start)
        end_ts = pd.Timestamp(window_end)
        mask = mask | ((df["date"] >= start_ts) & (df["date"] <= end_ts))
    d = df[mask].copy()
    d["water_year"] = d["date"].apply(water_year_of)
    return d.dropna(subset=["flow_cfs"])


def compute_weibull_table(df):
    """Sort flows descending (rank 1 = highest flow), assign the Weibull
    plotting-position exceedance probability, and back out the equivalent
    return period (years) for every retained daily value."""
    d = df.dropna(subset=["flow_cfs"]).copy()
    d = d.sort_values("flow_cfs", ascending=False).reset_index(drop=True)
    n = len(d)
    if n == 0:
        raise ValueError(
            "No data available for the selected water years and month/day window."
        )
    d["rank"] = np.arange(1, n + 1)
    d["exceedance_prob_pct"] = 100.0 * d["rank"] / (n + 1.0)
    d["return_period_years"] = 100.0 / d["exceedance_prob_pct"]
    return d


def summary_table(weibull_df, return_periods=None):
    """Interpolate the flow value at standard return-period thresholds from
    the full Weibull point set."""
    if return_periods is None:
        return_periods = TABLE_RETURN_PERIODS
    probs = [100.0 / t for t in return_periods]
    x = weibull_df["exceedance_prob_pct"].values  # increases with rank
    y = weibull_df["flow_cfs"].values              # decreases with rank
    flows = np.interp(probs, x, y)
    out = pd.DataFrame({
        "Return Period (years)": return_periods,
        "Percent of Time Equaled or Exceeded (%)": np.round(probs, 2),
        "Flow (cfs)": np.round(flows, 1),
    })
    return out


def build_display_table(weibull_df, start_wy, end_wy,
                         start_month, start_day, end_month, end_day):
    """Prepend an info block (water years / month-day window / day count
    actually analyzed) on top of the standard return-period summary table."""
    season_text = (
        f"{calendar.month_abbr[start_month]} {start_day} to "
        f"{calendar.month_abbr[end_month]} {end_day}"
    )
    info = pd.DataFrame({
        "Return Period (years)": ["—", "—", "—"],
        "Percent of Time Equaled or Exceeded (%)": ["—", "—", "—"],
        "Flow (cfs)": [
            f"Water years included: WY{start_wy}-WY{end_wy}",
            f"Month/day window (each year): {season_text}",
            f"Days analyzed: {len(weibull_df):,}",
        ],
    })
    summary = summary_table(weibull_df)
    return pd.concat([info, summary], ignore_index=True)


def flow_at_percent(weibull_df, pct):
    """Interpolate the combined flow value at a single arbitrary exceedance
    percentage (0-100)."""
    x = weibull_df["exceedance_prob_pct"].values
    y = weibull_df["flow_cfs"].values
    return float(np.interp(pct, x, y))


# ── Plot ──────────────────────────────────────────────────────────────────────
def make_plot(weibull_df, combined_label, start_wy, end_wy,
              start_month, start_day, end_month, end_day,
              use_log, curve_color, curve_style, show_points, show_markers,
              show_threshold, threshold_pct, threshold_color, threshold_style,
              custom_title=""):
    fig, ax = plt.subplots(figsize=(11, 6.5))

    if show_points:
        ax.scatter(weibull_df["exceedance_prob_pct"], weibull_df["flow_cfs"],
                   s=6, color="#AAAAAA", alpha=0.5, zorder=1,
                   label="Individual daily values")

    ax.plot(weibull_df["exceedance_prob_pct"], weibull_df["flow_cfs"],
            color=curve_color, linewidth=1.8, linestyle=curve_style,
            zorder=2, label="Combined flow-duration curve (Weibull)")

    if show_markers:
        summary = summary_table(weibull_df, return_periods=PLOT_MARKER_RETURN_PERIODS)
        ax.scatter(summary["Percent of Time Equaled or Exceeded (%)"],
                   summary["Flow (cfs)"], color=CALIFORNIA_SUNSET, edgecolor=BRAND_DARK,
                   s=40, zorder=3, label="Standard return periods (2-100 yr)")

    if use_log:
        ax.set_yscale("log")

    ax.set_xlim(0, 100)
    ax.set_xlabel("Percent of Time Combined Flow Was Equaled or Exceeded (%)")
    ax.set_ylabel("Combined Flow (cfs)")

    # -- User-chosen percentage threshold: dashed drop-lines + callout box --
    if show_threshold:
        flow_at_pct = flow_at_percent(weibull_df, threshold_pct)
        ylim = ax.get_ylim()

        ax.plot([threshold_pct, threshold_pct], [ylim[0], flow_at_pct],
                color=threshold_color, linestyle=threshold_style,
                linewidth=1.6, zorder=4)
        ax.plot([0, threshold_pct], [flow_at_pct, flow_at_pct],
                color=threshold_color, linestyle=threshold_style,
                linewidth=1.2, alpha=0.75, zorder=4)
        ax.set_ylim(ylim)

        label_text = f"Q{threshold_pct:g}% = {flow_at_pct:,.1f} cfs"
        if threshold_pct > 82:
            xytext = (threshold_pct - 3, flow_at_pct)
            ha = "right"
        else:
            xytext = (threshold_pct + 3, flow_at_pct)
            ha = "left"
        ax.annotate(
            label_text, xy=(threshold_pct, flow_at_pct), xytext=xytext,
            va="center", ha=ha, fontsize=9, fontweight="bold", color=BRAND_DARK,
            bbox=dict(boxstyle="round,pad=0.35", fc="white",
                      ec=threshold_color, lw=1.3), zorder=5,
        )

    season_text = (
        f"{calendar.month_abbr[start_month]} {start_day} to "
        f"{calendar.month_abbr[end_month]} {end_day}"
    )
    default_title = (
        f"Combined Flow-Duration Curve (Weibull Plotting Position)\n"
        f"{combined_label} — WY{start_wy}-WY{end_wy} — {season_text} each year"
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
