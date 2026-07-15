"""Shared 'View source' panel used at the bottom of every page.

Lets teammates see exactly how a tool works without leaving the app -- on
top of (not instead of) the code being browsable on GitHub.
"""

from pathlib import Path

import streamlit as st


def render_view_source(file_path, label="View source code for this page"):
    """Render a collapsed expander showing the raw source of ``file_path``.

    Call this at the bottom of any page with ``render_view_source(__file__)``.
    """
    path = Path(file_path).resolve()
    with st.expander(f"🔍 {label}"):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as e:
            st.error(f"Could not read source file: {e}")
            return
        st.caption(str(path.name))
        st.code(source, language="python", line_numbers=True)
