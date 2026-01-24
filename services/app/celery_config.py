"""Celery configuration for formatting service."""
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
worker_prefetch_multiplier = 1
worker_max_tasks_per_child = 50
task_acks_late = True
task_reject_on_worker_lost = True

# Task routing
task_routes = {
    "celery_tasks.tag_image": {"queue": "formatting_queue"},
    "celery_tasks.tag_document": {"queue": "formatting_queue"},
    "celery_tasks.format_chunks": {"queue": "formatting_queue"},
}

# Task-specific configurations
task_default_retry_delay = 30
task_max_retries = 2

# Celery beat schedule
beat_schedule = {}
