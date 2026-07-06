# pages/1_🗂_Upload_Transactions.py
import streamlit as st
from pathlib import Path
import pandas as pd
from utils.budget import read_statement  # your parser

st.set_page_config(page_title="Upload Transactions", layout="wide")
st.title("📁 Upload Transactions")
st.write("Upload a bank/UPI statement (CSV or XLSX). The app will try to clean & parse it.")

uploaded_file = st.file_uploader("Drag and drop file here", type=["csv", "xls", "xlsx"], accept_multiple_files=False)

if "transactions_df" not in st.session_state:
    st.session_state["transactions_df"] = None

if uploaded_file is not None:
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    save_path = data_dir / uploaded_file.name

    # Save uploaded file
    try:
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"Saved uploaded file to {save_path}")
    except Exception as e:
        st.error(f"Failed to save uploaded file: {e}")
        st.stop()

    st.info("Cleaning and parsing transactions using project helper...")

    try:
        # call your parser and store in session_state
        df = read_statement(str(save_path))
        if df is None or len(df) == 0:
            raise ValueError("Parser returned empty DataFrame.")
        st.session_state["transactions_df"] = df
        st.success("Transactions cleaned and loaded (using utils.budget.read_statement).")
        st.dataframe(df.head(50))
    except Exception as e:
        st.error(f"Failed to read/clean the uploaded file: {e}")

        # fallback: try a raw preview using pandas so user can inspect columns
        try:
            if save_path.suffix.lower() in (".xls", ".xlsx"):
                raw_preview = pd.read_excel(save_path, nrows=20, dtype=str)
            else:
                raw_preview = pd.read_csv(save_path, nrows=20, dtype=str, engine="python")
            st.markdown("**Raw file preview (first 20 rows):**")
            st.dataframe(raw_preview)
            st.info(
                "Tip: if the parser failed because of mismatched column names, open the CSV in Excel and "
                "check column headers — map them by editing utils/budget.read_statement if needed."
            )
        except Exception as e2:
            st.warning(f"Also failed to preview raw file with pandas: {e2}")

else:
    st.info("No file uploaded yet. Supported formats: CSV, XLS, XLSX.")
