#!/usr/bin/env python3
"""Compare worker_assignments DB state vs get_mobile_assignments API for a date."""
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

TARGET = os.environ.get("TARGET_DATE", "2026-06-24")


async def main():
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import User, WorkerAssignment
    from app.services.assignment_helpers import get_mobile_assignments

    target = date.fromisoformat(TARGET)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(User.id, User.first_name, User.surname, WorkerAssignment.accepted)
            .join(WorkerAssignment, WorkerAssignment.worker_id == User.id)
            .where(WorkerAssignment.assignment_date == target, User.is_active == True)
            .order_by(User.first_name)
        )).all()

        mismatches = []
        ok = 0
        print(f"Target date: {target.isoformat()}")
        print(f"{'Worker':<28} {'DB':<10} {'App API':<10} Match")
        print("-" * 58)
        for uid, fn, sn, db_acc in rows:
            mobile = await get_mobile_assignments(db, uid)
            jobs = mobile.get("upcoming_jobs") or mobile.get("assignments") or []
            tomorrow = next(
                (j for j in jobs if j.get("assignment_date") == target.isoformat()),
                None,
            )
            app_acc = tomorrow.get("accepted") if tomorrow else "MISSING"
            db_label = "Yes" if db_acc is True else ("No" if db_acc is False else "Pending")
            if app_acc is True:
                app_label = "Yes"
            elif app_acc is False:
                app_label = "No"
            elif app_acc is None:
                app_label = "Pending"
            else:
                app_label = str(app_acc)
            match = db_acc == app_acc
            if match:
                ok += 1
            else:
                mismatches.append((f"{fn} {sn}", db_label, app_label))
            print(f"{fn} {sn:<22} {db_label:<10} {app_label:<10} {'OK' if match else 'MISMATCH'}")

        print("-" * 58)
        accepted = sum(1 for r in rows if r[3] is True)
        pending = sum(1 for r in rows if r[3] is None)
        declined = sum(1 for r in rows if r[3] is False)
        print(
            f"Allocated: {len(rows)} | Accepted: {accepted} | "
            f"Pending: {pending} | Declined: {declined}"
        )
        print(f"App API matches DB: {ok}/{len(rows)}")
        if mismatches:
            print("Mismatches:")
            for m in mismatches:
                print(f"  - {m[0]}: DB={m[1]}, App={m[2]}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
