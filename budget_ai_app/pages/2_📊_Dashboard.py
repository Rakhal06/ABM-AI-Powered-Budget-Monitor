# pages/2_Dashboard.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("📊 Dashboard")

# Ensure transactions exist in session_state
if "transactions_df" not in st.session_state or st.session_state["transactions_df"] is None:
    st.info("No transactions found. Please upload a statement on the Upload page.")
    st.stop()

df = st.session_state["transactions_df"].copy()

# Basic metrics
total_tx = len(df)
total_spend = float(df[df["amount"] < 0]["amount"].sum()) if "amount" in df.columns else 0.0
total_income = float(df[df["amount"] > 0]["amount"].sum()) if "amount" in df.columns else 0.0
avg_tx = float(df["amount"].abs().mean()) if "amount" in df.columns else 0.0

cols = st.columns(3)
cols[0].metric("Transactions", f"{total_tx}")
cols[1].metric("Net spend (neg)", f"{total_spend:,.2f}")
cols[2].metric("Net income", f"{total_income:,.2f}")

st.markdown("### Top categories / description summary")

# group by category if present else by description
group_col = "category" if "category" in df.columns else "description"
by_cat = df.groupby(group_col)["amount"].sum().sort_values(ascending=False)

st.dataframe(by_cat.head(20).reset_index().rename(columns={group_col: "category/description", "amount": "net_amount"}))

# Charts: pie (top categories) and monthly trend
st.markdown("### Charts")
chart_col1, chart_col2 = st.columns([2, 3])

# Pie: top 8 categories
top = by_cat.head(8)
if top.empty:
    chart_col1.info("Not enough category/description data to plot.")
else:
    fig1, ax1 = plt.subplots(figsize=(6, 6))
    labels = top.index.tolist()
    sizes = top.values
    # create explode for the largest slice to emphasize
    explode = [0.08 if i == 0 else 0.02 for i in range(len(sizes))]
    wedges, texts, autotexts = ax1.pie(
        sizes,
        labels=None,
        autopct="%1.1f%%",
        startangle=140,
        wedgeprops=dict(width=0.5, edgecolor="w"),
        explode=explode
    )
    ax1.legend(wedges, labels, title="Top", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
    ax1.set_title("Spending by category (top categories)")
    chart_col1.pyplot(fig1)

# Monthly trend
if "date" in df.columns and "amount" in df.columns:
    tmp = df.copy()
    tmp["date"] = pd.to_datetime(tmp["date"], errors="coerce")
    tmp = tmp.dropna(subset=["date"])
    monthly = tmp.resample("M", on="date")["amount"].sum()
    if monthly.empty:
        chart_col2.info("Not enough date/amount data to plot monthly trend.")
    else:
        fig2, ax2 = plt.subplots(figsize=(8, 4))
        ax2.plot(monthly.index.strftime("%Y-%m"), monthly.values, marker="o")
        ax2.set_title("Monthly net amount")
        ax2.set_xlabel("Month")
        ax2.set_ylabel("Net amount")
        plt.xticks(rotation=30)
        chart_col2.pyplot(fig2)
else:
    chart_col2.info("Missing date or amount column to compute monthly trend.")

st.markdown("### Recent transactions")
st.dataframe(df.sort_values(by="date", ascending=False).head(100))
