"""Small shared Streamlit UI widgets used across multiple tool pages."""

import streamlit as st

MAX_COPY_ROWS = 5000


def toggle_button(label_off, label_on, key, default=False):
    """A button that flips between two states each click (rather than a
    checkbox), used for optional "add a second station" style toggles.

    label_off -- shown when the toggle is currently OFF (click to turn on)
    label_on  -- shown when the toggle is currently ON (click to turn off)
    key       -- unique widget key; the on/off state itself is stored under
                 f"{key}__on" in session_state so it survives reruns
    default   -- initial state the first time this key is seen

    Returns the current boolean state.
    """
    state_key = f"{key}__on"
    if state_key not in st.session_state:
        st.session_state[state_key] = default

    enabled = st.session_state[state_key]
    if st.button(label_on if enabled else label_off, key=key,
                 type="primary" if enabled else "secondary"):
        st.session_state[state_key] = not enabled
        st.rerun()

    return st.session_state[state_key]


def render_copy_as_text(df, key_prefix, anchor_cols=("Date",)):
    """The "Copy as text" expander used on every multi-column data page --
    a plain paste-friendly tab-separated block. Defaults to the whole
    table, but offers a dropdown to narrow it down to just one column
    (alongside the anchor column(s), e.g. Date) instead of everything --
    handy for pasting a single series into Excel without dragging along
    every other item/QC column that happened to be fetched.

    anchor_cols -- columns always kept regardless of which single column
        is picked (e.g. ("Date",), or ("Date", "Time") for NOAA). Only
        columns that actually exist in `df` are kept.
    """
    with st.expander("📋 Copy as text (tab-separated, paste straight into Excel)"):
        anchors = [c for c in anchor_cols if c in df.columns]
        other_cols = [c for c in df.columns if c not in anchors]

        if len(other_cols) > 1:
            choice = st.selectbox(
                "Columns to include", ["All columns"] + other_cols, key=f"{key_prefix}_copy_cols",
            )
            copy_df = df if choice == "All columns" else df[anchors + [choice]]
        else:
            copy_df = df

        if len(copy_df) > MAX_COPY_ROWS:
            st.caption(f"Showing the first {MAX_COPY_ROWS:,} of {len(copy_df):,} rows here -- "
                       "use the CSV download above for the full dataset.")
        st.code(copy_df.head(MAX_COPY_ROWS).to_csv(index=False, sep="\t"), language=None)
