# utils/ai_advisor.py
import os
import math
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime
import logging

# Try to import both the new and old SDK interfaces; support either.
try:
    # openai v1 (new): from openai import OpenAI; client = OpenAI()
    from openai import OpenAI as _OpenAI
    _HAS_OPENAI_NEW = True
except Exception:
    _OpenAI = None
    _HAS_OPENAI_NEW = False

try:
    import openai as _openai_legacy
    _HAS_OPENAI_LEGACY = True
except Exception:
    _openai_legacy = None
    _HAS_OPENAI_LEGACY = False

logger = logging.getLogger("ai_advisor")
logger.setLevel(logging.INFO)


def _summarize_data(df: pd.DataFrame) -> Dict[str, Any]:
    """Return numeric summary, top categories and monthly trend."""
    # ensure expected columns exist
    if "amount" not in df.columns:
        raise ValueError("DataFrame missing 'amount' column")

    summary = {}
    summary['n_transactions'] = int(len(df))
    summary['total'] = float(df['amount'].sum())
    summary['income'] = float(df.loc[df['amount'] > 0, 'amount'].sum())
    summary['expense'] = float(df.loc[df['amount'] < 0, 'amount'].sum())

    # by category (if exists) or by description first token
    if 'category' in df.columns:
        by_cat = df.groupby('category')['amount'].sum().sort_values(ascending=False)
    else:
        # try best-effort category from description first few words
        # fall back to description itself
        by_cat = df.groupby('description')['amount'].sum().sort_values(ascending=False)
    summary['by_category'] = by_cat

    # Top large transactions (abs)
    top_abs = df.assign(abs_amt=df['amount'].abs()).sort_values('abs_amt', ascending=False).head(10)
    top_list = []
    for _, r in top_abs.iterrows():
        top_list.append({
            "date": str(r.get('date')) if 'date' in r else None,
            "description": str(r.get('description', '')),
            "type": str(r.get('type', '')),
            "amount": float(r.get('amount', 0.0))
        })
    summary['top_transactions'] = top_list

    # monthly trend: group by year-month
    if 'date' in df.columns:
        try:
            monthly = df.set_index(pd.to_datetime(df['date'], errors='coerce')).resample('M')['amount'].sum()
            monthly.index = monthly.index.to_period('M').to_timestamp()
            summary['monthly'] = monthly
        except Exception:
            summary['monthly'] = pd.Series(dtype=float)
    else:
        summary['monthly'] = pd.Series(dtype=float)

    return summary


def _local_rule_based_advice(summary: Dict[str, Any], question: str, deep: bool) -> str:
    """Produce a readable local fallback analysis (no external API)."""
    lines = []
    lines.append("**Local rule-based analysis (no AI key)**\n")
    lines.append(f"- Transactions analysed: **{summary['n_transactions']}**")
    lines.append(f"- Net total: **{summary['total']:.2f}**, Income: **{summary['income']:.2f}**, Expenses: **{summary['expense']:.2f}**\n")

    # Top categories
    by_cat = summary['by_category']
    if not by_cat.empty:
        top = by_cat.head(8)
        lines.append("**Top categories (by net amount):**")
        for label, val in top.items():
            lines.append(f"- {label}: {val:.2f}")
    else:
        lines.append("No category breakdown available.")

    # If question contains specific keywords, give tailored advice
    q = (question or "").lower()
    tailored = []
    if 'save' in q or 'reduce' in q or 'spend less' in q or 'budget' in q:
        tailored.append("Focus immediate cuts on top discretionary categories and subscriptions.")
    elif 'fraud' in q or 'unauthorised' in q or 'charge' in q:
        tailored.append("Check the top transactions and contact your bank/UPI provider for unexpected debits.")
    if tailored:
        lines.append("\n**Targeted suggestions:**")
        for t in tailored:
            lines.append(f"- {t}")

    # actionable steps
    lines.append("\n**Action plan (rule-based):**")
    # prioritized actions
    lines.append("1. Identify and categorize unknown transactions; clarify any ambiguous entries.")
    lines.append("2. Cancel unused subscriptions or downgrade plans (top subscription entries above).")
    lines.append("3. Set monthly caps for top 3 expense categories. Example:")
    # compute example budgets
    try:
        top_three = by_cat.head(3)
        total_spend = -summary['expense'] if summary['expense'] < 0 else abs(summary['expense'])
        if total_spend == 0:
            total_spend = 1.0
        for label, val in top_three.items():
            percent = (-val / total_spend) * 100 if val < 0 else 0.0
            suggested = max(0, -val * 0.9)  # suggest 10% cut
            lines.append(f"   - {label}: recent net {val:.2f} -> suggested monthly cap {suggested:.2f} (~{percent:.0f}% of recent spend)")
    except Exception:
        pass

    if deep:
        lines.append("\n**Deeper checks to run (manual):**")
        lines.append("- Inspect recurring merchant names and their dates to find subscriptions.")
        lines.append("- Compare monthly average spend vs current month to find spikes.")
        lines.append("- Create a 30-day decision rule for non-essential purchases.")

    # short answer to question
    if question:
        lines.append(f"\n**Quick answer to your question:** {question}")
        lines.append("- Based on top categories above, prioritize trimming the largest discretionary buckets (see top categories).")

    return "\n".join(lines)


def _build_prompt(summary: Dict[str, Any], question: str, deep: bool) -> str:
    """Create a long prompt for the LLM containing the numeric summary and clear instructions."""
    s = []
    s.append("You are a helpful, concise financial advisor assistant. Analyze the transactions summary below and produce a structured, actionable response.")
    s.append("")
    s.append("### Summary of dataset")
    s.append(f"- Transactions analysed: {summary['n_transactions']}")
    s.append(f"- Net total: {summary['total']:.2f}; Income: {summary['income']:.2f}; Expenses: {summary['expense']:.2f}")
    s.append("")
    s.append("### Top categories (top 10):")
    by_cat = summary['by_category']
    if not by_cat.empty:
        for label, val in by_cat.head(10).items():
            s.append(f"- {label}: {val:.2f}")
    else:
        s.append("- (no category data available)")
    s.append("")
    s.append("### Top large transactions (10):")
    for t in summary['top_transactions'][:10]:
        s.append(f"- {t.get('date','')} | {t.get('description','')[:60]} | {t.get('type','')} | {t.get('amount'):.2f}")
    s.append("")
    # monthly trend compact
    monthly = summary.get('monthly', None)
    if isinstance(monthly, pd.Series) and not monthly.empty:
        s.append("### Monthly totals (most recent 12):")
        m = monthly.tail(12)
        s.append(", ".join(f"{d.strftime('%Y-%m')}:{v:.0f}" for d, v in m.items()))
    s.append("")
    s.append("### Instructions for the assistant:")
    s.append("Produce a markdown reply with these labeled sections:")
    s.append("1) Short summary (2-3 sentences).")
    s.append("2) Root-cause analysis (why major categories are large, recurring charges and spikes).")
    s.append("3) Prioritized action plan (3-7 concrete steps, with example numbers where possible).")
    s.append("4) If user asked a specific question, answer it directly in 1-2 paragraphs.")
    s.append("5) Provide 3 quick wins (bullet list) and 2 medium-term actions (30-90 days).")
    if deep:
        s.append("6) Deep mode: include a 6-step implementation plan with suggested budgets and monitoring KPIs.")
    s.append("")
    if question:
        s.append(f"User question: {question}")
    s.append("")
    s.append("Be concise, but give numeric examples where feasible. Return only markdown text (no JSON).")
    return "\n".join(s)


def _call_llm(prompt: str, model: str, api_key: Optional[str], temperature: float = 0.2, max_tokens: int = 700):
    """Call OpenAI; support new and legacy clients if present."""
    # prefer new client
    if _HAS_OPENAI_NEW:
        client = _OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        try:
            # create with messages: system / user
            system_msg = {"role": "system", "content": "You are a helpful financial analysis assistant."}
            user_msg = {"role": "user", "content": prompt}
            resp = client.chat.completions.create(model=model, messages=[system_msg, user_msg], temperature=temperature, max_tokens=max_tokens)
            # respond text:
            if resp and resp.choices and len(resp.choices) > 0:
                return resp.choices[0].message.content
        except Exception as e:
            logger.exception("OpenAI new client failed: %s", e)
            raise
    # try legacy library
    if _HAS_OPENAI_LEGACY:
        _openai_legacy.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        try:
            resp = _openai_legacy.ChatCompletion.create(model=model, messages=[{"role": "system", "content": "You are a helpful financial analysis assistant."}, {"role": "user", "content": prompt}], temperature=temperature, max_tokens=max_tokens)
            if resp and resp.choices and len(resp.choices) > 0:
                return resp.choices[0].message['content']
        except Exception as e:
            logger.exception("OpenAI legacy client failed: %s", e)
            raise
    raise RuntimeError("No OpenAI client available (install 'openai' or 'openai>=1.0.0' SDK).")


def get_advice_from_data(df: pd.DataFrame, question: str = "", mode: str = "quick", model: str = "gpt-4o-mini", api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Main entrypoint used by the Streamlit page.
    Returns dict: { "text": markdown string, "charts": {"by_category": pd.Series, "monthly": pd.Series} }
    - mode: "quick" or "deep"
    - model: OpenAI model name (if available)
    - api_key: optional explicit API key (falls back to environment / st.secrets)
    """
    deep = (mode.lower() == "deep")
    # safe copy
    dfc = df.copy().reset_index(drop=True)

    # basic cleaning: ensure columns present and amount numeric
    if 'amount' not in dfc.columns or dfc['amount'].isna().all():
        # try common alternative column names
        for alt in ['amt', 'Amount', 'AMOUNT', 'value']:
            if alt in dfc.columns:
                dfc['amount'] = pd.to_numeric(dfc[alt].astype(str).str.replace('[^0-9\.\-]', '', regex=True), errors='coerce')
                break

    # compute summary
    try:
        summary = _summarize_data(dfc)
    except Exception as e:
        logger.exception("summary failed: %s", e)
        # fallback minimal summary
        summary = {
            "n_transactions": len(dfc),
            "total": float(dfc['amount'].sum() if 'amount' in dfc.columns else 0.0),
            "income": float(dfc.loc[dfc['amount'] > 0, 'amount'].sum()) if 'amount' in dfc.columns else 0.0,
            "expense": float(dfc.loc[dfc['amount'] < 0, 'amount'].sum()) if 'amount' in dfc.columns else 0.0,
            "by_category": pd.Series(dtype=float),
            "top_transactions": [],
            "monthly": pd.Series(dtype=float)
        }

    # build charts payload
    charts = {
        "by_category": summary.get('by_category', pd.Series(dtype=float)),
        "monthly": summary.get('monthly', pd.Series(dtype=float))
    }

    # if there's an API key, call the LLM
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if key and ( _HAS_OPENAI_NEW or _HAS_OPENAI_LEGACY):
        prompt = _build_prompt(summary, question, deep)
        try:
            # model param fallback to a sensible default if not provided
            model_used = model or "gpt-4o-mini"
            text = _call_llm(prompt, model_used, api_key=key, temperature=0.2 if not deep else 0.6, max_tokens=900 if deep else 500)
            return {"text": text, "charts": charts}
        except Exception as e:
            logger.exception("LLM call failed, falling back to local: %s", e)
            fallback_text = f"AI request failed, falling back to local analysis. Error: {e}\n\n" + _local_rule_based_advice(summary, question, deep)
            return {"text": fallback_text, "charts": charts}
    else:
        # no api key -> local analysis
        text = _local_rule_based_advice(summary, question, deep)
        return {"text": text, "charts": charts}
