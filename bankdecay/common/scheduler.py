import os

import pytz
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

if "TZ" not in os.environ:
    os.environ["TZ"] = "UTC"
scheduler = AsyncIOScheduler(jobstores={"default": MemoryJobStore()})
scheduler.configure(timezone=pytz.timezone("UTC"))
