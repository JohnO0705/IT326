"""Run scheduled reminders while the API is running."""

import asyncio
import logging

from ITask import utc_now
from backend.repository import TaskBuddyRepository
from backend.services import ReminderService

LOGGER = logging.getLogger("taskbuddy")


async def run_reminder_worker(database, sender, settings, stop: asyncio.Event):
    def deliver():
        with database.session() as session:
            service = ReminderService(TaskBuddyRepository(session), sender)
            return service.send_due_reminders(utc_now())

    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.reminder_poll_seconds)
        except asyncio.TimeoutError:
            try:
                await asyncio.to_thread(deliver)
            except Exception:
                LOGGER.exception("The reminder check failed; it will be retried.")
