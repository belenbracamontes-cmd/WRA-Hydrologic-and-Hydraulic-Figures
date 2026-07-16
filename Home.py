"""Landing page for the WRA Hydrology Tools web app.

Run with:
    streamlit run Home.py

Streamlit automatically turns every script in pages/ into a page reachable
from the sidebar, so adding a new tool later just means dropping a new file
in pages/ -- no other wiring needed.
"""

import streamlit as st

from core.branding import logo_path_if_present, BRAND_DARK
from core.view_source import render_view_source

REPO_URL = "https://github.com/belenbracamontes-cmd/WRA-Hydrologic-and-Hydraulic-Figures"

st.set_page_config(
    page_title="WRA Hydrology Tools",
    page_icon="💧",
    layout="wide",
)

logo = logo_path_if_present()
col_logo, col_title = st.columns([1, 6])
with col_logo:
    if logo:
        st.image(str(logo), width=90)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>WRA Hydrology Tools</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Internal team toolkit — pick a tool from the sidebar.")

st.divider()

st.markdown(
    """
    ### Available tools

    - **📈 Peak Flow Viewer** — annual peak-flow bar chart with return-period
      bands, pulled live from USGS. Supports a single station or a
      side-by-side two-station comparison.
    - **📊 Annual Flow Chart** — dual-axis grouped bar chart of annual peak
      flow and annual average flow (Balance Hydrologics "Figure 3" style),
      pulled live from USGS. Supports a single station or a side-by-side
      two-station comparison.

    More tools will show up here as they're added — each one lives as its
    own file in the `pages/` folder, so the sidebar navigation updates
    automatically.
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
