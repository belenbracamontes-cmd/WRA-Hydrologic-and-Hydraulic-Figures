"""Intro to NOAA Tides -- Streamlit page.

A nationwide map of NOAA's water-level (tide gage) stations, mirroring the
"Intro to USGS" page's map/search/selection feature set. NOAA's metadata
API returns every water-level station (~300 nationwide) in a single
request -- no state-by-state chunking needed, unlike the USGS fetch.

"Find a station" narrows the list with optional State/City filters plus a
name/ID search, then a single "Add" click adds a station straight to the
map and the running selection below (no separate confirm step). Selected
stations render as larger highlighted points, each with its own color
(default terracotta); a "Zoom" button per station recenters the map, and
an "only show selected" toggle can hide the full nationwide cloud.

Like the USGS map, this uses only the "Standard" basemap -- a
Satellite/Terrain switcher was tried there and dropped after confirming
two separate bugs in Streamlit's bundled deck.gl component (a custom
map_style throws a client-side TypeError, and a TileLayer workaround
defaults to treating raster tiles as GeoJSON); the same underlying
component is used here, so the same limitation applies.
"""

import sys
from pathlib import Path

import pydeck as pdk
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, TERRACOTA, TERRACOTA_SHADE
from core.view_source import render_view_source
from core.noaa_station_map import fetch_all_tide_stations, hex_to_rgba

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Intro to NOAA Tides</h1>",
        unsafe_allow_html=True,
    )
    st.caption("A nationwide look at NOAA's water-level station network before you pull data "
               "from one on the Tide Gage Data page.")

st.markdown(
    """
    NOAA operates roughly 300 water-level (tide gage) stations nationwide as part of its
    National Water Level Observation Network (NWLON), each reporting real-time water level and
    contributing to long-term tidal datums. Every station has a unique **station ID** and feeds
    the same NOAA CO-OPS API the [Tide Gage Data](/noaa-tide-gages) page pulls from.

    Hover any point on the map below to see a station's name and ID, or use the state/city/search
    filters underneath to find and add stations to the map in their own color. For deeper
    station-by-station detail, NOAA's own
    [Tides & Currents map](https://tidesandcurrents.noaa.gov/map/) offers the same kind of view
    this page does.
    """
)

st.divider()


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_fetch_all_stations():
    return fetch_all_tide_stations()


all_stations = _cached_fetch_all_stations()

st.subheader(f"📍 {len(all_stations):,} NOAA water-level stations nationwide")

# ── Selection state ─────────────────────────────────────────────────────────
if "noaa_map_selected" not in st.session_state:
    st.session_state["noaa_map_selected"] = []  # list of station id strings
if "noaa_map_view" not in st.session_state:
    st.session_state["noaa_map_view"] = {"lat": 39.5, "lon": -98.35, "zoom": 3.2}

selected_ids = st.session_state["noaa_map_selected"]


def _color_key(station_id):
    return f"noaa_map_color_{station_id}"


def _station_row(station_id):
    match = all_stations[all_stations["id"] == station_id]
    return match.iloc[0] if not match.empty else None


# ── Map display controls ────────────────────────────────────────────────────
only_selected = st.checkbox("Only show selected stations", key="noaa_map_only_selected",
                             disabled=not selected_ids)

layers = []

if not (only_selected and selected_ids):
    base_layer = pdk.Layer(
        "ScatterplotLayer",
        data=all_stations,
        get_position=["lng", "lat"],
        get_fill_color=hex_to_rgba(TERRACOTA_SHADE, alpha=140),
        get_radius=1,
        radius_min_pixels=3,
        radius_max_pixels=8,
        pickable=True,
        auto_highlight=True,
    )
    layers.append(base_layer)

if selected_ids:
    sel_rows = []
    for station_id in selected_ids:
        row = _station_row(station_id)
        if row is None:
            continue
        color_hex = st.session_state.get(_color_key(station_id), TERRACOTA)
        sel_rows.append({
            "id": row["id"], "name": row["name"], "lat": row["lat"], "lng": row["lng"],
            "state": row["state"], "tide_type": row["tide_type"],
            "color": hex_to_rgba(color_hex, alpha=235),
        })
    if sel_rows:
        highlight_layer = pdk.Layer(
            "ScatterplotLayer",
            data=sel_rows,
            get_position=["lng", "lat"],
            get_fill_color="color",
            get_line_color=[255, 255, 255],
            line_width_min_pixels=1,
            stroked=True,
            get_radius=1,
            radius_min_pixels=7,
            radius_max_pixels=16,
            pickable=True,
            auto_highlight=True,
        )
        layers.append(highlight_layer)

view = st.session_state["noaa_map_view"]
view_state = pdk.ViewState(latitude=view["lat"], longitude=view["lon"], zoom=view["zoom"], pitch=0)
tooltip = {
    "html": "<b>{name}</b><br/>Station ID: {id}<br/>{state} — {tide_type}",
    "style": {"backgroundColor": TERRACOTA_SHADE, "color": "white"},
}
deck = pdk.Deck(layers=layers, initial_view_state=view_state, tooltip=tooltip)

# Force a full remount (not just a prop update) whenever anything that
# should visibly change the map changes -- deck.gl's initial_view_state and
# per-point colors aren't reliably re-applied to an already-mounted
# component across Streamlit reruns otherwise.
colors_sig = tuple(sorted((s, st.session_state.get(_color_key(s), TERRACOTA)) for s in selected_ids))
map_key = (f"noaa_map_{round(view['lat'], 4)}_{round(view['lon'], 4)}_{view['zoom']}_"
           f"{only_selected}_{hash(colors_sig)}")
st.pydeck_chart(deck, use_container_width=True, height=600, key=map_key)

st.divider()
st.subheader("Filter by state / city (optional)")
state_options = ["All states"] + sorted(s for s in all_stations["state"].unique() if s)

c1, c2 = st.columns(2)
with c1:
    state_choice = st.selectbox("State", state_options, key="noaa_map_state_filter")
with c2:
    city_query = st.text_input("City", key="noaa_map_city_filter",
                                placeholder="e.g. Charleston (matches the station name)")

filtered = all_stations
if state_choice != "All states":
    filtered = filtered[filtered["state"] == state_choice]
if city_query.strip():
    filtered = filtered[filtered["name"].str.contains(city_query.strip(), case=False, na=False)]

st.divider()
st.subheader("Find a station")
query = st.text_input("Search by station name or ID", key="noaa_map_search",
                       placeholder="e.g. Charleston, or 9414290")

if query.strip():
    q = query.strip().lower()
    filtered = filtered[
        filtered["name"].str.lower().str.contains(q, na=False)
        | filtered["id"].str.contains(q, na=False)
    ]

MAX_LISTED = 50
st.caption(f"{len(filtered):,} of {len(all_stations):,} stations match your filters.")

if len(filtered) == 0:
    st.info("No stations match -- try loosening the state/city/search filters above.")
elif len(filtered) > MAX_LISTED:
    st.info(f"That's {len(filtered):,} stations -- narrow with the State/City filters or the search box "
             f"above to list them here (up to {MAX_LISTED} at a time).")
else:
    for _, row in filtered.iterrows():
        station_id = row["id"]
        rc1, rc2, rc3 = st.columns([4, 3, 1.2])
        with rc1:
            st.write(f"**{row['name']}**  \n{station_id}")
        with rc2:
            st.caption(f"{row['state'] or '—'} · {row['tide_type'] or '—'} tide")
        with rc3:
            already = station_id in selected_ids
            if st.button("Added ✓" if already else "➕ Add", key=f"noaa_map_add_{station_id}",
                         disabled=already):
                selected_ids.append(station_id)
                st.rerun()

st.divider()
st.subheader(f"🎯 Selected stations ({len(selected_ids)})")
if not selected_ids:
    st.info("No stations selected yet. Click \"Add\" on a station above to get started.")
else:
    if st.button("Clear all", key="noaa_map_clear_all"):
        st.session_state["noaa_map_selected"] = []
        st.rerun()

    for station_id in list(selected_ids):
        row = _station_row(station_id)
        if row is None:
            continue
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([4, 1.3, 1, 1])
            with c1:
                st.markdown(f"**{row['name']}**  \nStation ID: {row['id']}")
            with c2:
                st.color_picker("Color", TERRACOTA, key=_color_key(station_id), label_visibility="collapsed")
            with c3:
                if st.button("🔍 Zoom", key=f"noaa_map_zoom_{station_id}"):
                    st.session_state["noaa_map_view"] = {
                        "lat": float(row["lat"]), "lon": float(row["lng"]), "zoom": 10.0,
                    }
                    st.rerun()
            with c4:
                if st.button("✕ Remove", key=f"noaa_map_remove_{station_id}"):
                    st.session_state["noaa_map_selected"] = [s for s in selected_ids if s != station_id]
                    st.rerun()

st.divider()
render_view_source(__file__)
