"""Log-Pearson Type III Flood Frequency Analysis -- Streamlit page.

Ported from a tkinter/ipywidgets notebook GUI (Bulletin 17C / standard LP3
method, Wilson-Hilferty quantiles, Kite (1977) variance). The math functions
in core/lp3_analysis.py are unchanged from the original -- only the GUI
layer and file-save mechanism were converted.

Differences from the notebook version:
  - Sidebar widgets replace ipywidgets controls.
  - Single-station only -- no second-station comparison.
  - Design return periods are no longer user-selectable; every run tabulates
    the full standard set through 1000-yr (see core.lp3_analysis.RP_ALL).
  - An optional "Water years to consider" range slider lets you restrict the
    LP3 fit to a subset of the station's period of record.
  - "Run LP3" fetches + caches USGS data in session_state.
  - The tkinter "Save SVG" file-dialog buttons (plot and table) are replaced
    with browser download buttons.
  - The logo uses the existing assets/logo.png placeholder mechanism
    (same as the other two pages) -- drop your logo file in later.
"""

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, TERRACOTA
from core.view_source import render_view_source
from core.export import render_figure_download
from core.lp3_analysis import (
    fetch_usgs_peaks,
    make_lp3_plot,
    lp3_params_table,
    build_table_figure,
    RP_ALL,
)

st.set_page_config(page_title="LP3 Flood Frequency", page_icon="📉", layout="wide")

_CURRENT_YEAR = dt.date.today().year


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch_peaks(station_id):
    return fetch_usgs_peaks(station_id)


logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Log-Pearson Type III Flood Frequency Analysis</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Bulletin 17C / standard LP3 method. Produces a probability plot matching USGS Peakfq / Figure 10-13 style.")

with st.sidebar:
    st.header("Station")
    s1_id = st.text_input("Station ID", placeholder="e.g. 11113000", key="lp3_s1_id")
    s1_color = st.color_picker("Color", TERRACOTA, key="lp3_s1_color")
    s1_label = st.text_input("Label (optional)", key="lp3_s1_label",
                              placeholder="Station name")

    st.divider()
    title = st.text_input("Title (optional)", key="lp3_title",
                          placeholder="e.g. Arkansas R. at Pueblo State Park")
    show_ci = st.checkbox("Show 2.5%/97.5% confidence limits", value=True, key="lp3_show_ci")

    st.divider()
    custom_years = st.checkbox("Water years to consider (optional)", key="lp3_custom_years")
    year_range = None
    if custom_years:
        year_range = st.slider(
            "Water year range", min_value=1900, max_value=_CURRENT_YEAR + 1,
            value=(1900, _CURRENT_YEAR + 1), key="lp3_year_range",
        )
        st.caption("Only peak flows within this range are used in the LP3 fit.")

    run = st.button("Run LP3", type="primary", use_container_width=True)

if run:
    if not s1_id.strip():
        st.error("Enter a Station ID.")
        st.stop()

    datasets = []
    try:
        sid1 = s1_id.strip()
        with st.spinner(f"Fetching peak flows for station {sid1}..."):
            df1 = cached_fetch_peaks(sid1)

        if year_range:
            df1 = df1[(df1["year"] >= year_range[0]) & (df1["year"] <= year_range[1])]
            if df1.empty:
                st.error(
                    f"No peak-flow data for station {sid1} in water years "
                    f"{year_range[0]}–{year_range[1]}. Widen the range and try again."
                )
                st.stop()

        if len(df1) < 10:
            st.warning(
                f"Station {sid1} has only {len(df1)} years of peak-flow "
                f"record. LP3 skew estimates are unreliable with fewer than "
                f"~10 years -- results shown, but treat with caution."
            )
        datasets.append({
            "peak_va": df1["peak_va"],
            "station_id": sid1,
            "label": s1_label.strip(),
            "color": s1_color,
        })
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.stop()

    st.session_state["lp3_datasets"] = datasets
    st.session_state["lp3_settings"] = dict(title=title, show_ci=show_ci)

if "lp3_datasets" in st.session_state:
    datasets = st.session_state["lp3_datasets"]
    settings = st.session_state["lp3_settings"]

    fig, summary = make_lp3_plot(
        datasets,
        custom_title=settings["title"],
        show_ci=settings["show_ci"],
        rp_list=RP_ALL,
    )

    st.pyplot(fig, use_container_width=True)

    render_figure_download(fig, "lp3_flood_frequency", key_prefix="lp3_plot", label="Download plot")

    st.subheader("LP3 Parameters (Bulletin 17C / Wilson-Hilferty)")
    st.dataframe(lp3_params_table(datasets), use_container_width=True, hide_index=True)

    st.subheader("Design Flows — LP3 with 2.5%/97.5% Confidence Limits")
    for station_title, rows in summary.items():
        st.markdown(f"**{station_title}**")
        df_tbl = pd.DataFrame(rows)
        st.dataframe(df_tbl, use_container_width=True, hide_index=True)

    table_fig = build_table_figure(summary)
    render_figure_download(
        table_fig, "lp3_design_flow_tables", key_prefix="lp3_table",
        label="Download design-flow tables",
    )
else:
    st.info("Enter a station ID in the sidebar and click **Run LP3** to get started.")

st.divider()
render_view_source(__file__)
