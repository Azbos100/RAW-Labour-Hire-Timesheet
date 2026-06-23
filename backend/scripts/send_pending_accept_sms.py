#!/usr/bin/env python3
"""One-off: SMS workers who haven't accepted tomorrow's job allocation."""
import asyncio
import os
import re
import sys
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

import psycopg2
from app.services.sms import CONTACT_FOOTER, brand_message, send_sms

TOMORROW = os.environ.get("TARGET_DATE", "2026-06-24")
DATE_LABEL = os.environ.get("TARGET_DATE_LABEL", "Wed 24 Jun")


def db_connect():
    url = os.environ.get("DATABASE_URL", "")
    m = re.search(r"postgresql\+?\w*://([^:]+):([^@]+)@([^:/]+)", url)
    if m:
        user, password, host = m.groups()
        return psycopg2.connect(
            dbname="raw_timesheet", user=user, password=password, host=host
        )
    raise SystemExit("DATABASE_URL not set")


def fetch_pending():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.id, u.first_name, u.surname, u.phone
        FROM worker_assignments wa
        JOIN users u ON u.id = wa.worker_id
        WHERE wa.assignment_date = %s
          AND u.is_active = true
          AND wa.accepted IS DISTINCT FROM true
          AND u.phone IS NOT NULL AND trim(u.phone) <> ''
        ORDER BY u.surname
        """,
        (TOMORROW,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


async def send_all(rows):
    sent = 0
    failed = []
    for wid, first, surname, phone in rows:
        name = (first or "").strip()
        body = (
            f"Hi {name}, RAW Labour Hire still shows your job for {DATE_LABEL} as NOT accepted. "
            f"Why: tapping Accept on the home screen was saving TODAY's job, not tomorrow's — that's fixed now, "
            f"but we still need you to accept {DATE_LABEL}. "
            f"Please: 1) Close & reopen the app 2) Open My Jobs 3) Tap Accept on the {DATE_LABEL} card only. "
            f"{CONTACT_FOOTER}"
        )
        msg = brand_message(body)
        res = await send_sms(
            phone,
            msg,
            recipient_name=f"{first} {surname}".strip(),
            worker_id=wid,
            message_type="custom",
        )
        if res.get("success"):
            sent += 1
            print(f"OK  {first} {surname} ({phone})")
        else:
            failed.append((f"{first} {surname}", res.get("error")))
            print(f"FAIL {first} {surname}: {res.get('error')}")
    return sent, failed


def main():
    rows = fetch_pending()
    print(f"Found {len(rows)} pending workers with phones for {TOMORROW}")
    sent, failed = asyncio.run(send_all(rows))
    print(f"\nDone: sent={sent}, failed={len(failed)}")
    for n, err in failed:
        print(f"  - {n}: {err}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
