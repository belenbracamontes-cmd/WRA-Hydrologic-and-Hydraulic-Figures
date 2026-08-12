"""Core data-fetching and plotting logic for the Annual Peak Flow & Average
Flow Chart Generator tool.

Ported from a tkinter/ipywidgets notebook GUI (WRA -- Riverscapes & Shorelines
Team). Streamlit-agnostic on purpose, same pattern as core/peak_flow.py.
"""

import datetime as _dt
from io import StringIO

import numpy as np
import pandas as pd
import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib import rcParams

from core.branding import (
    BRAND_FONT_STACK,
    TERRACOTA_SHADE,
    CALIFORNIA_SUNSET,
    OCEAN_BLUE_SHADE,
    OCEAN_BLUE_TINT,
    WARMER_CREAM,
    NEUTRAL_BACKGROUND,
)

# Values below are real WRA brand colors (Brand Guide section 04), not
# invented placeholders. Peak/avg use the Ocean Blue family (shade for the
# dark "peak" series, tint for the light "average" series); the annotation
# boxes use California Sunset on Warmer Cream.
WRA_NAVY      = TERRACOTA_SHADE
WRA_PEAK_BLUE = OCEAN_BLUE_SHADE  # annual peak flow bars  (dark navy-teal)
WRA_AVG_CYAN  = OCEAN_BLUE_TINT   # annual average flow bars (light cyan)
WRA_GOLD      = CALIFORNIA_SUNSET # annotation box border
WRA_GOLD_FILL = WARMER_CREAM      # annotation box fill
WRA_WHITE     = NEUTRAL_BACKGROUND
WRA_GRID      = "#D0D0D0"

rcParams["font.family"]     = "sans-serif"
rcParams["font.sans-serif"] = BRAND_FONT_STACK
rcParams["axes.titlesize"]  = 13
rcParams["axes.labelsize"]  = 11
rcParams["xtick.labelsize"] = 9
rcParams["ytick.labelsize"] = 9


# ══════════════════════════════════════════════════════════════════════════
#  USGS NWIS DATA FETCH
# ══════════════════════════════════════════════════════════════════════════

def water_year(date):
    """Return USGS water year for a datetime (Oct 1 -> Sep 30)."""
    return date.year + 1 if date.month >= 10 else date.year


def fetch_peak_flows(site_no, start_wy, end_wy):
    """
    Pull annual instantaneous peak flows from USGS NWIS.
    Returns DataFrame with columns [water_year, peak_flow_cfs].
    One row per water year -- maximum peak if multiple peaks recorded.
    """
    urls = [
        (f"https://nwis.waterdata.usgs.gov/usa/nwis/peak"
         f"?site_no={site_no}&agency_cd=USGS&format=rdb"),
        (f"https://waterdata.usgs.gov/nwis/peak"
         f"?site_no={site_no}&agency_cd=USGS&format=rdb"),
    ]

    resp, last_err = None, None
    for url in urls:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            if "peak_dt" in r.text or "peak_va" in r.text:
                resp = r
                break
        except Exception as e:
            last_err = e

    if resp is None:
        raise RuntimeError(
            f"Could not retrieve peak flows for station {site_no}. "
            f"Last error: {last_err}"
        )

    lines = [l for l in resp.text.splitlines()
             if not l.startswith("#") and l.strip()]
    if len(lines) < 3:
        return pd.DataFrame(columns=["water_year", "peak_flow_cfs"])

    header = lines[0]
    n_cols = len(header.split("\t"))
    data_lines = [l for l in lines[2:]
                  if not l.startswith("5s")
                  and len(l.split("\t")) == n_cols]
    if not data_lines:
        return pd.DataFrame(columns=["water_year", "peak_flow_cfs"])

    df = pd.read_csv(
        StringIO("\n".join([header] + data_lines)),
        sep="\t", low_memory=False,
    )

    if "peak_va" not in df.columns or "peak_dt" not in df.columns:
        raise ValueError(
            f"Expected columns 'peak_dt'/'peak_va' for station {site_no}. "
            f"Got: {list(df.columns)}"
        )

    df = df[["peak_dt", "peak_va"]].copy()
    df.columns = ["date", "peak_flow_cfs"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["peak_flow_cfs"] = pd.to_numeric(df["peak_flow_cfs"], errors="coerce")
    df = df.dropna(subset=["date", "peak_flow_cfs"])
    df["water_year"] = df["date"].apply(water_year)

    df = (df.groupby("water_year", as_index=False)["peak_flow_cfs"]
            .max()
            .dropna(subset=["peak_flow_cfs"]))
    return df[(df["water_year"] >= start_wy) & (df["water_year"] <= end_wy)]


def fetch_annual_avg_flow(site_no, start_wy, end_wy):
    """
    Pull annual mean discharge from USGS NWIS statistics service.
    Returns DataFrame with columns [water_year, avg_flow_cfs].
    Returns empty DataFrame (silently) if the service has no annual stats.
    """
    url = (
        f"https://waterservices.usgs.gov/nwis/stat/"
        f"?sites={site_no}&statReportType=annual&statYearType=water"
        f"&parameterCd=00060&format=rdb"
    )
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except Exception:
        return pd.DataFrame(columns=["water_year", "avg_flow_cfs"])

    lines = [l for l in r.text.splitlines()
             if not l.startswith("#") and l.strip()]
    if len(lines) < 3:
        return pd.DataFrame(columns=["water_year", "avg_flow_cfs"])

    header = lines[0].split("\t")
    data_lines = [l for l in lines[2:]
                  if l.strip()
                  and not l.startswith("5s")
                  and not l.startswith("site_no")]
    if not data_lines:
        return pd.DataFrame(columns=["water_year", "avg_flow_cfs"])

    rows = [l.split("\t") for l in data_lines]
    df = pd.DataFrame(rows, columns=header[:len(rows[0])])

    wy_col = next((c for c in df.columns if "year" in c.lower()), None)
    mean_col = next((c for c in df.columns if "mean" in c.lower()), None)
    if wy_col is None or mean_col is None:
        return pd.DataFrame(columns=["water_year", "avg_flow_cfs"])

    df = df[[wy_col, mean_col]].copy()
    df.columns = ["water_year", "avg_flow_cfs"]
    df["water_year"] = pd.to_numeric(df["water_year"], errors="coerce")
    df["avg_flow_cfs"] = pd.to_numeric(df["avg_flow_cfs"], errors="coerce")
    df = df.dropna().copy()
    df["water_year"] = df["water_year"].astype(int)
    return df[(df["water_year"] >= start_wy) & (df["water_year"] <= end_wy)]


def fetch_station_name(site_no):
    """Return human-readable station name from USGS site service, or fallback string."""
    url = (
        f"https://waterservices.usgs.gov/nwis/site/"
        f"?sites={site_no}&format=rdb&siteOutput=expanded"
    )
    try:
        r = requests.get(url, timeout=15)
        for line in r.text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) > 2 and parts[0] == site_no:
                return parts[2].strip().title()
    except Exception:
        pass
    return f"USGS Station {site_no}"


# ══════════════════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════

def summary_table(datasets):
    """Return a DataFrame summarizing mean/max peak flow and mean average flow
    per station -- same numbers as the on-chart stats box."""
    rows = []
    for d in datasets:
        lbl = d["label"] or d["station_name"] or f"Station {d['station_id']}"
        pk, av = d["peak_df"], d["avg_df"]
        if pk.empty:
            continue
        max_idx = pk["peak_flow_cfs"].idxmax()
        rows.append({
            "Station": f"{lbl} (USGS {d['station_id']})",
            "Record Span": f"WY{pk['water_year'].min()}–WY{pk['water_year'].max()}",
            "N Years (peak)": len(pk),
            "Mean Peak Flow (cfs)": round(pk["peak_flow_cfs"].mean(), 0),
            "Max Peak Flow (cfs)": round(pk.loc[max_idx, "peak_flow_cfs"], 0),
            "Max Peak Water Year": int(pk.loc[max_idx, "water_year"]),
            "Mean Avg Flow (cfs)": round(av["avg_flow_cfs"].mean(), 1) if not av.empty else "N/A",
        })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════
#  CHART BUILD
# ══════════════════════════════════════════════════════════════════════════

def build_annual_flow_chart(datasets, custom_title="", show_avg=True, organization="WRA, Inc."):
    """
    Build a Balance Hydrologics-style dual-axis grouped bar chart.
    Supports 1 or 2 stations. Returns the matplotlib Figure (does not call
    plt.show()).

    datasets -- list of dicts, one per station:
        peak_df, avg_df, station_id, station_name, peak_color, avg_color, label
    """
    n_stations = len(datasets)

    all_years = sorted(
        set().union(*[set(d["peak_df"]["water_year"]) for d in datasets])
    )
    n_years = len(all_years)
    x = np.arange(n_years)

    total_bars = n_stations
    group_width = 0.72
    slot_w = group_width / total_bars
    peak_w = slot_w * 0.45
    avg_w = slot_w * 1.05

    fig, ax1 = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor(WRA_WHITE)
    ax1.set_facecolor(WRA_WHITE)
    ax2 = ax1.twinx()

    ax1.set_zorder(ax2.get_zorder() + 1)
    ax1.patch.set_visible(False)

    all_peak_vals, all_avg_vals = [], []

    for i_s, d in enumerate(datasets):
        peak_map = dict(zip(d["peak_df"]["water_year"], d["peak_df"]["peak_flow_cfs"]))
        avg_map = (dict(zip(d["avg_df"]["water_year"], d["avg_df"]["avg_flow_cfs"]))
                   if show_avg and not d["avg_df"].empty else {})

        peak_vals = [peak_map.get(y, 0) for y in all_years]
        avg_vals = [avg_map.get(y, 0) for y in all_years]

        all_peak_vals.extend(v for v in peak_vals if v > 0)
        all_avg_vals.extend(v for v in avg_vals if v > 0)

        lbl = d["label"] or d["station_name"] or f"Station {d['station_id']}"
        offset = (i_s - (total_bars - 1) / 2.0) * slot_w

        if show_avg and avg_vals and any(v > 0 for v in avg_vals):
            ax2.bar(
                x + offset, avg_vals, width=avg_w,
                color=d["avg_color"], alpha=0.7, zorder=2,
                label=(f"{lbl} — Annual Average Flow (cfs)"
                       if n_stations > 1 else "Annual Average Flow (cfs)"),
            )

        ax1.bar(
            x + offset, peak_vals, width=peak_w,
            color=d["peak_color"], zorder=4,
            label=(f"{lbl} — Annual Peak Flow (cfs)"
                   if n_stations > 1 else "Annual Peak Flow (cfs)"),
        )

    ax1.set_xticks(x)
    ax1.set_xticklabels([str(y) for y in all_years],
                        rotation=90, fontsize=8, fontfamily="sans-serif")
    ax1.set_xlim(-0.6, n_years - 0.4)
    ax1.set_ylim(0, max(all_peak_vals, default=1) * 1.1)
    ax2.set_ylim(0, max(all_avg_vals, default=1) * 1.5 if all_avg_vals else 10)

    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax1.tick_params(axis="y", labelsize=8)
    ax2.tick_params(axis="y", labelsize=8)

    ax1.set_ylabel("Annual Peak Flow (cfs)", fontsize=10, fontfamily="sans-serif", labelpad=6)
    ax2.set_ylabel("Annual Average Flow (cfs)", fontsize=10, fontfamily="sans-serif", labelpad=6)
    ax1.set_xlabel("Water Year", fontsize=10, fontfamily="sans-serif", labelpad=6)

    ax1.grid(axis="y", color=WRA_GRID, linewidth=0.5, zorder=0)
    ax1.grid(axis="x", visible=False)

    # ── Stats box (top-left) -- Mean AND Max Peak Flow, plus Mean Average Flow ──
    stats_lines = []
    for d in datasets:
        lbl = d["label"] or d["station_name"] or f"Station {d['station_id']}"
        peak_map = dict(zip(d["peak_df"]["water_year"], d["peak_df"]["peak_flow_cfs"]))
        avg_map = (dict(zip(d["avg_df"]["water_year"], d["avg_df"]["avg_flow_cfs"]))
                   if show_avg and not d["avg_df"].empty else {})
        vp = [v for v in peak_map.values() if v > 0]
        va = [v for v in avg_map.values() if v > 0]
        wy_s = min(peak_map) if peak_map else "?"
        wy_e = max(peak_map) if peak_map else "?"
        hdr = f"{lbl}\n" if n_stations > 1 else ""

        if vp:
            max_val = max(vp)
            max_wy = next(y for y, v in peak_map.items() if v == max_val)
            block = (
                f"{hdr}Mean Peak Flow (WY{wy_s}–WY{wy_e}) = {np.mean(vp):,.0f} cfs\n"
                f"Max Peak Flow (WY{max_wy}) = {max_val:,.0f} cfs"
            )
        else:
            block = f"{hdr}No peak flow data"

        if va:
            block += f"\nMean Annual Average Flow (WY{wy_s}–WY{wy_e}) = {np.mean(va):,.0f} cfs"
        stats_lines.append(block)

    ax1.text(
        0.01, 0.97, "\n\n".join(stats_lines),
        transform=ax1.transAxes, fontsize=8, va="top", ha="left",
        bbox=dict(boxstyle="round,pad=0.5", facecolor=WRA_GOLD_FILL,
                  edgecolor=WRA_GOLD, linewidth=1.2),
        fontfamily="sans-serif", linespacing=1.5,
    )

    ax1.text(
        0.99, 0.97, "Data collected and provided by the USGS.",
        transform=ax1.transAxes, fontsize=8, va="top", ha="right",
        bbox=dict(boxstyle="round,pad=0.4", facecolor=WRA_GOLD_FILL,
                  edgecolor=WRA_GOLD, linewidth=1.2),
        fontfamily="sans-serif",
    )

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    seen, uh, ul = set(), [], []
    for h, l in zip(h1 + h2, l1 + l2):
        if l not in seen:
            seen.add(l)
            uh.append(h)
            ul.append(l)
    leg = ax1.legend(uh, ul, fontsize=8.5, framealpha=1,
                     edgecolor="#AAAAAA",
                     bbox_to_anchor=(0.99, 0.87), loc="upper right")
    for t in leg.get_texts():
        t.set_fontfamily("Verdana")

    if custom_title.strip():
        title_str = custom_title.strip()
    else:
        ids_str = " | ".join(f"USGS {d['station_id']}" for d in datasets)
        names_str = " | ".join(
            d["label"] or d["station_name"] or f"Station {d['station_id']}"
            for d in datasets
        )
        title_str = (
            f"Annual Peak Flow and Average Flow Summary Data\n"
            f"{ids_str} — {names_str}"
        )
    fig.suptitle(title_str, fontsize=12, fontweight="bold", fontfamily="sans-serif", y=0.99)

    last_year = all_years[-1] if all_years else "?"
    captions = []
    for d in datasets:
        pk_map = dict(zip(d["peak_df"]["water_year"], d["peak_df"]["peak_flow_cfs"]))
        av_map = (dict(zip(d["avg_df"]["water_year"], d["avg_df"]["avg_flow_cfs"]))
                  if show_avg and not d["avg_df"].empty else {})
        lp = pk_map.get(last_year, 0)
        la = av_map.get(last_year, 0)
        lbl = d["label"] or d["station_name"] or f"Station {d['station_id']}"
        captions.append(
            f"{lbl}: WY{last_year} peak = {lp:,.0f} cfs"
            + (f", avg = {la:,.0f} cfs" if la else "")
        )
    fig.text(0.5, 0.005, "   |   ".join(captions),
             ha="center", va="bottom", fontsize=7.5,
             fontfamily="sans-serif", color="#444444", style="italic")
    fig.text(0.99, 0.005, f"© {_dt.date.today().year} {organization}",
             ha="right", va="bottom", fontsize=7,
             fontfamily="sans-serif", color="#888888")

    fig.subplots_adjust(left=0.07, right=0.93, top=0.91, bottom=0.15)
    return fig
