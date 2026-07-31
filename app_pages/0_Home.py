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

    - **📐 1D Figures** — cross-section plotter for 1D HEC-RAS model
      results: upload an Excel sheet and plot any number of
      Velocity/WSE/Profile/Elevation scenarios, each with its own Station
      column.
    - **🗺️ 2D Figures** — time-series plotter for 2D HEC-RAS model results:
      upload an Excel sheet and overlay any number of point/cross-section
      scenarios (each with its own Datetime column) as Velocity/WSE/Depth
      lines on one chart for direct comparison.

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
