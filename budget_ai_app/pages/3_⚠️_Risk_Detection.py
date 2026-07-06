# pages/3_⚠️_Risk_Detection.py (cleaned)
import os
from typing import Tuple
from pathlib import Path

import streamlit as st
import pandas as pd

from utils.risk import compute_monthly_income, detect_suspicious_transactions
from utils.logger import log_freeze_request

st.set_page_config(page_title="Risk Detection", layout="wide")
st.title("⚠️ Risk Detection")

# ----------------- Twilio SMS helper (reads secrets or env) -----------------
def send_sms_via_twilio(body: str) -> Tuple[bool, str]:
    """
    Send SMS using Twilio. Returns (success, info).
    Looks up credentials in st.secrets (preferred) or environment variables.
    """
    sid = token = tw_from = tw_to = None

    try:
        sid = st.secrets.get("TWILIO_ACCOUNT_SID")
        token = st.secrets.get("TWILIO_AUTH_TOKEN")
        tw_from = st.secrets.get("TWILIO_FROM")
        tw_to = st.secrets.get("TWILIO_TO")
    except Exception:
        pass

    # fallback to environment variables
    sid = sid or os.environ.get("TWILIO_ACCOUNT_SID")
    token = token or os.environ.get("TWILIO_AUTH_TOKEN")
    tw_from = tw_from or os.environ.get("TWILIO_FROM")
    tw_to = tw_to or os.environ.get("TWILIO_TO")

    if not (sid and token and tw_from and tw_to):
        return False, "Twilio credentials not found. Set .streamlit/secrets.toml or environment variables."

    try:
        from twilio.rest import Client
    except Exception as e:
        return False, f"Twilio library not installed. Run: pip install twilio. ({e})"

    try:
        client = Client(sid, token)
        msg = client.messages.create(body=body, from_=tw_from, to=tw_to)
        sid_info = getattr(msg, "sid", None)
        return True, f"Message SID: {sid_info}"
    except Exception as e:
        return False, f"Failed to send SMS: {e}"

# -------------------------------------------------------------------------

# Ensure session_state helpers exist
if "freeze_flags" not in st.session_state:
    st.session_state["freeze_flags"] = {}   # key_base -> True when frozen
if "sent_sms_flags" not in st.session_state:
    st.session_state["sent_sms_flags"] = {} # key_base -> True when SMS sent

# Ensure transactions available
if "transactions_df" not in st.session_state or st.session_state["transactions_df"] is None:
    st.warning("Upload transactions first on the Upload page.")
    st.stop()

df = st.session_state["transactions_df"]
if df is None or len(df) == 0:
    st.warning("No transactions available - upload file or use sample data.")
    st.stop()

st.write(f"Transactions loaded: **{len(df)}**")

# Controls
col1, col2 = st.columns([2, 1])
with col1:
    unaff_thresh = st.slider(
        "Unaffordable threshold (single payment > X% of monthly income)",
        min_value=10, max_value=100, value=50
    ) / 100.0
    outlier_z = st.slider(
        "Outlier z-threshold (amount z-score)",
        min_value=1.0, max_value=6.0, value=3.0, step=0.5
    )
    lookback_months = st.number_input(
        "Recent payee lookback (months)",
        min_value=1, max_value=24, value=6
    )
    run_scan = st.button("Run risk scan")
with col2:
    est_income = compute_monthly_income(df)
    st.metric("Estimated monthly income", f"{est_income:.2f}")

    if "account_frozen" not in st.session_state:
        st.session_state["account_frozen"] = False
    if st.session_state["account_frozen"]:
        st.error("Account status: **FROZEN** — user requested freeze locally. Contact bank immediately.")

# Run scan
if run_scan:
    with st.spinner("Scanning transactions..."):
        try:
            flags = detect_suspicious_transactions(
                df,
                unaffordable_threshold=unaff_thresh,
                outlier_z=outlier_z,
                recent_payees_months=lookback_months
            )
        except Exception as e:
            st.error(f"Risk scan failed: {e}")
            flags = []

    if not flags:
        st.success("No suspicious transactions found with current thresholds.")
    else:
        st.warning(f"{len(flags)} suspicious transactions found.")
        # Iterate flagged transactions
        for f in flags:
            # keys and values (coerce safe types)
            idx = f.get("index", None)
            try:
                amount = float(f.get("amount", 0.0))
            except Exception:
                amount = 0.0
            date = f.get("date", "")
            desc = f.get("description", "")
            reasons = f.get("reasons", [])

            st.markdown("---")
            st.markdown(f"**Transaction:** {date} — **{desc}** — **{amount:.2f}**")
            for r in reasons:
                msg = r.get("message", str(r)) if isinstance(r, dict) else str(r)
                st.info(f"Reason: {msg}")

            # stable widget key for this flagged txn
            key_id = str(idx) if idx is not None else str(hash(str(f)) % (10**9))
            key_base = f"flag_{key_id}"

            cola, colb = st.columns([2, 1])
            with cola:
                performed = st.radio(
                    "Did you (or an authorized person) make this transaction?",
                    options=["Yes", "No", "Not sure"],
                    key=key_base + "_radio"
                )
            with colb:
                # If user says No -> freeze + SMS options
                if performed == "No":
                    # Freeze button (safe id)
                    if not st.session_state["freeze_flags"].get(key_base, False):
                        if st.button("Freeze account (local action)", key=key_base + "_freeze"):
                            st.session_state["account_frozen"] = True
                            st.session_state["freeze_flags"][key_base] = True
                            st.success("Account freeze requested (local). Contact your bank/UPI provider immediately to request an official freeze and dispute.")
                            # persist frozen txn in session
                            st.session_state.setdefault("frozen_transactions", []).append({
                                "index": idx, "date": date, "description": desc, "amount": amount
                            })

                            # Log the freeze event (no SMS yet)
                            try:
                                log_freeze_request({
                                    "index": idx, "date": date, "description": desc, "amount": amount,
                                    "sms_sent": False, "sms_info": ""
                                })
                            except Exception as e:
                                st.error(f"Failed to write log: {e}")
                    else:
                        st.info("Freeze already requested for this transaction in this session.")

                    # Offer SMS alert option - show send button but prevent duplicate sends
                    send_sms_check = st.checkbox("Send SMS alert to your phone number now?", key=key_base + "_send_sms_check")
                    if send_sms_check:
                        st.info("SMS will be sent to configured TWILIO_TO (set in .streamlit/secrets.toml or environment).")
                        sms_preview = (
                            f"ALERT: Suspicious transaction detected.\n"
                            f"Date: {date}\n"
                            f"Desc: {desc}\n"
                            f"Amount: {amount:.2f}\n"
                            f"If unauthorized contact your bank immediately."
                        )
                        # Editable preview text area
                        st.text_area("SMS preview (editable)", value=sms_preview, key=key_base + "_sms_preview", height=140)

                        # prevent duplicate send in same session
                        if st.session_state["sent_sms_flags"].get(key_base, False):
                            st.info("SMS already sent for this flagged transaction in this session.")
                        else:
                            if st.button("Send SMS now", key=key_base + "_send_sms_btn"):
                                sms_msg = st.session_state.get(key_base + "_sms_preview", sms_preview)
                                with st.spinner("Sending SMS..."):
                                    success, info = send_sms_via_twilio(sms_msg)
                                if success:
                                    st.success("SMS sent successfully.")
                                    st.info(info)
                                    st.session_state["sent_sms_flags"][key_base] = True
                                else:
                                    st.error("Failed to send SMS.")
                                    st.error(info)

                                # Log the SMS attempt (success or failure)
                                try:
                                    log_freeze_request({
                                        "index": idx, "date": date, "description": desc, "amount": amount,
                                        "sms_sent": bool(success), "sms_info": str(info)
                                    })
                                except Exception as e:
                                    st.error(f"Failed to write log: {e}")

                elif performed == "Not sure":
                    st.warning("If unsure, consider freezing temporarily and contacting your bank. You can update this selection later.")
                else:
                    st.success("Marked as authorized.")

        st.markdown("---")
        st.info(
            "If you pressed Freeze on any transaction, the local app has stored the request (client-side only). "
            "To actually block payments, contact your bank/UPI provider and provide the transaction details."
        )

        # Show local frozen transactions log (session)
        if "frozen_transactions" in st.session_state and st.session_state["frozen_transactions"]:
            st.write("Frozen transactions (local record):")
            try:
                st.dataframe(pd.DataFrame(st.session_state["frozen_transactions"])[['date', 'description', 'amount']])
            except Exception:
                st.dataframe(pd.DataFrame(st.session_state["frozen_transactions"]))

# Recent transactions preview
st.markdown("### Recent transactions preview")
try:
    st.dataframe(df.sort_values(by="date", ascending=False).head(50))
except Exception:
    st.dataframe(df.head(50))
