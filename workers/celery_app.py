"""
Celery configuration and app initialization.
This sets up Celery with Redis as the message broker.
All worker tasks are registered here.
"""

import logging
from celery import Celery
from celery.schedules import crontab

# Import config
from app.config import (
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    CELERY_TASK_SERIALIZER,
    CELERY_ACCEPT_CONTENT,
    CELERY_RESULT_SERIALIZER,
    CELERY_TIMEZONE,
    CELERY_ENABLE_UTC,
    CELERY_TASK_TRACK_STARTED,
    CELERY_TASK_TIME_LIMIT,
    CELERY_TASK_SOFT_TIME_LIMIT,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

celery_app = Celery(
    __name__,
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer=CELERY_TASK_SERIALIZER,
    accept_content=CELERY_ACCEPT_CONTENT,
    result_serializer=CELERY_RESULT_SERIALIZER,
    timezone=CELERY_TIMEZONE,
    enable_utc=CELERY_ENABLE_UTC,
    task_track_started=CELERY_TASK_TRACK_STARTED,
    task_time_limit=CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=CELERY_TASK_SOFT_TIME_LIMIT,
    task_routes={
        'workers.tasks.process_audio_task': {'queue': 'default'},
        'workers.tasks.health_check': {'queue': 'default'},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    task_autoretry_for=(Exception,),
    task_max_retries=3,
)

celery_app.autodiscover_tasks(['workers'])

logger.info(f"✓ Celery configured")
logger.info(f"  Broker: {CELERY_BROKER_URL}")
logger.info(f"  Backend: {CELERY_RESULT_BACKEND}")

@celery_app.task(bind=True, name='workers.tasks.health_check')
def health_check(self):
    return {"status": "worker_ok", "worker_id": self.request.hostname}