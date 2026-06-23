"""Helpers for per-day timesheet approval and admin display status."""

from __future__ import annotations

from typing import Iterable, Optional

from ..models import Timesheet, TimesheetEntry, TimesheetStatus


def summarize_entries(entries: Iterable[TimesheetEntry]) -> dict:
    """Summarise day-entry states for admin list views."""
    entries = list(entries)
    approved = sum(1 for e in entries if e.entry_status == "approved")
    submitted = sum(1 for e in entries if e.entry_status == "submitted")
    rejected = sum(1 for e in entries if e.entry_status == "rejected")
    draft = sum(1 for e in entries if (e.entry_status or "draft") == "draft")
    clocked_not_out = sum(
        1 for e in entries
        if (e.entry_status or "draft") == "draft" and e.clock_in_time and not e.clock_out_time
    )
    clocked_not_sent = sum(
        1 for e in entries
        if (e.entry_status or "draft") == "draft" and e.clock_out_time
    )
    total = len(entries)

    if submitted > 0:
        display_status = "submitted"
    elif total > 0 and approved == total:
        display_status = "approved"
    elif clocked_not_out > 0:
        display_status = "in_progress"
    elif clocked_not_sent > 0:
        display_status = "not_submitted"
    elif approved > 0 and approved < total:
        display_status = "partial"
    elif rejected > 0:
        display_status = "rejected"
    else:
        display_status = "draft"

    parts = []
    for e in sorted(entries, key=lambda x: x.entry_date):
        st = e.entry_status or "draft"
        if st == "approved":
            mark = "✓"
        elif st == "submitted":
            mark = "?"
        elif e.clock_in_time and not e.clock_out_time:
            mark = "●"
        elif e.clock_out_time:
            mark = "!"
        else:
            mark = "-"
        parts.append(f"{e.day_of_week[:3]} {mark}")

    return {
        "total_entries_count": total,
        "approved_entries_count": approved,
        "submitted_entries_count": submitted,
        "draft_entries_count": draft,
        "rejected_entries_count": rejected,
        "clocked_in_count": clocked_not_out,
        "display_status": display_status,
        "entries_summary": " · ".join(parts),
        "approved_hours": round(
            sum((e.total_hours or 0) for e in entries if e.entry_status == "approved"), 2
        ),
    }


def sync_timesheet_status(timesheet: Timesheet, entries: Iterable[TimesheetEntry]) -> None:
    """Keep stored timesheet.status aligned with per-day entry approval."""
    summary = summarize_entries(entries)
    display = summary["display_status"]

    if display == "approved":
        timesheet.status = TimesheetStatus.APPROVED
    elif display == "submitted":
        timesheet.status = TimesheetStatus.SUBMITTED
    elif display == "rejected" and summary["approved_entries_count"] == 0:
        timesheet.status = TimesheetStatus.REJECTED
    else:
        # draft, not_submitted, in_progress, partial — still open for the week
        if timesheet.status == TimesheetStatus.APPROVED:
            timesheet.status = TimesheetStatus.DRAFT
        elif timesheet.status == TimesheetStatus.REJECTED and summary["approved_entries_count"] > 0:
            timesheet.status = TimesheetStatus.SUBMITTED


def display_status_label(status: str) -> str:
    labels = {
        "draft": "Draft",
        "submitted": "Pending Approval",
        "approved": "Approved",
        "rejected": "Rejected",
        "not_submitted": "Not Submitted",
        "in_progress": "On Site",
        "partial": "Partial",
    }
    return labels.get(status, status.replace("_", " ").title())


def matches_admin_status_filter(display_status: str, status_filter: Optional[str]) -> bool:
    if not status_filter:
        return True
    if status_filter == "submitted":
        return display_status in ("submitted", "partial")
    if status_filter == "not_submitted":
        return display_status in ("not_submitted", "in_progress", "draft")
    if status_filter == "approved":
        return display_status == "approved"
    if status_filter == "rejected":
        return display_status == "rejected"
    return display_status == status_filter
