#!/usr/bin/env python3
"""Manual/local trigger for the daily synthetic-data pipeline
(`sephiroth.safety.synthetic_daily`) -- the same logic `POST
/internal/simulate-day` runs from an external cron, callable directly
against whichever `DATABASE_URL` is in `.env` (Supabase or local Postgres).

Usage:
    PYTHONPATH=.:platform .venv/bin/python scripts/simulate_daily.py [--dry-run] [--force]
"""

import argparse
import asyncio
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "platform")

from core.db import SessionLocal
from sephiroth.safety.synthetic_daily import run_daily_simulation


async def main(dry_run: bool, force: bool) -> None:
    async with SessionLocal() as session:
        summary = await run_daily_simulation(session, force=force, dry_run=dry_run)
        print(summary.to_dict())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change, write nothing")
    parser.add_argument("--force", action="store_true", help="Run even if today's run already completed")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run, args.force))
