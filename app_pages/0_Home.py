"""Landing page for the WRA Hydrology Tools web app.

Referenced by Home.py's st.navigation() router as the default page. See
Home.py for the sectioned sidebar navigation (page config + st.Page/
st.navigation live there, not here -- only one st.set_page_config call is
allowed per run).
"""

import streamlit as st

from core.branding import logo_path_if_present, BRAND_DARK
from core.view_source import render_view_source

REPO_URL = "https://github.com/belenbracamontes-cmd/WRA-Hydrologic-and-Hydraulic-Figures"

logo = logo_path_if_present()
col_logo, col_title = st.columns([2, 5])
with col_logo:
    if logo:
        st.image(str(logo), width=220)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>WRA Hydrology Tools</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Internal team toolkit — pick a tool from the sidebar.")

st.divider()

st.markdown(
    """
    ### USGS station tools

    - **🗺️ Intro to USGS** — nationwide map of active USGS streamgages
      (similar to the station map on StreamStats), with a search box to
      find a specific gauge by name or site number.
    - **📈 Peak Flow Viewer** — annual peak-flow bar chart with return-period
      bands, pulled live from USGS. Supports a single station or a
      side-by-side two-station comparison.
    - **📊 Annual Flow Chart** — dual-axis grouped bar chart of annual peak
      flow and annual average flow (Balance Hydrologics "Figure 3" style),
      pulled live from USGS. Supports a single station or a side-by-side
      two-station comparison.
    - **📉 LP3 Flood Frequency** — Log-Pearson Type III flood frequency
      analysis (Bulletin 17C, Wilson-Hilferty quantiles), producing a
      probability plot in USGS Peakfq / Figure 10-13 style with design-flow
      tables and confidence limits.
    - **🌊 Daily Flow & Duration Analysis** — five related daily-flow tools
      grouped into one page as tabs: historical daily flow range (min/max
      band + mean), streamflow duration hydrographs by day-of-year
      percentile (single station and combined two-station), and Weibull
      flow-duration/exceedance analysis (single station with optional
      overlay, and combined two-station with a recurring month/day window).

    ### HEC RAS figures

    - **📐 1D Figures** — profile plotter for 1D HEC-RAS model results:
      upload an Excel sheet and plot any number of Velocity/WSE/Profile/
      Elevation scenarios, each with its own Station column.
    - **🗺️ 2D Figures** — time-series plotter for 2D HEC-RAS model results:
      upload an Excel sheet and overlay any number of point/cross-section
      scenarios (each with its own Datetime column) as Velocity/WSE/Depth
      lines on one chart for direct comparison.
    - **📏 Cross Sections** — Station-vs-Elevation geometry plotter: upload
      an Excel sheet and overlay any number of cross sections, each with
      an optional "modification" profile (e.g. a proposed/regraded
      channel) plotted alongside it.

    ### NOAA tide tools

    - **🗺️ Intro to NOAA Tides** — nationwide map of NOAA's ~300 water-level
      stations (same map/search/selection feature set as Intro to USGS),
      with a search box to find a specific gage by name or station ID.
    - **🌊 Tide Gage Data** — water levels for any NOAA tidal station over
      any date range (chunked automatically past NOAA's own 30-day
      request limit), with datum/units/time-zone/interval options matching
      NOAA's own site. Each row auto-fills from whichever product NOAA
      actually has data for -- Verified/Preliminary observed readings
      where available, the astronomical Predicted tide otherwise -- plus
      chart export, CSV download, and copy-paste-ready text.

    ### CIMIS weather tools

    - **🗺️ Intro to CIMIS** — statewide map of California's ~275 CIMIS weather stations (same
      map/search/selection feature set as Intro to USGS/NOAA Tides), with a search box to find a
      specific station by name or number, and an active/inactive toggle.
    - **🌦️ CIMIS Weather Data** — daily or hourly weather data (Reference ETo, precipitation,
      temperature, humidity, solar radiation, wind, and more) for any CIMIS station, over any date
      range, chunked automatically. Requires your own free CIMIS appKey. Each value carries CIMIS's
      own QC flag, plus chart export, CSV download, and copy-paste-ready text.

    ### PRISM climate tools

    - **🗺️ Intro to PRISM** — PRISM is a gridded climate dataset (not a station network) covering
      the whole contiguous US. Pin any point by coordinates or place-name search, and see its
      state/county, grid elevation, and 1991-2020 monthly climate normals.
    - **🌦️ PRISM Climate Data** — daily, monthly, or annual precipitation, temperature, dew point,
      vapor pressure deficit, and solar radiation for any point in the contiguous US, over any date
      range, chunked automatically. No API key needed. Chart export, CSV download, and
      copy-paste-ready text included.

    More tools will show up here as they're added.
    """
)

st.divider()
st.caption(
    "Running this app: `streamlit run Home.py` from the `peak_flow_webapp` "
    "folder. Share the resulting URL with the team, or deploy it to an "
    "internal server / Streamlit Community Cloud so everyone gets a link "
    "instead of running it locally."
)
st.caption(f"Full source code and history: [{REPO_URL}]({REPO_URL})")

st.divider()
render_view_source(__file__, label="View source code for this page")
