"""Daily Flow & Duration Analysis -- Streamlit page.

Ported from five tkinter/ipywidgets notebook GUIs (the "Daily Flow and
Range" section of the source notebook), grouped here as five tabs on one
page rather than five separate sidebar pages:

  1. Historical Daily Flow Range Viewer -- min/max band + mean daily flow.
  2. Streamflow Duration Hydrograph -- daily percentiles (single station).
  3. Streamflow Duration Hydrograph -- daily percentiles (combined 2-station).
  4. Weibull Flow-Duration Analysis -- single station, optional 2nd overlay.
  5. Weibull Flow-Duration Analysis -- combined 2-station, month/day window.

Each tab has its own controls (Streamlit doesn't support per-tab sidebars),
its own "Run"/"Fetch" buttons that cache fetched data in session_state, its
own presentation-styling panel, and its own SVG download -- matching the
conventions of the other three tool pages.
"""

import calendar
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK, TERRACOTA, OCEAN_BLUE
from core.view_source import render_view_source
from core.export import render_figure_download
from core.style_options import restyle_annotations, ANNOTATION_PRESETS
from core.ui_helpers import toggle_button

from core import daily_flow_range as dfr
from core import duration_hydrograph_single as dh1
from core import duration_hydrograph_combined as dh2
from core import weibull_flow_duration as wfd
from core import weibull_flow_duration_combined as wfc

_CURRENT_YEAR = dt.date.today().year
_MONTH_ABBRS = [calendar.month_abbr[m] for m in range(1, 13)]
_MONTH_ABBR_TO_NUM = {calendar.month_abbr[m]: m for m in range(1, 13)}


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_dfr(site_no, start, end):
    return dfr.fetch_site_daily_flow(site_no, start, end)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_percentiles(site_no, start_wy, end_wy):
    return dh1.fetch_daily_percentiles(site_no, start_wy, end_wy)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_daily_flow_dh1(site_no, start, end):
    return dh1.fetch_daily_flow(site_no, start, end)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_full_dh2(site_no):
    return dh2.fetch_full_daily_flow(site_no)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_full_wfd(site_no):
    return wfd.fetch_full_daily_flow(site_no)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch_full_wfc(site_no):
    return wfc.fetch_full_daily_flow(site_no)


def _styling_and_download(fig, axis_specs, base_filename, key_prefix, label="Download chart"):
    """Shared presentation-styling panel + SVG download, used by every tab."""
    st.subheader("🎨 Presentation styling (optional)")
    preset = st.selectbox(
        "Annotation color (title, axis labels, ticks, borders, legend)",
        list(ANNOTATION_PRESETS.keys()),
        index=1,  # default: Black -- matches the plot's current look
        key=f"{key_prefix}_annotation_preset",
    )
    restyle_annotations(fig, preset, axis_specs)
    st.pyplot(fig, use_container_width=True)
    render_figure_download(fig, base_filename, key_prefix=key_prefix, label=label)


logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=180)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>Daily Flow & Duration Analysis</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Five related USGS daily-flow tools, grouped into one page.")

tab_dfr, tab_dh1, tab_dh2, tab_wfd, tab_wfc = st.tabs([
    "🌊 Daily Flow Range",
    "📊 Duration Hydrograph",
    "📊 Duration Hydrograph (Combined)",
    "📉 Weibull Flow-Duration",
    "📉 Weibull Flow-Duration (Combined)",
])

# =============================================================================
# Tab 1 -- Historical Daily Flow Range Viewer
# =============================================================================
with tab_dfr:
    st.subheader("Historical Daily Flow Range Viewer")
    st.caption("Min-max band + mean daily flow for one or two USGS gauges, aligned onto a single water-year timeline.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        dfr_s1_id = st.text_input("Station 1 ID", placeholder="e.g. 11464000", key="dfr_s1_id")
    with c2:
        dfr_s1_color = st.color_picker("Color", TERRACOTA, key="dfr_s1_color")
    with c3:
        dfr_s1_style = st.selectbox("Line style", ["-", "--", "-.", ":"], key="dfr_s1_style",
                                     format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                             "-.": "Dash-dot", ":": "Dotted"}[v])
    with c4:
        dfr_s1_label = st.text_input("Label (optional)", key="dfr_s1_label", placeholder="Station 1 name")

    dfr_compare = toggle_button("+ Compare a second station", "− Remove second station",
                                 key="dfr_compare")
    dfr_s2_id, dfr_s2_color, dfr_s2_style, dfr_s2_label = "", OCEAN_BLUE, "-", ""
    if dfr_compare:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            dfr_s2_id = st.text_input("Station 2 ID", placeholder="e.g. 11465350", key="dfr_s2_id")
        with c2:
            dfr_s2_color = st.color_picker("Color", OCEAN_BLUE, key="dfr_s2_color")
        with c3:
            dfr_s2_style = st.selectbox("Line style", ["-", "--", "-.", ":"], key="dfr_s2_style",
                                         format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                 "-.": "Dash-dot", ":": "Dotted"}[v])
        with c4:
            dfr_s2_label = st.text_input("Label (optional)", key="dfr_s2_label", placeholder="Station 2 name")

    dfr_custom_years = st.checkbox(
        "Specify water year range (uncheck to use all available data)", key="dfr_custom_years",
    )
    dfr_wy_start, dfr_wy_end = 1991, _CURRENT_YEAR
    if dfr_custom_years:
        c1, c2 = st.columns(2)
        with c1:
            dfr_wy_start = st.number_input("History start (WY)", min_value=1900, max_value=_CURRENT_YEAR + 1,
                                            value=1991, key="dfr_wy_start")
        with c2:
            dfr_wy_end = st.number_input("End water year", min_value=1900, max_value=_CURRENT_YEAR + 1,
                                          value=_CURRENT_YEAR, key="dfr_wy_end")

    c1, c2 = st.columns(2)
    with c1:
        dfr_title = st.text_input("Title (optional)", key="dfr_title", placeholder="e.g. Hydrologic Year Daily Flow")
    with c2:
        dfr_log = st.checkbox("Log scale (y-axis)", value=True, key="dfr_log")

    dfr_avg_toggle = st.checkbox("Show monthly average line", key="dfr_avg_toggle")
    dfr_avg_color, dfr_avg_style = "#000000", "-"
    if dfr_avg_toggle:
        c1, c2 = st.columns(2)
        with c1:
            dfr_avg_color = st.color_picker("Monthly average color", "#000000", key="dfr_avg_color")
        with c2:
            dfr_avg_style = st.selectbox("Monthly average line style", ["-", "--", "-.", ":"],
                                          key="dfr_avg_style",
                                          format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                  "-.": "Dash-dot", ":": "Dotted"}[v])

    if st.button("Run", type="primary", key="dfr_run"):
        if not dfr_s1_id.strip():
            st.error("Enter a Station ID for Station 1.")
            st.stop()
        try:
            stations = [{
                "id": dfr_s1_id.strip(), "color": dfr_s1_color, "line_style": dfr_s1_style,
                "label": dfr_s1_label.strip(),
            }]
            if dfr_compare and dfr_s2_id.strip():
                stations.append({
                    "id": dfr_s2_id.strip(), "color": dfr_s2_color, "line_style": dfr_s2_style,
                    "label": dfr_s2_label.strip(),
                })

            if not dfr_custom_years:
                history_start, end_date_str = "1900-01-01", None
            else:
                if dfr_wy_start > dfr_wy_end:
                    st.error("History start (WY) must be <= End water year.")
                    st.stop()
                history_start = f"{int(dfr_wy_start) - 1}-10-01"
                end_date_str = f"{int(dfr_wy_end)}-09-30"

            raw_data = {}
            for s in stations:
                with st.spinner(f"Fetching station {s['id']}..."):
                    raw_data[s["id"]] = _cached_fetch_dfr(s["id"], history_start, end_date_str)

            if not dfr_custom_years:
                all_wy = pd.concat([raw["date"].apply(dfr.water_year_of) for raw in raw_data.values()])
                wy_start, wy_end = int(all_wy.min()), int(all_wy.max())
            else:
                wy_start, wy_end = int(dfr_wy_start), int(dfr_wy_end)

            datasets = []
            for s in stations:
                raw = raw_data[s["id"]]
                monthly_avg = dfr.build_monthly_avg_series(raw, wy_end) if dfr_avg_toggle else None
                datasets.append({
                    "stats": dfr.process_site(raw, wy_end),
                    "station_id": s["id"],
                    "label": s["label"] or f"Site {s['id']}",
                    "color": s["color"],
                    "line_style": s["line_style"],
                    "monthly_avg": monthly_avg,
                    "monthly_avg_color": dfr_avg_color,
                    "monthly_avg_style": dfr_avg_style,
                })

            st.session_state["dfr_datasets"] = datasets
            st.session_state["dfr_raw_data"] = raw_data
            st.session_state["dfr_settings"] = dict(wy_start=wy_start, wy_end=wy_end,
                                                      use_log=dfr_log, title=dfr_title)
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            st.stop()

    if "dfr_datasets" in st.session_state:
        datasets = st.session_state["dfr_datasets"]
        settings = st.session_state["dfr_settings"]
        raw_data = st.session_state["dfr_raw_data"]

        fig = dfr.make_plot(datasets, settings["wy_start"], settings["wy_end"],
                             settings["use_log"], settings["title"])
        st.pyplot(fig, use_container_width=True)

        axis_specs = [(fig.axes[0], ["x", "y"], datasets[0]["color"])]
        _styling_and_download(fig, axis_specs, "daily_flow_range", key_prefix="dfr_chart")

        for d in datasets:
            raw = raw_data[d["station_id"]]
            total_start, total_end = dfr.fetch_period_of_record(d["station_id"])
            with st.expander(f"Monthly summary -- {d['label']} (USGS {d['station_id']})"):
                st.dataframe(dfr.build_summary_table(raw, total_start, total_end), use_container_width=True)
    else:
        st.info("Enter a station ID above and click **Run** to get started.")

# =============================================================================
# Tab 2 -- Streamflow Duration Hydrograph (single station)
# =============================================================================
with tab_dh1:
    st.subheader("Streamflow Duration Hydrograph -- Daily Percentiles")
    st.caption("Percentile bands (3-7, your choice) from the USGS NWIS daily statistics service, plus an optional single-year overlay.")

    c1, c2 = st.columns(2)
    with c1:
        dh1_site = st.text_input("Station ID", placeholder="e.g. 11169500", key="dh1_site")
    with c2:
        dh1_label = st.text_input("Label (optional)", key="dh1_label",
                                   placeholder="e.g. San Francisquito Ck at Stanford")

    dh1_year_type = st.selectbox("Year type", ["water", "calendar"], key="dh1_year_type",
                                  format_func=lambda v: "Water Year (Oct-Sep)" if v == "water"
                                  else "Calendar Year (Jan-Dec)")

    dh1_show_year = st.checkbox("Overlay a specific year's daily flow", key="dh1_show_year")
    dh1_plot_year, dh1_year_color, dh1_year_style = dh1.water_year_of(dt.date.today()), "#000000", "-"
    if dh1_show_year:
        c1, c2, c3 = st.columns(3)
        with c1:
            dh1_plot_year = st.number_input("Year to plot", min_value=1900, max_value=_CURRENT_YEAR + 1,
                                             value=dh1.water_year_of(dt.date.today()), key="dh1_plot_year")
        with c2:
            dh1_year_color = st.color_picker("Overlay color", "#000000", key="dh1_year_color")
        with c3:
            dh1_year_style = st.selectbox("Overlay line style", ["-", "--", "-.", ":"], key="dh1_year_style",
                                           format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                   "-.": "Dash-dot", ":": "Dotted"}[v])

    c1, c2, c3 = st.columns(3)
    with c1:
        dh1_nbands = st.selectbox("# of bands", [3, 4, 5, 6, 7], index=4, key="dh1_nbands")
    with c2:
        dh1_palette = st.selectbox("Color palette", [v for _, v in dh1.DUR_PALETTE_LABELS],
                                    key="dh1_palette",
                                    format_func=lambda v: {val: lbl for lbl, val in dh1.DUR_PALETTE_LABELS}.get(v, v))
    with c3:
        st.markdown("&nbsp;")
        st.markdown(dh1.palette_swatch_html(dh1_palette, dh1_nbands), unsafe_allow_html=True)

    dh1_log = st.checkbox("Log scale (y-axis)", value=True, key="dh1_log")

    dh1_median = st.checkbox("Show median (P50) line", value=True, key="dh1_median")
    dh1_median_color, dh1_median_style = "#FFFFFF", "--"
    if dh1_median:
        c1, c2 = st.columns(2)
        with c1:
            dh1_median_color = st.color_picker("Median color", "#FFFFFF", key="dh1_median_color")
        with c2:
            dh1_median_style = st.selectbox("Median line style", ["-", "--", "-.", ":"], key="dh1_median_style",
                                             index=1,
                                             format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                     "-.": "Dash-dot", ":": "Dotted"}[v])

    dh1_monthly_avg = st.checkbox("Show monthly average line", key="dh1_monthly_avg")
    dh1_monthly_avg_color, dh1_monthly_avg_style = "#000000", "-."
    if dh1_monthly_avg:
        c1, c2 = st.columns(2)
        with c1:
            dh1_monthly_avg_color = st.color_picker("Monthly average color", "#000000", key="dh1_monthly_avg_color")
        with c2:
            dh1_monthly_avg_style = st.selectbox("Monthly average line style", ["-", "--", "-.", ":"],
                                                  key="dh1_monthly_avg_style", index=2,
                                                  format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                          "-.": "Dash-dot", ":": "Dotted"}[v])

    dh1_custom_years = st.checkbox(
        "Specify years for historical percentiles (default: full period of record)", key="dh1_custom_years",
    )
    dh1_hist_start, dh1_hist_end = 1990, _CURRENT_YEAR
    if dh1_custom_years:
        c1, c2 = st.columns(2)
        with c1:
            dh1_hist_start = st.number_input("History start", min_value=1900, max_value=_CURRENT_YEAR + 1,
                                              value=1990, key="dh1_hist_start")
        with c2:
            dh1_hist_end = st.number_input("History end", min_value=1900, max_value=_CURRENT_YEAR + 1,
                                            value=_CURRENT_YEAR, key="dh1_hist_end")

    dh1_title = st.text_input("Title (optional)", key="dh1_title",
                               placeholder="e.g. Streamflow Percentiles - Site 11169500")

    if st.button("Run", type="primary", key="dh1_run"):
        site_no = dh1_site.strip()
        if not site_no:
            st.error("Enter a Station ID.")
            st.stop()
        try:
            if dh1_show_year:
                plot_year = int(dh1_plot_year)
            else:
                plot_year = (dh1.water_year_of(dt.date.today()) if dh1_year_type == "water"
                             else dt.date.today().year)

            if dh1_custom_years:
                if dh1_hist_start > dh1_hist_end:
                    st.error("History start must be <= History end.")
                    st.stop()
                hist_start_wy, hist_end_wy = int(dh1_hist_start), int(dh1_hist_end)
            else:
                hist_start_wy, hist_end_wy = None, None

            with st.spinner("Fetching historical percentiles..."):
                pctl = _cached_fetch_percentiles(site_no, hist_start_wy, hist_end_wy)
            pctl = pctl.copy()
            pctl["plot_date"] = pctl.apply(
                lambda r: dh1.plot_date(r["month_nu"], r["day_nu"], plot_year, dh1_year_type), axis=1)
            pctl["plot_date"] = pd.to_datetime(pctl["plot_date"])
            pctl = pctl.sort_values("plot_date")

            flow = None
            if dh1_show_year:
                with st.spinner("Fetching daily mean flow for selected year..."):
                    if dh1_year_type == "water":
                        start, end = f"{plot_year - 1}-10-01", f"{plot_year}-09-30"
                    else:
                        start, end = f"{plot_year}-01-01", f"{plot_year}-12-31"
                    flow = _cached_fetch_daily_flow_dh1(site_no, start, end)
                flow = flow.copy()
                flow["plot_date"] = flow["date"].apply(
                    lambda d: dh1.plot_date(d.month, d.day, plot_year, dh1_year_type))
                flow["plot_date"] = pd.to_datetime(flow["plot_date"])
                flow = flow.sort_values("plot_date")

            site_label = dh1_label.strip() or dh1.fetch_station_name(site_no)

            monthly_avg_series = None
            if dh1_monthly_avg:
                monthly_avg_series = dh1.build_monthly_avg_series(pctl, plot_year, dh1_year_type)

            st.session_state["dh1_result"] = dict(
                pctl=pctl, flow=flow, site_label=site_label, site_no=site_no,
                year_type=dh1_year_type, plot_year=plot_year, use_log=dh1_log,
                palette=dh1_palette, show_median=dh1_median, n_bands=dh1_nbands,
                title=dh1_title, median_color=dh1_median_color, median_style=dh1_median_style,
                year_color=dh1_year_color, year_style=dh1_year_style,
                show_monthly_avg=dh1_monthly_avg, monthly_avg_color=dh1_monthly_avg_color,
                monthly_avg_style=dh1_monthly_avg_style, monthly_avg_series=monthly_avg_series,
                custom_years=dh1_custom_years, hist_start_wy=hist_start_wy, hist_end_wy=hist_end_wy,
            )
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            st.stop()

    if "dh1_result" in st.session_state:
        r = st.session_state["dh1_result"]
        fig = dh1.make_plot(
            r["pctl"], r["flow"], r["site_label"], r["year_type"], r["plot_year"],
            r["use_log"], r["palette"], r["show_median"], r["n_bands"], r["title"],
            median_color=r["median_color"], median_style=r["median_style"],
            year_color=r["year_color"], year_style=r["year_style"],
            show_monthly_avg=r["show_monthly_avg"], monthly_avg_color=r["monthly_avg_color"],
            monthly_avg_style=r["monthly_avg_style"], monthly_avg_series=r["monthly_avg_series"],
        )
        st.pyplot(fig, use_container_width=True)

        axis_specs = [(fig.axes[0], ["x", "y"], None)]
        _styling_and_download(fig, axis_specs, "duration_hydrograph", key_prefix="dh1_chart")

        if r["custom_years"]:
            total_start_wy, total_end_wy = dh1.fetch_period_of_record(r["site_no"])
        else:
            total_start_wy = int(r["pctl"]["begin_yr"].min())
            total_end_wy = int(r["pctl"]["end_yr"].max())
        with st.expander(f"Monthly summary -- {r['site_label']} (USGS {r['site_no']})"):
            st.dataframe(dh1.build_summary_table(r["pctl"], total_start_wy, total_end_wy),
                         use_container_width=True)
    else:
        st.info("Enter a station ID above and click **Run** to get started.")

# =============================================================================
# Tab 3 -- Streamflow Duration Hydrograph (combined 2-station)
# =============================================================================
with tab_dh2:
    st.subheader("Streamflow Duration Hydrograph -- Combined Two-Station Percentiles")
    st.caption("Sums the daily flow of two stations (e.g. two tributaries above a confluence) and computes percentile bands locally.")

    c1, c2 = st.columns(2)
    with c1:
        dh2_site1 = st.text_input("Station 1 ID", placeholder="e.g. 11169500", key="dh2_site1")
    with c2:
        dh2_site2 = st.text_input("Station 2 ID", placeholder="e.g. 11169800", key="dh2_site2")
    dh2_label = st.text_input("Label (optional)", key="dh2_label",
                               placeholder="e.g. Combined flow above confluence")

    dh2_year_type = st.selectbox("Year type", ["water", "calendar"], key="dh2_year_type",
                                  format_func=lambda v: "Water Year (Oct-Sep)" if v == "water"
                                  else "Calendar Year (Jan-Dec)")

    dh2_show_year = st.checkbox("Overlay a specific year's combined daily flow", key="dh2_show_year")
    dh2_plot_year, dh2_year_color, dh2_year_style = dh2.water_year_of(dt.date.today()), "#000000", "-"
    if dh2_show_year:
        c1, c2, c3 = st.columns(3)
        with c1:
            dh2_plot_year = st.number_input("Year to plot", min_value=1900, max_value=_CURRENT_YEAR + 1,
                                             value=dh2.water_year_of(dt.date.today()), key="dh2_plot_year")
        with c2:
            dh2_year_color = st.color_picker("Overlay color", "#000000", key="dh2_year_color")
        with c3:
            dh2_year_style = st.selectbox("Overlay line style", ["-", "--", "-.", ":"], key="dh2_year_style",
                                           format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                   "-.": "Dash-dot", ":": "Dotted"}[v])

    c1, c2, c3 = st.columns(3)
    with c1:
        dh2_nbands = st.selectbox("# of bands", [3, 4, 5, 6, 7], index=4, key="dh2_nbands")
    with c2:
        dh2_palette = st.selectbox("Color palette", [v for _, v in dh2.DUR_PALETTE_LABELS],
                                    key="dh2_palette",
                                    format_func=lambda v: {val: lbl for lbl, val in dh2.DUR_PALETTE_LABELS}.get(v, v))
    with c3:
        st.markdown("&nbsp;")
        st.markdown(dh2.palette_swatch_html(dh2_palette, dh2_nbands), unsafe_allow_html=True)

    dh2_log = st.checkbox("Log scale (y-axis)", value=True, key="dh2_log")

    dh2_median = st.checkbox("Show median (P50) line", value=True, key="dh2_median")
    dh2_median_color, dh2_median_style = "#FFFFFF", "--"
    if dh2_median:
        c1, c2 = st.columns(2)
        with c1:
            dh2_median_color = st.color_picker("Median color", "#FFFFFF", key="dh2_median_color")
        with c2:
            dh2_median_style = st.selectbox("Median line style", ["-", "--", "-.", ":"], key="dh2_median_style",
                                             index=1,
                                             format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                     "-.": "Dash-dot", ":": "Dotted"}[v])

    dh2_monthly_avg = st.checkbox("Show monthly average line", key="dh2_monthly_avg")
    dh2_monthly_avg_color, dh2_monthly_avg_style = "#000000", "-."
    if dh2_monthly_avg:
        c1, c2 = st.columns(2)
        with c1:
            dh2_monthly_avg_color = st.color_picker("Monthly average color", "#000000", key="dh2_monthly_avg_color")
        with c2:
            dh2_monthly_avg_style = st.selectbox("Monthly average line style", ["-", "--", "-.", ":"],
                                                  key="dh2_monthly_avg_style", index=2,
                                                  format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                          "-.": "Dash-dot", ":": "Dotted"}[v])

    dh2_custom_years = st.checkbox(
        "Specify water years for historical percentiles (default: full overlapping record)", key="dh2_custom_years",
    )
    dh2_hist_start, dh2_hist_end = 1990, _CURRENT_YEAR
    if dh2_custom_years:
        c1, c2 = st.columns(2)
        with c1:
            dh2_hist_start = st.number_input("History start (WY)", min_value=1900, max_value=_CURRENT_YEAR + 1,
                                              value=1990, key="dh2_hist_start")
        with c2:
            dh2_hist_end = st.number_input("History end (WY)", min_value=1900, max_value=_CURRENT_YEAR + 1,
                                            value=_CURRENT_YEAR, key="dh2_hist_end")

    dh2_title = st.text_input("Title (optional)", key="dh2_title",
                               placeholder="e.g. Combined Streamflow Percentiles")

    if st.button("Run", type="primary", key="dh2_run"):
        site1, site2 = dh2_site1.strip(), dh2_site2.strip()
        if not site1 or not site2:
            st.error("Enter both Station 1 and Station 2 IDs.")
            st.stop()
        try:
            if dh2_show_year:
                plot_year = int(dh2_plot_year)
            else:
                plot_year = (dh2.water_year_of(dt.date.today()) if dh2_year_type == "water"
                             else dt.date.today().year)

            with st.spinner(f"Fetching full daily history for Station {site1}..."):
                full1 = _cached_fetch_full_dh2(site1)
            with st.spinner(f"Fetching full daily history for Station {site2}..."):
                full2 = _cached_fetch_full_dh2(site2)
            with st.spinner("Combining both stations' daily flow..."):
                combined = dh2.combine_two_stations(full1, full2)

            if dh2_custom_years:
                if dh2_hist_start > dh2_hist_end:
                    st.error("History start (WY) must be <= History end (WY).")
                    st.stop()
                hist_start_wy, hist_end_wy = int(dh2_hist_start), int(dh2_hist_end)
            else:
                hist_start_wy, hist_end_wy = None, None

            pctl, rec_start_wy, rec_end_wy = dh2.compute_percentiles(combined, hist_start_wy, hist_end_wy)
            pctl["plot_date"] = pctl.apply(
                lambda r: dh2.plot_date(r["month_nu"], r["day_nu"], plot_year, dh2_year_type), axis=1)
            pctl["plot_date"] = pd.to_datetime(pctl["plot_date"])
            pctl = pctl.sort_values("plot_date")

            flow_year = None
            if dh2_show_year:
                if dh2_year_type == "water":
                    yr_start, yr_end = dt.date(plot_year - 1, 10, 1), dt.date(plot_year, 9, 30)
                else:
                    yr_start, yr_end = dt.date(plot_year, 1, 1), dt.date(plot_year, 12, 31)
                flow_year = combined[
                    (combined["date"].dt.date >= yr_start) & (combined["date"].dt.date <= yr_end)
                ].copy()
                if flow_year.empty:
                    yt_label = "water year" if dh2_year_type == "water" else "calendar year"
                    raise ValueError(f"No combined data available for {yt_label} {plot_year}.")
                flow_year["plot_date"] = flow_year["date"].apply(
                    lambda d: dh2.plot_date(d.month, d.day, plot_year, dh2_year_type))
                flow_year["plot_date"] = pd.to_datetime(flow_year["plot_date"])
                flow_year = flow_year.sort_values("plot_date")

            name1, name2 = dh2.fetch_station_name(site1), dh2.fetch_station_name(site2)
            combined_label = dh2_label.strip() or f"{name1} + {name2}"

            combined["water_year"] = combined["date"].apply(dh2.water_year_of)
            if hist_start_wy is not None:
                table_data = combined[(combined["water_year"] >= hist_start_wy)
                                       & (combined["water_year"] <= hist_end_wy)]
            else:
                table_data = combined

            monthly_avg_series = None
            if dh2_monthly_avg:
                monthly_avg_series = dh2.build_monthly_avg_series(table_data, plot_year, dh2_year_type)

            st.session_state["dh2_result"] = dict(
                pctl=pctl, flow_year=flow_year, combined_label=combined_label,
                site1=site1, site2=site2, table_data=table_data,
                rec_start_wy=rec_start_wy, rec_end_wy=rec_end_wy,
                year_type=dh2_year_type, plot_year=plot_year, use_log=dh2_log,
                palette=dh2_palette, show_median=dh2_median, n_bands=dh2_nbands,
                title=dh2_title, median_color=dh2_median_color, median_style=dh2_median_style,
                year_color=dh2_year_color, year_style=dh2_year_style,
                show_monthly_avg=dh2_monthly_avg, monthly_avg_color=dh2_monthly_avg_color,
                monthly_avg_style=dh2_monthly_avg_style, monthly_avg_series=monthly_avg_series,
            )
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            st.stop()

    if "dh2_result" in st.session_state:
        r = st.session_state["dh2_result"]
        fig = dh2.make_plot(
            r["pctl"], r["flow_year"], r["combined_label"], r["year_type"], r["plot_year"],
            r["use_log"], r["palette"], r["show_median"], r["n_bands"], r["title"],
            median_color=r["median_color"], median_style=r["median_style"],
            year_color=r["year_color"], year_style=r["year_style"],
            show_monthly_avg=r["show_monthly_avg"], monthly_avg_color=r["monthly_avg_color"],
            monthly_avg_style=r["monthly_avg_style"], monthly_avg_series=r["monthly_avg_series"],
        )
        st.pyplot(fig, use_container_width=True)

        axis_specs = [(fig.axes[0], ["x", "y"], None)]
        _styling_and_download(fig, axis_specs, "duration_hydrograph_combined", key_prefix="dh2_chart")

        total1 = dh2.fetch_period_of_record(r["site1"])
        total2 = dh2.fetch_period_of_record(r["site2"])
        with st.expander(f"Monthly summary -- {r['combined_label']}"):
            st.dataframe(
                dh2.build_summary_table(r["table_data"], r["site1"], r["site2"], total1, total2,
                                         r["rec_start_wy"], r["rec_end_wy"]),
                use_container_width=True,
            )
    else:
        st.info("Enter both station IDs above and click **Run** to get started.")

# =============================================================================
# Tab 4 -- Weibull Flow-Duration Analysis (single + optional overlay)
# =============================================================================
with tab_wfd:
    st.subheader("Weibull Flow-Duration Analysis")
    st.caption("Flow vs. Percent of Time Equaled or Exceeded, from the full daily-mean-flow record. "
               "An optional second station can be overlaid as its own independent curve (not combined).")

    c1, c2 = st.columns(2)
    with c1:
        wfd_site1 = st.text_input("Station 1 ID", placeholder="e.g. 11169500", key="wfd_site1")
    with c2:
        wfd_compare = toggle_button("+ Overlay a second station", "− Remove second station overlay",
                                     key="wfd_compare")
    wfd_site2 = ""
    if wfd_compare:
        wfd_site2 = st.text_input("Station 2 ID", placeholder="e.g. 11169800", key="wfd_site2")

    if st.button("Fetch Station Data", key="wfd_fetch"):
        site1 = wfd_site1.strip()
        if not site1:
            st.error("Enter a Station 1 ID first.")
            st.stop()
        try:
            with st.spinner(f"Fetching full daily history for Station {site1}..."):
                full_df1 = _cached_fetch_full_wfd(site1)
            name1 = wfd.fetch_station_name(site1)

            full_df2, site2, name2 = None, None, None
            if wfd_compare:
                site2 = wfd_site2.strip()
                if site2:
                    with st.spinner(f"Fetching full daily history for Station {site2}..."):
                        full_df2 = _cached_fetch_full_wfd(site2)
                    name2 = wfd.fetch_station_name(site2)

            all_dates = full_df1["date"]
            if full_df2 is not None:
                all_dates = pd.concat([all_dates, full_df2["date"]])
            wy_all = all_dates.apply(wfd.water_year_of)
            wy_min, wy_max = int(wy_all.min()), int(wy_all.max())

            st.session_state["wfd_fetched"] = dict(
                full_df1=full_df1, site1=site1, name1=name1,
                full_df2=full_df2, site2=site2, name2=name2,
                wy_min=wy_min, wy_max=wy_max,
            )
            st.session_state["wfd_year_slider"] = (wy_min, wy_max)
            st.session_state["wfd_months_sel"] = _MONTH_ABBRS.copy()
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            st.stop()

    if "wfd_fetched" in st.session_state:
        fetched = st.session_state["wfd_fetched"]
        if fetched["full_df2"] is not None:
            st.success(f"Loaded {fetched['name1']} ({fetched['site1']}) and "
                       f"{fetched['name2']} ({fetched['site2']}) -- "
                       f"WY{fetched['wy_min']}-WY{fetched['wy_max']} combined range.")
        else:
            st.success(f"Loaded {fetched['name1']} ({fetched['site1']}) -- "
                       f"WY{fetched['wy_min']}-WY{fetched['wy_max']}, "
                       f"{len(fetched['full_df1']):,} daily values.")

        st.markdown("**Water years to include:**")
        if "wfd_year_slider" not in st.session_state:
            st.session_state["wfd_year_slider"] = (fetched["wy_min"], fetched["wy_max"])
        wfd_year_range = st.slider("Water years", min_value=fetched["wy_min"], max_value=fetched["wy_max"],
                                    key="wfd_year_slider")

        st.markdown("**Months to include:**")
        if "wfd_months_sel" not in st.session_state:
            st.session_state["wfd_months_sel"] = _MONTH_ABBRS.copy()
        mc1, mc2, mc3 = st.columns([3, 1, 1])
        with mc1:
            wfd_months_sel = st.multiselect("Months", _MONTH_ABBRS, key="wfd_months_sel",
                                             label_visibility="collapsed")
        with mc2:
            st.button("Select all", key="wfd_months_all",
                      on_click=lambda: st.session_state.update(wfd_months_sel=_MONTH_ABBRS.copy()))
        with mc3:
            st.button("Clear all", key="wfd_months_clear",
                      on_click=lambda: st.session_state.update(wfd_months_sel=[]))

        c1, c2, c3 = st.columns(3)
        with c1:
            wfd_log = st.checkbox("Log scale (y-axis)", value=True, key="wfd_log")
        with c2:
            wfd_show_points = st.checkbox("Show individual daily points", key="wfd_show_points")
        with c3:
            wfd_show_markers = st.checkbox("Mark standard exceedance percentages", value=True, key="wfd_show_markers")

        c1, c2 = st.columns(2)
        with c1:
            wfd_curve1_color = st.color_picker("Station 1 color", BRAND_DARK, key="wfd_curve1_color")
            wfd_curve1_style = st.selectbox("Station 1 line style", ["-", "--", "-.", ":"], key="wfd_curve1_style",
                                             format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                     "-.": "Dash-dot", ":": "Dotted"}[v])
        wfd_curve2_color, wfd_curve2_style = "#B22222", "--"
        if wfd_compare:
            with c2:
                wfd_curve2_color = st.color_picker("Station 2 color", "#B22222", key="wfd_curve2_color")
                wfd_curve2_style = st.selectbox("Station 2 line style", ["-", "--", "-.", ":"],
                                                 key="wfd_curve2_style", index=1,
                                                 format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                         "-.": "Dash-dot", ":": "Dotted"}[v])

        wfd_title = st.text_input("Title (optional)", key="wfd_title",
                                   placeholder="e.g. Flow-Duration Curve - Station 11169500")

        if st.button("Run Analysis", type="primary", key="wfd_run"):
            try:
                start_wy, end_wy = wfd_year_range
                months = sorted(_MONTH_ABBR_TO_NUM[m] for m in wfd_months_sel)
                if not months:
                    st.error("Select at least one month.")
                    st.stop()

                filtered1 = wfd.filter_by_years_months(fetched["full_df1"], start_wy, end_wy, months)
                if filtered1.empty:
                    raise ValueError(
                        "No Station 1 daily values fall within the selected water-year range and month(s)."
                    )
                weibull1 = wfd.compute_weibull_table(filtered1)
                label1 = f"{fetched['name1']} ({fetched['site1']})"

                weibull2, label2 = None, None
                if wfd_compare and fetched["full_df2"] is not None:
                    filtered2 = wfd.filter_by_years_months(fetched["full_df2"], start_wy, end_wy, months)
                    if not filtered2.empty:
                        weibull2 = wfd.compute_weibull_table(filtered2)
                        label2 = f"{fetched['name2']} ({fetched['site2']})"

                st.session_state["wfd_result"] = dict(
                    weibull1=weibull1, label1=label1, weibull2=weibull2, label2=label2,
                    site1=fetched["site1"], site2=fetched["site2"],
                    start_wy=start_wy, end_wy=end_wy, months=months,
                    use_log=wfd_log, show_points=wfd_show_points, show_markers=wfd_show_markers,
                    curve1_color=wfd_curve1_color, curve1_style=wfd_curve1_style,
                    curve2_color=wfd_curve2_color, curve2_style=wfd_curve2_style,
                    title=wfd_title,
                )
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

    if "wfd_result" in st.session_state:
        r = st.session_state["wfd_result"]
        fig = wfd.make_plot(
            r["weibull1"], r["label1"], r["curve1_color"], r["curve1_style"],
            r["weibull2"], r["label2"], r["curve2_color"], r["curve2_style"],
            r["start_wy"], r["end_wy"], r["months"], r["use_log"],
            r["show_points"], r["show_markers"], r["title"],
        )
        st.pyplot(fig, use_container_width=True)

        axis_specs = [(fig.axes[0], ["x", "y"], None)]
        _styling_and_download(fig, axis_specs, "weibull_flow_duration", key_prefix="wfd_chart",
                               label="Download plot")

        st.markdown(f"**{r['label1']}** -- WY{r['start_wy']}-WY{r['end_wy']} -- "
                    f"n = {len(r['weibull1']):,} daily values")
        st.dataframe(wfd.summary_table(r["weibull1"]), use_container_width=True, hide_index=True)
        if r["weibull2"] is not None:
            st.markdown(f"**{r['label2']}** -- WY{r['start_wy']}-WY{r['end_wy']} -- "
                        f"n = {len(r['weibull2']):,} daily values")
            st.dataframe(wfd.summary_table(r["weibull2"]), use_container_width=True, hide_index=True)

        full_table = wfd.full_point_table(r["weibull1"], r["site1"], r["weibull2"], r["site2"])
        st.download_button(
            "Download full point set (CSV)",
            data=full_table.to_csv(index=False).encode("utf-8"),
            file_name="weibull_flow_duration_full.csv",
            mime="text/csv",
            key="wfd_csv_download",
        )
    elif "wfd_fetched" in st.session_state:
        st.info("Adjust the settings above and click **Run Analysis**.")
    else:
        st.info("Enter a Station 1 ID above and click **Fetch Station Data** to get started.")

# =============================================================================
# Tab 5 -- Weibull Flow-Duration Analysis (combined 2-station, month/day window)
# =============================================================================
with tab_wfc:
    st.subheader("Weibull Flow-Duration Analysis -- Combined Two-Station")
    st.caption("Sums two stations' daily flow, then runs a Weibull analysis over a water-year range and a "
               "recurring month/day window (e.g. Jun 15 - Sep 15) applied within every one of those water years.")

    c1, c2 = st.columns(2)
    with c1:
        wfc_site1 = st.text_input("Station 1 ID", placeholder="e.g. 11169500", key="wfc_site1")
    with c2:
        wfc_site2 = st.text_input("Station 2 ID", placeholder="e.g. 11169800", key="wfc_site2")
    wfc_label = st.text_input("Label (optional)", key="wfc_label",
                               placeholder="e.g. Combined flow above confluence")

    if st.button("Fetch & Combine Stations", key="wfc_fetch"):
        site1, site2 = wfc_site1.strip(), wfc_site2.strip()
        if not site1 or not site2:
            st.error("Enter both Station 1 and Station 2 IDs.")
            st.stop()
        try:
            with st.spinner(f"Fetching full daily history for Station {site1}..."):
                full1 = _cached_fetch_full_wfc(site1)
            with st.spinner(f"Fetching full daily history for Station {site2}..."):
                full2 = _cached_fetch_full_wfc(site2)
            with st.spinner("Combining both stations' daily flow..."):
                combined = wfc.combine_two_stations(full1, full2)

            name1, name2 = wfc.fetch_station_name(site1), wfc.fetch_station_name(site2)
            combined_label = wfc_label.strip() or f"{name1} + {name2}"

            wy_all = combined["date"].apply(wfc.water_year_of)
            wy_min, wy_max = int(wy_all.min()), int(wy_all.max())

            st.session_state["wfc_fetched"] = dict(
                combined=combined, site1=site1, site2=site2,
                combined_label=combined_label, wy_min=wy_min, wy_max=wy_max,
            )
            st.session_state["wfc_year_slider"] = (wy_min, wy_max)
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            st.stop()

    if "wfc_fetched" in st.session_state:
        fetched = st.session_state["wfc_fetched"]
        st.success(f"Loaded {fetched['combined_label']} -- overlapping record "
                   f"WY{fetched['wy_min']}-WY{fetched['wy_max']}, "
                   f"{len(fetched['combined']):,} combined daily values.")

        st.markdown("**Water years to include:**")
        if "wfc_year_slider" not in st.session_state:
            st.session_state["wfc_year_slider"] = (fetched["wy_min"], fetched["wy_max"])
        wfc_year_range = st.slider("Water years", min_value=fetched["wy_min"], max_value=fetched["wy_max"],
                                    key="wfc_year_slider")

        st.markdown("**Month/day window to apply within each selected water year:**")
        c1, c2 = st.columns(2)
        with c1:
            wfc_start_month = st.selectbox("Start month", list(range(1, 13)), index=9, key="wfc_start_month",
                                            format_func=lambda m: calendar.month_abbr[m])
            wfc_start_day = st.selectbox("Start day", list(range(1, 32)), index=0, key="wfc_start_day")
        with c2:
            wfc_end_month = st.selectbox("End month", list(range(1, 13)), index=8, key="wfc_end_month",
                                          format_func=lambda m: calendar.month_abbr[m])
            wfc_end_day = st.selectbox("End day", list(range(1, 32)), index=29, key="wfc_end_day")

        c1, c2, c3 = st.columns(3)
        with c1:
            wfc_log = st.checkbox("Log scale (y-axis)", value=True, key="wfc_log")
        with c2:
            wfc_show_points = st.checkbox("Show individual daily points", key="wfc_show_points")
        with c3:
            wfc_show_markers = st.checkbox("Mark standard return periods", value=True, key="wfc_show_markers")

        c1, c2 = st.columns(2)
        with c1:
            wfc_curve_color = st.color_picker("Curve color", BRAND_DARK, key="wfc_curve_color")
        with c2:
            wfc_curve_style = st.selectbox("Curve line style", ["-", "--", "-.", ":"], key="wfc_curve_style",
                                            format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                    "-.": "Dash-dot", ":": "Dotted"}[v])

        wfc_threshold = st.checkbox("Show flow value at a chosen percentage", value=True, key="wfc_threshold")
        wfc_threshold_pct, wfc_threshold_color, wfc_threshold_style = 50.0, "#B22222", "--"
        if wfc_threshold:
            c1, c2, c3 = st.columns(3)
            with c1:
                wfc_threshold_pct = st.number_input("Percentage", min_value=0.01, max_value=99.99,
                                                     value=50.0, step=0.5, key="wfc_threshold_pct")
            with c2:
                wfc_threshold_color = st.color_picker("Line color", "#B22222", key="wfc_threshold_color")
            with c3:
                wfc_threshold_style = st.selectbox("Line style", ["-", "--", "-.", ":"],
                                                    key="wfc_threshold_style", index=1,
                                                    format_func=lambda v: {"-": "Solid", "--": "Dashed",
                                                                            "-.": "Dash-dot", ":": "Dotted"}[v])

        wfc_title = st.text_input("Title (optional)", key="wfc_title",
                                   placeholder="e.g. Combined Flow-Duration Curve")

        if st.button("Run Analysis", type="primary", key="wfc_run"):
            try:
                start_wy, end_wy = wfc_year_range
                filtered = wfc.filter_by_years_and_season(
                    fetched["combined"], start_wy, end_wy,
                    wfc_start_month, wfc_start_day, wfc_end_month, wfc_end_day,
                )
                if filtered.empty:
                    raise ValueError(
                        "No combined daily values fall within the selected water years and month/day window."
                    )
                weibull_full = wfc.compute_weibull_table(filtered)

                st.session_state["wfc_result"] = dict(
                    weibull_full=weibull_full, combined_label=fetched["combined_label"],
                    start_wy=start_wy, end_wy=end_wy,
                    start_month=wfc_start_month, start_day=wfc_start_day,
                    end_month=wfc_end_month, end_day=wfc_end_day,
                    use_log=wfc_log, curve_color=wfc_curve_color, curve_style=wfc_curve_style,
                    show_points=wfc_show_points, show_markers=wfc_show_markers,
                    show_threshold=wfc_threshold, threshold_pct=wfc_threshold_pct,
                    threshold_color=wfc_threshold_color, threshold_style=wfc_threshold_style,
                    title=wfc_title,
                )
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

    if "wfc_result" in st.session_state:
        r = st.session_state["wfc_result"]
        fig = wfc.make_plot(
            r["weibull_full"], r["combined_label"], r["start_wy"], r["end_wy"],
            r["start_month"], r["start_day"], r["end_month"], r["end_day"],
            r["use_log"], r["curve_color"], r["curve_style"], r["show_points"], r["show_markers"],
            r["show_threshold"], r["threshold_pct"], r["threshold_color"], r["threshold_style"],
            r["title"],
        )
        st.pyplot(fig, use_container_width=True)

        axis_specs = [(fig.axes[0], ["x", "y"], r["curve_color"])]
        _styling_and_download(fig, axis_specs, "weibull_flow_duration_combined", key_prefix="wfc_chart",
                               label="Download plot")

        st.markdown(f"**{r['combined_label']}**")
        st.dataframe(
            wfc.build_display_table(r["weibull_full"], r["start_wy"], r["end_wy"],
                                     r["start_month"], r["start_day"], r["end_month"], r["end_day"]),
            use_container_width=True, hide_index=True,
        )
        if r["show_threshold"]:
            flow_at_pct = wfc.flow_at_percent(r["weibull_full"], r["threshold_pct"])
            st.write(f"Flow equaled or exceeded {r['threshold_pct']:g}% of the time: **{flow_at_pct:,.1f} cfs**")

        out_cols = ["date", "flow_cfs", "water_year", "rank", "exceedance_prob_pct", "return_period_years"]
        st.download_button(
            "Download full point set (CSV)",
            data=r["weibull_full"][out_cols].to_csv(index=False).encode("utf-8"),
            file_name="weibull_flow_duration_combined_full.csv",
            mime="text/csv",
            key="wfc_csv_download",
        )
    elif "wfc_fetched" in st.session_state:
        st.info("Adjust the settings above and click **Run Analysis**.")
    else:
        st.info("Enter both station IDs above and click **Fetch & Combine Stations** to get started.")

st.divider()
render_view_source(__file__)
