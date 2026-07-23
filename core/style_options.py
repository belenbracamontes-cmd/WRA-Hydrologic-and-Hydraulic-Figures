"""Presentation-styling options applied to a finished chart, just before
export (e.g. for dropping into a PowerPoint deck).

"Annotations" here means every non-data-color chrome element: title, axis
labels, tick labels, tick marks, axis spines (border lines), and legend
text/border. The actual bars/lines/markers are never touched. All colors
are pulled from the WRA brand palette (core/branding.py) -- no arbitrary
hex values.
"""

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
