import pytz
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(jobstores={"default": MemoryJobStore()})
scheduler.configure(timezone=pytz.timezone("UTC"))
