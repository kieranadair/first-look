"""First Look v2 · your data, your questions, a clearer understanding."""

import streamlit as st

from firstlook import __version__
from firstlook.ui import poll_work, workspace

st.set_page_config(
    page_title="First Look · get to know your data",
    page_icon=":material/explore:",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.logo(
    "static/wordmark-dark.svg" if st.context.theme.type == "dark" else "static/wordmark.svg",
    icon_image="static/mark.png",
)
state = workspace()
page = st.navigation(
    [
        st.Page("app_pages/data.py", title="Data", icon=":material/table_chart:", default=True),
        st.Page("app_pages/investigate.py", title="Investigate", icon=":material/explore:"),
        st.Page("app_pages/record.py", title="Record", icon=":material/bookmarks:"),
    ],
    position="top",
)
if state.ds:
    with st.sidebar:
        st.caption(state.ds.name)
        st.caption(f"{len(state.ds.frame):,} records · {len(state.ds.fields)} fields")
        st.caption(f"{len(state.record)} views kept")
        st.caption("First Look " + __version__)
if st.session_state.get("notice"):
    st.toast(st.session_state.pop("notice"))
page.run()
# Process visitor actions before a completed background job requests a full rerun.
poll_work()
