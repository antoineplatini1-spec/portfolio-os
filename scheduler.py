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


def start():
    """Démarre le scheduler en arrière-plan (à appeler une seule fois au boot)."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="America/New_York")
    _scheduler.add_job(
        _job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=30),
        id="daily_scan",
        replace_existing=True,
        misfire_grace_time=3600,   # si le serveur redémarre, tolère 1h de retard
    )
    _scheduler.start()
    logger.info("[scheduler] Démarré — scan quotidien lun-ven 9h30 ET")


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
