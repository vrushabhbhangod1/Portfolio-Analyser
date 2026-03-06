"""
Risk Metrics Module
Calculates Sharpe Ratio, Sortino Ratio, Max Drawdown, Win Rate, etc.
"""

import pandas as pd
import numpy as np
from typing import List, Dict


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 4.5) -> float:
    """
    Calculate Sharpe Ratio
    
    Args:
        returns: List of monthly returns (in %)
        risk_free_rate: Annual risk-free rate (in %)
    
    Returns:
        Sharpe ratio (annualized)
    """
    
    if not returns or len(returns) < 2:
        return 0.0
    
    # Convert annual risk-free rate to monthly
    monthly_rf = risk_free_rate / 12
    
    # Convert returns to decimals
    returns_decimal = [r / 100 for r in returns]
    
    # Calculate excess returns
    excess_returns = [r - (monthly_rf / 100) for r in returns_decimal]
    
    # Calculate mean and std dev
    mean_excess = np.mean(excess_returns)
    std_dev = np.std(excess_returns, ddof=1)
    
    if std_dev == 0:
        return 0.0
    
    # Annualize: multiply by sqrt(12) for monthly data
    sharpe = (mean_excess / std_dev) * np.sqrt(12)
    
    return sharpe


def calculate_sortino_ratio(returns: List[float], risk_free_rate: float = 4.5) -> float:
    """
    Calculate Sortino Ratio
    (Like Sharpe but only penalizes downside volatility)
    
    Args:
        returns: List of monthly returns (in %)
        risk_free_rate: Annual risk-free rate (in %)
    
    Returns:
        Sortino ratio (annualized)
    """
    
    if not returns or len(returns) < 2:
        return 0.0
    
    # Convert annual risk-free rate to monthly
    monthly_rf = risk_free_rate / 12
    
    # Convert returns to decimals
    returns_decimal = [r / 100 for r in returns]
    
    # Calculate excess returns
    excess_returns = [r - (monthly_rf / 100) for r in returns_decimal]
    
    # Calculate mean
    mean_excess = np.mean(excess_returns)
    
    # Calculate downside deviation (only negative returns)
    negative_returns = [r for r in excess_returns if r < 0]
    
    if not negative_returns:
        # No downside, return high value
        return 999.0
    
    downside_dev = np.std(negative_returns, ddof=1)
    
    if downside_dev == 0:
        return 0.0
    
    # Annualize
    sortino = (mean_excess / downside_dev) * np.sqrt(12)
    
    return sortino


def calculate_max_drawdown(values: List[float]) -> Dict:
    """
    Calculate Maximum Drawdown
    
    Args:
        values: List of portfolio values over time
    
    Returns:
        Dict with max_drawdown (%), peak_value, trough_value, peak_date, trough_date
    """
    
    if not values or len(values) < 2:
        return {
            'max_drawdown': 0.0,
            'peak_value': 0.0,
            'trough_value': 0.0,
            'peak_idx': 0,
            'trough_idx': 0
        }
    
    peak = values[0]
    peak_idx = 0
    max_dd = 0.0
    max_dd_peak_idx = 0
    max_dd_trough_idx = 0
    
    for i, value in enumerate(values):
        # Update peak if we have a new high
        if value > peak:
            peak = value
            peak_idx = i
        
        # Calculate current drawdown
        if peak > 0:
            drawdown = (value - peak) / peak * 100
            
            # Update max drawdown if current is worse
            if drawdown < max_dd:
                max_dd = drawdown
                max_dd_peak_idx = peak_idx
                max_dd_trough_idx = i
    
    result = {
        'max_drawdown': max_dd,
        'peak_value': values[max_dd_peak_idx] if values else 0,
        'trough_value': values[max_dd_trough_idx] if values else 0,
        'peak_idx': max_dd_peak_idx,
        'trough_idx': max_dd_trough_idx
    }
    
    return result


def calculate_win_rate(returns: List[float]) -> Dict:
    """
    Calculate Win Rate (% of positive return periods)
    
    Args:
        returns: List of returns (in %)
    
    Returns:
        Dict with win_rate, wins, losses, total
    """
    
    if not returns:
        return {
            'win_rate': 0.0,
            'wins': 0,
            'losses': 0,
            'total': 0
        }
    
    wins = sum(1 for r in returns if r > 0)
    losses = sum(1 for r in returns if r < 0)
    total = len(returns)
    
    win_rate = (wins / total * 100) if total > 0 else 0.0
    
    return {
        'win_rate': win_rate,
        'wins': wins,
        'losses': losses,
        'total': total
    }


def calculate_volatility(returns: List[float], annualize: bool = True) -> float:
    """
    Calculate volatility (standard deviation of returns)
    
    Args:
        returns: List of returns (in %)
        annualize: If True, annualize the volatility
    
    Returns:
        Volatility (%)
    """
    
    if not returns or len(returns) < 2:
        return 0.0
    
    # Convert to decimals
    returns_decimal = [r / 100 for r in returns]
    
    # Calculate std dev
    vol = np.std(returns_decimal, ddof=1)
    
    # Annualize if requested (multiply by sqrt(12) for monthly data)
    if annualize:
        vol = vol * np.sqrt(12)
    
    # Convert back to percentage
    return vol * 100


def calculate_all_risk_metrics(df: pd.DataFrame, risk_free_rate: float = 4.5) -> Dict:
    """
    Calculate all risk metrics from a timeline DataFrame
    
    Args:
        df: DataFrame with columns 'return_pct' and 'end_value'
        risk_free_rate: Annual risk-free rate (in %)
    
    Returns:
        Dict with all risk metrics
    """
    
    if df.empty:
        return {
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'max_drawdown': 0.0,
            'max_drawdown_details': {},
            'win_rate': 0.0,
            'win_rate_details': {},
            'volatility': 0.0,
            'best_month': 0.0,
            'worst_month': 0.0,
            'avg_return': 0.0
        }
    
    returns = df['return_pct'].tolist()
    values = df['end_value'].tolist()
    
    # Calculate metrics
    sharpe = calculate_sharpe_ratio(returns, risk_free_rate)
    sortino = calculate_sortino_ratio(returns, risk_free_rate)
    max_dd = calculate_max_drawdown(values)
    win_rate_data = calculate_win_rate(returns)
    volatility = calculate_volatility(returns, annualize=True)
    
    result = {
        'sharpe_ratio': sharpe,
        'sortino_ratio': sortino,
        'max_drawdown': max_dd['max_drawdown'],
        'max_drawdown_details': max_dd,
        'win_rate': win_rate_data['win_rate'],
        'win_rate_details': win_rate_data,
        'volatility': volatility,
        'best_month': max(returns) if returns else 0.0,
        'worst_month': min(returns) if returns else 0.0,
        'avg_return': np.mean(returns) if returns else 0.0
    }
    
    return result


def calculate_rolling_sharpe(df: pd.DataFrame, window: int = 6, risk_free_rate: float = 4.5) -> pd.DataFrame:
    """
    Calculate rolling Sharpe ratio
    
    Args:
        df: DataFrame with 'return_pct' column
        window: Rolling window size (in months)
        risk_free_rate: Annual risk-free rate (in %)
    
    Returns:
        DataFrame with added 'rolling_sharpe' column
    """
    
    if df.empty or len(df) < window:
        return df
    
    df = df.copy()
    df['rolling_sharpe'] = np.nan
    
    for i in range(window - 1, len(df)):
        window_returns = df['return_pct'].iloc[i - window + 1:i + 1].tolist()
        sharpe = calculate_sharpe_ratio(window_returns, risk_free_rate)
        df.loc[df.index[i], 'rolling_sharpe'] = sharpe
    
    return df
