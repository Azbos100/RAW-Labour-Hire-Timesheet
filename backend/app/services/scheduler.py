"""
RAW Labour Hire - Automatic Reminder Scheduler
Sends clock-in/out reminders at configured times
"""

import asyncio
from datetime import datetime, time, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# Australian Eastern timezone
TIMEZONE = pytz.timezone('Australia/Melbourne')

scheduler = AsyncIOScheduler(timezone=TIMEZONE)


async def check_clock_in_reminders():
    """Check and send clock-in reminders"""
    from ..database import AsyncSessionLocal
    from ..routes.notifications import check_clock_in_reminders as send_reminders
    
    print(f"[Scheduler] Running clock-in reminder check at {datetime.now(TIMEZONE)}")
    
    try:
        async with AsyncSessionLocal() as db:
            result = await send_reminders(db)
            print(f"[Scheduler] Clock-in reminders result: {result}")
    except Exception as e:
        print(f"[Scheduler] Error sending clock-in reminders: {e}")


async def check_clock_out_reminders():
    """Check and send clock-out reminders"""
    from ..database import AsyncSessionLocal
    from ..routes.notifications import check_clock_out_reminders as send_reminders
    
    print(f"[Scheduler] Running clock-out reminder check at {datetime.now(TIMEZONE)}")
    
    try:
        async with AsyncSessionLocal() as db:
            result = await send_reminders(db)
            print(f"[Scheduler] Clock-out reminders result: {result}")
    except Exception as e:
        print(f"[Scheduler] Error sending clock-out reminders: {e}")


async def check_push_receipts():
    """Verify Expo delivery receipts and clear any permanently-dead tokens so
    future notifications fall back to SMS."""
    from .push_receipts import check_pending_receipts

    try:
        await check_pending_receipts()
    except Exception as e:
        print(f"[Scheduler] Error checking push receipts: {e}")


async def auto_archive_prior_pay_week():
    """
    Auto-archive approved timesheets from prior pay week (Fri→Thu).
    Runs every Friday at 7am Melbourne time.
    """
    from ..database import AsyncSessionLocal
    from ..routes.timesheets import archive_prior_pay_week

    print(f"[Scheduler] Running weekly auto-archive at {datetime.now(TIMEZONE)}")

    try:
        async with AsyncSessionLocal() as db:
            result = await archive_prior_pay_week(db)
            print(f"[Scheduler] Auto-archive result: {result}")
    except Exception as e:
        print(f"[Scheduler] Error during auto-archive: {e}")


def _parse_csv_ids(value):
    """CSV string of user ids -> list[int] (tolerant of blanks/garbage)."""
    if not value:
        return []
    out = []
    for part in str(value).split(','):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError:
                pass
    return out


def _parse_csv_phones(value):
    """CSV string of phone numbers -> list[str] (trimmed, blanks dropped)."""
    if not value:
        return []
    return [p.strip() for p in str(value).split(',') if p.strip()]


def _chunk_sms(text, limit=1400):
    """Split a long SMS body into gateway-safe chunks (max ~1400 chars each).

    Splits on line boundaries so a worker's line is never cut in half, and
    prefixes each part with "(i/n)" when more than one part is needed.
    """
    lines = text.split("\n")
    chunks, current = [], ""
    for line in lines:
        # Hard-split any single line that is somehow longer than the limit.
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = line if not current else current + "\n" + line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)

    if len(chunks) <= 1:
        return chunks or [text]
    total = len(chunks)
    return [f"({i}/{total}) {c}" for i, c in enumerate(chunks, 1)]


async def _deliver_notice(db, recipient_ids, extra_phones, title, body, data, sms_enabled, notice_label, prefer_sms=False):
    """Send a notice to a set of worker recipients plus a set of raw phone
    numbers (SMS only). Looked up live so we always use the latest token/phone
    for each worker.

    By default worker recipients get a push (SMS fallback). When prefer_sms is
    True we text them instead (falling back to push only if they have no phone),
    so notices like the roster digest reliably land as an SMS.
    """
    from sqlalchemy import select
    from ..models import User
    from .push_notifications import send_push_notification
    from .sms import send_sms, format_phone_number

    sms_body = f"RAW: {title}. {body}"
    sms_parts = _chunk_sms(sms_body)

    # Track numbers we've already texted (in E.164) so a recipient who is both a
    # worker and an extra number doesn't get the same SMS twice.
    texted = set()

    async def _sms_once(phone, who, worker_id=None):
        fp = format_phone_number(phone) if phone else ""
        if not fp or fp in texted:
            return False
        texted.add(fp)
        msg_type = "allocation_notice" if "allocation" in notice_label.lower() else (
            "roster_digest" if "roster" in notice_label.lower() else "notice"
        )
        for part in sms_parts:
            result = await send_sms(
                phone, part,
                recipient_name=who,
                worker_id=worker_id,
                message_type=msg_type,
            )
            print(f"[Scheduler] {notice_label} SMS -> {who} ({fp}): {result}")
        return True

    recipients = []
    if recipient_ids:
        recipients = (await db.execute(
            select(User).where(User.id.in_(recipient_ids))
        )).scalars().all()

    sent = 0
    for r in recipients:
        who = f"{r.first_name} {r.surname}"
        can_sms = bool(r.phone and sms_enabled)
        if prefer_sms and can_sms:
            if await _sms_once(r.phone, who, r.id):
                sent += 1
        elif r.push_token:
            from .push_notifications import ticket_status
            from .push_receipts import handle_push_result
            push_result = await send_push_notification(r.push_token, title, body, data)
            push_ok = push_result.get("success") and ticket_status(push_result.get("result")) != "error"
            # Record receipt (if accepted) or clear a dead token (blanks r.push_token).
            await handle_push_result(r, push_result)
            print(f"[Scheduler] {notice_label} push -> {who}: ok={push_ok}")
            if push_ok:
                sent += 1
            elif can_sms and await _sms_once(r.phone, who, r.id):
                # Push failed (e.g. dead token) — fall back to SMS like the worker path.
                sent += 1
            else:
                print(f"[Scheduler] {notice_label}: push failed for {who} and no SMS fallback")
        elif can_sms:
            if await _sms_once(r.phone, who, r.id):
                sent += 1
        else:
            print(f"[Scheduler] {notice_label}: {who} has no push token / usable SMS; skipped")

    if sms_enabled:
        for phone in extra_phones:
            if await _sms_once(phone, "extra"):
                sent += 1
    elif extra_phones:
        print(f"[Scheduler] {notice_label}: SMS disabled; skipped {len(extra_phones)} extra number(s)")

    if sent == 0:
        print(f"[Scheduler] {notice_label}: no deliverable recipients")
    return sent


async def notify_unaccepted_allocations():
    """Notify the chosen people of workers who haven't accepted tomorrow's jobs.

    Runs Mon-Fri at the configured time (default 18:15). "Haven't accepted" =
    assigned for tomorrow with assignment_accepted still pending (None) or
    declined (False). Recipients are the configured workers + extra phones; if
    none are configured it defaults to Joshua McPherson.
    """
    from ..database import AsyncSessionLocal
    from sqlalchemy import select, func, or_
    from ..models import User, NotificationSettings, WorkerAssignment

    tomorrow = (datetime.now(TIMEZONE) + timedelta(days=1)).date()
    print(f"[Scheduler] Running unaccepted-allocation notice for {tomorrow}")

    try:
        async with AsyncSessionLocal() as db:
            settings = (await db.execute(select(NotificationSettings).limit(1))).scalar_one_or_none()
            if settings and settings.allocation_notice_enabled is False:
                print("[Scheduler] Allocation notice disabled in settings; skipping")
                return
            sms_enabled = settings.sms_enabled if settings else True

            recipient_ids = _parse_csv_ids(settings.allocation_notice_recipient_ids) if settings else []
            extra_phones = _parse_csv_phones(settings.allocation_notice_extra_phones) if settings else []

            # Default to Joshua McPherson when nobody is configured.
            if not recipient_ids and not extra_phones:
                josh = (await db.execute(
                    select(User).where(
                        func.lower(User.first_name) == "joshua",
                        func.lower(User.surname) == "mcpherson",
                    )
                )).scalars().first()
                if josh:
                    recipient_ids = [josh.id]
                else:
                    print("[Scheduler] No allocation-notice recipient configured and no Joshua McPherson; skipping")
                    return

            # Active workers assigned for tomorrow who haven't accepted yet.
            rows = (await db.execute(
                select(User, WorkerAssignment)
                .join(WorkerAssignment, WorkerAssignment.worker_id == User.id)
                .where(
                    User.is_active == True,  # noqa: E712
                    WorkerAssignment.assignment_date == tomorrow,
                    or_(
                        WorkerAssignment.accepted.is_(None),
                        WorkerAssignment.accepted.is_(False),
                    ),
                ).order_by(User.surname, User.first_name)
            )).all()

            date_label = tomorrow.strftime("%a %d %b")
            if rows:
                lines = []
                for w, wa in rows:
                    status = "declined" if wa.accepted is False else "pending"
                    lines.append(f"{w.first_name} {w.surname} ({status})")
                title = f"{len(rows)} not accepted for tomorrow"
                body = f"{date_label} — not accepted:\n" + "\n".join(lines)
            else:
                title = "All jobs accepted for tomorrow"
                body = f"All allocated workers have accepted their jobs for {date_label}."

            await _deliver_notice(
                db, recipient_ids, extra_phones, title, body,
                {"type": "allocation_acceptance_summary", "date": tomorrow.isoformat()},
                sms_enabled, "Allocation notice",
            )
    except Exception as e:
        print(f"[Scheduler] Error sending unaccepted-allocation notice: {e}")


async def send_roster_digest():
    """Send a daily roster digest: who's out (allocated) vs who's still
    available (unallocated) for the next day. Runs every day at the configured
    time (default 19:00) to the configured recipients + extra phones.
    """
    from ..database import AsyncSessionLocal
    from sqlalchemy import select
    from ..models import User, NotificationSettings, UserRole, JobSite, Client, WorkerAssignment

    tomorrow = (datetime.now(TIMEZONE) + timedelta(days=1)).date()
    print(f"[Scheduler] Running roster digest for {tomorrow}")

    try:
        async with AsyncSessionLocal() as db:
            settings = (await db.execute(select(NotificationSettings).limit(1))).scalar_one_or_none()
            if settings and settings.roster_digest_enabled is False:
                print("[Scheduler] Roster digest disabled in settings; skipping")
                return
            sms_enabled = settings.sms_enabled if settings else True

            recipient_ids = _parse_csv_ids(settings.roster_digest_recipient_ids) if settings else []
            extra_phones = _parse_csv_phones(settings.roster_digest_extra_phones) if settings else []
            if not recipient_ids and not extra_phones:
                print("[Scheduler] Roster digest has no recipients configured; skipping")
                return

            workers = (await db.execute(
                select(User).where(
                    User.is_active == True,  # noqa: E712
                    User.role == UserRole.WORKER,
                ).order_by(User.surname, User.first_name)
            )).scalars().all()

            assignment_rows = (await db.execute(
                select(WorkerAssignment, User)
                .join(User, WorkerAssignment.worker_id == User.id)
                .where(
                    WorkerAssignment.assignment_date == tomorrow,
                    User.is_active == True,  # noqa: E712
                )
            )).all()

            assigned_worker_ids = {u.id for _, u in assignment_rows}
            out = [u for u in workers if u.id in assigned_worker_ids]
            available = [u for u in workers if u.id not in assigned_worker_ids]

            site_ids = list({wa.job_site_id for wa, _ in assignment_rows})
            sites_map = {}
            if site_ids:
                site_rows = (await db.execute(
                    select(JobSite, Client.name)
                    .outerjoin(Client, JobSite.client_id == Client.id)
                    .where(JobSite.id.in_(site_ids))
                )).all()
                for js, client_name in site_rows:
                    sites_map[js.id] = (client_name, js.name, js.address)

            assignment_by_worker = {u.id: wa for wa, u in assignment_rows}
            accepted_count = sum(1 for wa, _ in assignment_rows if wa.accepted is True)
            pending_count = len(assignment_rows) - accepted_count

            def _out_line(w):
                wa = assignment_by_worker.get(w.id)
                client_name, site_name, address = sites_map.get(
                    wa.job_site_id if wa else None, (None, "Unknown site", None)
                )
                parts = [f"{w.first_name} {w.surname}:"]
                where = " / ".join(p for p in (client_name, site_name) if p)
                if where:
                    parts.append(where)
                if address:
                    parts.append(f"@ {address}")
                if wa and wa.start_time:
                    parts.append(f"start {wa.start_time}")
                if wa and wa.contact_name:
                    foreman = wa.contact_name
                    if wa.contact_phone:
                        foreman += f" {wa.contact_phone}"
                    parts.append(f"foreman {foreman}")
                status = "accepted" if wa and wa.accepted is True else ("declined" if wa and wa.accepted is False else "not accepted")
                parts.append(f"[{status}]")
                return "  - " + " ".join(parts)

            date_label = tomorrow.strftime("%a %d %b")
            out_block = "\n".join(_out_line(w) for w in out) if out else "  - none"
            avail_block = "\n".join(f"  - {w.first_name} {w.surname}" for w in available) if available else "  - none"
            title = (
                f"Roster {date_label}: {len(out)} allocated "
                f"({accepted_count} accepted, {pending_count} pending), "
                f"{len(available)} available"
            )
            body = (
                f"Roster for {date_label}\n"
                f"{accepted_count} accepted · {pending_count} still pending\n\n"
                f"ALLOCATED ({len(out)}):\n{out_block}\n\n"
                f"AVAILABLE ({len(available)}):\n{avail_block}"
            )

            await _deliver_notice(
                db, recipient_ids, extra_phones, title, body,
                {"type": "roster_digest", "date": tomorrow.isoformat()},
                sms_enabled, "Roster digest",
            )
    except Exception as e:
        print(f"[Scheduler] Error sending roster digest: {e}")


def _parse_reminder_time(value):
    """Return (hour, minute) from a reminder time value.

    The DB column is a Time, so SQLAlchemy gives us a datetime.time; but tolerate
    an "HH:MM" string too in case of legacy/manually-entered data.
    """
    if isinstance(value, time):
        return value.hour, value.minute
    parts = str(value).split(':')
    return int(parts[0]), int(parts[1])


async def load_settings_from_db():
    """Load notification settings from database and update scheduler times"""
    from ..database import AsyncSessionLocal
    from sqlalchemy import select
    from ..models import NotificationSettings
    
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(NotificationSettings).limit(1))
            settings = result.scalar_one_or_none()
            
            if settings:
                # clock_*_reminder_time is a Time column -> datetime.time object.
                # (Older data / manual edits may store it as an "HH:MM" string, so
                # handle both forms.)
                if settings.clock_in_reminder_time:
                    try:
                        hour, minute = _parse_reminder_time(settings.clock_in_reminder_time)
                        update_clock_in_time(hour, minute)
                        print(f"[Scheduler] Loaded clock-in time from DB: {hour:02d}:{minute:02d}")
                    except Exception as e:
                        print(f"[Scheduler] Error parsing clock-in time: {e}")
                
                if settings.clock_out_reminder_time:
                    try:
                        hour, minute = _parse_reminder_time(settings.clock_out_reminder_time)
                        update_clock_out_time(hour, minute)
                        print(f"[Scheduler] Loaded clock-out time from DB: {hour:02d}:{minute:02d}")
                    except Exception as e:
                        print(f"[Scheduler] Error parsing clock-out time: {e}")

                if getattr(settings, 'allocation_notice_time', None):
                    try:
                        hour, minute = _parse_reminder_time(settings.allocation_notice_time)
                        update_allocation_notice_time(hour, minute)
                        print(f"[Scheduler] Loaded allocation notice time from DB: {hour:02d}:{minute:02d}")
                    except Exception as e:
                        print(f"[Scheduler] Error parsing allocation notice time: {e}")

                if getattr(settings, 'roster_digest_time', None):
                    try:
                        hour, minute = _parse_reminder_time(settings.roster_digest_time)
                        update_roster_digest_time(hour, minute)
                        print(f"[Scheduler] Loaded roster digest time from DB: {hour:02d}:{minute:02d}")
                    except Exception as e:
                        print(f"[Scheduler] Error parsing roster digest time: {e}")
            else:
                print("[Scheduler] No settings in DB, using defaults")
    except Exception as e:
        print(f"[Scheduler] Error loading settings from DB: {e}")


def setup_scheduler():
    """Setup the scheduler with default jobs (will be updated from DB later)"""
    # NOTE: pass the coroutine functions DIRECTLY (not wrapped in a lambda that
    # calls asyncio.create_task). AsyncIOScheduler awaits coroutine jobs on the
    # event loop; a plain lambda runs on a worker thread with no running loop, so
    # asyncio.create_task() raised "no running event loop" and the reminder never
    # actually ran.
    # Default: Clock-in reminder at 6:55 AM Melbourne time on weekdays
    scheduler.add_job(
        check_clock_in_reminders,
        CronTrigger(hour=6, minute=55, day_of_week='mon-fri', timezone=TIMEZONE),
        id='clock_in_reminder',
        replace_existing=True,
        name='Clock-In Reminder'
    )
    
    # Default: Clock-out reminder at 3:30 PM Melbourne time on weekdays
    scheduler.add_job(
        check_clock_out_reminders,
        CronTrigger(hour=15, minute=30, day_of_week='mon-fri', timezone=TIMEZONE),
        id='clock_out_reminder',
        replace_existing=True,
        name='Clock-Out Reminder'
    )

    # Weekly auto-archive: Every Friday at 7:00 AM Melbourne time
    # Archives approved timesheets from the prior pay week (Fri→Thu).
    scheduler.add_job(
        auto_archive_prior_pay_week,
        CronTrigger(hour=7, minute=0, day_of_week='fri', timezone=TIMEZONE),
        id='weekly_auto_archive',
        replace_existing=True,
        name='Weekly Auto-Archive (Prior Pay Week)'
    )

    # Unaccepted-allocation notice: Mon-Fri at 6:15 PM (default) with the workers
    # who haven't accepted tomorrow's jobs.
    scheduler.add_job(
        notify_unaccepted_allocations,
        CronTrigger(hour=18, minute=15, day_of_week='mon-fri', timezone=TIMEZONE),
        id='unaccepted_allocations_notice',
        replace_existing=True,
        name='Unaccepted Allocations Notice'
    )

    # Daily roster digest: every day at 7:00 PM (default) — who's out vs available.
    scheduler.add_job(
        send_roster_digest,
        CronTrigger(hour=19, minute=0, timezone=TIMEZONE),
        id='roster_digest',
        replace_existing=True,
        name='Daily Roster Digest'
    )

    # Push receipt verification: every 20 minutes, check delivery receipts for
    # pushes sent >15 min ago and clear any dead tokens (self-healing fallback).
    scheduler.add_job(
        check_push_receipts,
        CronTrigger(minute='*/20', timezone=TIMEZONE),
        id='push_receipt_check',
        replace_existing=True,
        name='Push Receipt Check'
    )

    print("[Scheduler] Initial reminders scheduled (defaults):")
    print("  - Clock-in reminder: 6:55 AM AEST/AEDT (Mon-Fri)")
    print("  - Clock-out reminder: 3:30 PM AEST/AEDT (Mon-Fri)")
    print("  - Weekly auto-archive: 7:00 AM AEST/AEDT (Fri)")
    print("  - Unaccepted allocations notice: 6:15 PM AEST/AEDT (Mon-Fri)")
    print("  - Daily roster digest: 7:00 PM AEST/AEDT (every day)")
    print("  - Push receipt check: every 20 min")


def update_clock_in_time(hour: int, minute: int):
    """Update the clock-in reminder time"""
    scheduler.reschedule_job(
        'clock_in_reminder',
        trigger=CronTrigger(hour=hour, minute=minute, day_of_week='mon-fri', timezone=TIMEZONE)
    )
    print(f"[Scheduler] Clock-in reminder rescheduled to {hour:02d}:{minute:02d}")


def update_clock_out_time(hour: int, minute: int):
    """Update the clock-out reminder time"""
    scheduler.reschedule_job(
        'clock_out_reminder',
        trigger=CronTrigger(hour=hour, minute=minute, day_of_week='mon-fri', timezone=TIMEZONE)
    )
    print(f"[Scheduler] Clock-out reminder rescheduled to {hour:02d}:{minute:02d}")


def update_allocation_notice_time(hour: int, minute: int):
    """Update the unaccepted-allocations notice time (Mon-Fri)"""
    scheduler.reschedule_job(
        'unaccepted_allocations_notice',
        trigger=CronTrigger(hour=hour, minute=minute, day_of_week='mon-fri', timezone=TIMEZONE)
    )
    print(f"[Scheduler] Allocation notice rescheduled to {hour:02d}:{minute:02d}")


def update_roster_digest_time(hour: int, minute: int):
    """Update the daily roster digest time (every day)"""
    scheduler.reschedule_job(
        'roster_digest',
        trigger=CronTrigger(hour=hour, minute=minute, timezone=TIMEZONE)
    )
    print(f"[Scheduler] Roster digest rescheduled to {hour:02d}:{minute:02d}")


def start_scheduler():
    """Start the scheduler"""
    if not scheduler.running:
        setup_scheduler()
        scheduler.start()
        print("[Scheduler] Started")
        # Schedule loading settings from DB (needs to run in async context)
        asyncio.get_event_loop().create_task(load_settings_from_db())


def stop_scheduler():
    """Stop the scheduler"""
    if scheduler.running:
        scheduler.shutdown()
        print("[Scheduler] Stopped")
