# app.py
import streamlit as st
from utils.auth import login_ui, get_current_user
import pandas as pd
import os

st.set_page_config(page_title="BudgetAI — Advanced", layout="wide")

# --- Authentication / simple user handling (local JSON) ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# show the login/signup UI in the sidebar (it will display the logged-in user there)
login_ui()

# stop rendering pages until the user logs in
if not st.session_state.get("logged_in"):
    st.stop()

# If logged in, show main index
user = get_current_user()

# Friendly header on the main page (do NOT duplicate the username in the sidebar)
st.markdown(f"# 👋 Welcome, {user['username']} — BudgetAI Advanced")
st.markdown("Use the left sidebar to navigate pages (Upload, Dashboard, Risk, Advisor).")

# show quick summary
uploaded = st.session_state.get("transactions_df") is not None
if not uploaded:
    st.info("No transactions loaded yet. Go to '📁 Upload Transactions' page to upload a statement (CSV/Excel/PDF).")
else:
    df = st.session_state["transactions_df"]
    st.metric("Loaded transactions", f"{len(df):,}")
    st.dataframe(df.head(10))
