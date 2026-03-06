"""
Benchmarks Module - S&P 500 and NASDAQ comparison
Uses yfinance to fetch market data and calculate comparison metrics
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import yfinance as yf
from src.risk_analysis import (
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
)


def fetch_benchmark_data(
    start_date: datetime, end_date: datetime, tickers: List[str] = ["^GSPC", "^IXIC"]
) -> Dict:
    """
    Fetch benchmark data from yfinance

    Args:
        start_date: Start date for data
        end_date: End date for data
        tickers: List of ticker symbols (default: S&P 500 and NASDAQ)

    Returns:
        Dict with benchmark data
    """

    benchmarks = {}

    for ticker in tickers:
        try:
            # Add buffer to dates (yfinance sometimes needs this)
            buffer_start = start_date - timedelta(days=7)
            buffer_end = end_date + timedelta(days=7)

            # Fetch data with multiple retry attempts
            data = None
            for attempt in range(3):
                try:
                    data = yf.download(
                        ticker,
                        start=buffer_start,
                        end=buffer_end,
                        progress=False,
                        timeout=10,
                    )
                    if not data.empty:
                        break
                except Exception as e:
                    if attempt == 2:  # Last attempt
                        print(f"Failed to download {ticker} after 3 attempts: {e}")
                    continue

            if data is None or data.empty:
                print(f"No data available for {ticker}")
                continue

            # Filter to actual date range
            data = data[
                (data.index >= pd.Timestamp(start_date))
                & (data.index <= pd.Timestamp(end_date))
            ]

            if data.empty:
                print(f"No data in date range for {ticker}")
                continue

            # Get benchmark name
            if ticker == "^GSPC":
                name = "S&P 500"
            elif ticker == "^IXIC":
                name = "NASDAQ"
            else:
                name = ticker

            benchmarks[name] = {
                "ticker": ticker,
                "data": data,
                "start_date": data.index[0].to_pydatetime(),
                "end_date": data.index[-1].to_pydatetime(),
            }

        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            continue

    return benchmarks


def calculate_monthly_benchmark_returns(benchmark_data: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate monthly returns from daily benchmark data

    Args:
        benchmark_data: DataFrame from yfinance with daily prices

    Returns:
        DataFrame with monthly returns
    """

    if benchmark_data.empty:
        return pd.DataFrame()

    # Resample to month-end and get closing prices
    monthly = benchmark_data["Close"].resample("M").last()

    # Calculate returns
    monthly_returns = monthly.pct_change() * 100  # Convert to percentage

    # Create DataFrame
    df = pd.DataFrame(
        {
            "date": monthly.index,
            "price": monthly.values,
            "return_pct": monthly_returns.values,
        }
    )

    # Remove first row (NaN return)
    df = df.dropna()

    # Add month string
    df["month"] = df["date"].dt.strftime("%Y-%m")

    return df


def align_benchmark_to_portfolio(
    benchmark_df: pd.DataFrame, portfolio_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Align benchmark data to portfolio timeline
    Only keep months where portfolio has data

    Args:
        benchmark_df: Benchmark monthly data
        portfolio_df: Portfolio timeline data

    Returns:
        Aligned benchmark DataFrame
    """

    if benchmark_df.empty or portfolio_df.empty:
        return pd.DataFrame()

    # Get portfolio months
    portfolio_months = set(portfolio_df["month"].tolist())

    # Filter benchmark to only these months
    aligned = benchmark_df[benchmark_df["month"].isin(portfolio_months)].copy()

    return aligned


def calculate_beta(
    portfolio_returns: List[float], market_returns: List[float]
) -> float:
    """
    Calculate Beta (portfolio volatility relative to market)

    Beta > 1: More volatile than market
    Beta < 1: Less volatile than market
    Beta = 1: Same volatility as market

    Args:
        portfolio_returns: List of portfolio returns (%)
        market_returns: List of market returns (%)

    Returns:
        Beta value
    """

    if len(portfolio_returns) != len(market_returns) or len(portfolio_returns) < 2:
        return 0.0

    # Convert to numpy arrays (as decimals)
    port = np.array(portfolio_returns) / 100
    mkt = np.array(market_returns) / 100

    # Calculate covariance and variance
    covariance = np.cov(port, mkt)[0, 1]
    market_variance = np.var(mkt, ddof=1)

    if market_variance == 0:
        return 0.0

    beta = covariance / market_variance

    return beta


def calculate_alpha(
    portfolio_return: float,
    market_return: float,
    beta: float,
    risk_free_rate: float = 4.5,
) -> float:
    """
    Calculate Alpha (excess return beyond what beta explains)

    Alpha = Portfolio Return - (Risk Free + Beta × (Market Return - Risk Free))

    Positive alpha: Outperformed expectations
    Negative alpha: Underperformed expectations

    Args:
        portfolio_return: Total portfolio return (%)
        market_return: Total market return (%)
        beta: Portfolio beta vs market
        risk_free_rate: Annual risk-free rate (%)

    Returns:
        Alpha (%)
    """

    # Expected return based on CAPM
    expected_return = risk_free_rate + beta * (market_return - risk_free_rate)

    # Alpha is actual return minus expected
    alpha = portfolio_return - expected_return

    return alpha


def calculate_correlation(
    portfolio_returns: List[float], market_returns: List[float]
) -> float:
    """
    Calculate correlation between portfolio and market

    Range: -1 (perfect negative) to +1 (perfect positive)

    Args:
        portfolio_returns: List of portfolio returns (%)
        market_returns: List of market returns (%)

    Returns:
        Correlation coefficient
    """

    if len(portfolio_returns) != len(market_returns) or len(portfolio_returns) < 2:
        return 0.0

    # Convert to numpy arrays
    port = np.array(portfolio_returns)
    mkt = np.array(market_returns)

    # Calculate correlation
    correlation = np.corrcoef(port, mkt)[0, 1]

    return correlation


def calculate_benchmark_metrics(
    benchmark_df: pd.DataFrame, risk_free_rate: float = 4.5
) -> Dict:
    """
    Calculate all metrics for a benchmark

    Args:
        benchmark_df: Benchmark monthly data
        risk_free_rate: Annual risk-free rate (%)

    Returns:
        Dict with all benchmark metrics
    """

    if benchmark_df.empty:
        return {}

    returns = benchmark_df["return_pct"].tolist()
    prices = benchmark_df["price"].tolist()

    # Calculate total return
    if len(prices) >= 2:
        total_return = ((prices[-1] - prices[0]) / prices[0]) * 100
    else:
        total_return = 0.0

    # Risk metrics
    sharpe = calculate_sharpe_ratio(returns, risk_free_rate)
    sortino = calculate_sortino_ratio(returns, risk_free_rate)
    max_dd = calculate_max_drawdown(prices)
    win_rate = calculate_win_rate(returns)
    volatility = np.std(returns, ddof=1) if len(returns) > 1 else 0.0

    metrics = {
        "total_return": total_return,
        "avg_monthly_return": np.mean(returns) if returns else 0.0,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_dd["max_drawdown"],
        "win_rate": win_rate["win_rate"],
        "volatility": volatility,
        "best_month": max(returns) if returns else 0.0,
        "worst_month": min(returns) if returns else 0.0,
    }

    return metrics


def compare_to_benchmarks(
    portfolio_df: pd.DataFrame,
    start_date: datetime,
    end_date: datetime,
    risk_free_rate: float = 4.5,
) -> Dict:
    """
    Complete benchmark comparison analysis

    Args:
        portfolio_df: Portfolio timeline DataFrame
        start_date: Start date for analysis
        end_date: End date for analysis
        risk_free_rate: Annual risk-free rate (%)

    Returns:
        Dict with all benchmark comparisons
    """

    # Fetch benchmarks
    benchmarks_raw = fetch_benchmark_data(start_date, end_date)

    if not benchmarks_raw:
        return {
            "benchmarks": {},
            "comparison": {},
            "error": "Could not fetch benchmark data",
        }

    result = {"benchmarks": {}, "comparison": {}}

    portfolio_returns = portfolio_df["return_pct"].tolist()
    portfolio_total_return = (
        (
            (portfolio_df["end_value"].iloc[-1] - portfolio_df["end_value"].iloc[0])
            / portfolio_df["end_value"].iloc[0]
            * 100
        )
        if len(portfolio_df) > 0
        else 0.0
    )

    for name, bench_data in benchmarks_raw.items():
        # Calculate monthly returns
        bench_monthly = calculate_monthly_benchmark_returns(bench_data["data"])

        # Align to portfolio timeline
        bench_aligned = align_benchmark_to_portfolio(bench_monthly, portfolio_df)

        if bench_aligned.empty:
            continue

        # Calculate benchmark metrics
        bench_metrics = calculate_benchmark_metrics(bench_aligned, risk_free_rate)

        # Store aligned data
        result["benchmarks"][name] = {"data": bench_aligned, "metrics": bench_metrics}

        # Calculate comparison metrics
        bench_returns = bench_aligned["return_pct"].tolist()

        beta = calculate_beta(portfolio_returns, bench_returns)
        alpha = calculate_alpha(
            portfolio_total_return, bench_metrics["total_return"], beta, risk_free_rate
        )
        correlation = calculate_correlation(portfolio_returns, bench_returns)

        result["comparison"][name] = {
            "beta": beta,
            "alpha": alpha,
            "correlation": correlation,
            "excess_return": portfolio_total_return - bench_metrics["total_return"],
        }

    return result


def create_comparison_dataframe(
    portfolio_df: pd.DataFrame, benchmarks: Dict
) -> pd.DataFrame:
    """
    Create a combined DataFrame for charting portfolio vs benchmarks

    Args:
        portfolio_df: Portfolio timeline
        benchmarks: Benchmark data dict from compare_to_benchmarks

    Returns:
        DataFrame with normalized values (all start at 100)
    """

    if portfolio_df.empty:
        return pd.DataFrame()

    # Start with portfolio cumulative returns
    df = portfolio_df[["month", "date", "cumulative_value"]].copy()
    df.rename(columns={"cumulative_value": "Portfolio"}, inplace=True)

    # Add each benchmark
    for name, bench_data in benchmarks.items():
        bench_df = bench_data["data"]

        if bench_df.empty:
            continue

        # Calculate cumulative for benchmark (starting at 100)
        cumulative = [100.0]
        for ret in bench_df["return_pct"].iloc[1:]:
            cumulative.append(cumulative[-1] * (1 + ret / 100))

        bench_df = bench_df.copy()
        bench_df["cumulative"] = cumulative

        # Merge with main df
        df = df.merge(bench_df[["month", "cumulative"]], on="month", how="left")
        df.rename(columns={"cumulative": name}, inplace=True)

    return df
