"""Core data-fetching, return-period math, and plotting logic for the
Annual Peak Flow Viewer tool.

This module is Streamlit-agnostic on purpose: it can be imported, tested, or
reused from a plain script. The Streamlit page (pages/1_Peak_Flow_Viewer.py)
is a thin UI layer on top of it.
"""

import colorsys
from io import StringIO

import numpy as np
import pandas as pd
import requests

import matplotlib
matplotlib.use("Agg")  # headless backend -- required for a server process
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.transforms as mtransforms
from matplotlib import rcParams
from matplotlib.colors import hex2color, to_hex

from core.branding import BRAND_FONT_STACK

# Archia (primary) -> Tenorite (secondary) -> Verdana (tertiary) -> generic,
# per WRA_Brand_Guide_Revised_2026.pdf section 05. Individual fontfamily=
# calls below use "sans-serif" so they all resolve through this same chain.
rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = BRAND_FONT_STACK
rcParams["axes.titlesize"] = 13
rcParams["axes.labelsize"] = 11
rcParams["xtick.labelsize"] = 8
rcParams["ytick.labelsize"] = 8

# ── Return period config ──────────────────────────────────────────────────────
ALL_RP_TARGETS = [1.5, 2, 5, 10, 25, 50, 100]
ALL_RP_LABELS = ["1.5-yr", "2-yr", "5-yr", "10-yr", "25-yr", "50-yr", "100-yr"]
RP_MIN_N = {"100-yr": 100, "50-yr": 50, "25-yr": 25,
            "10-yr": 10, "5-yr": 5, "2-yr": 2, "1.5-yr": 1}


def active_rps(n):
    active_t, active_l = [], []
    for t, l in zip(ALL_RP_TARGETS, ALL_RP_LABELS):
        if n >= RP_MIN_N[l]:
            active_t.append(t)
            active_l.append(l)
    return active_t, active_l


# ── Color interpolation from a base hex color ─────────────────────────────────
def build_palette(base_hex, n_steps=8):
    r, g, b = hex2color(base_hex)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    palette = []
    for i in range(n_steps):
        t = i / (n_steps - 1)
        s_i = s * (1.0 - t * 0.75)
        v_i = v + (1.0 - v) * t * 0.9
        r_i, g_i, b_i = colorsys.hsv_to_rgb(h, s_i, min(v_i, 1.0))
        palette.append(to_hex((r_i, g_i, b_i)))
    return palette


def interp_from_palette(palette, t):
    t = np.clip(t, 0.0, 1.0)
    idx = t * (len(palette) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(palette) - 1)
    frac = idx - lo
    c_lo = np.array(hex2color(palette[lo]))
    c_hi = np.array(hex2color(palette[hi]))
    rgb = c_lo * (1 - frac) + c_hi * frac
    return to_hex(rgb)


def bar_color_for(val, sorted_flows, palette):
    if pd.isna(val):
        return "#cccccc"
    if val >= sorted_flows[-1]:
        return interp_from_palette(palette, 0.0)
    if val < sorted_flows[0]:
        return interp_from_palette(palette, 1.0)
    for i in range(len(sorted_flows) - 1):
        lo_flow, hi_flow = sorted_flows[i], sorted_flows[i + 1]
        if lo_flow <= val < hi_flow:
            t_hi = i / (len(sorted_flows) - 1)
            t_lo = (i + 1) / (len(sorted_flows) - 1)
            frac = (val - lo_flow) / (hi_flow - lo_flow)
            t = t_lo + frac * (t_hi - t_lo)
            return interp_from_palette(palette, 1.0 - t)
    return interp_from_palette(palette, 1.0)


# ── Data fetch / transform ────────────────────────────────────────────────────
def hydro_year(date):
    return date.year + 1 if date.month >= 10 else date.year


def fetch_data(station_id):
    urls_to_try = [
        f"https://nwis.waterdata.usgs.gov/usa/nwis/peak?site_no={station_id}&agency_cd=USGS&format=rdb",
        f"https://waterdata.usgs.gov/nwis/peak?site_no={station_id}&agency_cd=USGS&format=rdb",
    ]
    resp = None
    for url in urls_to_try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        if "peak_dt" in r.text or "peak_va" in r.text:
            resp = r
            break
    if resp is None:
        raise ValueError(
            f"Could not retrieve RDB peak-flow data for station {station_id}. "
            f"Tried both national USGS endpoints."
        )

    data_lines = [l for l in resp.text.splitlines()
                  if l.strip() and not l.startswith("#")]

    if len(data_lines) < 3:
        raise ValueError(f"No data returned for station {station_id}. "
                         "Check the station ID and try again.")

    header_line = data_lines[0]
    n_cols = len(header_line.split("\t"))

    # data_lines[1] is the RDB format-spec row (e.g. "16s\t8n"); real records
    # start after it.
    record_lines = data_lines[2:]
    good_lines = [l for l in record_lines if len(l.split("\t")) == n_cols]

    if not good_lines:
        raise ValueError(
            f"Station {station_id}: header has {n_cols} columns but no data "
            f"rows matched. First few raw lines:\n" + "\n".join(data_lines[:6])
        )

    clean = "\n".join([header_line] + good_lines)
    df = pd.read_csv(StringIO(clean), sep="\t", low_memory=False)

    if "peak_va" not in df.columns or "peak_dt" not in df.columns:
        raise ValueError(
            f"Expected columns 'peak_dt' and 'peak_va' not found for station "
            f"{station_id}. Columns present: {list(df.columns)}"
        )

    keep_cols = ["peak_dt", "peak_va"]
    for optional in ["peak_tm", "peak_cd", "gage_ht", "gage_ht_cd"]:
        if optional in df.columns:
            keep_cols.append(optional)

    df = df[keep_cols].copy()
    df = df.dropna(subset=["peak_va"])
    df["peak_va"] = pd.to_numeric(df["peak_va"], errors="coerce")
    df["peak_dt"] = pd.to_datetime(df["peak_dt"], errors="coerce")
    df = df.dropna(subset=["peak_va", "peak_dt"])
    df["year"] = df["peak_dt"].apply(hydro_year)
    return df


def compute_return_periods(df):
    n = len(df)
    df = df.sort_values("peak_va", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    df["exceedance_prob_%"] = (df["rank"] / (n + 1)) * 100
    df["return_period_yr"] = (n + 1) / df["rank"]
    return df


def build_df_full(df):
    df_annual = df.groupby("year", as_index=False)["peak_va"].max()
    all_years = pd.RangeIndex(df_annual["year"].min(), df_annual["year"].max() + 1)
    return pd.DataFrame({"year": all_years}).merge(df_annual, on="year", how="left")


def return_period_table(df, n):
    """Return a small DataFrame of active return-period targets vs. flow (cfs)."""
    rp_targets, rp_labels = active_rps(n)
    rows = []
    for rp, lbl in zip(rp_targets, rp_labels):
        flow = np.interp(rp, df["return_period_yr"].iloc[::-1],
                         df["peak_va"].iloc[::-1])
        rows.append({
            "Event": lbl.replace("-yr", "-Year"),
            "Return Period (yr)": rp,
            "Flow (cfs)": round(float(flow)),
        })
    return pd.DataFrame(rows)


def full_record_table(df):
    """Return the full ranked peak-flow record, formatted for display/export."""
    base_cols = ["rank", "year", "peak_dt", "peak_va",
                 "exceedance_prob_%", "return_period_yr"]
    base_names = ["Rank", "Hydro Year", "Date", "Flow (cfs)",
                  "Exceedance Prob (%)", "Return Period (yr)"]
    if "gage_ht" in df.columns:
        base_cols.insert(4, "gage_ht")
        base_names.insert(4, "Gage Ht (ft)")

    display_df = df[base_cols].copy()
    display_df.columns = base_names
    display_df["Exceedance Prob (%)"] = display_df["Exceedance Prob (%)"].round(2)
    display_df["Return Period (yr)"] = display_df["Return Period (yr)"].round(2)
    return display_df


# ── Plot ──────────────────────────────────────────────────────────────────────
def make_plot(datasets, use_log, break_val, custom_title="", axis_ratio=0.6):
    """Build the two-panel peak-flow bar chart for one or two stations.

    ``datasets`` is a list of dicts, each with keys:
        df, df_full, station_id, base_color, label, n
    Returns the matplotlib Figure (does not call plt.show()).
    """
    BREAK = break_val
    all_min = min(d["df_full"]["year"].min() for d in datasets)
    all_max = max(d["df_full"]["year"].max() for d in datasets)
    all_years = np.arange(all_min, all_max + 1)
    x_all = np.arange(len(all_years))
    year_to_x = {y: i for i, y in enumerate(all_years)}

    n_stations = len(datasets)
    total_width = 0.75
    bar_w = total_width / n_stations
    offsets = [(i - (n_stations - 1) / 2) * bar_w for i in range(n_stations)]

    global_max = max(d["df_full"]["peak_va"].max() for d in datasets)
    y_top_max = global_max * 1.1

    fig = plt.figure(figsize=(18, 9))
    fig.patch.set_facecolor("white")
    top_r = axis_ratio
    bot_r = 1.0 - axis_ratio
    gs = fig.add_gridspec(2, 1, height_ratios=[top_r, bot_r], hspace=0)
    ax_top = fig.add_subplot(gs[0])
    ax_bot = fig.add_subplot(gs[1], sharex=ax_top)

    for d, offset in zip(datasets, offsets):
        df_full = d["df_full"]
        palette = build_palette(d["base_color"])
        n = d["n"]
        rp_targets, rp_labels = active_rps(n)
        rp_flows = {}
        for rp, lbl in zip(rp_targets, rp_labels):
            rp_flows[lbl] = np.interp(
                rp, d["df"]["return_period_yr"].iloc[::-1],
                d["df"]["peak_va"].iloc[::-1]
            )
        sorted_flows = [rp_flows[l] for l in rp_labels]

        for _, row in df_full.iterrows():
            if pd.isna(row["peak_va"]):
                continue
            xi = year_to_x[row["year"]]
            color = bar_color_for(row["peak_va"], sorted_flows, palette)
            for ax in (ax_top, ax_bot):
                ax.bar(xi + offset, row["peak_va"], width=bar_w * 0.92,
                       color=color, edgecolor="white", linewidth=0.2)

    # Draw asterisks for missing years pinned to the visual bottom of ax_bot.
    blended = mtransforms.blended_transform_factory(
        ax_bot.transData, ax_bot.transAxes
    )
    for d, offset in zip(datasets, offsets):
        for _, row in d["df_full"].iterrows():
            if pd.isna(row["peak_va"]):
                xi = year_to_x[row["year"]]
                ax_bot.text(xi + offset, 0.02, "*", ha="center", va="bottom",
                            fontsize=8, color=d["base_color"], fontweight="bold",
                            fontfamily="sans-serif", transform=blended)

    all_bot_items = []
    all_top_items = []
    for d in datasets:
        d_n = d["n"]
        d_rp_t, d_rp_l = active_rps(d_n)
        d_rp_flows = {}
        for rp, lbl in zip(d_rp_t, d_rp_l):
            d_rp_flows[lbl] = np.interp(
                rp, d["df"]["return_period_yr"].iloc[::-1],
                d["df"]["peak_va"].iloc[::-1]
            )
        base_color = d["base_color"]

        for lbl in d_rp_l:
            flow = d_rp_flows[lbl]
            ax = ax_top if flow >= BREAK else ax_bot
            ax.axhline(y=flow, color=base_color, linewidth=1.2, linestyle=":", alpha=0.85)

        bot_items = [(d_rp_flows[l], l, base_color) for l in d_rp_l if d_rp_flows[l] < BREAK]
        top_items = [(d_rp_flows[l], l, base_color) for l in d_rp_l if d_rp_flows[l] >= BREAK]
        all_bot_items.extend(bot_items)
        all_top_items.extend(top_items)

    def _nudge_positions(items, ylim, yscale, min_gap_frac=0.03):
        if not items:
            return []
        lo, hi = ylim
        if yscale == "log":
            import math
            lo_t = math.log10(max(lo, 1e-9))
            hi_t = math.log10(hi)
            span = hi_t - lo_t
            to_t = lambda v: math.log10(max(v, 1e-9))
            from_t = lambda t: 10 ** t
        else:
            span = hi - lo
            to_t = lambda v: v
            from_t = lambda t: t

        gap = min_gap_frac * span
        sorted_items = sorted(items, key=lambda x: x[0])
        positions = [to_t(flow) for flow, _, _ in sorted_items]

        for i in range(1, len(positions)):
            if positions[i] - positions[i - 1] < gap:
                positions[i] = positions[i - 1] + gap

        hi_t_val = to_t(hi) - gap * 0.2
        for i in range(len(positions) - 1, -1, -1):
            if positions[i] > hi_t_val:
                positions[i] = hi_t_val
                hi_t_val -= gap
            else:
                break

        return [(from_t(pos), lbl, color)
                for pos, (_, lbl, color) in zip(positions, sorted_items)]

    def _draw_rp_annotations(ax, items, ylim, yscale):
        if not items:
            return
        nudged = _nudge_positions(items, ylim, yscale)
        ax.tick_params(axis="y", which="both", right=False)
        for (y_text, lbl, color) in nudged:
            ax.annotate(
                lbl,
                xy=(1.01, y_text), xycoords=("axes fraction", "data"),
                fontsize=8, fontweight="bold", fontfamily="sans-serif",
                color=color, va="center", ha="left",
                annotation_clip=False,
            )

    _draw_rp_annotations(ax_bot, all_bot_items,
                         (1 if use_log else 0, BREAK),
                         "log" if use_log else "linear")
    _draw_rp_annotations(ax_top, all_top_items,
                         (BREAK, y_top_max), "linear")

    if use_log:
        ax_bot.set_yscale("log")
        ax_bot.set_ylim(1, BREAK)
    else:
        ax_bot.set_ylim(0, BREAK)
    ax_top.set_ylim(BREAK, y_top_max)

    ax_top.spines["bottom"].set_visible(False)
    ax_bot.spines["top"].set_visible(False)
    ax_top.tick_params(axis="x", which="both", bottom=False, labelbottom=False)

    ax_bot.set_xticks(x_all)
    ax_bot.set_xticklabels([str(y) for y in all_years],
                           fontsize=7.5, rotation=90, ha="center",
                           fontfamily="sans-serif")
    ax_bot.set_xlabel("Hydrological Year", fontsize=11, fontfamily="sans-serif")
    ax_bot.set_xlim(-0.8, len(all_years) - 0.2)

    title_str = (custom_title.strip() if custom_title.strip()
                 else "Annual Peak Flow — " +
                      " vs ".join(d["label"] or f"Station {d['station_id']}"
                                  for d in datasets))
    ax_top.set_title(title_str, fontsize=13, fontweight="bold", fontfamily="sans-serif")
    fig.supylabel("Peak Discharge (cfs)", fontsize=11, fontfamily="sans-serif", x=0.0)

    ax_top.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{int(y):,}"))
    ax_bot.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{int(y):,}"))
    for ax in (ax_top, ax_bot):
        ax.grid(axis="y", linestyle=":", alpha=0.4, which="both")
        ax.set_axisbelow(True)
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            lbl.set_fontfamily("Verdana")

    for d_idx, d in enumerate(datasets):
        palette = build_palette(d["base_color"])
        n = d["n"]
        _, rp_lbls = active_rps(n)
        max_lbl = rp_lbls[-1]
        site_name = d["label"] or f"Station {d['station_id']}"

        handles = []
        handles.append(mpatches.Patch(color=interp_from_palette(palette, 0.0),
                                      label=f">{max_lbl}"))
        for i in range(len(rp_lbls) - 1, 0, -1):
            mid_t = 1.0 - ((i - 0.5) / (len(rp_lbls) - 1))
            handles.append(mpatches.Patch(color=interp_from_palette(palette, mid_t),
                                          label=f"{rp_lbls[i-1]} – {rp_lbls[i]}"))
        handles.append(mpatches.Patch(color=interp_from_palette(palette, 1.0),
                                      label=f"<{rp_lbls[0]}"))

        x_anchor = 0.01 + d_idx * 0.18
        leg = ax_top.legend(
            handles=handles,
            title=f"{site_name}\n(max: {max_lbl}, n={n})",
            fontsize=9.5, title_fontsize=9.5,
            loc="upper left",
            bbox_to_anchor=(x_anchor, 1.0),
            framealpha=0.9, handlelength=1.2,
        )
        for text in leg.get_texts():
            text.set_fontfamily("Verdana")
        leg.get_title().set_fontfamily("Verdana")
        ax_top.add_artist(leg)

    fig.text(0.99, 0.01, "© WRA, Inc.",
              ha="right", va="bottom", fontsize=7,
              fontfamily="sans-serif", color="#888888")

    fig.tight_layout()
    return fig
