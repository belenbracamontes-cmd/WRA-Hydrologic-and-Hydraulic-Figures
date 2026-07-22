"""Annual Peak Flow Viewer -- Streamlit page.

Ported from the original ipywidgets GUI. Differences from the notebook
version:
  - Sidebar widgets replace ipywidgets controls.
  - "Run" fetches + caches USGS data in session_state so tweaking display
    options (log scale, break point, panel ratio) doesn't re-hit the network.
  - The tkinter "Save SVG" file-dialog button is replaced with a browser
    download button (a native file dialog can't run on a web server).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, TERRACOTA, OCEAN_BLUE
from core.peak_flow import (
    fetch_data,
    compute_return_periods,
    build_df_full,
    make_plot,
    return_period_table,
    full_record_table,
)
from core.view_source import render_view_source
from core.export import render_figure_download

st.set_page_config(page_title="Peak Flow Viewer", page_icon="📈", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch_and_compute(station_id):
    return compute_return_periods(fetch_data(station_id))


logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Annual Peak Flow Viewer</h1>",
        unsafe_allow_html=True,
    )
    st.caption("USGS annual peak-flow bar chart with return-period bands.")

with st.sidebar:
    st.header("Station 1")
    s1_id = st.text_input("Station ID", placeholder="e.g. 11113000", key="s1_id")
    s1_color = st.color_picker("Color", TERRACOTA, key="s1_color")
    s1_label = st.text_input("Label (optional)", key="s1_label",
                              placeholder="Station 1 name")

    st.divider()
    compare = st.checkbox("Compare a second station", key="compare")
    s2_id, s2_color, s2_label = "", OCEAN_BLUE, ""
    if compare:
        st.subheader("Station 2")
        s2_id = st.text_input("Station ID", placeholder="e.g. 11109000", key="s2_id")
        s2_color = st.color_picker("Color", OCEAN_BLUE, key="s2_color")
        s2_label = st.text_input("Label (optional)", key="s2_label",
                                  placeholder="Station 2 name")

    st.divider()
    title = st.text_input("Chart title (optional)", key="chart_title",
                           placeholder="e.g. Santa Ynez River at Baptism Creek")
    use_log = st.checkbox("Log scale (bottom panel)", value=True, key="use_log")
    break_val = st.slider("Break point (cfs)", 1000, 100000, 15000, step=1000,
                          key="break_val")
    axis_ratio = st.slider("Top panel share", 0.1, 0.9, 0.6, step=0.05,
                           key="axis_ratio")

    run = st.button("Run", type="primary", use_container_width=True)

if run:
    if not s1_id.strip():
        st.error("Enter a Station ID for Station 1.")
        st.stop()

    datasets = []
    try:
        with st.spinner(f"Fetching station {s1_id}..."):
            df1 = cached_fetch_and_compute(s1_id.strip())
        datasets.append({
            "df": df1,
            "df_full": build_df_full(df1),
            "station_id": s1_id.strip(),
            "base_color": s1_color,
            "label": s1_label.strip(),
            "n": len(df1),
        })

        if compare and s2_id.strip():
            with st.spinner(f"Fetching station {s2_id}..."):
                df2 = cached_fetch_and_compute(s2_id.strip())
            datasets.append({
                "df": df2,
                "df_full": build_df_full(df2),
                "station_id": s2_id.strip(),
                "base_color": s2_color,
                "label": s2_label.strip(),
                "n": len(df2),
            })
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.stop()

    st.session_state["pf_datasets"] = datasets
    st.session_state["pf_settings"] = dict(
        title=title, use_log=use_log, break_val=break_val, axis_ratio=axis_ratio
    )

if "pf_datasets" in st.session_state:
    datasets = st.session_state["pf_datasets"]
    settings = st.session_state["pf_settings"]

    fig = make_plot(
        datasets,
        settings["use_log"],
        settings["break_val"],
        settings["title"],
        settings["axis_ratio"],
    )
    st.pyplot(fig, use_container_width=True)

    render_figure_download(fig, "peak_flow_chart", key_prefix="pfv_chart")

    for d in datasets:
        name = d["label"] or f"Station {d['station_id']}"
        n = d["n"]
        max_row = d["df"].loc[d["df"]["peak_va"].idxmax()]

        st.subheader(name)
        st.write(
            f"**n = {n} years** — Max flow on record: **{max_row['peak_va']:,.0f} cfs** "
            f"(WY{int(max_row['year'])}, {pd.to_datetime(max_row['peak_dt']).date()})"
        )

        st.table(return_period_table(d["df"], n))

        with st.expander("Full peak-flow record"):
            display_df = full_record_table(d["df"])
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            csv_bytes = display_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                f"Download {name} data as CSV",
                data=csv_bytes,
                file_name=f"{d['station_id']}_peak_flow.csv",
                mime="text/csv",
                key=f"csv_{d['station_id']}",
            )
else:
    st.info("Enter a station ID in the sidebar and click **Run** to get started.")

st.divider()
render_view_source(__file__)
