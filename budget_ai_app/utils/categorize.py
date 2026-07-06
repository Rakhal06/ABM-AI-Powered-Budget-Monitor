# categorize
import pandas as pd
import os
import openai
import re

CATEGORIES = [
    "Food", "Groceries", "Travel", "Transport", "Bills", "Entertainment",
    "Shopping", "Health", "Subscriptions", "Investment", "Salary", "Others"
]

if "OPENAI_API_KEY" in os.environ:
    openai.api_key = os.environ["OPENAI_API_KEY"]
else:
    openai = None

def _simple_rule(desc):
    d = desc.lower()
    if any(x in d for x in ["uber", "ola", "taxi", "cab"]):
        return "Transport"
    if any(x in d for x in ["starbuck", "cafe", "restaurant", "zomato", "swiggy"]):
        return "Food"
    if any(x in d for x in ["supermarket", "grocery", "bigbasket"]):
        return "Groceries"
    if any(x in d for x in ["flight", "airline", "hotel", "booking"]):
        return "Travel"
    if any(x in d for x in ["netflix", "spotify", "subscription"]):
        return "Subscriptions"
    if any(x in d for x in ["amazon", "myntra"]):
        return "Shopping"
    if any(x in d for x in ["doctor", "pharmacy", "clinic"]):
        return "Health"
    return None

def categorize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["category"] = None
    for idx, r in df.iterrows():
        c = _simple_rule(str(r.get("description", "")))
        if c:
            df.at[idx, "category"] = c

    df["category"] = df["category"].fillna("Others")
    return df
