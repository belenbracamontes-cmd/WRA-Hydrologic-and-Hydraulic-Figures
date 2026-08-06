"""Intro to CIMIS -- Streamlit page.

A statewide map of California's CIMIS (California Irrigation Management
Information System) weather stations, mirroring the "Intro to USGS" /
"Intro to NOAA Tides" map/search/selection feature set. CIMIS's station
metadata API returns every station statewide (~275) in a single request --
no chunking needed -- and, unlike the CIMIS *data* API, doesn't require an
appKey.

Since every CIMIS station is in California, the geographic filter here is
County rather than State. Roughly half of all CIMIS stations on record are
long since disconnected, so an "Only show active stations" toggle is on by
default -- most people are here to plan a data pull, and only active
stations can supply anything recent.

"Find a station" narrows the list with optional County/City filters plus a
name/ID search, then a single "Add" click adds a station straight to the
map and the running selection below (no separate confirm step). Selected
stations render as larger highlighted points, each with its own color
(default field green); a "Zoom" button per station recenters the map, and
an "only show selected" toggle can hide the full statewide cloud.

Like the USGS/NOAA maps, this uses only the "Standard" basemap -- the same
Streamlit-bundled deck.gl component is used here, and it has the same
Satellite/Terrain limitations documented on those pages.
"""

import sys
from pathlib import Path

import pydeck as pdk
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, FIELD_GREEN, FIELD_GREEN_SHADE
from core.view_source import render_view_source
from core.cimis_stations import fetch_all_cimis_stations, hex_to_rgba

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Intro to CIMIS</h1>",
        unsafe_allow_html=True,
    )
    st.caption("A statewide look at California's CIMIS weather station network before you pull "
               "data from one on the CIMIS Data page.")

st.markdown(
    """
    CIMIS (the California Irrigation Management Information System, run by the CA Dept. of Water
    Resources) operates a statewide network of automated weather stations feeding reference
    evapotranspiration (ETo), precipitation, temperature, and other daily/hourly weather data.
    Every station has a unique **station number** and feeds the same CIMIS Web API the
    [CIMIS Data](/cimis-data) page pulls from.

    Hover any point on the map below to see a station's name and number, or use the
    county/city/search filters underneath to find and add stations to the map in their own color.
    For deeper station-by-station detail (siting photos, full history), see CIMIS's own
    [station finder](https://cimis.water.ca.gov/WSNReportCriteria.aspx).
    """
)

st.divider()


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_fetch_all_stations():
    return fetch_all_cimis_stations()


all_stations = _cached_fetch_all_stations()

only_active_default = st.checkbox("Only show active stations", value=True, key="cimis_map_only_active")
display_stations = all_stations[all_stations["is_active"]] if only_active_default else all_stations

st.subheader(f"📍 {len(display_stations):,} of {len(all_stations):,} CIMIS stations statewide")

# ── Selection state ─────────────────────────────────────────────────────────
if "cimis_map_selected" not in st.session_state:
    st.session_state["cimis_map_selected"] = []  # list of station id strings
if "cimis_map_view" not in st.session_state:
    st.session_state["cimis_map_view"] = {"lat": 37.2, "lon": -119.5, "zoom": 5.4}

selected_ids = st.session_state["cimis_map_selected"]


def _color_key(station_id):
    return f"cimis_map_color_{station_id}"


def _station_row(station_id):
    match = all_stations[all_stations["id"] == station_id]
    return match.iloc[0] if not match.empty else None


# ── Map display controls ────────────────────────────────────────────────────
only_selected = st.checkbox("Only show selected stations", key="cimis_map_only_selected",
                             disabled=not selected_ids)

layers = []

if not (only_selected and selected_ids):
    base_layer = pdk.Layer(
        "ScatterplotLayer",
        data=display_stations,
        get_position=["lng", "lat"],
        get_fill_color=hex_to_rgba(FIELD_GREEN_SHADE, alpha=140),
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
        color_hex = st.session_state.get(_color_key(station_id), FIELD_GREEN)
        sel_rows.append({
            "id": row["id"], "name": row["name"], "lat": row["lat"], "lng": row["lng"],
            "county": row["county"], "is_active": "Active" if row["is_active"] else "Inactive",
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

view = st.session_state["cimis_map_view"]
view_state = pdk.ViewState(latitude=view["lat"], longitude=view["lon"], zoom=view["zoom"], pitch=0)
tooltip = {
    "html": "<b>{name}</b><br/>Station #{id}<br/>{county} County",
    "style": {"backgroundColor": FIELD_GREEN_SHADE, "color": "white"},
}
deck = pdk.Deck(layers=layers, initial_view_state=view_state, tooltip=tooltip)

# Force a full remount (not just a prop update) whenever anything that
# should visibly change the map changes -- deck.gl's initial_view_state and
# per-point colors aren't reliably re-applied to an already-mounted
# component across Streamlit reruns otherwise.
colors_sig = tuple(sorted((s, st.session_state.get(_color_key(s), FIELD_GREEN)) for s in selected_ids))
map_key = (f"cimis_map_{round(view['lat'], 4)}_{round(view['lon'], 4)}_{view['zoom']}_"
           f"{only_selected}_{only_active_default}_{hash(colors_sig)}")
st.pydeck_chart(deck, use_container_width=True, height=600, key=map_key)

st.divider()
st.subheader("Filter by county / city (optional)")
county_options = ["All counties"] + sorted(c for c in display_stations["county"].unique() if c)

c1, c2 = st.columns(2)
with c1:
    county_choice = st.selectbox("County", county_options, key="cimis_map_county_filter")
with c2:
    city_query = st.text_input("City", key="cimis_map_city_filter",
                                placeholder="e.g. Davis (matches the station name)")

filtered = display_stations
if county_choice != "All counties":
    filtered = filtered[filtered["county"] == county_choice]
if city_query.strip():
    filtered = filtered[filtered["name"].str.contains(city_query.strip(), case=False, na=False)]

st.divider()
st.subheader("Find a station")
query = st.text_input("Search by station name or number", key="cimis_map_search",
                       placeholder="e.g. Fresno, or 2")

if query.strip():
    q = query.strip().lower()
    filtered = filtered[
        filtered["name"].str.lower().str.contains(q, na=False)
        | filtered["id"].str.contains(q, na=False)
    ]

MAX_LISTED = 50
st.caption(f"{len(filtered):,} of {len(display_stations):,} shown stations match your filters.")

if len(filtered) == 0:
    st.info("No stations match -- try loosening the county/city/search filters above, or unchecking "
             "\"Only show active stations\".")
elif len(filtered) > MAX_LISTED:
    st.info(f"That's {len(filtered):,} stations -- narrow with the County/City filters or the search box "
             f"above to list them here (up to {MAX_LISTED} at a time).")
else:
    for _, row in filtered.iterrows():
        station_id = row["id"]
        rc1, rc2, rc3 = st.columns([4, 3, 1.2])
        with rc1:
            st.write(f"**{row['name']}**  \nStation #{station_id}")
        with rc2:
            status = "🟢 Active" if row["is_active"] else "⚪ Inactive"
            st.caption(f"{row['county'] or '—'} County · {status}")
        with rc3:
            already = station_id in selected_ids
            if st.button("Added ✓" if already else "➕ Add", key=f"cimis_map_add_{station_id}",
                         disabled=already):
                selected_ids.append(station_id)
                st.rerun()

st.divider()
st.subheader(f"🎯 Selected stations ({len(selected_ids)})")
if not selected_ids:
    st.info("No stations selected yet. Click \"Add\" on a station above to get started.")
else:
    if st.button("Clear all", key="cimis_map_clear_all"):
        st.session_state["cimis_map_selected"] = []
        st.rerun()

    for station_id in list(selected_ids):
        row = _station_row(station_id)
        if row is None:
            continue
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([4, 1.3, 1, 1])
            with c1:
                status = "🟢 Active" if row["is_active"] else "⚪ Inactive"
                st.markdown(f"**{row['name']}**  \nStation #{row['id']} · {row['county']} County · {status}")
            with c2:
                st.color_picker("Color", FIELD_GREEN, key=_color_key(station_id), label_visibility="collapsed")
            with c3:
                if st.button("🔍 Zoom", key=f"cimis_map_zoom_{station_id}"):
                    st.session_state["cimis_map_view"] = {
                        "lat": float(row["lat"]), "lon": float(row["lng"]), "zoom": 10.0,
                    }
                    st.rerun()
            with c4:
                if st.button("✕ Remove", key=f"cimis_map_remove_{station_id}"):
                    st.session_state["cimis_map_selected"] = [s for s in selected_ids if s != station_id]
                    st.rerun()

st.divider()
render_view_source(__file__)
