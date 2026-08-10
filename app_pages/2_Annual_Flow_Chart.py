"""Annual Peak Flow & Average Flow Chart Generator -- Streamlit page.

Ported from a tkinter/ipywidgets notebook GUI (WRA -- Riverscapes &
Shorelines Team). Differences from the notebook version:
  - Inputs live in the main body (numbered sections), matching the layout
    convention every other tool page in the app uses -- not a sidebar.
  - "Generate Chart" fetches + caches USGS data in session_state so tweaking
    display options doesn't re-hit the network.
  - The tkinter "Save SVG" file-dialog button is replaced with a browser
    download button.
  - The logo is loaded from assets/logo.png via core.branding (same
    placeholder mechanism as the Peak Flow Viewer page) instead of an
    embedded base64 string -- drop your logo file in later.
  - The on-chart stats box now shows both Mean Peak Flow and Max Peak Flow
    (previously mean only).
"""

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import (
    logo_path_if_present, BRAND_DARK, FIELD_GREEN_SHADE, FIELD_GREEN_TINT,
)
from core.style_options import render_chart_panel, render_data_color_pickers
from core.ui_helpers import toggle_button
from core.annual_flow_chart import (
    fetch_peak_flows,
    fetch_annual_avg_flow,
    fetch_station_name,
    build_annual_flow_chart,
    summary_table,
    WRA_PEAK_BLUE,
    WRA_AVG_CYAN,
)

_CURRENT_YEAR = dt.date.today().year


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch_peak(site_no, start_wy, end_wy):
    return fetch_peak_flows(site_no, start_wy, end_wy)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch_avg(site_no, start_wy, end_wy):
    return fetch_annual_avg_flow(site_no, start_wy, end_wy)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch_name(site_no):
    return fetch_station_name(site_no)


logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Annual Peak Flow & Average Flow Chart Generator</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Dual-axis grouped bar chart (Balance Hydrologics \"Figure 3\" style), pulled live from USGS.")

st.divider()
st.subheader("1. Station(s)")

# Colors start at these WRA defaults and stay that way until the user
# customizes them in the "Customize & export" panel below, once results
# exist -- no separate color choice up here, so there's exactly one place
# in the whole page where chart color gets decided.
c1, c2 = st.columns(2)
with c1:
    s1_id = st.text_input("Station 1 ID", value="11164500", key="afg_s1_id")
with c2:
    s1_label = st.text_input("Label (optional)", key="afg_s1_label",
                              placeholder="e.g. San Francisquito Ck")
s1_peak_color, s1_avg_color = WRA_PEAK_BLUE, WRA_AVG_CYAN

compare = toggle_button("+ Compare a second station", "− Remove second station",
                         key="afg_compare")
s2_id, s2_peak_color, s2_avg_color, s2_label = "", FIELD_GREEN_SHADE, FIELD_GREEN_TINT, ""
if compare:
    c1, c2 = st.columns(2)
    with c1:
        s2_id = st.text_input("Station 2 ID", placeholder="e.g. 11143000", key="afg_s2_id")
    with c2:
        s2_label = st.text_input("Label (optional)", key="afg_s2_label",
                                  placeholder="Station 2 name")

st.subheader("2. Options")
custom_range = st.checkbox(
    "Customize water year range (default: show all available data)",
    key="afg_custom_range",
)
start_wy, end_wy = 1900, _CURRENT_YEAR + 1
if custom_range:
    c1, c2 = st.columns(2)
    with c1:
        start_wy = st.number_input("Start WY", min_value=1900, max_value=2100,
                                   value=1900, key="afg_start_wy")
    with c2:
        end_wy = st.number_input("End WY", min_value=1900, max_value=2100,
                                 value=_CURRENT_YEAR + 1, key="afg_end_wy")

c1, c2 = st.columns(2)
with c1:
    title = st.text_input("Title (optional)", key="afg_title",
                          placeholder="e.g. San Francisquito Creek at Stanford")
with c2:
    org = st.text_input("Organization", value="WRA, Inc.", key="afg_org")

run = st.button("Generate Chart", type="primary")

if run:
    if not s1_id.strip():
        st.error("Enter a Station ID for Station 1.")
        st.stop()

    datasets = []
    try:
        sid1 = s1_id.strip()
        with st.spinner(f"Fetching peak flows for station {sid1}..."):
            peak1 = cached_fetch_peak(sid1, int(start_wy), int(end_wy))
        if peak1.empty:
            st.error(
                f"No peak flow data found for Station {sid1} in "
                f"WY{start_wy}–{end_wy}. Check the station ID and year range."
            )
            st.stop()
        with st.spinner(f"Fetching annual average flows for station {sid1}..."):
            avg1 = cached_fetch_avg(sid1, int(start_wy), int(end_wy))
        name1 = cached_fetch_name(sid1)

        datasets.append({
            "peak_df": peak1,
            "avg_df": avg1,
            "station_id": sid1,
            "station_name": name1,
            "peak_color": s1_peak_color,
            "avg_color": s1_avg_color,
            "label": s1_label.strip(),
        })

        if compare and s2_id.strip():
            sid2 = s2_id.strip()
            with st.spinner(f"Fetching peak flows for station {sid2}..."):
                peak2 = cached_fetch_peak(sid2, int(start_wy), int(end_wy))
            with st.spinner(f"Fetching annual average flows for station {sid2}..."):
                avg2 = cached_fetch_avg(sid2, int(start_wy), int(end_wy))
            name2 = cached_fetch_name(sid2)
            datasets.append({
                "peak_df": peak2,
                "avg_df": avg2,
                "station_id": sid2,
                "station_name": name2,
                "peak_color": s2_peak_color,
                "avg_color": s2_avg_color,
                "label": s2_label.strip(),
            })
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.stop()

    st.session_state["afg_datasets"] = datasets
    st.session_state["afg_settings"] = dict(title=title, org=org)

if "afg_datasets" in st.session_state:
    datasets = st.session_state["afg_datasets"]
    settings = st.session_state["afg_settings"]

    def _ds_name(d):
        return d["label"] or d["station_name"] or f"Station {d['station_id']}"

    color_series = []
    for d in datasets:
        color_series.append({"label": f"{_ds_name(d)} Peak", "color": d["peak_color"]})
        color_series.append({"label": f"{_ds_name(d)} Avg", "color": d["avg_color"]})
    color_overrides = render_data_color_pickers(color_series, key_prefix="afc_chart")
    for d in datasets:
        d["peak_color"] = color_overrides.get(f"{_ds_name(d)} Peak", d["peak_color"])
        d["avg_color"] = color_overrides.get(f"{_ds_name(d)} Avg", d["avg_color"])

    fig = build_annual_flow_chart(
        datasets,
        custom_title=settings["title"],
        show_avg=True,
        organization=settings["org"] or "WRA, Inc.",
    )
    if len(datasets) > 1:
        st.caption(
            "Two stations are shown -- \"Match axis color to its data series\" "
            "uses Station 1's peak/average colors for the left/right axes."
        )
    peak_color = datasets[0]["peak_color"]
    avg_color = datasets[0]["avg_color"]
    axis_specs = [
        (fig.axes[0], ["x", "y"], peak_color),
        (fig.axes[1], ["y"], avg_color),
    ]
    render_chart_panel(fig, key_prefix="afc_chart", base_filename="annual_flow_chart",
                        axis_specs=axis_specs)

    st.subheader("Annual Flow Summary")
    st.dataframe(summary_table(datasets), use_container_width=True, hide_index=True)

    for d in datasets:
        name = d["label"] or d["station_name"] or f"Station {d['station_id']}"
        with st.expander(f"Full data for {name}"):
            merged = pd.merge(
                d["peak_df"], d["avg_df"], on="water_year", how="outer"
            ).sort_values("water_year")
            st.dataframe(merged, use_container_width=True, hide_index=True)
            csv_bytes = merged.to_csv(index=False).encode("utf-8")
            st.download_button(
                f"Download {name} data as CSV",
                data=csv_bytes,
                file_name=f"{d['station_id']}_annual_flow.csv",
                mime="text/csv",
                key=f"csv_{d['station_id']}",
            )
else:
    st.info("Enter a station ID above and click **Generate Chart** to get started.")

