"""Precipitation Data Collector -- Streamlit page.

Combines the two station/point-based precipitation (and other weather/
climate variable) data pullers -- CIMIS and PRISM -- onto one page as
tabs, the same way Daily Flow & Duration Analysis groups five related
USGS tools into one page rather than five separate sidebar entries. Each
tab is otherwise unchanged from its original standalone page (own inputs,
own session-state keys already prefixed cimis_*/prism_*, so nothing
collides sharing a page): CIMIS pulls real station measurements (needs a
free CIMIS appKey), PRISM pulls a modeled value for any point on its
gridded dataset (no API key needed, no station to pick).

The map/intro pages for each ("Intro to CIMIS", "Intro to PRISM") stay
separate -- this page is specifically the two data-pulling tools.
"""

import sys
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, FIELD_GREEN_SHADE, CALIFORNIA_SUNSET_SHADE
from core.style_options import render_chart_panel, render_data_color_pickers
from core.cimis_stations import fetch_all_cimis_stations
from core.cimis_data import (
    DAILY_DATA_ITEMS, HOURLY_DATA_ITEMS, UNITS_OPTIONS as CIMIS_UNITS_OPTIONS,
    SCOPE_OPTIONS, QC_FLAG_MEANINGS, fetch_cimis_data, make_plot as cimis_make_plot,
)
from core.prism_data import (
    VARIABLES, RANGE_OPTIONS, UNITS_OPTIONS as PRISM_UNITS_OPTIONS, RESOLUTION_OPTIONS,
    in_conus, fetch_location_info, fetch_prism_timeseries, make_plot as prism_make_plot,
)

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Precipitation Data Collector</h1>",
        unsafe_allow_html=True,
    )
    st.caption("CIMIS station data and PRISM gridded climate data, side by side as tabs.")

tab_cimis, tab_prism = st.tabs(["🌦️ CIMIS", "🌦️ PRISM"])

# =============================================================================
# CIMIS tab
# =============================================================================
with tab_cimis:
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

    def _default_cimis_app_key():
        try:
            return st.secrets.get("CIMIS_APP_KEY", "")
        except Exception:
            return ""

    cimis_app_key = st.text_input(
        "CIMIS appKey", value=_default_cimis_app_key(), type="password", key="cimis_app_key",
        placeholder="e.g. a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        help="From your CIMIS account's \"Web API\" page after registering.",
    )

    st.divider()
    st.subheader("2. Station & date range")

    @st.cache_data(ttl=86400, show_spinner=False)
    def _cached_fetch_all_cimis_stations():
        return fetch_all_cimis_stations()

    cimis_lookup_method = st.radio(
        "Don't know the station number? Pick it from a list instead.",
        ["Type station number", "Browse by county"], key="cimis_lookup_method", horizontal=True,
    )

    if cimis_lookup_method == "Browse by county":
        cimis_all_stations = _cached_fetch_all_cimis_stations()
        cimis_county_options = sorted(c for c in cimis_all_stations["county"].unique() if c)
        sc1, sc2 = st.columns(2)
        with sc1:
            picked_county = st.selectbox("County", cimis_county_options, key="cimis_picker_county")
        with sc2:
            county_stations = cimis_all_stations[cimis_all_stations["county"] == picked_county].sort_values("name")
            station_labels = {
                row["id"]: f"{row['name']} ({row['id']}){'' if row['is_active'] else ' — inactive'}"
                for _, row in county_stations.iterrows()
            }
            picked_station_id = st.selectbox(
                "Station", list(station_labels.keys()), key="cimis_picker_station",
                format_func=lambda sid: station_labels.get(sid, sid),
            )
        cimis_station_id = picked_station_id or ""
    else:
        cimis_station_id = st.text_input("CIMIS Station Number", placeholder="e.g. 2", key="cimis_station_id")

    c2, c3 = st.columns(2)
    with c2:
        _cimis_default_end = dt.date.today()
        cimis_begin_date = st.date_input("Begin date", value=_cimis_default_end - dt.timedelta(days=365),
                                          min_value=dt.date(1982, 6, 7), max_value=_cimis_default_end,
                                          key="cimis_begin_date")
    with c3:
        cimis_end_date = st.date_input("End date", value=_cimis_default_end,
                                        min_value=dt.date(1982, 6, 7), max_value=_cimis_default_end,
                                        key="cimis_end_date")

    # ── Station info (mirrors the NOAA page's "which datums does this station
    # support" lookup -- surface what's actually on file for the station in
    # play before the user commits to a fetch).
    _all_cimis_stations_for_info = _cached_fetch_all_cimis_stations()
    _cimis_station_info = None
    if cimis_station_id.strip():
        _match = _all_cimis_stations_for_info[_all_cimis_stations_for_info["id"] == cimis_station_id.strip()]
        if not _match.empty:
            _cimis_station_info = _match.iloc[0]

    if _cimis_station_info is not None:
        with st.expander(f"ℹ️ Station info — {_cimis_station_info['name']}"):
            ic1, ic2 = st.columns(2)
            with ic1:
                st.write(f"**County:** {_cimis_station_info['county'] or '—'}")
                st.write(f"**City:** {_cimis_station_info['city'] or '—'}")
                st.write(f"**Elevation:** {_cimis_station_info['elevation_ft']:,.0f} ft"
                         if pd.notna(_cimis_station_info["elevation_ft"]) else "**Elevation:** —")
                st.write(f"**Ground cover:** {_cimis_station_info['ground_cover'] or '—'}")
            with ic2:
                status = "🟢 Active" if _cimis_station_info["is_active"] else "⚪ Inactive"
                st.write(f"**Status:** {status}")
                st.write(f"**ETo station:** {'Yes' if _cimis_station_info['is_eto_station'] else 'No'}")
                st.write(f"**Connected:** {_cimis_station_info['connect_date'] or '—'}")
                if not _cimis_station_info["is_active"]:
                    st.write(f"**Disconnected:** {_cimis_station_info['disconnect_date'] or '—'}")
            if _cimis_station_info["siting_desc"]:
                st.caption(_cimis_station_info["siting_desc"])
            if not _cimis_station_info["is_active"]:
                st.warning("This station is inactive -- data will only exist up through its "
                           "disconnect date above.")
    elif cimis_station_id.strip():
        st.caption("⚠️ Station number not found in the CIMIS station directory -- double-check it, "
                   "or use \"Browse by county\" above.")

    st.subheader("3. Options")
    c1, c2 = st.columns(2)
    with c1:
        cimis_scope = st.selectbox("Data interval", [v for _, v in SCOPE_OPTIONS], key="cimis_scope",
                                    format_func=lambda v: {val: lbl for lbl, val in SCOPE_OPTIONS}.get(v, v))
    with c2:
        cimis_units = st.selectbox("Units", [v for _, v in CIMIS_UNITS_OPTIONS], key="cimis_units",
                                    format_func=lambda v: {val: lbl for lbl, val in CIMIS_UNITS_OPTIONS}.get(v, v))

    cimis_item_choices = DAILY_DATA_ITEMS if cimis_scope == "daily" else HOURLY_DATA_ITEMS
    cimis_item_labels = st.multiselect(
        "Data items", [lbl for lbl, _ in cimis_item_choices], default=[cimis_item_choices[0][0]],
        key="cimis_items",
    )
    if cimis_scope == "hourly":
        st.caption("Hourly requests are chunked in short (weekly) windows since hourly data is much "
                   "larger per day than daily data -- a long hourly range may take a while to fetch.")

    cimis_title = st.text_input("Chart title (optional)", key="cimis_title",
                                 placeholder="e.g. Five Points Reference ETo")

    if st.button("Fetch Data", type="primary", key="cimis_fetch"):
        if not cimis_app_key.strip():
            st.error("Enter your CIMIS appKey above (register for free at CIMIS's account signup page).")
            st.stop()
        if not cimis_station_id.strip():
            st.error("Enter or pick a CIMIS station number.")
            st.stop()
        if not cimis_item_labels:
            st.error("Pick at least one data item.")
            st.stop()
        if cimis_begin_date > cimis_end_date:
            st.error("Begin date must be on or before end date.")
            st.stop()

        cimis_item_labels_codes = [(lbl, code) for lbl, code in cimis_item_choices if lbl in cimis_item_labels]
        cimis_station_label = (_cimis_station_info["name"] if _cimis_station_info is not None
                                else f"CIMIS Station {cimis_station_id.strip()}")

        try:
            progress_bar = st.progress(0.0, text="Fetching CIMIS data...")

            def _on_cimis_progress(done, total, label):
                progress_bar.progress(done / total, text=f"Fetching {label} ({done}/{total})...")

            df = fetch_cimis_data(
                cimis_app_key.strip(), cimis_station_id.strip(), cimis_begin_date, cimis_end_date,
                cimis_item_labels_codes, cimis_units, scope=cimis_scope,
                progress_callback=_on_cimis_progress,
            )
            progress_bar.empty()

            if df.empty:
                st.error("No data was returned for that station/date range combination. "
                         "Double-check the station number and that it was active over that period.")
                st.stop()

            st.session_state["cimis_result"] = dict(
                df=df, station_label=cimis_station_label, station_id=cimis_station_id.strip(),
                item_labels=cimis_item_labels, units=cimis_units, scope=cimis_scope, title=cimis_title,
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

        color_overrides = render_data_color_pickers(
            [{"label": label, "color": FIELD_GREEN_SHADE} for label in r["item_labels"]],
            key_prefix="cimis_chart",
        )
        fig = cimis_make_plot(df, r["station_label"], r["item_labels"], unit_label, r["title"],
                               colors=color_overrides)
        axis_specs = [(ax, ["x", "y"], color_overrides.get(label, FIELD_GREEN_SHADE))
                       for ax, label in zip(fig.axes, r["item_labels"])]
        render_chart_panel(fig, key_prefix="cimis_chart", base_filename=f"cimis_{r['station_id']}",
                            axis_specs=axis_specs)

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

# =============================================================================
# PRISM tab
# =============================================================================
with tab_prism:
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

    prism_pinned = st.session_state.get("prism_pinned", [])
    prism_method = st.radio(
        "Pinned a point already on the Intro to PRISM page? Pick it here instead of retyping it.",
        ["Enter coordinates", "Use a pinned location"], key="prism_data_method", horizontal=True,
    )

    if prism_method == "Use a pinned location" and prism_pinned:
        pin_labels = {f"{p['label']} ({p['lat']:.4f}, {p['lon']:.4f})": p for p in prism_pinned}
        picked = st.selectbox("Pinned location", list(pin_labels.keys()), key="prism_data_pin_pick")
        chosen = pin_labels[picked]
        prism_lat, prism_lon, prism_location_label = chosen["lat"], chosen["lon"], chosen["label"]
    elif prism_method == "Use a pinned location":
        st.info("No locations pinned yet -- add one on the [Intro to PRISM](/intro-to-prism) page, "
                 "or enter coordinates directly.")
        prism_lat, prism_lon, prism_location_label = 37.77, -122.42, "San Francisco"
    else:
        c1, c2 = st.columns(2)
        with c1:
            prism_lat = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=37.77,
                                         step=0.01, format="%.4f", key="prism_lat")
        with c2:
            prism_lon = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=-122.42,
                                         step=0.01, format="%.4f", key="prism_lon")
        prism_location_label = st.text_input("Location label (optional)", key="prism_location_label",
                                              placeholder="e.g. San Francisco") or f"{prism_lat:.4f}, {prism_lon:.4f}"

    if not in_conus(prism_lat, prism_lon):
        st.error("That point falls outside PRISM's CONUS grid -- pick a point within the "
                 "contiguous US (Alaska, Hawaii, and offshore points aren't covered).")

    with st.expander(f"ℹ️ Location info — {prism_location_label}"):
        try:
            info = fetch_location_info(prism_lat, prism_lon)
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
        prism_range_key = st.selectbox("Time step", [v for _, v in RANGE_OPTIONS], key="prism_range",
                                        format_func=lambda v: {val: lbl for lbl, val in RANGE_OPTIONS}.get(v, v))
    with c2:
        prism_units = st.selectbox("Units", [v for _, v in PRISM_UNITS_OPTIONS], key="prism_units",
                                    format_func=lambda v: {val: lbl for lbl, val in PRISM_UNITS_OPTIONS}.get(v, v))
    with c3:
        prism_resolution = st.selectbox("Grid resolution", [v for _, v in RESOLUTION_OPTIONS], key="prism_resolution",
                                         format_func=lambda v: {val: lbl for lbl, val in RESOLUTION_OPTIONS}.get(v, v))

    _prism_min_dates = {"daily": dt.date(1981, 1, 1), "monthly": dt.date(1895, 1, 1), "yearly": dt.date(1895, 1, 1)}
    _prism_default_end = dt.date.today() - dt.timedelta(days=3)  # PRISM's most recent data lags a few days
    prism_min_date = _prism_min_dates[prism_range_key]

    c4, c5 = st.columns(2)
    with c4:
        prism_begin_date = st.date_input(
            "Begin date", value=max(prism_min_date, _prism_default_end - dt.timedelta(days=365 * 3)),
            min_value=prism_min_date, max_value=_prism_default_end, key="prism_begin_date")
    with c5:
        prism_end_date = st.date_input("End date", value=_prism_default_end, min_value=prism_min_date,
                                        max_value=_prism_default_end, key="prism_end_date")

    prism_item_labels = st.multiselect("Variables", [lbl for lbl, _ in VARIABLES],
                                        default=["Precipitation", "Mean Temperature"], key="prism_items")

    prism_title = st.text_input("Chart title (optional)", key="prism_title",
                                 placeholder="e.g. San Francisco Precipitation")

    if st.button("Fetch Data", type="primary", key="prism_fetch"):
        if not in_conus(prism_lat, prism_lon):
            st.error("Pick a point inside PRISM's CONUS grid before fetching.")
            st.stop()
        if not prism_item_labels:
            st.error("Pick at least one variable.")
            st.stop()
        if prism_begin_date > prism_end_date:
            st.error("Begin date must be on or before end date.")
            st.stop()

        prism_item_labels_codes = [(lbl, code) for lbl, code in VARIABLES if lbl in prism_item_labels]

        try:
            progress_bar = st.progress(0.0, text="Fetching PRISM data...")

            def _on_prism_progress(done, total, label):
                progress_bar.progress(done / total, text=f"Fetching {label} ({done}/{total})...")

            df = fetch_prism_timeseries(
                prism_lat, prism_lon, prism_range_key, prism_begin_date, prism_end_date,
                prism_item_labels_codes, prism_units, prism_resolution,
                progress_callback=_on_prism_progress,
            )
            progress_bar.empty()

            if df.empty:
                st.error("No data was returned for that location/date range combination.")
                st.stop()

            st.session_state["prism_result"] = dict(
                df=df, location_label=prism_location_label, lat=prism_lat, lon=prism_lon,
                item_labels=prism_item_labels, units=prism_units, range_key=prism_range_key, title=prism_title,
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
        fig = prism_make_plot(df, r["location_label"], r["item_labels"], unit_label, r["title"],
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
