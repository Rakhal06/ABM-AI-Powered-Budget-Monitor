# pages/4_AI_Financial_Advisor.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from utils.ai_advisor import get_advice_from_data

st.set_page_config(page_title="AI Financial Advisor", layout="wide")

st.header("😀 AI Financial Advisor")
st.write("This feature gives budgeting advice based on your spending pattern.")

# load transactions (prefer categorized_df if available)
df = None
if "categorized_df" in st.session_state and st.session_state["categorized_df"] is not None:
    df = st.session_state["categorized_df"]
elif "transactions_df" in st.session_state and st.session_state["transactions_df"] is not None:
    df = st.session_state["transactions_df"]

if df is None or len(df) == 0:
    st.info("No transactions found. Please upload and categorize transactions first (Upload Transactions).")
    st.stop()

# UI controls
question = st.text_area("Ask something about your finances:", height=140, placeholder="e.g. how can I reduce my monthly expenses?")
model_choice = st.selectbox("Model (if using OpenAI)", options=["gpt-4o-mini", "gpt-4", "gpt-4o", "gpt-3.5-turbo"], index=0)
deep_mode = st.checkbox("Deep analysis mode (longer, root-cause + action-plan)", value=False)
show_charts = st.checkbox("Show analysis charts", value=True)

col_left, col_right = st.columns([3, 1])
with col_right:
    st.markdown("**Controls**")
    st.write("Transactions:", f"{len(df)}")
    # read API key from secrets or environment
    key_present = False
    try:
        if "OPENAI_API_KEY" in st.secrets:
            key_present = True
    except Exception:
        pass
    if not key_present:
        key_present = bool(os.environ.get("OPENAI_API_KEY"))
    st.write("DEBUG: secrets contains key =", key_present)
    st.write("Mode:", "Deep" if deep_mode else "Quick")

if st.button("Get Advice"):
    with st.spinner("Analysing data and getting advice..."):
        mode = "deep" if deep_mode else "quick"
        # get key (prefer st.secrets)
        api_key = None
        try:
            api_key = st.secrets.get("OPENAI_API_KEY") if "OPENAI_API_KEY" in st.secrets else None
        except Exception:
            api_key = None
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY")

        # Call the shared helper
        try:
            res = get_advice_from_data(df, question=question, mode=mode, model=model_choice, api_key=api_key)
        except TypeError:
            # older helper signatures - try without named args (robustness)
            res = get_advice_from_data(df, question, mode, model_choice, api_key)
        except Exception as e:
            st.error(f"AI request failed: {e}")
            # fallback: local call without key
            try:
                res = get_advice_from_data(df, question=question, mode=mode, model=model_choice, api_key=None)
            except Exception as e2:
                st.error(f"Fallback also failed: {e2}")
                st.stop()

    # show the AI / analysis text
    st.subheader("AI Analysis and Advice")
    st.markdown(res.get("text", "No advice returned."))

    # optional charts (series or dataframe)
    charts = res.get("charts", {})
    by_cat = charts.get("by_category", None)
    monthly = charts.get("monthly", None)

    if show_charts:
        st.subheader("Charts")
        # layout for charts
        c1, c2 = st.columns([1, 2])
        if by_cat is not None and not getattr(by_cat, "empty", True):
            # prepare top categories
            top = by_cat.copy()
            # make sure numeric
            top = top.astype(float).abs().sort_values(ascending=False).head(8)
            # nicer donut chart
            fig1, ax1 = plt.subplots(figsize=(5,5))
            wedges, texts, autotexts = ax1.pie(top.values, labels=top.index, autopct="%1.1f%%", startangle=140, pctdistance=0.75)
            # draw circle for donut
            centre_circle = plt.Circle((0,0),0.55,fc='white')
            fig1.gca().add_artist(centre_circle)
            ax1.axis('equal')
            ax1.set_title("Spending by category (top categories)")
            ax1.legend(wedges, top.index, bbox_to_anchor=(1.05, 0.5), loc='center left', fontsize='small')
            c1.pyplot(fig1)
        else:
            c1.info("No category data to plot.")

        if monthly is not None and getattr(monthly, "shape", (0,))[0] > 0:
            fig2, ax2 = plt.subplots(figsize=(8,4))
            try:
                months = monthly.index.to_series().dt.strftime("%Y-%m")
            except Exception:
                months = [str(x) for x in monthly.index]
            ax2.plot(months, monthly.values, marker="o", linewidth=2)
            ax2.set_title("Monthly net amount")
            ax2.set_xlabel("Month")
            ax2.set_ylabel("Net amount")
            plt.xticks(rotation=30)
            plt.grid(alpha=0.25)
            c2.pyplot(fig2)
        else:
            c2.info("No monthly data to plot.")

    # show recent transactions preview
    st.markdown("### Recent transactions")
    try:
        st.dataframe(df.sort_values(by="date", ascending=False).head(100))
    except Exception:
        st.dataframe(df.head(100))
