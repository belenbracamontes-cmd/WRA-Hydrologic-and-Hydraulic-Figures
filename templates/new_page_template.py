"""TEMPLATE -- copy this file into pages/ to add a new tool.

Do NOT leave this file inside pages/ itself -- Streamlit turns every .py
file directly under pages/ into a sidebar page, so this template lives here
in templates/ where it's inert, and gets copied+renamed when you actually
use it.

HOW TO USE THIS TEMPLATE
-------------------------
1. Copy it into pages/, with a name of the form "N_Display_Name.py":
     cp templates/new_page_template.py "pages/2_My_New_Tool.py"
   The leading number controls sidebar order; underscores become spaces in
   the sidebar label ("2_My_New_Tool.py" -> "My New Tool").

2. If your tool has real data-fetching / math / plotting logic (like
   core/peak_flow.py does for the Peak Flow Viewer), put THAT in its own
   module under core/, e.g. core/my_new_tool.py. Keep this page file as a
   thin UI layer that imports from core/ -- it makes the logic testable
   and reusable outside Streamlit, and keeps pages/ readable.

3. Replace every "TODO" below, delete this docstring's instructions (keep
   a short one describing the actual tool), and run the app locally to
   check it shows up correctly:
     streamlit run Home.py

4. Commit and push (see README.md for the git workflow).
"""

import sys
from pathlib import Path

import streamlit as st

# Makes `core.*` importable regardless of which page Streamlit runs.
sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.branding import logo_path_if_present, BRAND_DARK
from core.view_source import render_view_source

# TODO: import your tool's own logic module, e.g.:
# from core.my_new_tool import fetch_data, compute_something, make_plot

st.set_page_config(page_title="TODO: Tool Name", page_icon="🧰", layout="wide")

# ── Header (logo + title) -- same pattern on every page for consistency ──────
logo = logo_path_if_present()
col_logo, col_title = st.columns([1, 6])
with col_logo:
    if logo:
        st.image(str(logo), width=70)
with col_title:
    st.markdown(
        f"<h1 style='color:{BRAND_DARK};margin-bottom:0'>TODO: Tool Name</h1>",
        unsafe_allow_html=True,
    )
    st.caption("TODO: one-line description of what this tool does.")

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Inputs")
    # TODO: replace with your tool's actual inputs, e.g.:
    # some_id = st.text_input("ID", key="some_id")
    # some_color = st.color_picker("Color", "#004ca3", key="some_color")
    run = st.button("Run", type="primary", use_container_width=True)

# ── Run + cache pattern ───────────────────────────────────────────────────────
# Fetching/computing only happens on button click, and results are stashed in
# session_state under a key unique to this page so re-running other pages
# doesn't clobber it and tweaking a display-only widget doesn't re-fetch.
STATE_KEY = "TODO_tool_results"  # e.g. "my_new_tool_results"

if run:
    try:
        with st.spinner("Working..."):
            # TODO: call your core module's fetch/compute functions here and
            # store whatever the rest of the page needs to render.
            result = None
        st.session_state[STATE_KEY] = result
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

if STATE_KEY in st.session_state:
    result = st.session_state[STATE_KEY]
    # TODO: render the chart / table / whatever this tool produces.
    st.write(result)
else:
    st.info("Fill in the inputs in the sidebar and click **Run** to get started.")

# ── View source -- keep this at the bottom of every page ─────────────────────
st.divider()
render_view_source(__file__)
