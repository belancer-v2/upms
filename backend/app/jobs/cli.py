"""Command line for cron (cPanel) hosting.

    python -m app.jobs.cli run-due        run every job that is due, once, then exit (cron every minute or every 5 minutes)
    python -m app.jobs.cli run <name>     run one job now (ignores its schedule, still takes the DB lock)
    python -m app.jobs.cli list           print job names and schedules

One JSON log line per job on stdout. Exit code 0 when every job that ran finished ok/warn and nothing was misconfigured,
1 when any job failed, 2 on a usage error. Overlapping cron runs are safe: the DB lock lets exactly one run a given job.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def _line(r: dict) -> None:
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **{k: r.get(k) for k in ("name", "status", "result", "error")}}, default=str, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    from .runner import JOBS, run_due_jobs, run_job
    from . import tasks  # noqa: F401
    if not argv or argv[0] not in ("run-due", "run", "list"):
        print(__doc__, file=sys.stderr)
        return 2
    if argv[0] == "list":
        for j in JOBS.values():
            print(f"{j.name:20s} {j.schedule.label():22s} {j.title}")
        return 0
    if argv[0] == "run":
        if len(argv) != 2 or argv[1] not in JOBS:
            print("usage: run <name>; names: " + ", ".join(JOBS), file=sys.stderr)
            return 2
        r = run_job(argv[1], trigger="manual")
        _line(r or {"name": argv[1], "status": "locked"})
        return 1 if r and r["status"] == "failed" else 0
    results = run_due_jobs()
    for r in results:
        _line(r)
    return 1 if any(r["status"] == "failed" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
