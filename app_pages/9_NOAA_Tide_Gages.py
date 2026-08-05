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

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, OCEAN_BLUE_SHADE, TERRACOTA_SHADE
from core.view_source import render_view_source
from core.export import render_figure_download
from core.style_options import restyle_annotations, ANNOTATION_PRESETS
from core.noaa_tides import (
    DATUM_OPTIONS, UNITS_OPTIONS, TIMEZONE_OPTIONS, INTERVAL_OPTIONS, SOURCE_OPTIONS,
    fetch_station_name, fetch_tide_data, make_plot,
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

c1, c2, c3 = st.columns(3)
with c1:
    station_id = st.text_input("NOAA Station ID", placeholder="e.g. 9414290", key="noaa_station_id")
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
c1, c2, c3, c4 = st.columns(4)
with c1:
    datum = st.selectbox("Datum", [v for _, v in DATUM_OPTIONS], key="noaa_datum",
                          format_func=lambda v: {val: lbl for lbl, val in DATUM_OPTIONS}.get(v, v))
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

    fig = make_plot(df, r["station_label"], r["datum"], r["units"], r["title"])
    st.pyplot(fig, use_container_width=True)

    st.subheader("🎨 Presentation styling (optional)")
    preset = st.selectbox(
        "Annotation color (title, axis labels, ticks, borders, legend)",
        list(ANNOTATION_PRESETS.keys()), index=1, key="noaa_annotation_preset",
    )
    axis_specs = [(fig.axes[0], ["x", "y"], OCEAN_BLUE_SHADE)]
    restyle_annotations(fig, preset, axis_specs)
    st.pyplot(fig, use_container_width=True)

    render_figure_download(fig, f"noaa_tides_{r['station_id']}", key_prefix="noaa_chart")

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

st.divider()
render_view_source(__file__)
