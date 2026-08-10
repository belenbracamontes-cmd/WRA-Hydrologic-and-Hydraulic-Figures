"""NOAA Tide Gage Data -- Streamlit page.

Pulls water level data from the NOAA CO-OPS ("Tides and Currents") API for
any tidal station, over an arbitrarily long date range -- NOAA's own web
interface (and its API) caps a single request at 31 days for the raw
6-minute observed product, so core.noaa_tides chunks a longer request into
multiple calls automatically, the same pattern used for the nationwide
USGS station fetch on the "Intro to USGS" page.

Each row is automatically populated from whichever NOAA product actually
has data for that timestamp: observed readings (tagged Verified once NOAA
has QA'd them, or Preliminary in the ~month before that happens) wherever
available, falling back to the astronomical tide Prediction for anything
NOAA hasn't observed yet (very recent dates awaiting verification, or
future dates).

Units, time zone, datum, and interval all mirror NOAA's own site. One
caveat surfaced directly to the user: NOAA's observed water_level product
always returns raw 6-minute data regardless of the interval chosen --
interval only actually changes the granularity of the Predicted portion.
"""

import sys
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, OCEAN_BLUE_SHADE, OCEAN_BLUE_TINT, TERRACOTA_SHADE
from core.style_options import render_chart_panel, render_data_color_pickers
from core.noaa_station_map import fetch_all_tide_stations
from core.noaa_tides import (
    DATUM_OPTIONS, UNITS_OPTIONS, TIMEZONE_OPTIONS, INTERVAL_OPTIONS, SOURCE_OPTIONS,
    fetch_station_name, fetch_tide_data, make_plot, fetch_station_datums, available_datum_codes,
)

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>NOAA Tide Gage Data</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Water levels for any NOAA tidal station, over any date range -- longer than the "
               "30-day window NOAA's own site limits a single request to.")

st.markdown(
    """
    Each row is automatically filled from whichever NOAA product actually has data for that
    moment: an **observed reading** (labeled **Verified** once NOAA has finished quality-checking
    it, or **Preliminary** in the roughly month-long window before that happens) wherever one
    exists, or the astronomical **Predicted** tide otherwise -- covering both very recent dates
    NOAA hasn't verified yet and any future dates.

    Don't know a station's ID? Look one up on NOAA's own
    [Tides & Currents map](https://tidesandcurrents.noaa.gov/map/).
    """
)

st.divider()
st.subheader("1. Station & date range")


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_fetch_all_stations():
    return fetch_all_tide_stations()


lookup_method = st.radio(
    "Don't know the station number? Pick it from a list instead.",
    ["Type station ID", "Browse by state"], key="noaa_lookup_method", horizontal=True,
)

if lookup_method == "Browse by state":
    all_stations = _cached_fetch_all_stations()
    state_options = sorted(s for s in all_stations["state"].unique() if s)
    sc1, sc2 = st.columns(2)
    with sc1:
        picked_state = st.selectbox("State", state_options, key="noaa_picker_state")
    with sc2:
        state_stations = all_stations[all_stations["state"] == picked_state].sort_values("name")
        station_labels = {row["id"]: f"{row['name']} ({row['id']})" for _, row in state_stations.iterrows()}
        picked_station_id = st.selectbox(
            "Station", list(station_labels.keys()), key="noaa_picker_station",
            format_func=lambda sid: station_labels.get(sid, sid),
        )
    station_id = picked_station_id or ""
else:
    station_id = st.text_input("NOAA Station ID", placeholder="e.g. 9414290", key="noaa_station_id")

c2, c3 = st.columns(2)
with c2:
    _default_end = dt.date.today()
    begin_date = st.date_input("Begin date", value=_default_end - dt.timedelta(days=45),
                                min_value=dt.date(1990, 1, 1), max_value=_default_end + dt.timedelta(days=365),
                                key="noaa_begin_date")
with c3:
    end_date = st.date_input("End date", value=_default_end + dt.timedelta(days=10),
                              min_value=dt.date(1990, 1, 1), max_value=_default_end + dt.timedelta(days=365),
                              key="noaa_end_date")

st.subheader("2. Options")


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_fetch_station_datums(sid):
    return fetch_station_datums(sid)


station_datums = _cached_fetch_station_datums(station_id.strip()) if station_id.strip() else None
avail_datum_codes = available_datum_codes(station_datums)

if station_datums:
    with st.expander(f"📏 Which datums does this station support? ({len(station_datums['datums'])} on file)"):
        datum_table = pd.DataFrame(station_datums["datums"]).rename(columns={
            "name": "Datum", "description": "Description",
            "value": f"Value, relative to station datum ({station_datums['units']})",
        })
        st.dataframe(datum_table, use_container_width=True, hide_index=True)
        if station_datums["orthometric_datum"]:
            st.caption(f"Also referenced to the **{station_datums['orthometric_datum']}** orthometric "
                       "datum (selectable below as NAVD).")
        else:
            st.caption("This station is **not** referenced to a NAVD orthometric datum -- picking "
                       "NAVD below will likely return an error.")
elif station_id.strip():
    st.caption("⚠️ Couldn't look up which datums this station supports -- showing the full standard "
               "list below; NOAA will report an error at fetch time if it picks one this station doesn't have.")

c1, c2, c3, c4 = st.columns(4)
with c1:
    datum = st.selectbox("Datum", [v for _, v in DATUM_OPTIONS], key="noaa_datum",
                          format_func=lambda v: {val: lbl for lbl, val in DATUM_OPTIONS}.get(v, v))
    if station_datums and datum not in avail_datum_codes:
        st.caption(f"⚠️ {station_id.strip()} doesn't list this datum -- NOAA may reject the request.")
with c2:
    units = st.selectbox("Units", [v for _, v in UNITS_OPTIONS], key="noaa_units",
                          format_func=lambda v: {val: lbl for lbl, val in UNITS_OPTIONS}.get(v, v))
with c3:
    time_zone = st.selectbox("Time zone", [v for _, v in TIMEZONE_OPTIONS], key="noaa_time_zone",
                              format_func=lambda v: {val: lbl for lbl, val in TIMEZONE_OPTIONS}.get(v, v))
with c4:
    interval = st.selectbox("Interval", [v for _, v in INTERVAL_OPTIONS], key="noaa_interval",
                             format_func=lambda v: {val: lbl for lbl, val in INTERVAL_OPTIONS}.get(v, v))

source = st.selectbox("Data source", [v for _, v in SOURCE_OPTIONS], key="noaa_source",
                       format_func=lambda v: {val: lbl for lbl, val in SOURCE_OPTIONS}.get(v, v))
st.caption("NOAA's observed water level product always returns raw 6-minute data no matter what "
           "interval you pick -- interval only changes the granularity of the Predicted portion.")

title = st.text_input("Chart title (optional)", key="noaa_title",
                       placeholder="e.g. San Francisco Water Level")

if st.button("Fetch Data", type="primary", key="noaa_fetch"):
    if not station_id.strip():
        st.error("Enter a NOAA Station ID.")
        st.stop()
    if begin_date > end_date:
        st.error("Begin date must be on or before end date.")
        st.stop()

    try:
        station_label = fetch_station_name(station_id.strip())

        progress_bar = st.progress(0.0, text="Fetching NOAA tide data...")

        def _on_progress(done, total, label):
            progress_bar.progress(done / total, text=f"Fetching {label} ({done}/{total})...")

        df = fetch_tide_data(
            station_id.strip(), begin_date, end_date, datum, units, time_zone, interval,
            source=source, progress_callback=_on_progress,
        )
        progress_bar.empty()

        if df.empty:
            st.error("No data was returned for that station/date range/datum combination. "
                     "Double-check the station ID and that it supports the datum you picked.")
            st.stop()

        st.session_state["noaa_result"] = dict(
            df=df, station_label=station_label, station_id=station_id.strip(),
            datum=datum, units=units, time_zone=time_zone, interval=interval,
            source=source, title=title,
        )
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.stop()

if "noaa_result" in st.session_state:
    r = st.session_state["noaa_result"]
    df = r["df"]

    st.divider()
    st.subheader(f"📈 {r['station_label']} (Station {r['station_id']})")
    st.caption(f"{len(df):,} rows — " +
               ", ".join(f"{status}: {count:,}" for status, count in df["status"].value_counts().items()))

    has_predicted = (df["status"] == "Predicted").any()
    has_observed = (df["status"] != "Predicted").any()
    color_series = []
    if has_predicted:
        color_series.append({"label": "Predicted", "color": OCEAN_BLUE_TINT})
    if has_observed:
        color_series.append({"label": "Observed (verified/preliminary)", "color": OCEAN_BLUE_SHADE})
    color_overrides = render_data_color_pickers(color_series, key_prefix="noaa_chart")
    predicted_color = color_overrides.get("Predicted", OCEAN_BLUE_TINT)
    observed_color = color_overrides.get("Observed (verified/preliminary)", OCEAN_BLUE_SHADE)

    fig = make_plot(df, r["station_label"], r["datum"], r["units"], r["title"],
                     predicted_color=predicted_color, observed_color=observed_color)
    axis_specs = [(fig.axes[0], ["x", "y"], observed_color)]
    render_chart_panel(fig, key_prefix="noaa_chart", base_filename=f"noaa_tides_{r['station_id']}",
                        axis_specs=axis_specs)

    st.divider()
    st.subheader("Data table")
    display_df = df.rename(columns={
        "date": "Date", "time": "Time", "water_level": f"Water Level ({r['datum']})", "status": "Status",
    })
    st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)

    csv_bytes = display_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV", data=csv_bytes,
        file_name=f"noaa_tides_{r['station_id']}_{r['datum']}.csv",
        mime="text/csv", key="noaa_csv_download",
    )

    with st.expander("📋 Copy as text (tab-separated, paste straight into Excel)"):
        MAX_COPY_ROWS = 5000
        copy_df = display_df.head(MAX_COPY_ROWS)
        if len(display_df) > MAX_COPY_ROWS:
            st.caption(f"Showing the first {MAX_COPY_ROWS:,} of {len(display_df):,} rows here -- "
                       "use the CSV download above for the full dataset.")
        st.code(copy_df.to_csv(index=False, sep="\t"), language=None)
else:
    st.info("Enter a station ID and date range above, then click **Fetch Data** to get started.")

