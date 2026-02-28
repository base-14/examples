import logging
import os
import time

from celery import Celery
from opentelemetry import trace

logger = logging.getLogger(__name__)

RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")

celery = Celery(
    "tasks",
    broker=f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}//",
    backend=f"redis://{REDIS_HOST}:6379/0",
)


@celery.task
def process_task(task_id: int):
    logger.info(f"Starting to process task {task_id}")
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("process_task") as span:
        span.set_attribute("task_id", task_id)
        logger.info(f"Task {task_id}: Beginning heavy processing")
        # Simulate some heavy processing
        with tracer.start_span("heavy_processing") as processing_span:
            time.sleep(10)
            processing_span.set_attribute("processing_time", 10)

        logger.info(f"Task {task_id}: Processing completed successfully")
        span.set_attribute("status", "completed")
        return {"task_id": task_id, "status": "completed"}
