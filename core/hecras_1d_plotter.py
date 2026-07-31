"""Core data-loading and plotting logic for the HEC-RAS 1D Cross Section
Plotter tool -- ported from the "HEC-RAS 1D Profile Plotter" ipywidgets GUI.

Plots any number of "scenarios" (comparisons) across up to four series
types (Velocity, WSE, Profile, Elevation) read from arbitrary columns of an
uploaded Excel sheet, against a chosen Station column. Velocity goes on the
left y-axis; WSE/Profile/Elevation go on the right y-axis (or the left axis
alone, if Velocity isn't included) -- a dual axis is used only when both a
Velocity-type and an Elevation-type series are both active.

This module is Streamlit-agnostic on purpose: it can be imported, tested, or
reused from a plain script. The Streamlit page (pages/5_HEC_RAS_1D_Figures.py)
is a thin UI layer on top of it, including the actual file upload handling.
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

# ── WRA brand palette (verified hex from core/branding.py -- no invented
#    placeholder colors), offered as named swatch choices per series ------
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

# Default color assigned per scenario index, cycling through distinct hues
# before repeating a shade/tint of one already used.
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

SERIES_TYPES = ["Velocity", "WSE", "Profile", "Elevation"]
SERIES_ICONS = {"Velocity": "🌊", "WSE": "💧", "Profile": "📐", "Elevation": "🏔"}
ELEV_TYPES = {"WSE", "Profile", "Elevation"}
VEL_TYPES = {"Velocity"}

YLABEL_VEL = "Velocity (ft/s)"
YLABEL_ELEV = "Elevation (ft)"
XLABEL = "Station (ft)"


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
    first column (usually the station column) and offset by scenario."""
    if not col_opts:
        return None
    idx = min(scenario_idx + 1, len(col_opts) - 1)
    return col_opts[idx][1]


def default_scenario_color(scenario_idx):
    return SCENARIO_COLOR_SEQUENCE[scenario_idx % len(SCENARIO_COLOR_SEQUENCE)]


def default_scenario_style(scenario_idx):
    return LINE_STYLE_NAMES[scenario_idx % len(LINE_STYLE_NAMES)]


# ── Excel loading ─────────────────────────────────────────────────────────
def list_sheet_names(file_obj):
    file_obj.seek(0)
    return pd.ExcelFile(file_obj).sheet_names


def load_sheet(file_obj, sheet_name, header_row):
    file_obj.seek(0)
    return pd.read_excel(file_obj, sheet_name=sheet_name, header=header_row)


def get_title_from_first_row(file_obj, sheet_name):
    file_obj.seek(0)
    raw = pd.read_excel(file_obj, sheet_name=sheet_name, header=None, nrows=1)
    return str(raw.iloc[0, 0])


# ── Plot ──────────────────────────────────────────────────────────────────
def make_plot(df_raw, station_idx, series_specs, custom_title=""):
    """Build the cross-section plot.

    df_raw        -- the loaded sheet (header row already applied)
    station_idx   -- column index used for the x-axis (Station)
    series_specs  -- list of dicts, one per plotted line:
                     {"stype": one of SERIES_TYPES, "col_idx": int,
                      "color_hex": str, "line_style": matplotlib linestyle,
                      "label": str}
    Returns the matplotlib Figure (does not call plt.show()).
    """
    df = df_raw[pd.to_numeric(df_raw.iloc[:, station_idx], errors="coerce").notna()].copy()
    df.iloc[:, station_idx] = df.iloc[:, station_idx].astype(float)
    df = df.sort_values(df.columns[station_idx])
    x = df.iloc[:, station_idx]

    def col_data(idx):
        return pd.to_numeric(df.iloc[:, idx], errors="coerce")

    has_vel = any(s["stype"] in VEL_TYPES for s in series_specs)
    has_elev = any(s["stype"] in ELEV_TYPES for s in series_specs)
    dual = has_vel and has_elev

    fig, ax1 = plt.subplots(figsize=(11, 7))
    ax2 = ax1.twinx() if dual else None

    lines, lbls = [], []
    for spec in series_specs:
        ax = ax1 if spec["stype"] in VEL_TYPES else (ax2 if dual else ax1)
        ln, = ax.plot(
            x, col_data(spec["col_idx"]),
            color=spec["color_hex"], linestyle=spec["line_style"],
            linewidth=1.8, label=spec["label"],
        )
        lines.append(ln)
        lbls.append(spec["label"])

    ax1.set_xlabel(XLABEL, fontsize=11)
    if has_vel and not has_elev:
        ax1.set_ylabel(YLABEL_VEL, fontsize=11)
    elif has_elev and not has_vel:
        ax1.set_ylabel(YLABEL_ELEV, fontsize=11)
    else:
        ax1.set_ylabel(YLABEL_VEL, fontsize=11)
        if ax2:
            ax2.set_ylabel(YLABEL_ELEV, fontsize=11)

    ax1.set_title(custom_title, fontsize=13, fontweight="bold", color=BRAND_DARK)
    ax1.grid(True, linestyle="--", linewidth=0.7, alpha=0.6)

    fig.legend(
        lines, lbls,
        loc="lower center", bbox_to_anchor=(0.5, -0.14),
        ncol=min(4, len(lines)), fontsize=10,
        frameon=True, edgecolor="#C8D8E4",
    )

    fig.text(0.99, 0.01, "© WRA, Inc.",
             ha="right", va="bottom", fontsize=7,
             fontfamily="sans-serif", color="#888888")

    fig.tight_layout()
    return fig
