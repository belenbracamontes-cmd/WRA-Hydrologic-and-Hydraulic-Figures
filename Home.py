"""Entry point / sectioned sidebar navigation for the WRA Hydrology Tools
web app.

Run with:
    streamlit run Home.py

Uses st.navigation() with grouped sections so the sidebar shows labeled
headers ("USGS station tools", "HEC RAS figures") instead of a flat page
list. Tool pages live in app_pages/ rather than pages/ -- Streamlit
unconditionally falls back to its legacy auto-discovery behavior (ignoring
st.navigation entirely) whenever a folder literally named pages/ exists next
to the entrypoint, regardless of what this script does.

Only ONE st.set_page_config() call is allowed per run, so it lives here --
individual page files must not call it themselves.
"""

import streamlit as st

st.set_page_config(
    page_title="WRA Hydrology Tools",
    page_icon="💧",
    layout="wide",
)

home_page = st.Page("app_pages/0_Home.py", title="Home", icon="💧", default=True, url_path="home")

peak_flow_page = st.Page("app_pages/1_Peak_Flow_Viewer.py", title="Peak Flow Viewer", icon="📈",
                          url_path="peak-flow-viewer")
annual_flow_page = st.Page("app_pages/2_Annual_Flow_Chart.py", title="Annual Flow Chart", icon="📊",
                            url_path="annual-flow-chart")
lp3_page = st.Page("app_pages/3_LP3_Flood_Frequency.py", title="LP3 Flood Frequency", icon="📉",
                    url_path="lp3-flood-frequency")
daily_flow_page = st.Page("app_pages/4_Daily_Flow_Duration_Analysis.py",
                           title="Daily Flow & Duration Analysis", icon="🌊",
                           url_path="daily-flow-duration-analysis")

hecras_1d_page = st.Page("app_pages/5_HEC_RAS_1D_Figures.py", title="1D Figures", icon="📐",
                          url_path="hecras-1d-figures")
hecras_2d_page = st.Page("app_pages/6_HEC_RAS_2D_Figures.py", title="2D Figures", icon="🗺️",
                          url_path="hecras-2d-figures")

pg = st.navigation({
    "": [home_page],
    "USGS station tools": [peak_flow_page, annual_flow_page, lp3_page, daily_flow_page],
    "HEC RAS figures": [hecras_1d_page, hecras_2d_page],
})
pg.run()
