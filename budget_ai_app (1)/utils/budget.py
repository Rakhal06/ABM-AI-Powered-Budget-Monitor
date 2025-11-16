# utils/budget.py
import re
from pathlib import Path
from typing import Optional, List
import pandas as pd
import numpy as np
from datetime import datetime

# detect month names + day + year like "Nov 16, 2025"
DATE_RE = re.compile(
    r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
    r'Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)|Oct(?:ober)?|Nov(?:ember)?|'
    r'Dec(?:ember)?)\b\s*\d{1,2},?\s*\d{4}', flags=re.I
)

CURRENCY_RE = re.compile(r'[\u20b9₹$€£]|(?<=\s)rs(?=\s)|(?<=\s)rs\.', flags=re.I)


def _find_header_row(raw_df: pd.DataFrame) -> Optional[int]:
    header_keywords = ('date', 'transaction', 'transaction details', 'details', 'type', 'amount', 'amt', 'description', 'narration')
    for i, row in raw_df.iterrows():
        joined = ' '.join([str(x).lower() if pd.notna(x) else '' for x in row.values])
        hits = sum(1 for kw in header_keywords if kw in joined)
        if hits >= 2:
            return i
    return None


def _clean_amount(val: str) -> Optional[float]:
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s == '':
        return None
    s = s.replace('\u20b9', '').replace('₹', '').replace(',', '')
    s = re.sub(r'[^\d\.\-]', '', s)
    if s in ('', '.', '-'):
        return None
    try:
        return float(s)
    except Exception:
        return None


def _try_read_csv_with_encodings(path: Path, encodings: List[str] = None) -> pd.DataFrame:
    if encodings is None:
        encodings = ["utf-8", "utf-8-sig", "cp1252", "latin1"]
    last_err = None
    for enc in encodings:
        try:
            # use engine="python" for more tolerant parsing
            df = pd.read_csv(path, header=None, dtype=str, engine="python", encoding=enc, keep_default_na=False, na_values=[''])
            return df
        except Exception as e:
            last_err = e
            # try next encoding
    raise UnicodeDecodeError("reading_csv", b"", 0, 1, f"Failed to read CSV with tried encodings {encodings}. Last error: {last_err}")


def read_statement(path: str) -> pd.DataFrame:
    """
    Robust reader/cleaner for bank/UPI statement CSV/XLSX files.
    Returns DataFrame with columns: date (datetime), description (str), type (str), amount (float)
    """
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = csv_path.suffix.lower()
    # === read raw table (no header) to find header row or use pandas native reader for excel ===
    if suffix in (".xls", ".xlsx"):
        try:
            # read first sheet
            raw_df = pd.read_excel(csv_path, header=None, dtype=str)
        except Exception as e:
            # Provide clearer message to user
            raise ValueError(f"Failed to read Excel file: {e}")
    else:
        # CSV: try multiple encodings
        try:
            raw_df = _try_read_csv_with_encodings(csv_path)
        except UnicodeDecodeError as ude:
            # final fallback: try pandas default read (may raise)
            try:
                raw_df = pd.read_csv(csv_path, header=None, dtype=str, engine="python", keep_default_na=False, na_values=[''])
            except Exception as e:
                raise ValueError(f"Failed to read CSV file (encoding issues). Last error: {ude}; fallback error: {e}")

    # normalize empty strings to NaN
    raw_df = raw_df.replace(r'^\s*$', np.nan, regex=True)

    # detect header row
    header_row_idx = _find_header_row(raw_df)

    # If header not auto-detected, try the first row-as-header approach
    if header_row_idx is None:
        # attempt a small preview (pandas default header) to see if file already contains headers
        try:
            if suffix in (".xls", ".xlsx"):
                preview = pd.read_excel(csv_path, nrows=10, dtype=str)
            else:
                # try common encodings quickly
                preview = pd.read_csv(csv_path, nrows=10, dtype=str, engine="python")
            lowcols = [c.lower() for c in preview.columns.astype(str)]
            if any('amount' in c or 'transaction' in c or 'date' in c for c in lowcols):
                # file already had header row (pandas parsed it)
                df = preview if len(preview) > 0 else preview
                # if preview had only first 10 rows, re-read full file as header present
                if suffix in (".xls", ".xlsx"):
                    df = pd.read_excel(csv_path, dtype=str)
                else:
                    df = pd.read_csv(csv_path, dtype=str, engine="python")
            else:
                # fallback: try to find explicit "Transaction Details" row
                header_row_idx = None
                for i, row in raw_df.iterrows():
                    if any('transaction details' in str(x).lower() for x in row.values if pd.notna(x)):
                        header_row_idx = i
                        break
                if header_row_idx is None:
                    raise ValueError("Failed to find header row automatically. Open CSV/XLSX and check header row location.")
                header = raw_df.loc[header_row_idx].fillna('').astype(str).tolist()
                data = raw_df.loc[header_row_idx + 1:].copy()
                data.columns = header
                df = data.reset_index(drop=True)
        except Exception as e:
            raise ValueError("Failed to find header row or read file: " + str(e))
    else:
        header = raw_df.loc[header_row_idx].fillna('').astype(str).tolist()
        data = raw_df.loc[header_row_idx + 1:].copy()
        data.columns = header
        df = data.reset_index(drop=True)

    # LOWER->ORIG mapping
    lname = {str(c).lower(): c for c in df.columns}

    # Explicit mapping helper (handles header names like "Date,Transaction,Type,amount")
    if 'date' in lname and ('transaction' in lname or 'transaction details' in lname) and 'amount' in lname:
        date_col = lname.get('date')
        desc_col = lname.get('transaction') or lname.get('transaction details') or lname.get('transaction_details')
        type_col = lname.get('type') or lname.get('txn type') or lname.get('transaction type')
        amt_col = lname.get('amount')
    else:
        def pick_col(keywords):
            for low, orig in lname.items():
                for kw in keywords:
                    if kw in low:
                        return orig
            return None
        date_col = pick_col(['date'])
        desc_col = pick_col(['transaction', 'details', 'description', 'narration'])
        type_col = pick_col(['type', 'txn type', 'transaction type'])
        amt_col = pick_col(['amount', 'amt', 'value'])

    # If amount column still missing, inspect values for currency patterns
    if amt_col is None:
        for c in df.columns:
            sample = df[c].dropna().astype(str).head(20).tolist()
            if any(CURRENCY_RE.search(s) or re.search(r'\d', s) for s in sample):
                amt_col = c
                break

    # Pick a description column if none found
    if desc_col is None:
        for c in df.columns:
            if c not in (date_col, amt_col, type_col) and df[c].dropna().shape[0] > 0:
                desc_col = c
                break

    if amt_col is None:
        raise ValueError("No 'amount' column detected in the file. Open the file and ensure a column is named 'amount' or similar (amt).")
    if date_col is None:
        # attempt to find date-like content in columns
        for c in df.columns:
            sample = df[c].dropna().astype(str).head(20).tolist()
            if any(DATE_RE.search(s) or re.search(r'\d{2}[-/]\d{2}[-/]\d{2,4}', s) for s in sample):
                date_col = c
                break
    if date_col is None:
        raise ValueError("No 'date' column detected in the file. Open the file and ensure a date column exists.")

    # Work copy
    work = df.copy()
    work = work.replace({r'^\s*$': np.nan}, regex=True)
    work['__date_raw'] = work[date_col].astype(str).where(work[date_col].notna(), np.nan)

    def looks_like_date(x):
        if pd.isna(x):
            return False
        s = str(x)
        return bool(DATE_RE.search(s) or re.search(r'\d{2}[-/]\d{2}[-/]\d{2,4}', s))

    def has_amount_val(x):
        if pd.isna(x):
            return False
        s = str(x)
        return bool(re.search(r'\d', s))

    mask_date = work['__date_raw'].apply(lambda x: looks_like_date(x))
    mask_amt = work[amt_col].apply(has_amount_val) if amt_col in work.columns else pd.Series(False, index=work.index)
    mask = mask_date | mask_amt
    filtered = work[mask].copy()

    if filtered.empty:
        raise ValueError("File did not contain recognizable transaction rows (no dates or amounts found).")

    # Parse date
    def parse_date(val):
        try:
            if pd.isna(val):
                return pd.NaT
            s = str(val).strip()
            m = DATE_RE.search(s)
            if m:
                sdate = m.group(0)
                for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        return pd.to_datetime(datetime.strptime(sdate, fmt))
                    except Exception:
                        pass
                try:
                    return pd.to_datetime(sdate, errors='coerce')
                except Exception:
                    return pd.NaT
            return pd.to_datetime(s, errors='coerce')
        except Exception:
            return pd.NaT

    filtered['date'] = filtered['__date_raw'].apply(parse_date)

    # description
    if desc_col in filtered.columns:
        filtered['description'] = filtered[desc_col].astype(str).fillna('').str.strip()
    else:
        filtered['description'] = filtered.astype(str).apply(lambda r: ' '.join([str(x) for x in r.values if pd.notna(x) and str(x).strip() != '']), axis=1)

    # type column
    filtered['type'] = filtered[type_col].astype(str).fillna('').str.strip() if (type_col in filtered.columns) else ''

    # amount raw and cleaned
    filtered['amount_raw'] = filtered[amt_col].astype(str).where(filtered[amt_col].notna(), np.nan)
    filtered['amount'] = filtered['amount_raw'].apply(_clean_amount)

    def normalize_amount(row):
        amt = row['amount']
        if pd.isna(amt):
            return None
        t = str(row.get('type', '')).lower()
        if 'debit' in t or 'dr' in t:
            return -abs(amt)
        if 'credit' in t or 'cr' in t:
            return abs(amt)
        raw = str(row.get('amount_raw', '')).lower()
        if raw.endswith('cr') or ' cr' in raw:
            return abs(amt)
        if raw.endswith('dr') or ' dr' in raw:
            return -abs(amt)
        return amt

    filtered['amount'] = filtered.apply(normalize_amount, axis=1)

    # drop non-transaction rows
    filtered = filtered[filtered['amount'].notna()].copy()

    final = filtered[['date', 'description', 'type', 'amount']].copy().reset_index(drop=True)
    final['date'] = pd.to_datetime(final['date'], errors='coerce')
    final['description'] = final['description'].astype(str)
    final['type'] = final['type'].astype(str)
    final['amount'] = pd.to_numeric(final['amount'], errors='coerce')

    return final
