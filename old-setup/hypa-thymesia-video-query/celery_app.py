"""Celery app initialization for video service."""
import os
from celery import Celery

# Create Celery app
celery_app = Celery(__name__)

# Load configuration
celery_app.config_from_object("celery_config")

# Import tasks manually to avoid autodiscovery issues
try:
    from . import celery_tasks
except ImportError:
    try:
        import celery_tasks
    except ImportError:
        # Tasks module not yet available - will be imported at runtime
        pass

@celery_app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
