"""Lance le backtest 2022 (bear market) et affiche les resultats."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from datetime import date
from backtest.engine import BacktestEngine
from config import DEFAULT_WATCHLIST

SEP = "-" * 50

print("=" * 60)
print("BACKTEST 2022 -- Bear Market (SPY -18%)")
print("Capital : 10 000 EUR  |  Score min : 45")
print("=" * 60)

engine = BacktestEngine(
    tickers=DEFAULT_WATCHLIST,
    start=date(2022, 1, 3),
    end=date(2022, 12, 30),
    initial_cash=10_000.0,
    min_score=45,
)

print("\n[1/3] Chargement des donnees...")
errors = engine.load_data()
print(f"  {len(engine._data)} tickers charges, {len(errors)} erreurs")
print(f"  {len(engine._trading_days)} jours de trading")

print("\n[2/3] Simulation...")
n = len(engine._trading_days)
for i, day in enumerate(engine._trading_days):
    if i % 20 == 0:
        pct = i / n * 100
        print(f"  {pct:.0f}%  {day}...", end="\r")
    engine._refresh_weekly_budget(day)
    engine._process_fixed_allocations(day)
    engine._update_positions(day)
    engine._open_signals(day)
    engine._record_snapshot(day)

engine.close_all_at_end()
print("\n  100% -- Simulation terminee")

print("\n[3/3] Resultats :")
stats = engine.stats()

print(f"\n  {SEP}")
print(f"  Capital initial    : 10 000.00 EUR")
print(f"  Capital final      : {stats['final_value']:,.2f} EUR")
print(f"  PnL net            : {stats['total_pnl']:+,.2f} EUR ({stats['total_pnl_pct']:+.2f}%)")
print(f"  Rend. annualise    : {stats.get('annualized_return', 0):+.2f}%")
print(f"  {SEP}")
print(f"  Sharpe             : {stats['sharpe']:.2f}")
print(f"  Max Drawdown       : {stats['max_drawdown_pct']:.1f}%")
print(f"  Volatilite         : {stats.get('volatility', 0):.1f}%")
print(f"  Calmar             : {stats.get('calmar', 0):.2f}")
print(f"  {SEP}")
print(f"  Trades             : {stats['total_trades']}")
print(f"  Win rate           : {stats['win_rate']:.1f}%")
print(f"  Profit factor      : {stats['profit_factor']:.2f}")
print(f"  Gain moyen         : {stats['avg_win']:+.2f} EUR")
print(f"  Perte moyenne      : {stats['avg_loss']:+.2f} EUR")
print(f"  Duree moy.         : {stats.get('avg_holding_days', 0):.0f} jours")
print(f"  {SEP}")

print("\n  Rendements mensuels :")
for month, ret in stats.get("monthly_returns", {}).items():
    bar = "#" * int(abs(ret) / 2) if abs(ret) >= 1 else ""
    sign = "+" if ret >= 0 else ""
    arrow = "^" if ret >= 0 else "v"
    print(f"  {month}  {arrow} {sign}{ret:5.1f}%  {bar}")

print(f"\n  {SEP}")
print(f"  SPY 2022 (benchmark) : -18.1%")
print(f"  Surperformance       : {stats['total_pnl_pct'] - (-18.1):+.1f}%")

if stats['total_trades'] > 0:
    print(f"\n  Top 3 gains :")
    sorted_trades = sorted(engine.trades, key=lambda t: -t.pnl)
    for t in sorted_trades[:3]:
        print(f"    {t.ticker:8s} {t.entry_date} -> {t.exit_date}  {t.pnl:+.2f}EUR  [{t.reason}]")
    print(f"\n  Top 3 pertes :")
    for t in sorted_trades[-3:]:
        print(f"    {t.ticker:8s} {t.entry_date} -> {t.exit_date}  {t.pnl:+.2f}EUR  [{t.reason}]")
