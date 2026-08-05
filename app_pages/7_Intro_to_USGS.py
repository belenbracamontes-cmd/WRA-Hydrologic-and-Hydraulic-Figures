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

"Find a station" lets you check stations from the search results table and
add them to a running selection, each with its own color (default
terracotta). Selected stations render as larger highlighted points on the
map; a "Zoom" button per station recenters the map on it, and an "only show
selected" toggle can hide the full nationwide cloud entirely.

A Standard/Satellite/Terrain map-type switcher was attempted (Esri's free
World Imagery/Topo tiles, since Google's terms of service don't allow
pulling their map tiles outside their own paid API) but dropped: both ways
of adding a custom basemap through st.pydeck_chart hit confirmed bugs in
Streamlit's bundled deck.gl component -- a custom map_style (dict or
string) throws a client-side TypeError, and a TileLayer data-layer
workaround defaults to treating the raster tiles as GeoJSON. Only the
single reliable "Standard" map ships for now.
"""

import sys
from pathlib import Path

import pydeck as pdk
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, TERRACOTA, TERRACOTA_SHADE
from core.view_source import render_view_source
from core.usgs_station_map import fetch_all_active_streamgages, hex_to_rgba

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
    box underneath to check off stations and add them to the map in their own color. For deeper
    station-by-station exploration, USGS's own
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


all_sites = st.session_state.get("usgs_all_sites")
if all_sites is None:
    all_sites, failed_states = _cached_fetch_all_streamgages()
    st.session_state["usgs_all_sites"] = all_sites
    st.session_state["usgs_failed_states"] = failed_states
else:
    failed_states = st.session_state.get("usgs_failed_states", [])

st.subheader(f"📍 {len(all_sites):,} active streamgages nationwide")
if failed_states:
    st.caption(f"Note: couldn't fetch data for {', '.join(failed_states)} (skipped, not fatal to the rest).")

# ── Selection state ─────────────────────────────────────────────────────────
if "usgs_selected" not in st.session_state:
    st.session_state["usgs_selected"] = []  # list of site_no strings
if "usgs_map_view" not in st.session_state:
    st.session_state["usgs_map_view"] = {"lat": 39.5, "lon": -98.35, "zoom": 3.2}

selected_site_nos = st.session_state["usgs_selected"]


def _color_key(site_no):
    return f"usgs_color_{site_no}"


def _station_row(site_no):
    match = all_sites[all_sites["site_no"] == site_no]
    return match.iloc[0] if not match.empty else None


# ── Map display controls ────────────────────────────────────────────────────
only_selected = st.checkbox("Only show selected stations", key="usgs_only_selected",
                             disabled=not selected_site_nos)

layers = []

if not (only_selected and selected_site_nos):
    base_layer = pdk.Layer(
        "ScatterplotLayer",
        data=all_sites,
        get_position=["dec_long_va", "dec_lat_va"],
        get_fill_color=hex_to_rgba(TERRACOTA_SHADE, alpha=140),
        get_radius=1,
        radius_min_pixels=2,
        radius_max_pixels=6,
        pickable=True,
        auto_highlight=True,
    )
    layers.append(base_layer)

if selected_site_nos:
    sel_rows = []
    for site_no in selected_site_nos:
        row = _station_row(site_no)
        if row is None:
            continue
        color_hex = st.session_state.get(_color_key(site_no), TERRACOTA)
        sel_rows.append({
            "site_no": row["site_no"], "station_nm": row["station_nm"],
            "dec_lat_va": row["dec_lat_va"], "dec_long_va": row["dec_long_va"],
            "drain_area_va": row["drain_area_va"],
            "color": hex_to_rgba(color_hex, alpha=235),
        })
    if sel_rows:
        highlight_layer = pdk.Layer(
            "ScatterplotLayer",
            data=sel_rows,
            get_position=["dec_long_va", "dec_lat_va"],
            get_fill_color="color",
            get_line_color=[255, 255, 255],
            line_width_min_pixels=1,
            stroked=True,
            get_radius=1,
            radius_min_pixels=6,
            radius_max_pixels=14,
            pickable=True,
            auto_highlight=True,
        )
        layers.append(highlight_layer)

view = st.session_state["usgs_map_view"]
view_state = pdk.ViewState(latitude=view["lat"], longitude=view["lon"], zoom=view["zoom"], pitch=0)
tooltip = {
    "html": "<b>{station_nm}</b><br/>Site No: {site_no}<br/>Drainage area: {drain_area_va} sq mi",
    "style": {"backgroundColor": TERRACOTA_SHADE, "color": "white"},
}
deck = pdk.Deck(layers=layers, initial_view_state=view_state, tooltip=tooltip)

# Force a full remount (not just a prop update) whenever anything that
# should visibly change the map changes -- deck.gl's initial_view_state and
# per-point colors aren't reliably re-applied to an already-mounted
# component across Streamlit reruns otherwise.
colors_sig = tuple(sorted((s, st.session_state.get(_color_key(s), TERRACOTA)) for s in selected_site_nos))
map_key = (f"usgs_map_{round(view['lat'], 4)}_{round(view['lon'], 4)}_{view['zoom']}_"
           f"{only_selected}_{hash(colors_sig)}")
st.pydeck_chart(deck, use_container_width=True, height=600, key=map_key)

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

st.caption(f"{len(filtered):,} of {len(all_sites):,} stations shown -- check a row and click "
           "\"Add checked stations to map\" to add it to your selection below.")

display_df = filtered[["site_no", "station_nm", "dec_lat_va", "dec_long_va", "drain_area_va", "huc_cd"]].copy()
display_df.insert(0, "Add", display_df["site_no"].isin(selected_site_nos))
display_df = display_df.rename(columns={
    "site_no": "Site No", "station_nm": "Station Name",
    "dec_lat_va": "Latitude", "dec_long_va": "Longitude",
    "drain_area_va": "Drainage Area (sq mi)", "huc_cd": "HUC Code",
})

edited = st.data_editor(
    display_df,
    column_config={"Add": st.column_config.CheckboxColumn(help="Check to add this station to the map")},
    disabled=[c for c in display_df.columns if c != "Add"],
    hide_index=True, use_container_width=True, height=350, key="usgs_search_editor",
)

if st.button("➕ Add checked stations to map", key="usgs_add_checked"):
    newly_checked = edited[edited["Add"]]["Site No"].tolist()
    added = 0
    for site_no in newly_checked:
        if site_no not in selected_site_nos:
            selected_site_nos.append(site_no)
            added += 1
    if added:
        st.success(f"Added {added} station(s) to the map.")
        st.rerun()
    else:
        st.info("Nothing new to add -- those stations are already selected.")

# A narrowed search (e.g. an exact site number) gets quick one-click "Add"
# buttons too, for the common case of adding a single known station without
# needing to find its checkbox in a big table.
if 0 < len(filtered) <= 15:
    st.caption("Quick add:")
    for _, row in filtered.iterrows():
        site_no = row["site_no"]
        qc1, qc2 = st.columns([5, 1])
        with qc1:
            st.write(f"{row['station_nm']} ({site_no})")
        with qc2:
            already = site_no in selected_site_nos
            if st.button("Added ✓" if already else "➕ Add", key=f"usgs_quickadd_{site_no}",
                         disabled=already):
                selected_site_nos.append(site_no)
                st.rerun()

st.divider()
st.subheader(f"🎯 Selected stations ({len(selected_site_nos)})")
if not selected_site_nos:
    st.info("No stations selected yet. Check some off in the search results above.")
else:
    if st.button("Clear all", key="usgs_clear_all"):
        st.session_state["usgs_selected"] = []
        st.rerun()

    for site_no in list(selected_site_nos):
        row = _station_row(site_no)
        if row is None:
            continue
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([4, 1.3, 1, 1])
            with c1:
                st.markdown(f"**{row['station_nm']}**  \nSite No: {row['site_no']}")
            with c2:
                st.color_picker("Color", TERRACOTA, key=_color_key(site_no), label_visibility="collapsed")
            with c3:
                if st.button("🔍 Zoom", key=f"usgs_zoom_{site_no}"):
                    st.session_state["usgs_map_view"] = {
                        "lat": float(row["dec_lat_va"]), "lon": float(row["dec_long_va"]), "zoom": 11.0,
                    }
                    st.rerun()
            with c4:
                if st.button("✕ Remove", key=f"usgs_remove_{site_no}"):
                    st.session_state["usgs_selected"] = [s for s in selected_site_nos if s != site_no]
                    st.rerun()

st.divider()
render_view_source(__file__)
