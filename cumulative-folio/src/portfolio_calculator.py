"""
Portfolio Metrics Calculator
"""

import pandas as pd
import numpy as np
from typing import Dict, List


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_get(row, col, default=0.0):
    v = row.get(col, default) if isinstance(row, dict) else getattr(row, col, default)
    return float(v) if pd.notna(v) else default


def _monthly_return(change_in_value: float, starting_value: float) -> float:
    """
    Monthly investment return = change_in_value / starting_value.
    change_in_value already excludes deposits/withdrawals (it's the raw
    investment P&L reported by the broker), so no further cash-flow
    adjustment is needed.
    """
    if starting_value > 0:
        return change_in_value / starting_value
    return 0.0


def _consolidated_monthly_returns(df: pd.DataFrame) -> pd.Series:
    """
    Build one return per calendar month for the total consolidated portfolio.
    Groups all accounts by end_date, sums change_in_value and starting_value.
    """
    grp = (
        df.groupby("end_date")[["change_in_value", "starting_value"]]
        .sum()
        .sort_index()
    )
    grp["return"] = grp.apply(
        lambda r: _monthly_return(r["change_in_value"], r["starting_value"]), axis=1
    )
    return grp["return"]


def _twr(monthly_returns: pd.Series) -> float:
    """Time-Weighted Return = product of (1 + r_i) - 1"""
    if monthly_returns.empty:
        return 0.0
    return float(np.prod(1 + monthly_returns) - 1)


def _risk_metrics(monthly_returns: pd.Series, risk_free_rate: float) -> Dict:
    """Sharpe, Sortino, volatility, max-dd, win-rate from monthly return series."""
    if len(monthly_returns) < 2:
        return dict(sharpe=0.0, sortino=0.0, volatility=0.0, max_dd=0.0, win_rate=0.0)

    rfr_monthly = risk_free_rate / 100 / 12
    excess = monthly_returns - rfr_monthly
    std = monthly_returns.std()
    downside = monthly_returns[monthly_returns < rfr_monthly]
    down_std = downside.std() if len(downside) > 0 else std

    sharpe   = float((excess.mean() / std) * np.sqrt(12)) if std > 0 else 0.0
    sortino  = float((excess.mean() / down_std) * np.sqrt(12)) if down_std > 0 else 0.0
    vol      = float(std * np.sqrt(12) * 100)       # annualised, in %
    win_rate = float((monthly_returns > 0).mean() * 100)

    # Max drawdown from cumulative wealth index
    cum = (1 + monthly_returns).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = float(dd.min() * 100)                  # negative %

    return dict(sharpe=sharpe, sortino=sortino, volatility=vol,
                max_dd=max_dd, win_rate=win_rate)


# ── public API ────────────────────────────────────────────────────────────────

def build_timeline_dataframe(statements: List[Dict]) -> pd.DataFrame:
    """
    Long-format timeline DataFrame — one row per (account, month).
    Appends a "Total Portfolio" row per month that sums all accounts.

    Columns:
        month, date, broker, account_number,
        starting_value, ending_value,
        deposits, withdrawals, security_transfers, change_in_value,
        dividend_income, interest_income,
        realised_gains, realised_st, realised_lt, unrealised_gains,
        net_cash_flow, return_pct,
        start_value, end_value          (aliases for backward compat)
    """
    if not statements:
        return pd.DataFrame()

    rows = []
    for s in statements:
        civ    = _safe_get(s, "change_in_value")
        start  = _safe_get(s, "starting_value")
        rp     = _monthly_return(civ, start) * 100   # in %

        rows.append({
            "month":              s["end_date"].strftime("%Y-%m"),
            "date":               s["end_date"],
            "broker":             s["broker"],
            "account_number":     s.get("account_number"),
            "starting_value":     start,
            "ending_value":       _safe_get(s, "ending_value"),
            "deposits":           _safe_get(s, "deposits"),
            "withdrawals":        _safe_get(s, "withdrawals"),
            "security_transfers": _safe_get(s, "security_transfers"),
            "change_in_value":    civ,
            "dividend_income":    _safe_get(s, "dividend_income"),
            "interest_income":    _safe_get(s, "interest_income"),
            "realised_gains":     _safe_get(s, "realised_gains"),
            "realised_st":        _safe_get(s, "realised_st"),
            "realised_lt":        _safe_get(s, "realised_lt"),
            "unrealised_gains":   _safe_get(s, "unrealised_gains"),
            "net_cash_flow":      _safe_get(s, "deposits") - _safe_get(s, "withdrawals"),
            "return_pct":         rp,
        })

    tdf = pd.DataFrame(rows).sort_values(["date", "broker"])

    # ── Total Portfolio rows (one per calendar month) ─────────────────────────
    sum_cols = [
        "starting_value", "ending_value", "deposits", "withdrawals",
        "security_transfers", "change_in_value", "dividend_income",
        "interest_income", "realised_gains", "realised_st", "realised_lt",
        "unrealised_gains", "net_cash_flow",
    ]
    monthly = tdf.groupby("date")[sum_cols].sum().reset_index()
    monthly["return_pct"] = monthly.apply(
        lambda r: _monthly_return(r["change_in_value"], r["starting_value"]) * 100,
        axis=1,
    )
    monthly["broker"]         = "Total Portfolio"
    monthly["account_number"] = None
    monthly["month"]          = monthly["date"].dt.strftime("%Y-%m")
    monthly = monthly[tdf.columns]

    tdf = pd.concat([tdf, monthly], ignore_index=True).sort_values(["date", "broker"])

    # Cumulative index for Total Portfolio (start = 100)
    tp = tdf[tdf["broker"] == "Total Portfolio"].copy()
    if not tp.empty and tp.iloc[0]["starting_value"] > 0:
        base = tp.iloc[0]["starting_value"]
        tdf.loc[tdf["broker"] == "Total Portfolio", "cumulative_value"] = (
            tp["ending_value"] / base * 100
        ).values
    tdf["cumulative_value"] = tdf.get("cumulative_value", pd.Series(dtype=float)).fillna(0)

    # Backward-compat aliases
    tdf["start_value"] = tdf["starting_value"]
    tdf["end_value"]   = tdf["ending_value"]

    return tdf


def build_summary_export_dataframe(
    statements: List[Dict], risk_free_rate: float = 4.5
) -> pd.DataFrame:
    """One row per account — all aggregated metrics."""
    if not statements:
        return pd.DataFrame()

    df = pd.DataFrame(statements)
    df["_key"] = df.apply(
        lambda r: r["account_number"] if pd.notna(r.get("account_number")) and r.get("account_number") else r["broker"],
        axis=1,
    )

    rows = []
    for key in df["_key"].unique():
        acct = df[df["_key"] == key].sort_values("start_date")
        first, last = acct.iloc[0], acct.iloc[-1]

        # Aggregates
        start_val   = float(first["starting_value"])
        end_val     = float(last["ending_value"])
        deposits    = float(acct["deposits"].sum())
        withdrawals = float(acct["withdrawals"].sum())
        net_cf      = deposits - withdrawals
        sec_xfr     = float(acct.get("security_transfers", pd.Series([0])).sum())
        civ_total   = float(acct["change_in_value"].sum()) if "change_in_value" in acct else 0.0
        div_total   = float(acct["dividend_income"].sum()) if "dividend_income" in acct else 0.0
        int_total   = float(acct["interest_income"].sum()) if "interest_income" in acct else 0.0
        real_total  = float(acct["realised_gains"].sum())
        real_st     = float(acct["realised_st"].sum()) if "realised_st" in acct else 0.0
        real_lt     = float(acct["realised_lt"].sum()) if "realised_lt" in acct else 0.0
        unreal      = float(last["unrealised_gains"])
        n_months    = len(acct)

        # Monthly returns for this account
        monthly_r = acct.apply(
            lambda r: pd.Series({
                "end_date": r["end_date"],
                "r": _monthly_return(float(r["change_in_value"]), float(r["starting_value"])),
            }),
            axis=1,
        ).set_index("end_date")["r"]

        twr = _twr(monthly_r)
        n_m  = n_months or 1
        twr_ann = float(((1 + twr) ** (12 / n_m)) - 1) if n_m > 0 else 0.0
        risk = _risk_metrics(monthly_r, risk_free_rate)

        rows.append({
            "Broker":                first["broker"],
            "Account Number":        first.get("account_number"),
            "Period":                f"{first['start_date'].strftime('%Y-%m-%d')} → {last['end_date'].strftime('%Y-%m-%d')}",
            "Months":                n_months,
            "Starting Value":        start_val,
            "Ending Value":          end_val,
            "Deposits":              deposits,
            "Withdrawals":           withdrawals,
            "Net Cash Flow":         net_cf,
            "Security Transfers":    sec_xfr,
            "Change in Value":       civ_total,
            "Dividend Income":       div_total,
            "Interest Income":       int_total,
            "Realised (ST)":         real_st,
            "Realised (LT)":         real_lt,
            "Realised Gains":        real_total,
            "Unrealised Gains":      unreal,
            "Total Gains":           real_total + unreal,
            "TWR (%)":               round(twr * 100, 2),
            "TWR Annualized (%)":    round(twr_ann * 100, 2),
            "Return (%)":            round(twr * 100, 2),   # alias
            "Sharpe Ratio":          round(risk["sharpe"], 2),
            "Sortino Ratio":         round(risk["sortino"], 2),
            "Max Drawdown (%)":      round(risk["max_dd"], 2),
            "Win Rate (%)":          round(risk["win_rate"], 2),
            "Volatility (%)":        round(risk["volatility"], 2),
            "Files":                 n_months,
        })

    return pd.DataFrame(rows)


def calculate_metrics(statements: List[Dict], risk_free_rate: float = 4.5) -> Dict:
    """Consolidated portfolio metrics — all accounts combined."""
    if not statements:
        return {}

    df = pd.DataFrame(statements)

    if "start_date" not in df.columns or df["start_date"].isna().all():
        return _calculate_metrics_no_dates(statements, risk_free_rate)

    # Ensure numeric
    for col in ["change_in_value", "starting_value", "ending_value",
                "deposits", "withdrawals", "realised_gains", "realised_st",
                "realised_lt", "unrealised_gains", "dividend_income", "interest_income"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        else:
            df[col] = 0.0

    # ── Per-account summary ───────────────────────────────────────────────────
    df["_key"] = df.apply(
        lambda r: r["account_number"] if pd.notna(r.get("account_number")) and r.get("account_number") else r["broker"],
        axis=1,
    )
    broker_summary = {}
    for key in df["_key"].unique():
        acct = df[df["_key"] == key].sort_values("start_date")
        first, last = acct.iloc[0], acct.iloc[-1]
        label = (f"{first['broker']} ({first.get('account_number')})"
                 if first.get("account_number") else first["broker"])
        broker_summary[label] = {
            "starting_value":  float(first["starting_value"]),
            "ending_value":    float(last["ending_value"]),
            "deposits":        float(acct["deposits"].sum()),
            "withdrawals":     float(acct["withdrawals"].sum()),
            "realised_gains":  float(acct["realised_gains"].sum()),
            "realised_st":     float(acct["realised_st"].sum()),
            "realised_lt":     float(acct["realised_lt"].sum()),
            "dividend_income": float(acct["dividend_income"].sum()),
            "interest_income": float(acct["interest_income"].sum()),
            "unrealised_gains":float(last["unrealised_gains"]),
            "change_in_value": float(acct["change_in_value"].sum()),
            "files":           acct["filename"].tolist(),
            "num_months":      len(acct),
        }
        sv = broker_summary[label]["starting_value"]
        ev = broker_summary[label]["ending_value"]
        broker_summary[label]["return_pct"] = (ev - sv) / sv * 100 if sv > 0 else 0.0

    # ── Consolidated totals ───────────────────────────────────────────────────
    total_start      = sum(b["starting_value"]  for b in broker_summary.values())
    total_end        = sum(b["ending_value"]     for b in broker_summary.values())
    total_deposits   = sum(b["deposits"]         for b in broker_summary.values())
    total_withdrawals= sum(b["withdrawals"]      for b in broker_summary.values())
    net_cf           = total_deposits - total_withdrawals
    total_civ        = sum(b["change_in_value"]  for b in broker_summary.values())
    total_div        = sum(b["dividend_income"]  for b in broker_summary.values())
    total_int        = sum(b["interest_income"]  for b in broker_summary.values())
    total_real       = sum(b["realised_gains"]   for b in broker_summary.values())
    total_real_st    = sum(b["realised_st"]      for b in broker_summary.values())
    total_real_lt    = sum(b["realised_lt"]      for b in broker_summary.values())
    total_unreal     = sum(b["unrealised_gains"] for b in broker_summary.values())

    # ── Consolidated monthly returns (for TWR + risk metrics) ─────────────────
    monthly_r = _consolidated_monthly_returns(df)

    first_date = df["start_date"].min()
    last_date  = df["end_date"].max()
    months_in_period = (
        (last_date.year - first_date.year) * 12
        + (last_date.month - first_date.month) + 1
    )

    twr        = _twr(monthly_r)
    twr_ann    = float(((1 + twr) ** (12 / months_in_period)) - 1) if months_in_period > 0 else 0.0
    twr_monthly= float(((1 + twr) ** (1 / months_in_period)) - 1) if months_in_period > 0 else 0.0

    # MWR (Modified Dietz) for the full period
    avg_cap = total_start + net_cf / 2
    mwr     = total_civ / avg_cap if avg_cap > 0 else 0.0
    mwr_ann = float(((1 + mwr) ** (12 / months_in_period)) - 1) if months_in_period > 0 else 0.0

    risk = _risk_metrics(monthly_r, risk_free_rate)

    return {
        "broker_summary":        broker_summary,
        "total_starting_value":  total_start,
        "total_ending_value":    total_end,
        "change_in_value":       total_end - total_start,
        "total_change_in_value": total_civ,
        "total_deposits":        total_deposits,
        "total_withdrawals":     total_withdrawals,
        "net_cash_flow":         net_cf,
        "investment_return":     total_civ,
        "total_dividend_income": total_div,
        "total_interest_income": total_int,
        "total_realised_gains":  total_real,
        "total_realised_st":     total_real_st,
        "total_realised_lt":     total_real_lt,
        "total_unrealised_gains":total_unreal,
        "total_gains":           total_real + total_unreal,
        "months_in_period":      months_in_period,
        # Returns
        "twr_total":             twr * 100,
        "twr_monthly":           twr_monthly * 100,
        "twr_annualized":        twr_ann * 100,
        "mwr_period":            mwr * 100,
        "mwr_annualized":        mwr_ann * 100,
        # Risk
        "sharpe_ratio":          risk["sharpe"],
        "sortino_ratio":         risk["sortino"],
        "max_drawdown":          risk["max_dd"],
        "win_rate":              risk["win_rate"],
        "volatility":            risk["volatility"],
        "risk_free_rate":        risk_free_rate,
    }


def _calculate_metrics_no_dates(statements, risk_free_rate):
    """Fallback when statements lack dates."""
    broker_summary = {}
    for s in statements:
        key = s.get("account_number") or s["broker"]
        if key not in broker_summary:
            broker_summary[key] = dict(
                starting_value=0, ending_value=0, deposits=0, withdrawals=0,
                realised_gains=0, realised_st=0, realised_lt=0,
                dividend_income=0, interest_income=0, unrealised_gains=0,
                change_in_value=0, files=[],
            )
        for f in ["starting_value","ending_value","deposits","withdrawals",
                  "realised_gains","realised_st","realised_lt",
                  "dividend_income","interest_income","unrealised_gains","change_in_value"]:
            broker_summary[key][f] += _safe_get(s, f)
        broker_summary[key]["files"].append(s.get("filename",""))

    total_start = sum(b["starting_value"] for b in broker_summary.values())
    total_end   = sum(b["ending_value"]   for b in broker_summary.values())
    total_civ   = sum(b["change_in_value"] for b in broker_summary.values())
    deps        = sum(b["deposits"]        for b in broker_summary.values())
    withs       = sum(b["withdrawals"]     for b in broker_summary.values())
    net_cf      = deps - withs
    avg_cap     = total_start + net_cf / 2

    twr = total_civ / total_start if total_start > 0 else 0.0
    mwr = total_civ / avg_cap     if avg_cap > 0     else 0.0

    return {
        "broker_summary":        broker_summary,
        "total_starting_value":  total_start,
        "total_ending_value":    total_end,
        "change_in_value":       total_end - total_start,
        "total_change_in_value": total_civ,
        "total_deposits":        deps,
        "total_withdrawals":     withs,
        "net_cash_flow":         net_cf,
        "investment_return":     total_civ,
        "total_dividend_income": sum(b["dividend_income"] for b in broker_summary.values()),
        "total_interest_income": sum(b["interest_income"] for b in broker_summary.values()),
        "total_realised_gains":  sum(b["realised_gains"]  for b in broker_summary.values()),
        "total_realised_st":     sum(b["realised_st"]     for b in broker_summary.values()),
        "total_realised_lt":     sum(b["realised_lt"]     for b in broker_summary.values()),
        "total_unrealised_gains":sum(b["unrealised_gains"] for b in broker_summary.values()),
        "total_gains":           sum(b["realised_gains"] + b["unrealised_gains"] for b in broker_summary.values()),
        "months_in_period":      1,
        "twr_total":             twr * 100,
        "twr_monthly":           twr * 100,
        "twr_annualized":        twr * 100,
        "mwr_period":            mwr * 100,
        "mwr_annualized":        mwr * 100,
        "sharpe_ratio":0, "sortino_ratio":0, "max_drawdown":0, "win_rate":0, "volatility":0,
        "risk_free_rate":        risk_free_rate,
    }


def prepare_export_data(
    metrics: Dict, timeline_df: pd.DataFrame = None, summary_df: pd.DataFrame = None
) -> Dict:
    """Prepare data for CSV/Excel export."""
    export_data = {}
    if summary_df is not None and not summary_df.empty:
        export_data["Portfolio_Summary"] = summary_df
    if timeline_df is not None and not timeline_df.empty:
        export_data["Monthly_Timeline"] = timeline_df
    details = []
    for broker, data in metrics.get("broker_summary", {}).items():
        for fn in data.get("files", []):
            details.append({
                "Broker": broker, "Filename": fn,
                "Starting Value": data["starting_value"],
                "Ending Value":   data["ending_value"],
                "Deposits":       data["deposits"],
                "Withdrawals":    data["withdrawals"],
                "Change in Value":data.get("change_in_value", 0),
                "Dividend Income":data.get("dividend_income", 0),
                "Interest Income":data.get("interest_income", 0),
                "Realised (ST)":  data.get("realised_st", 0),
                "Realised (LT)":  data.get("realised_lt", 0),
                "Realised Gains": data["realised_gains"],
                "Unrealised Gains":data["unrealised_gains"],
            })
    if details:
        export_data["File_Details"] = pd.DataFrame(details)
    return export_data
