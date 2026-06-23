"""Per-date worker job assignments (one row per worker per day)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pytz
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, JobSite, Client, WorkerAssignment, Timesheet, TimesheetEntry

MELBOURNE_TZ = pytz.timezone("Australia/Melbourne")


def melbourne_today() -> date:
    return datetime.now(MELBOURNE_TZ).date()


def assignment_to_dict(row: WorkerAssignment, job_site: JobSite, client_name: Optional[str] = None) -> dict:
    return {
        "id": row.id,
        "job_site_id": job_site.id,
        "job_site_name": job_site.name,
        "job_site_address": job_site.address or "",
        "job_site_latitude": job_site.latitude,
        "job_site_longitude": job_site.longitude,
        "client_name": client_name,
        "assignment_date": row.assignment_date.isoformat() if row.assignment_date else None,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "contact_name": row.contact_name or job_site.contact_name,
        "contact_phone": row.contact_phone or job_site.contact_phone,
        "accepted": row.accepted,
        "assigned_at": row.assigned_at.isoformat() if row.assigned_at else None,
    }


async def load_assignments_map(
    db: AsyncSession,
    worker_ids: List[int],
) -> Dict[int, List[dict]]:
    """All assignments for the given workers, keyed by worker_id."""
    if not worker_ids:
        return {}
    rows = (await db.execute(
        select(WorkerAssignment, JobSite, Client.name)
        .join(JobSite, WorkerAssignment.job_site_id == JobSite.id)
        .outerjoin(Client, JobSite.client_id == Client.id)
        .where(WorkerAssignment.worker_id.in_(worker_ids))
        .order_by(WorkerAssignment.assignment_date, WorkerAssignment.id)
    )).all()
    out: Dict[int, List[dict]] = {wid: [] for wid in worker_ids}
    for wa, js, client_name in rows:
        out.setdefault(wa.worker_id, []).append(assignment_to_dict(wa, js, client_name))
    return out


async def sync_user_legacy_fields(db: AsyncSession, worker: User) -> None:
    """Mirror the earliest assignment from today onward onto User.* for legacy code."""
    today = melbourne_today()
    row = (await db.execute(
        select(WorkerAssignment)
        .where(
            WorkerAssignment.worker_id == worker.id,
            WorkerAssignment.assignment_date >= today,
        )
        .order_by(WorkerAssignment.assignment_date)
        .limit(1)
    )).scalar_one_or_none()

    if row:
        worker.assigned_job_site_id = row.job_site_id
        worker.assignment_date = row.assignment_date
        worker.assignment_start_time = row.start_time
        worker.assignment_end_time = row.end_time
        worker.assignment_contact_name = row.contact_name
        worker.assignment_contact_phone = row.contact_phone
        worker.assignment_accepted = row.accepted
        worker.assigned_at = row.assigned_at
    else:
        worker.assigned_job_site_id = None
        worker.assignment_date = None
        worker.assignment_start_time = None
        worker.assignment_end_time = None
        worker.assignment_contact_name = None
        worker.assignment_contact_phone = None
        worker.assignment_accepted = None
        worker.assigned_at = None


async def upsert_assignment(
    db: AsyncSession,
    worker: User,
    *,
    job_site_id: int,
    assignment_date: date,
    start_time: Optional[str],
    end_time: Optional[str],
    contact_name: Optional[str],
    contact_phone: Optional[str],
    reset_acceptance: bool = True,
) -> WorkerAssignment:
    existing = (await db.execute(
        select(WorkerAssignment).where(
            WorkerAssignment.worker_id == worker.id,
            WorkerAssignment.assignment_date == assignment_date,
        )
    )).scalar_one_or_none()

    if existing:
        existing.job_site_id = job_site_id
        existing.start_time = start_time
        existing.end_time = end_time
        existing.contact_name = (contact_name or "").strip() or None
        existing.contact_phone = (contact_phone or "").strip() or None
        if reset_acceptance:
            existing.accepted = None
        existing.assigned_at = datetime.utcnow()
        row = existing
    else:
        row = WorkerAssignment(
            worker_id=worker.id,
            job_site_id=job_site_id,
            assignment_date=assignment_date,
            start_time=start_time,
            end_time=end_time,
            contact_name=(contact_name or "").strip() or None,
            contact_phone=(contact_phone or "").strip() or None,
            accepted=None,
            assigned_at=datetime.utcnow(),
        )
        db.add(row)

    await sync_user_legacy_fields(db, worker)
    return row


async def delete_assignment(
    db: AsyncSession,
    worker: User,
    assignment_date: Optional[date] = None,
) -> None:
    """Delete one day's assignment, or all assignments if no date given."""
    q = delete(WorkerAssignment).where(WorkerAssignment.worker_id == worker.id)
    if assignment_date is not None:
        q = q.where(WorkerAssignment.assignment_date == assignment_date)
    await db.execute(q)
    await sync_user_legacy_fields(db, worker)


async def get_current_clock_job(db: AsyncSession, worker_id: int) -> Optional[dict]:
    today = melbourne_today()
    yesterday = today - timedelta(days=1)

    active_row = (await db.execute(
        select(TimesheetEntry, JobSite)
        .join(Timesheet, TimesheetEntry.timesheet_id == Timesheet.id)
        .outerjoin(JobSite, TimesheetEntry.job_site_id == JobSite.id)
        .where(
            Timesheet.worker_id == worker_id,
            TimesheetEntry.entry_date.in_([today, yesterday]),
            TimesheetEntry.clock_in_time.isnot(None),
            TimesheetEntry.clock_out_time.is_(None),
        )
        .limit(1)
    )).first()

    if not active_row:
        return None

    entry, js = active_row
    site_name = js.name if js else (entry.clock_in_address or "On site")
    return {
        "job_site_id": js.id if js else entry.job_site_id,
        "job_site_name": site_name,
        "job_site_address": js.address if js else entry.clock_in_address,
        "job_site_latitude": js.latitude if js else entry.clock_in_latitude,
        "job_site_longitude": js.longitude if js else entry.clock_in_longitude,
        "assignment_date": entry.entry_date.isoformat() if entry.entry_date else today.isoformat(),
        "start_time": entry.clock_in_time.strftime("%H:%M") if entry.clock_in_time else None,
        "assigned_at": None,
        "accepted": True,
        "is_current": True,
    }


def _format_assignment_day_label(assignment_date: Optional[str]) -> str:
    if not assignment_date:
        return "TBC"
    try:
        d = date.fromisoformat(assignment_date)
        return d.strftime("%a %d %b")
    except ValueError:
        return assignment_date


def _job_status_label(job: dict, *, today_iso: str) -> str:
    if job.get("is_current"):
        return "On site now"
    if job.get("accepted") is True:
        return "Accepted"
    if job.get("accepted") is False:
        return "Declined"
    return "Pending"


def _build_legacy_assignment_card(
    pending: Optional[dict],
    upcoming_jobs: List[dict],
    current_job: Optional[dict],
    today: date,
) -> Optional[dict]:
    """Old app builds only read `assignment` and render a single card.

    List every allocated day in that card so staff still see accepted jobs
    until they receive an OTA / new TestFlight build with stacked cards.
    """
    today_iso = today.isoformat()
    all_jobs: List[dict] = []
    if current_job:
        all_jobs.append(current_job)
    for job in upcoming_jobs:
        if current_job and job.get("assignment_date") == current_job.get("assignment_date") and job.get("job_site_id") == current_job.get("job_site_id"):
            continue
        all_jobs.append(job)

    if not all_jobs:
        return pending

    tomorrow_iso = (today + timedelta(days=1)).isoformat()
    tomorrow_job = next((j for j in all_jobs if j.get("assignment_date") == tomorrow_iso), None)
    # Headline the next shift (tomorrow) so today's row doesn't look like the only job.
    primary = pending or tomorrow_job or all_jobs[-1]
    card = dict(primary)

    summary_lines: List[str] = []
    for job in all_jobs:
        day = _format_assignment_day_label(job.get("assignment_date"))
        time_str = f" {job['start_time']}" if job.get("start_time") else ""
        status = _job_status_label(job, today_iso=today_iso)
        prefix = "✓" if job.get("accepted") is True or job.get("is_current") else ("✗" if job.get("accepted") is False else "⏳")
        site = job.get("job_site_name") or "Job"
        summary_lines.append(f"{prefix} {day}{time_str} — {site} ({status})")

    base_address = (primary.get("job_site_address") or "").strip()
    card["job_site_address"] = base_address + ("\n\n" if base_address else "") + "\n".join(summary_lines)
    card["other_jobs"] = [j for j in all_jobs if j.get("assignment_date") != primary.get("assignment_date")]
    return card


async def get_mobile_assignments(db: AsyncSession, worker_id: int) -> dict:
    """Build current_job + upcoming_jobs for the mobile app."""
    today = melbourne_today()
    current_job = await get_current_clock_job(db, worker_id)

    rows = (await db.execute(
        select(WorkerAssignment, JobSite)
        .join(JobSite, WorkerAssignment.job_site_id == JobSite.id)
        .where(
            WorkerAssignment.worker_id == worker_id,
            WorkerAssignment.assignment_date >= today,
        )
        .order_by(WorkerAssignment.assignment_date)
    )).all()

    upcoming_jobs = []
    for wa, js in rows:
        payload = assignment_to_dict(wa, js)
        is_duplicate = (
            current_job
            and current_job.get("job_site_id") == payload["job_site_id"]
            and wa.assignment_date == today
            and wa.accepted is True
        )
        if not is_duplicate:
            upcoming_jobs.append(payload)

    pending = next((j for j in upcoming_jobs if j.get("accepted") is None), None)
    if not pending:
        pending = upcoming_jobs[0] if upcoming_jobs else None

    # Full list for mobile clients (current + all upcoming days)
    all_assignments = list(upcoming_jobs)
    if current_job:
        all_assignments.insert(0, current_job)

    legacy_assignment = _build_legacy_assignment_card(pending, upcoming_jobs, current_job, today)

    return {
        "current_job": current_job,
        "upcoming_jobs": upcoming_jobs,
        "assignments": all_assignments,
        "jobs": all_assignments,
        # Backward compat for older app builds — single card listing every day
        "assignment": legacy_assignment,
    }
