"""Celery configuration for backend service."""
import os

# Broker and result backend
broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

# Task configuration
task_serializer = "json"
accept_content = ["json"]
result_serializer = "json"
timezone = "UTC"
enable_utc = True

# Result backend settings
result_expires = 86400  # 24 hours

# Worker settings
worker_prefetch_multiplier = 1  # One task at a time (for long-running tasks)
worker_max_tasks_per_child = 50  # Restart worker after 50 tasks to prevent memory leaks
task_acks_late = True  # Acknowledge after task completes
task_reject_on_worker_lost = True  # Requeue if worker crashes

# Task routing
task_routes = {
    "celery_tasks.ingest_file": {"queue": "backend_queue"},
    "celery_tasks.ingest_video": {"queue": "backend_queue"},
    "celery_tasks.delete_document": {"queue": "backend_queue"},
}

# Task-specific configurations
task_default_retry_delay = 60  # seconds
task_max_retries = 3

# Celery beat schedule (for periodic tasks)
beat_schedule = {}
