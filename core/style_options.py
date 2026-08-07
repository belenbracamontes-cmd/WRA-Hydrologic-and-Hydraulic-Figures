"""Presentation-styling options applied to a finished chart, just before
export (e.g. for dropping into a PowerPoint deck).

"Annotations" here means every non-data-color chrome element: title, axis
labels, tick labels, tick marks, axis spines (border lines), and legend
text/border. The actual bars/lines/markers are never touched. All colors
are pulled from the WRA brand palette (core/branding.py) -- no arbitrary
hex values.

render_chart_panel() (bottom of this file) is the shared "customize &
export" block every tool page uses: size, annotation color, plot-area
background, and export background/download all grouped together, with
exactly one st.pyplot(fig) call -- deliberately never a "before" render
followed by a re-styled "after" render, per explicit user feedback that
seeing two copies of the same chart stacked on screen was confusing.
"""

from io import BytesIO

import streamlit as st

from core.branding import (
    BRAND_DARK,
    TERRACOTA,
    TERRACOTA_SHADE,
    CALIFORNIA_SUNSET_SHADE,
    MOSS_GREEN_SHADE,
    FIELD_GREEN_SHADE,
    OCEAN_BLUE_SHADE,
)

MATCH_SERIES = "Match axis color to its data series"

# Ordered so the dropdown reads: match-series option first, then a neutral
# black, then the primary brand color, then every "shade" (the darker,
# presentation-friendly variant of each of the five brand colors).
ANNOTATION_PRESETS = {
    MATCH_SERIES: None,  # resolved per-axis in restyle_annotations, not a single color
    "Black": "#000000",
    "Terracota": TERRACOTA,
    "Terracota Shade": TERRACOTA_SHADE,
    "California Sunset Shade": CALIFORNIA_SUNSET_SHADE,
    "Moss Green Shade": MOSS_GREEN_SHADE,
    "Field Green Shade": FIELD_GREEN_SHADE,
    "Ocean Blue Shade": OCEAN_BLUE_SHADE,
}


def _style_axis_chrome(ax, color, sides):
    """Recolor one axes' label/ticks/spine(s) on the given sides ('x'/'y')."""
    for side in sides:
        axis_obj = ax.xaxis if side == "x" else ax.yaxis
        axis_obj.label.set_color(color)
        ax.tick_params(axis=side, colors=color)
    for spine_name, spine in ax.spines.items():
        relevant = (
            ("x" in sides and spine_name in ("top", "bottom")) or
            ("y" in sides and spine_name in ("left", "right"))
        )
        if relevant:
            spine.set_edgecolor(color)


def restyle_annotations(fig, preset, axis_specs):
    """Recolor every chrome element in `fig` according to `preset`.

    axis_specs -- list of (ax, sides, series_color) tuples, one per axes
        that should be restyled. `sides` is a subset of {"x", "y"}
        indicating which of that axes' label/ticks/spine to touch.
        `series_color` is that axis's own data-series color, used only
        when preset == MATCH_SERIES (ignored for fixed-color presets).
    """
    match_mode = preset == MATCH_SERIES
    base_color = BRAND_DARK if match_mode else ANNOTATION_PRESETS.get(preset, "#000000")

    suptitle = getattr(fig, "_suptitle", None)
    if suptitle is not None:
        suptitle.set_color(base_color)
    supylabel = getattr(fig, "_supylabel", None)
    if supylabel is not None:
        supylabel.set_color(base_color)
    supxlabel = getattr(fig, "_supxlabel", None)
    if supxlabel is not None:
        supxlabel.set_color(base_color)
    for ax in fig.axes:
        if ax.get_title():
            ax.title.set_color(base_color)

    for ax, sides, series_color in axis_specs:
        color = (series_color or base_color) if match_mode else base_color
        _style_axis_chrome(ax, color, sides)

    for ax in fig.axes:
        leg = ax.get_legend()
        if leg is None:
            continue
        leg.get_frame().set_edgecolor(base_color)
        for text in leg.get_texts():
            text.set_color(base_color)
        if leg.get_title().get_text():
            leg.get_title().set_color(base_color)


# ── Chart size ────────────────────────────────────────────────────────────────
# A "Current" entry matching the chart's own native figsize is always
# prepended and selected by default in render_chart_panel() -- these named
# presets are additional choices, not a replacement for whatever size a
# given chart was already built at (multi-subplot charts in particular size
# themselves taller per subplot, which a single fixed default would clobber).
SIZE_PRESETS = {
    "Compact (9 × 5.5 in)": (9.0, 5.5),
    "Standard (11 × 7 in)": (11.0, 7.0),
    "Large (14 × 9 in)": (14.0, 9.0),
    "Widescreen (16 × 6 in)": (16.0, 6.0),
    "Custom...": None,
}

# ── Plot-area (axes) background -- "inside the box" only, never the outer
#    figure background (that's EXPORT_BG_OPTIONS below) ─────────────────────
PLOT_BG_PRESETS = {
    "White": "#FFFFFF",
    "Neutral": "#fbf6ec",
    "Light Grey": "#F0F0F0",
    "Transparent": None,
}

# ── Export (outer figure) background, used both for the on-screen preview
#    and the downloaded file -- Transparent is the default so a chart drops
#    cleanly onto a colored PowerPoint slide without an extra click ────────
EXPORT_BG_OPTIONS = ["Transparent", "Normal"]


def render_chart_panel(fig, key_prefix, base_filename, axis_specs,
                        default_annotation_index=1, download_label="Download chart"):
    """The one consolidated "customize & export" block every chart uses --
    size, annotation color, plot-area background, and export background/
    download all grouped together, with exactly one st.pyplot(fig) call.

    axis_specs -- same shape restyle_annotations() expects: a list of
        (ax, sides, series_color) tuples built from fig.axes right after
        the caller creates `fig` (this varies per chart -- dual-axis vs.
        single-axis, "match series color" support -- so it stays the
        caller's responsibility, same as before this function existed).
    """
    st.subheader("🎨 Customize & export")

    native_w, native_h = fig.get_size_inches()
    size_options = {f"Current ({native_w:.1f} × {native_h:.1f} in)": (native_w, native_h)}
    size_options.update(SIZE_PRESETS)
    size_names = list(size_options.keys())

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        size_name = st.selectbox("Chart size", size_names, index=0, key=f"{key_prefix}_size")
    with c2:
        preset = st.selectbox(
            "Annotation color", list(ANNOTATION_PRESETS.keys()),
            index=default_annotation_index, key=f"{key_prefix}_annotation_preset",
        )
    with c3:
        bg_name = st.selectbox("Plot area background", list(PLOT_BG_PRESETS.keys()),
                                key=f"{key_prefix}_plot_bg")
    with c4:
        export_bg = st.selectbox("Export background", EXPORT_BG_OPTIONS, key=f"{key_prefix}_export_bg")

    if size_options[size_name] is None:  # "Custom..."
        sc1, sc2 = st.columns(2)
        with sc1:
            width = st.number_input("Width (in)", min_value=3.0, max_value=30.0, value=float(native_w),
                                     step=0.5, key=f"{key_prefix}_custom_width")
        with sc2:
            height = st.number_input("Height (in)", min_value=2.0, max_value=25.0, value=float(native_h),
                                      step=0.5, key=f"{key_prefix}_custom_height")
    else:
        width, height = size_options[size_name]
    fig.set_size_inches(width, height)

    restyle_annotations(fig, preset, axis_specs)

    bg_color = PLOT_BG_PRESETS[bg_name]
    for ax in fig.axes:
        if bg_color is None:
            ax.patch.set_alpha(0)
        else:
            ax.patch.set_alpha(1)
            ax.set_facecolor(bg_color)

    transparent = (export_bg == "Transparent")
    fig.patch.set_alpha(0 if transparent else 1)

    st.pyplot(fig, use_container_width=True)

    buf = BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", transparent=transparent)
    st.download_button(
        f"{download_label} (SVG, {export_bg.lower()} export background)",
        data=buf.getvalue(), file_name=f"{base_filename}.svg", mime="image/svg+xml",
        key=f"{key_prefix}_download",
    )
