"""
PDF Parsers for E*TRADE, Fidelity, and IBKR statements
"""

import re
import pandas as pd
import numpy as np
from datetime import datetime
from calendar import monthrange
from pypdf import PdfReader
from typing import Dict, List, Tuple
import io


def extract_text_from_pdf(pdf_file) -> str:
    """Extract text from uploaded PDF file object"""
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text


def _parse_short_date(date_str: str) -> datetime:
    """Parse M/D/YY or M/D/YYYY into a datetime."""
    parts = date_str.split("/")
    month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
    if year < 100:
        year += 2000 if year < 50 else 1900
    return datetime(year, month, day)


def _parse_etrade_month_text(text: str, filename: str) -> Dict:
    """Parse a single month's text from an E*TRADE statement into a dict."""

    def _num(s):
        return float(s.replace(",", ""))

    data = {
        "broker": "E*TRADE",
        "account_number": None,
        "filename": filename,
        "period": None,
        "start_date": None,
        "end_date": None,
        "starting_value": 0.0,
        "ending_value": 0.0,
        "deposits": 0.0,
        "withdrawals": 0.0,
        "security_transfers": 0.0,
        "change_in_value": 0.0,
        "realised_gains": 0.0,
        "realised_st": 0.0,
        "realised_lt": 0.0,
        "unrealised_gains": 0.0,
        "dividend_income": 0.0,
        "interest_income": 0.0,
        "holdings": [],
        "needs_clipping": False,
        "original_end_date": None,
    }

    # Account number
    acct_match = re.search(r"\b(\d{3}-\d{6}-\d{3})\b", text)
    if acct_match:
        data["account_number"] = acct_match.group(1)

    # Dates — "For the Period January 1 -31, 2025"
    period_match = re.search(
        r"For the Period\s+(\w+)\s+(\d+)\s*-\s*(\d+),\s*(\d{4})", text
    )
    if period_match:
        try:
            month_num = datetime.strptime(period_match.group(1), "%B").month
            year = int(period_match.group(4))
            data["start_date"] = datetime(year, month_num, int(period_match.group(2)))
            data["end_date"] = datetime(year, month_num, int(period_match.group(3)))
            data["period"] = data["start_date"].strftime("%B %Y")
        except Exception as ex:
            print(f"E*TRADE date parse error: {ex}")

    # CHANGE IN VALUE section
    civ_match = re.search(
        r"CHANGE IN VALUE OF YOUR ACCOUNT.*?TOTAL ENDING VALUE\s+\$([0-9,]+\.\d+)",
        text, re.DOTALL,
    )
    if civ_match:
        civ = civ_match.group(0)
        beg = re.search(r"TOTAL BEGINNING VALUE\s+\$([0-9,]+\.\d+)", civ)
        if beg:
            data["starting_value"] = _num(beg.group(1))
        data["ending_value"] = _num(civ_match.group(1))

        cr = re.search(r"Credits\s+([0-9,]+\.\d+)", civ)
        if cr:
            data["deposits"] = _num(cr.group(1))

        db = re.search(r"Debits\s+\(([0-9,]+\.\d+)\)", civ)
        if db:
            data["withdrawals"] = _num(db.group(1))

        sec_out = re.search(r"Security Transfers\s+\(([0-9,]+\.\d+)\)", civ)
        if sec_out:
            data["security_transfers"] = -_num(sec_out.group(1))
        else:
            sec_in = re.search(r"Security Transfers\s+([0-9,]+\.\d+)", civ)
            if sec_in:
                data["security_transfers"] = _num(sec_in.group(1))

        chg_neg = re.search(r"Change in Value\s+\(([0-9,]+\.\d+)\)", civ)
        if chg_neg:
            data["change_in_value"] = -_num(chg_neg.group(1))
        else:
            chg_pos = re.search(r"Change in Value\s+([0-9,]+\.\d+)", civ)
            if chg_pos:
                data["change_in_value"] = _num(chg_pos.group(1))
    else:
        # page-1 fallback
        beg = re.search(r"Beginning Total Value.*?\$([0-9,]+\.\d+)", text, re.DOTALL)
        if beg:
            data["starting_value"] = _num(beg.group(1))
        end = re.search(r"Ending Total Value.*?\$([0-9,]+\.\d+)", text, re.DOTALL)
        if end:
            data["ending_value"] = _num(end.group(1))
        cr = re.search(r"Credits\s+([0-9,]+\.\d+)", text)
        if cr:
            data["deposits"] = _num(cr.group(1))
        db = re.search(r"Debits\s+\(([0-9,]+\.\d+)\)", text)
        if db:
            data["withdrawals"] = _num(db.group(1))

    # GAIN/(LOSS) SUMMARY — short term + long term realized, this period column only
    gl_match = re.search(r"GAIN/\(LOSS\) SUMMARY.*?TOTAL GAIN/\(LOSS\)", text, re.DOTALL)
    if gl_match:
        gl = gl_match.group(0)
        # Short-term gain (positive)
        st_gain = re.search(r"Short-Term Gain\s+\$?([0-9,]+\.\d+)", gl)
        st_loss = re.search(r"Short-Term \(Loss\)\s+\(([0-9,]+\.\d+)\)", gl)
        lt_gain = re.search(r"Long-Term Gain\s+\$?([0-9,]+\.\d+)", gl)
        lt_loss = re.search(r"Long-Term \(Loss\)\s+\(([0-9,]+\.\d+)\)", gl)

        st = (_num(st_gain.group(1)) if st_gain else 0.0) - (_num(st_loss.group(1)) if st_loss else 0.0)
        lt = (_num(lt_gain.group(1)) if lt_gain else 0.0) - (_num(lt_loss.group(1)) if lt_loss else 0.0)
        data["realised_st"] = st
        data["realised_lt"] = lt
        data["realised_gains"] = st + lt

    # INCOME AND DISTRIBUTION SUMMARY
    inc_match = re.search(r"INCOME AND DISTRIBUTION SUMMARY.*?(?=\n[A-Z]{3,}|\Z)", text, re.DOTALL)
    if inc_match:
        inc = inc_match.group(0)
        qual_div = re.search(r"Qualified Dividends\s+\$?([0-9,]+\.\d+)", inc)
        ord_div  = re.search(r"Ordinary Dividends\s+\$?([0-9,]+\.\d+)", inc)
        int_inc  = re.search(r"(?:Taxable )?Interest\s+\$?([0-9,]+\.\d+)", inc)
        if qual_div:
            data["dividend_income"] += _num(qual_div.group(1))
        if ord_div:
            data["dividend_income"] += _num(ord_div.group(1))
        if int_inc:
            data["interest_income"] = _num(int_inc.group(1))

    data["unrealised_gains"] = (
        data["change_in_value"]
        - data["realised_gains"]
        - data["dividend_income"]
        - data["interest_income"]
    )

    return data


def _parse_etrade_holdings(text: str, account_number: str) -> pd.DataFrame:
    """Parse ending holdings from an E*TRADE month's text (most recent month)."""
    rows = []
    # Each stock line: NAME (TICKER) [Purchases/Reinvestments rows...] Total qty cost mktval unrealized
    # Match the "Total" summary line per position
    for m in re.finditer(
        r"([A-Z][A-Z0-9 &\-\.'/]+)\s+\(([A-Z0-9\.]+)\).*?Total\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+\(?([\d,]+\.\d+)\)?",
        text, re.DOTALL
    ):
        desc, ticker, qty, cost, mktval, unreal_raw = m.groups()
        # check if unrealized is negative (wrapped in parens in original)
        snippet = text[m.start():m.end()]
        unreal = -float(unreal_raw.replace(",", "")) if f"({unreal_raw}" in snippet else float(unreal_raw.replace(",", ""))
        rows.append({
            "account_number": account_number,
            "symbol": ticker.strip(),
            "description": desc.strip(),
            "quantity": float(qty.replace(",", "")),
            "market_value": float(mktval.replace(",", "")),
            "unrealized_pnl": unreal,
        })
    # Also catch single-line positions (no Purchases/Reinvestments breakdown)
    for m in re.finditer(
        r"([A-Z][A-Z0-9 &\-\.'/]+)\s+\(([A-Z0-9\.]+)\)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+\(?([\d,]+\.\d+)\)?",
        text
    ):
        desc, ticker, qty, price, cost, mktval, unreal_raw = m.groups()
        snippet = text[m.start():m.end()]
        unreal = -float(unreal_raw.replace(",", "")) if f"({unreal_raw}" in snippet else float(unreal_raw.replace(",", ""))
        # avoid duplicating tickers already captured above
        if not any(r["symbol"] == ticker.strip() for r in rows):
            rows.append({
                "account_number": account_number,
                "symbol": ticker.strip(),
                "description": desc.strip(),
                "quantity": float(qty.replace(",", "")),
                "market_value": float(mktval.replace(",", "")),
                "unrealized_pnl": unreal,
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def parse_etrade(pdf_file) -> Tuple[List[Dict], pd.DataFrame]:
    """Parse E*TRADE (Morgan Stanley) statement — handles multi-month PDFs.
    Returns (list of monthly statement dicts, ending_holdings_df)."""
    from pypdf import PdfReader
    import io as _io

    content = pdf_file.read()
    reader = PdfReader(_io.BytesIO(content))
    filename = pdf_file.name

    # Split pages into monthly chunks by detecting "For the Period" on each page
    month_pages = []  # list of (start_page_idx, period_str)
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        m = re.search(r"For the Period\s+(\w+\s+\d+\s*-\s*\d+,\s*\d{4})", text)
        if m:
            period_str = m.group(1)
            if not month_pages or month_pages[-1][1] != period_str:
                month_pages.append((i, period_str))

    if not month_pages:
        full_text = "\n".join(p.extract_text() or "" for p in reader.pages)
        result = _parse_etrade_month_text(full_text, filename)
        holdings_df = _parse_etrade_holdings(full_text, result.get("account_number", ""))
        return [result], holdings_df

    # Build text for each month chunk
    results = []
    for idx, (start_pg, period_str) in enumerate(month_pages):
        end_pg = month_pages[idx + 1][0] if idx + 1 < len(month_pages) else len(reader.pages)
        chunk_text = "\n".join(
            reader.pages[i].extract_text() or "" for i in range(start_pg, end_pg)
        )
        parsed = _parse_etrade_month_text(chunk_text, filename)
        results.append(parsed)

    # Holdings from the first chunk (most recent month — PDF is reverse chronological)
    first_chunk = "\n".join(
        reader.pages[i].extract_text() or ""
        for i in range(month_pages[0][0], month_pages[1][0] if len(month_pages) > 1 else len(reader.pages))
    )
    acct = results[0].get("account_number", "") if results else ""
    holdings_df = _parse_etrade_holdings(first_chunk, acct)

    return results, holdings_df


def parse_fidelity_csv(
    history_file, statement_file
) -> Tuple[List[Dict], pd.DataFrame]:
    """Parse Fidelity BrokerageLink CSV files.
    history_file  — History_for_Account_*.csv  (transactions)
    statement_file — Statement*.csv             (starting balance + holdings)
    Returns (list of monthly dicts, ending_holdings_df)
    """
    import io as _io

    # ── Read history CSV (skip BOM + 2 blank header lines, skip footer) ──────
    hist_content = history_file.read()
    if isinstance(hist_content, bytes):
        hist_content = hist_content.decode("utf-8-sig")
    # strip leading blank lines
    hist_lines = hist_content.splitlines()
    data_start = next(i for i, l in enumerate(hist_lines) if l.startswith("Run Date"))
    hist_df = pd.read_csv(
        _io.StringIO("\n".join(hist_lines[data_start:])),
        on_bad_lines="skip",
    )
    hist_df["Run Date"] = pd.to_datetime(hist_df["Run Date"], errors="coerce")
    hist_df = hist_df.dropna(subset=["Run Date"])
    hist_df["Amount ($)"] = pd.to_numeric(hist_df["Amount ($)"], errors="coerce").fillna(0.0)
    hist_df["YearMonth"] = hist_df["Run Date"].dt.to_period("M")
    acct_id = history_file.name.split("Account_")[-1].replace(".csv", "").replace("-2", "")

    # ── Read statement CSV (starting balance + ending holdings) ──────────────
    stmt_content = statement_file.read()
    if isinstance(stmt_content, bytes):
        stmt_content = stmt_content.decode("utf-8-sig")
    stmt_lines = stmt_content.splitlines()

    # Data row starts with "BrokerageLink," (comma distinguishes it from the header)
    # format: AccountType,Account,Beginning mkt Value,Change in Investment,Ending mkt Value,...
    summary_row = next(
        (l for l in stmt_lines if l.strip().startswith("BrokerageLink,")), ""
    )
    summary_parts = summary_row.split(",")
    starting_value = 0.0
    ending_value_stmt = 0.0
    try:
        starting_value = float(summary_parts[2].replace(",", "").strip())
        ending_value_stmt = float(summary_parts[4].replace(",", "").strip())
    except Exception:
        pass

    # ── Categorize transactions ───────────────────────────────────────────────
    def action_type(action: str) -> str:
        a = action.upper()
        if a.startswith("YOU BOUGHT") or a.startswith("REINVESTMENT"):
            return "buy"
        if a.startswith("YOU SOLD"):
            return "sell"
        if "DIVIDEND RECEIVED" in a:
            return "dividend"
        if "LONG-TERM CAP GAIN" in a:
            return "lt_gain"
        if "SHORT-TERM CAP GAIN" in a:
            return "st_gain"
        if "ELECTRONIC FUNDS TRANSFER" in a or "CONTRIBUTION" in a:
            return "deposit"
        if "WITHDRAWAL" in a:
            return "withdrawal"
        return "other"

    hist_df["TxType"] = hist_df["Action"].fillna("").apply(action_type)

    # ── Build month list from history date range ──────────────────────────────
    file_start = hist_df["Run Date"].min()
    file_end   = hist_df["Run Date"].max()
    months = []
    y, m = file_start.year, file_start.month
    while True:
        months.append(datetime(y, m, 1))
        if y == file_end.year and m == file_end.month:
            break
        m += 1
        if m > 12:
            m = 1; y += 1

    # ── Monthly aggregation ───────────────────────────────────────────────────
    monthly_divs    = hist_df[hist_df["TxType"] == "dividend"].groupby("YearMonth")["Amount ($)"].sum()
    monthly_lt      = hist_df[hist_df["TxType"] == "lt_gain"].groupby("YearMonth")["Amount ($)"].sum()
    monthly_st      = hist_df[hist_df["TxType"] == "st_gain"].groupby("YearMonth")["Amount ($)"].sum()
    monthly_deps    = hist_df[hist_df["TxType"] == "deposit"].groupby("YearMonth")["Amount ($)"].sum()
    monthly_withs   = hist_df[hist_df["TxType"] == "withdrawal"].groupby("YearMonth")["Amount ($)"].sum()

    # NAV proxy: use Cash Balance at last transaction of each month
    month_end_cash = hist_df.sort_values("Run Date").groupby("YearMonth")["Cash Balance ($)"].last()

    # ── Ending holdings from statement CSV ───────────────────────────────────
    holdings_rows = []
    holdings_start = next(
        (i for i, l in enumerate(stmt_lines) if l.startswith("Symbol/CUSIP")), None
    )
    if holdings_start is not None:
        for line in stmt_lines[holdings_start + 2:]:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue
            sym, desc, qty, price, beg_val, end_val = parts[:6]
            if not sym or sym.startswith("Subtotal") or not qty:
                continue
            try:
                end_v = float(end_val.replace(",", ""))
                beg_v = float(beg_val.replace(",", "")) if beg_val not in ("", "unavailable") else end_v
                holdings_rows.append({
                    "account_number": acct_id,
                    "symbol": sym,
                    "description": desc,
                    "quantity": float(qty.replace(",", "")),
                    "market_value": end_v,
                    "unrealized_pnl": end_v - beg_v,
                })
            except Exception:
                continue
    holdings_df = pd.DataFrame(holdings_rows) if holdings_rows else pd.DataFrame()

    # ── Build monthly statement dicts ─────────────────────────────────────────
    results = []
    prev_nav = starting_value
    for month_dt in months:
        period = pd.Period(month_dt, freq="M")
        _, last_day = monthrange(month_dt.year, month_dt.month)

        divs  = float(monthly_divs.get(period, 0.0))
        lt    = float(monthly_lt.get(period, 0.0))
        st    = float(monthly_st.get(period, 0.0))
        deps  = float(monthly_deps.get(period, 0.0))
        withs = abs(float(monthly_withs.get(period, 0.0)))
        realized = st + lt

        # ending NAV: we don't have daily NAV so derive from cash balance change
        # best proxy = prev_nav + deps - withs + dividends + realized + unrealized
        # but we can't split unrealized without NAV. Use statement end value for last month,
        # and roll forward using net cash flows otherwise
        is_last = (period.year == file_end.year and period.month == file_end.month)
        if is_last and ending_value_stmt:
            # anchor December to statement ending value
            ending = ending_value_stmt
        else:
            ending = prev_nav + deps - withs + divs + realized  # approximate (no intra-month NAV)

        change = ending - prev_nav
        unrealized = change - (deps - withs) - divs - realized

        results.append({
            "broker": "Fidelity BrokerageLink",
            "account_number": acct_id,
            "filename": history_file.name,
            "period": month_dt.strftime("%B %Y"),
            "start_date": month_dt,
            "end_date": datetime(month_dt.year, month_dt.month, last_day),
            "starting_value": prev_nav,
            "ending_value": ending,
            "deposits": deps,
            "withdrawals": withs,
            "security_transfers": 0.0,
            "change_in_value": change,
            "realised_gains": realized,
            "realised_st": st,
            "realised_lt": lt,
            "unrealised_gains": unrealized,
            "dividend_income": divs,
            "interest_income": 0.0,
            "holdings": [],
            "needs_clipping": False,
            "original_end_date": None,
        })
        prev_nav = ending

    return results, holdings_df


def parse_fidelity(pdf_file) -> Tuple[List[Dict], pd.DataFrame]:
    """Parse a Fidelity monthly PDF investment report.
    Returns (list_with_one_statement_dict, holdings_df).
    """
    text = extract_text_from_pdf(pdf_file)
    filename = pdf_file.name

    # ── Broker type ───────────────────────────────────────────────────────────
    if "BrokerageLink" in text or "(866) 956-3193" in text:
        broker = "Fidelity BrokerageLink"
    elif "Health Savings" in text or "HEALTH SAVINGS ACCOUNT" in text.upper():
        broker = "Fidelity HSA"
    elif "ROTH IRA" in text.upper():
        broker = "Fidelity Roth IRA"
    elif "TRADITIONAL IRA" in text.upper():
        broker = "Fidelity Traditional IRA"
    else:
        broker = "Fidelity"

    # ── Account number ────────────────────────────────────────────────────────
    acct_m = re.search(r"Account[:\s#]+(\d{3}-\d{6})", text)
    account_number = acct_m.group(1) if acct_m else None

    # ── Period dates — "December 1, 2025 - December 31, 2025" ─────────────────
    date_m = re.search(
        r"([A-Za-z]+)\s+(\d+),\s+(\d{4})\s+-\s+([A-Za-z]+)\s+(\d+),\s+(\d{4})", text
    )
    start_date = end_date = period = None
    if date_m:
        try:
            start_date = datetime(
                int(date_m.group(3)),
                datetime.strptime(date_m.group(1), "%B").month,
                int(date_m.group(2)),
            )
            end_date = datetime(
                int(date_m.group(6)),
                datetime.strptime(date_m.group(4), "%B").month,
                int(date_m.group(5)),
            )
            period = start_date.strftime("%B %Y")
        except Exception:
            pass

    # ── Helper: first numeric match ───────────────────────────────────────────
    def _first(pattern: str) -> float:
        m = re.search(pattern, text)
        return float(m.group(1).replace(",", "")) if m else 0.0

    # ── Summary values (first = "This Period" column) ─────────────────────────
    beginning     = _first(r"Beginning Account Value\s+\$?([\d,]+\.\d+)")
    ending        = _first(r"Ending Account Value\s+[*\s]*\$?([\d,]+\.\d+)")
    additions     = _first(r"Additions\s+([\d,]+\.\d+)")
    subtractions  = _first(r"Subtractions\s+([\d,]+\.\d+)")
    change_in_val = _first(r"Change in Investment Value\s+[*\s]*([\d,]+\.\d+)")

    # ── Activity income — sum individual transaction lines ────────────────────
    def _sum_activity(keyword: str) -> float:
        total = 0.0
        for m in re.finditer(re.escape(keyword) + r"\s+[-\s]*([\d,]+\.\d+)", text):
            total += float(m.group(1).replace(",", ""))
        return total

    lt_gains  = _sum_activity("Long-Term Cap Gain")
    st_gains  = _sum_activity("Short-Term Cap Gain")

    # Fallback for HSA / accounts using "Realized Gains and Losses from Sales" summary
    # (page 3 of HSA statements — "Net Short-term Gain/Loss 207.47  1,528.94")
    # A bare dash means zero this period.
    if st_gains == 0.0 and lt_gains == 0.0:
        rgl_match = re.search(
            r"Realized Gains and Losses from Sales.*?Net Gain/Loss",
            text, re.DOTALL,
        )
        if rgl_match:
            rgl = rgl_match.group(0)

            def _rgl_first(label: str) -> float:
                m = re.search(label + r"\s+([\d,]+\.\d+|-)", rgl)
                if m:
                    v = m.group(1)
                    return 0.0 if v == "-" else float(v.replace(",", ""))
                return 0.0

            st_gains = _rgl_first(r"Net Short-term Gain/Loss")
            lt_gains = _rgl_first(r"Net Long-term Gain/Loss")

    dividends = _sum_activity("Dividend Received")
    interest  = _sum_activity("Interest Received") + _sum_activity("Interest Credited")

    realized  = lt_gains + st_gains
    unrealized = change_in_val - dividends - interest - realized

    # ── Holdings — search full text for (TICKER) patterns ────────────────────
    # "Activity\b" falsely terminates at footnote text "Other Activity In or Out"
    # so search the full text and filter false positives instead.
    # Known non-ticker tokens that appear in parentheses in disclosures/footnotes:
    _SKIP_TICKERS = {"AI", "EY", "EAI", "NFS", "FBS", "NYSE", "SIPC", "IRS", "ETF"}

    holdings_rows = []
    seen = set()
    for m in re.finditer(r"\(([A-Z][A-Z0-9]{1,5})\)", text):
        ticker = m.group(1)
        if ticker in seen or ticker in _SKIP_TICKERS:
            continue
        seen.add(ticker)

        after = text[m.end(): m.end() + 400]
        has_na = "not applicable" in after[:200]
        nums = [float(x.replace(",", "")) for x in re.findall(r"-?[\d,]+\.\d+", after[:300])]

        if len(nums) < 4:
            continue
        # columns: beg_val, qty, price, end_val, [cost], [unrealized], [EAI]
        end_val  = nums[3]
        qty      = nums[1]
        if has_na:
            cost, unreal = end_val, 0.0
        elif len(nums) >= 6:
            cost, unreal = nums[4], nums[5]
        else:
            cost, unreal = 0.0, 0.0

        # Description: text ending just before '('
        before = text[max(0, m.start() - 150): m.start()]
        desc_lines = []
        for ln in reversed(before.split("\n")):
            ln = ln.strip()
            if ln and re.match(r"^[A-Z][A-Z0-9\'\s&\-\.\/,]+$", ln):
                desc_lines.insert(0, ln)
            else:
                break
        desc = " ".join(desc_lines).strip() or ticker

        holdings_rows.append({
            "account_number": account_number,
            "symbol": ticker,
            "description": desc,
            "quantity": qty,
            "market_value": end_val,
            "unrealized_pnl": unreal,
        })

    holdings_df = pd.DataFrame(holdings_rows) if holdings_rows else pd.DataFrame()

    stmt = {
        "broker": broker,
        "account_number": account_number,
        "filename": filename,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "starting_value": beginning,
        "ending_value": ending,
        "deposits": additions,
        "withdrawals": subtractions,
        "security_transfers": 0.0,
        "change_in_value": change_in_val,
        "realised_gains": realized,
        "realised_st": st_gains,
        "realised_lt": lt_gains,
        "unrealised_gains": unrealized,
        "dividend_income": dividends,
        "interest_income": interest,
        "holdings": [],
        "needs_clipping": False,
        "original_end_date": None,
    }
    return [stmt], holdings_df


def parse_ibkr(pdf_file) -> Dict:
    """Parse IBKR statement with January clipping"""
    text = extract_text_from_pdf(pdf_file)

    # Account number (IBKR format: U9840866)
    acct_match = re.search(r"\b(U\d{7})\b", text)
    account_number = acct_match.group(1) if acct_match else None

    data = {
        "broker": "Interactive Brokers",
        "account_number": account_number,
        "filename": pdf_file.name,
        "period": None,
        "start_date": None,
        "end_date": None,
        "starting_value": 0.0,
        "ending_value": 0.0,
        "deposits": 0.0,
        "withdrawals": 0.0,
        "security_transfers": 0.0,
        "change_in_value": 0.0,
        "realised_gains": 0.0,
        "unrealised_gains": 0.0,
        "dividend_income": 0.0,
        "interest_income": 0.0,
        "holdings": [],
        "needs_clipping": False,
        "original_end_date": None,
    }

    # Detect period
    if "January 1, 2026 - February" in text:
        data["needs_clipping"] = True
        data["start_date"] = datetime(2026, 1, 1)
        data["end_date"] = datetime(2026, 1, 31)  # Will clip to this

        # Extract actual end date from statement
        feb_date = re.search(r"February (\d+), 2026", text)
        if feb_date:
            data["original_end_date"] = datetime(2026, 2, int(feb_date.group(1)))
            data["period"] = (
                f"January 1 - February {feb_date.group(1)}, 2026 (clipped to Jan 31)"
            )
    else:
        # Month-end statement
        data["start_date"] = datetime(2026, 1, 1)
        data["end_date"] = datetime(2026, 1, 31)
        data["period"] = "January 1-31, 2026"

    # Extract NAV Summary
    nav_section = re.search(r"NAV Summary(.*?)Profit and Loss", text, re.DOTALL)
    if nav_section:
        nav_text = nav_section.group(1)

        # Get total line
        total_match = re.search(r"Total\s+([0-9,]+\.\d+)\s+([0-9,]+\.\d+)", nav_text)
        if total_match:
            data["starting_value"] = float(total_match.group(1).replace(",", ""))
            feb_end_value = float(total_match.group(2).replace(",", ""))

            if data["needs_clipping"]:
                # Calculate January-only value using time-weighting
                # Extract TWR
                twr_matches = re.findall(r"(-?\d+\.\d+)%", nav_text)
                if twr_matches:
                    # Get rates, excluding zeros
                    rates = [float(r) for r in twr_matches if float(r) != 0]
                    if rates:
                        avg_twr = np.mean(rates)

                        # Calculate January factor
                        total_days = (
                            data["original_end_date"] - data["start_date"]
                        ).days
                        january_days = 31
                        january_factor = january_days / total_days

                        # Apply to TWR
                        january_twr = avg_twr * january_factor

                        # Calculate January ending value
                        data["ending_value"] = data["starting_value"] * (
                            1 + january_twr / 100
                        )
                    else:
                        # Fallback: linear interpolation
                        data["ending_value"] = feb_end_value * 0.705  # 31/44 days
                else:
                    data["ending_value"] = feb_end_value * 0.705
            else:
                data["ending_value"] = feb_end_value

    # Extract cash flows from Cash and Position Activity section
    cash_section = re.search(
        r"Cash and Position Activity(.*?)(?:$|Envelope)", text, re.DOTALL
    )
    if cash_section:
        cash_text = cash_section.group(1)

        # Look for the activity table with Deposits/Withdrawals
        # Pattern: Deposits followed by amount on same or next line
        deposit_match = re.search(r"Deposits\s+([0-9,]+\.\d+)", cash_text)
        if deposit_match:
            deposits = float(deposit_match.group(1).replace(",", ""))
            if data["needs_clipping"]:
                # Don't clip cash flows - use actual amounts
                # Cash flows are discrete events, not time-based
                data["deposits"] = deposits
            else:
                data["deposits"] = deposits

        # Withdrawals
        withdrawal_match = re.search(r"Withdrawals\s+([0-9,]+\.\d+)", cash_text)
        if withdrawal_match:
            withdrawals = float(withdrawal_match.group(1).replace(",", ""))
            if data["needs_clipping"]:
                data["withdrawals"] = withdrawals
            else:
                data["withdrawals"] = withdrawals

        # Also check for Dividends and Interest in the same section
        div_match = re.search(r"Dividends\s+([0-9,]+\.\d+)", cash_text)
        if div_match:
            dividends = float(div_match.group(1).replace(",", ""))
            # Dividends are income, not deposits, but track them
            data["dividend_income"] = dividends

        interest_match = re.search(r"Interest\s+([0-9,]+\.\d+)", cash_text)
        if interest_match:
            interest = float(interest_match.group(1).replace(",", ""))
            data["interest_income"] = interest

    # Extract P&L
    pnl_section = re.search(
        r"Profit and Loss Summary(.*?)Open Positions", text, re.DOTALL
    )
    if pnl_section:
        pnl_text = pnl_section.group(1)
        lines = pnl_text.split("\n")

        for line in lines:
            if "Total" in line and "USD" not in line:
                numbers = re.findall(r"([0-9,]+\.\d+)", line)
                if len(numbers) >= 2:
                    mtm = float(numbers[0].replace(",", ""))
                    realized = float(numbers[1].replace(",", ""))

                    if data["needs_clipping"]:
                        data["unrealised_gains"] = mtm * 0.705
                        data["realised_gains"] = realized * 0.705
                    else:
                        data["unrealised_gains"] = mtm
                        data["realised_gains"] = realized
                    data["change_in_value"] = (
                        data["unrealised_gains"] + data["realised_gains"]
                    )
                    break

    return data


def parse_ibkr_csv(csv_file) -> Tuple[List[Dict], pd.DataFrame]:
    """
    Parse IBKR Flex Query Portfolio Analysis Monthly CSV.

    Returns:
        - list of monthly statement dicts (one per account per month)
        - ending_holdings DataFrame (year-end open positions from FIFO section)
    """
    import csv as csv_module
    from calendar import monthrange

    content = csv_file.read()
    if isinstance(content, bytes):
        content = content.decode("utf-8")

    lines = list(csv_module.reader(io.StringIO(content)))

    # BOF row: ["BOF", master_account, report_name, ..., start_date, end_date, ...]
    bof_row = lines[0]
    file_start_date = datetime.strptime(bof_row[4], "%Y%m%d")
    file_end_date = datetime.strptime(bof_row[5], "%Y%m%d")
    filename = csv_file.name

    # Build ordered list of all months in file period
    months = []
    y, m = file_start_date.year, file_start_date.month
    while True:
        months.append(datetime(y, m, 1))
        if y == file_end_date.year and m == file_end_date.month:
            break
        m += 1
        if m > 12:
            m = 1
            y += 1

    # --- Parse account sections (BOA…EOA) ---
    PARSED_SECTIONS = ("equt", "stfu", "trnt", "trfr", "fifo", "cnav")
    account_data = {}
    current_account = None
    current_section = None
    current_headers = None

    for row in lines:
        if not row:
            continue
        marker = row[0]

        if marker == "BOA":
            current_account = row[1]
            account_data[current_account] = {s: [] for s in PARSED_SECTIONS}
            current_section = None
            current_headers = None

        elif marker == "EOA":
            current_account = None
            current_section = None
            current_headers = None

        elif marker == "BOS":
            section = row[1].lower()
            if section in PARSED_SECTIONS:
                current_section = section
                current_headers = None
            else:
                current_section = None

        elif marker == "EOS":
            current_section = None
            current_headers = None

        elif marker in ("BOF", "EOF"):
            continue

        elif current_account and current_section:
            if current_headers is None:
                current_headers = row
            elif len(row) == len(current_headers):
                account_data[current_account][current_section].append(
                    dict(zip(current_headers, row))
                )

    # --- Build monthly statements and ending_holdings per account ---
    all_monthly_statements = []
    ending_holdings_rows = []

    for account_id, sections in account_data.items():
        equt_rows = sections["equt"]
        stfu_rows = sections["stfu"]
        trnt_rows = sections["trnt"]
        trfr_rows = sections["trfr"]
        fifo_rows = sections["fifo"]
        cnav_rows = sections["cnav"]

        # ── EQUT: daily NAV → month-end values ──────────────────────────────
        month_end_nav = {}
        initial_nav = 0.0
        if equt_rows:
            equt_df = pd.DataFrame(equt_rows)
            equt_df["ReportDate"] = pd.to_datetime(
                equt_df["ReportDate"], format="%Y%m%d", errors="coerce"
            )
            equt_df["Total"] = pd.to_numeric(equt_df["Total"], errors="coerce").fillna(0.0)
            equt_df["YearMonth"] = equt_df["ReportDate"].dt.to_period("M")
            month_end_nav = equt_df.groupby("YearMonth")["Total"].last().to_dict()
            prev_year_dec = pd.Period(year=file_start_date.year - 1, month=12, freq="M")
            initial_nav = month_end_nav.get(prev_year_dec, 0.0)

        use_equt = len(month_end_nav) > 1  # daily file: many months; sparse file: ≤1

        # ── STFU: monthly cash flows (DEP/WITH/DIV/CINT/DINT) ───────────────
        monthly_flows = {}
        if use_equt and stfu_rows:
            stfu_df = pd.DataFrame(stfu_rows)
            if {"Date", "ActivityCode", "Amount"}.issubset(stfu_df.columns):
                stfu_df["Date"] = pd.to_datetime(
                    stfu_df["Date"], format="%Y%m%d", errors="coerce"
                )
                stfu_df["Amount"] = pd.to_numeric(
                    stfu_df["Amount"], errors="coerce"
                ).fillna(0.0)
                stfu_df["YearMonth"] = stfu_df["Date"].dt.to_period("M")
                for period, grp in stfu_df.groupby("YearMonth"):
                    flows = {"deposits": 0.0, "withdrawals": 0.0,
                             "dividends": 0.0, "interest": 0.0}
                    for _, txn in grp.iterrows():
                        code = txn["ActivityCode"]
                        amt = float(txn["Amount"])
                        if code == "DEP":
                            flows["deposits"] += abs(amt)
                        elif code == "WITH":
                            flows["withdrawals"] += abs(amt)
                        elif code == "DIV":
                            flows["dividends"] += abs(amt)
                        elif code in ("CINT", "DINT"):
                            flows["interest"] += amt   # DINT is negative
                    monthly_flows[period] = flows

        # ── TRFR: ACATS security transfers in per month ───────────────────────
        # INTERNAL cash moves are already captured in STFU as DEP/WITH — skip them.
        # ACATS stock transfers use PositionAmount (CashTransfer is 0 for equities).
        monthly_transfers = {}
        if use_equt and trfr_rows:
            trfr_df = pd.DataFrame(trfr_rows)
            date_col = next((c for c in ("Date", "ReportDate") if c in trfr_df.columns), None)
            if date_col and "PositionAmount" in trfr_df.columns:
                trfr_df[date_col] = pd.to_datetime(
                    trfr_df[date_col], format="%Y%m%d", errors="coerce"
                )
                trfr_df["PositionAmount"] = pd.to_numeric(
                    trfr_df["PositionAmount"], errors="coerce"
                ).fillna(0.0)
                trfr_df["YearMonth"] = trfr_df[date_col].dt.to_period("M")
                # Only ACATS security (non-cash) rows
                if "Type" in trfr_df.columns and "AssetClass" in trfr_df.columns:
                    acats = trfr_df[
                        (trfr_df["Type"] == "ACATS") & (trfr_df["AssetClass"] != "CASH")
                    ]
                else:
                    acats = trfr_df[trfr_df["PositionAmount"] != 0]
                monthly_transfers = acats.groupby("YearMonth")["PositionAmount"].sum().to_dict()

        # ── FIFO: per-symbol realised ST/LT profile (used by TRNT below) ────────
        # FIFO has cumulative RealizedShortTermProfit/Loss and LongTermProfit/Loss
        # per open symbol. Use these to classify closed trades as ST or LT.
        symbol_lt_fraction: dict = {}
        for _pos in fifo_rows:
            _sym = _pos.get("Symbol", "")
            if not _sym:
                continue
            _rst = (float(_pos.get("RealizedShortTermProfit", 0) or 0)
                    + float(_pos.get("RealizedShortTermLoss", 0) or 0))
            _rlt = (float(_pos.get("RealizedLongTermProfit", 0) or 0)
                    + float(_pos.get("RealizedLongTermLoss", 0) or 0))
            _total = abs(_rst) + abs(_rlt)
            symbol_lt_fraction[_sym] = abs(_rlt) / _total if _total > 0.01 else None

        # ── TRNT: monthly realised gains (closed trades) ──────────────────────
        monthly_realised = {}
        monthly_realised_st = {}
        monthly_realised_lt = {}
        if trnt_rows:
            trnt_df = pd.DataFrame(trnt_rows)
            req = {"TradeDate", "FifoPnlRealized", "Open/CloseIndicator"}
            if req.issubset(trnt_df.columns):
                trnt_df["TradeDate"] = pd.to_datetime(
                    trnt_df["TradeDate"], format="%Y%m%d", errors="coerce"
                )
                trnt_df["FifoPnlRealized"] = pd.to_numeric(
                    trnt_df["FifoPnlRealized"], errors="coerce"
                ).fillna(0.0)
                closed = trnt_df[trnt_df["Open/CloseIndicator"] == "C"].copy()
                closed["YearMonth"] = closed["TradeDate"].dt.to_period("M")

                # Determine long-term per trade:
                # 1. If the symbol is still in FIFO, use its LT fraction (accurate)
                # 2. If OpenDateTime is populated and parseable, use holding period
                # 3. Fallback: Notes/Codes — ML or MLL indicates a long-term lot
                def _is_lt(row):
                    sym = row.get("Symbol", "") if isinstance(row, dict) else row["Symbol"]
                    lt_frac = symbol_lt_fraction.get(sym)
                    if lt_frac is not None:
                        return lt_frac >= 0.5
                    # Try OpenDateTime if not blank
                    open_dt_str = (row.get("OpenDateTime", "") if isinstance(row, dict)
                                   else row["OpenDateTime"])
                    if open_dt_str:
                        open_dt = pd.to_datetime(open_dt_str, errors="coerce")
                        close_dt = (row.get("TradeDate") if isinstance(row, dict)
                                    else row["TradeDate"])
                        if pd.notna(open_dt) and pd.notna(close_dt):
                            return (close_dt - open_dt).days >= 365
                    # Fallback: ML or MLL in Notes/Codes
                    codes = str(row.get("Notes/Codes", "") if isinstance(row, dict)
                                else row["Notes/Codes"])
                    return any(c in ("ML", "MLL") for c in codes.split(";"))

                closed["IsLT"] = closed.apply(_is_lt, axis=1)
                monthly_realised = (
                    closed.groupby("YearMonth")["FifoPnlRealized"].sum().to_dict()
                )
                monthly_realised_lt = (
                    closed[closed["IsLT"]].groupby("YearMonth")["FifoPnlRealized"].sum().to_dict()
                )
                monthly_realised_st = (
                    closed[~closed["IsLT"]].groupby("YearMonth")["FifoPnlRealized"].sum().to_dict()
                )

        # ── CNAV fallback: aggregate to monthly when EQUT is sparse ──────────
        cnav_by_period = {}
        if not use_equt and cnav_rows:
            cnav_df = pd.DataFrame(cnav_rows)
            for col in ("StartingValue", "EndingValue", "DepositsWithdrawals",
                        "Dividends", "Interest", "Realized", "Mtm"):
                cnav_df[col] = pd.to_numeric(cnav_df[col], errors="coerce").fillna(0.0)
            cnav_df["_ToDate"] = pd.to_datetime(
                cnav_df["ToDate"], format="%Y%m%d", errors="coerce"
            )
            cnav_df["_FromDate"] = pd.to_datetime(
                cnav_df["FromDate"], format="%Y%m%d", errors="coerce"
            )
            cnav_df["YearMonth"] = cnav_df["_ToDate"].dt.to_period("M")
            for period, grp in cnav_df.groupby("YearMonth"):
                grp_s = grp.sort_values("_FromDate")
                cnav_by_period[period] = {
                    "StartingValue": grp_s.iloc[0]["StartingValue"],
                    "EndingValue":   grp_s.iloc[-1]["EndingValue"],
                    "DepositsWithdrawals": grp["DepositsWithdrawals"].sum(),
                    "Dividends":   grp["Dividends"].sum(),
                    "Interest":    grp["Interest"].sum(),
                    "Realized":    grp["Realized"].sum(),
                    "Mtm":         grp["Mtm"].sum(),
                }

        # ── FIFO: open positions → ending_holdings ───────────────────────────
        for pos in fifo_rows:
            symbol = pos.get("Symbol", "")
            if not symbol:
                continue
            unrealized = float(pos.get("TotalUnrealizedPnl", 0) or 0)
            if unrealized != 0.0:
                ending_holdings_rows.append(
                    {
                        "account_number": account_id,
                        "symbol": symbol,
                        "description": pos.get("Description", ""),
                        "unrealized_pnl": unrealized,
                        "realized_pnl": float(pos.get("TotalRealizedPnl", 0) or 0),
                        "total_pnl": float(pos.get("TotalFifoPnl", 0) or 0),
                    }
                )

        # ── Build one dict per month ──────────────────────────────────────────
        prev_nav = initial_nav
        for month_dt in months:
            period = pd.Period(month_dt, freq="M")
            _, last_day = monthrange(month_dt.year, month_dt.month)

            if use_equt:
                month_nav = month_end_nav.get(period, 0.0)
                flows = monthly_flows.get(
                    period,
                    {"deposits": 0.0, "withdrawals": 0.0, "dividends": 0.0, "interest": 0.0},
                )
                realized = monthly_realised.get(period, 0.0)
                realized_st = monthly_realised_st.get(period, 0.0)
                realized_lt = monthly_realised_lt.get(period, 0.0)
                transfers = monthly_transfers.get(period, 0.0)
                change = month_nav - prev_nav
                net_deposits = flows["deposits"] - flows["withdrawals"]
                # investment_pnl strips out cash flows and security transfers from NAV change
                investment_pnl = change - net_deposits - transfers
                unrealized = (
                    investment_pnl
                    - flows["dividends"]
                    - flows["interest"]
                    - realized
                )
                starting, ending = prev_nav, month_nav
                deposits, withdrawals = flows["deposits"], flows["withdrawals"]
                dividends, interest = flows["dividends"], flows["interest"]
            else:
                cnav = cnav_by_period.get(period)
                if cnav:
                    starting = float(cnav["StartingValue"])
                    ending   = float(cnav["EndingValue"])
                    dw       = float(cnav["DepositsWithdrawals"])
                    deposits = dw if dw > 0 else 0.0
                    withdrawals = abs(dw) if dw < 0 else 0.0
                    dividends = float(cnav["Dividends"])
                    interest  = float(cnav["Interest"])
                    realized  = monthly_realised.get(period, float(cnav["Realized"]))
                    realized_st = monthly_realised_st.get(period, 0.0)
                    realized_lt = monthly_realised_lt.get(period, 0.0)
                    unrealized = float(cnav["Mtm"])
                    change = ending - starting
                    transfers = 0.0
                    investment_pnl = change - dw  # strip net deposits from raw NAV change
                else:
                    starting = ending = deposits = withdrawals = dividends = \
                        interest = realized = realized_st = realized_lt = \
                        unrealized = change = transfers = investment_pnl = 0.0

            all_monthly_statements.append(
                {
                    "broker": "Interactive Brokers",
                    "account_number": account_id,
                    "filename": filename,
                    "period": month_dt.strftime("%B %Y"),
                    "start_date": month_dt,
                    "end_date": datetime(month_dt.year, month_dt.month, last_day),
                    "starting_value": starting,
                    "ending_value": ending,
                    "deposits": deposits,
                    "withdrawals": withdrawals,
                    "security_transfers": transfers,
                    "change_in_value": investment_pnl,
                    "realised_gains": realized,
                    "realised_st": realized_st,
                    "realised_lt": realized_lt,
                    "unrealised_gains": unrealized,
                    "dividend_income": dividends,
                    "interest_income": interest,
                    "holdings": [],
                    "needs_clipping": False,
                    "original_end_date": None,
                }
            )
            if use_equt:
                prev_nav = month_nav

    ending_holdings_df = (
        pd.DataFrame(ending_holdings_rows) if ending_holdings_rows else pd.DataFrame()
    )
    return all_monthly_statements, ending_holdings_df


def detect_common_period(statements: List[Dict]) -> Tuple[datetime, datetime]:
    """
    Detect the common period across all statements
    Returns the overlapping date range
    """
    if not statements:
        return None, None

    # Find latest start date and earliest end date
    start_dates = [s["start_date"] for s in statements if s["start_date"]]
    end_dates = [s["end_date"] for s in statements if s["end_date"]]

    if not start_dates or not end_dates:
        return None, None

    common_start = max(start_dates)
    common_end = min(end_dates)

    return common_start, common_end


def parse_all_statements(
    etrade_files, fidelity_files, ibkr_files
) -> Tuple[List[Dict], datetime, datetime, bool, pd.DataFrame]:
    """
    Parse all uploaded statements and detect common period

    Returns:
        - List of parsed statements
        - Common start date
        - Common end date
        - Whether any clipping was needed
        - ending_holdings DataFrame (from IBKR CSV, empty otherwise)
    """
    all_statements = []
    ending_holdings_df = pd.DataFrame()

    # Parse E*TRADE — keep only most recent holdings per account
    if etrade_files:
        _latest_et: dict = {}  # account_number → (end_date, holdings_df)
        for file in etrade_files:
            try:
                monthly, holdings_df = parse_etrade(file)
                all_statements.extend(monthly)
                if not holdings_df.empty:
                    for stmt in monthly:
                        acct = stmt.get("account_number")
                        ed = stmt.get("end_date") or datetime.min
                        if acct:
                            prev = _latest_et.get(acct)
                            if prev is None or ed >= prev[0]:
                                _latest_et[acct] = (ed, holdings_df)
            except Exception as e:
                print(f"Error parsing {file.name}: {e}")
        for _, hdf in _latest_et.values():
            ending_holdings_df = pd.concat(
                [ending_holdings_df, hdf], ignore_index=True
            )

    # Parse Fidelity PDFs — keep only most recent holdings per account
    if fidelity_files:
        _latest_fid: dict = {}  # account_number → (end_date, holdings_df)
        for file in fidelity_files:
            try:
                monthly, holdings_df = parse_fidelity(file)
                all_statements.extend(monthly)
                if not holdings_df.empty:
                    for stmt in monthly:
                        acct = stmt.get("account_number")
                        ed = stmt.get("end_date") or datetime.min
                        if acct:
                            prev = _latest_fid.get(acct)
                            if prev is None or ed >= prev[0]:
                                _latest_fid[acct] = (ed, holdings_df)
            except Exception as e:
                print(f"Error parsing {file.name}: {e}")
        for _, hdf in _latest_fid.values():
            ending_holdings_df = pd.concat(
                [ending_holdings_df, hdf], ignore_index=True
            )

    # Parse IBKR (PDF or CSV)
    if ibkr_files:
        for file in ibkr_files:
            try:
                if file.name.lower().endswith(".csv"):
                    monthly_stmts, holdings_df = parse_ibkr_csv(file)
                    all_statements.extend(monthly_stmts)
                    if not holdings_df.empty:
                        ending_holdings_df = pd.concat(
                            [ending_holdings_df, holdings_df], ignore_index=True
                        )
                else:
                    data = parse_ibkr(file)
                    all_statements.append(data)
            except Exception as e:
                print(f"Error parsing {file.name}: {e}")

    # Detect common period
    common_start, common_end = detect_common_period(all_statements)

    # Check if any clipping was applied
    clipping_needed = any(s.get("needs_clipping", False) for s in all_statements)

    return all_statements, common_start, common_end, clipping_needed, ending_holdings_df
