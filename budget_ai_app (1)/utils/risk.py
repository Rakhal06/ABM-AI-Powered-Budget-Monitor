# utils/risk.py
import pandas as pd
import numpy as np
from typing import List, Dict, Any

def compute_monthly_income(df: pd.DataFrame) -> float:
    """
    Estimate monthly income as average of positive (credit) totals per month.
    Requires 'date' and 'amount' columns.
    """
    if 'date' not in df.columns or 'amount' not in df.columns:
        return 0.0
    df2 = df.dropna(subset=['date', 'amount']).copy()
    df2['date'] = pd.to_datetime(df2['date'], errors='coerce')
    df2 = df2.dropna(subset=['date'])
    if df2.empty:
        return 0.0
    monthly = df2.set_index('date').resample('M')['amount'].sum()
    # take only months where net positive (or optionally only credits)
    monthly_income = monthly[monthly > 0]
    if monthly_income.empty:
        # fallback: sum credits only
        credits = df2[df2['amount'] > 0].set_index('date').resample('M')['amount'].sum()
        if credits.empty:
            return 0.0
        return float(credits.mean())
    return float(monthly_income.mean())


def detect_suspicious_transactions(df: pd.DataFrame,
                                   unaffordable_threshold: float = 0.5,
                                   outlier_z: float = 3.0,
                                   recent_payees_months: int = 6) -> List[Dict[str, Any]]:
    """
    Scan the transactions DataFrame and return list of suspicious items with reasons.
    - unaffordable_threshold: fraction of monthly income above which a single debit is flagged
    - outlier_z: amount z-score above which flagged as 'anomalous amount'
    - recent_payees_months: how many months to look back to consider a payee 'existing'
    """

    flags = []
    if df is None or df.empty:
        return flags

    # ensure date and amount present & typed
    dfc = df.copy()
    if 'amount' not in dfc.columns:
        raise ValueError("DataFrame must have 'amount' column")
    if 'date' in dfc.columns:
        dfc['date'] = pd.to_datetime(dfc['date'], errors='coerce')

    # estimate monthly income
    monthly_income = compute_monthly_income(dfc)
    # numeric stats for amount (use absolute values for outlier detection)
    amounts = dfc['amount'].dropna().astype(float)
    if amounts.empty:
        return flags
    mean_amt = amounts.mean()
    std_amt = amounts.std(ddof=0) if amounts.std(ddof=0) > 0 else 0.0

    # prepare recent payees set
    recent_payees = set()
    if 'description' in dfc.columns and 'date' in dfc.columns:
        min_date = dfc['date'].max() - pd.DateOffset(months=recent_payees_months) if pd.notna(dfc['date'].max()) else None
        recent_df = dfc[dfc['date'] >= min_date] if min_date is not None else dfc
        recent_payees = set(recent_df['description'].dropna().astype(str).str.strip().str.lower().unique())

    # iterate rows and flag
    for idx, row in dfc.iterrows():
        try:
            amt = float(row['amount'])
        except Exception:
            continue
        # only consider debits as payments for unaffordability
        if amt >= 0:
            # still check anomalous large credits (rare) - skip unaffordable
            pass

        reasons = []

        # Unaffordable check (debit amount > unaffordable_threshold * monthly_income)
        if monthly_income > 0 and amt < 0:
            if abs(amt) > unaffordable_threshold * monthly_income:
                reasons.append({
                    "code": "unaffordable",
                    "message": f"Single payment {abs(amt):.2f} is > {unaffordable_threshold*100:.0f}% of estimated monthly income ({monthly_income:.2f})."
                })

        # Outlier check (z-score)
        if std_amt > 0:
            z = (amt - mean_amt) / std_amt
            if abs(z) >= outlier_z:
                reasons.append({
                    "code": "anomalous_amount",
                    "message": f"Transaction amount {amt:.2f} is an outlier (z={z:.1f})."
                })

        # New payee check: if description not in recent_payees and it's a debit or large credit
        desc = str(row.get('description', '')).strip().lower() if 'description' in row else ''
        if desc and desc not in recent_payees:
            # treat as suspicious if debit or large credit
            if amt < 0 or abs(amt) > (0.2 * monthly_income if monthly_income > 0 else 0):
                reasons.append({
                    "code": "new_payee",
                    "message": "Payee appears new (not seen in recent months)."
                })

        # Frequency-based: repeated very frequent small transactions in short time could be suspicious
        # (very basic: check if same payee appears 4+ times within 7 days)
        if 'date' in dfc.columns and desc:
            try:
                payee_rows = dfc[dfc['description'].astype(str).str.strip().str.lower() == desc]
                if len(payee_rows) >= 4:
                    # check if 4+ occurrences happened in any 7-day window
                    dates_sorted = payee_rows['date'].dropna().sort_values()
                    if len(dates_sorted) >= 4:
                        # sliding window approach
                        ds = dates_sorted.reset_index(drop=True)
                        for i in range(len(ds) - 3):
                            if (ds.iloc[i+3] - ds.iloc[i]).days <= 7:
                                reasons.append({
                                    "code": "freq_small_trans",
                                    "message": f"Multiple ({len(payee_rows)}) transactions to same payee in a short window."
                                })
                                break
            except Exception:
                pass

        # If we collected any reasons, add to flags
        if reasons:
            flags.append({
                "index": int(idx),
                "date": str(row.get('date')) if 'date' in row else None,
                "description": row.get('description', ''),
                "type": row.get('type', ''),
                "amount": float(amt),
                "reasons": reasons
            })

    # Sort flags by severity (unaffordable first, anomalous next)
    def severity_score(f):
        score = 0
        for r in f['reasons']:
            if r['code'] == 'unaffordable':
                score += 100
            if r['code'] == 'anomalous_amount':
                score += 50
            if r['code'] == 'new_payee':
                score += 20
            if r['code'] == 'freq_small_trans':
                score += 10
        return -score

    flags_sorted = sorted(flags, key=severity_score)
    return flags_sorted
