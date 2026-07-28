from celery import Celery

from app.core.config import settings

celery = Celery(
    "cholavin",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery.conf.update(
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "drain-outbox": {
            "task": "app.workers.tasks.drain_outbox",
            "schedule": 3.0,  # seconds
        }
    },
)
