"""Intro to PRISM -- Streamlit page.

PRISM is fundamentally different from the USGS/NOAA/CIMIS networks
elsewhere in this app: it's a spatially continuous *gridded* climate
dataset covering the contiguous US, not a network of discrete stations.
There's no station list to browse -- instead, this page lets you pin any
point (by clicking the map directly, typing lat/lon, or searching by
place name) and see it on a map, along with what PRISM knows about that
exact spot: its state/county, grid elevation, and 1991-2020 monthly
climate normals. Pinned points carry over to the PRISM tab of the
[Precipitation Data Collector](/precipitation-data-collector) page as a
shortcut for pulling a full time series from one of them later.

Unlike the pydeck-based USGS/NOAA/CIMIS maps, this page's map is a small
Leaflet map (via a custom Streamlit component) rather than pydeck --
pydeck's ``on_select`` only reports clicks on already-rendered pickable
objects, with no event for a plain click on empty map area returning a
latitude/longitude, which is exactly what click-to-drop-a-pin needs. See
core/click_map.py for the full rationale.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, CALIFORNIA_SUNSET
from core.click_map import render_click_map
from core.prism_data import (
    CONUS_BOUNDS, in_conus, fetch_location_info, fetch_climate_normals, geocode_place,
)

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Intro to PRISM</h1>",
        unsafe_allow_html=True,
    )
    st.caption("A gridded climate dataset covering the whole contiguous US -- pin a point here "
               "before pulling its full time series on the Precipitation Data Collector page.")

st.markdown(
    """
    PRISM (the Parameter-elevation Regressions on Independent Slopes Model, run by Oregon State
    University's PRISM Climate Group) isn't a network of individual weather stations like USGS,
    NOAA, or CIMIS -- it's a continuous **grid** (4 km or 800 m cells) covering the contiguous US,
    built by statistically blending thousands of station observations with terrain. That means you
    don't pick a station number here; you pick a **point** (any latitude/longitude within the US),
    and PRISM gives you precipitation, temperature, dew point, vapor pressure deficit, and solar
    radiation estimates for that exact spot.

    **Click anywhere on the map below to drop a pin there directly** -- or type coordinates or
    search by place name underneath it. No API key is needed for anything on this page or the
    PRISM tab of the [Precipitation Data Collector](/precipitation-data-collector) page -- unlike
    CIMIS, PRISM's public API is fully open.
    """
)

st.divider()

# ── Selection state ─────────────────────────────────────────────────────────
if "prism_pinned" not in st.session_state:
    st.session_state["prism_pinned"] = []  # list of dicts: lat, lon, label
if "prism_map_view" not in st.session_state:
    st.session_state["prism_map_view"] = {"lat": 39.5, "lon": -98.35, "zoom": 3.9}
if "prism_view_signal" not in st.session_state:
    st.session_state["prism_view_signal"] = 0

pinned = st.session_state["prism_pinned"]


def _color_key(idx):
    return f"prism_pin_color_{idx}"


# ── Map (click anywhere to drop a pin, once click-to-add is armed) ─────────
add_mode = st.toggle("📍 Click-to-add pins", key="prism_click_add_mode",
                      help="Turn this on, then click anywhere on the map to drop a pin there.")

map_pins = [
    {"lat": p["lat"], "lon": p["lon"], "label": p["label"],
     "color": st.session_state.get(_color_key(i), CALIFORNIA_SUNSET)}
    for i, p in enumerate(pinned)
]
view = st.session_state["prism_map_view"]
clicked = render_click_map(
    center={"lat": view["lat"], "lon": view["lon"]}, zoom=view["zoom"],
    pins=map_pins, bounds=CONUS_BOUNDS, view_signal=st.session_state["prism_view_signal"],
    add_mode=add_mode, key="prism_click_map",
)
if add_mode:
    st.caption("Click-to-add is **on** -- click anywhere on the map to drop a pin there.")
else:
    st.caption("Turn on **Click-to-add pins** above to drop a pin by clicking the map, or use the "
               "fields below.")
st.caption("The dashed outline marks PRISM's CONUS grid extent -- points outside it have no PRISM data. "
           "Map tiles © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.")

if clicked and add_mode:
    lat, lon = clicked["lat"], clicked["lon"]
    pinned.append({"lat": lat, "lon": lon, "label": f"{lat:.4f}, {lon:.4f}"})
    if not in_conus(lat, lon):
        st.warning("That point falls outside PRISM's CONUS grid -- it won't return any data.")
    st.rerun()

st.divider()
st.subheader("Or specify a point directly")

method = st.radio("How do you want to specify a location?", ["Enter coordinates", "Search by place name"],
                   key="prism_pick_method", horizontal=True)

new_lat, new_lon, new_label = None, None, ""
if method == "Enter coordinates":
    c1, c2 = st.columns(2)
    with c1:
        new_lat = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=37.77,
                                    step=0.01, format="%.4f", key="prism_new_lat")
    with c2:
        new_lon = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=-122.42,
                                    step=0.01, format="%.4f", key="prism_new_lon")
    new_label = st.text_input("Label (optional)", key="prism_new_label",
                               placeholder="e.g. San Francisco")
else:
    query = st.text_input("Place name or address", key="prism_geocode_query",
                           placeholder="e.g. Fresno, CA")
    if query.strip():
        matches = geocode_place(query.strip())
        if not matches:
            st.caption("No matches found -- try a different search, or switch to entering "
                       "coordinates directly.")
        else:
            match_options = {f"{m['display_name']} ({m['lat']:.4f}, {m['lon']:.4f})": m for m in matches}
            picked = st.selectbox("Matches", list(match_options.keys()), key="prism_geocode_pick")
            chosen = match_options[picked]
            new_lat, new_lon, new_label = chosen["lat"], chosen["lon"], chosen["display_name"].split(",")[0]
    st.caption("Search results via [OpenStreetMap Nominatim](https://nominatim.org/).")

if new_lat is not None and new_lon is not None:
    if not in_conus(new_lat, new_lon):
        st.warning("That point falls outside PRISM's CONUS grid -- it won't return any data.")
    if st.button("➕ Add to map", key="prism_add_pin"):
        pinned.append({"lat": float(new_lat), "lon": float(new_lon),
                       "label": new_label.strip() or f"{new_lat:.4f}, {new_lon:.4f}"})
        st.rerun()

st.divider()
st.subheader(f"🎯 Pinned locations ({len(pinned)})")
if not pinned:
    st.info("No locations pinned yet. Add one above to see its climate info and place it on the map.")
else:
    if st.button("Clear all", key="prism_clear_all"):
        st.session_state["prism_pinned"] = []
        st.rerun()

    for i, p in enumerate(list(pinned)):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([4, 1.3, 1, 1])
            with c1:
                st.markdown(f"**{p['label']}**  \n{p['lat']:.4f}, {p['lon']:.4f}")
            with c2:
                st.color_picker("Color", CALIFORNIA_SUNSET, key=_color_key(i), label_visibility="collapsed")
            with c3:
                if st.button("🔍 Zoom", key=f"prism_zoom_{i}"):
                    st.session_state["prism_map_view"] = {"lat": p["lat"], "lon": p["lon"], "zoom": 9}
                    st.session_state["prism_view_signal"] += 1
                    st.rerun()
            with c4:
                if st.button("✕ Remove", key=f"prism_remove_{i}"):
                    st.session_state["prism_pinned"] = [x for j, x in enumerate(pinned) if j != i]
                    st.rerun()

            with st.expander("ℹ️ Location info & 1991-2020 climate normals"):
                try:
                    info = fetch_location_info(p["lat"], p["lon"])
                    ic1, ic2 = st.columns(2)
                    with ic1:
                        st.write(f"**State:** {info['state'] or '—'}")
                        st.write(f"**County:** {info['county'] or '—'}")
                    with ic2:
                        elev = info["elev_800m_ft"]
                        st.write(f"**Elevation (800m grid):** {elev:,.0f} ft" if elev is not None
                                 else "**Elevation:** — (outside PRISM's grid)")

                    normals = fetch_climate_normals(p["lat"], p["lon"])
                    if normals["monthly"]:
                        import pandas as pd
                        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                        label_map = {"ppt": "Precip (in)", "tmin": "Min Temp (°F)",
                                     "tmean": "Mean Temp (°F)", "tmax": "Max Temp (°F)",
                                     "tdmean": "Dew Point (°F)"}
                        table = pd.DataFrame(
                            {label_map.get(k, k): v for k, v in normals["monthly"].items()},
                            index=months,
                        )
                        st.dataframe(table.T, use_container_width=True)
                        annual = normals["annual"]
                        st.caption("Annual: " + ", ".join(
                            f"{label_map.get(k, k)} {v}" for k, v in annual.items()))
                except Exception as e:
                    st.caption(f"Couldn't load climate info for this point: {e}")

