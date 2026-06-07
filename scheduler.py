"""
Scheduler in-process (APScheduler).
Utilisé sur Railway / cloud pour remplacer le Task Scheduler Windows.
Lance daily_auto.run() chaque jour de semaine à 9h30 ET (New York).
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _job():
    try:
        import daily_auto
        daily_auto.run()
    except Exception as e:
        logger.error(f"[scheduler] Erreur daily_auto : {e}", exc_info=True)


def _intraday_sl_check():
    """Vérifie les SL/TP en cours de séance et ferme immédiatement si atteint."""
    try:
        from portfolio.manager import PortfolioManager
        from data.fetcher import fetch_ohlcv

        pm = PortfolioManager()
        open_pos = pm.open_positions
        if not open_pos:
            return

        prices = {}
        for ticker in open_pos:
            try:
                df = fetch_ohlcv(ticker, period="5d", interval="1d", force_refresh=True)
                if not df.empty:
                    prices[ticker] = float(df["Close"].iloc[-1])
            except Exception:
                pass

        if not prices:
            return

        before_cash = pm.cash
        pm.update_prices(prices)
        delta = pm.cash - before_cash
        closed = [t for t in open_pos if t not in pm.open_positions]
        if closed:
            logger.info(f"[intraday SL] Positions fermées : {closed} | cash +{delta:.2f} €")
        else:
            logger.debug("[intraday SL] Aucun SL/TP déclenché")
    except Exception as e:
        logger.error(f"[intraday_sl_check] {e}", exc_info=True)


def start():
    """Démarre le scheduler en arrière-plan (à appeler une seule fois au boot)."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="America/New_York")

    # Scan quotidien 9h30 ET
    _scheduler.add_job(
        _job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=30),
        id="daily_scan",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Surveillance intraday SL/TP — toutes les heures de 10h30 à 15h30 ET
    _scheduler.add_job(
        _intraday_sl_check,
        CronTrigger(day_of_week="mon-fri", hour="10,11,12,13,14,15", minute=30),
        id="intraday_sl",
        replace_existing=True,
        misfire_grace_time=600,
    )

    _scheduler.start()
    logger.info("[scheduler] Démarré — scan 9h30 ET + surveillance SL 10h30-15h30 ET")


def stop():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] Arrêté")


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def next_run() -> str:
    if _scheduler is None:
        return "non démarré"
    job = _scheduler.get_job("daily_scan")
    if job and job.next_run_time:
        return job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")
    return "inconnu"
