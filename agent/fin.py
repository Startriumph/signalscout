import pandas as pd
import yfinance as yf
from agent.cache import cache_get, cache_set

FIELDS = ["revenue", "cogs", "receivables", "inventory", "payables", "net_income"]

# Yahoo's row labels vary by company, so we try several names per field
ROW_NAMES = {
    "revenue": ["Total Revenue", "Operating Revenue", "Revenue"],
    "cogs": ["Cost Of Revenue", "Cost of Revenue"],
    "receivables": ["Accounts Receivable", "Receivables"],
    "inventory": ["Inventory"],
    "payables": ["Accounts Payable", "Payables"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
}


def _get(t, *attrs):
    for a in attrs:
        try:
            df = getattr(t, a)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
    return None


def _extract(df):
    out = {}
    if df is None:
        return out
    for field, names in ROW_NAMES.items():
        for n in names:
            if n in df.index:
                out[field] = pd.to_numeric(df.loc[n], errors="coerce")
                break
    return out


def _table(income, balance):
    series = {}
    series.update(_extract(income))
    series.update(_extract(balance))
    if not series:
        return []
    table = pd.DataFrame(series).sort_index()
    table = table.reindex(columns=FIELDS)
    table = table.dropna(how="all")
    rows = []
    for d, row in table.iterrows():
        rec = {"date": pd.Timestamp(d).strftime("%Y-%m-%d")}
        for k in FIELDS:
            v = row[k]
            rec[k] = None if pd.isna(v) else float(v)
        rows.append(rec)
    return rows


def _fetch_raw(ticker):
    t = yf.Ticker(ticker)
    quarterly = _table(
        _get(t, "quarterly_income_stmt", "quarterly_financials"),
        _get(t, "quarterly_balance_sheet"),
    )
    annual = _table(
        _get(t, "income_stmt", "financials"),
        _get(t, "balance_sheet"),
    )
    return {"quarterly": quarterly, "annual": annual}


def _add_yoy(df, col="revenue"):
    df = df.sort_values("date").reset_index(drop=True)
    vals = []
    for _, row in df.iterrows():
        lo = row["date"] - pd.Timedelta(days=380)
        hi = row["date"] - pd.Timedelta(days=350)
        prev = df[(df["date"] >= lo) & (df["date"] <= hi)]
        if len(prev) and pd.notna(row[col]) and pd.notna(prev.iloc[-1][col]) and prev.iloc[-1][col] != 0:
            vals.append((row[col] / prev.iloc[-1][col] - 1) * 100)
        else:
            vals.append(None)
    df[col + "_yoy_pct"] = vals
    return df


def get_financials(ticker):
    """Returns {'quarterly': DataFrame, 'annual': DataFrame}. Values are in INR."""
    key = f"fin|{ticker}"
    raw = cache_get(key)
    if raw is None:
        try:
            raw = _fetch_raw(ticker)
        except Exception as e:
            print(f"  Financials failed for {ticker}: {e}")
            raw = {"quarterly": [], "annual": []}
        if raw["quarterly"] or raw["annual"]:
            cache_set(key, raw)

    out = {}
    for freq in ("quarterly", "annual"):
        df = pd.DataFrame(raw[freq], columns=["date"] + FIELDS)
        df["date"] = pd.to_datetime(df["date"])
        for c in FIELDS:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        if len(df):
            bad = df["cogs"] > df["revenue"]
            if bad.any():
                dates = ", ".join(df.loc[bad, "date"].dt.strftime("%Y-%m-%d"))
                print(f"  Warning: {ticker} {freq} cost exceeds revenue on {dates}; cost ignored there")
                df.loc[bad, "cogs"] = float("nan")

        out[freq] = _add_yoy(df) if len(df) else df
    return out


def show(name, fin):
    print(f"\n=== {name} (INR crore; growth in %) ===")
    for freq in ("quarterly", "annual"):
        df = fin[freq]
        if df.empty:
            print(f"{freq}: no data from Yahoo")
            continue
        view = df.copy()
        view["date"] = view["date"].dt.strftime("%Y-%m-%d")
        for c in FIELDS:
            view[c] = (view[c] / 1e7).round(0)
        if "revenue_yoy_pct" in view:
            view["revenue_yoy_pct"] = view["revenue_yoy_pct"].astype(float).round(1)
        print(f"\n{freq}:")
        print(view.to_string(index=False))
        missing = [c for c in FIELDS if df[c].isna().all()]
        if missing:
            print(f"  never available: {', '.join(missing)}")

