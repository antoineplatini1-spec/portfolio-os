"""Graphiques Plotly : prix + indicateurs + niveaux TP/SL."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from portfolio.position import Position
from utils.fees import break_even_price


def build_price_chart(
    df: pd.DataFrame,
    ticker: str,
    position: Position | None = None,
    show_ema: bool = True,
    show_bb: bool = True,
    show_vwap: bool = True,
    show_fib: bool = False,
) -> go.Figure:
    """Graphique principal : chandeliers + indicateurs + niveaux."""

    rows = 4
    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        row_heights=[0.50, 0.17, 0.17, 0.16],
        vertical_spacing=0.03,
        subplot_titles=("Prix", "RSI", "MACD", "Volume"),
    )

    # ── Chandeliers ───────────────────────────────────────────────
    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"], name=ticker,
            increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        ),
        row=1, col=1,
    )

    # ── EMA ───────────────────────────────────────────────────────
    if show_ema:
        for period, color in [(20, "#ffb300"), (50, "#29b6f6"), (200, "#ab47bc")]:
            col = f"EMA{period}"
            if col in df.columns:
                fig.add_trace(
                    go.Scatter(x=df.index, y=df[col], name=f"EMA{period}",
                               line=dict(color=color, width=1.2), opacity=0.8),
                    row=1, col=1,
                )

    # ── Bollinger ─────────────────────────────────────────────────
    if show_bb and "BB_upper" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["BB_upper"], name="BB sup",
                       line=dict(color="#546e7a", width=1, dash="dot"), opacity=0.6),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=df["BB_lower"], name="BB inf",
                       fill="tonexty", fillcolor="rgba(84,110,122,0.08)",
                       line=dict(color="#546e7a", width=1, dash="dot"), opacity=0.6),
            row=1, col=1,
        )

    # ── VWAP ──────────────────────────────────────────────────────
    if show_vwap and "VWAP" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["VWAP"], name="VWAP",
                       line=dict(color="#ff7043", width=1.5, dash="dash"), opacity=0.9),
            row=1, col=1,
        )

    # ── Fibonacci ─────────────────────────────────────────────────
    if show_fib:
        fib_cols = [c for c in df.columns if c.startswith("FIB_")]
        fib_colors = {
            "FIB_0": "#ef5350", "FIB_236": "#ff7043", "FIB_382": "#ffb300",
            "FIB_500": "#66bb6a", "FIB_618": "#26a69a", "FIB_786": "#29b6f6",
            "FIB_1000": "#ab47bc",
        }
        for col in fib_cols:
            val = df[col].iloc[-1]
            fig.add_hline(
                y=val, row=1, col=1,
                line=dict(color=fib_colors.get(col, "gray"), width=0.8, dash="dot"),
                annotation_text=col.replace("FIB_", "Fib "),
                annotation_position="right",
            )

    # ── Niveaux position ──────────────────────────────────────────
    if position is not None:
        # Entry
        fig.add_hline(y=position.entry_price, row=1, col=1,
                      line=dict(color="#ffffff", width=1.5),
                      annotation_text="Entrée")
        # Break-even
        be = break_even_price(position.entry_price, position.qty_total)
        fig.add_hline(y=be, row=1, col=1,
                      line=dict(color="#ffb300", width=1, dash="dot"),
                      annotation_text="Break-even")
        # SL
        sl_lvl = position.trailing_stop_price if position.trailing_stop else position.sl
        fig.add_hline(y=sl_lvl, row=1, col=1,
                      line=dict(color="#ef5350", width=1.5, dash="dash"),
                      annotation_text="SL")
        # TP levels
        tp_colors = ["#66bb6a", "#26a69a", "#00bcd4"]
        for i, tp in enumerate(position.tp_levels):
            color = tp_colors[i % len(tp_colors)]
            style = "solid" if not tp.hit else "dot"
            fig.add_hline(y=tp.price, row=1, col=1,
                          line=dict(color=color, width=1.2, dash=style),
                          annotation_text=f"TP{i+1} {'✓' if tp.hit else ''}")

    # ── RSI ───────────────────────────────────────────────────────
    if "RSI" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["RSI"], name="RSI",
                       line=dict(color="#ffb300", width=1.5)),
            row=2, col=1,
        )
        fig.add_hline(y=70, row=2, col=1, line=dict(color="#ef5350", width=0.8, dash="dot"))
        fig.add_hline(y=30, row=2, col=1, line=dict(color="#66bb6a", width=0.8, dash="dot"))
        fig.add_hrect(y0=30, y1=70, row=2, col=1, fillcolor="gray", opacity=0.05)

    # ── MACD ──────────────────────────────────────────────────────
    if "MACD" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["MACD"], name="MACD",
                       line=dict(color="#29b6f6", width=1.2)),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=df["MACD_signal"], name="Signal",
                       line=dict(color="#ff7043", width=1.2)),
            row=3, col=1,
        )
        if "MACD_hist" in df.columns:
            colors = ["#26a69a" if v >= 0 else "#ef5350" for v in df["MACD_hist"]]
            fig.add_trace(
                go.Bar(x=df.index, y=df["MACD_hist"], name="Histogramme",
                       marker_color=colors, opacity=0.6),
                row=3, col=1,
            )

    # ── Volume ────────────────────────────────────────────────────
    vol_colors = [
        "#26a69a" if df["Close"].iloc[i] >= df["Open"].iloc[i] else "#ef5350"
        for i in range(len(df))
    ]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], name="Volume",
               marker_color=vol_colors, opacity=0.7),
        row=4, col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        height=750,
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(l=50, r=50, t=60, b=30),
        title=dict(text=f"<b>{ticker}</b>", x=0.5),
    )
    fig.update_yaxes(row=2, col=1, range=[0, 100])
    return fig
