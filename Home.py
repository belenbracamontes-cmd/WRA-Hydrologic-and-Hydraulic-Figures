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

usgs_intro_page = st.Page("app_pages/7_Intro_to_USGS.py", title="Intro to USGS", icon="🗺️",
                           url_path="intro-to-usgs")

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
hecras_xs_page = st.Page("app_pages/14_HEC_RAS_Cross_Sections.py", title="Cross Sections", icon="📏",
                          url_path="cross-sections")

noaa_intro_page = st.Page("app_pages/8_Intro_to_NOAA_Tides.py", title="Intro to NOAA Tides", icon="🗺️",
                           url_path="intro-to-noaa-tides")
noaa_tides_page = st.Page("app_pages/9_NOAA_Tide_Gages.py", title="Tide Gage Data", icon="🌊",
                           url_path="noaa-tide-gages")

cimis_intro_page = st.Page("app_pages/10_Intro_to_CIMIS.py", title="Intro to CIMIS", icon="🗺️",
                            url_path="intro-to-cimis")
cimis_data_page = st.Page("app_pages/11_CIMIS_Data.py", title="CIMIS Weather Data", icon="🌦️",
                           url_path="cimis-data")

prism_intro_page = st.Page("app_pages/12_Intro_to_PRISM.py", title="Intro to PRISM", icon="🗺️",
                            url_path="intro-to-prism")
prism_data_page = st.Page("app_pages/13_PRISM_Climate_Data.py", title="PRISM Climate Data", icon="🌦️",
                           url_path="prism-data")

pg = st.navigation({
    "": [home_page],
    "USGS station tools": [usgs_intro_page, peak_flow_page, annual_flow_page, lp3_page, daily_flow_page],
    "HEC RAS figures": [hecras_1d_page, hecras_2d_page, hecras_xs_page],
    "NOAA tide tools": [noaa_intro_page, noaa_tides_page],
    "CIMIS weather tools": [cimis_intro_page, cimis_data_page],
    "PRISM climate tools": [prism_intro_page, prism_data_page],
})
pg.run()
