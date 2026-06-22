"""
RAW Labour Hire - Automatic Reminder Scheduler
Sends clock-in/out reminders at configured times
"""

import asyncio
from datetime import datetime, time
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

    print("[Scheduler] Initial reminders scheduled (defaults):")
    print("  - Clock-in reminder: 6:55 AM AEST/AEDT (Mon-Fri)")
    print("  - Clock-out reminder: 3:30 PM AEST/AEDT (Mon-Fri)")
    print("  - Weekly auto-archive: 7:00 AM AEST/AEDT (Fri)")


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
