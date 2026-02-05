"""
RAW Labour Hire - Automatic Reminder Scheduler
Sends clock-in/out reminders at configured times
"""

import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# Australian Eastern timezone
TIMEZONE = pytz.timezone('Australia/Sydney')

scheduler = AsyncIOScheduler(timezone=TIMEZONE)


async def check_clock_in_reminders():
    """Check and send clock-in reminders"""
    from ..database import AsyncSessionLocal
    from ..routes.notifications import check_clock_in_reminders as send_reminders
    
    print(f"[Scheduler] Running clock-in reminder check at {datetime.now(TIMEZONE)}")
    
    try:
        async with AsyncSessionLocal() as db:
            # Create a mock request-like context
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


def setup_scheduler():
    """Setup the scheduler with default jobs"""
    # Clock-in reminder at 7:00 AM Sydney time on weekdays
    scheduler.add_job(
        lambda: asyncio.create_task(check_clock_in_reminders()),
        CronTrigger(hour=7, minute=0, day_of_week='mon-fri', timezone=TIMEZONE),
        id='clock_in_reminder',
        replace_existing=True,
        name='Clock-In Reminder'
    )
    
    # Clock-out reminder at 5:00 PM Sydney time on weekdays
    scheduler.add_job(
        lambda: asyncio.create_task(check_clock_out_reminders()),
        CronTrigger(hour=17, minute=0, day_of_week='mon-fri', timezone=TIMEZONE),
        id='clock_out_reminder',
        replace_existing=True,
        name='Clock-Out Reminder'
    )
    
    print("[Scheduler] Automatic reminders scheduled:")
    print("  - Clock-in reminder: 7:00 AM AEST (Mon-Fri)")
    print("  - Clock-out reminder: 5:00 PM AEST (Mon-Fri)")


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


def stop_scheduler():
    """Stop the scheduler"""
    if scheduler.running:
        scheduler.shutdown()
        print("[Scheduler] Stopped")
