"""PRISM Climate Data -- Streamlit page.

Pulls gridded climate data (precipitation, temperature, dew point, vapor
pressure deficit, solar radiation) from PRISM for any point in the
contiguous US, over any date range -- chunked automatically (5-year
chunks for daily data, 20-year chunks for monthly; PRISM's own Data
Explorer sets a generous 5-minute ajax timeout, suggesting it tolerates
large single requests, but this keeps individual requests and progress
steps a manageable size).

Unlike NOAA/CIMIS, there's no station to pick -- PRISM is a continuous
grid, so you specify a point directly (or reuse one pinned on the
[Intro to PRISM](/intro-to-prism) page). No API key is needed.
"""

import sys
import datetime as dt
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, CALIFORNIA_SUNSET_SHADE
from core.style_options import render_chart_panel, render_data_color_pickers
from core.prism_data import (
    VARIABLES, RANGE_OPTIONS, UNITS_OPTIONS, RESOLUTION_OPTIONS,
    in_conus, fetch_location_info, fetch_prism_timeseries, make_plot,
)

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>PRISM Climate Data</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Daily, monthly, or annual gridded climate data for any point in the contiguous US, "
               "over any date range.")

st.markdown(
    """
    Pick one or more variables below (Precipitation and Mean Temperature are the most commonly
    used) and they'll each get their own chart, stacked so you can compare them over the same time
    span. PRISM is a gridded dataset, not a station network, so there's no data-quality flag to
    show the way NOAA/CIMIS station readings have -- every value here is PRISM's own modeled
    estimate for the exact point you specify.
    """
)

st.divider()
st.subheader("1. Location & date range")

pinned = st.session_state.get("prism_pinned", [])
method = st.radio(
    "Pinned a point already on the Intro to PRISM page? Pick it here instead of retyping it.",
    ["Enter coordinates", "Use a pinned location"], key="prism_data_method", horizontal=True,
)

if method == "Use a pinned location" and pinned:
    pin_labels = {f"{p['label']} ({p['lat']:.4f}, {p['lon']:.4f})": p for p in pinned}
    picked = st.selectbox("Pinned location", list(pin_labels.keys()), key="prism_data_pin_pick")
    chosen = pin_labels[picked]
    lat, lon, location_label = chosen["lat"], chosen["lon"], chosen["label"]
elif method == "Use a pinned location":
    st.info("No locations pinned yet -- add one on the [Intro to PRISM](/intro-to-prism) page, "
             "or enter coordinates directly.")
    lat, lon, location_label = 37.77, -122.42, "San Francisco"
else:
    c1, c2 = st.columns(2)
    with c1:
        lat = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=37.77,
                               step=0.01, format="%.4f", key="prism_lat")
    with c2:
        lon = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=-122.42,
                               step=0.01, format="%.4f", key="prism_lon")
    location_label = st.text_input("Location label (optional)", key="prism_location_label",
                                    placeholder="e.g. San Francisco") or f"{lat:.4f}, {lon:.4f}"

if not in_conus(lat, lon):
    st.error("That point falls outside PRISM's CONUS grid -- pick a point within the "
             "contiguous US (Alaska, Hawaii, and offshore points aren't covered).")

with st.expander(f"ℹ️ Location info — {location_label}"):
    try:
        info = fetch_location_info(lat, lon)
        ic1, ic2 = st.columns(2)
        with ic1:
            st.write(f"**State:** {info['state'] or '—'}")
            st.write(f"**County:** {info['county'] or '—'}")
        with ic2:
            elev = info["elev_800m_ft"]
            st.write(f"**Elevation (800m grid):** {elev:,.0f} ft" if elev is not None
                     else "**Elevation:** — (outside PRISM's grid)")
    except Exception as e:
        st.caption(f"Couldn't load location info: {e}")

st.subheader("2. Options")
c1, c2, c3 = st.columns(3)
with c1:
    range_key = st.selectbox("Time step", [v for _, v in RANGE_OPTIONS], key="prism_range",
                              format_func=lambda v: {val: lbl for lbl, val in RANGE_OPTIONS}.get(v, v))
with c2:
    units = st.selectbox("Units", [v for _, v in UNITS_OPTIONS], key="prism_units",
                          format_func=lambda v: {val: lbl for lbl, val in UNITS_OPTIONS}.get(v, v))
with c3:
    resolution = st.selectbox("Grid resolution", [v for _, v in RESOLUTION_OPTIONS], key="prism_resolution",
                               format_func=lambda v: {val: lbl for lbl, val in RESOLUTION_OPTIONS}.get(v, v))

_min_dates = {"daily": dt.date(1981, 1, 1), "monthly": dt.date(1895, 1, 1), "yearly": dt.date(1895, 1, 1)}
_default_end = dt.date.today() - dt.timedelta(days=3)  # PRISM's most recent data lags a few days
min_date = _min_dates[range_key]

c4, c5 = st.columns(2)
with c4:
    begin_date = st.date_input("Begin date", value=max(min_date, _default_end - dt.timedelta(days=365 * 3)),
                                min_value=min_date, max_value=_default_end, key="prism_begin_date")
with c5:
    end_date = st.date_input("End date", value=_default_end, min_value=min_date, max_value=_default_end,
                              key="prism_end_date")

item_labels = st.multiselect("Variables", [lbl for lbl, _ in VARIABLES],
                              default=["Precipitation", "Mean Temperature"], key="prism_items")

title = st.text_input("Chart title (optional)", key="prism_title",
                       placeholder="e.g. San Francisco Precipitation")

if st.button("Fetch Data", type="primary", key="prism_fetch"):
    if not in_conus(lat, lon):
        st.error("Pick a point inside PRISM's CONUS grid before fetching.")
        st.stop()
    if not item_labels:
        st.error("Pick at least one variable.")
        st.stop()
    if begin_date > end_date:
        st.error("Begin date must be on or before end date.")
        st.stop()

    item_labels_codes = [(lbl, code) for lbl, code in VARIABLES if lbl in item_labels]

    try:
        progress_bar = st.progress(0.0, text="Fetching PRISM data...")

        def _on_progress(done, total, label):
            progress_bar.progress(done / total, text=f"Fetching {label} ({done}/{total})...")

        df = fetch_prism_timeseries(
            lat, lon, range_key, begin_date, end_date, item_labels_codes,
            units, resolution, progress_callback=_on_progress,
        )
        progress_bar.empty()

        if df.empty:
            st.error("No data was returned for that location/date range combination.")
            st.stop()

        st.session_state["prism_result"] = dict(
            df=df, location_label=location_label, lat=lat, lon=lon,
            item_labels=item_labels, units=units, range_key=range_key, title=title,
        )
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.stop()

if "prism_result" in st.session_state:
    r = st.session_state["prism_result"]
    df = r["df"]
    unit_label = "English" if r["units"] == "eng" else "Metric (SI)"
    range_label = {"daily": "Daily", "monthly": "Monthly", "yearly": "Annual"}[r["range_key"]]

    st.divider()
    st.subheader(f"📈 {r['location_label']} ({r['lat']:.4f}, {r['lon']:.4f})")
    st.caption(f"{len(df):,} rows — {range_label}, {unit_label} units")

    color_overrides = render_data_color_pickers(
        [{"label": label, "color": CALIFORNIA_SUNSET_SHADE} for label in r["item_labels"]],
        key_prefix="prism_chart",
    )
    fig = make_plot(df, r["location_label"], r["item_labels"], unit_label, r["title"],
                     colors=color_overrides)
    axis_specs = [(ax, ["x", "y"], color_overrides.get(label, CALIFORNIA_SUNSET_SHADE))
                   for ax, label in zip(fig.axes, r["item_labels"])]
    render_chart_panel(fig, key_prefix="prism_chart",
                        base_filename=f"prism_{r['lat']:.4f}_{r['lon']:.4f}", axis_specs=axis_specs)

    st.divider()
    st.subheader("Data table")
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV", data=csv_bytes,
        file_name=f"prism_{r['lat']:.4f}_{r['lon']:.4f}_{r['range_key']}.csv",
        mime="text/csv", key="prism_csv_download",
    )

    with st.expander("📋 Copy as text (tab-separated, paste straight into Excel)"):
        MAX_COPY_ROWS = 5000
        copy_df = df.head(MAX_COPY_ROWS)
        if len(df) > MAX_COPY_ROWS:
            st.caption(f"Showing the first {MAX_COPY_ROWS:,} of {len(df):,} rows here -- "
                       "use the CSV download above for the full dataset.")
        st.code(copy_df.to_csv(index=False, sep="\t"), language=None)
else:
    st.info("Pick a location and date range above, then click **Fetch Data** to get started.")

