"""HEC-RAS Cross Sections -- Streamlit page.

A Station-vs-Elevation geometry plot. Each cross section added gets its
own Station/Elevation column pair (Station on the x-axis, Elevation on
the y-axis) plus an optional second "Modification" elevation column
(e.g. a proposed/regraded profile) -- add as many cross sections as
needed with the "+" button and they're all overlaid on one chart. Unset
labels fall back to whatever the Excel column header says.

Its own sidebar page (rather than a tab on the 1D Figures page) since
it's a genuinely different kind of plot from the Velocity/WSE/Profile/
Elevation scenario plotter there -- raw cross-section geometry, not a
model-results comparison.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK
from core.style_options import render_chart_panel, render_data_color_pickers
from core.hecras_1d_plotter import (
    LINE_STYLES, LINE_STYLE_NAMES, WRA_COLORS,
    column_options, default_scenario_color, default_xs_column,
    list_sheet_names, load_sheet, get_title_from_first_row, make_cross_section_plot,
)

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>HEC-RAS Cross Sections</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Upload an Excel sheet and plot one or more Station-vs-Elevation cross sections, "
               "each with an optional modification profile, overlaid on one chart.")

st.markdown(
    "Each cross section gets its own **Station** (x-axis) and **Elevation** (y-axis) column, "
    "plus an optional **Modification** column (e.g. a proposed/regraded profile) plotted "
    "alongside it. Add as many cross sections as you need -- they're all overlaid on one chart. "
    "Leave a label blank to use whatever the Excel column header says."
)

st.subheader("1. File")
xs_uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx", "xls"], key="xs_upload")

if xs_uploaded_file is not None:
    xs_sheet_names = list_sheet_names(xs_uploaded_file)
    c1, c2, c3 = st.columns(3)
    with c1:
        xs_sheet_name = st.selectbox("Sheet", xs_sheet_names, key="xs_sheet")
    with c2:
        xs_header_row = st.number_input("Header row", min_value=0, max_value=20, value=1, key="xs_header_row")
    with c3:
        st.markdown("&nbsp;")
        xs_load_clicked = st.button("Load Sheet", key="xs_load_sheet")

    if xs_load_clicked:
        try:
            xs_df_raw = load_sheet(xs_uploaded_file, xs_sheet_name, xs_header_row)
            st.session_state["xs_df_raw"] = xs_df_raw
            st.session_state["xs_col_opts"] = column_options(xs_df_raw)
            try:
                st.session_state["xs_auto_title"] = get_title_from_first_row(xs_uploaded_file, xs_sheet_name)
            except Exception:
                st.session_state["xs_auto_title"] = ""
            st.success(f"Sheet **{xs_sheet_name}** loaded: {len(xs_df_raw)} rows x {len(xs_df_raw.columns)} columns.")
        except Exception as e:
            st.error(f"Error loading sheet: {e}")

if "xs_df_raw" in st.session_state:
    xs_df_raw = st.session_state["xs_df_raw"]
    xs_col_opts = st.session_state["xs_col_opts"]
    xs_col_idx_list = [idx for _, idx in xs_col_opts]

    def xs_col_label(idx):
        for label, i in xs_col_opts:
            if i == idx:
                return label
        return str(idx)

    if "xs_ids" not in st.session_state:
        st.session_state["xs_ids"] = [0]
    if "xs_next_id" not in st.session_state:
        st.session_state["xs_next_id"] = 1
    xs_ids = st.session_state["xs_ids"]

    st.subheader("2. Cross sections")
    for pos, xid in enumerate(list(xs_ids)):
        with st.container(border=True):
            head_col, remove_col = st.columns([6, 1])
            with head_col:
                st.markdown(f"**Cross section {pos + 1}**")
            with remove_col:
                if len(xs_ids) > 1 and st.button("✕", key=f"xs_remove_{xid}",
                                                   help="Remove this cross section"):
                    st.session_state["xs_ids"] = [x for x in xs_ids if x != xid]
                    st.rerun()

            sc1, sc2 = st.columns(2)
            with sc1:
                station_default = default_xs_column(xs_col_opts, "station")
                st.selectbox(
                    "Station column (x-axis)", xs_col_idx_list,
                    index=xs_col_idx_list.index(station_default) if station_default is not None else 0,
                    format_func=xs_col_label, key=f"xs_station_{xid}",
                )
            with sc2:
                elevation_default = default_xs_column(xs_col_opts, "elevation")
                st.selectbox(
                    "Elevation column (y-axis)", xs_col_idx_list,
                    index=xs_col_idx_list.index(elevation_default) if elevation_default is not None else 0,
                    format_func=xs_col_label, key=f"xs_elevation_{xid}",
                )

            ec1, ec2, ec3 = st.columns([3, 1, 1.5])
            default_color_name = default_scenario_color(pos)
            with ec1:
                st.text_input("Label (optional)", key=f"xs_label_{xid}",
                               placeholder="auto (column name)")
            with ec2:
                st.color_picker("Color", WRA_COLORS[default_color_name], key=f"xs_color_{xid}",
                                 label_visibility="collapsed")
            with ec3:
                st.selectbox("Line style", LINE_STYLE_NAMES, index=0,
                             key=f"xs_style_{xid}", label_visibility="collapsed")

            has_mod = st.checkbox("➕ Add modification column", key=f"xs_has_mod_{xid}")
            if has_mod:
                mod_default = default_xs_column(xs_col_opts, "modification")
                mc1, mc2, mc3 = st.columns([3, 1, 1.5])
                with mc1:
                    st.selectbox(
                        "Modification column", xs_col_idx_list,
                        index=xs_col_idx_list.index(mod_default) if mod_default is not None else 0,
                        format_func=xs_col_label, key=f"xs_mod_col_{xid}",
                    )
                with mc2:
                    st.color_picker("Color", WRA_COLORS[default_color_name], key=f"xs_mod_color_{xid}",
                                     label_visibility="collapsed")
                with mc3:
                    st.selectbox("Line style", LINE_STYLE_NAMES,
                                 index=LINE_STYLE_NAMES.index("Dashed"),
                                 key=f"xs_mod_style_{xid}", label_visibility="collapsed")
                st.text_input("Modification label (optional)", key=f"xs_mod_label_{xid}",
                               placeholder="auto (column name)")

    if st.button("➕ Add cross section", key="xs_add"):
        st.session_state["xs_ids"].append(st.session_state["xs_next_id"])
        st.session_state["xs_next_id"] += 1
        st.rerun()

    st.subheader("3. Title & generate")
    xs_title = st.text_input(
        "Plot title (optional)", key="xs_title",
        placeholder=st.session_state.get("xs_auto_title", "") or "Auto-pulled from Excel row 1 if blank",
    )

    if st.button("Generate Plot", type="primary", key="xs_generate"):
        try:
            xs_specs = []
            for xid in st.session_state["xs_ids"]:
                elevation_idx = st.session_state[f"xs_elevation_{xid}"]
                label_input = st.session_state[f"xs_label_{xid}"]
                spec = {
                    "station_idx": st.session_state[f"xs_station_{xid}"],
                    "elevation_idx": elevation_idx,
                    "elevation_label": label_input.strip() if label_input.strip() else xs_col_label(elevation_idx),
                    "elevation_color_hex": st.session_state[f"xs_color_{xid}"],
                    "elevation_line_style": LINE_STYLES[st.session_state[f"xs_style_{xid}"]],
                    "has_modification": st.session_state.get(f"xs_has_mod_{xid}", False),
                }
                if spec["has_modification"]:
                    mod_idx = st.session_state[f"xs_mod_col_{xid}"]
                    mod_label_input = st.session_state[f"xs_mod_label_{xid}"]
                    spec.update({
                        "modification_idx": mod_idx,
                        "modification_label": mod_label_input.strip() if mod_label_input.strip() else xs_col_label(mod_idx),
                        "modification_color_hex": st.session_state[f"xs_mod_color_{xid}"],
                        "modification_line_style": LINE_STYLES[st.session_state[f"xs_mod_style_{xid}"]],
                    })
                xs_specs.append(spec)

            final_xs_title = xs_title.strip() or st.session_state.get("xs_auto_title", "") or "Cross Section Plot"

            st.session_state["xs_result"] = dict(xs_specs=xs_specs, title=final_xs_title)
        except Exception as e:
            st.error(f"Error building plot: {e}")
            st.stop()

    if "xs_result" in st.session_state:
        r = st.session_state["xs_result"]

        color_series = []
        for spec in r["xs_specs"]:
            color_series.append({"label": spec["elevation_label"], "color": spec["elevation_color_hex"]})
            if spec.get("has_modification"):
                color_series.append({"label": spec["modification_label"], "color": spec["modification_color_hex"]})
        color_overrides = render_data_color_pickers(color_series, key_prefix="xs_chart")
        for spec in r["xs_specs"]:
            spec["elevation_color_hex"] = color_overrides.get(spec["elevation_label"], spec["elevation_color_hex"])
            if spec.get("has_modification"):
                spec["modification_color_hex"] = color_overrides.get(
                    spec["modification_label"], spec["modification_color_hex"])

        xs_fig = make_cross_section_plot(xs_df_raw, r["xs_specs"], r["title"])
        first_color = r["xs_specs"][0]["elevation_color_hex"] if r["xs_specs"] else None
        axis_specs = [(xs_fig.axes[0], ["x", "y"], first_color)]
        render_chart_panel(xs_fig, key_prefix="xs_chart", base_filename="hecras_1d_cross_section",
                            axis_specs=axis_specs)
else:
    st.info("Upload an Excel file above to get started.")

