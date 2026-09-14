"""Shared styling for small italic Roboto text — used for timestamp/range
captions (main page's "Last synced," Overview's "Showing ... to ...") so the
look stays identical everywhere it's used instead of each page redefining it.
"""

import streamlit as st

# st.markdown(..., unsafe_allow_html=True) silently strips "opacity" from
# inline style="" attributes (confirmed by inspecting the rendered DOM) —
# st.html() goes through lighter sanitization and keeps it, so that's used
# here instead.
_STYLE = "font-family: 'Roboto', sans-serif; font-size: 1.0rem; font-weight: 400; font-style: italic; opacity: 0.6;"


def styled_caption(text: str) -> None:
    st.html(
        '<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400&display=swap" rel="stylesheet">'
        f'<p style="{_STYLE}">{text}</p>'
    )
