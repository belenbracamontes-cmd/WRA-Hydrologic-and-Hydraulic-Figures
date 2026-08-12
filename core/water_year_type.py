"""Core classification and plotting logic for the Water Year Type
Classifier tool.

Ported from a one-off analysis notebook ("Water Year type RDH.ipynb") that
classified water years for one specific watershed (Santa Clara River)
into Critical/Dry/Normal/Wet/Very Wet using HARDCODED annual precipitation
totals and fixed inch-based band edges someone had computed externally.

This module generalizes that to any USGS gauge: instead of a fixed
precipitation record and fixed thresholds, it pulls a station's own
annual mean flow (reusing core.annual_flow_chart's USGS fetch) and splits
that station's own years into quintiles (20/40/60/80th percentiles) --
the driest fifth of years on record become "Critical", the wettest fifth
"Very Wet", and so on. This is the same quintile-based logic California's
official water-year hydrologic classifications use, just computed live
per station/year-range rather than baked in once for one watershed.

Streamlit-agnostic on purpose, same pattern as the other core/ modules.
"""

import datetime as dt

import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

from core.branding import (
    BRAND_FONT_STACK,
    TERRACOTA,
    CALIFORNIA_SUNSET,
    MOSS_GREEN,
    FIELD_GREEN,
    OCEAN_BLUE,
)

rcParams["font.family"]     = "sans-serif"
rcParams["font.sans-serif"] = BRAND_FONT_STACK
rcParams["axes.titlesize"]  = 13
rcParams["axes.labelsize"]  = 11
rcParams["xtick.labelsize"] = 8
rcParams["ytick.labelsize"] = 9

# Low -> high wetness order. Colors are the exact hex values the source
# notebook already used -- which happen to be exact WRA brand colors.
CATEGORIES = ["Critical", "Dry", "Normal", "Wet", "Very Wet"]
WETNESS_VALUE = {cat: i + 1 for i, cat in enumerate(CATEGORIES)}
CATEGORY_COLORS = {
    "Critical": TERRACOTA,
    "Dry": CALIFORNIA_SUNSET,
    "Normal": MOSS_GREEN,
    "Wet": FIELD_GREEN,
    "Very Wet": OCEAN_BLUE,
}

# Quintile split (5 categories) needs at least 5 data points to even
# attempt; fewer than ~10 makes the split fairly meaningless statistically,
# but that's a judgment call left to the user via a warning, not a hard
# stop.
MIN_YEARS_FOR_CLASSIFICATION = 5
RECOMMENDED_MIN_YEARS = 10


def classify_water_years(df, value_col):
    """Classify each row of `df` into one of CATEGORIES via quintiles of
    df[value_col] -- the lowest 20% of years become "Critical", the next
    20% "Dry", and so on up to "Very Wet" for the top 20%.

    Returns (df_with_new_columns, band_edges):
      - df gets two added columns: "WaterYearType" (str) and
        "WetnessValue" (int, 1-5, low-to-high).
      - band_edges is {category: (low, high)} using the actual computed
        quantile cut points for that category, in value_col's units.

    Raises ValueError (with a message safe to show directly to the user)
    if there isn't enough data, or too many repeated values, to form 5
    distinct quantile bins.
    """
    df = df.copy()
    n = len(df)
    if n < MIN_YEARS_FOR_CLASSIFICATION:
        raise ValueError(
            f"Only {n} year(s) of data in this range -- need at least "
            f"{MIN_YEARS_FOR_CLASSIFICATION} to split into 5 water year "
            "types at all (10+ recommended for a meaningful split)."
        )

    try:
        cats, bin_edges = pd.qcut(df[value_col], 5, labels=CATEGORIES, retbins=True)
    except ValueError as e:
        raise ValueError(
            f"This station's {n} years of data don't have enough spread to "
            "split cleanly into 5 water year types (too many repeated/"
            "identical annual values). Try a longer or different year range."
        ) from e

    df["WaterYearType"] = cats.astype(str)
    df["WetnessValue"] = df["WaterYearType"].map(WETNESS_VALUE)

    band_edges = {cat: (bin_edges[i], bin_edges[i + 1]) for i, cat in enumerate(CATEGORIES)}
    return df, band_edges


def _legend_handles(colors):
    return [plt.Rectangle((0, 0), 1, 1, color=colors[cat]) for cat in CATEGORIES]


def _finish_common(fig, ax, station_label, custom_title):
    ax.set_xlabel("Water Year")
    ax.grid(axis="y", linestyle="--", alpha=0.5, linewidth=1.2, color="#421B03")

    title_str = custom_title.strip() if custom_title.strip() else f"{station_label} — Water Year Type"
    fig.suptitle(title_str, fontsize=13, fontweight="bold", fontfamily="sans-serif", y=0.98)

    fig.text(0.99, 0.01, f"© {dt.date.today().year} WRA, Inc.",
              ha="right", va="bottom", fontsize=7, fontfamily="sans-serif", color="#888888")
    fig.subplots_adjust(bottom=0.32)


def make_flow_plot(df, station_label, band_edges, unit_label="cfs", custom_title="", colors=None):
    """Bar height = actual annual mean flow, colored by water year type,
    with a legend showing each category's computed flow band."""
    colors = colors or CATEGORY_COLORS
    fig, ax = plt.subplots(figsize=(16, 8))

    bar_colors = df["WaterYearType"].map(colors)
    ax.bar(df["water_year"], df["avg_flow_cfs"], color=bar_colors)
    ax.set_ylabel(f"Annual Mean Flow ({unit_label})")
    ax.set_xticks(df["water_year"])
    ax.set_xticklabels(df["water_year"].astype(str), rotation=90)

    legend_labels = [
        f"{cat} ({band_edges[cat][0]:,.0f}–{band_edges[cat][1]:,.0f} {unit_label})"
        for cat in CATEGORIES
    ]
    ax.legend(_legend_handles(colors), legend_labels, title="Water Year Type",
              ncol=5, bbox_to_anchor=(0.5, -0.22), loc="upper center", fontsize=8.5,
              title_fontsize=9.5)

    _finish_common(fig, ax, station_label, custom_title)
    return fig


def make_wetness_plot(df, station_label, custom_title="", colors=None):
    """Bar height = the 1-5 wetness scale itself (categorical, all bars
    reaching one of 5 discrete heights), colored by water year type."""
    colors = colors or CATEGORY_COLORS
    fig, ax = plt.subplots(figsize=(16, 8))

    bar_colors = df["WaterYearType"].map(colors)
    ax.bar(df["water_year"], df["WetnessValue"], color=bar_colors)
    ax.set_ylabel("Water Year Type")
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(CATEGORIES)
    ax.set_xticks(df["water_year"])
    ax.set_xticklabels(df["water_year"].astype(str), rotation=90)

    ax.legend(_legend_handles(colors), CATEGORIES, title="Water Year Type",
              ncol=5, bbox_to_anchor=(0.5, -0.22), loc="upper center", fontsize=8.5,
              title_fontsize=9.5)

    _finish_common(fig, ax, station_label, custom_title)
    return fig
