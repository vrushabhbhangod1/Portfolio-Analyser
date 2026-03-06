"""
Quick test script to run PDF/CSV files through all broker parsers and inspect output.
Usage: python tests/test_broker_parsers.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime
import pandas as pd

# Ensure project root is on the path so src.* imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.broker_parsers import (
    parse_fidelity,
    parse_fidelity_csv,
    parse_etrade,
    parse_ibkr,
    parse_ibkr_csv,
)


class FakePdfFile:
    """Mimics the Streamlit UploadedFile object parsers expect."""

    def __init__(self, path: str):
        self._path = Path(path)
        self.name = self._path.name
        self._file = open(self._path, "rb")

    def read(self, *args):
        return self._file.read(*args)

    def seek(self, *args):
        return self._file.seek(*args)

    def tell(self):
        return self._file.tell()

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def pretty_print(data: dict):
    """Print parsed data in a readable format."""
    for k, v in data.items():
        if k == "holdings":
            print(f"  {k}: {len(v)} entries")
        elif hasattr(v, "strftime"):
            print(f"  {k}: {v.strftime('%Y-%m-%d')}")
        else:
            print(f"  {k}: {v}")


STATEMENTS_DIR = Path(__file__).parent.parent / "statements"

# ------------------------------------------------------------------
# Fidelity PDF files — scan statements/fidelity/*.pdf, all months
# ------------------------------------------------------------------
fidelity_pdf_dir = STATEMENTS_DIR / "fidelity"
fidelity_pdfs = (
    sorted(fidelity_pdf_dir.glob("Statement*.pdf")) if fidelity_pdf_dir.exists() else []
)

print("=" * 60)
print("FIDELITY PDF PARSER TEST")
print("=" * 60)

all_fidelity_stmts = []
# Track most-recent holdings per account (keyed by account_number)
latest_fid_holdings: dict = {}

for path in fidelity_pdfs:
    print(f"\n--- {path.name} ---")
    try:
        with FakePdfFile(str(path)) as f:
            stmts, holdings_df = parse_fidelity(f)
        all_fidelity_stmts.extend(stmts)
        # Keep holdings from the most recent PDF per account
        for s in stmts:
            acct = s["account_number"]
            if not holdings_df.empty:
                prev = latest_fid_holdings.get(acct)
                if prev is None or (s["end_date"] or datetime.min) >= prev[0]:
                    latest_fid_holdings[acct] = (s["end_date"] or datetime.min, holdings_df)
        print(f"  parsed {len(stmts)} month(s)")
    except Exception as e:
        import traceback
        print(f"  ERROR: {e}")
        traceback.print_exc()

if not fidelity_pdfs:
    print("\n[SKIP] no PDFs found in statements/fidelity/")

if all_fidelity_stmts:
    all_fidelity_stmts.sort(key=lambda s: s["start_date"] or datetime.min)

    accounts = sorted(set(s["account_number"] for s in all_fidelity_stmts))
    print(f"\n  Total statements : {len(all_fidelity_stmts)} across {len(accounts)} account(s)")

    hdr = f"  {'Period':<18} {'Start':>12} {'End':>12} {'Dep':>10} {'With':>8} {'Div':>7} {'Int':>7} {'Chg':>10} {'Real(ST)':>10} {'Real(LT)':>10} {'Unrealised':>11}"
    for acct in accounts:
        print(f"\n  {'─'*125}")
        print(f"  {acct}")
        print(hdr)
        for s in [x for x in all_fidelity_stmts if x["account_number"] == acct]:
            print(
                f"  {s['period']:<18} {s['starting_value']:>12,.2f} {s['ending_value']:>12,.2f}"
                f" {s['deposits']:>10,.2f} {s['withdrawals']:>8,.2f}"
                f" {s['dividend_income']:>7,.2f} {s['interest_income']:>7,.2f}"
                f" {s['change_in_value']:>10,.2f} {s.get('realised_st',0):>10,.2f} {s.get('realised_lt',0):>10,.2f} {s['unrealised_gains']:>11,.2f}"
            )

    # Ending portfolio — most recent holdings per account
    ending_dfs = [df for _, df in sorted(latest_fid_holdings.values(), key=lambda x: x[0])]
    if ending_dfs:
        ending_holdings = pd.concat(ending_dfs, ignore_index=True)
        print(f"\n  {'─'*110}")
        print(f"  ENDING PORTFOLIO ({len(ending_holdings)} positions)")
        print(f"  {'Account':<15} {'Symbol':<8} {'Description':<35} {'Qty':>8} {'MktVal':>12} {'Unrealised':>11}")
        for _, row in ending_holdings.sort_values("unrealized_pnl", ascending=False).iterrows():
            print(
                f"  {row['account_number']:<15} {row['symbol']:<8} {str(row['description'])[:35]:<35}"
                f" {row['quantity']:>8,.3f} {row['market_value']:>12,.2f} {row['unrealized_pnl']:>11,.2f}"
            )


# ------------------------------------------------------------------
# E*TRADE files — scan all PDFs in statements/etrade/
# ------------------------------------------------------------------
etrade_dir = STATEMENTS_DIR / "etrade"
etrade_pdf_files = sorted(etrade_dir.glob("*.pdf")) if etrade_dir.exists() else []

print("\n" + "=" * 60)
print("E*TRADE PARSER TEST")
print("=" * 60)

all_etrade_stmts = []
all_etrade_holdings = []

for path in etrade_pdf_files:
    print(f"\n--- {path.name} ---")
    try:
        with FakePdfFile(str(path)) as f:
            stmts, holdings_df = parse_etrade(f)
        all_etrade_stmts.extend(stmts)
        if not holdings_df.empty:
            all_etrade_holdings.append(holdings_df)
        print(f"  parsed {len(stmts)} month(s)")
    except Exception as e:
        import traceback

        print(f"  ERROR: {e}")
        traceback.print_exc()

if not etrade_pdf_files:
    print("\n[SKIP] no PDFs found in statements/etrade/")

if all_etrade_stmts:
    # sort chronologically
    all_etrade_stmts.sort(key=lambda s: s["start_date"] or datetime.min)
    combined_holdings = (
        pd.concat(all_etrade_holdings, ignore_index=True).drop_duplicates(
            subset=["account_number", "symbol"]
        )
        if all_etrade_holdings
        else pd.DataFrame()
    )

    accounts = sorted(set(s["account_number"] for s in all_etrade_stmts))
    print(
        f"\n  Total statements : {len(all_etrade_stmts)} across {len(accounts)} account(s)"
    )

    hdr = f"  {'Period':<18} {'Start':>12} {'End':>12} {'Dep':>10} {'With':>8} {'Div':>7} {'Int':>7} {'Chg':>10} {'Real(ST)':>10} {'Real(LT)':>10} {'Unrealised':>11}"
    for acct in accounts:
        print(f"\n  {'─'*125}")
        print(f"  {acct}")
        print(hdr)
        for s in [x for x in all_etrade_stmts if x["account_number"] == acct]:
            print(
                f"  {s['period']:<18} {s['starting_value']:>12,.2f} {s['ending_value']:>12,.2f}"
                f" {s['deposits']:>10,.2f} {s['withdrawals']:>8,.2f}"
                f" {s['dividend_income']:>7,.2f} {s['interest_income']:>7,.2f}"
                f" {s['change_in_value']:>10,.2f} {s.get('realised_st',0):>10,.2f} {s.get('realised_lt',0):>10,.2f} {s['unrealised_gains']:>11,.2f}"
            )

    if not combined_holdings.empty:
        print(f"\n  {'─'*110}")
        print(f"  ENDING HOLDINGS ({len(combined_holdings)} positions)")
        print(
            f"  {'Account':<15} {'Symbol':<8} {'Description':<35} {'Qty':>8} {'MktVal':>12} {'Unrealised':>11}"
        )
        for _, row in combined_holdings.sort_values(
            "unrealized_pnl", ascending=False
        ).iterrows():
            print(
                f"  {row['account_number']:<15} {row['symbol']:<8} {str(row['description'])[:35]:<35}"
                f" {row['quantity']:>8,.3f} {row['market_value']:>12,.2f} {row['unrealized_pnl']:>11,.2f}"
            )

# ------------------------------------------------------------------
# IBKR files
# ------------------------------------------------------------------
ibkr_files = [
    "MULTI_20260101_20260213.pdf",
]

print("\n" + "=" * 60)
print("IBKR PARSER TEST")
print("=" * 60)

for fname in ibkr_files:
    path = STATEMENTS_DIR / fname
    if not path.exists():
        print(f"\n[SKIP] {fname} — file not found")
        continue

    print(f"\n--- {fname} ---")
    try:
        with FakePdfFile(str(path)) as f:
            result = parse_ibkr(f)
        pretty_print(result)
    except Exception as e:
        print(f"  ERROR: {e}")

# ------------------------------------------------------------------
# IBKR CSV parser
# ------------------------------------------------------------------
ibkr_csv_files = ["ibkr/Portfolio_Analysis_Monthly.csv"]

print("\n" + "=" * 60)
print("IBKR CSV PARSER TEST")
print("=" * 60)

for fname in ibkr_csv_files:
    path = STATEMENTS_DIR / fname
    if not path.exists():
        print(f"\n[SKIP] {fname} — file not found")
        continue

    print(f"\n--- {fname} ---")
    try:
        with FakePdfFile(str(path)) as f:
            stmts, holdings = parse_ibkr_csv(f)

        accounts = sorted(set(s["account_number"] for s in stmts))
        print(
            f"  Statements : {len(stmts)} ({len(accounts)} accounts × {len(stmts)//len(accounts)} months)"
        )
        print(f"  Holdings   : {len(holdings)} rows\n")

        # Full monthly breakdown per account
        hdr = f"  {'Period':<18} {'Start':>12} {'End':>12} {'Dep':>10} {'With':>8} {'Div':>7} {'Int':>7} {'Chg':>10} {'Real(ST)':>10} {'Real(LT)':>10} {'Unrealised':>11}"
        for acct in accounts:
            print(f"  {'─'*125}")
            print(f"  {acct}")
            print(hdr)
            for s in [x for x in stmts if x["account_number"] == acct]:
                print(
                    f"  {s['period']:<18} {s['starting_value']:>12,.2f} {s['ending_value']:>12,.2f}"
                    f" {s['deposits']:>10,.2f} {s['withdrawals']:>8,.2f}"
                    f" {s['dividend_income']:>7,.2f} {s['interest_income']:>7,.2f}"
                    f" {s['change_in_value']:>10,.2f} {s.get('realised_st', 0):>10,.2f} {s.get('realised_lt', 0):>10,.2f} {s['unrealised_gains']:>11,.2f}"
                )

        # Holdings
        if not holdings.empty:
            print(f"\n  {'─'*110}")
            print(f"  ENDING HOLDINGS ({len(holdings)} positions)")
            print(
                f"  {'Account':<12} {'Symbol':<8} {'Description':<35} {'Unrealised':>11} {'Realised':>10} {'Total':>10}"
            )
            for _, row in holdings.sort_values(
                ["account_number", "unrealized_pnl"], ascending=[True, False]
            ).iterrows():
                print(
                    f"  {row['account_number']:<12} {row['symbol']:<8} {row['description'][:35]:<35}"
                    f" {row['unrealized_pnl']:>11,.2f} {row['realized_pnl']:>10,.2f} {row['total_pnl']:>10,.2f}"
                )

    except Exception as e:
        import traceback

        print(f"  ERROR: {e}")
        traceback.print_exc()
