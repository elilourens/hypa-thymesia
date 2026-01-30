"""Celery app initialization for formatting service."""
import os
import sys
from celery import Celery

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create Celery app
celery_app = Celery(__name__)

# Load configuration from celery_config module
celery_app.config_from_object("app.celery_config")

# Import tasks manually to avoid autodiscovery issues
try:
    from . import celery_tasks
except ImportError:
    try:
        from app import celery_tasks
    except ImportError:
        # Tasks module not yet available - will be imported at runtime
        pass

@celery_app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
