"""Log-Pearson Type III Flood Frequency Analysis -- Streamlit page.

Ported from a tkinter/ipywidgets notebook GUI (Bulletin 17C / standard LP3
method, Wilson-Hilferty quantiles, Kite (1977) variance). The math functions
in core/lp3_analysis.py are unchanged from the original -- only the GUI
layer and file-save mechanism were converted.

Differences from the notebook version:
  - Sidebar widgets replace ipywidgets controls.
  - "Run LP3" fetches + caches USGS data in session_state.
  - The tkinter "Save SVG" file-dialog buttons (plot and table) are replaced
    with browser download buttons.
  - The logo uses the existing assets/logo.png placeholder mechanism
    (same as the other two pages) -- drop your logo file in later.
"""

import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK
from core.view_source import render_view_source
from core.lp3_analysis import (
    fetch_usgs_peaks,
    make_lp3_plot,
    lp3_params_table,
    build_table_figure,
    RP_STD,
    RP_EXT,
)

st.set_page_config(page_title="LP3 Flood Frequency", page_icon="📉", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch_peaks(station_id):
    return fetch_usgs_peaks(station_id)


logo = logo_path_if_present()
col_logo, col_title = st.columns([1, 6])
with col_logo:
    if logo:
        st.image(str(logo), width=70)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Log-Pearson Type III Flood Frequency Analysis</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Bulletin 17C / standard LP3 method. Produces a probability plot matching USGS Peakfq / Figure 10-13 style.")

with st.sidebar:
    st.header("Station 1")
    s1_id = st.text_input("Station ID", placeholder="e.g. 11113000", key="lp3_s1_id")
    s1_color = st.color_picker("Color", "#c0392b", key="lp3_s1_color")
    s1_label = st.text_input("Label (optional)", key="lp3_s1_label",
                              placeholder="Station 1 name")

    st.divider()
    compare = st.checkbox("Compare a second station", key="lp3_compare")
    s2_id, s2_color, s2_label = "", "#2980b9", ""
    if compare:
        st.subheader("Station 2")
        s2_id = st.text_input("Station ID", placeholder="e.g. 11109000", key="lp3_s2_id")
        s2_color = st.color_picker("Color", "#2980b9", key="lp3_s2_color")
        s2_label = st.text_input("Label (optional)", key="lp3_s2_label",
                                  placeholder="Station 2 name")

    st.divider()
    title = st.text_input("Title (optional)", key="lp3_title",
                          placeholder="e.g. Arkansas R. at Pueblo State Park")
    show_ci = st.checkbox("Show 2.5%/97.5% confidence limits", value=True, key="lp3_show_ci")

    st.divider()
    st.write("**Design return periods to tabulate:**")
    selected_rps = []
    std_cols = st.columns(len(RP_STD))
    for col, rp in zip(std_cols, RP_STD):
        with col:
            if st.checkbox(f"{rp}-yr", value=True, key=f"lp3_rp_{rp}"):
                selected_rps.append(rp)
    st.caption("⚠️ Extrapolations (use with caution):")
    ext_cols = st.columns(len(RP_EXT))
    for col, rp in zip(ext_cols, RP_EXT):
        with col:
            if st.checkbox(f"{rp}-yr", value=False, key=f"lp3_rp_{rp}"):
                selected_rps.append(rp)

    run = st.button("Run LP3", type="primary", use_container_width=True)

if run:
    if not s1_id.strip():
        st.error("Enter a Station ID for Station 1.")
        st.stop()
    if not selected_rps:
        selected_rps = RP_STD

    datasets = []
    try:
        sid1 = s1_id.strip()
        with st.spinner(f"Fetching peak flows for station {sid1}..."):
            df1 = cached_fetch_peaks(sid1)
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

        if compare and s2_id.strip():
            sid2 = s2_id.strip()
            with st.spinner(f"Fetching peak flows for station {sid2}..."):
                df2 = cached_fetch_peaks(sid2)
            datasets.append({
                "peak_va": df2["peak_va"],
                "station_id": sid2,
                "label": s2_label.strip(),
                "color": s2_color,
            })
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.stop()

    st.session_state["lp3_datasets"] = datasets
    st.session_state["lp3_settings"] = dict(
        title=title, show_ci=show_ci, selected_rps=selected_rps,
    )

if "lp3_datasets" in st.session_state:
    datasets = st.session_state["lp3_datasets"]
    settings = st.session_state["lp3_settings"]

    fig, summary = make_lp3_plot(
        datasets,
        custom_title=settings["title"],
        show_ci=settings["show_ci"],
        rp_list=settings["selected_rps"],
    )

    st.pyplot(fig, use_container_width=True)

    svg_buf = BytesIO()
    fig.savefig(svg_buf, format="svg", bbox_inches="tight")
    st.download_button(
        "Download plot as SVG",
        data=svg_buf.getvalue(),
        file_name="lp3_flood_frequency.svg",
        mime="image/svg+xml",
    )

    st.subheader("LP3 Parameters (Bulletin 17C / Wilson-Hilferty)")
    st.dataframe(lp3_params_table(datasets), use_container_width=True, hide_index=True)

    st.subheader("Design Flows — LP3 with 2.5%/97.5% Confidence Limits")
    for station_title, rows in summary.items():
        st.markdown(f"**{station_title}**")
        df_tbl = pd.DataFrame(rows)

        def _rp_val(s):
            try:
                return float(str(s).replace("-yr", "").replace(",", ""))
            except Exception:
                return 0

        def _highlight_extrapolated(row):
            is_extrap = _rp_val(row["Return Period"]) > 100
            return ["background-color: #fff8e1" if is_extrap else "" for _ in row]

        st.dataframe(
            df_tbl.style.apply(_highlight_extrapolated, axis=1),
            use_container_width=True, hide_index=True,
        )
    st.caption("Rows with RP > 100-yr (highlighted) are extrapolations beyond the period of record.")

    table_fig = build_table_figure(summary)
    table_svg_buf = BytesIO()
    table_fig.savefig(table_svg_buf, format="svg", bbox_inches="tight")
    st.download_button(
        "Download design-flow tables as SVG",
        data=table_svg_buf.getvalue(),
        file_name="lp3_design_flow_tables.svg",
        mime="image/svg+xml",
    )
else:
    st.info("Enter a station ID in the sidebar and click **Run LP3** to get started.")

st.divider()
render_view_source(__file__)
