"""
Plotly Chart Visualizations - Updated with Timeline and Benchmark Charts
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np


def create_timeline_chart(
    df: pd.DataFrame, title: str = "Portfolio Value Over Time"
) -> go.Figure:
    """Create timeline chart showing portfolio value over time"""

    # Filter for Total Portfolio rows
    total_df = df[df["broker"] == "Total Portfolio"].copy()

    if total_df.empty:
        # Fallback: sum all brokers by date
        total_df = df.groupby("date")["ending_value"].sum().reset_index()

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=total_df["date"],
            y=total_df["ending_value"],
            mode="lines+markers",
            name="Portfolio Value",
            line=dict(color="#2ecc71", width=3),
            marker=dict(size=8),
            hovertemplate="<b>%{x|%b %Y}</b><br>Value: $%{y:,.0f}<br><extra></extra>",
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Portfolio Value ($)",
        hovermode="x unified",
        height=500,
    )

    fig.update_yaxes(tickformat="$,.0f")
    return fig


def create_benchmark_comparison_chart(comparison_df: pd.DataFrame) -> go.Figure:
    """Create chart comparing portfolio to benchmarks (normalized to 100)"""

    fig = go.Figure()

    colors = {"Portfolio": "#2ecc71", "S&P 500": "#3498db", "NASDAQ": "#e74c3c"}

    for col in comparison_df.columns:
        if col in ["date", "month"]:
            continue

        fig.add_trace(
            go.Scatter(
                x=comparison_df["date"],
                y=comparison_df[col],
                mode="lines+markers",
                name=col,
                line=dict(color=colors.get(col, "#95a5a6"), width=2),
                marker=dict(size=6),
            )
        )

    fig.update_layout(
        title="Portfolio vs Benchmarks (Normalized)",
        xaxis_title="Date",
        yaxis_title="Value (Start = 100)",
        hovermode="x unified",
        height=500,
    )

    fig.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.5)
    return fig


def create_monthly_returns_chart(
    df: pd.DataFrame, benchmark_data: dict = None
) -> go.Figure:
    """Create bar chart of monthly returns with optional benchmarks"""

    fig = go.Figure()

    colors = ["#2ecc71" if r >= 0 else "#e74c3c" for r in df["return_pct"]]

    fig.add_trace(
        go.Bar(
            x=df["month"],
            y=df["return_pct"],
            name="Portfolio",
            marker_color=colors,
            text=[f"{r:.1f}%" for r in df["return_pct"]],
            textposition="outside",
        )
    )

    if benchmark_data:
        for name, bench_df in benchmark_data.items():
            if "data" in bench_df:
                bench_df = bench_df["data"]

            fig.add_trace(
                go.Scatter(
                    x=bench_df["month"],
                    y=bench_df["return_pct"],
                    name=name,
                    mode="lines+markers",
                    line=dict(width=2),
                )
            )

    fig.update_layout(
        title="Monthly Returns Comparison",
        xaxis_title="Month",
        yaxis_title="Return (%)",
        hovermode="x unified",
        height=450,
    )

    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    return fig


def create_drawdown_chart(df: pd.DataFrame) -> go.Figure:
    """Create chart showing drawdown from peak over time"""

    if df.empty:
        return go.Figure()

    values = df["end_value"].values
    peak = values[0]
    drawdowns = []

    for value in values:
        if value > peak:
            peak = value
        drawdown = ((value - peak) / peak * 100) if peak > 0 else 0
        drawdowns.append(drawdown)

    df_dd = df.copy()
    df_dd["drawdown"] = drawdowns

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df_dd["date"],
            y=df_dd["drawdown"],
            fill="tozeroy",
            mode="lines",
            line=dict(color="#e74c3c", width=2),
            fillcolor="rgba(231, 76, 60, 0.3)",
        )
    )

    fig.update_layout(
        title="Portfolio Drawdown from Peak",
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        height=400,
        showlegend=False,
    )

    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    return fig


def create_risk_return_scatter(
    portfolio_metrics: dict, benchmark_metrics: dict
) -> go.Figure:
    """Create risk-return scatter plot"""

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=[portfolio_metrics.get("volatility", 0)],
            y=[portfolio_metrics.get("total_return", 0)],
            mode="markers+text",
            name="Portfolio",
            marker=dict(size=15, color="#2ecc71"),
            text=["Portfolio"],
            textposition="top center",
        )
    )

    colors_bench = {"S&P 500": "#3498db", "NASDAQ": "#e74c3c"}

    for name, metrics in benchmark_metrics.items():
        if "metrics" in metrics:
            metrics = metrics["metrics"]

        fig.add_trace(
            go.Scatter(
                x=[metrics.get("volatility", 0)],
                y=[metrics.get("total_return", 0)],
                mode="markers+text",
                name=name,
                marker=dict(size=12, color=colors_bench.get(name, "#95a5a6")),
                text=[name],
                textposition="bottom center",
            )
        )

    fig.update_layout(
        title="Risk-Return Profile",
        xaxis_title="Risk (Volatility %)",
        yaxis_title="Return (%)",
        height=500,
        showlegend=False,
    )

    return fig


def create_consolidated_charts(metrics: dict, df_brokers: pd.DataFrame):
    """Create consolidated view charts"""

    # Chart 1: Account Values
    fig1 = go.Figure()
    brokers = df_brokers["Broker"].tolist()
    starting = df_brokers["Starting Value"].tolist()
    ending = df_brokers["Ending Value"].tolist()

    fig1.add_trace(
        go.Bar(
            name="Starting",
            x=brokers,
            y=starting,
            marker_color="#3498db",
            text=[f"${v:,.0f}" for v in starting],
            textposition="outside",
        )
    )

    fig1.add_trace(
        go.Bar(
            name="Ending",
            x=brokers,
            y=ending,
            marker_color="#2ecc71",
            text=[f"${v:,.0f}" for v in ending],
            textposition="outside",
        )
    )

    fig1.update_layout(
        title="Account Values by Broker",
        xaxis_title="Broker",
        yaxis_title="Value ($)",
        barmode="group",
        height=400,
    )
    fig1.update_yaxes(tickformat="$,.0f")

    # Chart 2: Allocation Pie
    fig2 = go.Figure(
        data=[
            go.Pie(
                labels=brokers,
                values=ending,
                hole=0.4,
                marker_colors=["#3498db", "#2ecc71", "#e74c3c", "#f39c12"],
            )
        ]
    )

    fig2.update_layout(title="Portfolio Allocation", height=400)
    fig2.add_annotation(
        text=f"Total<br>${sum(ending):,.0f}",
        x=0.5,
        y=0.5,
        font_size=16,
        showarrow=False,
    )

    # Chart 3: Returns
    returns = df_brokers["Return (%)"].tolist()
    colors = ["#2ecc71" if r >= 0 else "#e74c3c" for r in returns]

    fig3 = go.Figure(
        data=[
            go.Bar(
                x=returns,
                y=brokers,
                orientation="h",
                marker_color=colors,
                text=[f"{r:.2f}%" for r in returns],
                textposition="outside",
            )
        ]
    )

    fig3.update_layout(title="Returns by Broker", xaxis_title="Return (%)", height=400)
    fig3.add_vline(x=0, line_dash="dash", line_color="gray")

    # Chart 4: Cash Flows
    categories = ["Deposits", "Withdrawals", "Realised<br>Gains", "Unrealised<br>Gains"]
    values = [
        metrics["total_deposits"],
        -metrics["total_withdrawals"],
        metrics["total_realised_gains"],
        metrics["total_unrealised_gains"],
    ]
    colors_cf = ["#2ecc71", "#e74c3c", "#3498db", "#9b59b6"]

    fig4 = go.Figure(
        data=[
            go.Bar(
                x=categories,
                y=values,
                marker_color=colors_cf,
                text=[f"${abs(v):,.0f}" for v in values],
                textposition="outside",
            )
        ]
    )

    fig4.update_layout(
        title="Cash Flows and Gains/Losses", yaxis_title="Amount ($)", height=400
    )
    fig4.update_yaxes(tickformat="$,.0f")
    fig4.add_hline(y=0, line_dash="dash", line_color="gray")

    return fig1, fig2, fig3, fig4


def create_individual_charts(metrics: dict, df_brokers: pd.DataFrame):
    """Create individual broker charts"""

    broker_figures = {}

    for _, row in df_brokers.iterrows():
        broker = row["Broker"]

        fig = make_subplots(
            rows=1, cols=2, subplot_titles=("Value Change", "Gains Breakdown")
        )

        fig.add_trace(
            go.Bar(
                x=["Starting", "Ending"],
                y=[row["Starting Value"], row["Ending Value"]],
                marker_color=["#3498db", "#2ecc71"],
                text=[f"${row['Starting Value']:,.0f}", f"${row['Ending Value']:,.0f}"],
                textposition="outside",
                showlegend=False,
            ),
            row=1,
            col=1,
        )

        fig.add_trace(
            go.Bar(
                x=["Realised", "Unrealised"],
                y=[row["Realised Gains"], row["Unrealised Gains"]],
                marker_color=["#3498db", "#9b59b6"],
                text=[
                    f'${row["Realised Gains"]:,.0f}',
                    f'${row["Unrealised Gains"]:,.0f}',
                ],
                textposition="outside",
                showlegend=False,
            ),
            row=1,
            col=2,
        )

        fig.update_layout(title_text=f"{broker} - Detailed Breakdown", height=350)

        fig.update_yaxes(tickformat="$,.0f", row=1, col=1)
        fig.update_yaxes(tickformat="$,.0f", row=1, col=2)

        broker_figures[broker] = fig

    return broker_figures


def create_comparison_chart(df_brokers: pd.DataFrame):
    """Create comprehensive comparison chart"""

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=("Values", "Returns", "Cash Flows", "Gains"),
        vertical_spacing=0.15,
        horizontal_spacing=0.12,
    )

    brokers = df_brokers["Broker"].tolist()

    # Values
    fig.add_trace(
        go.Bar(
            name="Starting",
            x=brokers,
            y=df_brokers["Starting Value"],
            marker_color="#3498db",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            name="Ending",
            x=brokers,
            y=df_brokers["Ending Value"],
            marker_color="#2ecc71",
        ),
        row=1,
        col=1,
    )

    # Returns
    returns = df_brokers["Return (%)"].tolist()
    colors = ["#2ecc71" if r >= 0 else "#e74c3c" for r in returns]
    fig.add_trace(
        go.Bar(x=brokers, y=returns, marker_color=colors, showlegend=False),
        row=1,
        col=2,
    )

    # Cash Flows
    fig.add_trace(
        go.Bar(
            name="Deposits", x=brokers, y=df_brokers["Deposits"], marker_color="#2ecc71"
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            name="Withdrawals",
            x=brokers,
            y=df_brokers["Withdrawals"],
            marker_color="#e74c3c",
        ),
        row=2,
        col=1,
    )

    # Gains
    fig.add_trace(
        go.Bar(
            name="Realised",
            x=brokers,
            y=df_brokers["Realised Gains"],
            marker_color="#3498db",
        ),
        row=2,
        col=2,
    )
    fig.add_trace(
        go.Bar(
            name="Unrealised",
            x=brokers,
            y=df_brokers["Unrealised Gains"],
            marker_color="#9b59b6",
        ),
        row=2,
        col=2,
    )

    fig.update_yaxes(tickformat="$,.0f", row=1, col=1)
    fig.update_yaxes(tickformat="$,.0f", row=2, col=1)
    fig.update_yaxes(tickformat="$,.0f", row=2, col=2)

    fig.update_layout(height=700, barmode="group")

    return fig
