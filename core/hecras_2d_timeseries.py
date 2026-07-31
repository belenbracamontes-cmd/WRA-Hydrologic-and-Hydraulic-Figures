"""Core data-loading and plotting logic for the HEC-RAS 2D Time Series
Plotter tool -- ported from the "2D HEC RAS Model Figures Script".

The original script looped over a list of sensor points/cross-sections and
saved one separate figure per point. This version instead treats each point
as a "scenario" (mirroring core/hecras_1d_plotter.py) so multiple points can
be overlaid as color-coded lines on ONE chart for direct comparison, across
up to three series types (Velocity, WSE, Depth). Velocity goes on the left
y-axis; WSE/Depth go on the right y-axis (or the left axis alone, if
Velocity isn't included) -- a dual axis is used only when both a
Velocity-type and a level-type series are active somewhere.

The time axis is NOT real pandas datetimes: HEC-RAS 2D exports timestamps
like "01Jan1000 00:00:00" using a placeholder simulation-start year that's
out of pandas' valid datetime range, so (like the original script) this
plots against a plain row-sequence index and derives display-only tick
labels by string-slicing the raw timestamp text.

This module is Streamlit-agnostic on purpose: it can be imported, tested, or
reused from a plain script. The Streamlit page is a thin UI layer on top of
it, including the actual file upload handling.
"""

import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

from core.branding import (
    BRAND_FONT_STACK, BRAND_DARK,
    TERRACOTA, TERRACOTA_SHADE, TERRACOTA_TINT,
    CALIFORNIA_SUNSET, CALIFORNIA_SUNSET_SHADE, CALIFORNIA_SUNSET_TINT,
    MOSS_GREEN, MOSS_GREEN_SHADE, MOSS_GREEN_TINT,
    FIELD_GREEN, FIELD_GREEN_SHADE, FIELD_GREEN_TINT,
    OCEAN_BLUE, OCEAN_BLUE_SHADE, OCEAN_BLUE_TINT,
)

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = BRAND_FONT_STACK
rcParams["axes.titlesize"] = 13
rcParams["axes.labelsize"] = 11
rcParams["xtick.labelsize"] = 9
rcParams["ytick.labelsize"] = 9

# ── WRA brand palette (verified hex from core/branding.py), offered as
#    named swatch choices per series -----------------------------------------
WRA_COLORS = {
    "Terracota": TERRACOTA, "Terracota Shade": TERRACOTA_SHADE, "Terracota Tint": TERRACOTA_TINT,
    "California Sunset": CALIFORNIA_SUNSET, "California Sunset Shade": CALIFORNIA_SUNSET_SHADE,
    "California Sunset Tint": CALIFORNIA_SUNSET_TINT,
    "Moss Green": MOSS_GREEN, "Moss Green Shade": MOSS_GREEN_SHADE, "Moss Green Tint": MOSS_GREEN_TINT,
    "Field Green": FIELD_GREEN, "Field Green Shade": FIELD_GREEN_SHADE, "Field Green Tint": FIELD_GREEN_TINT,
    "Ocean Blue": OCEAN_BLUE, "Ocean Blue Shade": OCEAN_BLUE_SHADE, "Ocean Blue Tint": OCEAN_BLUE_TINT,
    "Black": "#000000",
}
COLOR_NAMES = list(WRA_COLORS.keys())

SCENARIO_COLOR_SEQUENCE = [
    "Ocean Blue", "Terracota", "Field Green", "California Sunset", "Moss Green",
    "Ocean Blue Shade", "Terracota Shade", "Field Green Shade",
]

LINE_STYLES = {
    "Solid": "-",
    "Dashed": "--",
    "Dash-dot": "-.",
    "Dotted": ":",
    "Long dash": (0, (5, 5)),
}
LINE_STYLE_NAMES = list(LINE_STYLES.keys())

SERIES_TYPES = ["Velocity", "WSE", "Depth"]
SERIES_ICONS = {"Velocity": "🌊", "WSE": "💧", "Depth": "📏"}
VEL_TYPES = {"Velocity"}
LEVEL_TYPES = {"WSE", "Depth"}

YLABEL_VEL = "Velocity (fps)"
XLABEL = "Date / Time"

MONTHS = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
          "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}


# ── Column-letter helpers ─────────────────────────────────────────────────
def index_to_col_letter(idx):
    result, idx = "", idx + 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def column_options(df):
    """Return [(label, index), ...] for a dropdown, e.g. 'A  -  Station'."""
    return [(f"{index_to_col_letter(i)}  –  {str(c)}", i)
            for i, c in enumerate(df.columns)]


def default_scenario_column(col_opts, scenario_idx):
    """A reasonable default column pick for a new scenario picker: skip the
    first column (usually the datetime column) and offset by scenario."""
    if not col_opts:
        return None
    idx = min(scenario_idx + 1, len(col_opts) - 1)
    return col_opts[idx][1]


def default_scenario_color(scenario_idx):
    return SCENARIO_COLOR_SEQUENCE[scenario_idx % len(SCENARIO_COLOR_SEQUENCE)]


def default_scenario_style(scenario_idx):
    return LINE_STYLE_NAMES[scenario_idx % len(LINE_STYLE_NAMES)]


def level_ylabel(active_level_types):
    """WSE-only, Depth-only, or both -- picks the right axis label."""
    active = set(active_level_types)
    if active == {"WSE"}:
        return "WSE (ft)"
    if active == {"Depth"}:
        return "Depth (ft)"
    return "WSE / Depth (ft)"


# ── Excel loading ─────────────────────────────────────────────────────────
def list_sheet_names(file_obj):
    file_obj.seek(0)
    return pd.ExcelFile(file_obj).sheet_names


def load_sheet(file_obj, sheet_name, header_row):
    file_obj.seek(0)
    df = pd.read_excel(file_obj, sheet_name=sheet_name, header=header_row)
    return df.dropna(how="all")


def get_title_from_first_row(file_obj, sheet_name):
    file_obj.seek(0)
    raw = pd.read_excel(file_obj, sheet_name=sheet_name, header=None, nrows=1)
    return str(raw.iloc[0, 0])


def clean_timestamp_label(s):
    """Parses '01Jan1000 00:00:00' -> '01/01 00:00' using string slicing.
    Avoids real datetime parsing since HEC-RAS 2D exports use a placeholder
    simulation-start year (e.g. 1000) that's out of pandas' valid range."""
    try:
        s = str(s).strip()
        day = s[0:2]
        mon = s[2:5]
        tim = s[10:15]
        return f"{MONTHS.get(mon, mon)}/{day} {tim}"
    except Exception:
        return str(s).strip()


# ── Plot ──────────────────────────────────────────────────────────────────
def make_plot(df_raw, scenario_specs, custom_title=""):
    """Build the time-series plot.

    df_raw          -- the loaded sheet (header row already applied)
    scenario_specs  -- list of dicts, one per point/cross-section (a
                       "scenario"), since each point's columns -- including
                       its own datetime column -- can live in a different
                       block of the sheet:
                       {"datetime_idx": int,
                        "series": [{"stype": one of SERIES_TYPES,
                                    "col_idx": int, "color_hex": str,
                                    "line_style": matplotlib linestyle,
                                    "label": str}, ...]}
                       Series within a scenario should be ordered Velocity,
                       WSE, Depth -- the first entry's column is used to
                       decide which rows have real data (matching the
                       original script's per-point filtering).
    Returns the matplotlib Figure (does not call plt.show()).
    """
    all_series = [s for sc in scenario_specs for s in sc["series"]]
    has_vel = any(s["stype"] in VEL_TYPES for s in all_series)
    has_level = any(s["stype"] in LEVEL_TYPES for s in all_series)
    dual = has_vel and has_level

    fig, ax1 = plt.subplots(figsize=(12, 6.5))
    ax2 = ax1.twinx() if dual else None

    lines, lbls = [], []
    tick_x, tick_labels = None, None

    for sc in scenario_specs:
        if not sc["series"]:
            continue
        filter_col_idx = sc["series"][0]["col_idx"]
        df = df_raw[pd.to_numeric(df_raw.iloc[:, filter_col_idx], errors="coerce").notna()].copy()
        df = df.reset_index(drop=True)
        x = df.index

        date_labels = df.iloc[:, sc["datetime_idx"]].apply(clean_timestamp_label)
        if tick_x is None:
            tick_x, tick_labels = x, date_labels

        for spec in sc["series"]:
            ax = ax1 if spec["stype"] in VEL_TYPES else (ax2 if dual else ax1)
            y = pd.to_numeric(df.iloc[:, spec["col_idx"]], errors="coerce")
            ln, = ax.plot(
                x, y, color=spec["color_hex"], linestyle=spec["line_style"],
                linewidth=1.5, label=spec["label"],
            )
            lines.append(ln)
            lbls.append(spec["label"])

    if tick_x is not None:
        n = max(1, len(tick_labels) // 10)
        ax1.set_xticks(tick_x[::n])
        ax1.set_xticklabels(tick_labels.iloc[::n], rotation=45, ha="right")

    ax1.set_xlabel(XLABEL, fontsize=11)
    level_types_active = [s["stype"] for s in all_series if s["stype"] in LEVEL_TYPES]
    if has_vel and not has_level:
        ax1.set_ylabel(YLABEL_VEL, fontsize=11)
    elif has_level and not has_vel:
        ax1.set_ylabel(level_ylabel(level_types_active), fontsize=11)
    else:
        ax1.set_ylabel(YLABEL_VEL, fontsize=11)
        if ax2:
            ax2.set_ylabel(level_ylabel(level_types_active), fontsize=11)

    ax1.set_title(custom_title, fontsize=13, fontweight="bold", color=BRAND_DARK)
    ax1.grid(True, linestyle="--", linewidth=0.7, alpha=0.6)

    fig.legend(
        lines, lbls,
        loc="lower center", bbox_to_anchor=(0.5, -0.16),
        ncol=min(4, len(lines)), fontsize=10,
        frameon=True, edgecolor="#C8D8E4",
    )

    fig.text(0.99, 0.01, "© WRA, Inc.",
             ha="right", va="bottom", fontsize=7,
             fontfamily="sans-serif", color="#888888")

    fig.tight_layout()
    return fig
