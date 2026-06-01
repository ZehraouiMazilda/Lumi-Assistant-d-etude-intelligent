import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import streamlit as st

st.set_page_config(
    page_title="Lumi",
    page_icon="🌟",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Init session state
for k, v in {"page": "auth", "user": None}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Si pas connecté → auth
if st.session_state["user"] is None and st.session_state["page"] != "auth":
    st.session_state["page"] = "auth"

page = st.session_state.page

if page == "auth":
    from views.auth import show; show()
elif page == "home":
    from views.home import show; show()
elif page == "session":
    from views.session import show; show()
elif page == "analytics":
    from views.analytics import show; show()
