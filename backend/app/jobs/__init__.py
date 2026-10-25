"""Background jobs (P3). A small DB-locked runner, no Celery.

    JOBS_ENABLED=1   start the scheduler loop inside every API worker (the DB lock makes this safe with many workers)
    JOBS_TICK_SECONDS=30   how often the loop looks for due jobs

Job functions live in tasks.py and have the shape fn(db, at) -> dict, so tests call them directly with the time injected.
"""
from .runner import JOBS, run_job, scheduler_running  # noqa: F401
