"""APScheduler wiring: a publish tick plus one cron job per active campaign."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import service
from .config import get_settings

log = logging.getLogger("postpilot.scheduler")
_scheduler: BackgroundScheduler | None = None


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception:  # a failing job must never kill the scheduler thread
        log.exception("scheduled job failed")


def sync_campaigns() -> int:
    """Rebuild campaign jobs from the database. Returns the number of jobs registered."""
    if _scheduler is None:
        return 0
    for job in _scheduler.get_jobs():
        if job.id.startswith("campaign-"):
            job.remove()
    campaigns = [c for c in service.list_campaigns() if c["active"]]
    for c in campaigns:
        _scheduler.add_job(
            _safe, CronTrigger.from_crontab(c["cron"]), args=[service.run_campaign, c["id"]],
            id=f"campaign-{c['id']}", replace_existing=True, max_instances=1, coalesce=True,
        )
    return len(campaigns)


def start() -> None:
    global _scheduler
    if _scheduler is not None or not get_settings().scheduler_enabled:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_safe, "interval", seconds=30, args=[service.publish_due], id="publish-tick", max_instances=1, coalesce=True)
    _scheduler.start()
    sync_campaigns()


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
