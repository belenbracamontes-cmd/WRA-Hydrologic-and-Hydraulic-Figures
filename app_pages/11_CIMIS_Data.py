"""CIMIS Weather Station Data -- Streamlit page.

Pulls weather station data from the California Dept. of Water Resources'
CIMIS Web API for any station, over any date range -- chunked
automatically (about a year per request for daily data, a week for
hourly, per CIMIS's own client-library guidance) the same way the NOAA
Tide Gage Data and nationwide USGS pages chunk long date ranges.

Unlike NOAA tides, CIMIS has no separate "observed vs. predicted" product
to blend -- every value is a real station measurement carrying a single QC
flag (blank means it passed quality control cleanly).

Every data request needs a personal, free CIMIS appKey -- register at
https://cimis.water.ca.gov/Auth/Register.aspx. The station list/map
doesn't need one; only actual data pulls do.
"""

import sys
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, FIELD_GREEN_SHADE
from core.view_source import render_view_source
from core.export import render_figure_download
from core.style_options import restyle_annotations, ANNOTATION_PRESETS
from core.cimis_stations import fetch_all_cimis_stations
from core.cimis_data import (
    DAILY_DATA_ITEMS, HOURLY_DATA_ITEMS, UNITS_OPTIONS, SCOPE_OPTIONS, QC_FLAG_MEANINGS,
    fetch_cimis_data, make_plot,
)

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>CIMIS Weather Station Data</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Daily or hourly weather data (ETo, precipitation, temperature, and more) for any "
               "CIMIS station, over any date range.")

st.markdown(
    """
    Pick one or more data items below (Reference ETo and Precipitation are the most commonly
    used) and they'll each get their own chart, stacked so you can compare them over the same
    time span. Every value carries a QC flag from CIMIS itself -- a blank flag means it passed
    quality control cleanly; see the legend near the data table for the rest.

    **You'll need a free CIMIS appKey** to pull data (the station list above doesn't need one) --
    register in under a minute at CIMIS's
    [account signup page](https://cimis.water.ca.gov/Auth/Register.aspx), then paste your key
    below.
    """
)

st.divider()
st.subheader("1. CIMIS account")


def _default_app_key():
    try:
        return st.secrets.get("CIMIS_APP_KEY", "")
    except Exception:
        return ""


app_key = st.text_input(
    "CIMIS appKey", value=_default_app_key(), type="password", key="cimis_app_key",
    placeholder="e.g. a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    help="From your CIMIS account's \"Web API\" page after registering.",
)

st.divider()
st.subheader("2. Station & date range")


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_fetch_all_stations():
    return fetch_all_cimis_stations()


lookup_method = st.radio(
    "Don't know the station number? Pick it from a list instead.",
    ["Type station number", "Browse by county"], key="cimis_lookup_method", horizontal=True,
)

if lookup_method == "Browse by county":
    all_stations = _cached_fetch_all_stations()
    county_options = sorted(c for c in all_stations["county"].unique() if c)
    sc1, sc2 = st.columns(2)
    with sc1:
        picked_county = st.selectbox("County", county_options, key="cimis_picker_county")
    with sc2:
        county_stations = all_stations[all_stations["county"] == picked_county].sort_values("name")
        station_labels = {
            row["id"]: f"{row['name']} ({row['id']}){'' if row['is_active'] else ' — inactive'}"
            for _, row in county_stations.iterrows()
        }
        picked_station_id = st.selectbox(
            "Station", list(station_labels.keys()), key="cimis_picker_station",
            format_func=lambda sid: station_labels.get(sid, sid),
        )
    station_id = picked_station_id or ""
else:
    station_id = st.text_input("CIMIS Station Number", placeholder="e.g. 2", key="cimis_station_id")

c2, c3 = st.columns(2)
with c2:
    _default_end = dt.date.today()
    begin_date = st.date_input("Begin date", value=_default_end - dt.timedelta(days=365),
                                min_value=dt.date(1982, 6, 7), max_value=_default_end,
                                key="cimis_begin_date")
with c3:
    end_date = st.date_input("End date", value=_default_end,
                              min_value=dt.date(1982, 6, 7), max_value=_default_end,
                              key="cimis_end_date")

# ── Station info (mirrors the NOAA page's "which datums does this station
# support" lookup -- surface what's actually on file for the station in
# play before the user commits to a fetch).
_all_stations_for_info = _cached_fetch_all_stations()
_station_info = None
if station_id.strip():
    _match = _all_stations_for_info[_all_stations_for_info["id"] == station_id.strip()]
    if not _match.empty:
        _station_info = _match.iloc[0]

if _station_info is not None:
    with st.expander(f"ℹ️ Station info — {_station_info['name']}"):
        ic1, ic2 = st.columns(2)
        with ic1:
            st.write(f"**County:** {_station_info['county'] or '—'}")
            st.write(f"**City:** {_station_info['city'] or '—'}")
            st.write(f"**Elevation:** {_station_info['elevation_ft']:,.0f} ft"
                     if pd.notna(_station_info["elevation_ft"]) else "**Elevation:** —")
            st.write(f"**Ground cover:** {_station_info['ground_cover'] or '—'}")
        with ic2:
            status = "🟢 Active" if _station_info["is_active"] else "⚪ Inactive"
            st.write(f"**Status:** {status}")
            st.write(f"**ETo station:** {'Yes' if _station_info['is_eto_station'] else 'No'}")
            st.write(f"**Connected:** {_station_info['connect_date'] or '—'}")
            if not _station_info["is_active"]:
                st.write(f"**Disconnected:** {_station_info['disconnect_date'] or '—'}")
        if _station_info["siting_desc"]:
            st.caption(_station_info["siting_desc"])
        if not _station_info["is_active"]:
            st.warning("This station is inactive -- data will only exist up through its "
                       "disconnect date above.")
elif station_id.strip():
    st.caption("⚠️ Station number not found in the CIMIS station directory -- double-check it, "
               "or use \"Browse by county\" above.")

st.subheader("3. Options")
c1, c2 = st.columns(2)
with c1:
    scope = st.selectbox("Data interval", [v for _, v in SCOPE_OPTIONS], key="cimis_scope",
                          format_func=lambda v: {val: lbl for lbl, val in SCOPE_OPTIONS}.get(v, v))
with c2:
    units = st.selectbox("Units", [v for _, v in UNITS_OPTIONS], key="cimis_units",
                          format_func=lambda v: {val: lbl for lbl, val in UNITS_OPTIONS}.get(v, v))

item_choices = DAILY_DATA_ITEMS if scope == "daily" else HOURLY_DATA_ITEMS
item_labels = st.multiselect(
    "Data items", [lbl for lbl, _ in item_choices], default=[item_choices[0][0]], key="cimis_items",
)
if scope == "hourly":
    st.caption("Hourly requests are chunked in short (weekly) windows since hourly data is much "
               "larger per day than daily data -- a long hourly range may take a while to fetch.")

title = st.text_input("Chart title (optional)", key="cimis_title",
                       placeholder="e.g. Five Points Reference ETo")

if st.button("Fetch Data", type="primary", key="cimis_fetch"):
    if not app_key.strip():
        st.error("Enter your CIMIS appKey above (register for free at CIMIS's account signup page).")
        st.stop()
    if not station_id.strip():
        st.error("Enter or pick a CIMIS station number.")
        st.stop()
    if not item_labels:
        st.error("Pick at least one data item.")
        st.stop()
    if begin_date > end_date:
        st.error("Begin date must be on or before end date.")
        st.stop()

    item_labels_codes = [(lbl, code) for lbl, code in item_choices if lbl in item_labels]
    station_label = (_station_info["name"] if _station_info is not None
                      else f"CIMIS Station {station_id.strip()}")

    try:
        progress_bar = st.progress(0.0, text="Fetching CIMIS data...")

        def _on_progress(done, total, label):
            progress_bar.progress(done / total, text=f"Fetching {label} ({done}/{total})...")

        df = fetch_cimis_data(
            app_key.strip(), station_id.strip(), begin_date, end_date, item_labels_codes,
            units, scope=scope, progress_callback=_on_progress,
        )
        progress_bar.empty()

        if df.empty:
            st.error("No data was returned for that station/date range combination. "
                     "Double-check the station number and that it was active over that period.")
            st.stop()

        st.session_state["cimis_result"] = dict(
            df=df, station_label=station_label, station_id=station_id.strip(),
            item_labels=item_labels, units=units, scope=scope, title=title,
        )
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.stop()

if "cimis_result" in st.session_state:
    r = st.session_state["cimis_result"]
    df = r["df"]
    unit_label = "English" if r["units"] == "E" else "Metric"

    st.divider()
    st.subheader(f"📈 {r['station_label']} (Station {r['station_id']})")
    st.caption(f"{len(df):,} rows — {r['scope'].capitalize()}, {unit_label} units")

    fig = make_plot(df, r["station_label"], r["item_labels"], unit_label, r["title"])
    st.pyplot(fig, use_container_width=True)

    st.subheader("🎨 Presentation styling (optional)")
    preset = st.selectbox(
        "Annotation color (title, axis labels, ticks, borders, legend)",
        list(ANNOTATION_PRESETS.keys()), index=1, key="cimis_annotation_preset",
    )
    axis_specs = [(ax, ["x", "y"], FIELD_GREEN_SHADE) for ax in fig.axes]
    restyle_annotations(fig, preset, axis_specs)
    st.pyplot(fig, use_container_width=True)

    render_figure_download(fig, f"cimis_{r['station_id']}", key_prefix="cimis_chart")

    st.divider()
    st.subheader("Data table")
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)

    with st.expander("📋 QC flag legend"):
        for code, meaning in QC_FLAG_MEANINGS.items():
            st.write(f"**{code or '(blank)'}** — {meaning}")
        st.caption("A handful of rarer flags beyond this list may occasionally appear; they're "
                   "shown as-is in the QC columns above.")

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV", data=csv_bytes,
        file_name=f"cimis_{r['station_id']}_{r['scope']}.csv",
        mime="text/csv", key="cimis_csv_download",
    )

    with st.expander("📋 Copy as text (tab-separated, paste straight into Excel)"):
        MAX_COPY_ROWS = 5000
        copy_df = df.head(MAX_COPY_ROWS)
        if len(df) > MAX_COPY_ROWS:
            st.caption(f"Showing the first {MAX_COPY_ROWS:,} of {len(df):,} rows here -- "
                       "use the CSV download above for the full dataset.")
        st.code(copy_df.to_csv(index=False, sep="\t"), language=None)
else:
    st.info("Enter your appKey, pick a station and date range above, then click **Fetch Data** "
             "to get started.")

st.divider()
render_view_source(__file__)
