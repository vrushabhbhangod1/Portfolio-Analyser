"""
Portfolio Analyzer - Complete Step 3
Multi-period analysis with benchmarks and risk metrics
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io

# Import all modules
from src.broker_parsers import parse_all_statements
from src.portfolio_calculator import (
    calculate_metrics,
    build_timeline_dataframe,
    build_summary_export_dataframe,
    prepare_export_data,
)
from src.period_detector import detect_date_ranges
from src.risk_analysis import calculate_all_risk_metrics
from src.benchmark_comparison import compare_to_benchmarks, create_comparison_dataframe
from src.chart_builder import (
    create_consolidated_charts,
    create_individual_charts,
    create_comparison_chart,
    create_timeline_chart,
    create_benchmark_comparison_chart,
    create_monthly_returns_chart,
    create_drawdown_chart,
    create_risk_return_scatter,
)

# Page configuration
st.set_page_config(
    page_title="Portfolio Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
    <style>
    .main {padding: 0rem 1rem;}
    h1 {color: #1f77b4; padding-bottom: 1rem;}
    h2 {color: #2c3e50; padding-top: 1rem;}
    .stAlert {margin-top: 1rem;}
    .metric-row {display: flex; gap: 1rem;}
    </style>
""",
    unsafe_allow_html=True,
)


def export_to_csv(export_data: dict):
    """Create CSV export"""
    output = io.StringIO()
    for sheet_name, df in export_data.items():
        output.write(f"\n{sheet_name}\n")
        df.to_csv(output, index=False)
        output.write("\n")
    return output.getvalue()


def export_to_excel(export_data: dict):
    """Create Excel export"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in export_data.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


def main():
    """Main application"""

    # Header
    st.title("📊 Portfolio Analyzer")
    st.markdown("**Multi-period analysis with benchmarks and risk metrics**")
    st.markdown("---")

    # Sidebar
    with st.sidebar:
        st.header("📁 Upload Statements")

        # E*TRADE
        st.subheader("🔵 E*TRADE")
        etrade_files = st.file_uploader(
            "Upload E*TRADE statements",
            type=["pdf"],
            accept_multiple_files=True,
            key="etrade",
            help="Upload monthly or yearly statements",
        )
        if etrade_files:
            st.success(f"✓ {len(etrade_files)} file(s)")

        st.markdown("---")

        # Fidelity
        st.subheader("🟢 Fidelity")
        fidelity_files = st.file_uploader(
            "Upload Fidelity statements",
            type=["pdf"],
            accept_multiple_files=True,
            key="fidelity",
            help="HSA, 401k, or brokerage statements",
        )
        if fidelity_files:
            st.success(f"✓ {len(fidelity_files)} file(s)")

        st.markdown("---")

        # IBKR
        st.subheader("🔴 Interactive Brokers")
        ibkr_files = st.file_uploader(
            "Upload IBKR statements",
            type=["pdf", "csv"],
            accept_multiple_files=True,
            key="ibkr",
            help="Monthly PDF or activity CSV statements",
        )
        if ibkr_files:
            st.success(f"✓ {len(ibkr_files)} file(s)")

        st.markdown("---")

        # Settings
        st.subheader("⚙️ Settings")
        risk_free_rate = st.number_input(
            "Risk-Free Rate (%)",
            min_value=0.0,
            max_value=10.0,
            value=4.5,
            step=0.1,
            help="Annual risk-free rate for Sharpe/Sortino calculations (default: 4.5%)",
        )

        st.markdown("---")

        # Analyze button
        analyze_button = st.button(
            "🚀 Analyze Portfolio", type="primary", use_container_width=True
        )

    # Persist "analyzed" state so widget interactions (selectbox, tabs, etc.)
    # don't reset the page back to the "upload files" screen.
    if analyze_button:
        st.session_state["analyzed"] = True

    # Main content
    if not (etrade_files or fidelity_files or ibkr_files):
        # Clear state when files are removed
        st.session_state.pop("analyzed", None)
        show_welcome_screen()

    elif st.session_state.get("analyzed", False):
        # Re-run analysis on every rerun so widget interactions work correctly
        run_analysis(etrade_files, fidelity_files, ibkr_files, risk_free_rate)

    else:
        # Files uploaded, waiting for analysis
        st.info("👆 Click **'Analyze Portfolio'** in the sidebar to start")
        show_uploaded_files(etrade_files, fidelity_files, ibkr_files)


def show_welcome_screen():
    """Display welcome screen with instructions"""
    st.info("👈 **Get Started:** Upload your brokerage statements using the sidebar")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 📈 Features")
        st.markdown(
            """
        - Multi-period analysis
        - Automatic date alignment
        - Risk metrics (Sharpe, Sortino, Max DD)
        - Benchmark comparison (S&P 500, NASDAQ)
        - Interactive Plotly charts
        - Export to CSV/Excel
        """
        )

    with col2:
        st.markdown("### 🏦 Supported Brokers")
        st.markdown(
            """
        - **E*TRADE** - All account types
        - **Fidelity** - HSA, 401k, Brokerage
        - **IBKR** - All account types
        - Auto-detects account types
        """
        )

    with col3:
        st.markdown("### 📊 Metrics")
        st.markdown(
            """
        - TWR & MWR Returns
        - Sharpe & Sortino Ratios
        - Maximum Drawdown
        - Win Rate & Volatility
        - Alpha & Beta vs benchmarks
        - Correlation analysis
        """
        )


def show_uploaded_files(etrade_files, fidelity_files, ibkr_files):
    """Show list of uploaded files"""
    st.markdown("### Files Ready for Analysis:")

    col1, col2, col3 = st.columns(3)

    with col1:
        if etrade_files:
            st.markdown("**🔵 E*TRADE**")
            for f in etrade_files:
                st.caption(f"• {f.name}")

    with col2:
        if fidelity_files:
            st.markdown("**🟢 Fidelity**")
            for f in fidelity_files:
                st.caption(f"• {f.name}")

    with col3:
        if ibkr_files:
            st.markdown("**🔴 IBKR**")
            for f in ibkr_files:
                st.caption(f"• {f.name}")


def run_analysis(etrade_files, fidelity_files, ibkr_files, risk_free_rate):
    """Run complete portfolio analysis"""

    st.markdown("## 🔍 Analysis Results")

    # Parse statements
    with st.spinner("📄 Parsing statements..."):
        statements, common_start, common_end, clipping_needed, ending_holdings_df = parse_all_statements(
            etrade_files, fidelity_files, ibkr_files
        )

    if not statements:
        st.error("❌ Could not parse any statements. Please check your files.")
        return

    # Detect date ranges
    with st.spinner("📅 Detecting date ranges..."):
        date_info = detect_date_ranges(statements)

    # Check if we have valid dates
    if not date_info or not date_info["min_date"]:
        st.error(
            "❌ Could not detect date ranges from statements. Please check your PDFs."
        )
        st.warning("⚠️ Debug info: No start/end dates found in the parsed statements")

        # Show what was parsed
        with st.expander("🔍 Debug: Parsed Statement Info"):
            for stmt in statements:
                st.write(
                    f"**{stmt['broker']}**: Start: {stmt.get('start_date')}, End: {stmt.get('end_date')}"
                )
        return

    # Show date range summary
    show_date_summary(date_info, clipping_needed)

    # Calculate metrics
    with st.spinner("🧮 Calculating metrics..."):
        # Build timeline and summary DataFrames
        timeline_df = build_timeline_dataframe(statements)
        summary_df = build_summary_export_dataframe(statements, risk_free_rate)

        # Calculate consolidated metrics
        metrics = calculate_metrics(statements, risk_free_rate)

        # Create simple DataFrames for UI display (backward compatibility)
        df_brokers = summary_df if not summary_df.empty else pd.DataFrame()
        df_portfolio = (
            pd.DataFrame(
                [
                    {
                        "Metric": "Total Value",
                        "Value": f"${metrics.get('total_ending_value', 0):,.2f}",
                    }
                ]
            )
            if metrics
            else pd.DataFrame()
        )

    # Fetch benchmarks
    benchmark_comparison = None
    comparison_df = None

    if not timeline_df.empty and len(timeline_df) >= 2:
        with st.spinner("📈 Fetching benchmark data..."):
            try:
                # Filter to Total Portfolio only for benchmark comparison
                total_portfolio_df = timeline_df[
                    timeline_df["broker"] == "Total Portfolio"
                ].copy()

                # Suppress yfinance warnings
                import warnings

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    benchmark_comparison = compare_to_benchmarks(
                        total_portfolio_df,
                        date_info["min_date"],
                        date_info["max_date"],
                        risk_free_rate,
                    )

                if benchmark_comparison and "benchmarks" in benchmark_comparison:
                    comparison_df = create_comparison_dataframe(
                        total_portfolio_df, benchmark_comparison["benchmarks"]
                    )
            except Exception as e:
                # Silently fail - benchmarks are optional
                benchmark_comparison = None
                comparison_df = None

    # Create tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            "📊 Consolidated",
            "📈 Timeline",
            "🏦 Individual Brokers",
            "📦 Holdings",
            "🎯 Benchmarks",
            "💾 Export",
        ]
    )

    with tab1:
        show_consolidated_view(metrics, df_portfolio, df_brokers, timeline_df)

    with tab2:
        show_timeline_view(timeline_df, comparison_df, benchmark_comparison, metrics)

    with tab3:
        show_individual_view(
            statements, df_brokers, metrics, timeline_df, risk_free_rate
        )

    with tab4:
        show_holdings_view(ending_holdings_df)

    with tab5:
        show_benchmarks_view(benchmark_comparison, metrics, timeline_df)

    with tab6:
        show_export_view(metrics, summary_df, timeline_df)


def show_date_summary(date_info, clipping_needed):
    """Show date range summary"""

    # Show account ranges
    st.markdown("### 📅 Date Ranges by Account")

    broker_cols = st.columns(len(date_info["broker_ranges"]))
    for i, (broker, range_info) in enumerate(date_info["broker_ranges"].items()):
        with broker_cols[i]:
            st.markdown(f"**{broker}**")
            if range_info["start"] and range_info["end"]:
                st.caption(
                    f"{range_info['start'].strftime('%b %Y')} → {range_info['end'].strftime('%b %Y')}"
                )
                st.caption(f"({len(range_info['periods'])} month(s))")

    st.markdown("---")

    # Overall summary
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Earliest Date", date_info["min_date"].strftime("%b %Y"))

    with col2:
        st.metric("Latest Date", date_info["max_date"].strftime("%b %Y"))

    with col3:
        st.metric("Total Months Span", date_info["total_months"])

    with col4:
        if date_info["has_overlap"]:
            st.metric("Overlap Months", date_info["overlap_months"])
        else:
            st.metric("Overlap Months", "None", delta="⚠️")

    # Overlap explanation
    if date_info["has_overlap"]:
        st.success(
            f"✅ **Consolidated Analysis Period:** {date_info['overlap_start'].strftime('%b %Y')} - {date_info['overlap_end'].strftime('%b %Y')} (period where ALL brokers have data)"
        )
    else:
        st.warning(
            "⚠️ **No Overlap:** Brokers have different date ranges with no common period. Consolidated view will be limited."
        )

    if clipping_needed:
        st.info(
            "ℹ️ **Note:** Some IBKR statements covered multiple months and were adjusted to match the analysis period."
        )

    st.markdown("---")


def show_consolidated_view(metrics, df_portfolio, df_brokers, timeline_df):
    """Show consolidated portfolio view"""
    st.markdown("### Consolidated Portfolio View")
    st.markdown("*All brokers combined for the analysis period*")

    # Key metrics — row 1
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Portfolio Value",
            f"${metrics['total_ending_value']:,.0f}",
            f"${metrics['change_in_value']:,.0f}",
        )

    with col2:
        months = metrics.get("months_in_period", 1)
        st.metric(
            f"TWR ({months} month{'s' if months > 1 else ''})",
            f"{metrics.get('twr_total', metrics['twr_monthly']):.2f}%",
            f"{metrics['twr_annualized']:.2f}% annualized",
        )

    with col3:
        st.metric(
            "MWR (Period)",
            f"{metrics.get('mwr_period', 0):.2f}%",
            f"{metrics.get('mwr_annualized', 0):.2f}% annualized",
        )

    with col4:
        st.metric("Net Cash Flow", f"${metrics['net_cash_flow']:,.0f}")

    # Income & gains breakdown — row 2
    st.markdown("### 💰 Income & Gains")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Investment P&L", f"${metrics.get('total_change_in_value', 0):,.0f}")

    with col2:
        st.metric("Dividends", f"${metrics.get('total_dividend_income', 0):,.0f}")

    with col3:
        st.metric("Interest", f"${metrics.get('total_interest_income', 0):,.0f}")

    with col4:
        st.metric("Realised ST", f"${metrics.get('total_realised_st', 0):,.0f}")

    with col5:
        st.metric("Realised LT", f"${metrics.get('total_realised_lt', 0):,.0f}")

    # Risk metrics
    if not timeline_df.empty and len(timeline_df) >= 2:
        st.markdown("### 🎯 Risk Metrics")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            sharpe = metrics.get("sharpe_ratio", 0)
            st.metric("Sharpe Ratio", f"{sharpe:.2f}")

        with col2:
            max_dd = metrics.get("max_drawdown", 0)
            st.metric("Max Drawdown", f"{max_dd:.2f}%")

        with col3:
            win_rate = metrics.get("win_rate", 0)
            st.metric("Win Rate", f"{win_rate:.1f}%")
            st.caption("*% of months with positive portfolio return*")

        with col4:
            volatility = metrics.get("volatility", 0)
            st.metric("Volatility", f"{volatility:.2f}%")

    st.markdown("---")

    # Broker / account filters (used by breakdown table + charts below)
    _fc1, _fc2 = st.columns(2)
    with _fc1:
        _all_brokers = sorted(df_brokers["Broker"].dropna().unique().tolist()) if "Broker" in df_brokers.columns else []
        _sel_brokers = st.multiselect("Filter by Broker", _all_brokers, default=_all_brokers, key="cons_broker")
    with _fc2:
        if "Account Number" in df_brokers.columns:
            _cand = df_brokers.loc[df_brokers["Broker"].isin(_sel_brokers), "Account Number"].dropna().unique().tolist()
            _all_accts = sorted(str(a) for a in _cand)
        else:
            _all_accts = []
        _sel_accts = st.multiselect("Filter by Account", _all_accts, default=_all_accts, key="cons_account") if _all_accts else []
    _filt = df_brokers["Broker"].isin(_sel_brokers) if _sel_brokers else pd.Series([True] * len(df_brokers), index=df_brokers.index)
    if _sel_accts and "Account Number" in df_brokers.columns:
        _filt = _filt & (df_brokers["Account Number"].astype(str).isin(_sel_accts) | df_brokers["Account Number"].isna())
    _df_brokers_filtered = df_brokers[_filt]

    # Charts
    with st.spinner("📊 Creating charts..."):
        fig1, fig2, fig3, fig4 = create_consolidated_charts(metrics, df_brokers)

    col1, col2 = st.columns(2)

    with col1:
        st.plotly_chart(fig1, use_container_width=True)
        st.plotly_chart(fig3, use_container_width=True)

    with col2:
        st.plotly_chart(fig2, use_container_width=True)
        st.plotly_chart(fig4, use_container_width=True)

    # Broker breakdown table (full-width, filtered)
    st.markdown("### 📋 Broker Breakdown")
    dollar_cols = [
        "Starting Value", "Ending Value", "Deposits", "Withdrawals",
        "Net Cash Flow", "Security Transfers", "Change in Value",
        "Dividend Income", "Interest Income",
        "Realised (ST)", "Realised (LT)", "Realised Gains",
        "Unrealised Gains", "Total Gains",
    ]
    pct_cols = ["TWR (%)", "TWR Annualized (%)", "Return (%)"]
    fmt = {c: "${:,.0f}" for c in dollar_cols if c in df_brokers.columns}
    fmt.update({c: "{:.2f}%" for c in pct_cols if c in df_brokers.columns})
    show_cols = [c for c in [
        "Broker", "Account Number", "Period", "Months",
        "Starting Value", "Ending Value", "Change in Value",
        "Dividend Income", "Interest Income",
        "Realised (ST)", "Realised (LT)", "Unrealised Gains",
        "TWR (%)", "TWR Annualized (%)",
        "Sharpe Ratio", "Max Drawdown (%)", "Volatility (%)",
    ] if c in df_brokers.columns]
    st.dataframe(
        _df_brokers_filtered[show_cols].style.format(fmt, na_rep="—"),
        use_container_width=True,
        hide_index=True,
    )


def show_timeline_view(timeline_df, comparison_df, benchmark_comparison, metrics):
    """Show timeline analysis"""
    st.markdown("### Timeline Analysis")

    if timeline_df.empty:
        st.info("📊 Upload multiple months of statements to see timeline analysis")
        return

    # Timeline chart
    st.markdown("#### Portfolio Value Over Time")
    fig_timeline = create_timeline_chart(timeline_df)
    st.plotly_chart(fig_timeline, use_container_width=True)

    # Benchmark comparison
    if comparison_df is not None and not comparison_df.empty:
        st.markdown("#### vs Benchmarks (Normalized to 100)")
        fig_bench = create_benchmark_comparison_chart(comparison_df)
        st.plotly_chart(fig_bench, use_container_width=True)

    # Monthly returns
    st.markdown("#### Monthly Returns")
    bench_data = benchmark_comparison["benchmarks"] if benchmark_comparison else None
    fig_returns = create_monthly_returns_chart(timeline_df, bench_data)
    st.plotly_chart(fig_returns, use_container_width=True)

    # Drawdown
    if len(timeline_df) >= 2:
        st.markdown("#### Drawdown from Peak")
        fig_dd = create_drawdown_chart(timeline_df)
        st.plotly_chart(fig_dd, use_container_width=True)

    # Monthly breakdown table — with broker/account filters
    st.markdown("#### Monthly Breakdown")

    _tl_brokers = sorted(
        b for b in timeline_df["broker"].dropna().unique() if b != "Total Portfolio"
    ) if "broker" in timeline_df.columns else []
    _tfc1, _tfc2 = st.columns(2)
    with _tfc1:
        _tl_sel_brokers = st.multiselect(
            "Filter by Broker", _tl_brokers, default=_tl_brokers, key="tl_broker"
        )
    with _tfc2:
        if "account_number" in timeline_df.columns and _tl_sel_brokers:
            _tl_cand = timeline_df.loc[
                timeline_df["broker"].isin(_tl_sel_brokers), "account_number"
            ].dropna().unique().tolist()
            _tl_all_accts = sorted(str(a) for a in _tl_cand)
        else:
            _tl_all_accts = []
        _tl_sel_accts = st.multiselect(
            "Filter by Account", _tl_all_accts, default=_tl_all_accts, key="tl_account"
        ) if _tl_all_accts else []

    # Apply filter (keep Total Portfolio row only when no filter active, or show per-account rows)
    if _tl_sel_accts and "account_number" in timeline_df.columns:
        _tl_filt_df = timeline_df[timeline_df["account_number"].astype(str).isin(_tl_sel_accts)].copy()
    elif _tl_sel_brokers and len(_tl_sel_brokers) < len(_tl_brokers):
        _tl_filt_df = timeline_df[timeline_df["broker"].isin(_tl_sel_brokers)].copy()
    else:
        _tl_filt_df = timeline_df[timeline_df["broker"] == "Total Portfolio"].copy()

    # Cumulative unrealised — running total per account/broker, sorted by month
    if "unrealised_gains" in _tl_filt_df.columns:
        _grp_col = "account_number" if "account_number" in _tl_filt_df.columns else "broker"
        _tl_filt_df = _tl_filt_df.sort_values([_grp_col, "month"])
        _tl_filt_df["cumulative_unrealised"] = (
            _tl_filt_df.groupby(_grp_col)["unrealised_gains"].cumsum()
        )

    _have_broker_col = "broker" in _tl_filt_df.columns and _tl_filt_df["broker"].nunique() > 1
    base_cols = ["broker", "account_number"] if _have_broker_col else []
    base_cols += [
        "month", "start_value", "end_value", "return_pct",
        "deposits", "withdrawals", "realised_gains", "unrealised_gains",
        "cumulative_unrealised",
    ]
    base_names = (["Broker", "Account"] if _have_broker_col else []) + [
        "Month", "Start Value", "End Value", "Return (%)",
        "Deposits", "Withdrawals", "Realised Gains", "Unrealised Gains",
        "Cumulative Unrealised",
    ]
    fmt = {
        "Start Value": "${:,.0f}", "End Value": "${:,.0f}",
        "Return (%)": "{:.2f}%",
        "Deposits": "${:,.0f}", "Withdrawals": "${:,.0f}",
        "Realised Gains": "${:,.0f}", "Unrealised Gains": "${:,.0f}",
        "Cumulative Unrealised": "${:,.0f}",
    }

    for extra_col, extra_name, extra_fmt in [
        ("security_transfers", "Security Transfers", "${:,.0f}"),
        ("change_in_value",    "Change in Value",    "${:,.0f}"),
        ("dividend_income",    "Dividend Income",    "${:,.0f}"),
        ("interest_income",    "Interest Income",    "${:,.0f}"),
        ("realised_st",        "Realised ST",        "${:,.0f}"),
        ("realised_lt",        "Realised LT",        "${:,.0f}"),
    ]:
        if extra_col in _tl_filt_df.columns:
            base_cols.append(extra_col)
            base_names.append(extra_name)
            fmt[extra_name] = extra_fmt

    avail = [c for c in base_cols if c in _tl_filt_df.columns]
    avail_names = [base_names[base_cols.index(c)] for c in avail]
    display_df = _tl_filt_df[avail].copy()
    display_df.columns = avail_names

    st.dataframe(
        display_df.style.format(fmt, na_rep="—"),
        use_container_width=True,
        hide_index=True,
    )


def show_individual_view(statements, df_brokers, metrics, timeline_df, risk_free_rate):
    """Show individual broker analysis"""
    st.markdown("### Individual Broker Analysis")

    # Account selector — show "Broker (AccountNumber)" labels
    def _account_label(row):
        acct = row.get("Account Number")
        if acct and pd.notna(acct):
            return f"{row['Broker']} ({acct})"
        return row["Broker"]

    account_labels = [_account_label(row) for _, row in df_brokers.iterrows()]
    selected_label = st.selectbox("Select Account", account_labels)

    if not selected_label:
        return

    # Get account row from df_brokers by position
    selected_idx = account_labels.index(selected_label)
    broker_row = df_brokers.iloc[selected_idx]

    # Show metrics — row 1
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Starting Value", f"${broker_row['Starting Value']:,.0f}")

    with col2:
        st.metric("Ending Value", f"${broker_row['Ending Value']:,.0f}")

    with col3:
        twr = broker_row.get("TWR (%)", broker_row.get("Return (%)", 0))
        twr_ann = broker_row.get("TWR Annualized (%)", 0)
        st.metric("TWR", f"{twr:.2f}%", f"{twr_ann:.2f}% annualized")

    with col4:
        st.metric("Months", int(broker_row.get("Months", broker_row.get("Files", 0))))

    # Income metrics — row 2
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Investment P&L", f"${broker_row.get('Change in Value', 0):,.0f}")
    with col2:
        st.metric("Dividends", f"${broker_row.get('Dividend Income', 0):,.0f}")
    with col3:
        st.metric("Realized ST", f"${broker_row.get('Realized (ST)', 0):,.0f}")
    with col4:
        st.metric("Realized LT", f"${broker_row.get('Realized (LT)', 0):,.0f}")

    # Filter timeline_df by account_number if available, else by broker name
    acct_num = broker_row.get("Account Number")
    if pd.notna(acct_num) and acct_num and "account_number" in timeline_df.columns:
        broker_df = timeline_df[timeline_df["account_number"] == acct_num].copy()
    else:
        broker_df = timeline_df[timeline_df["broker"] == broker_row["Broker"]].copy()
    broker_df = broker_df.sort_values("date")

    if not broker_df.empty and len(broker_df) >= 2:
        # Calculate risk metrics
        broker_risk = calculate_all_risk_metrics(broker_df, risk_free_rate)

        st.markdown("#### Risk Metrics")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Sharpe Ratio", f"{broker_risk['sharpe_ratio']:.2f}")

        with col2:
            st.metric("Max Drawdown", f"{broker_risk['max_drawdown']:.2f}%")

        with col3:
            st.metric("Win Rate", f"{broker_risk['win_rate']:.1f}%")
            st.caption("*% of months with positive portfolio return*")

        with col4:
            st.metric("Volatility", f"{broker_risk['volatility']:.2f}%")

        # Timeline chart
        st.markdown("#### Timeline")
        fig_broker_timeline = create_timeline_chart(
            broker_df, title=f"{selected_label} - Value Over Time"
        )
        st.plotly_chart(fig_broker_timeline, use_container_width=True)

        # Monthly breakdown
        st.markdown("#### Monthly Performance")
        display_df = broker_df[
            ["month", "start_value", "end_value", "return_pct"]
        ].copy()
        display_df.columns = ["Month", "Start Value", "End Value", "Return (%)"]

        st.dataframe(
            display_df.style.format(
                {
                    "Start Value": "${:,.0f}",
                    "End Value": "${:,.0f}",
                    "Return (%)": "{:.2f}%",
                }
            ).background_gradient(
                subset=["Return (%)"], cmap="RdYlGn", vmin=-5, vmax=5
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "📊 Only one period available for this broker. Upload more statements to see timeline."
        )

    # Detailed breakdown chart (visualizer is keyed by account label)
    broker_figures = create_individual_charts(metrics, df_brokers)
    if selected_label in broker_figures:
        st.markdown("#### Detailed Breakdown")
        st.plotly_chart(broker_figures[selected_label], use_container_width=True)


def show_holdings_view(ending_holdings_df):
    """Show current holdings across all brokers."""
    st.markdown("### 📦 Portfolio Holdings")
    st.markdown("*Most recent holdings per account across all brokers*")

    if ending_holdings_df is None or (
        hasattr(ending_holdings_df, "empty") and ending_holdings_df.empty
    ):
        st.info("📊 No holdings data available. Upload Fidelity or E*TRADE statements with holdings pages.")
        return

    # Broker + account filters
    _hfc1, _hfc2 = st.columns(2)
    with _hfc1:
        brokers = sorted(ending_holdings_df["broker"].dropna().unique().tolist()) if "broker" in ending_holdings_df.columns else []
        selected_brokers = st.multiselect("Filter by Broker", brokers, default=brokers, key="hld_broker")
    with _hfc2:
        if "account_number" in ending_holdings_df.columns and selected_brokers:
            _hld_cand = ending_holdings_df.loc[
                ending_holdings_df["broker"].isin(selected_brokers), "account_number"
            ].dropna().unique().tolist()
            _hld_all_accts = sorted(str(a) for a in _hld_cand)
        else:
            _hld_all_accts = []
        selected_accounts = st.multiselect(
            "Filter by Account", _hld_all_accts, default=_hld_all_accts, key="hld_account"
        ) if _hld_all_accts else []

    df = ending_holdings_df.copy()
    if selected_brokers:
        df = df[df["broker"].isin(selected_brokers)]
    if selected_accounts and "account_number" in df.columns:
        df = df[df["account_number"].astype(str).isin(selected_accounts)]

    if df.empty:
        st.info("No holdings for selected brokers/accounts.")
        return

    # Summary totals
    col1, col2, col3 = st.columns(3)
    with col1:
        if "market_value" in df.columns:
            st.metric("Total Market Value", f"${df['market_value'].sum():,.0f}")
    with col2:
        if "cost_basis" in df.columns:
            st.metric("Total Cost Basis", f"${df['cost_basis'].sum():,.0f}")
    with col3:
        if "unrealized_gain" in df.columns:
            unreal = df["unrealized_gain"].sum()
            st.metric("Total Unrealised", f"${unreal:,.0f}")

    st.markdown("---")

    # Holdings table — broker and account_number always lead
    priority_cols = [
        "broker", "account_number", "ticker", "description",
        "quantity", "price", "market_value", "cost_basis", "unrealized_gain",
        "beginning_value", "end_date",
    ]
    display_cols = [c for c in priority_cols if c in df.columns]
    # Guarantee broker + account_number at front if present
    for must_have in ("account_number", "broker"):
        if must_have in df.columns and must_have not in display_cols:
            display_cols.insert(0, must_have)
    if not display_cols:
        display_cols = df.columns.tolist()

    col_labels = {
        "broker": "Broker", "account_number": "Account",
        "ticker": "Ticker", "description": "Description",
        "quantity": "Qty", "price": "Price",
        "market_value": "Market Value", "cost_basis": "Cost Basis",
        "unrealized_gain": "Unrealised G/L",
        "beginning_value": "Beg. Value", "end_date": "As Of",
    }
    display_df = df[display_cols].rename(columns=col_labels)

    # Format
    dollar_disp = {"Market Value", "Cost Basis", "Unrealised G/L", "Beg. Value", "Price"}
    qty_disp = {"Qty"}
    fmt = {}
    for c in display_df.columns:
        if c in dollar_disp:
            fmt[c] = "${:,.2f}"
        elif c in qty_disp:
            fmt[c] = "{:,.4f}"

    st.dataframe(
        display_df.style.format(fmt, na_rep="—"),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

    # Per-broker breakdown
    if "broker" in df.columns and "market_value" in df.columns:
        st.markdown("#### Holdings by Broker")
        by_broker = (
            df.groupby("broker")["market_value"]
            .sum()
            .reset_index()
            .rename(columns={"broker": "Broker", "market_value": "Market Value"})
            .sort_values("Market Value", ascending=False)
        )
        st.dataframe(
            by_broker.style.format({"Market Value": "${:,.0f}"}),
            use_container_width=True,
            hide_index=True,
        )


def show_benchmarks_view(benchmark_comparison, metrics, timeline_df):
    """Show benchmark comparison analysis"""
    st.markdown("### Benchmark Comparison")

    if not benchmark_comparison or "benchmarks" not in benchmark_comparison:
        st.info(
            "📈 Benchmark data could not be fetched. Check your internet connection."
        )
        return

    if timeline_df.empty or len(timeline_df) < 2:
        st.info("📊 Need at least 2 months of data for benchmark comparison")
        return

    # Overall comparison
    st.markdown("#### Performance Summary")

    comparison_data = []

    # Portfolio row
    comparison_data.append(
        {
            "Name": "Portfolio",
            "Total Return": f"{metrics.get('twr_monthly', 0) * len(timeline_df):.2f}%",
            "Sharpe Ratio": f"{metrics.get('sharpe_ratio', 0):.2f}",
            "Sortino Ratio": f"{metrics.get('sortino_ratio', 0):.2f}",
            "Max Drawdown": f"{metrics.get('max_drawdown', 0):.2f}%",
            "Win Rate": f"{metrics.get('win_rate', 0):.1f}%",
            "Volatility": f"{metrics.get('volatility', 0):.2f}%",
        }
    )

    # Benchmark rows
    for name, bench_data in benchmark_comparison["benchmarks"].items():
        bench_metrics = bench_data["metrics"]
        comparison_data.append(
            {
                "Name": name,
                "Total Return": f"{bench_metrics['total_return']:.2f}%",
                "Sharpe Ratio": f"{bench_metrics['sharpe_ratio']:.2f}",
                "Sortino Ratio": f"{bench_metrics['sortino_ratio']:.2f}",
                "Max Drawdown": f"{bench_metrics['max_drawdown']:.2f}%",
                "Win Rate": f"{bench_metrics['win_rate']:.1f}%",
                "Volatility": f"{bench_metrics['volatility']:.2f}%",
            }
        )

    comparison_df_display = pd.DataFrame(comparison_data)
    st.dataframe(comparison_df_display, use_container_width=True, hide_index=True)

    # Alpha & Beta
    st.markdown("#### Alpha & Beta Analysis")

    for name, comp_metrics in benchmark_comparison["comparison"].items():
        st.markdown(f"**vs {name}**")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Beta", f"{comp_metrics['beta']:.2f}")

        with col2:
            st.metric("Alpha", f"{comp_metrics['alpha']:.2f}%")

        with col3:
            st.metric("Correlation", f"{comp_metrics['correlation']:.2f}")

        with col4:
            excess = comp_metrics["excess_return"]
            st.metric("Excess Return", f"{excess:.2f}%")

    # Risk-return scatter
    st.markdown("#### Risk-Return Profile")

    portfolio_metrics_chart = {
        "total_return": metrics.get("twr_monthly", 0) * len(timeline_df),
        "volatility": metrics.get("volatility", 0),
    }

    fig_scatter = create_risk_return_scatter(
        portfolio_metrics_chart, benchmark_comparison["benchmarks"]
    )
    st.plotly_chart(fig_scatter, use_container_width=True)


def show_export_view(metrics, summary_df, timeline_df):
    """Show export options"""
    st.markdown("### 💾 Export Data")

    # Prepare export
    export_data = prepare_export_data(metrics, timeline_df, summary_df)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 📄 CSV Export")
        st.markdown("Compatible with Excel, Google Sheets")

        csv_data = export_to_csv(export_data)

        st.download_button(
            label="⬇️ Download CSV",
            data=csv_data,
            file_name=f"portfolio_analysis_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col2:
        st.markdown("#### 📊 Excel Export")
        st.markdown("Multiple sheets with formatting")

        excel_data = export_to_excel(export_data)

        st.download_button(
            label="⬇️ Download Excel",
            data=excel_data,
            file_name=f"portfolio_analysis_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.markdown("---")

    st.markdown("#### 📦 What's Included:")
    st.markdown(
        """
    - **Portfolio Summary**: Overall metrics and risk metrics
    - **Broker Breakdown**: Detailed breakdown by broker
    - **Monthly Timeline**: Month-by-month performance (if available)
    - **Detailed Files**: Individual statement information
    """
    )

    # Preview
    with st.expander("👀 Preview Export Data"):
        for sheet_name, df in export_data.items():
            st.markdown(f"**{sheet_name}**")
            st.dataframe(df.head(10), use_container_width=True)


if __name__ == "__main__":
    main()
