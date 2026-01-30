"""Celery configuration for formatting/tagging service."""

import os
from kombu import Exchange, Queue

# Broker and result backend
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# Result backend settings
result_expires = 86400  # 24 hours
result_extended = True  # Store additional metadata

# Task settings
task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]
timezone = "UTC"
enable_utc = True

# Worker settings
worker_prefetch_multiplier = 1  # One task at a time (long-running tasks)
worker_max_tasks_per_child = 50  # Restart worker after 50 tasks (memory cleanup)
task_acks_late = True  # Acknowledge after task completion (safer for crashes)
task_reject_on_worker_lost = True  # Requeue if worker crashes

# Rate limits
task_default_rate_limit = "10/m"  # 10 tasks per minute default

# Queue definitions
task_queues = (
    Queue("backend_queue", Exchange("backend"), routing_key="backend.*"),
    Queue("formatting_queue", Exchange("formatting"), routing_key="formatting.*"),
    Queue("video_queue", Exchange("video"), routing_key="video.*"),
)

# Task routing
task_routes = {
    "backend.celery_tasks.*": {"queue": "backend_queue"},
    "app.celery_tasks.*": {"queue": "formatting_queue"},
    "video.celery_tasks.*": {"queue": "video_queue"},
}

# Monitoring
worker_send_task_events = True
task_send_sent_event = True

# Task visibility timeout
broker_connection_retry_on_startup = True
broker_transport_options = {"visibility_timeout": 3600}  # 1 hour
