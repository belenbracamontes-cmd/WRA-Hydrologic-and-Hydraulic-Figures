"""USGS Data Retrieval -- Streamlit page.

General-purpose companion to the flow-specific USGS tools elsewhere in
this app (Peak Flow Viewer, Annual Flow Chart, LP3, Daily Flow & Duration
Analysis, Water Year Type -- all built around streamflow specifically).
This one pulls WHATEVER a given USGS station actually reports: gage
height / water-surface elevation, water temperature, specific
conductance, dissolved oxygen, turbidity, and more, in addition to
streamflow -- discovered live per station rather than assumed in
advance, the same way the NOAA page looks up which datums a station
supports before you commit to a fetch.

Two USGS services are involved (surfaced via a "Service" column, not
hidden): Daily Values (one aggregated value/day, can span decades) and
Instantaneous Values (raw sensor readings at their native interval, often
15 minutes -- this is usually where gage height/WSE lives, since it's
rarely computed as a daily statistic).
"""

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK
from core.style_options import render_chart_panel, render_data_color_pickers
from core.ui_helpers import render_copy_as_text
from core.annual_flow_chart import fetch_station_name
from core.usgs_data import DEFAULT_ITEM_COLOR, fetch_available_parameters, fetch_usgs_series, make_plot


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_catalog(site_no):
    return fetch_available_parameters(site_no)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_name(site_no):
    return fetch_station_name(site_no)


logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>USGS Data Retrieval</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Pull any data type a USGS station reports -- streamflow, gage height / "
               "water-surface elevation, temperature, water quality, and more.")

st.markdown(
    """
    Unlike the other USGS tools in this app (all built around streamflow specifically), this pulls
    **whatever a station actually has on file** -- enter a station ID below to see its full list of
    available data items, pick any combination, and they'll each get their own chart, stacked so
    you can compare them over the same time span.
    """
)

st.divider()
st.subheader("1. Station")

c1, c2 = st.columns(2)
with c1:
    station_id = st.text_input("Station ID", placeholder="e.g. 11447650", key="usgs_dr_station_id")
with c2:
    title = st.text_input("Chart title (optional)", key="usgs_dr_title",
                           placeholder="e.g. Sacramento River at Freeport")

st.subheader("2. Data items")

catalog = _cached_fetch_catalog(station_id.strip()) if station_id.strip() else []

if catalog:
    with st.expander(f"📏 What data does this station have? ({len(catalog)} series on file)"):
        cat_table = pd.DataFrame(catalog)[["label", "service", "begin_date", "end_date", "count"]].copy()
        cat_table["service"] = cat_table["service"].map({"dv": "Daily Values", "iv": "Instantaneous"})
        cat_table.columns = ["Data item", "Service", "Begin date", "End date", "# values"]
        st.dataframe(cat_table, use_container_width=True, hide_index=True)
        st.caption("\"Instantaneous\" items are raw sensor readings at their native reporting "
                   "interval (often 15 minutes) -- this is usually where gage height / "
                   "water-surface elevation lives, since it's rarely computed as a daily statistic.")
elif station_id.strip():
    st.caption("⚠️ Couldn't find any daily-value or instantaneous-value data series for this "
               "station -- double-check the station ID.")
else:
    st.info("Enter a station ID above to see what data it has on file.")

item_options = [c["label"] for c in catalog]
item_labels = st.multiselect(
    "Data items", item_options, default=item_options[:1] if item_options else [], key="usgs_dr_items",
)

st.subheader("3. Options")
c1, c2 = st.columns(2)
with c1:
    _default_end = dt.date.today()
    begin_date = st.date_input("Begin date", value=_default_end - dt.timedelta(days=365),
                                min_value=dt.date(1900, 1, 1), max_value=_default_end,
                                key="usgs_dr_begin_date")
with c2:
    end_date = st.date_input("End date", value=_default_end, min_value=dt.date(1900, 1, 1),
                              max_value=_default_end, key="usgs_dr_end_date")

selected_items = [c for c in catalog if c["label"] in item_labels]
has_iv_selection = any(c["service"] == "iv" for c in selected_items)
if has_iv_selection and (end_date - begin_date).days > 400:
    st.caption("⚠️ At least one selected item is Instantaneous (native reporting interval, often "
               "15 minutes) -- fetching more than about a year of it at once can be slow and "
               "return a very large amount of data.")

if st.button("Fetch Data", type="primary", key="usgs_dr_fetch"):
    if not station_id.strip():
        st.error("Enter a Station ID.")
        st.stop()
    if not selected_items:
        st.error("Pick at least one data item.")
        st.stop()
    if begin_date > end_date:
        st.error("Begin date must be on or before end date.")
        st.stop()

    try:
        progress_bar = st.progress(0.0, text="Fetching USGS data...")

        def _on_progress(done, total, label):
            progress_bar.progress(done / total, text=f"Fetching {label} ({done}/{total})...")

        series = fetch_usgs_series(station_id.strip(), selected_items, begin_date, end_date,
                                    progress_callback=_on_progress)
        progress_bar.empty()

        if not series:
            st.error("No data was returned for that station/date range/item combination. "
                     "Double-check the date range against the item's begin/end dates above.")
            st.stop()

        station_name = _cached_fetch_name(station_id.strip())
        st.session_state["usgs_dr_result"] = dict(
            series=series, station_label=station_name, station_id=station_id.strip(), title=title,
        )
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.stop()

if "usgs_dr_result" in st.session_state:
    r = st.session_state["usgs_dr_result"]
    series = r["series"]

    st.divider()
    st.subheader(f"📈 {r['station_label']} (Station {r['station_id']})")
    st.caption(", ".join(f"{label}: {len(df):,} rows" for label, df in series.items()))

    color_overrides = render_data_color_pickers(
        [{"label": label, "color": DEFAULT_ITEM_COLOR} for label in series],
        key_prefix="usgs_dr_chart",
    )
    fig = make_plot(series, r["station_label"], custom_title=r["title"], colors=color_overrides)
    axis_specs = [(ax, ["x", "y"], color_overrides.get(label, DEFAULT_ITEM_COLOR))
                   for ax, label in zip(fig.axes, series.keys())]
    render_chart_panel(fig, key_prefix="usgs_dr_chart", base_filename=f"usgs_{r['station_id']}",
                        axis_specs=axis_specs)

    st.divider()
    st.subheader("Data table")
    # One column per data item (wide format) -- items are merged on Date,
    # so an item with no reading at another item's exact timestamp (e.g.
    # a daily value next to a 15-minute instantaneous one) just shows
    # blank there rather than forcing everything onto a single frequency.
    wide = None
    for label, df in series.items():
        d = df.rename(columns={"value": label})[["Date", label]]
        wide = d if wide is None else wide.merge(d, on="Date", how="outer")
    wide = wide.sort_values("Date").reset_index(drop=True)

    st.dataframe(wide, use_container_width=True, hide_index=True, height=400)

    csv_bytes = wide.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV", data=csv_bytes,
        file_name=f"usgs_{r['station_id']}.csv", mime="text/csv", key="usgs_dr_csv_download",
    )

    render_copy_as_text(wide, key_prefix="usgs_dr", anchor_cols=("Date",))
else:
    st.info("Enter a station ID, pick data items and a date range above, then click "
             "**Fetch Data** to get started.")
