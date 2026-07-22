"""Shared figure-download widget used on every tool page.

Always exports SVG (vector, scales cleanly for reports/PowerPoint); the only
choice offered is background (normal vs. transparent).
"""

from io import BytesIO

import streamlit as st


def render_figure_download(fig, base_filename, key_prefix, label="Download chart"):
    """Render a Background dropdown and a single SVG download button for a
    matplotlib figure.

    fig          -- the matplotlib Figure to export
    base_filename -- file name without extension, e.g. "peak_flow_chart"
    key_prefix   -- unique Streamlit widget key prefix for this control
                    (needed when a page renders more than one download panel)
    label        -- text prefix for the download button
    """
    col1, col2 = st.columns([1, 2])
    with col1:
        bg = st.selectbox("Background", ["Normal", "Transparent"], key=f"{key_prefix}_bg")

    transparent = (bg == "Transparent")
    buf = BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", transparent=transparent)

    with col2:
        st.write("")  # align button with the dropdown's baseline
        st.download_button(
            f"{label} (SVG, {bg.lower()} background)",
            data=buf.getvalue(),
            file_name=f"{base_filename}.svg",
            mime="image/svg+xml",
            key=f"{key_prefix}_download",
        )
