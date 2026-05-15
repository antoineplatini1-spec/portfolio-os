"""
Agent macro hebdomadaire — détermine le cadre stratégique dans lequel
opèrent les agents tactiques (Bull/Bear/Arbitre).

Analyse :
  - Régime SPY (au-dessus/en-dessous EMA200)
  - Performance relative des secteurs ETF vs SPY sur 20 jours
  - Niveau de peur (VIX)
  - Consensus : secteurs autorisés + paramètres dynamiques
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd


# Mapping ETF → secteur (doit correspondre aux valeurs de SECTOR_MAP)
SECTOR_ETFS = {
    "XLK":  "Tech",
    "SMH":  "Semi",
    "XLF":  "Finance",
    "XLE":  "Energie",
    "XLV":  "Santé",
    "XLI":  "Industrie",
    "XLY":  "Conso",
    "XLP":  "ConsoBase",
    "XLB":  "Materiaux",
    "XLRE": "REIT",
    "XLU":  "Utilities",
    "GLD":  "Macro",
    "TLT":  "Macro",
}

OUTPERFORM_THRESHOLD = 2.0   # % de surperformance vs SPY sur 20j pour être "autorisé"
LOOKBACK_DAYS        = 20    # fenêtre de performance relative


@dataclass
class MacroContext:
    date: str
    regime: str                          # "BULL" | "BEAR" | "NEUTRAL"
    spy_vs_ema200_pct: float             # % au-dessus/en-dessous EMA200
    vix_level: float                     # niveau VIX (0 si indisponible)
    vix_regime: str                      # "LOW" <20 | "MEDIUM" 20-30 | "HIGH" >30
    top_sectors: list[str]               # secteurs surperformants SPY (20j)
    allowed_sectors: Optional[list[str]] # None = tous autorisés
    max_trades_per_day: int              # 1 BEAR | 2 NEUTRAL | 3 BULL
    min_net_score: int                   # seuil arbitre dynamique : 30 BEAR | 20 NEUTRAL | 10 BULL
    sector_perf: dict[str, float]        # {sector: relative_perf_%}
    rationale: str                       # texte lisible

    def format_log(self) -> list[str]:
        lines = [
            "══════════════════════════════════════════════",
            f"  AGENT MACRO — {self.date}",
            "══════════════════════════════════════════════",
            f"  Régime marché  : {self.regime}",
            f"  SPY vs EMA200  : {self.spy_vs_ema200_pct:+.1f}%",
            f"  VIX            : {self.vix_level:.1f} ({self.vix_regime})",
            f"  Max trades/j   : {self.max_trades_per_day}",
            f"  Seuil net min  : {self.min_net_score}",
        ]
        if self.top_sectors:
            lines.append(f"  Top secteurs   : {', '.join(self.top_sectors)}")
        if self.allowed_sectors is not None:
            lines.append(f"  Secteurs auth. : {', '.join(self.allowed_sectors)}")
        else:
            lines.append(  "  Secteurs auth. : TOUS (régime favorable)")
        lines.append(f"  Rationale      : {self.rationale}")
        lines.append("══════════════════════════════════════════════")
        return lines


class MacroAgent:
    """
    Analyse le contexte macro et produit un MacroContext utilisé pour
    contraindre les agents tactiques (secteurs autorisés, seuils, volume).

    Fonctionne en deux modes :
      - Live : télécharge les données via yfinance
      - Backtest : reçoit data_override = dict {ticker: DataFrame}
    """

    def analyze(
        self,
        as_of_date: Optional[datetime] = None,
        data_override: Optional[dict[str, pd.DataFrame]] = None,
        newsletter_signal: Optional[object] = None,   # NewsletterSignal
    ) -> MacroContext:
        """
        Lance l'analyse macro.

        Args:
            as_of_date  : date de référence (None = aujourd'hui)
            data_override: données pré-chargées pour le backtest (évite les téléchargements)
        """
        as_of = as_of_date or datetime.now()
        date_str = as_of.strftime("%Y-%m-%d")

        spy_df = self._get_data("SPY", as_of, data_override)
        vix_df = self._get_data("^VIX", as_of, data_override)

        # ── Régime SPY ────────────────────────────────────────────────
        regime, spy_vs_ema200 = self._spy_regime(spy_df, as_of)

        # ── VIX ───────────────────────────────────────────────────────
        vix_level, vix_regime = self._vix_level(vix_df, as_of)

        # ── Performance sectorielle relative ──────────────────────────
        sector_perf: dict[str, float] = {}
        for etf, sector in SECTOR_ETFS.items():
            etf_df = self._get_data(etf, as_of, data_override)
            rel = self._relative_perf(etf_df, spy_df, as_of, LOOKBACK_DAYS)
            if rel is not None:
                # Si plusieurs ETF dans même secteur → prendre le max
                if sector not in sector_perf or rel > sector_perf[sector]:
                    sector_perf[sector] = round(rel, 2)

        top_sectors = [s for s, p in sector_perf.items() if p >= OUTPERFORM_THRESHOLD]
        top_sectors.sort(key=lambda s: -sector_perf.get(s, 0))

        # ── Overlay newsletter ────────────────────────────────────────
        if newsletter_signal is not None and newsletter_signal.source != "none":
            for sector, bias in newsletter_signal.sector_bias.items():
                # Le biais newsletter ajuste la perf relative (1 unité = 2%)
                current = sector_perf.get(sector, 0.0)
                sector_perf[sector] = round(current + bias * 2.0, 2)
            # Recalculer top_sectors avec le biais newsletter
            top_sectors = [s for s, p in sector_perf.items() if p >= OUTPERFORM_THRESHOLD]
            top_sectors.sort(key=lambda s: -sector_perf.get(s, 0))
            # CAC40 bearish → durcir seulement si SPY est déjà proche de sa EMA200
            # (évite d'écraser un régime BULL US clairement haussier avec une newsletter FR)
            if newsletter_signal.cac40_sentiment == "BEARISH" and abs(spy_vs_ema200) < 5.0:
                regime = regime if regime == "BEAR" else ("NEUTRAL" if regime == "BULL" else "BEAR")

        # ── Paramètres dynamiques selon le régime ─────────────────────
        if regime == "BEAR":
            max_trades   = 1
            min_net      = 30
            # En BEAR : seulement les secteurs qui surperforment SPY
            allowed      = top_sectors if top_sectors else None
            rationale    = (
                f"Marché baissier (SPY {spy_vs_ema200:+.1f}% vs EMA200). "
                f"Restriction aux secteurs résilients : {', '.join(top_sectors) if top_sectors else 'aucun identifié — cash préférable'}."
            )
        elif regime == "NEUTRAL":
            max_trades   = 2
            min_net      = 20
            allowed      = None  # tous autorisés
            rationale    = (
                f"Marché incertain (SPY {spy_vs_ema200:+.1f}% vs EMA200). "
                f"Sélectivité accrue ({max_trades} trades/j max, net ≥ {min_net})."
            )
        else:  # BULL
            max_trades   = 3
            min_net      = 10
            allowed      = None
            rationale    = (
                f"Marché haussier (SPY {spy_vs_ema200:+.1f}% vs EMA200). "
                f"Exposition maximale autorisée."
            )

        # VIX élevé → toujours réduire
        if vix_regime == "HIGH":
            max_trades = max(1, max_trades - 1)
            min_net    = min_net + 10
            rationale += f" VIX élevé ({vix_level:.0f}) → seuils durcis."

        return MacroContext(
            date              = date_str,
            regime            = regime,
            spy_vs_ema200_pct = round(spy_vs_ema200, 2),
            vix_level         = vix_level,
            vix_regime        = vix_regime,
            top_sectors       = top_sectors,
            allowed_sectors   = allowed,
            max_trades_per_day= max_trades,
            min_net_score     = min_net,
            sector_perf       = sector_perf,
            rationale         = rationale,
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_data(
        self,
        ticker: str,
        as_of: datetime,
        data_override: Optional[dict],
    ) -> Optional[pd.DataFrame]:
        """Récupère les données : override (backtest) ou yfinance (live)."""
        if data_override is not None:
            df = data_override.get(ticker)
            if df is not None:
                # Filtrer jusqu'à as_of
                df = df[df.index <= pd.Timestamp(as_of)]
            return df

        # Mode live : télécharger les 12 derniers mois
        try:
            import yfinance as yf
            start = (as_of - timedelta(days=365)).strftime("%Y-%m-%d")
            end   = (as_of + timedelta(days=1)).strftime("%Y-%m-%d")
            df = yf.download(ticker, start=start, end=end,
                             interval="1d", auto_adjust=True, progress=False)
            if df.empty:
                return None
            df.index = pd.to_datetime(df.index).tz_localize(None)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except Exception:
            return None

    def _spy_regime(
        self, spy_df: Optional[pd.DataFrame], as_of: datetime
    ) -> tuple[str, float]:
        """Retourne (régime, % vs EMA200)."""
        if spy_df is None or spy_df.empty or len(spy_df) < 200:
            return "NEUTRAL", 0.0
        close  = float(spy_df["Close"].iloc[-1])
        ema200 = spy_df["Close"].ewm(span=200, adjust=False).mean().iloc[-1]
        pct    = (close - float(ema200)) / float(ema200) * 100
        if pct > 1.0:
            return "BULL", pct
        elif pct < -1.0:
            return "BEAR", pct
        else:
            return "NEUTRAL", pct

    def _vix_level(
        self, vix_df: Optional[pd.DataFrame], as_of: datetime
    ) -> tuple[float, str]:
        """Retourne (niveau VIX, régime)."""
        if vix_df is None or vix_df.empty:
            return 0.0, "UNKNOWN"
        col   = "Close" if "Close" in vix_df.columns else vix_df.columns[0]
        level = float(vix_df[col].iloc[-1])
        if level < 20:
            return level, "LOW"
        elif level < 30:
            return level, "MEDIUM"
        else:
            return level, "HIGH"

    def _relative_perf(
        self,
        etf_df: Optional[pd.DataFrame],
        spy_df: Optional[pd.DataFrame],
        as_of: datetime,
        days: int,
    ) -> Optional[float]:
        """Performance relative ETF vs SPY sur `days` jours."""
        if etf_df is None or spy_df is None:
            return None
        if len(etf_df) < days + 1 or len(spy_df) < days + 1:
            return None
        def perf(df):
            c = df["Close"].dropna()
            if len(c) < days + 1:
                return None
            return (float(c.iloc[-1]) - float(c.iloc[-days - 1])) / float(c.iloc[-days - 1]) * 100
        etf_p = perf(etf_df)
        spy_p = perf(spy_df)
        if etf_p is None or spy_p is None:
            return None
        return etf_p - spy_p
