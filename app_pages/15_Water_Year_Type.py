"""Water Year Type Classifier -- Streamlit page.

Ported from a one-off notebook that classified water years for one
watershed (Santa Clara River) into Critical/Dry/Normal/Wet/Very Wet using
a hardcoded annual-precipitation record and fixed inch-based thresholds
computed externally. Generalized here into a real USGS station tool,
matching the conventions of the other "USGS station tools" pages:

  - Any USGS station ID works -- classification is computed fresh from
    that station's own annual mean flow (pulled the same way the Annual
    Flow Chart page does), split into quintiles (lowest 20% of years on
    record = Critical, highest 20% = Very Wet), not fixed band edges.
  - Two chart views (never both on screen at once, per the app's usual
    "one chart" rule): the actual annual-flow bars colored by category
    (closest to the notebook's real deliverable), or a categorical 1-5
    "wetness scale" bar chart (the notebook's other, unused cell).
  - Colors default to the notebook's own hex values, which are exact WRA
    brand colors -- customizable in the usual "Customize & export" panel.
"""

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK
from core.style_options import render_chart_panel, render_data_color_pickers
from core.annual_flow_chart import fetch_annual_avg_flow, fetch_station_name
from core.water_year_type import (
    CATEGORIES, CATEGORY_COLORS, MIN_YEARS_FOR_CLASSIFICATION, RECOMMENDED_MIN_YEARS,
    classify_water_years, make_flow_plot, make_wetness_plot,
)

_CURRENT_YEAR = dt.date.today().year


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_avg(site_no, start_wy, end_wy):
    return fetch_annual_avg_flow(site_no, start_wy, end_wy)


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
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Water Year Type Classifier</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Classify each water year as Critical / Dry / Normal / Wet / Very Wet from a "
               "USGS station's own annual flow record.")

st.markdown(
    f"""
    Pulls annual mean discharge from the same USGS statistics service the
    [Annual Flow Chart](/annual-flow-chart) page uses, then splits that station's own years into
    5 equal-count groups by flow (quintiles) -- the driest fifth of years on record become
    **Critical**, the next **Dry**, the middle **Normal**, then **Wet**, and the wettest fifth
    **Very Wet**. Thresholds are computed fresh from whatever station and year range you pick,
    not fixed in advance. Needs at least {MIN_YEARS_FOR_CLASSIFICATION} years of data to split at
    all ({RECOMMENDED_MIN_YEARS}+ recommended for the split to mean much statistically).
    """
)

st.divider()
st.subheader("1. Station")

c1, c2 = st.columns(2)
with c1:
    station_id = st.text_input("Station ID", placeholder="e.g. 11164500", key="wyt_station_id")
with c2:
    title = st.text_input("Chart title (optional)", key="wyt_title",
                           placeholder="e.g. San Francisquito Ck Water Year Type")

st.subheader("2. Options")
custom_range = st.toggle(
    "Customize water year range (default: show all available data)",
    key="wyt_custom_range",
)
start_wy, end_wy = 1900, _CURRENT_YEAR + 1
if custom_range:
    start_wy, end_wy = st.slider(
        "Water year range", min_value=1900, max_value=_CURRENT_YEAR + 1,
        value=(1900, _CURRENT_YEAR + 1), key="wyt_year_range",
    )

run = st.button("Classify", type="primary")

if run:
    site_no = station_id.strip()
    if not site_no:
        st.error("Enter a Station ID.")
        st.stop()

    try:
        with st.spinner(f"Fetching annual mean flow for station {site_no}..."):
            df = _cached_fetch_avg(site_no, int(start_wy), int(end_wy))

        if df.empty:
            st.error(
                f"No annual mean flow data found for station {site_no} in "
                f"WY{start_wy}–{end_wy}. This USGS statistics service doesn't cover every "
                "station -- double-check the station ID, or try a different year range."
            )
            st.stop()

        df, band_edges = classify_water_years(df, "avg_flow_cfs")
        station_name = _cached_fetch_name(site_no)

        st.session_state["wyt_result"] = dict(
            df=df, band_edges=band_edges, station_id=site_no,
            station_name=station_name, title=title,
        )
    except ValueError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.stop()

if "wyt_result" in st.session_state:
    r = st.session_state["wyt_result"]
    df = r["df"]
    band_edges = r["band_edges"]
    station_label = r["station_name"] or f"USGS Station {r['station_id']}"

    st.divider()
    st.subheader(f"📈 {station_label} (Station {r['station_id']})")
    st.caption(f"{len(df):,} classified water years — "
               f"WY{int(df['water_year'].min())}–WY{int(df['water_year'].max())}")
    if len(df) < RECOMMENDED_MIN_YEARS:
        st.warning(
            f"Only {len(df)} years went into this split -- fewer than the "
            f"{RECOMMENDED_MIN_YEARS} recommended for a statistically meaningful quintile "
            "classification. Treat the categories with caution, or widen the year range."
        )

    chart_type = st.selectbox(
        "Chart type", ["Actual annual flow", "Water year type scale"], key="wyt_chart_type",
    )

    color_series = [{"label": cat, "color": CATEGORY_COLORS[cat]} for cat in CATEGORIES]
    color_overrides = render_data_color_pickers(color_series, key_prefix="wyt_chart")

    if chart_type == "Actual annual flow":
        fig = make_flow_plot(df, station_label, band_edges, custom_title=r["title"],
                              colors=color_overrides)
    else:
        fig = make_wetness_plot(df, station_label, custom_title=r["title"], colors=color_overrides)

    axis_specs = [(fig.axes[0], ["x", "y"], None)]
    render_chart_panel(fig, key_prefix="wyt_chart", base_filename=f"water_year_type_{r['station_id']}",
                        axis_specs=axis_specs)

    st.divider()
    st.subheader("Classification table")
    display_df = df.rename(columns={
        "water_year": "Water Year", "avg_flow_cfs": "Annual Mean Flow (cfs)",
        "WaterYearType": "Water Year Type", "WetnessValue": "Wetness (1-5)",
    })[["Water Year", "Annual Mean Flow (cfs)", "Water Year Type", "Wetness (1-5)"]]
    st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)

    with st.expander("📏 Computed water year type bands (this station, this year range)"):
        band_rows = [
            {"Water Year Type": cat, "Annual Mean Flow range (cfs)": f"{lo:,.1f} – {hi:,.1f}"}
            for cat, (lo, hi) in band_edges.items()
        ]
        st.dataframe(pd.DataFrame(band_rows), use_container_width=True, hide_index=True)

    csv_bytes = display_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV", data=csv_bytes,
        file_name=f"water_year_type_{r['station_id']}.csv",
        mime="text/csv", key="wyt_csv_download",
    )
else:
    st.info("Enter a station ID above and click **Classify** to get started.")
