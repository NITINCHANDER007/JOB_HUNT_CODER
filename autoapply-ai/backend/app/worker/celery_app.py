"""
Celery application setup for AutoApply AI.
"""

import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()


def make_celery(app=None):
    """Create and configure Celery. Can be used standalone or with Flask app context."""
    broker = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

    celery = Celery(
        "autoapply",
        broker=broker,
        backend=backend,
        include=[
            "app.worker.tasks",
        ],
    )

    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_routes={
            "app.worker.tasks.run_application": {"queue": "applications"},
            "app.worker.tasks.sync_gmail": {"queue": "gmail"},
        },
        beat_schedule={},
        broker_connection_retry_on_startup=True,
    )

    if app is not None:
        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)
        celery.Task = ContextTask

    return celery


# Standalone Celery app (used when running `celery worker`)
celery_app = make_celery()
