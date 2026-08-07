"""HEC-RAS 2D Time Series Plotter -- Streamlit page.

Ported from the "2D HEC RAS Model Figures Script". Differences from the
notebook version:
  - The original script looped over a list of sensor points/cross-sections
    and saved one separate chart per point. This version treats each point
    as a "scenario" (matching the HEC-RAS 1D tool's pattern) so multiple
    points can be overlaid as color-coded lines on ONE chart for direct
    comparison, instead of generating N un-comparable charts.
  - The "paste a file path" pattern is replaced with a real file upload
    (st.file_uploader).
  - Colors use native st.color_picker widgets (WRA brand hex defaults)
    instead of a fixed color name.
  - Each scenario gets its own Datetime column picker, since each point's
    columns -- including its own datetime block -- can live anywhere in
    the sheet (matching the original SENSOR_POINTS structure).
  - The logo uses the existing assets/logo.png placeholder mechanism (same
    as the other tool pages).
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK
from core.view_source import render_view_source
from core.style_options import render_chart_panel
from core.hecras_2d_timeseries import (
    SERIES_TYPES, SERIES_ICONS, VEL_TYPES, LEVEL_TYPES,
    LINE_STYLES, LINE_STYLE_NAMES, WRA_COLORS,
    column_options, default_scenario_column, default_scenario_color, default_scenario_style,
    list_sheet_names, load_sheet, get_title_from_first_row, make_plot,
)

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>HEC-RAS 2D Time Series Plotter</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Upload an Excel sheet of 2D model results and plot any number of point/cross-section "
               "scenarios, each with its own Velocity/WSE/Depth columns, over time.")

st.subheader("1. File")
uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx", "xls"], key="hec2d_upload")

if uploaded_file is not None:
    sheet_names = list_sheet_names(uploaded_file)
    c1, c2, c3 = st.columns(3)
    with c1:
        sheet_name = st.selectbox("Sheet", sheet_names, key="hec2d_sheet")
    with c2:
        header_row = st.number_input("Header row", min_value=0, max_value=20, value=1, key="hec2d_header_row")
    with c3:
        st.markdown("&nbsp;")
        load_clicked = st.button("Load Sheet", key="hec2d_load_sheet")

    if load_clicked:
        try:
            df_raw = load_sheet(uploaded_file, sheet_name, header_row)
            st.session_state["hec2d_df_raw"] = df_raw
            st.session_state["hec2d_col_opts"] = column_options(df_raw)
            try:
                st.session_state["hec2d_auto_title"] = get_title_from_first_row(uploaded_file, sheet_name)
            except Exception:
                st.session_state["hec2d_auto_title"] = ""
            st.success(f"Sheet **{sheet_name}** loaded: {len(df_raw)} rows x {len(df_raw.columns)} columns.")
        except Exception as e:
            st.error(f"Error loading sheet: {e}")

if "hec2d_df_raw" in st.session_state:
    df_raw = st.session_state["hec2d_df_raw"]
    col_opts = st.session_state["hec2d_col_opts"]

    def col_label(idx):
        for label, i in col_opts:
            if i == idx:
                return label
        return str(idx)

    st.subheader("2. What to plot")
    st.caption("Check all series types that apply -- each point/scenario below will get a column "
               "picker for every type checked here.")
    cbs = st.columns(len(SERIES_TYPES))
    active_types = {}
    for c, stype in zip(cbs, SERIES_TYPES):
        with c:
            active_types[stype] = st.checkbox(f"{SERIES_ICONS[stype]} {stype}", key=f"hec2d_active_{stype}")

    n_scenarios = st.number_input("# of points / cross-sections to compare", min_value=1, max_value=8, value=1,
                                   key="hec2d_n_scenarios")

    active_list = [s for s in SERIES_TYPES if active_types[s]]

    st.subheader("3. Configure each point / cross-section")
    if not active_list:
        st.info("Check at least one series type above to configure points.")
    else:
        st.caption("Each point's Datetime column doesn't have to be in the same spot -- pick "
                   "whichever column is correct for each one.")
        legend_names = []
        for i in range(n_scenarios):
            with st.container(border=True):
                st.markdown(f"**Point {i + 1}**")

                datetime_default = col_opts[0][1] if col_opts else None
                datetime_index = ([idx for _, idx in col_opts].index(datetime_default)
                                   if datetime_default is not None else 0)
                st.selectbox(f"Datetime column (Point {i + 1})", [idx for _, idx in col_opts],
                             index=datetime_index, format_func=col_label, key=f"hec2d_datetime_{i}")

                for stype in active_list:
                    st.markdown(f"{SERIES_ICONS[stype]} {stype}")
                    c1, c2, c3 = st.columns([3, 1, 1.5])
                    default_col = default_scenario_column(col_opts, i)
                    default_color_name = default_scenario_color(i)
                    default_style_name = default_scenario_style(i)
                    with c1:
                        st.selectbox(f"{stype} column", [idx for _, idx in col_opts],
                                     index=[idx for _, idx in col_opts].index(default_col) if default_col is not None else 0,
                                     format_func=col_label, key=f"hec2d_col_{stype}_{i}",
                                     label_visibility="collapsed")
                    with c2:
                        st.color_picker("Color", WRA_COLORS[default_color_name], key=f"hec2d_color_{stype}_{i}",
                                         label_visibility="collapsed")
                    with c3:
                        st.selectbox("Line style", LINE_STYLE_NAMES,
                                     index=LINE_STYLE_NAMES.index(default_style_name),
                                     key=f"hec2d_style_{stype}_{i}", label_visibility="collapsed")

                legend_names.append(
                    st.text_input(f"Legend label (Point {i + 1})", key=f"hec2d_label_{i}",
                                   placeholder="auto (column name)")
                )

    st.subheader("4. Title & generate")
    title = st.text_input("Plot title (optional)", key="hec2d_title",
                           placeholder=st.session_state.get("hec2d_auto_title", "") or "Auto-pulled from Excel row 1 if blank")

    if st.button("Generate Plot", type="primary", key="hec2d_generate"):
        if not active_list:
            st.error("Check at least one series type first.")
            st.stop()
        try:
            scenario_specs = []
            for i in range(n_scenarios):
                series = []
                for stype in active_list:
                    col_idx = st.session_state[f"hec2d_col_{stype}_{i}"]
                    color_hex = st.session_state[f"hec2d_color_{stype}_{i}"]
                    style_name = st.session_state[f"hec2d_style_{stype}_{i}"]
                    label = legend_names[i].strip() if legend_names[i].strip() else col_label(col_idx)
                    series.append({
                        "stype": stype, "col_idx": col_idx, "color_hex": color_hex,
                        "line_style": LINE_STYLES[style_name], "label": label,
                    })
                scenario_specs.append({
                    "datetime_idx": st.session_state[f"hec2d_datetime_{i}"],
                    "series": series,
                })

            final_title = title.strip() or st.session_state.get("hec2d_auto_title", "") or "2D Time Series Plot"

            st.session_state["hec2d_result"] = dict(
                scenario_specs=scenario_specs, title=final_title,
            )
        except Exception as e:
            st.error(f"Error building plot: {e}")
            st.stop()

    if "hec2d_result" in st.session_state:
        r = st.session_state["hec2d_result"]
        fig = make_plot(df_raw, r["scenario_specs"], r["title"])

        all_series = [s for sc in r["scenario_specs"] for s in sc["series"]]
        dual = len(fig.axes) > 1
        if dual:
            vel_colors = [s["color_hex"] for s in all_series if s["stype"] in VEL_TYPES]
            level_colors = [s["color_hex"] for s in all_series if s["stype"] in LEVEL_TYPES]
            axis_specs = [
                (fig.axes[0], ["x", "y"], vel_colors[0] if vel_colors else None),
                (fig.axes[1], ["y"], level_colors[0] if level_colors else None),
            ]
        else:
            first_color = all_series[0]["color_hex"] if all_series else None
            axis_specs = [(fig.axes[0], ["x", "y"], first_color)]

        render_chart_panel(fig, key_prefix="hec2d_chart", base_filename="hecras_2d_timeseries",
                            axis_specs=axis_specs)
else:
    st.info("Upload an Excel file above to get started.")

st.divider()
render_view_source(__file__)
