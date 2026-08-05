"""Intro to USGS -- Streamlit page.

A nationwide map of active USGS streamgages (~11-12k sites), similar in
spirit to the station map on USGS StreamStats. Meant as an orientation page
for anyone new to USGS data before they dive into the station-specific
tools elsewhere on this site.

Every other tool page fetches data for ONE station at a time by site
number; this page instead pulls active-site metadata (location, name,
drainage area) for every state/territory and combines it into one
dataset, since NWIS's site service requires a geographic filter per
request and won't return "every site" in a single call.

The first-ever load (across all users -- st.cache_data's cache is shared
server-side) takes roughly a minute since it's ~56 sequential state/
territory requests; every load after that is served from cache until it
expires (24h) or the server restarts.
"""

import sys
from pathlib import Path

import pydeck as pdk
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, TERRACOTA_SHADE
from core.view_source import render_view_source
from core.usgs_station_map import fetch_all_active_streamgages

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Intro to USGS Streamgages</h1>",
        unsafe_allow_html=True,
    )
    st.caption("A nationwide look at the active USGS streamgage network before you dive into the "
               "station-specific tools in the sidebar.")

st.markdown(
    """
    The U.S. Geological Survey operates a nationwide network of **streamgages** that measure
    river and stream conditions -- stage, discharge, and more -- in near real time. Every gauge
    has a unique **site number** (8-15 digits) and reports to USGS's National Water Information
    System (NWIS), the same public API every tool on this site pulls from when you type in a
    station ID.

    Hover any point on the map below to see a station's name and site number, or use the search
    box underneath to look one up directly. For deeper station-by-station exploration, USGS's own
    [National Water Dashboard](https://dashboard.waterdata.usgs.gov/) and
    [NWIS Mapper](https://maps.waterdata.usgs.gov/mapper/) offer the same kind of view this page
    does, with more detail once you've found a site you care about.
    """
)

st.divider()


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_fetch_all_streamgages():
    progress_bar = st.progress(0.0, text="Fetching active USGS streamgages nationwide...")

    def _on_progress(done, total, state_cd):
        progress_bar.progress(done / total, text=f"Fetching {state_cd} ({done}/{total})...")

    all_sites, failed_states = fetch_all_active_streamgages(progress_callback=_on_progress)
    progress_bar.empty()
    return all_sites, failed_states


all_sites, failed_states = _cached_fetch_all_streamgages()

st.subheader(f"📍 {len(all_sites):,} active streamgages nationwide")
if failed_states:
    st.caption(f"Note: couldn't fetch data for {', '.join(failed_states)} (skipped, not fatal to the rest).")

view_state = pdk.ViewState(latitude=39.5, longitude=-98.35, zoom=3.2, pitch=0)
layer = pdk.Layer(
    "ScatterplotLayer",
    data=all_sites,
    get_position=["dec_long_va", "dec_lat_va"],
    get_fill_color=[10, 89, 106, 160],  # WRA Ocean Blue Shade, semi-transparent
    get_radius=1,
    radius_min_pixels=2,
    radius_max_pixels=6,
    pickable=True,
    auto_highlight=True,
)
tooltip = {
    "html": "<b>{station_nm}</b><br/>Site No: {site_no}<br/>Drainage area: {drain_area_va} sq mi",
    "style": {"backgroundColor": TERRACOTA_SHADE, "color": "white"},
}
deck = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip)
st.pydeck_chart(deck, use_container_width=True, height=600)

st.divider()
st.subheader("Find a station")
query = st.text_input("Search by station name or site number", key="usgs_search",
                       placeholder="e.g. Russian River, or 11463500")

if query.strip():
    q = query.strip().lower()
    filtered = all_sites[
        all_sites["station_nm"].str.lower().str.contains(q, na=False)
        | all_sites["site_no"].str.contains(q, na=False)
    ]
else:
    filtered = all_sites

st.caption(f"{len(filtered):,} of {len(all_sites):,} stations shown")
st.dataframe(
    filtered[["site_no", "station_nm", "dec_lat_va", "dec_long_va", "drain_area_va", "huc_cd"]]
    .rename(columns={
        "site_no": "Site No", "station_nm": "Station Name",
        "dec_lat_va": "Latitude", "dec_long_va": "Longitude",
        "drain_area_va": "Drainage Area (sq mi)", "huc_cd": "HUC Code",
    }),
    use_container_width=True, hide_index=True, height=350,
)

st.divider()
render_view_source(__file__)
