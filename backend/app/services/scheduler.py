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
                # Parse clock_in_reminder_time (stored as "HH:MM" string)
                if settings.clock_in_reminder_time:
                    try:
                        parts = settings.clock_in_reminder_time.split(':')
                        hour, minute = int(parts[0]), int(parts[1])
                        update_clock_in_time(hour, minute)
                        print(f"[Scheduler] Loaded clock-in time from DB: {hour:02d}:{minute:02d}")
                    except Exception as e:
                        print(f"[Scheduler] Error parsing clock-in time: {e}")
                
                # Parse clock_out_reminder_time
                if settings.clock_out_reminder_time:
                    try:
                        parts = settings.clock_out_reminder_time.split(':')
                        hour, minute = int(parts[0]), int(parts[1])
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
    # Default: Clock-in reminder at 6:55 AM Melbourne time on weekdays
    scheduler.add_job(
        lambda: asyncio.create_task(check_clock_in_reminders()),
        CronTrigger(hour=6, minute=55, day_of_week='mon-fri', timezone=TIMEZONE),
        id='clock_in_reminder',
        replace_existing=True,
        name='Clock-In Reminder'
    )
    
    # Default: Clock-out reminder at 3:30 PM Melbourne time on weekdays
    scheduler.add_job(
        lambda: asyncio.create_task(check_clock_out_reminders()),
        CronTrigger(hour=15, minute=30, day_of_week='mon-fri', timezone=TIMEZONE),
        id='clock_out_reminder',
        replace_existing=True,
        name='Clock-Out Reminder'
    )

    # Weekly auto-archive: Every Friday at 7:00 AM Melbourne time
    # Archives approved timesheets from the prior pay week (Fri→Thu).
    scheduler.add_job(
        lambda: asyncio.create_task(auto_archive_prior_pay_week()),
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
