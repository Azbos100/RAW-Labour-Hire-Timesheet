"""
RAW Labour Hire - Billing / Invoicing API

Replicates the Excel "billing engine" (Client_Billing, Worker_Totals,
MYOB_Payroll) directly off the timesheet data so weekly invoicing and payroll
can be done from the admin page.

Billing week = Saturday -> Friday, labelled by the Friday "week ending" date
(matching the spreadsheet). Hours are derived per day:
  - Mon-Fri: first 8h Ordinary, remainder OT
  - Saturday: all hours -> OT_Sat
  - Sunday:   all hours -> OT_Sun
  - Shift_Type: Night if the day started at/after 6pm, else Day
  - Role: the entry's "worked as" value, defaulting to "Reg"
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date, timedelta
from typing import Optional

from ..database import get_db
from ..models import User, Timesheet, TimesheetEntry, Client, JobSite

router = APIRouter()

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOUR_KEYS = ("ordinary", "ot", "ot_sat", "ot_sun", "total")
MONEY_KEYS = ("charge", "pay")
SUM_KEYS = HOUR_KEYS + MONEY_KEYS


def _zero():
    return {k: 0.0 for k in SUM_KEYS}


def _accumulate(acc, row):
    for k in SUM_KEYS:
        acc[k] = round(acc[k] + (row.get(k) or 0.0), 2)


def _amounts(d: dict, worker, client) -> dict:
    """Dollar amounts for one worker-day.

    Worker pay = ordinary*rate + OT*OT_rate + (Sat+Sun)*weekend_rate
                 + demo_allowance*total_hours + travel_allowance (per day).
    Client charge = same hour buckets at billing rates
                    + travel_charge_per_day + tool_hire_per_day (per day per worker).
    On a Night shift, ordinary hours use the night rate (OT unchanged).
    """
    night = d.get("shift_type") == "Night"

    # ---- worker pay ----
    base = (worker.base_pay_rate or 0) if worker else 0
    ot_r = (worker.overtime_pay_rate or 0) if worker else 0
    wknd = (worker.weekend_pay_rate or 0) if worker else 0
    night_r = (worker.night_pay_rate or 0) if worker else 0
    travel = (worker.travel_allowance or 0) if worker else 0
    demo = (worker.demo_allowance or 0) if worker else 0
    ord_pay_rate = night_r if (night and night_r > 0) else base
    pay = (
        d["ordinary"] * ord_pay_rate
        + d["ot"] * ot_r
        + (d["ot_sat"] + d["ot_sun"]) * wknd
        + d["total"] * demo
        + travel
    )

    # ---- client charge ----
    b_ord = (client.hourly_billing_rate or 0) if client else 0
    b_ot = (client.overtime_billing_rate or 0) if client else 0
    b_wknd = (client.weekend_billing_rate or 0) if client else 0
    b_night = (client.night_billing_rate or 0) if client else 0
    c_travel = (client.travel_charge_per_day or 0) if client else 0
    c_tool = (client.tool_hire_per_day or 0) if client else 0
    ord_charge_rate = b_night if (night and b_night > 0) else b_ord
    charge = (
        d["ordinary"] * ord_charge_rate
        + d["ot"] * b_ot
        + (d["ot_sat"] + d["ot_sun"]) * b_wknd
        + c_travel
        + c_tool
    )

    return {"pay": round(pay, 2), "charge": round(charge, 2)}


def _week_ending_for(d: date) -> date:
    """Friday that ends the Sat->Fri week containing date d."""
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _resolve_week(week_ending: Optional[str]):
    if week_ending:
        we = date.fromisoformat(week_ending)
    else:
        we = _week_ending_for(date.today())
    ws = we - timedelta(days=6)
    return ws, we


def _derive(entry: TimesheetEntry) -> dict:
    """Split a single day's hours into the billing columns."""
    total = float(entry.total_hours or 0)
    wd = entry.entry_date.weekday()  # Mon=0 .. Sun=6
    ordinary = ot = ot_sat = ot_sun = 0.0
    if wd == 5:        # Saturday
        ot_sat = total
    elif wd == 6:      # Sunday
        ot_sun = total
    else:              # Mon-Fri
        ordinary = min(8.0, total)
        ot = max(0.0, total - 8.0)

    shift_type = "Day"
    if entry.time_start is not None:
        shift_type = "Night" if entry.time_start.hour >= 18 else "Day"

    role = (entry.worked_as or "").strip() or "Reg"

    return {
        "ordinary": round(ordinary, 2),
        "ot": round(ot, 2),
        "ot_sat": round(ot_sat, 2),
        "ot_sun": round(ot_sun, 2),
        "total": round(total, 2),
        "shift_type": shift_type,
        "role": role,
    }


def _job_address(job_site: Optional[JobSite], entry: TimesheetEntry) -> str:
    if job_site:
        addr = (job_site.address or "").strip() or (job_site.name or "").strip()
        if addr:
            return addr
    for candidate in (entry.clock_in_address, entry.host_company_name):
        if candidate and candidate.strip():
            return candidate.strip()
    return "Unassigned"


async def _fetch_rows(db, ws, we, client_id, approved_only):
    """Return derived row dicts for every worked day in the week."""
    q = (
        select(TimesheetEntry, Timesheet, User, Client, JobSite)
        .join(Timesheet, TimesheetEntry.timesheet_id == Timesheet.id)
        .join(User, Timesheet.worker_id == User.id)
        .outerjoin(Client, Timesheet.client_id == Client.id)
        .outerjoin(JobSite, TimesheetEntry.job_site_id == JobSite.id)
        .where(Timesheet.archived_at.is_(None))
        .where(TimesheetEntry.entry_date >= ws)
        .where(TimesheetEntry.entry_date <= we)
    )
    if client_id:
        q = q.where(Timesheet.client_id == client_id)
    if approved_only:
        q = q.where(TimesheetEntry.entry_status == "approved")

    result = await db.execute(q)
    rows = []
    for entry, ts, worker, client, job_site in result.all():
        if (entry.total_hours or 0) <= 0:
            continue
        derived = _derive(entry)
        amounts = _amounts(derived, worker, client)
        rows.append({
            "entry_id": entry.id,
            "date": entry.entry_date,
            "day": entry.day_of_week or DAY_ABBR[entry.entry_date.weekday()],
            "worker": f"{worker.first_name} {worker.surname}".strip() if worker else "Unknown",
            "worker_id": worker.id if worker else None,
            "client": (client.name if client else None) or "No Client",
            "client_id": ts.client_id,
            "job_address": _job_address(job_site, entry),
            **derived,
            **amounts,
        })
    return rows


@router.get("/weeks")
async def list_weeks(db: AsyncSession = Depends(get_db)):
    """Distinct billing week-ending Fridays that have timesheet data."""
    result = await db.execute(
        select(TimesheetEntry.entry_date)
        .join(Timesheet, TimesheetEntry.timesheet_id == Timesheet.id)
        .where(Timesheet.archived_at.is_(None))
    )
    weeks = set()
    for (d,) in result.all():
        if d:
            weeks.add(_week_ending_for(d))
    default = _week_ending_for(date.today())
    weeks.add(default)
    return {
        "weeks": [w.isoformat() for w in sorted(weeks, reverse=True)],
        "default": default.isoformat(),
    }


@router.get("/client-billing")
async def client_billing(
    week_ending: Optional[str] = None,
    client_id: Optional[int] = None,
    approved_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Pivot: Client -> Job_Address -> Date -> Worker, with subtotals."""
    ws, we = _resolve_week(week_ending)
    rows = await _fetch_rows(db, ws, we, client_id, approved_only)

    clients = {}
    grand = _zero()

    for r in rows:
        c = clients.setdefault(r["client"], {"client": r["client"], "totals": _zero(), "_addrs": {}})
        a = c["_addrs"].setdefault(r["job_address"], {"address": r["job_address"], "totals": _zero(), "_dates": {}})
        dkey = r["date"].isoformat()
        d = a["_dates"].setdefault(dkey, {"date": dkey, "day": r["day"], "totals": _zero(), "rows": []})
        d["rows"].append({
            "worker": r["worker"],
            "shift_type": r["shift_type"],
            "role": r["role"],
            "ordinary": r["ordinary"],
            "ot": r["ot"],
            "ot_sat": r["ot_sat"],
            "ot_sun": r["ot_sun"],
            "total": r["total"],
            "charge": r["charge"],
            "pay": r["pay"],
        })
        _accumulate(d["totals"], r)
        _accumulate(a["totals"], r)
        _accumulate(c["totals"], r)
        _accumulate(grand, r)

    client_list = []
    for c in sorted(clients.values(), key=lambda x: x["client"].lower()):
        addr_list = []
        for a in sorted(c["_addrs"].values(), key=lambda x: x["address"].lower()):
            date_list = []
            for dkey in sorted(a["_dates"].keys()):
                d = a["_dates"][dkey]
                d["rows"].sort(key=lambda x: x["worker"].lower())
                date_list.append(d)
            addr_list.append({"address": a["address"], "totals": a["totals"], "dates": date_list})
        client_list.append({"client": c["client"], "totals": c["totals"], "addresses": addr_list})

    return {
        "week_ending": we.isoformat(),
        "week_start": ws.isoformat(),
        "clients": client_list,
        "grand_total": grand,
    }


@router.get("/worker-totals")
async def worker_totals(
    week_ending: Optional[str] = None,
    approved_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Worker -> total hours for the week (cross-check against billing)."""
    ws, we = _resolve_week(week_ending)
    rows = await _fetch_rows(db, ws, we, None, approved_only)

    workers = {}
    grand = _zero()
    for r in rows:
        w = workers.setdefault(r["worker"], _zero())
        _accumulate(w, r)
        _accumulate(grand, r)

    worker_list = [
        {"worker": name, **totals}
        for name, totals in sorted(workers.items(), key=lambda x: x[0].lower())
    ]
    return {
        "week_ending": we.isoformat(),
        "week_start": ws.isoformat(),
        "workers": worker_list,
        "grand_total": grand,
    }


@router.get("/myob-payroll")
async def myob_payroll(
    week_ending: Optional[str] = None,
    approved_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Worker -> Shift_Type -> Role -> summed hours (payroll entry)."""
    ws, we = _resolve_week(week_ending)
    rows = await _fetch_rows(db, ws, we, None, approved_only)

    groups = {}
    grand = _zero()
    for r in rows:
        key = (r["worker"], r["shift_type"], r["role"])
        g = groups.setdefault(key, _zero())
        _accumulate(g, r)
        _accumulate(grand, r)

    payroll = [
        {"worker": w, "shift_type": st, "role": role, **totals}
        for (w, st, role), totals in sorted(groups.items(), key=lambda x: (x[0][0].lower(), x[0][1], x[0][2]))
    ]
    return {
        "week_ending": we.isoformat(),
        "week_start": ws.isoformat(),
        "rows": payroll,
        "grand_total": grand,
    }
